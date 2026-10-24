from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock
from dataclasses import replace
from decimal import Decimal

import pytest
from fastapi import UploadFile
from sqlalchemy.exc import SQLAlchemyError
from starlette.datastructures import Headers
from starlette.requests import Request

from backend.api import analisis
from backend.models.usuario import Usuario
from backend.services.audio_processing_service import AudioProcessingResult
from backend.services.audio_service import StoredAudio
from backend.services.identification_service import IdentificationCandidate
from backend.services.verification_service import IndividualVerificationResult


def make_request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/analisis/identificacion", "headers": [], "query_string": b"", "server": ("testserver", 80), "client": ("192.0.2.40", 50000), "scheme": "http", "root_path": "", "http_version": "1.1"})


def make_user() -> Usuario:
    return Usuario(id_usuario=1, id_rol=1, nombre="Admin", correo="admin@voxtrace.com", password_hash="hidden", estado=True)


def make_candidate() -> IdentificationCandidate:
    return IdentificationCandidate(
        posicion=1,
        id_persona=4,
        identificador="P-004",
        nombre="Persona 4",
        alias="Alias 4",
        similitud_mejor=0.8,
        similitud_promedio=0.7,
        muestras_comparadas=2,
        muestras_sin_embedding=1,
        resultados_individuales=[IndividualVerificationResult(id_audio=10, similitud=0.8)],
    )


def make_db(tmp_path: Path) -> MagicMock:
    db = MagicMock()
    db.scalar.return_value = None
    analysis_id = 77

    def refresh(entity):
        if hasattr(entity, "id_analisis"):
            entity.id_analisis = analysis_id

    db.refresh.side_effect = refresh
    return db


@pytest.mark.anyio
async def test_analysis_endpoint_persists_threshold_from_original_cosine(tmp_path, monkeypatch) -> None:
    original = tmp_path / "original.mp3"
    original.write_bytes(b"original")
    processed = tmp_path / "processed.wav"
    processed.write_bytes(b"processed")
    async def fake_store(file, category):
        return StoredAudio(original, "query.mp3", "mp3", "a" * 64, 8)

    monkeypatch.setattr(analisis, "store_original_audio", fake_store)
    monkeypatch.setattr(analisis, "process_audio_copy", lambda path, category: AudioProcessingResult(0.5, processed))
    monkeypatch.setattr(analisis, "identify_top_candidates", lambda db, path, limit: [make_candidate()])
    db = make_db(tmp_path)
    file = UploadFile(file=BytesIO(b"query"), filename="query.mp3", headers=Headers({"content-type": "audio/mpeg"}))

    response = await analisis.run_identification(make_request(), file, db, make_user())

    assert response.id_analisis == 77
    assert response.estado == "completado"
    assert response.candidatos[0].puntuacion_normalizada == 90
    assert response.candidatos[0].similitud_mejor == 0.8
    assert response.candidatos[0].supera_umbral is True
    assert response.candidatos[0].estado_umbral == "posible_coincidencia"
    assert response.estado_coincidencia == "posible_coincidencia"
    persisted_results = [item for item in db.add.call_args_list if item.args and item.args[0].__class__.__name__ == "ResultadoAnalisis"]
    assert len(persisted_results) == 1
    assert persisted_results[0].args[0].supera_umbral is True
    assert not processed.exists()
    assert original.exists()


@pytest.mark.anyio
async def test_threshold_decision_does_not_use_rounded_normalized_score(tmp_path, monkeypatch) -> None:
    original = tmp_path / "original.wav"
    original.write_bytes(b"original")
    processed = tmp_path / "processed.wav"
    processed.write_bytes(b"processed")

    async def fake_store(file, category):
        return StoredAudio(original, "query.wav", "wav", "f" * 64, 8)

    candidate = replace(make_candidate(), similitud_mejor=0.628186503599)
    monkeypatch.setattr(analisis, "store_original_audio", fake_store)
    monkeypatch.setattr(
        analisis,
        "process_audio_copy",
        lambda path, category: AudioProcessingResult(0.5, processed),
    )
    monkeypatch.setattr(
        analisis, "identify_top_candidates", lambda db, path, limit: [candidate]
    )
    db = make_db(tmp_path)
    file = UploadFile(
        file=BytesIO(b"query"),
        filename="query.wav",
        headers=Headers({"content-type": "audio/wav"}),
    )

    response = await analisis.run_identification(make_request(), file, db, make_user())

    assert response.candidatos[0].puntuacion_normalizada == Decimal("81.409")
    assert response.candidatos[0].supera_umbral is False
    assert response.candidatos[0].estado_umbral == "coincidencia_insuficiente"
    persisted = [
        call.args[0]
        for call in db.add.call_args_list
        if call.args and call.args[0].__class__.__name__ == "ResultadoAnalisis"
    ]
    assert persisted[0].supera_umbral is False


