import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.core.security import require_roles
from backend.database.connection import get_db
from backend.models.analisis import Analisis
from backend.models.audio import Audio
from backend.models.resultado_analisis import ResultadoAnalisis
from backend.models.usuario import Usuario
from backend.schemas.resultados import AnalisisResponse, CandidatoResponse, ResultadoIndividualResponse
from backend.schemas.reutilizacion import ReutilizarAudioRequest, ReutilizarAudioResponse
from backend.services.analysis_reuse_service import reuse_analysis_audio
from backend.services.audit_service import record_event
from backend.services.audio_processing_service import AudioProcessingError, process_audio_copy
from backend.services.audio_service import store_original_audio
from backend.services.identification_service import identify_top_candidates
from backend.services.score_normalization_service import normalize_cosine_for_persistence
from backend.services.threshold_service import exceeds_experimental_threshold, threshold_state

router = APIRouter(prefix="/analisis", tags=["analisis"])
logger = logging.getLogger(__name__)


@router.post("/{analysis_id}/muestra", response_model=ReutilizarAudioResponse, status_code=201)
async def reuse_audio(
    analysis_id: int,
    payload: ReutilizarAudioRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("Administrador", "Investigador")),
) -> ReutilizarAudioResponse:
    return await reuse_analysis_audio(analysis_id, payload, request, db, current_user)


def _cleanup_processed_query(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("No se pudo eliminar un WAV temporal de consulta")


@router.post("/identificacion", response_model=AnalisisResponse, status_code=status.HTTP_201_CREATED)
async def run_identification(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(
        require_roles("Administrador", "Investigador", "Analista")
    ),
) -> AnalisisResponse:
    stored_audio = None
    processing = None
    analysis: Analisis | None = None

    try:
        try:
            stored_audio = await store_original_audio(file, category="consultas")
        except ValueError as error:
            record_event(db, "error_analisis", current_user.id_usuario, request, "archivo_consulta_rechazado")
            raise HTTPException(status_code=400, detail=str(error)) from error

        reference_audio_id = db.scalar(
            select(Audio.id_audio)
            .where(Audio.hash_archivo == stored_audio.sha256)
            .limit(1)
        )
        if reference_audio_id is not None:
            record_event(
                db,
                "analisis_rechazado",
                current_user.id_usuario,
                request,
                "archivo_duplicado_referencia",
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Este archivo ya se encuentra registrado como una muestra de "
                    "referencia. Utilice un audio diferente para realizar el análisis."
                ),
            )

        analysis = Analisis(
            id_usuario=current_user.id_usuario,
            ruta_audio_consulta=stored_audio.path.as_posix(),
            nombre_original=stored_audio.original_name,
            formato_original=stored_audio.extension,
            hash_audio_consulta=stored_audio.sha256,
            estado="pendiente",
        )
        db.add(analysis)
        db.flush()
        db.refresh(analysis)

        processing = process_audio_copy(stored_audio.path, category="consultas")
        analysis.estado = "procesando"

        candidates = identify_top_candidates(db, processing.processed_path, limit=3)
        for candidate in candidates:
            exceeds_threshold = exceeds_experimental_threshold(candidate.similitud_mejor)
            db.add(
                ResultadoAnalisis(
                    id_analisis=analysis.id_analisis,
                    id_persona=candidate.id_persona,
                    similitud=normalize_cosine_for_persistence(candidate.similitud_mejor),
                    posicion=candidate.posicion,
                    supera_umbral=exceeds_threshold,
                )
            )
        analysis.estado = "completado"
        db.commit()
        db.refresh(analysis)
        record_event(db, "analisis_iniciado", current_user.id_usuario, request, f"id_analisis={analysis.id_analisis}")
        record_event(db, "analisis_completado", current_user.id_usuario, request, f"id_analisis={analysis.id_analisis}")

        response_candidates = [
            CandidatoResponse(
                posicion=candidate.posicion,
                id_persona=candidate.id_persona,
                identificador=candidate.identificador,
                nombre=candidate.nombre,
                alias=candidate.alias,
                similitud_mejor=candidate.similitud_mejor,
                similitud_promedio=candidate.similitud_promedio,
                puntuacion_normalizada=normalize_cosine_for_persistence(candidate.similitud_mejor),
                supera_umbral=exceeds_experimental_threshold(candidate.similitud_mejor),
                estado_umbral=threshold_state(
                    exceeds_experimental_threshold(candidate.similitud_mejor)
                ),
                muestras_comparadas=candidate.muestras_comparadas,
                muestras_sin_embedding=candidate.muestras_sin_embedding,
                resultados_individuales=[
                    ResultadoIndividualResponse(id_audio=item.id_audio, similitud=item.similitud)
                    for item in candidate.resultados_individuales
                ],
            )
            for candidate in candidates
        ]
        return AnalisisResponse(
            id_analisis=analysis.id_analisis,
            estado=analysis.estado,
            nombre_original=analysis.nombre_original,
            tipo_analisis="identificacion_1_n",
            estado_coincidencia=threshold_state(
                bool(candidates)
                and exceeds_experimental_threshold(candidates[0].similitud_mejor)
            ),
            candidatos=response_candidates,
        )
    except HTTPException:
        raise
    except (AudioProcessingError, ValueError, FileNotFoundError) as error:
        db.rollback()
        record_event(db, "analisis_fallido", current_user.id_usuario, request, "procesamiento_no_completado")
        raise HTTPException(status_code=400, detail="No se pudo procesar el audio de consulta") from error
    except SQLAlchemyError as error:
        db.rollback()
        record_event(db, "analisis_fallido", current_user.id_usuario, request, "persistencia_no_completada")
        raise HTTPException(status_code=500, detail="No se pudo persistir el análisis") from error
    except Exception as error:
        db.rollback()
        record_event(db, "analisis_fallido", current_user.id_usuario, request, "fallo_interno_controlado")
        raise HTTPException(
            status_code=500,
            detail="No se pudo completar el análisis",
        ) from error
    finally:
        if processing is not None:
            _cleanup_processed_query(processing.processed_path)
