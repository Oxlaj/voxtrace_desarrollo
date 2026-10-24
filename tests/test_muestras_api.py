from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from starlette.requests import Request

from backend.api import muestras
from backend.services.audio_processing_service import AudioProcessingResult
from backend.models.audio import Audio
from backend.models.embedding import Embedding
from backend.models.persona import Persona
from backend.models.usuario import Usuario


def make_audio() -> Audio:
    return Audio(
        id_audio=11,
        id_persona=3,
        id_usuario=7,
        ruta_archivo="storage/audio/referencias/originales/internal.wav",
        nombre_original="referencia.wav",
        formato_original="wav",
        duracion_segundos=Decimal("2.50"),
        hash_archivo="a" * 64,
        fecha_subida=datetime(2026, 9, 7),
    )


def make_user() -> Usuario:
    return Usuario(id_usuario=7, id_rol=1, nombre="Admin", correo="admin@example.com", password_hash="hash", estado=True)


def test_list_samples_returns_metadata_for_existing_person() -> None:
    db = MagicMock()
    db.get.return_value = Persona(id_persona=3, nombre="Persona de prueba", identificador="P-003")
    db.execute.return_value.all.return_value = [(make_audio(), 21)]

    result = muestras.list_samples(3, db, make_user())

    assert result[0].id_audio == 11
    assert result[0].nombre_original == "referencia.wav"
    assert result[0].estado_procesamiento == "embedding_disponible"
    assert "hash_archivo" not in result[0].model_dump()
    db.execute.assert_called_once()


@pytest.mark.anyio
async def test_upload_sample_rolls_back_keeps_original_and_removes_processed_on_database_error(tmp_path, monkeypatch) -> None:
    stored_path = tmp_path / "internal.wav"
    stored_path.write_bytes(b"audio")
    stored = MagicMock(
        path=stored_path,
        original_name="referencia.wav",
        extension="wav",
        sha256="b" * 64,
    )

    async def fake_store_original_audio(upload, category):
        return stored

    monkeypatch.setattr(muestras, "store_original_audio", fake_store_original_audio)
    processed_path = tmp_path / "processed.wav"
    processed_path.write_bytes(b"processed-audio")
    monkeypatch.setattr(
        muestras,
        "process_audio_copy",
        lambda source_path, category: AudioProcessingResult(0.5, processed_path),
    )
    monkeypatch.setattr(muestras, "generate_embedding", lambda path: [0.1] * 192)
    monkeypatch.setattr(muestras, "record_event", lambda *args, **kwargs: True)
    db = MagicMock()
    db.get.return_value = Persona(id_persona=3, nombre="Persona de prueba", identificador="P-003")
    db.scalar.return_value = None
    db.flush.side_effect = SQLAlchemyError("database unavailable")

    with pytest.raises(HTTPException) as error:
        await muestras.upload_sample(3, Request({"type": "http", "client": ("test", 1)}), MagicMock(), db, make_user())

    assert error.value.status_code == 500
    assert stored_path.exists()
    assert not processed_path.exists()
    assert db.rollback.call_count >= 1


@pytest.mark.anyio
async def test_upload_sample_persists_audio_and_embedding_in_one_commit(tmp_path, monkeypatch) -> None:
    stored_path = tmp_path / "original.wav"
    stored_path.write_bytes(b"audio")
    stored = MagicMock(path=stored_path, original_name="voz.wav", extension="wav", sha256="c" * 64)

    async def fake_store(upload, category):
        return stored

    processed_path = tmp_path / "processed.wav"
    processed_path.write_bytes(b"processed")
    monkeypatch.setattr(muestras, "store_original_audio", fake_store)
    monkeypatch.setattr(muestras, "process_audio_copy", lambda *args, **kwargs: AudioProcessingResult(61.25, processed_path))
    monkeypatch.setattr(muestras, "generate_embedding", lambda path: [0.25] * 192)
    monkeypatch.setattr(muestras, "record_event", lambda *args, **kwargs: True)
    db = MagicMock()
    db.get.return_value = Persona(id_persona=3, nombre="Persona", identificador="P-003")
    db.scalar.return_value = None

    def assign_audio_id() -> None:
        audio = next(item for item in (call.args[0] for call in db.add.call_args_list) if isinstance(item, Audio))
        audio.id_audio = 31
        audio.fecha_subida = datetime(2026, 9, 8)
    db.flush.side_effect = assign_audio_id

    result = await muestras.upload_sample(3, Request({"type": "http", "client": ("test", 1)}), MagicMock(), db, make_user())

    added = [call.args[0] for call in db.add.call_args_list]
    audio = next(item for item in added if isinstance(item, Audio))
    embedding = next(item for item in added if isinstance(item, Embedding))
    assert embedding.id_audio == audio.id_audio == 31
    assert embedding.modelo_utilizado == muestras.settings.speechbrain_model_source
    assert len(__import__("json").loads(embedding.vector)) == 192
    assert db.commit.call_count == 1
    assert result.estado_procesamiento == "embedding_disponible"
    assert "hash_archivo" not in result.model_dump()
    assert stored_path.exists() and processed_path.exists()


@pytest.mark.anyio
async def test_embedding_failure_keeps_accepted_original_and_cleans_processed(tmp_path, monkeypatch) -> None:
    original = tmp_path / "original.wav"; original.write_bytes(b"audio")
    processed = tmp_path / "processed.wav"; processed.write_bytes(b"processed")
    stored = MagicMock(path=original, original_name="voz.wav", extension="wav", sha256="d" * 64)
    async def fake_store(upload, category): return stored
    monkeypatch.setattr(muestras, "store_original_audio", fake_store)
    monkeypatch.setattr(muestras, "process_audio_copy", lambda *args, **kwargs: AudioProcessingResult(61, processed))
    monkeypatch.setattr(muestras, "generate_embedding", MagicMock(side_effect=muestras.EmbeddingError("internal")))
    monkeypatch.setattr(muestras, "record_event", lambda *args, **kwargs: True)
    db = MagicMock(); db.get.return_value = Persona(id_persona=3, nombre="Persona", identificador="P-003"); db.scalar.return_value = None

    with pytest.raises(HTTPException) as error:
        await muestras.upload_sample(3, Request({"type": "http", "client": ("test", 1)}), MagicMock(), db, make_user())

    assert error.value.status_code == 500
    assert error.value.detail == "No se pudo generar la representación biométrica"
    assert original.exists() and not processed.exists()
    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.rollback.assert_called()
