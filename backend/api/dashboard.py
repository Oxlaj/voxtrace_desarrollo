from datetime import datetime, time, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.security import require_roles
from backend.database.connection import get_db
from backend.models.analisis import Analisis
from backend.models.audio import Audio
from backend.models.persona import Persona
from backend.models.resultado_analisis import ResultadoAnalisis
from backend.models.usuario import Usuario
from backend.schemas.dashboard import (
    AnalisisDiaResponse,
    DashboardStatsResponse,
    InventarioDashboardResponse,
    ResultadosDashboardResponse,
)
from backend.services.threshold_service import threshold_state

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
GLOBAL_STATS_ROLES = {"Administrador", "Investigador"}
DASHBOARD_DAYS = 7


@router.get("/estadisticas", response_model=DashboardStatsResponse)
def dashboard_stats(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(
        require_roles("Administrador", "Investigador", "Analista")
    ),
) -> DashboardStatsResponse:
    now = datetime.now()
    first_day = now.date() - timedelta(days=DASHBOARD_DAYS - 1)
    analysis_filters = []
    global_scope = current_user.rol.nombre in GLOBAL_STATS_ROLES
    if not global_scope:
        analysis_filters.append(Analisis.id_usuario == current_user.id_usuario)

    people_count = db.scalar(select(func.count()).select_from(Persona)) or 0
    samples_count = db.scalar(select(func.count()).select_from(Audio)) or 0
    analyses_count = (
        db.scalar(select(func.count()).select_from(Analisis).where(*analysis_filters))
        or 0
    )
    recent_dates = db.scalars(
        select(Analisis.fecha_analisis).where(
            *analysis_filters,
            Analisis.fecha_analisis >= datetime.combine(first_day, time.min),
        )
    ).all()
    daily_counts = {
        first_day + timedelta(days=offset): 0 for offset in range(DASHBOARD_DAYS)
    }
    for value in recent_dates:
        day = value.date()
        if day in daily_counts:
            daily_counts[day] += 1

    outcome_rows = db.execute(
        select(Analisis.fecha_analisis, ResultadoAnalisis.supera_umbral)
        .join(
            ResultadoAnalisis,
            ResultadoAnalisis.id_analisis == Analisis.id_analisis,
        )
        .where(*analysis_filters, ResultadoAnalisis.posicion == 1)
    ).all()
    outcomes = {
        "posible_coincidencia": 0,
        "coincidencia_insuficiente": 0,
        "umbral_no_evaluado": 0,
    }
    for analysis_date, exceeds_threshold in outcome_rows:
        outcomes[threshold_state(exceeds_threshold, analysis_date)] += 1

    return DashboardStatsResponse(
        alcance_analisis="global" if global_scope else "propio",
        total_analisis=analyses_count,
        analisis_ultimos_dias=[
            AnalisisDiaResponse(fecha=day.isoformat(), cantidad=count)
            for day, count in daily_counts.items()
        ],
        resultados=ResultadosDashboardResponse(**outcomes),
        inventario=InventarioDashboardResponse(
            personas=people_count,
            muestras=samples_count,
        ),
        actualizado_en=now,
    )
