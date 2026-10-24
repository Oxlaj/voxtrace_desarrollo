from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from backend.schemas.reportes import ReporteAnalisisResponse

NAVY = colors.HexColor("#0F2747")
BLUE = colors.HexColor("#2563A6")
LIGHT_GRAY = colors.HexColor("#F3F4F6")
DARK_GRAY = colors.HexColor("#1E293B")


def _safe(value: object) -> str:
    return escape(str(value))


def _uncompressed_canvas(*args, **kwargs) -> Canvas:
    kwargs["pageCompression"] = 0
    return Canvas(*args, **kwargs)


def generate_analysis_pdf(report: ReporteAnalisisResponse) -> bytes:
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"VoxTrace - Análisis {report.id_analisis}",
        author="VoxTrace",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("VoxTraceTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=NAVY, alignment=TA_CENTER, spaceAfter=12)
    heading = ParagraphStyle("VoxTraceHeading", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=BLUE, spaceBefore=10, spaceAfter=7)
    body = ParagraphStyle("VoxTraceBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.5, leading=13, textColor=DARK_GRAY)
    label = ParagraphStyle("VoxTraceLabel", parent=body, fontName="Helvetica-Bold")

    story = [
        Paragraph("VoxTrace", title),
        Paragraph("Reporte de análisis biométrico de voz", title),
    ]
    general_data = [
        [Paragraph("Identificador del análisis", label), Paragraph(_safe(report.id_analisis), body)],
        [Paragraph("Fecha y hora", label), Paragraph(_safe(report.fecha_analisis.strftime("%Y-%m-%d %H:%M:%S")), body)],
        [Paragraph("Usuario responsable", label), Paragraph(_safe(report.usuario.nombre), body)],
        [Paragraph("Archivo original", label), Paragraph(_safe(report.nombre_original), body)],
        [Paragraph("Formato original", label), Paragraph(_safe(report.formato_original.upper()), body)],
        [Paragraph("Estado", label), Paragraph(_safe(report.estado), body)],
        [Paragraph("Modelo biométrico", label), Paragraph(_safe(report.modelo_biometrico or "No registrado"), body)],
    ]
    general = Table(general_data, colWidths=[55 * mm, 95 * mm], hAlign="LEFT")
    general.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, -1), LIGHT_GRAY), ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")), ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story.extend([general, Paragraph("Resultados del análisis", heading)])

    if report.candidatos:
        rows = [["Posición", "Identificador", "Nombre / alias", "Puntuación", "Estado del umbral"]]
        for candidate in report.candidatos[:3]:
            person_text = candidate.nombre
            if candidate.alias:
                person_text += f" / {candidate.alias}"
            rows.append([
                _safe(candidate.posicion),
                _safe(candidate.identificador),
                Paragraph(_safe(person_text), body),
                Paragraph(f"Puntuación normalizada: {_safe(candidate.puntuacion_normalizada)} / 100", body),
                Paragraph(
                    {
                        "umbral_no_evaluado": "Umbral no evaluado",
                        "posible_coincidencia": "Posible coincidencia",
                        "coincidencia_insuficiente": "Coincidencia insuficiente",
                    }[candidate.estado_umbral],
                    body,
                ),
            ])
        candidates = Table(rows, colWidths=[14 * mm, 27 * mm, 38 * mm, 37 * mm, 42 * mm], repeatRows=1)
        candidates.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, 0), 8), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("FONTSIZE", (0, 1), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        story.append(candidates)
    else:
        story.append(Paragraph("No existen resultados almacenados para este análisis.", body))

    story.extend([
        Spacer(1, 7 * mm),
        Paragraph("Nota metodológica", heading),
        Paragraph(_safe(report.nota_metodologica), body),
    ])
    document.build(story, canvasmaker=_uncompressed_canvas)
    return buffer.getvalue()
