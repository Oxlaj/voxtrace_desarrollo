from datetime import datetime
from pydantic import BaseModel

class AuditUserResponse(BaseModel):
    id_usuario: int
    nombre: str
    correo: str

class AuditItemResponse(BaseModel):
    id_log: int
    fecha: datetime
    usuario: AuditUserResponse | None
    accion: str
    direccion_ip: str | None
    detalles: str | None

class AuditPageResponse(BaseModel):
    items: list[AuditItemResponse]
    pagina: int
    tamano_pagina: int
    total: int