@pytest.mark.anyio
async def test_invalid_upload_is_rejected_without_persisting_analysis(monkeypatch) -> None:
    async def reject(file, category):
        raise ValueError("Formato de audio no permitido")

    monkeypatch.setattr(analisis, "store_original_audio", reject)
    db = MagicMock()
    file = UploadFile(file=BytesIO(b"bad"), filename="bad.exe", headers=Headers({"content-type": "application/octet-stream"}))

    with pytest.raises(Exception) as error:
        await analisis.run_identification(make_request(), file, db, make_user())

    assert error.value.status_code == 400
    assert not any(item.args and item.args[0].__class__.__name__ == "Analisis" for item in db.add.call_args_list)


@pytest.mark.anyio
async def test_registered_reference_hash_is_rejected_before_processing(
    tmp_path, monkeypatch
) -> None:
    original = tmp_path / "accepted-duplicate.ogg"
    original.write_bytes(b"duplicate-reference-content")

    async def fake_store(file, category):
        return StoredAudio(
            original,
            "consulta.ogg",
            "ogg",
            "d" * 64,
            original.stat().st_size,
        )

    process = MagicMock()
    identify = MagicMock()
    monkeypatch.setattr(analisis, "store_original_audio", fake_store)
    monkeypatch.setattr(analisis, "process_audio_copy", process)
    monkeypatch.setattr(analisis, "identify_top_candidates", identify)
    db = make_db(tmp_path)
    db.scalar.return_value = 11
    file = UploadFile(
        file=BytesIO(b"query"),
        filename="consulta.ogg",
        headers=Headers({"content-type": "audio/ogg"}),
    )

    with pytest.raises(Exception) as captured:
        await analisis.run_identification(make_request(), file, db, make_user())

    assert captured.value.status_code == 409
    assert captured.value.detail == (
        "Este archivo ya se encuentra registrado como una muestra de referencia. "
        "Utilice un audio diferente para realizar el análisis."
    )
    assert original.exists()
    process.assert_not_called()
    identify.assert_not_called()
    added = [call.args[0] for call in db.add.call_args_list if call.args]
    assert not any(item.__class__.__name__ == "Analisis" for item in added)
    assert not any(item.__class__.__name__ == "ResultadoAnalisis" for item in added)
    audit_events = [item for item in added if item.__class__.__name__ == "Log"]
    assert len(audit_events) == 1
    assert audit_events[0].accion == "analisis_rechazado"
    assert audit_events[0].detalles == "archivo_duplicado_referencia"
    assert all(
        value not in audit_events[0].detalles
        for value in ("hash", "ruta", "audio_id", "persona", "embedding")
    )


@pytest.mark.anyio
async def test_same_name_with_different_hash_continues_analysis(
    tmp_path, monkeypatch
) -> None:
    original = tmp_path / "different-content.ogg"
    original.write_bytes(b"different-content")
    processed = tmp_path / "processed.wav"
    processed.write_bytes(b"processed")

    async def fake_store(file, category):
        return StoredAudio(
            original,
            "imitador 1 muestra 5.ogg",
            "ogg",
            "e" * 64,
            original.stat().st_size,
        )

    process = MagicMock(return_value=AudioProcessingResult(1.0, processed))
    monkeypatch.setattr(analisis, "store_original_audio", fake_store)
    monkeypatch.setattr(analisis, "process_audio_copy", process)
    monkeypatch.setattr(
        analisis,
        "identify_top_candidates",
        lambda db, path, limit: [make_candidate()],
    )
    db = make_db(tmp_path)
    db.scalar.return_value = None
    file = UploadFile(
        file=BytesIO(b"query"),
        filename="imitador 1 muestra 5.ogg",
        headers=Headers({"content-type": "audio/ogg"}),
    )

    response = await analisis.run_identification(make_request(), file, db, make_user())

    assert response.estado == "completado"
    process.assert_called_once()
    assert original.exists()
    assert not processed.exists()


