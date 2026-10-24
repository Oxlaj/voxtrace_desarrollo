from fastapi import Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.models.log import Log

LOGIN_SUCCESS = "login_exitoso"
LOGIN_FAILURE = "login_fallido"
LOGOUT = "logout"
PERSON_CREATED = "persona_creada"
PERSON_UPDATED = "persona_editada"
PERSON_DELETED = "persona_eliminada"
SAMPLE_UPLOADED = "muestra_cargada"
AUTH_ERROR = "error_autenticacion"
PERSON_ERROR = "error_persona"
SAMPLE_ERROR = "error_muestra"
HISTORY_VIEWED = "historial_consultado"
HISTORY_DETAIL_VIEWED = "detalle_historial_consultado"
HISTORY_ACCESS_DENIED = "acceso_historial_denegado"
REPORT_VIEWED = "reporte_analisis_consultado"
REPORT_ACCESS_DENIED = "acceso_reporte_denegado"
REPORT_PDF_VIEWED = "reporte_pdf_generado"


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def add_event(
    db: Session,
    action: str,
    user_id: int | None,
    request: Request,
    details: str,
) -> None:
    db.add(
        Log(
            id_usuario=user_id,
            accion=action,
            direccion_ip=client_ip(request),
            detalles=details,
        )
    )


def record_event(
    db: Session,
    action: str,
    user_id: int | None,
    request: Request,
    details: str,
) -> bool:
    try:
        add_event(db, action, user_id, request, details)
        db.commit()
        return True
    except SQLAlchemyError:
        db.rollback()
        return False
