"""Real HTTP registration contracts; DB, storage, conversion and embeddings mocked."""
import importlib
import json
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from test_analysis_reuse_http import http_case, login


class FakeEmbeddingError(ValueError):
    pass


@pytest.fixture
def registration(http_case, monkeypatch):
    case = http_case
    sys.modules["backend.services.embedding_service"].EmbeddingError = FakeEmbeddingError
    sys.modules["backend.core.config"].settings.speechbrain_model_source = "test-model"
    api = importlib.import_module("backend.api.personas")
    service = importlib.import_module("backend.services.person_registration_service")
    case.app.include_router(api.router)
    monkeypatch.setattr(api, "record_event", MagicMock(return_value=True))
    monkeypatch.setattr(service, "record_event", MagicMock(return_value=True))
    stored = MagicMock(original_name="test.wav", extension="wav", sha256="a" * 64)
    stored.path.as_posix.return_value = "storage/test/new.wav"
    processing = MagicMock(duration_seconds=2)
    processing.processed_path.as_posix.return_value = "storage/test/processed.wav"
    store = AsyncMock(return_value=stored)
    process = MagicMock(return_value=processing)
    embedding = MagicMock(return_value=[0.1])
    monkeypatch.setattr(service, "store_original_audio", store)
    monkeypatch.setattr(service, "process_audio_copy", process)
    monkeypatch.setattr(service, "generate_embedding", embedding)
    monkeypatch.setattr(service, "serialize_embedding", lambda vector: "[0.1]")

    def assign_ids(*args):
        entities = [call.args[0] for call in case.db.add.call_args_list]
        for entity in entities + list(args):
            if isinstance(entity, case.models.Persona):
                entity.id_persona = 3
                entity.fecha_registro = datetime(2026, 10, 8)
            if isinstance(entity, case.models.Audio):
                entity.id_audio = 11
    case.db.flush.side_effect = assign_ids
    case.db.refresh.side_effect = assign_ids
    case.store, case.process, case.embedding = store, process, embedding
    case.stored, case.processing = stored, processing
    case.registration_service = service
    return case


def authenticated(case, role="Administrador"):
    token = login(case, role)
    case.db.scalar.return_value = None
    return token


def upload(case, token, persona=None):
    return case.client.post("/personas/con-muestra", headers={"X-CSRF-Token": token},
                            data={"persona": json.dumps(persona or {"nombre": "Persona de prueba", "identificador": "P-3"})},
                            files={"file": ("test.wav", b"synthetic", "audio/wav")})


def test_registration_without_audio_preserves_json_endpoint(registration):
    case = registration
    token = authenticated(case)
    response = case.client.post("/personas", headers={"X-CSRF-Token": token},
                                json={"nombre": "Persona de prueba", "identificador": "P-3"})
    assert response.status_code == 201, response.text
    assert response.json()["id_persona"] == 3
    case.store.assert_not_called()
    case.embedding.assert_not_called()
    case.db.commit.assert_called_once()


@pytest.mark.parametrize("role", ["Administrador", "Investigador"])
def test_registration_with_audio_commits_all_entities_and_audit(registration, role):
    case = registration
    response = upload(case, authenticated(case, role))
    assert response.status_code == 201, response.text
    assert response.json()["id_persona"] == 3
    entities = [call.args[0] for call in case.db.add.call_args_list]
    assert sum(isinstance(item, case.models.Persona) for item in entities) == 1
    assert sum(isinstance(item, case.models.Audio) for item in entities) == 1
    assert sum(isinstance(item, case.models.Embedding) for item in entities) == 1
    actions = [item.accion for item in entities if isinstance(item, case.models.Log)]
    assert actions == ["persona_creada", "muestra_cargada"]
    case.db.commit.assert_called_once()
    case.stored.path.unlink.assert_not_called()
    assert "ruta_archivo" not in response.text


@pytest.mark.parametrize("failure,status", [("upload", 400), ("conversion", 400), ("embedding", 500)])
def test_processing_error_never_creates_partial_person(registration, failure, status):
    case = registration
    token = authenticated(case)
    if failure == "upload":
        case.store.side_effect = ValueError("wrong format")
    elif failure == "conversion":
        case.process.side_effect = case.registration_service.AudioProcessingError("invalid audio")
    else:
        case.embedding.side_effect = FakeEmbeddingError("failed model")
    response = upload(case, token)
    assert response.status_code == status, response.text
    case.db.add.assert_not_called()
    case.db.commit.assert_not_called()
    case.db.rollback.assert_called_once()
    if failure != "upload":
        case.stored.path.unlink.assert_called_once_with(missing_ok=True)
    if failure == "embedding":
        case.processing.processed_path.unlink.assert_called_once_with(missing_ok=True)


def test_duplicate_identifier_rejects_before_storage(registration):
    case = registration
    token = authenticated(case)
    case.db.scalar.return_value = 3
    assert upload(case, token).status_code == 409
    case.store.assert_not_called()
    case.db.add.assert_not_called()


def test_duplicate_audio_rejects_before_processing(registration):
    case = registration
    token = authenticated(case)
    case.db.scalar.side_effect = [None, 11, None, None]
    assert upload(case, token).status_code == 409
    case.process.assert_not_called()
    case.db.add.assert_not_called()


def test_invalid_person_schema_rejects_before_storage(registration):
    case = registration
    assert upload(case, authenticated(case), {"nombre": "", "identificador": "P-3"}).status_code == 422
    case.store.assert_not_called()


def test_analyst_and_missing_csrf_cannot_upload(registration):
    case = registration
    token = authenticated(case, "Analista")
    assert upload(case, token).status_code == 403
    assert case.client.post("/personas/con-muestra").status_code == 403
    case.store.assert_not_called()


def test_commit_error_keeps_copies_for_review(registration):
    case = registration
    token = authenticated(case)
    case.db.commit.side_effect = RuntimeError("lost commit reply")
    assert upload(case, token).status_code == 500
    case.stored.path.unlink.assert_not_called()
    case.processing.processed_path.unlink.assert_not_called()
    case.db.rollback.assert_called_once()


def test_405_reproduced_when_running_router_is_missing_sample_post(registration):
    """A stale app matches /{persona_id} partially and reports method 405."""
    case = registration
    token = authenticated(case)
    routes = case.app.router.routes
    sample_route = next(route for route in routes if getattr(route, "path", None) == "/personas/con-muestra")
    assert sample_route.methods == {"POST"}
    index = routes.index(sample_route)
    routes.remove(sample_route)
    try:
        response = upload(case, token)
        assert response.status_code == 405
        assert response.json()["detail"] == "Method Not Allowed"
        case.store.assert_not_called()
        case.db.add.assert_not_called()
    finally:
        routes.insert(index, sample_route)
    response = upload(case, token)
    assert response.status_code == 201, response.text
    case.store.assert_awaited_once()


def test_frontend_post_target_exists_in_registered_http_routes(registration):
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    script = (root / "frontend/static/js/persona-form.js").read_text(encoding="utf-8")
    assert 'audio ? "/personas/con-muestra" : "/personas"' in script
    assert '{method: "POST", body}' in script
    schema = registration.client.get("/openapi.json").json()
    assert "post" in schema["paths"]["/personas/con-muestra"]
    assert "post" in schema["paths"]["/personas"]
