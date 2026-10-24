from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.security import require_roles
from backend.database.connection import get_db
from backend.models.analisis import Analisis
from backend.models.persona import Persona
from backend.models.resultado_analisis import ResultadoAnalisis
from backend.models.usuario import Usuario
from backend.schemas.historial import (
    CandidatoHistorialResponse,
    HistorialDetalleResponse,
    HistorialItemResponse,
    HistorialPageResponse,
    UsuarioHistorialResponse,
)
from backend.services.audit_service import (
    HISTORY_ACCESS_DENIED,
    HISTORY_DETAIL_VIEWED,
    HISTORY_VIEWED,
    record_event,
)
from backend.services.threshold_service import threshold_state

router = APIRouter(prefix="/historial", tags=["historial"])
GLOBAL_HISTORY_ROLES = {"Administrador", "Investigador"}


def _can_view_all(current_user: Usuario) -> bool:
    return current_user.rol.nombre in GLOBAL_HISTORY_ROLES


@router.get("", response_model=HistorialPageResponse)
def list_history(
    request: Request,
    fecha_desde: datetime | None = None,
    fecha_hasta: datetime | None = None,
    estado: Literal["pendiente", "procesando", "completado", "error"] | None = None,
    id_usuario: int | None = Query(default=None, gt=0),
    busqueda: str | None = Query(default=None, min_length=1, max_length=100),
    pagina: int = Query(default=1, ge=1),
    tamano_pagina: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(
        require_roles("Administrador", "Investigador", "Analista")
    ),
) -> HistorialPageResponse:
    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="fecha_desde no puede ser posterior a fecha_hasta",
        )
    if busqueda is not None and not busqueda.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La búsqueda no puede estar vacía",
        )

    can_view_all = _can_view_all(current_user)
    if id_usuario is not None and not can_view_all:
        record_event(db, HISTORY_ACCESS_DENIED, current_user.id_usuario, request, "filtro_usuario_no_permitido")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para filtrar por usuario",
        )

    candidate_count = (
        select(func.count(ResultadoAnalisis.id_resultado))
        .where(ResultadoAnalisis.id_analisis == Analisis.id_analisis)
        .correlate(Analisis)
        .scalar_subquery()
    )
    filters = []
    if not can_view_all:
        filters.append(Analisis.id_usuario == current_user.id_usuario)
    elif id_usuario is not None:
        filters.append(Analisis.id_usuario == id_usuario)
    if fecha_desde is not None:
        filters.append(Analisis.fecha_analisis >= fecha_desde)
    if fecha_hasta is not None:
        filters.append(Analisis.fecha_analisis <= fecha_hasta)
    if estado is not None:
        filters.append(Analisis.estado == estado)
    if busqueda is not None:
        filters.append(Analisis.nombre_original.ilike(f"%{busqueda.strip()}%"))

    total = db.scalar(select(func.count()).select_from(Analisis).where(*filters)) or 0
    statement = (
        select(Analisis, Usuario, candidate_count.label("cantidad_candidatos"))
        .join(Usuario, Usuario.id_usuario == Analisis.id_usuario)
        .where(*filters)
        .order_by(Analisis.fecha_analisis.desc(), Analisis.id_analisis.desc())
        .offset((pagina - 1) * tamano_pagina)
        .limit(tamano_pagina)
    )
    rows = db.execute(statement).all()
    items = [
        HistorialItemResponse(
            id_analisis=analysis.id_analisis,
            fecha_analisis=analysis.fecha_analisis,
            nombre_original=analysis.nombre_original,
            formato_original=analysis.formato_original,
            estado=analysis.estado,
            usuario=UsuarioHistorialResponse(id_usuario=user.id_usuario, nombre=user.nombre),
            cantidad_candidatos=count,
        )
        for analysis, user, count in rows
    ]
    record_event(db, HISTORY_VIEWED, current_user.id_usuario, request, f"pagina={pagina}")
    return HistorialPageResponse(
        items=items,
        pagina=pagina,
        tamano_pagina=tamano_pagina,
        total=total,
    )


@router.get("/{analysis_id}", response_model=HistorialDetalleResponse)
def get_history_detail(
    analysis_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(
        require_roles("Administrador", "Investigador", "Analista")
    ),
) -> HistorialDetalleResponse:
    filters = [Analisis.id_analisis == analysis_id]
    if not _can_view_all(current_user):
        filters.append(Analisis.id_usuario == current_user.id_usuario)
    analysis = db.scalar(select(Analisis).where(*filters))
    if analysis is None:
        record_event(db, HISTORY_ACCESS_DENIED, current_user.id_usuario, request, "analisis_no_disponible")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Análisis no encontrado")

    rows = db.execute(
        select(ResultadoAnalisis, Persona)
        .join(Persona, Persona.id_persona == ResultadoAnalisis.id_persona)
        .where(ResultadoAnalisis.id_analisis == analysis_id)
        .order_by(ResultadoAnalisis.posicion)
    ).all()
    candidates = [
        CandidatoHistorialResponse(
            posicion=result.posicion,
            identificador=person.identificador,
            nombre=person.nombre,
            alias=person.alias,
            puntuacion_normalizada=result.similitud,
            supera_umbral=result.supera_umbral,
            estado_umbral=threshold_state(
                result.supera_umbral,
                analysis.fecha_analisis,
            ),
        )
        for result, person in rows
    ]
    record_event(db, HISTORY_DETAIL_VIEWED, current_user.id_usuario, request, f"id_analisis={analysis_id}")
    return HistorialDetalleResponse(
        id_analisis=analysis.id_analisis,
        fecha_analisis=analysis.fecha_analisis,
        nombre_original=analysis.nombre_original,
        formato_original=analysis.formato_original,
        estado=analysis.estado,
        usuario=UsuarioHistorialResponse(
            id_usuario=analysis.usuario.id_usuario,
            nombre=analysis.usuario.nombre,
        ),
        candidatos=candidates,
    )
