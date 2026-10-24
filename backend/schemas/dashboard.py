from datetime import datetime

from pydantic import BaseModel


class AnalisisDiaResponse(BaseModel):
    fecha: str
    cantidad: int


class ResultadosDashboardResponse(BaseModel):
    posible_coincidencia: int
    coincidencia_insuficiente: int
    umbral_no_evaluado: int


class InventarioDashboardResponse(BaseModel):
    personas: int
    muestras: int


class DashboardStatsResponse(BaseModel):
    alcance_analisis: str
    total_analisis: int
    analisis_ultimos_dias: list[AnalisisDiaResponse]
    resultados: ResultadosDashboardResponse
    inventario: InventarioDashboardResponse
    actualizado_en: datetime
