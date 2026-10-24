import re
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from backend.core.security import require_roles
from backend.database.connection import get_db
from backend.models.log import Log
from backend.models.usuario import Usuario
from backend.schemas.auditoria import AuditItemResponse, AuditPageResponse, AuditUserResponse
from backend.services.audit_service import record_event

router = APIRouter(prefix="/logs", tags=["auditoria"])
_SENSITIVE = re.compile(r"(?i)(password|contrase(?:ña|na)|password_hash|cookie|session_secret|csrf|embedding|vector|traceback|stack\s*trace|sha.?256|(?:[a-z]:\\|storage[/\\]|/users/)|(?:select\s+.+from|insert\s+into|delete\s+from|update\s+.+set)|(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f]))")

def safe_details(value: str | None) -> str | None:
    if value is None: return None
    return "Detalle omitido por seguridad" if _SENSITIVE.search(value) else value

@router.get("", response_model=AuditPageResponse)
def list_logs(request: Request, fecha_desde: datetime | None = None, fecha_hasta: datetime | None = None, id_usuario: int | None = Query(default=None, gt=0), accion: str | None = Query(default=None, max_length=150), direccion_ip: str | None = Query(default=None, max_length=45), busqueda: str | None = Query(default=None, max_length=100), pagina: int = Query(default=1, ge=1), tamano_pagina: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db), current_user: Usuario = Depends(require_roles("Administrador"))) -> AuditPageResponse:
    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta: raise HTTPException(422, "fecha_desde no puede ser posterior a fecha_hasta")
    filters=[]
    if fecha_desde: filters.append(Log.fecha >= fecha_desde)
    if fecha_hasta: filters.append(Log.fecha <= fecha_hasta)
    if id_usuario is not None: filters.append(Log.id_usuario == id_usuario)
    if accion: filters.append(Log.accion.ilike(f"%{accion.strip()}%"))
    if direccion_ip: filters.append(Log.direccion_ip == direccion_ip.strip())
    if busqueda:
        term=f"%{busqueda.strip()}%"; filters.append(or_(Log.accion.ilike(term), Log.detalles.ilike(term)))
    total=db.scalar(select(func.count()).select_from(Log).where(*filters)) or 0
    rows=db.execute(select(Log,Usuario).outerjoin(Usuario,Usuario.id_usuario==Log.id_usuario).where(*filters).order_by(Log.fecha.desc(),Log.id_log.desc()).offset((pagina-1)*tamano_pagina).limit(tamano_pagina)).all()
    items=[AuditItemResponse(id_log=entry.id_log,fecha=entry.fecha,usuario=AuditUserResponse(id_usuario=user.id_usuario,nombre=user.nombre,correo=user.correo) if user else None,accion=entry.accion,direccion_ip=entry.direccion_ip,detalles=safe_details(entry.detalles)) for entry,user in rows]
    record_event(db,"auditoria_consultada",current_user.id_usuario,request,f"pagina={pagina}")
    return AuditPageResponse(items=items,pagina=pagina,tamano_pagina=tamano_pagina,total=total)
