from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PersonaBase(BaseModel):
    nombre: str = Field(min_length=1, max_length=150)
    identificador: str = Field(min_length=1, max_length=50)
    alias: str | None = Field(default=None, max_length=100)
    descripcion: str | None = None
    observaciones: str | None = None


class PersonaCreate(PersonaBase):
    pass


class PersonaUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=150)
    identificador: str | None = Field(default=None, min_length=1, max_length=50)
    alias: str | None = Field(default=None, max_length=100)
    descripcion: str | None = None
    observaciones: str | None = None


class PersonaRead(PersonaBase):
    model_config = ConfigDict(from_attributes=True)

    id_persona: int
    fecha_registro: datetime
