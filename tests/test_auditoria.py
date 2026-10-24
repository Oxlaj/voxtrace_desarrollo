from datetime import datetime, timedelta
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request
from backend.api.auditoria import list_logs, safe_details
from backend.core.security import get_current_user
from backend.main import app
from backend.models.log import Log
from backend.models.rol import Rol
from backend.models.usuario import Usuario

def user(role="Administrador",user_id=1): return Usuario(id_usuario=user_id,id_rol=1,nombre="Admin",correo="admin@example.com",password_hash="hidden",estado=True,rol=Rol(id_rol=1,nombre=role))
def request(): return Request({"type":"http","method":"GET","path":"/logs","headers":[],"query_string":b"","client":("192.0.2.1",1)})
def call(db,**kw):
    args=dict(request=request(),fecha_desde=None,fecha_hasta=None,id_usuario=None,accion=None,direccion_ip=None,busqueda=None,pagina=1,tamano_pagina=20,db=db,current_user=user());args.update(kw);return list_logs(**args)

def test_admin_list_is_ordered_paginated_null_user_and_audited(monkeypatch):
    db=MagicMock(); db.scalar.return_value=1; entry=Log(id_log=5,id_usuario=None,accion="login_fallido",fecha=datetime(2026,9,9),direccion_ip=None,detalles="credenciales_invalidas");db.execute.return_value.all.return_value=[(entry,None)];events=[];monkeypatch.setattr("backend.api.auditoria.record_event",lambda *a,**k: events.append(a[1]))
    result=call(db,pagina=2,tamano_pagina=20)
    assert result.total==1 and result.pagina==2 and result.items[0].usuario is None
    statement=str(db.execute.call_args.args[0]);assert "ORDER BY" in statement and "DESC" in statement and "LIMIT" in statement and "OFFSET" in statement
    assert events==["auditoria_consultada"]

def test_filters_and_invalid_dates(monkeypatch):
    db=MagicMock();db.scalar.return_value=0;db.execute.return_value.all.return_value=[];monkeypatch.setattr("backend.api.auditoria.record_event",lambda *a,**k: True)
    call(db,fecha_desde=datetime(2026,9,1),fecha_hasta=datetime(2026,9,9),id_usuario=2,accion="login",direccion_ip="127.0.0.1",busqueda="sesion")
    statement=str(db.execute.call_args.args[0]);assert all(value in statement for value in ("log.fecha", "log.id_usuario", "log.accion", "log.direccion_ip", "log.detalles"))
    with pytest.raises(HTTPException) as error: call(db,fecha_desde=datetime.now(),fecha_hasta=datetime.now()-timedelta(days=1))
    assert error.value.status_code==422

@pytest.mark.parametrize("value",["password=secret","storage/audio/file.wav","a"*64,"embedding=[1,2]","SELECT value FROM secret","Traceback (most recent call last)"])
def test_sensitive_details_are_omitted(value): assert safe_details(value)=="Detalle omitido por seguridad"
def test_safe_details_are_preserved(): assert safe_details("id_analisis=17")=="id_analisis=17"

@pytest.mark.parametrize(("role","status"),[("Administrador",200),("Investigador",403),("Analista",403)])
def test_frontend_access_and_menu_by_role(role,status):
    app.dependency_overrides[get_current_user]=lambda:user(role)
    try: response=TestClient(app).get("/app/auditoria");menu=TestClient(app).get("/dashboard").text
    finally: app.dependency_overrides.clear()
    assert response.status_code==status;assert ('href="/app/auditoria"' in menu) is (role=="Administrador")

def test_without_session_is_401(): assert TestClient(app).get("/app/auditoria").status_code==401
def test_mutable_log_routes_do_not_exist():
    client=TestClient(app);token=client.get("/auth/csrf").json()["csrf_token"]
    assert client.post("/logs",headers={"X-CSRF-Token":token}).status_code==405

def test_frontend_filters_pagination_null_identity_and_privacy():
    client=TestClient(app);script=client.get("/static/js/auditoria.js").text
    for value in ("fecha_desde","fecha_hasta","id_usuario","accion","direccion_ip","busqueda","pagina","tamano_pagina","Sistema / usuario no disponible","audit-prev","audit-next"):assert value in script
    for value in ("password_hash","SESSION_SECRET","csrf_token","embedding.vector","localStorage","sessionStorage"):assert value not in script
