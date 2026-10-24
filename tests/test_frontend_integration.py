from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from backend.api.auth import authenticated_user
from backend.api.personas import create_persona
from backend.core.security import get_current_user
from backend.main import app
from backend.models.persona import Persona
from backend.models.rol import Rol
from backend.models.usuario import Usuario
from backend.schemas.persona import PersonaCreate


def make_user(role: str = "Administrador") -> Usuario:
    return Usuario(id_usuario=7, id_rol=1, nombre="Usuario autorizado", correo="usuario@example.com", password_hash="hidden", estado=True, rol=Rol(id_rol=1, nombre=role))


def make_request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/personas", "headers": [], "query_string": b"", "client": ("192.0.2.90", 50000)})


def test_login_page_renders_real_form_without_browser_storage() -> None:
    client = TestClient(app)
    response = client.get("/login")
    script = client.get("/static/js/login.js").text

    assert response.status_code == 200
    assert 'id="login-form"' in response.text
    assert 'autocomplete="current-password"' in response.text
    assert "/auth/login" in script
    assert "localStorage" not in script
    assert "sessionStorage" not in script


@pytest.mark.parametrize("path", ["/dashboard", "/app/personas", "/app/personas/nueva", "/app/personas/1/muestras"])
def test_protected_pages_reject_unauthenticated_access(path: str) -> None:
    assert TestClient(app).get(path).status_code == 401


def test_auth_me_returns_only_public_session_identity() -> None:
    payload = authenticated_user(make_user()).model_dump()

    assert payload == {"id_usuario": 7, "nombre": "Usuario autorizado", "correo": "usuario@example.com", "rol": "Administrador"}
    assert "password_hash" not in payload
    assert "cookie" not in payload


@pytest.mark.parametrize(
    ("role", "can_register"),
    [("Administrador", True), ("Investigador", True), ("Analista", False)],
)
def test_dashboard_and_people_render_role_appropriate_actions(role: str, can_register: bool) -> None:
    app.dependency_overrides[get_current_user] = lambda: make_user(role)
    try:
        client = TestClient(app)
        dashboard = client.get("/dashboard")
        people = client.get("/app/personas")
    finally:
        app.dependency_overrides.clear()

    assert dashboard.status_code == 200
    assert people.status_code == 200
    assert "Usuario autorizado" in dashboard.text
    assert role in dashboard.text
    assert ("Registrar persona" in dashboard.text) is can_register
    assert ("Registrar persona" in people.text) is can_register
    assert f'data-role="{role}"' in people.text
    for removed in (
        "Sesión activa como",
        "Entorno de apoyo analítico",
        "Consultar el registro autorizado de personas.",
        "Buscar posibles coincidencias entre las voces registradas.",
        "Crear un registro conforme al modelo oficial.",
        "Consultar análisis almacenados conforme a sus permisos.",
        "Registro autorizado",
        "Análisis biométrico de voz",
    ):
        assert removed not in dashboard.text + people.text


def test_analyst_cannot_open_person_registration_page() -> None:
    app.dependency_overrides[get_current_user] = lambda: make_user("Analista")
    try:
        response = TestClient(app).get("/app/personas/nueva")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 403


def test_create_person_contract_persists_required_fields() -> None:
    db = MagicMock()
    db.scalar.return_value = None
    db.refresh.side_effect = lambda person: (setattr(person, "id_persona", 12), setattr(person, "fecha_registro", datetime(2026, 9, 12)))
    payload = PersonaCreate(identificador="P-012", nombre="Persona doce", alias="Referencia")

    result = create_persona(payload, make_request(), db, make_user("Investigador"))

    assert result.identificador == "P-012"
    assert result.nombre == "Persona doce"
    db.commit.assert_called()


def test_duplicate_identifier_returns_conflict_without_clearing_frontend_form() -> None:
    db = MagicMock()
    db.scalar.return_value = Persona(id_persona=1, identificador="P-001", nombre="Existente")

    with pytest.raises(HTTPException) as conflict:
        create_persona(PersonaCreate(identificador="P-001", nombre="Nueva"), make_request(), db, make_user())

    form_script = TestClient(app).get("/static/js/persona-form.js").text
    assert conflict.value.status_code == 409
    assert "form.reset" not in form_script
    assert "identificador ya está registrado" in form_script


def test_people_script_handles_loading_empty_detail_and_crud_endpoints() -> None:
    script = TestClient(app).get("/static/js/personas.js").text

    for expected in ("Cargando personas", "No hay personas registradas", "Ver detalle", 'method: "PATCH"', 'method: "DELETE"'):
        assert expected in script
    assert "localStorage" not in script
    assert "sessionStorage" not in script


def test_people_script_explains_update_validation_and_delete_conflict() -> None:
    script = TestClient(app).get("/static/js/personas.js").text

    for status in ("400:", "403:", "404:", "409:", "422:", "500:"):
        assert status in script
    assert "Revisa los campos obligatorios y sus longitudes." in script
    assert "información asociada que debe conservarse" in script


@pytest.mark.parametrize(
    ("role", "can_edit", "can_delete"),
    [
        ("Administrador", True, True),
        ("Investigador", True, False),
        ("Analista", False, False),
    ],
)
def test_person_detail_controls_follow_role(
    role: str, can_edit: bool, can_delete: bool
) -> None:
    app.dependency_overrides[get_current_user] = lambda: make_user(role)
    try:
        response = TestClient(app).get("/app/personas")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert ('class="button button-primary can-edit"' in response.text) is can_edit
    assert ('id="delete-person"' in response.text) is can_delete
    assert ("Registrar persona" in response.text) is can_edit
    if role == "Analista":
        assert response.text.count("readonly") >= 5


def test_logout_script_uses_backend_and_does_not_manipulate_cookies() -> None:
    script = TestClient(app).get("/static/js/app.js").text

    assert "/auth/logout" in script
    assert "document.cookie" not in script
    assert 'window.location.assign("/login")' in script


@pytest.mark.parametrize(("role", "can_upload"), [("Administrador", True), ("Investigador", True), ("Analista", False)])
def test_samples_page_respects_visual_upload_permissions(role: str, can_upload: bool) -> None:
    app.dependency_overrides[get_current_user] = lambda: make_user(role)
    try:
        response = TestClient(app).get("/app/personas/3/muestras")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Muestras de voz" in response.text
    assert ('id="sample-form"' in response.text) is can_upload
    assert "duración se registrará" in response.text
    assert "Duración mínima" not in response.text


def test_samples_frontend_uses_safe_api_and_multipart_without_browser_storage() -> None:
    client = TestClient(app)
    script = client.get("/static/js/muestras.js").text
    api_script = client.get("/static/js/api.js").text

    assert "new FormData()" in script
    assert "/muestras" in script
    assert "Representación biométrica" in script
    assert "hash_archivo" not in script
    assert "ruta_archivo" not in script
    assert "localStorage" not in script and "sessionStorage" not in script
    assert "instanceof FormData" in api_script
