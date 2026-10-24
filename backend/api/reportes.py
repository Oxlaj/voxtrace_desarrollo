from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.core.security import require_roles
from backend.database.connection import get_db
from backend.models.usuario import Usuario
from backend.schemas.reportes import ReporteAnalisisResponse
from backend.services.audit_service import (
    REPORT_ACCESS_DENIED,
    REPORT_PDF_VIEWED,
    REPORT_VIEWED,
    record_event,
)
from backend.services.pdf_report_service import generate_analysis_pdf
from backend.services.report_service import METHODOLOGICAL_NOTE, build_analysis_report
from fastapi.responses import Response

router = APIRouter(prefix="/reportes", tags=["reportes"])


@router.get("/analisis/{analysis_id}", response_model=ReporteAnalisisResponse)
def get_analysis_report(
    analysis_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(
        require_roles("Administrador", "Investigador", "Analista")
    ),
) -> ReporteAnalisisResponse:
    report = build_analysis_report(db, analysis_id, current_user)
    if report is None:
        record_event(
            db,
            REPORT_ACCESS_DENIED,
            current_user.id_usuario,
            request,
            "analisis_no_disponible",
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Análisis no encontrado",
        )

    record_event(
        db,
        REPORT_VIEWED,
        current_user.id_usuario,
        request,
        f"id_analisis={analysis_id}",
    )
    return report


@router.get("/analisis/{analysis_id}/pdf", response_class=Response)
def download_analysis_pdf(
    analysis_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(
        require_roles("Administrador", "Investigador", "Analista")
    ),
) -> Response:
    report = build_analysis_report(db, analysis_id, current_user)
    if report is None:
        record_event(
            db,
            REPORT_ACCESS_DENIED,
            current_user.id_usuario,
            request,
            "analisis_no_disponible",
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Análisis no encontrado",
        )

    pdf = generate_analysis_pdf(report)
    record_event(
        db,
        REPORT_PDF_VIEWED,
        current_user.id_usuario,
        request,
        f"id_analisis={analysis_id}",
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="voxtrace_analisis_{analysis_id}.pdf"'
            )
        },
    )
