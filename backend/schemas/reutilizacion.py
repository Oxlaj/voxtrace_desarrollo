from typing import Literal

from pydantic import BaseModel, Field, model_validator

from backend.schemas.persona import PersonaCreate


class ReutilizarAudioRequest(BaseModel):
    confirmar: Literal[True]
    id_persona: int | None = Field(default=None, gt=0)
    nueva_persona: PersonaCreate | None = None

    @model_validator(mode="after")
    def one_destination(self) -> "ReutilizarAudioRequest":
        if (self.id_persona is None) == (self.nueva_persona is None):
            raise ValueError("Selecciona una persona existente o registra una nueva")
        return self


class ReutilizarAudioResponse(BaseModel):
    id_analisis: int
    id_persona: int
    id_audio: int
