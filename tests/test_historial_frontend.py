import pytest
from fastapi.testclient import TestClient

from backend.core.security import get_current_user
from backend.main import app
from backend.models.rol import Rol
from backend.models.usuario import Usuario


def make_user(role: str) -> Usuario:
    return Usuario(id_usuario=7, id_rol=1, nombre="Usuario", correo="user@example.com", password_hash="hidden", estado=True, rol=Rol(id_rol=1, nombre=role))


@pytest.mark.parametrize(("role", "has_user_filter"), [("Administrador", True), ("Investigador", True), ("Analista", False)])
def test_history_page_respects_role_specific_user_filter(role: str, has_user_filter: bool) -> None:
    app.dependency_overrides[get_current_user] = lambda: make_user(role)
    try:
        response = TestClient(app).get("/app/historial")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert "Historial de análisis" in response.text
    assert ('id="history-user"' in response.text) is has_user_filter
    assert "pagina" in TestClient(app).get("/static/js/historial.js").text


@pytest.mark.parametrize("path", ["/app/historial", "/app/historial/17"])
def test_history_pages_reject_unauthenticated_access(path: str) -> None:
    assert TestClient(app).get(path).status_code == 401


def test_history_frontend_connects_filters_and_pagination_without_sensitive_data() -> None:
    script = TestClient(app).get("/static/js/historial.js").text
    for parameter in ("fecha_desde", "fecha_hasta", "estado", "id_usuario", "busqueda", "pagina", "tamano_pagina"):
        assert parameter in script
    assert "No hay análisis" in script
    assert "previous-page" in script and "next-page" in script
    for forbidden in ("ruta_audio_consulta", "hash_audio_consulta", "embedding", "localStorage", "sessionStorage"):
        assert forbidden not in script


def test_history_pages_omit_removed_decorative_copy() -> None:
    app.dependency_overrides[get_current_user] = lambda: make_user("Administrador")
    try:
        client = TestClient(app)
        pages = client.get("/app/historial").text + client.get("/app/historial/17").text
    finally:
        app.dependency_overrides.clear()

    assert "Trazabilidad" not in pages
    assert "Consulta paginada de análisis disponibles" not in pages


def test_detail_page_has_report_pdf_and_methodological_contract() -> None:
    app.dependency_overrides[get_current_user] = lambda: make_user("Analista")
    try:
        client = TestClient(app)
        page = client.get("/app/historial/17")
        script = client.get("/static/js/historial-detalle.js").text
    finally:
        app.dependency_overrides.clear()
    assert page.status_code == 200
    assert 'data-analysis-id="17"' in page.text
    assert "Ver reporte" in page.text and "Descargar PDF" in page.text
    assert "/historial/${analysisId}" in script
    assert "/reportes/analisis/${analysisId}" in script
    assert "/reportes/analisis/${payload.id_analisis}/pdf" in script
    assert "Puntuación normalizada" in script
    assert "Umbral no evaluado" in script
    assert "Posible coincidencia" in script and "Coincidencia insuficiente" in script
    assert "experimento-01" in page.text
    assert "apoyo analítico" in page.text and "probabilidad estadística" in page.text
    for forbidden in ("ruta_audio_consulta", "hash_audio_consulta", "embedding", "cookie", "localStorage", "sessionStorage"):
        assert forbidden not in page.text + script


def test_analysis_success_builds_normal_navigation_to_detail() -> None:
    script = TestClient(app).get("/static/js/analizar.js").text
    page = open("frontend/templates/analizar.html", encoding="utf-8").read()
    assert 'id="analysis-detail-link"' in page
    assert "resultsPanel.dataset.analysisId" in script
    assert "`/app/historial/${id}`" in script
    assert "localStorage" not in script and "sessionStorage" not in script
