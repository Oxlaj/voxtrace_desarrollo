from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.requests import Request

from backend.api.personas import delete_persona, update_persona
from backend.core.security import get_current_user
from backend.database.connection import get_db
from backend.main import app
from backend.models.persona import Persona
from backend.models.rol import Rol
from backend.models.usuario import Usuario
from backend.schemas.persona import PersonaUpdate


def make_request(method: str, path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [],
            "query_string": b"",
            "client": ("192.0.2.50", 50000),
        }
    )


def make_admin() -> Usuario:
    return Usuario(
        id_usuario=7,
        id_rol=1,
        nombre="Administrador de prueba",
        correo="admin-test@example.com",
        password_hash="hidden",
        estado=True,
        rol=Rol(id_rol=1, nombre="Administrador"),
    )


def make_person() -> Persona:
    return Persona(
        id_persona=42,
        identificador="TEST-42",
        nombre="Persona inicial",
        alias=None,
        descripcion=None,
        observaciones=None,
        fecha_registro=datetime(2026, 10, 4),
    )


def test_update_persona_success(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    person = make_person()
    db.get.return_value = person
    db.scalar.return_value = None
    monkeypatch.setattr("backend.api.personas.record_event", lambda *args, **kwargs: None)

    result = update_persona(
        person.id_persona,
        PersonaUpdate(nombre="Persona editada", alias="Alias de prueba"),
        make_request("PATCH", "/personas/42"),
        db,
        make_admin(),
    )

    assert result.nombre == "Persona editada"
    assert result.alias == "Alias de prueba"
    db.commit.assert_called_once()
    db.rollback.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    [
        {"nombre": ""},
        {"identificador": ""},
        {"nombre": "x" * 151},
        {"identificador": "x" * 51},
    ],
)
def test_update_persona_rejects_invalid_fields(payload: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        PersonaUpdate(**payload)


def test_delete_persona_without_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    person = make_person()
    db.get.return_value = person
    db.scalar.side_effect = [None, None]
    monkeypatch.setattr("backend.api.personas.record_event", lambda *args, **kwargs: None)

    delete_persona(
        person.id_persona,
        make_request("DELETE", "/personas/42"),
        db,
        make_admin(),
    )

    db.delete.assert_called_once_with(person)
    db.commit.assert_called_once()
    db.rollback.assert_not_called()


@pytest.mark.parametrize("dependency_values", [(101, None), (None, 202)])
def test_delete_persona_with_related_data_returns_conflict_and_preserves_it(
    dependency_values: tuple[int | None, int | None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = MagicMock()
    person = make_person()
    db.get.return_value = person
    db.scalar.side_effect = dependency_values
    monkeypatch.setattr("backend.api.personas.record_event", lambda *args, **kwargs: None)

    with pytest.raises(HTTPException) as conflict:
        delete_persona(
            person.id_persona,
            make_request("DELETE", "/personas/42"),
            db,
            make_admin(),
        )

    assert conflict.value.status_code == 409
    assert "información asociada" in conflict.value.detail
    db.delete.assert_not_called()
    db.commit.assert_not_called()


def test_delete_persona_rolls_back_unexpected_database_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = MagicMock()
    db.get.return_value = make_person()
    db.scalar.side_effect = [None, None]
    db.commit.side_effect = SQLAlchemyError("fallo simulado")
    monkeypatch.setattr("backend.api.personas.record_event", lambda *args, **kwargs: None)

    with pytest.raises(HTTPException) as conflict:
        delete_persona(
            42,
            make_request("DELETE", "/personas/42"),
            db,
            make_admin(),
        )

    assert conflict.value.status_code == 409
    db.rollback.assert_called_once()


@pytest.mark.parametrize(
    ("role_name", "patch_status", "delete_status"),
    [
        ("Administrador", 200, 204),
        ("Investigador", 200, 403),
        ("Analista", 403, 403),
    ],
)
def test_person_mutation_endpoints_enforce_role_permissions(
    role_name: str,
    patch_status: int,
    delete_status: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = MagicMock()
    db.get.return_value = make_person()
    db.scalar.return_value = None
    actor = make_admin()
    actor.rol.nombre = role_name
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: actor
    monkeypatch.setattr("backend.api.personas.record_event", lambda *args, **kwargs: None)
    try:
        client = TestClient(app)
        token = client.get("/auth/csrf").json()["csrf_token"]
        headers = {"X-CSRF-Token": token}
        detail_response = client.get("/personas/42")
        patch_response = client.patch(
            "/personas/42",
            headers=headers,
            json={"nombre": "Persona autorizada"},
        )

        db.reset_mock()
        db.get.return_value = make_person()
        db.scalar.side_effect = [None, None]
        delete_response = client.delete("/personas/42", headers=headers)
    finally:
        app.dependency_overrides.clear()

    assert detail_response.status_code == 200
    assert patch_response.status_code == patch_status
    assert delete_response.status_code == delete_status


def test_analyst_cannot_upload_sample_directly() -> None:
    db = MagicMock()
    actor = make_admin()
    actor.rol.nombre = "Analista"
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: actor
    try:
        client = TestClient(app)
        token = client.get("/auth/csrf").json()["csrf_token"]
        response = client.post(
            "/personas/42/muestras",
            headers={"X-CSRF-Token": token},
            files={"file": ("muestra.wav", b"contenido-controlado", "audio/wav")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    db.add.assert_not_called()
    db.commit.assert_not_called()

