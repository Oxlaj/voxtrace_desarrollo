from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from starlette.requests import Request
from backend.api.usuarios import create_user, get_user, list_users, update_user, change_user_password
from backend.core.security import get_current_user, verify_password
from backend.main import app
from backend.models.rol import Rol
from backend.models.usuario import Usuario
from backend.schemas.usuario import PasswordAdminUpdate, UsuarioCreate, UsuarioUpdate

def role(name="Administrador", role_id=1): return Rol(id_rol=role_id,nombre=name,descripcion=None)
def user(name="Admin", role_name="Administrador", user_id=1, active=True): return Usuario(id_usuario=user_id,id_rol=1,nombre=name,correo=f"u{user_id}@example.com",password_hash="hidden",fecha_creacion=datetime(2026,9,8),estado=active,rol=role(role_name))
def request(path="/usuarios"): return Request({"type":"http","method":"POST","path":path,"headers":[],"query_string":b"","client":("test",1)})

def test_create_hashes_password_and_never_returns_it(monkeypatch):
    db=MagicMock(); admin=user(); target_role=role("Analista",3); db.get.return_value=target_role; db.scalar.return_value=None
    def refresh(entity): entity.id_usuario=9; entity.fecha_creacion=datetime(2026,9,8)
    db.refresh.side_effect=refresh; monkeypatch.setattr("backend.api.usuarios.record_event",lambda *a,**k: True)
    result=create_user(UsuarioCreate(nombre="Nueva",correo="new@example.com",id_rol=3,password="strong-password"),request(),db,admin)
    created=db.add.call_args.args[0]
    assert created.password_hash!="strong-password" and verify_password("strong-password",created.password_hash)
    assert "password" not in result.model_dump() and "password_hash" not in result.model_dump()

def test_duplicate_email_and_missing_user():
    db=MagicMock(); db.get.return_value=role("Analista",3); db.scalar.return_value=user(user_id=2)
    with pytest.raises(HTTPException) as conflict: create_user(UsuarioCreate(nombre="N",correo="u2@example.com",id_rol=3,password="strong-password"),request(),db,user())
    assert conflict.value.status_code==409
    db=MagicMock(); db.get.return_value=None
    with pytest.raises(HTTPException) as missing: get_user(99,db,user())
    assert missing.value.status_code==404

def test_last_active_admin_cannot_be_deactivated_or_demoted():
    for payload in (UsuarioUpdate(estado=False),UsuarioUpdate(id_rol=2)):
        db=MagicMock(); target=user(); investigator=role("Investigador",2)
        db.get.side_effect=lambda model,key: target if model is Usuario else investigator
        db.scalar.return_value=1
        with pytest.raises(HTTPException) as denied: update_user(1,payload,request("/usuarios/1"),db,user())
        assert denied.value.status_code==409
        db.commit.assert_not_called()

def test_update_and_password_change_are_audited_without_secret(monkeypatch):
    db=MagicMock(); target=user(role_name="Analista",user_id=2); db.get.side_effect=lambda model,key: target if model is Usuario else role("Analista",3); db.scalar.return_value=None
    events=[]; monkeypatch.setattr("backend.api.usuarios.record_event",lambda *a,**k: events.append(a[4]))
    update_user(2,UsuarioUpdate(nombre="Editado",id_rol=3,estado=False),request(),db,user())
    change_user_password(2,PasswordAdminUpdate(password="another-strong-password"),request(),db,user())
    assert verify_password("another-strong-password",target.password_hash)
    assert all("password" not in detail and "strong" not in detail for detail in events)
    assert db.commit.call_count==2

@pytest.mark.parametrize(("role_name","status"),[("Administrador",200),("Investigador",403),("Analista",403)])
def test_admin_pages_rbac_and_menu(role_name,status):
    current=user(role_name=role_name)
    app.dependency_overrides[get_current_user]=lambda: current
    try:
        response=TestClient(app).get("/app/usuarios")
        dashboard=TestClient(app).get("/dashboard")
    finally: app.dependency_overrides.clear()
    assert response.status_code==status
    assert ('href="/app/usuarios"' in dashboard.text) is (role_name=="Administrador")

def test_frontend_has_filters_password_confirmation_and_no_sensitive_storage():
    client=TestClient(app); scripts=client.get("/static/js/usuarios.js").text+client.get("/static/js/usuario-form.js").text
    assert all(value in scripts for value in ("busqueda","id_rol","estado","password"))
    assert "password_hash" not in scripts and "localStorage" not in scripts and "sessionStorage" not in scripts

def test_password_form_keeps_stable_reference_across_async_request():
    script=TestClient(app).get("/static/js/usuario-form.js").text
    capture="const passwordForm=e.currentTarget"
    request_call="await VoxTraceAPI.request(`/usuarios/${userId}/password`"
    reset="passwordForm.reset()"
    assert capture in script
    assert script.index(capture) < script.index(request_call) < script.index(reset)
    assert "e.currentTarget.reset()" not in script
    assert "Contraseña actualizada correctamente." in script

def test_password_form_handles_successful_204_without_javascript_error():
    matches=sorted(Path.home().glob("AppData/Local/ms-playwright/chromium-*/chrome-win*/chrome.exe"),reverse=True)
    if not matches: pytest.skip("Chromium E2E no disponible")
    page_errors=[]
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True,executable_path=str(matches[0]))
        page=browser.new_page()
        page.on("pageerror",lambda error: page_errors.append(str(error)))

        def api(route):
            path=route.request.url
            if path.endswith("/roles"):
                route.fulfill(status=200,content_type="application/json",body='[{"id_rol":1,"nombre":"Administrador","descripcion":null}]')
            elif path.endswith("/usuarios/9/password"):
                route.fulfill(status=204,headers={"content-type":"application/json"},body="")
            else:
                route.fulfill(status=200,content_type="application/json",body='{"id_usuario":9,"nombre":"Usuario","correo":"usuario@example.com","estado":true,"rol":{"id_rol":1,"nombre":"Administrador","descripcion":null}}')

        page.route("**/roles",api)
        page.route("**/usuarios/9",api)
        page.route("**/usuarios/9/password",api)
        page.set_content('''
            <base href="http://voxtrace.test/">
            <meta name="csrf-token" content="token-controlado">
            <form id="user-form"><input id="user-name"><input id="user-email"><select id="user-role"></select><select id="user-state"><option value="true">Activo</option></select><div id="user-form-message"></div></form>
            <form id="password-form"><input id="new-password"><input id="new-password-confirm"><div id="password-message"></div><button type="submit">Cambiar</button></form>
            <div id="user-context" data-user-id="9"></div>
        ''')
        page.add_script_tag(path=str(Path("frontend/static/js/api.js").resolve()))
        page.add_script_tag(path=str(Path("frontend/static/js/usuario-form.js").resolve()))
        page.fill("#new-password","clave-controlada-123")
        page.fill("#new-password-confirm","clave-controlada-123")
        page.click('#password-form button[type="submit"]')
        page.wait_for_function("document.querySelector('#password-message').textContent.length > 0")

        assert page.input_value("#new-password")==""
        assert page.input_value("#new-password-confirm")==""
        assert page.locator("#password-message").inner_text()=="Contraseña actualizada correctamente."
        assert "No fue posible cambiar la contraseña." not in page.locator("#password-message").inner_text()
        assert not page_errors
        browser.close()

def test_mutable_user_api_requires_csrf():
    assert TestClient(app).post("/usuarios",json={}).status_code==403
