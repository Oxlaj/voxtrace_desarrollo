from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.api.reportes import download_analysis_pdf, router
from backend.models.analisis import Analisis
from backend.models.persona import Persona
from backend.models.resultado_analisis import ResultadoAnalisis
from backend.models.rol import Rol
from backend.models.usuario import Usuario


def make_request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/reportes/analisis/10/pdf", "headers": [], "query_string": b"", "client": ("192.0.2.80", 50000)})


def make_user(user_id: int, role: str) -> Usuario:
    return Usuario(id_usuario=user_id, id_rol=1, nombre=f"Usuario {user_id}", correo=f"u{user_id}@example.com", password_hash="hidden", estado=True, rol=Rol(id_rol=1, nombre=role))


def make_analysis(owner: Usuario) -> Analisis:
    return Analisis(id_analisis=10, id_usuario=owner.id_usuario, ruta_audio_consulta="storage/private.wav", nombre_original="consulta_controlada.wav", formato_original="wav", hash_audio_consulta="sensitive-sha256", fecha_analisis=datetime(2026, 9, 10, 12, 0), estado="completado", usuario=owner)


def make_rows() -> list[tuple[ResultadoAnalisis, Persona]]:
    return [
        (
            ResultadoAnalisis(id_resultado=position, id_analisis=10, id_persona=position, similitud=Decimal(score), posicion=position, supera_umbral=False),
            Persona(id_persona=position, identificador=f"P-{position}", nombre=f"Persona {position}", alias=f"Alias {position}"),
        )
        for position, score in ((1, "79.207"), (2, "76.157"), (3, "68.864"))
    ]


def pdf_response(
    requester: Usuario,
    owner: Usuario | None = None,
    rows=None,
    analysis_date: datetime | None = None,
):
    db = MagicMock()
    analysis = make_analysis(owner or requester)
    if analysis_date is not None:
        analysis.fecha_analisis = analysis_date
    db.scalar.return_value = analysis
    db.execute.return_value.all.return_value = make_rows() if rows is None else rows
    return download_analysis_pdf(10, make_request(), db, requester), db


def pdf_text(response) -> str:
    return response.body.decode("latin-1")


def test_pdf_generation_content_type_and_filename() -> None:
    response, _ = pdf_response(make_user(1, "Administrador"))

    assert response.status_code == 200
    assert response.media_type == "application/pdf"
    assert response.body.startswith(b"%PDF-")
    assert response.headers["content-disposition"] == 'attachment; filename="voxtrace_analisis_10.pdf"'


@pytest.mark.parametrize("role", ["Administrador", "Investigador"])
def test_global_roles_can_download_any_analysis(role: str) -> None:
    response, db = pdf_response(make_user(1, role), owner=make_user(9, "Analista"))

    assert response.status_code == 200
    assert "analisis.id_usuario" not in str(db.scalar.call_args.args[0]).split("WHERE", 1)[-1]


def test_analyst_can_download_own_analysis() -> None:
    response, db = pdf_response(make_user(8, "Analista"))

    assert response.status_code == 200
    assert "analisis.id_usuario" in str(db.scalar.call_args.args[0])


def test_cross_analyst_and_missing_analysis_return_same_404() -> None:
    analyst = make_user(8, "Analista")
    for analysis_id in (10, 999):
        db = MagicMock()
        db.scalar.return_value = None
        with pytest.raises(HTTPException) as denied:
            download_analysis_pdf(analysis_id, make_request(), db, analyst)

        assert denied.value.status_code == 404
        assert denied.value.detail == "Análisis no encontrado"
        assert "analisis.id_usuario" in str(db.scalar.call_args.args[0])


def test_pdf_without_candidates_is_generated() -> None:
    response, _ = pdf_response(make_user(1, "Administrador"), rows=[])

    assert response.body.startswith(b"%PDF-")
    assert "No existen resultados almacenados" in pdf_text(response)


def test_pdf_contains_top_three_and_methodological_note() -> None:
    response, _ = pdf_response(make_user(1, "Administrador"))
    content = pdf_text(response)

    assert content.index("P-1") < content.index("P-2") < content.index("P-3")
    assert "79.207" in content
    assert "Nota metodol" in content
    assert "no representa una probabilidad" in content
    assert "posibles coincidencias" in content
    assert "Umbral no evaluado" in content
    assert "experimento-01" in content


def test_pdf_after_cutoff_displays_evaluated_threshold_states() -> None:
    rows = make_rows()
    rows[0][0].supera_umbral = True
    response, _ = pdf_response(
        make_user(1, "Administrador"),
        rows=rows,
        analysis_date=datetime(2026, 10, 5, 0, 0),
    )
    content = pdf_text(response)

    assert "Posible coincidencia" in content
    assert "Coincidencia insuficiente" in content
    assert "Umbral no evaluado" not in content


def test_pdf_does_not_contain_sensitive_values_or_forbidden_claims() -> None:
    response, _ = pdf_response(make_user(1, "Administrador"))
    content = pdf_text(response).lower()

    for forbidden in ("storage/private.wav", "sensitive-sha256", "embedding", "cookie", "password", "identificación confirmada", "% de identidad", "probabilidad de identidad"):
        assert forbidden not in content


def test_pdf_generation_is_audited_safely() -> None:
    _, db = pdf_response(make_user(1, "Administrador"))
    event = db.add.call_args.args[0]

    assert event.accion == "reporte_pdf_generado"
    assert event.detalles == "id_analisis=10"
    assert all(word not in event.detalles for word in ("hash", "ruta", "cookie"))


def test_pdf_route_uses_supported_roles() -> None:
    route = next(route for route in router.routes if route.path == "/reportes/analisis/{analysis_id}/pdf")
    dependency = route.dependant.dependencies[-1].call

    assert dependency.__closure__[0].cell_contents == ("Administrador", "Investigador", "Analista")
    with pytest.raises(HTTPException) as denied:
        dependency(make_user(4, "Invitado"))
    assert denied.value.status_code == 403
