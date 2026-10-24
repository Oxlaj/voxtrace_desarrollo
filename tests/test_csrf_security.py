from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.core.config import settings
from backend.core.security import hash_password
from backend.database.connection import get_db
from backend.main import app
from backend.models.rol import Rol
from backend.models.usuario import Usuario
from backend.core.security import get_current_user
from backend.services.audio_processing_service import AudioProcessingResult
from backend.api import muestras
from backend.models.persona import Persona
from datetime import datetime
from pathlib import Path


def make_user() -> Usuario:
    return Usuario(
        id_usuario=7,
        id_rol=1,
        nombre="Usuario seguro",
        correo="seguro@example.com",
        password_hash=hash_password("correct-password"),
        estado=True,
        rol=Rol(id_rol=1, nombre="Administrador"),
    )


def csrf(client: TestClient) -> str:
    response = client.get("/auth/csrf")
    assert response.status_code == 200
    return response.json()["csrf_token"]


@pytest.fixture
def mocked_client():
    db = MagicMock()
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app), db
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_mutable_request_without_token_is_rejected_before_operation(mocked_client, method: str) -> None:
    client, db = mocked_client

    response = getattr(client, method)("/personas")

    assert response.status_code == 403
    assert response.json() == {"detail": "Token CSRF ausente o inválido"}
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_invalid_token_is_rejected_without_partial_operation(mocked_client) -> None:
    client, db = mocked_client
    csrf(client)

    response = client.post("/auth/logout", headers={"X-CSRF-Token": "invalid"})

    assert response.status_code == 403
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_valid_token_allows_mutable_request(mocked_client) -> None:
    client, db = mocked_client
    token = csrf(client)

    response = client.post("/auth/logout", headers={"X-CSRF-Token": token})

    assert response.status_code == 200
    assert response.json() == {"message": "Sesión cerrada"}
    db.add.assert_called_once()


def test_login_uses_preauthenticated_token_and_rotates_it(mocked_client) -> None:
    client, db = mocked_client
    user = make_user()
    db.scalar.return_value = user
    db.get.return_value = user
    initial_token = csrf(client)

    login = client.post(
        "/auth/login",
        headers={"X-CSRF-Token": initial_token},
        json={"correo": "seguro@example.com", "password": "correct-password"},
    )
    rotated_token = csrf(client)
    me = client.get("/auth/me")

    assert login.status_code == 200
    assert rotated_token != initial_token
    assert me.status_code == 200
    assert me.json()["rol"] == "Administrador"


def test_invalid_login_with_valid_csrf_returns_401(mocked_client) -> None:
    client, db = mocked_client
    db.scalar.return_value = None
    token = csrf(client)

    response = client.post(
        "/auth/login",
        headers={"X-CSRF-Token": token},
        json={"correo": "nadie@example.com", "password": "incorrect"},
    )

    assert response.status_code == 401
    assert "csrf" not in response.text.lower()


def test_read_only_requests_do_not_require_csrf() -> None:
    assert TestClient(app).get("/health").status_code == 200


def test_login_page_exposes_session_token_only_in_csrf_meta() -> None:
    response = TestClient(app).get("/login")

    assert response.status_code == 200
    assert 'meta name="csrf-token"' in response.text
    assert "SESSION_SECRET" not in response.text
    assert "password_hash" not in response.text


def test_frontend_sends_csrf_header_without_browser_storage() -> None:
    script = TestClient(app).get("/static/js/api.js").text

    assert 'headers["X-CSRF-Token"]' in script
    assert 'meta[name="csrf-token"]' in script
    assert "localStorage" not in script
    assert "sessionStorage" not in script
    assert "document.cookie" not in script


def test_session_cookie_configuration_is_centralized() -> None:
    session_middleware = next(item for item in app.user_middleware if item.cls.__name__ == "SessionMiddleware")

    assert session_middleware.kwargs["secret_key"] == settings.session_secret
    assert session_middleware.kwargs["session_cookie"] == settings.session_cookie_name
    assert session_middleware.kwargs["https_only"] == settings.session_cookie_secure
    assert session_middleware.kwargs["same_site"] == settings.session_cookie_samesite
    assert len(settings.session_secret) >= 32


def test_session_cookie_has_httponly_samesite_and_environment_secure_flag() -> None:
    response = TestClient(app).get("/auth/csrf")
    cookie = response.headers["set-cookie"].lower()

    assert "httponly" in cookie
    assert f"samesite={settings.session_cookie_samesite}" in cookie
    assert ("secure" in cookie) is settings.session_cookie_secure


def test_multipart_sample_upload_requires_and_accepts_csrf(mocked_client, monkeypatch, tmp_path) -> None:
    client, db = mocked_client
    user = make_user()
    app.dependency_overrides[get_current_user] = lambda: user
    original = tmp_path / "original.wav"
    processed = tmp_path / "processed.wav"
    processed.write_bytes(b"processed")

    async def fake_store(upload, category):
        original.write_bytes(b"original")
        return MagicMock(path=original, original_name="voz.wav", extension="wav", sha256="e" * 64)

    monkeypatch.setattr(muestras, "store_original_audio", fake_store)
    monkeypatch.setattr(muestras, "process_audio_copy", lambda *args, **kwargs: AudioProcessingResult(61, processed))
    monkeypatch.setattr(muestras, "generate_embedding", lambda path: [0.1] * 192)
    monkeypatch.setattr(muestras, "record_event", lambda *args, **kwargs: True)
    db.get.return_value = Persona(id_persona=3, identificador="P-3", nombre="Persona")
    db.scalar.return_value = None

    def flush():
        audio = next(call.args[0] for call in db.add.call_args_list if call.args[0].__class__.__name__ == "Audio")
        audio.id_audio = 88
        audio.fecha_subida = datetime(2026, 9, 8)
    db.flush.side_effect = flush
    token = csrf(client)

    missing = client.post("/personas/3/muestras", files={"file": ("voz.wav", b"x", "audio/wav")})
    invalid = client.post("/personas/3/muestras", headers={"X-CSRF-Token": "wrong"}, files={"file": ("voz.wav", b"x", "audio/wav")})
    valid = client.post("/personas/3/muestras", headers={"X-CSRF-Token": token}, files={"file": ("voz.wav", b"x", "audio/wav")})

    assert missing.status_code == invalid.status_code == 403
    assert valid.status_code == 201
    assert valid.json()["estado_procesamiento"] == "embedding_disponible"
    assert "hash_archivo" not in valid.json() and "ruta_archivo" not in valid.json()
