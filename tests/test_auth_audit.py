from unittest.mock import MagicMock

from starlette.requests import Request

from backend.api.auth import LoginRequest, login, logout
from backend.core.security import hash_password
from backend.models.log import Log
from backend.models.rol import Rol
from backend.models.usuario import Usuario


def make_request(session: dict | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("192.0.2.30", 50000),
            "scheme": "http",
            "root_path": "",
            "http_version": "1.1",
            "session": session or {},
        }
    )


def make_admin() -> Usuario:
    return Usuario(
        id_usuario=7,
        id_rol=1,
        nombre="Admin",
        correo="admin@example.com",
        password_hash=hash_password("secret"),
        estado=True,
        debe_cambiar_password=False,
        rol=Rol(id_rol=1, nombre="Administrador"),
    )


def audit_action(db: MagicMock) -> str:
    event = db.add.call_args.args[0]
    assert isinstance(event, Log)
    return event.accion


def test_successful_login_is_audited() -> None:
    db = MagicMock()
    db.scalar.return_value = make_admin()
    request = make_request()

    response = login(LoginRequest(correo="admin@example.com", password="secret"), request, db)

    assert response == {"message": "Sesión iniciada", "debe_cambiar_password": False}
    assert isinstance(response["debe_cambiar_password"], bool)
    assert request.session["user_id"] == 7
    assert audit_action(db) == "login_exitoso"


def test_failed_login_is_audited_without_user_id() -> None:
    db = MagicMock()
    db.scalar.return_value = None
    request = make_request()

    try:
        login(LoginRequest(correo="admin@example.com", password="wrong"), request, db)
    except Exception as error:
        assert error.status_code == 401

    event = db.add.call_args.args[0]
    assert event.accion == "login_fallido"
    assert event.id_usuario is None
    assert "password" not in (event.detalles or "").lower()


def test_logout_is_audited_and_clears_session() -> None:
    db = MagicMock()
    session = {"user_id": 7}
    request = make_request(session)

    response = logout(request, db)

    assert response == {"message": "Sesión cerrada"}
    assert request.session == {}
    assert audit_action(db) == "logout"
