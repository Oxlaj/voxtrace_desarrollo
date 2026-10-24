from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class UsuarioHistorialResponse(BaseModel):
    id_usuario: int
    nombre: str


class HistorialItemResponse(BaseModel):
    id_analisis: int
    fecha_analisis: datetime
    nombre_original: str
    formato_original: str
    estado: str
    usuario: UsuarioHistorialResponse
    cantidad_candidatos: int


class HistorialPageResponse(BaseModel):
    items: list[HistorialItemResponse]
    pagina: int
    tamano_pagina: int
    total: int


class CandidatoHistorialResponse(BaseModel):
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


class HistorialDetalleResponse(BaseModel):
    id_analisis: int
    fecha_analisis: datetime
    nombre_original: str
    formato_original: str
    estado: str
    usuario: UsuarioHistorialResponse
    candidatos: list[CandidatoHistorialResponse]
