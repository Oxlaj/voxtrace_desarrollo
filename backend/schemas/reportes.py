from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class UsuarioReporteResponse(BaseModel):
    id_usuario: int
    nombre: str


class CandidatoReporteResponse(BaseModel):
    posicion: int
    identificador: str
    nombre: str
    alias: str | None
    puntuacion_normalizada: Decimal
    supera_umbral: bool
    estado_umbral: Literal[
        "umbral_no_evaluado",
        "posible_coincidencia",
        "coincidencia_insuficiente",
    ]


class ReporteAnalisisResponse(BaseModel):
    id_analisis: int
    fecha_analisis: datetime
    usuario: UsuarioReporteResponse
    nombre_original: str
    formato_original: str
    estado: str
    modelo_biometrico: str | None
    candidatos: list[CandidatoReporteResponse]
    nota_metodologica: str
