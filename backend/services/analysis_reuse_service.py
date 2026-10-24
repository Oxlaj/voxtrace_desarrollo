import logging

from fastapi import HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.models.analisis import Analisis
from backend.models.audio import Audio
from backend.models.embedding import Embedding
from backend.models.persona import Persona
from backend.models.usuario import Usuario
from backend.schemas.reutilizacion import ReutilizarAudioRequest, ReutilizarAudioResponse
from backend.services.audio_service import copy_analysis_original
from backend.services.audio_processing_service import AudioProcessingError, process_audio_copy
from backend.services.embedding_service import EmbeddingError, generate_embedding, serialize_embedding
from backend.services.audit_service import add_event, record_event, PERSON_CREATED, SAMPLE_ERROR

logger = logging.getLogger(__name__)


def _cleanup_unreferenced_copies(db: Session, stored, processing, analysis_id: int) -> None:
    """Only called after confirmed rollback, before any attempt to commit data."""
    paths = [path for path in (stored.path if stored else None,
                              processing.processed_path if processing else None) if path is not None]
    if not paths:
        return
    try:
        names = [path.as_posix() for path in paths]
        # A processed copy belongs to the same sample: preserve both if either
        # path or the sample hash has a reference. Unavailable DB means keep.
        audio_reference = db.scalar(select(Audio.id_audio).where(or_(
            Audio.ruta_archivo.in_(names), Audio.hash_archivo == stored.sha256,
        )).limit(1))
        analysis_reference = db.scalar(select(Analisis.id_analisis).where(
            Analisis.ruta_audio_consulta.in_(names),
        ).limit(1))
        if audio_reference is not None or analysis_reference is not None:
            logger.warning("Copias conservadas por referencias existentes; revisar reutilización del análisis %s", analysis_id)
            return
    except Exception:
        logger.warning("No se pudo confirmar ausencia de referencias; copias conservadas para revisión del análisis %s", analysis_id)
        return
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("No se pudo limpiar una copia nueva; revisar reutilización del análisis %s", analysis_id)


async def reuse_analysis_audio(
    analysis_id: int, payload: ReutilizarAudioRequest, request: Request,
    db: Session, current_user: Usuario,
) -> ReutilizarAudioResponse:
    # Same global access policy as history; defense in depth for direct callers.
    if current_user.rol.nombre not in {"Administrador", "Investigador"} or current_user.debe_cambiar_password:
        raise HTTPException(403, "No tienes permisos para reutilizar este audio")
    if payload.confirmar is not True:
        raise HTTPException(422, "Debes confirmar la asociación del audio")
    stored = processing = None
    committed = False
    commit_attempted = False
    rollback_confirmed = False
    try:
        analysis = db.get(Analisis, analysis_id)
        if analysis is None:
            raise HTTPException(404, "Análisis no encontrado")
        if analysis.estado != "completado":
            raise HTTPException(409, "El análisis debe estar completado")
        if db.scalar(select(Audio.id_audio).where(Audio.hash_archivo == analysis.hash_audio_consulta)) is not None:
            raise HTTPException(409, "El audio ya está registrado como muestra")
        if payload.nueva_persona is not None:
            if db.scalar(select(Persona.id_persona).where(Persona.identificador == payload.nueva_persona.identificador)) is not None:
                raise HTTPException(409, "El identificador ya está registrado")
            persona = Persona(**payload.nueva_persona.model_dump())
        else:
            persona = db.get(Persona, payload.id_persona)
            if persona is None:
                raise HTTPException(404, "Persona no encontrada")
        stored = await copy_analysis_original(
            analysis.ruta_audio_consulta, analysis.nombre_original,
            analysis.formato_original, analysis.hash_audio_consulta,
        )
        processing = process_audio_copy(stored.path, category="referencias")
        vector = serialize_embedding(generate_embedding(processing.processed_path))
        if payload.nueva_persona is not None:
            db.add(persona)
            db.flush()
            add_event(db, PERSON_CREATED, current_user.id_usuario, request, f"persona_id={persona.id_persona};id_analisis={analysis_id}")
        audio = Audio(
            id_persona=persona.id_persona, id_usuario=current_user.id_usuario,
            ruta_archivo=stored.path.as_posix(), nombre_original=stored.original_name,
            formato_original=stored.extension, duracion_segundos=processing.duration_seconds,
            hash_archivo=stored.sha256,
        )
        db.add(audio)
        db.flush()
        db.add(Embedding(id_audio=audio.id_audio, vector=vector, modelo_utilizado=settings.speechbrain_model_source))
        add_event(db, "audio_analisis_reutilizado", current_user.id_usuario, request,
                  f"id_analisis={analysis_id};persona_id={persona.id_persona};audio_id={audio.id_audio};confirmacion_explicita")
        response = ReutilizarAudioResponse(id_analisis=analysis_id, id_persona=persona.id_persona, id_audio=audio.id_audio)
        commit_attempted = True
        db.commit()
        committed = True
        return response
    except Exception as error:
        try:
            db.rollback()
            rollback_confirmed = True
        except Exception:
            logger.warning("Rollback no confirmado; conservar copias y revisar análisis %s", analysis_id)
        if rollback_confirmed:
            try:
                record_event(db, SAMPLE_ERROR, current_user.id_usuario, request,
                             f"reutilizacion_no_completada;id_analisis={analysis_id};commit_intentado={commit_attempted}")
            except Exception:
                logger.warning("No se pudo registrar el error de reutilización del análisis %s", analysis_id)
        if isinstance(error, HTTPException):
            raise
        if isinstance(error, IntegrityError):
            raise HTTPException(409, "El audio o el identificador ya está registrado") from error
        if isinstance(error, EmbeddingError):
            raise HTTPException(500, "No se pudo generar la representación biométrica") from error
        if isinstance(error, (ValueError, AudioProcessingError)):
            raise HTTPException(400, "No se pudo validar la integridad o procesar el audio original") from error
        if isinstance(error, SQLAlchemyError):
            raise HTTPException(500, "No se pudo guardar la persona y la muestra") from error
        raise HTTPException(500, "No se pudo reutilizar el audio analizado") from error
    finally:
        if not committed and (stored is not None or processing is not None):
            if commit_attempted or not rollback_confirmed:
                # A rollback cannot disprove a server-side commit whose reply
                # was lost. Do not infer failure from the exception type.
                logger.warning("Estado de persistencia no confirmado; copias conservadas para revisión del análisis %s", analysis_id)
            else:
                _cleanup_unreferenced_copies(db, stored, processing, analysis_id)
