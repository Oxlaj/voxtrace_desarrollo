from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class ResultadoIndividualResponse(BaseModel):
    id_audio: int
    similitud: float


class CandidatoResponse(BaseModel):
    posicion: int
    id_persona: int
    identificador: str
    nombre: str
    alias: str | None
    similitud_mejor: float
    similitud_promedio: float
    puntuacion_normalizada: Decimal
    supera_umbral: bool
    estado_umbral: Literal["posible_coincidencia", "coincidencia_insuficiente"]
    muestras_comparadas: int
    muestras_sin_embedding: int
    resultados_individuales: list[ResultadoIndividualResponse]


class AnalisisResponse(BaseModel):
    id_analisis: int
    estado: str
    nombre_original: str
    tipo_analisis: str
    estado_coincidencia: Literal["posible_coincidencia", "coincidencia_insuficiente"]
    candidatos: list[CandidatoResponse]
