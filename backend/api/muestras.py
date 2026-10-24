from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.core.security import require_roles
from backend.database.connection import get_db
from backend.models.audio import Audio
from backend.models.embedding import Embedding
from backend.models.persona import Persona
from backend.models.usuario import Usuario
from backend.schemas.muestra import MuestraRead
from backend.services.audit_service import SAMPLE_ERROR, SAMPLE_UPLOADED, record_event
from backend.services.audio_service import store_original_audio
from backend.services.audio_processing_service import AudioProcessingError, process_audio_copy
from backend.services.embedding_service import EmbeddingError, generate_embedding, serialize_embedding
from backend.core.config import settings

router = APIRouter(prefix="/personas", tags=["muestras"])


@router.get("/{persona_id}/muestras", response_model=list[MuestraRead])
def list_samples(
    persona_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("Administrador", "Investigador", "Analista")),
) -> list[MuestraRead]:
    if db.get(Persona, persona_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Persona no encontrada")
    statement = (
        select(Audio, Embedding.id_embedding)
        .outerjoin(Embedding, Embedding.id_audio == Audio.id_audio)
        .where(Audio.id_persona == persona_id)
        .order_by(Audio.id_audio)
    )
    return [_public_sample(audio, embedding_id is not None) for audio, embedding_id in db.execute(statement).all()]


@router.get("/{persona_id}/muestras/{audio_id}", response_model=MuestraRead)
def get_sample(
    persona_id: int,
    audio_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("Administrador", "Investigador", "Analista")),
) -> MuestraRead:
    row = db.execute(
        select(Audio, Embedding.id_embedding)
        .outerjoin(Embedding, Embedding.id_audio == Audio.id_audio)
        .where(Audio.id_audio == audio_id, Audio.id_persona == persona_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Muestra no encontrada")
    return _public_sample(row[0], row[1] is not None)


def _public_sample(audio: Audio, has_embedding: bool) -> MuestraRead:
    return MuestraRead(
        id_audio=audio.id_audio,
        id_persona=audio.id_persona,
        nombre_original=audio.nombre_original,
        formato_original=audio.formato_original,
        duracion_segundos=audio.duracion_segundos,
        fecha_subida=audio.fecha_subida,
        estado_procesamiento="embedding_disponible" if has_embedding else "embedding_no_disponible",
    )


@router.post("/{persona_id}/muestras", response_model=MuestraRead, status_code=status.HTTP_201_CREATED)
async def upload_sample(
    persona_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("Administrador", "Investigador")),
) -> MuestraRead:
    persona = db.get(Persona, persona_id)
    if persona is None:
        record_event(db, SAMPLE_ERROR, current_user.id_usuario, request, "persona_no_encontrada")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Persona no encontrada")

    try:
        stored_audio = await store_original_audio(file, category="referencias")
    except ValueError as error:
        record_event(db, SAMPLE_ERROR, current_user.id_usuario, request, "archivo_rechazado")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    duplicate = db.scalar(
        select(Audio).where(Audio.hash_archivo == stored_audio.sha256)
    )
    if duplicate is not None:
        stored_audio.path.unlink(missing_ok=True)
        record_event(db, SAMPLE_ERROR, current_user.id_usuario, request, "hash_duplicado")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El archivo ya está registrado",
        )

    try:
        processing = process_audio_copy(stored_audio.path, category="referencias")
    except AudioProcessingError as error:
        stored_audio.path.unlink(missing_ok=True)
        record_event(db, SAMPLE_ERROR, current_user.id_usuario, request, "audio_tecnicamente_invalido")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error

    try:
        serialized_vector = serialize_embedding(generate_embedding(processing.processed_path))
    except (EmbeddingError, FileNotFoundError, OSError, RuntimeError) as error:
        db.rollback()
        processing.processed_path.unlink(missing_ok=True)
        record_event(db, SAMPLE_ERROR, current_user.id_usuario, request, "embedding_no_generado")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo generar la representación biométrica",
        ) from error

    audio = Audio(
        id_persona=persona_id,
        id_usuario=current_user.id_usuario,
        ruta_archivo=stored_audio.path.as_posix(),
        nombre_original=stored_audio.original_name,
        formato_original=stored_audio.extension,
        duracion_segundos=processing.duration_seconds,
        hash_archivo=stored_audio.sha256,
    )
    db.add(audio)
    try:
        db.flush()
        db.add(
            Embedding(
                id_audio=audio.id_audio,
                vector=serialized_vector,
                modelo_utilizado=settings.speechbrain_model_source,
            )
        )
        db.commit()
        db.refresh(audio)
    except IntegrityError as error:
        db.rollback()
        processing.processed_path.unlink(missing_ok=True)
        record_event(db, SAMPLE_ERROR, current_user.id_usuario, request, "integridad_bd")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se pudo registrar la muestra",
        ) from error
    except SQLAlchemyError as error:
        db.rollback()
        processing.processed_path.unlink(missing_ok=True)
        record_event(db, SAMPLE_ERROR, current_user.id_usuario, request, "persistencia_bd")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo persistir la muestra",
        ) from error

    record_event(db, SAMPLE_UPLOADED, current_user.id_usuario, request, f"audio_id={audio.id_audio}")
    return _public_sample(audio, True)
