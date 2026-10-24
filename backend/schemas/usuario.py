from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class RolRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_rol: int
    nombre: str
    descripcion: str | None

class UsuarioRead(BaseModel):
    id_usuario: int
    nombre: str
    correo: str
    estado: bool
    debe_cambiar_password: bool
    fecha_creacion: datetime
    rol: RolRead

class UsuarioCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    correo: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=150)
    id_rol: int = Field(gt=0)
    password: str = Field(min_length=12, max_length=128)

class UsuarioUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    correo: str | None = Field(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=150)
    id_rol: int | None = Field(default=None, gt=0)
    estado: bool | None = None

class PasswordAdminUpdate(BaseModel):
    password: str = Field(min_length=12, max_length=128)

class PasswordSelfUpdate(BaseModel):
    password: str = Field(min_length=12, max_length=128)
