from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.analisis import Analisis
from backend.models.persona import Persona
from backend.models.resultado_analisis import ResultadoAnalisis
from backend.models.usuario import Usuario
from backend.schemas.reportes import (
    CandidatoReporteResponse,
    ReporteAnalisisResponse,
    UsuarioReporteResponse,
)
from backend.services.threshold_service import threshold_state

GLOBAL_REPORT_ROLES = {"Administrador", "Investigador"}
METHODOLOGICAL_NOTE = (
    "La puntuación normalizada no representa una probabilidad ni certeza de identidad. "
    "VoxTrace utiliza un umbral experimental provisional obtenido de experimento-01, "
    "con 5 consultas KNOWN y 17 UNKNOWN; todavía no constituye una validación biométrica "
    "definitiva. Los resultados constituyen apoyo analítico: representan candidatos o "
    "posibles coincidencias. Los análisis anteriores a la fecha de integración del "
    "umbral se muestran como umbral no evaluado y no se recalculan."
)


def build_analysis_report(
    db: Session,
    analysis_id: int,
    current_user: Usuario,
) -> ReporteAnalisisResponse | None:
    filters = [Analisis.id_analisis == analysis_id]
    if current_user.rol.nombre not in GLOBAL_REPORT_ROLES:
        filters.append(Analisis.id_usuario == current_user.id_usuario)

    analysis = db.scalar(select(Analisis).where(*filters))
    if analysis is None:
        return None

    rows = db.execute(
        select(ResultadoAnalisis, Persona)
        .join(Persona, Persona.id_persona == ResultadoAnalisis.id_persona)
        .where(ResultadoAnalisis.id_analisis == analysis_id)
        .order_by(ResultadoAnalisis.posicion)
        .limit(3)
    ).all()
    return ReporteAnalisisResponse(
        id_analisis=analysis.id_analisis,
        fecha_analisis=analysis.fecha_analisis,
        usuario=UsuarioReporteResponse(
            id_usuario=analysis.usuario.id_usuario,
            nombre=analysis.usuario.nombre,
        ),
        nombre_original=analysis.nombre_original,
        formato_original=analysis.formato_original,
        estado=analysis.estado,
        modelo_biometrico=None,
        candidatos=[
            CandidatoReporteResponse(
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
        ],
        nota_metodologica=METHODOLOGICAL_NOTE,
    )
