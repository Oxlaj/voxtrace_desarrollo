from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.api import analisis
from backend.core.security import get_current_user
from backend.database.connection import get_db
from backend.main import app
from backend.models.persona import Persona
from backend.models.rol import Rol
from backend.models.usuario import Usuario
from backend.services.audio_processing_service import AudioProcessingResult
from backend.services.audio_service import StoredAudio
from backend.services.identification_service import IdentificationCandidate


def user(role: str) -> Usuario:
    return Usuario(id_usuario=7, id_rol=1, nombre="Usuario", correo="user@example.com", password_hash="hidden", estado=True, rol=Rol(id_rol=1, nombre=role))


@pytest.mark.parametrize("role", ["Administrador", "Investigador", "Analista"])
def test_analyze_page_is_available_to_all_analysis_roles(role: str) -> None:
    app.dependency_overrides[get_current_user] = lambda: user(role)
    try:
        response = TestClient(app).get("/app/analizar")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert 'id="analysis-form"' in response.text
    assert "Formatos admitidos: MP3, OGG, MP4 y WAV." in response.text
    assert "duración se registrará" not in response.text
    assert "Identificación 1:N" not in response.text
    assert "Duración mínima" not in response.text
    assert "apoyo analítico" in response.text


def test_analyze_page_rejects_unauthenticated_access() -> None:
    assert TestClient(app).get("/app/analizar").status_code == 401


def test_analysis_frontend_contract_is_safe_and_non_definitive() -> None:
    client = TestClient(app)
    script = client.get("/static/js/analizar.js").text
    app.dependency_overrides[get_current_user] = lambda: user("Analista")
    try:
        page = client.get("/app/analizar").text
    finally:
        app.dependency_overrides.clear()
    combined = page + script
    assert "/analisis/identificacion" in script and "new FormData()" in script
    assert "Puntuación normalizada" in combined and "/ 100" in script
    assert "Posible coincidencia" in combined
    assert "Coincidencia insuficiente" in combined
    assert "experimento-01" in combined
    assert "No se encontraron candidatos disponibles" in combined
    assert "data-analysis-id" in page and "dataset.analysisId" in script
    assert "error.status === 400 || error.status === 409" in script
    for sensitive in ("ruta_audio_consulta", "hash_audio_consulta", "hash_archivo", "resultados_individuales", '"vector"', "localStorage", "sessionStorage"):
        assert sensitive not in combined
    for forbidden in ("Identidad confirmada", "Persona identificada", "Coincidencia definitiva", "% de identidad", "Porcentaje de certeza"):
        assert forbidden not in combined


def test_analysis_multipart_requires_csrf_and_returns_ordered_top_three(monkeypatch, tmp_path) -> None:
    db = MagicMock()
    db.scalar.return_value = None
    current_user = user("Analista")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: current_user
    original = tmp_path / "original.wav"; original.write_bytes(b"original")
    processed = tmp_path / "processed.wav"; processed.write_bytes(b"processed")

    async def store(file, category): return StoredAudio(original, "consulta.wav", "wav", "a" * 64, 8)
    candidates = [IdentificationCandidate(posicion=i, id_persona=i, identificador=f"P-{i}", nombre=f"Persona {i}", alias=None, similitud_mejor=0.9 - i / 10, similitud_promedio=0.8 - i / 10, muestras_comparadas=2, muestras_sin_embedding=0, resultados_individuales=[]) for i in (1, 2, 3)]
    monkeypatch.setattr(analisis, "store_original_audio", store)
    monkeypatch.setattr(analisis, "process_audio_copy", lambda *args, **kwargs: AudioProcessingResult(60, processed))
    monkeypatch.setattr(analisis, "identify_top_candidates", lambda *args, **kwargs: candidates)
    monkeypatch.setattr(analisis, "record_event", lambda *args, **kwargs: True)
    def refresh(entity):
        if entity.__class__.__name__ == "Analisis": entity.id_analisis = 91; entity.fecha_analisis = datetime(2026, 9, 8)
    db.refresh.side_effect = refresh
    client = TestClient(app)
    try:
        token = client.get("/auth/csrf").json()["csrf_token"]
        missing = client.post("/analisis/identificacion", files={"file": ("consulta.wav", b"audio", "audio/wav")})
        valid = client.post("/analisis/identificacion", headers={"X-CSRF-Token": token}, files={"file": ("consulta.wav", b"audio", "audio/wav")})
    finally:
        app.dependency_overrides.clear()
    assert missing.status_code == 403
    assert valid.status_code == 201
    body = valid.json()
    assert body["id_analisis"] == 91
    assert [item["posicion"] for item in body["candidatos"]] == [1, 2, 3]
    assert body["estado_coincidencia"] == "posible_coincidencia"
    assert [item["supera_umbral"] for item in body["candidatos"]] == [True, True, False]
    assert all(0 <= float(item["puntuacion_normalizada"]) <= 100 for item in body["candidatos"])
    assert len([call for call in db.add.call_args_list if call.args[0].__class__.__name__ == "ResultadoAnalisis"]) == 3
    assert db.commit.called