@pytest.mark.anyio
async def test_result_persistence_failure_rolls_back_and_preserves_only_original(tmp_path, monkeypatch) -> None:
    original = tmp_path / "accepted-original.wav"
    original.write_bytes(b"forensic-original")
    processed = tmp_path / "temporary-processed.wav"
    processed.write_bytes(b"processed")

    async def fake_store(file, category):
        return StoredAudio(original, "query.wav", "wav", "b" * 64, 17)

    monkeypatch.setattr(analisis, "store_original_audio", fake_store)
    monkeypatch.setattr(analisis, "process_audio_copy", lambda path, category: AudioProcessingResult(0.5, processed))
    monkeypatch.setattr(analisis, "identify_top_candidates", lambda db, path, limit: [make_candidate()])

    db = make_db(tmp_path)
    db.commit.side_effect = [SQLAlchemyError("result persistence failed"), None]
    file = UploadFile(file=BytesIO(b"query"), filename="query.wav", headers=Headers({"content-type": "audio/wav"}))

    with pytest.raises(Exception) as captured:
        await analisis.run_identification(make_request(), file, db, make_user())

    assert captured.value.status_code == 500
    db.rollback.assert_called_once_with()
    assert db.commit.call_count == 2
    method_names = [call[0] for call in db.method_calls]
    first_commit = method_names.index("commit")
    assert "flush" in method_names[:first_commit]
    assert method_names[first_commit + 1] == "rollback"
    assert original.exists()
    assert not processed.exists()

    added = [call.args[0] for call in db.add.call_args_list if call.args]
    analyses = [item for item in added if item.__class__.__name__ == "Analisis"]
    results = [item for item in added if item.__class__.__name__ == "ResultadoAnalisis"]
    audit_events = [item for item in added if item.__class__.__name__ == "Log"]
    assert len(analyses) == 1
    assert len(results) == 1
    assert analyses[0].estado == "completado"
    assert audit_events[-1].accion == "analisis_fallido"
    assert audit_events[-1].detalles == "persistencia_no_completada"
    assert "hash" not in audit_events[-1].detalles
    assert "ruta" not in audit_events[-1].detalles


@pytest.mark.anyio
async def test_unexpected_biometric_failure_rolls_back_and_cleans_only_processed(
    tmp_path, monkeypatch
) -> None:
    original = tmp_path / "accepted-original.wav"
    original.write_bytes(b"forensic-original")
    processed = tmp_path / "temporary-processed.wav"
    processed.write_bytes(b"processed")

    async def fake_store(file, category):
        return StoredAudio(original, "query.wav", "wav", "c" * 64, 17)

    monkeypatch.setattr(analisis, "store_original_audio", fake_store)
    monkeypatch.setattr(
        analisis,
        "process_audio_copy",
        lambda path, category: AudioProcessingResult(0.5, processed),
    )
    monkeypatch.setattr(
        analisis,
        "identify_top_candidates",
        MagicMock(side_effect=RuntimeError("fallo interno biométrico simulado")),
    )

    db = make_db(tmp_path)
    file = UploadFile(
        file=BytesIO(b"query"),
        filename="query.wav",
        headers=Headers({"content-type": "audio/wav"}),
    )

    with pytest.raises(Exception) as captured:
        await analisis.run_identification(make_request(), file, db, make_user())

    assert captured.value.status_code == 500
    assert captured.value.detail == "No se pudo completar el análisis"
    assert original.exists()
    assert not processed.exists()
    db.rollback.assert_called_once_with()

    added = [call.args[0] for call in db.add.call_args_list if call.args]
    assert not any(item.__class__.__name__ == "ResultadoAnalisis" for item in added)
    audit_events = [item for item in added if item.__class__.__name__ == "Log"]
    assert audit_events[-1].accion == "analisis_fallido"
    assert audit_events[-1].detalles == "fallo_interno_controlado"
    assert all(
        word not in audit_events[-1].detalles
        for word in ("hash", "ruta", "embedding", "traceback")
    )
