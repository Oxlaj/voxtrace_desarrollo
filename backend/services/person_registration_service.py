"""Atomic registration of a person and an uploaded first voice sample."""
import logging

from fastapi import HTTPException, Request, UploadFile
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.models.persona import Persona
from backend.models.audio import Audio
from backend.models.embedding import Embedding
from backend.models.analisis import Analisis
from backend.models.usuario import Usuario
from backend.schemas.persona import PersonaCreate, PersonaRead
from backend.services.audio_service import store_original_audio
from backend.services.audio_processing_service import AudioProcessingError, process_audio_copy
from backend.services.embedding_service import EmbeddingError, generate_embedding, serialize_embedding
from backend.services.audit_service import add_event, record_event, PERSON_CREATED, PERSON_ERROR, SAMPLE_UPLOADED

logger = logging.getLogger(__name__)


async def register_with_sample(payload: PersonaCreate, file: UploadFile, request: Request,
                               db: Session, actor: Usuario) -> PersonaRead:
    stored = processing = None
    commit_attempted = committed = rollback_confirmed = False
    try:
        if db.scalar(select(Persona.id_persona).where(Persona.identificador == payload.identificador)) is not None:
            raise HTTPException(409, "El identificador ya está registrado")
        stored = await store_original_audio(file, category="referencias")
        if db.scalar(select(Audio.id_audio).where(Audio.hash_archivo == stored.sha256)) is not None:
            raise HTTPException(409, "El archivo ya está registrado")
        processing = process_audio_copy(stored.path, category="referencias")
        vector = serialize_embedding(generate_embedding(processing.processed_path))
        person = Persona(**payload.model_dump())
        db.add(person)
        db.flush()
        audio = Audio(id_persona=person.id_persona, id_usuario=actor.id_usuario,
                      ruta_archivo=stored.path.as_posix(), nombre_original=stored.original_name,
                      formato_original=stored.extension, duracion_segundos=processing.duration_seconds,
                      hash_archivo=stored.sha256)
        db.add(audio)
        db.flush()
        db.add(Embedding(id_audio=audio.id_audio, vector=vector, modelo_utilizado=settings.speechbrain_model_source))
        add_event(db, PERSON_CREATED, actor.id_usuario, request, f"persona_id={person.id_persona}")
        add_event(db, SAMPLE_UPLOADED, actor.id_usuario, request, f"persona_id={person.id_persona};audio_id={audio.id_audio};primera_muestra")
        response = PersonaRead.model_validate(person)
        commit_attempted = True
        db.commit()
        committed = True
        return response
    except Exception as error:
        try:
            db.rollback()
            rollback_confirmed = True
        except Exception:
            logger.warning("Rollback no confirmado durante registro con primera muestra")
        if rollback_confirmed:
            try:
                record_event(db, PERSON_ERROR, actor.id_usuario, request, "registro_con_muestra_no_completado")
            except Exception:
                logger.warning("No se pudo auditar el registro con primera muestra fallido")
        if isinstance(error, HTTPException):
            raise
        if isinstance(error, EmbeddingError):
            raise HTTPException(500, "No se pudo generar la representación biométrica") from error
        if isinstance(error, (ValueError, AudioProcessingError)):
            raise HTTPException(400, "El archivo no cumple las condiciones de audio requeridas") from error
        if isinstance(error, IntegrityError):
            raise HTTPException(409, "El identificador o el audio ya está registrado") from error
        raise HTTPException(500, "No se pudo registrar la persona y su primera muestra") from error
    finally:
        try:
            await file.close()
        except OSError:
            logger.warning("No se pudo cerrar la carga de primera muestra")
        if stored is not None and not committed:
            paths = [stored.path] + ([processing.processed_path] if processing else [])
            safe_to_remove = False
            if rollback_confirmed and not commit_attempted:
                try:
                    names = [path.as_posix() for path in paths]
                    audio_ref = db.scalar(select(Audio.id_audio).where(or_(Audio.ruta_archivo.in_(names), Audio.hash_archivo == stored.sha256)).limit(1))
                    query_ref = db.scalar(select(Analisis.id_analisis).where(Analisis.ruta_audio_consulta.in_(names)).limit(1))
                    safe_to_remove = audio_ref is None and query_ref is None
                except Exception:
                    pass
            if safe_to_remove:
                for path in paths:
                    try:
                        path.unlink(missing_ok=True)
                    except OSError:
                        logger.warning("No se pudo limpiar una copia nueva del registro con muestra")
            else:
                logger.warning("Archivos conservados para revisión del registro con primera muestra")
