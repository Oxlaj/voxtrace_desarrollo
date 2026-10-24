"""HTTP contracts with real routing/auth/CSRF/Pydantic, no DB or audio I/O.

Run only this module:
  .venv/Scripts/python.exe -B -m pytest -p no:cacheprovider tests/test_analysis_reuse_http.py
"""
import importlib
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase
from starlette.middleware.sessions import SessionMiddleware


def forbidden(*args, **kwargs):
    raise AssertionError("Real database or biometric processing must never run")


def module(name, **attributes):
    result = ModuleType(name)
    result.__dict__.update(attributes)
    return result


@pytest.fixture
def http_case():
    # Restore the complete module registry afterwards, including any production
    # modules already imported by other tests. No global application is changed.
    with patch.dict(sys.modules), patch("sqlalchemy.create_engine", side_effect=forbidden):
        for name in list(sys.modules):
            if name == "backend" or name.startswith("backend."):
                del sys.modules[name]

        class TestBase(DeclarativeBase):
            metadata = MetaData(schema="voxtrace")

        db_module = module("backend.database.connection", Base=TestBase,
                           get_db=forbidden, SessionLocal=forbidden, engine=None)
        service = AsyncMock(return_value={
            "id_analisis": 77, "id_persona": 3, "id_audio": 11,
            # The real response model must filter unexpected physical paths.
            "ruta_archivo": "C:/private/reference.wav",
            "ruta_audio_consulta": "storage/audio/consultas/originales/private.wav",
        })
        sys.modules.update({
            "backend.database.connection": db_module,
            "backend.core.config": module("backend.core.config", settings=SimpleNamespace()),
            "backend.services.analysis_reuse_service": module(
                "backend.services.analysis_reuse_service", reuse_analysis_audio=service),
            "backend.services.identification_service": module(
                "backend.services.identification_service", identify_top_candidates=forbidden),
            "backend.services.embedding_service": module(
                "backend.services.embedding_service", generate_embedding=forbidden,
                serialize_embedding=forbidden),
        })
        auth = importlib.import_module("backend.api.auth")
        analisis = importlib.import_module("backend.api.analisis")
        security = importlib.import_module("backend.core.security")
        csrf_module = importlib.import_module("backend.core.csrf_middleware")
        models = importlib.import_module("backend.models")
        db = MagicMock()
        user = models.Usuario(
            id_usuario=7, id_rol=1, nombre="Usuario de prueba",
            correo="http-test@example.com", estado=True, debe_cambiar_password=False,
            password_hash=security.hash_password("HTTP-test-password-123"),
            rol=models.Rol(id_rol=1, nombre="Administrador"),
        )
        db.scalar.return_value = user
        db.get.return_value = user
        auth.record_event = MagicMock(return_value=True)
        # Only get_db is overridden; get_current_user and role/password checks
        # execute normally using the signed cookie from the actual login route.
        app = FastAPI()
        app.add_middleware(csrf_module.CSRFMiddleware)
        app.add_middleware(SessionMiddleware, secret_key="http-isolated-test-secret-32-characters",
                           session_cookie="voxtrace_test_session", same_site="lax")
        app.include_router(auth.router)
        app.include_router(analisis.router)
        app.dependency_overrides[db_module.get_db] = lambda: db
        with TestClient(app) as client:
            yield SimpleNamespace(client=client, db=db, user=user, service=service,
                                  app=app, auth=auth, models=models)
        app.dependency_overrides.clear()


def csrf(case):
    response = case.client.get("/auth/csrf")
    assert response.status_code == 200
    return response.json()["csrf_token"]


def login(case, role="Administrador", pending=False):
    case.user.rol.nombre = role
    case.user.debe_cambiar_password = pending
    initial = csrf(case)
    response = case.client.post("/auth/login", headers={"X-CSRF-Token": initial},
                                json={"correo": case.user.correo, "password": "HTTP-test-password-123"})
    assert response.status_code == 200
    token = csrf(case)
    assert token != initial
    return token


def post(case, payload=None, token=None, path="/analisis/77/muestra"):
    headers = {"X-CSRF-Token": token} if token is not None else {}
    return case.client.post(path, json=payload if payload is not None else {
        "confirmar": True, "id_persona": 3,
    }, headers=headers)


def rejected(case, response, status):
    assert response.status_code == status, response.text
    case.service.assert_not_awaited()
    case.service.assert_not_called()
    case.db.add.assert_not_called()
    case.db.flush.assert_not_called()
    case.db.commit.assert_not_called()


