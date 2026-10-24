from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.api.reportes import METHODOLOGICAL_NOTE, get_analysis_report, router
from backend.models.analisis import Analisis
from backend.models.persona import Persona
from backend.models.resultado_analisis import ResultadoAnalisis
from backend.models.rol import Rol
from backend.models.usuario import Usuario


def make_request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/reportes/analisis/10", "headers": [], "query_string": b"", "client": ("192.0.2.70", 50000)})


def make_user(user_id: int, role: str) -> Usuario:
    return Usuario(id_usuario=user_id, id_rol=1, nombre=f"Usuario {user_id}", correo=f"u{user_id}@example.com", password_hash="hidden", estado=True, rol=Rol(id_rol=1, nombre=role))


def make_analysis(owner: Usuario) -> Analisis:
    return Analisis(id_analisis=10, id_usuario=owner.id_usuario, ruta_audio_consulta="storage/private.wav", nombre_original="consulta.wav", formato_original="wav", hash_audio_consulta="secret-hash", fecha_analisis=datetime(2026, 9, 10, 12, 0), estado="completado", usuario=owner)


def make_rows() -> list[tuple[ResultadoAnalisis, Persona]]:
    return [
        (
            ResultadoAnalisis(id_resultado=position, id_analisis=10, id_persona=position, similitud=Decimal(str(score)), posicion=position, supera_umbral=False),
            Persona(id_persona=position, identificador=f"P-{position}", nombre=f"Persona {position}", alias=f"A-{position}"),
        )
        for position, score in ((1, 91.2), (2, 82.1), (3, 73.0))
    ]


def report_for(role: str, user_id: int = 1):
    user = make_user(user_id, role)
    db = MagicMock()
    db.scalar.return_value = make_analysis(user)
    db.execute.return_value.all.return_value = make_rows()
    return get_analysis_report(10, make_request(), db, user), db


def test_valid_report_contains_safe_general_data() -> None:
    report, _ = report_for("Administrador")

    assert report.id_analisis == 10
    assert report.usuario.nombre == "Usuario 1"
    assert report.nombre_original == "consulta.wav"
    assert report.modelo_biometrico is None


def test_report_candidates_are_top_three_in_position_order() -> None:
    report, db = report_for("Investigador")

    assert [candidate.posicion for candidate in report.candidatos] == [1, 2, 3]
    assert all(candidate.estado_umbral == "umbral_no_evaluado" for candidate in report.candidatos)
    statement = str(db.execute.call_args.args[0])
    assert "ORDER BY" in statement
    assert "LIMIT" in statement


def test_report_after_cutoff_uses_persisted_threshold_decisions() -> None:
    user = make_user(1, "Administrador")
    analysis = make_analysis(user)
    analysis.fecha_analisis = datetime(2026, 10, 5, 0, 0)
    rows = make_rows()
    rows[0][0].supera_umbral = True
    db = MagicMock()
    db.scalar.return_value = analysis
    db.execute.return_value.all.return_value = rows

    report = get_analysis_report(10, make_request(), db, user)

    assert [candidate.estado_umbral for candidate in report.candidatos] == [
        "posible_coincidencia",
        "coincidencia_insuficiente",
        "coincidencia_insuficiente",
    ]


@pytest.mark.parametrize("role", ["Administrador", "Investigador"])
def test_global_roles_can_access_any_report(role: str) -> None:
    requester = make_user(1, role)
    owner = make_user(9, "Analista")
    db = MagicMock()
    db.scalar.return_value = make_analysis(owner)
    db.execute.return_value.all.return_value = []

    response = get_analysis_report(10, make_request(), db, requester)

    assert response.id_analisis == 10
    assert "analisis.id_usuario" not in str(db.scalar.call_args.args[0]).split("WHERE", 1)[-1]


def test_analyst_can_access_own_report() -> None:
    report, db = report_for("Analista", user_id=8)

    assert report.id_analisis == 10
    assert "analisis.id_usuario" in str(db.scalar.call_args.args[0])


def test_cross_analyst_and_missing_report_are_same_404() -> None:
    analyst = make_user(8, "Analista")
    for analysis_id in (10, 999):
        db = MagicMock()
        db.scalar.return_value = None

        with pytest.raises(HTTPException) as denied:
            get_analysis_report(analysis_id, make_request(), db, analyst)

        assert denied.value.status_code == 404
        assert denied.value.detail == "Análisis no encontrado"
        assert "analisis.id_usuario" in str(db.scalar.call_args.args[0])
        event = db.add.call_args.args[0]
        assert event.accion == "acceso_reporte_denegado"
        assert event.detalles == "analisis_no_disponible"


def test_report_without_results_is_valid() -> None:
    user = make_user(1, "Administrador")
    db = MagicMock()
    db.scalar.return_value = make_analysis(user)
    db.execute.return_value.all.return_value = []

    assert get_analysis_report(10, make_request(), db, user).candidatos == []


def test_report_does_not_expose_private_fields() -> None:
    report, _ = report_for("Administrador")
    serialized = str(report.model_dump()).lower()

    for forbidden in ("ruta_audio_consulta", "secret-hash", "embedding", "cookie", "storage/private"):
        assert forbidden not in serialized


def test_methodological_note_is_explicit() -> None:
    report, _ = report_for("Administrador")
    note = report.nota_metodologica.lower()

    assert report.nota_metodologica == METHODOLOGICAL_NOTE
    assert "no representa una probabilidad" in note
    assert "umbral experimental provisional" in note
    assert "experimento-01" in note
    assert "5 consultas known y 17 unknown" in note
    assert "anteriores a la fecha de integración" in note
    assert "candidatos o posibles coincidencias" in note
    assert "apoyo analítico" in note


def test_report_access_is_audited_without_sensitive_details() -> None:
    _, db = report_for("Administrador")
    event = db.add.call_args.args[0]

    assert event.accion == "reporte_analisis_consultado"
    assert event.detalles == "id_analisis=10"
    assert all(word not in event.detalles for word in ("hash", "ruta", "cookie"))


def test_report_route_requires_supported_roles() -> None:
    route = next(route for route in router.routes if route.path == "/reportes/analisis/{analysis_id}")
    dependency = route.dependant.dependencies[-1].call

    assert dependency.__closure__[0].cell_contents == ("Administrador", "Investigador", "Analista")
    with pytest.raises(HTTPException) as denied:
        dependency(make_user(4, "Invitado"))
    assert denied.value.status_code == 403
