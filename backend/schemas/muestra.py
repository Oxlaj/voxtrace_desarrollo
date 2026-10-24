from datetime import datetime
from decimal import Decimal

from typing import Literal

from pydantic import BaseModel, ConfigDict


class MuestraRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_audio: int
    id_persona: int
    nombre_original: str
    formato_original: str
    duracion_segundos: Decimal | None
    fecha_subida: datetime
    estado_procesamiento: Literal["embedding_disponible", "embedding_no_disponible"]