@pytest.mark.parametrize("role", ["Administrador", "Investigador"])
@pytest.mark.parametrize("new_person", [False, True])
def test_201_for_each_destination_and_authorized_role(http_case, role, new_person):
    case = http_case
    token = login(case, role)
    payload = {"confirmar": True}
    if new_person:
        payload["nueva_persona"] = {"nombre": "Persona sintética", "identificador": "HTTP-001", "alias": "Prueba"}
    else:
        payload["id_persona"] = 3
    response = post(case, payload, token)
    assert response.status_code == 201, response.text
    assert response.json() == {"id_analisis": 77, "id_persona": 3, "id_audio": 11}
    case.service.assert_awaited_once()
    analysis_id, parsed, request, db, actor = case.service.await_args.args
    assert analysis_id == 77
    assert parsed.confirmar is True
    assert (parsed.nueva_persona is not None) == new_person
    assert parsed.id_persona == (None if new_person else 3)
    if new_person:
        assert parsed.nueva_persona.identificador == "HTTP-001"
    assert request.url.path == "/analisis/77/muestra"
    assert db is case.db and actor is case.user
    assert "ruta" not in response.text
    assert "storage/" not in response.text and "C:/" not in response.text


@pytest.mark.parametrize("payload", [
    {}, {"confirmar": True},
    {"confirmar": True, "id_persona": 3, "nueva_persona": {"nombre": "Persona", "identificador": "P-3"}},
    {"confirmar": False, "id_persona": 3},
    {"confirmar": None, "id_persona": 3},
    {"confirmar": "true", "id_persona": 3},
    {"confirmar": True, "id_persona": 0},
    {"confirmar": True, "id_persona": -1},
    {"confirmar": True, "id_persona": "not-an-id"},
    {"confirmar": True, "nueva_persona": {}},
    {"confirmar": True, "nueva_persona": {"nombre": "", "identificador": "P-3"}},
    {"confirmar": True, "nueva_persona": {"nombre": "Persona", "identificador": ""}},
    {"confirmar": True, "nueva_persona": {"nombre": "x" * 151, "identificador": "P-3"}},
    {"confirmar": True, "nueva_persona": {"nombre": "Persona", "identificador": "x" * 51}},
    {"confirmar": True, "id_persona": None, "nueva_persona": None},
])
def test_422_invalid_or_ambiguous_payload_never_calls_service(http_case, payload):
    token = login(http_case)
    rejected(http_case, post(http_case, payload, token), 422)


def test_422_invalid_analysis_id(http_case):
    token = login(http_case)
    rejected(http_case, post(http_case, token=token, path="/analisis/not-an-id/muestra"), 422)


def test_401_without_authenticated_session_with_valid_csrf(http_case):
    rejected(http_case, post(http_case, token=csrf(http_case)), 401)
    http_case.db.get.assert_not_called()


def test_401_user_deactivated_after_login(http_case):
    token = login(http_case)
    http_case.user.estado = False
    rejected(http_case, post(http_case, token=token), 401)
    assert http_case.client.get("/auth/me").status_code == 401  # session cleared


@pytest.mark.parametrize("role,pending", [("Analista", False), ("Administrador", True), ("Investigador", True)])
def test_403_role_or_pending_password(http_case, role, pending):
    token = login(http_case, role, pending)
    rejected(http_case, post(http_case, token=token), 403)


@pytest.mark.parametrize("supplied", [None, "incorrect-token"])
def test_403_missing_or_invalid_csrf_before_auth_or_service(http_case, supplied):
    login(http_case)
    http_case.db.reset_mock()
    rejected(http_case, post(http_case, token=supplied), 403)
    http_case.db.get.assert_not_called()


def test_403_csrf_from_another_session(http_case):
    token = login(http_case)
    http_case.client.cookies.clear()
    csrf(http_case)
    rejected(http_case, post(http_case, token=token), 403)


def test_405_wrong_method_never_calls_service(http_case):
    rejected(http_case, http_case.client.get("/analisis/77/muestra"), 405)


def test_openapi_uses_real_reuse_request_and_response_schemas(http_case):
    schema = http_case.client.get("/openapi.json").json()
    operation = schema["paths"]["/analisis/{analysis_id}/muestra"]["post"]
    assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("/ReutilizarAudioRequest")
    assert operation["responses"]["201"]["content"]["application/json"]["schema"]["$ref"].endswith("/ReutilizarAudioResponse")
    assert set(schema["components"]["schemas"]["ReutilizarAudioResponse"]["properties"]) == {"id_analisis", "id_persona", "id_audio"}
    http_case.service.assert_not_called()
