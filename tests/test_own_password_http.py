"""Account password page and endpoint with real auth/CSRF and a fake DB."""
import importlib
from unittest.mock import MagicMock

import pytest
from fastapi.staticfiles import StaticFiles

from test_analysis_reuse_http import http_case, login, csrf


@pytest.fixture
def account(http_case, monkeypatch):
    web = importlib.import_module("backend.api.web")
    users = importlib.import_module("backend.api.usuarios")
    http_case.app.include_router(web.router)
    http_case.app.include_router(users.router)
    http_case.app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
    monkeypatch.setattr(users, "record_event", MagicMock(return_value=True))
    http_case.users = users
    return http_case


@pytest.mark.parametrize("role", ["Administrador", "Investigador", "Analista"])
def test_menu_has_visible_own_password_link(account, role):
    login(account, role)
    response = account.client.get("/dashboard")
    assert response.status_code == 200
    assert 'href="/app/cambiar-password" class="nav-link">Cambiar contraseña</a>' in response.text


@pytest.mark.parametrize("role", ["Administrador", "Investigador", "Analista"])
@pytest.mark.parametrize("pending", [False, True])
def test_page_text_matches_voluntary_or_required_change(account, role, pending):
    login(account, role, pending)
    response = account.client.get("/app/cambiar-password")
    assert response.status_code == 200
    assert ("Debes establecer una nueva contraseña antes de continuar." in response.text) is pending
    assert ("Puedes actualizar la contraseña de tu cuenta" in response.text) is not pending
    assert ("Cancelar y volver al dashboard" in response.text) is not pending
    assert 'meta name="csrf-token"' in response.text
    assert 'minlength="12"' in response.text and 'maxlength="128"' in response.text
    script = account.client.get("/static/js/cambiar_password.js").text
    assert 'request("/cuenta/password"' in script and 'method: "POST"' in script
    assert "Las contraseñas no coinciden." in script


@pytest.mark.parametrize("role", ["Administrador", "Investigador", "Analista"])
@pytest.mark.parametrize("pending", [False, True])
def test_own_password_endpoint_works_for_each_role_and_mode(account, role, pending):
    token = login(account, role, pending)
    response = account.client.post("/cuenta/password", headers={"X-CSRF-Token": token},
                                   json={"password": "New-own-password-123"})
    assert response.status_code == 204
    security = importlib.import_module("backend.core.security")
    assert security.verify_password("New-own-password-123", account.user.password_hash)
    assert account.user.debe_cambiar_password is False
    account.db.commit.assert_called_once()
    assert account.users.record_event.call_args.args[2] == account.user.id_usuario


def test_page_and_endpoint_require_authenticated_session(account):
    assert account.client.get("/app/cambiar-password").status_code == 401
    token = csrf(account)
    assert account.client.post("/cuenta/password", headers={"X-CSRF-Token": token},
                               json={"password": "New-own-password-123"}).status_code == 401
    account.db.commit.assert_not_called()


@pytest.mark.parametrize("token", [None, "invalid"])
def test_password_change_keeps_csrf_protection(account, token):
    login(account)
    headers = {} if token is None else {"X-CSRF-Token": token}
    assert account.client.post("/cuenta/password", headers=headers,
                               json={"password": "New-own-password-123"}).status_code == 403
    account.db.commit.assert_not_called()


def test_short_password_rejected_without_changes(account):
    token = login(account)
    previous = account.user.password_hash
    assert account.client.post("/cuenta/password", headers={"X-CSRF-Token": token},
                               json={"password": "short"}).status_code == 422
    assert account.user.password_hash == previous
    account.db.commit.assert_not_called()
