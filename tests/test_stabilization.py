from datetime import datetime
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from starlette.requests import Request
from backend.api import usuarios
from backend.core.security import get_current_user
from backend.main import app
from backend.models.rol import Rol
from backend.models.usuario import Usuario
from backend.schemas.usuario import UsuarioCreate

def make_user(role="Administrador",active=True): return Usuario(id_usuario=1,id_rol=1,nombre="Usuario",correo="u@example.com",password_hash="hidden",fecha_creacion=datetime(2026,9,9),estado=active,rol=Rol(id_rol=1,nombre=role,descripcion=None))
def request(): return Request({"type":"http","method":"POST","path":"/usuarios","headers":[],"query_string":b"","client":("test",1)})

def test_no_duplicate_method_path_registrations():
    registrations=[(method,route.path) for route in app.routes for method in (getattr(route,"methods",None) or set()) if method not in {"HEAD","OPTIONS"}]
    assert len(registrations)==len(set(registrations))

@pytest.mark.parametrize("role,allowed",[("Administrador",{"/dashboard","/app/personas","/app/personas/nueva","/app/analizar","/app/historial","/app/usuarios","/app/auditoria"}),("Investigador",{"/dashboard","/app/personas","/app/personas/nueva","/app/analizar","/app/historial"}),("Analista",{"/dashboard","/app/personas","/app/analizar","/app/historial"})])
def test_navigation_links_exist_and_match_role(role,allowed):
    app.dependency_overrides[get_current_user]=lambda:make_user(role)
    try:
        client=TestClient(app);html=client.get("/dashboard").text
        for path in allowed: assert client.get(path).status_code==200
    finally: app.dependency_overrides.clear()
    assert ('href="/app/usuarios"' in html)==(role=="Administrador")
    assert ('href="/app/auditoria"' in html)==(role=="Administrador")
    assert ('href="/app/personas/nueva"' in html)==(role in {"Administrador","Investigador"})

def test_user_creation_unexpected_database_failure_rolls_back(monkeypatch):
    db=MagicMock();role=Rol(id_rol=3,nombre="Analista",descripcion=None);db.get.return_value=role;db.scalar.return_value=None;db.commit.side_effect=SQLAlchemyError("database unavailable");monkeypatch.setattr(usuarios,"record_event",lambda *a,**k: True)
    with pytest.raises(HTTPException) as error: usuarios.create_user(UsuarioCreate(nombre="Test",correo="test@example.com",id_rol=3,password="strong-password"),request(),db,make_user())
    assert error.value.status_code==500;db.rollback.assert_called_once()

def test_profile_and_password_forms_are_separate_operations():
    client=TestClient(app);script=client.get("/static/js/usuario-form.js").text
    assert 'document.getElementById("password-form")' in script
    assert 'VoxTraceAPI.request(`/usuarios/${userId}`' in script
    assert 'VoxTraceAPI.request(`/usuarios/${userId}/password`' in script
    assert script.index('VoxTraceAPI.request(`/usuarios/${userId}`') < script.index('document.getElementById("password-form")')

def test_public_openapi_contracts_exclude_sensitive_model_fields():
    schema=TestClient(app).get("/openapi.json").json();serialized=str(schema)
    for path in ("/auth/me","/personas","/historial","/reportes/analisis/{analysis_id}","/usuarios","/logs"): assert path in schema["paths"]
    assert "password_hash" not in serialized

def test_read_pages_require_session_and_mutations_require_csrf():
    client=TestClient(app)
    for path in ("/dashboard","/app/personas","/app/analizar","/app/historial","/app/usuarios","/app/auditoria"): assert client.get(path).status_code==401
    for method,path in (("post","/personas"),("post","/analisis/identificacion"),("patch","/usuarios/1"),("post","/auth/logout")): assert getattr(client,method)(path).status_code==403
