from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from backend.api.historial import get_history_detail, list_history, router
from backend.core.security import get_current_user
from backend.database.connection import get_db
from backend.main import app
from backend.models.analisis import Analisis
from backend.models.persona import Persona
from backend.models.resultado_analisis import ResultadoAnalisis
from backend.models.rol import Rol
from backend.models.usuario import Usuario


def make_request(path: str = "/historial") -> Request:
    return Request({"type": "http", "method": "GET", "path": path, "headers": [], "query_string": b"", "client": ("192.0.2.60", 50000)})


def make_user(user_id: int, role: str) -> Usuario:
    return Usuario(id_usuario=user_id, id_rol=1, nombre=f"Usuario {user_id}", correo=f"u{user_id}@example.com", password_hash="hidden", estado=True, rol=Rol(id_rol=1, nombre=role))


def make_analysis(owner: Usuario, analysis_id: int = 10) -> Analisis:
    return Analisis(
        id_analisis=analysis_id,
        id_usuario=owner.id_usuario,
        ruta_audio_consulta="storage/private.wav",
        nombre_original="consulta.wav",
        formato_original="wav",
        hash_audio_consulta="secret-hash",
        fecha_analisis=datetime(2026, 9, 10, 12, 0),
        estado="completado",
        usuario=owner,
    )


def list_call(db: MagicMock, user: Usuario, **overrides):
    arguments = {
        "request": make_request(), "fecha_desde": None, "fecha_hasta": None,
        "estado": None, "id_usuario": None, "busqueda": None,
        "pagina": 1, "tamano_pagina": 20, "db": db, "current_user": user,
    }
    arguments.update(overrides)
    return list_history(**arguments)


def test_empty_history_is_paginated_and_audited() -> None:
    db = MagicMock()
    db.scalar.return_value = 0
    db.execute.return_value.all.return_value = []

    response = list_call(db, make_user(1, "Administrador"), pagina=2, tamano_pagina=10)

    assert response.items == []
    assert (response.pagina, response.tamano_pagina, response.total) == (2, 10, 0)
    assert db.add.call_args.args[0].accion == "historial_consultado"


def test_list_exposes_only_public_fields() -> None:
    owner = make_user(2, "Investigador")
    analysis = make_analysis(owner)
    db = MagicMock()
    db.scalar.return_value = 1
    db.execute.return_value.all.return_value = [(analysis, owner, 3)]

    payload = list_call(db, owner).model_dump()
    serialized = str(payload).lower()

    assert payload["items"][0]["cantidad_candidatos"] == 3
    assert "ruta_audio_consulta" not in serialized
    assert "hash_audio_consulta" not in serialized
    assert "embedding" not in serialized


def test_date_state_and_name_filters_are_applied() -> None:
    db = MagicMock()
    db.scalar.return_value = 0
    db.execute.return_value.all.return_value = []

    list_call(
        db,
        make_user(1, "Administrador"),
        fecha_desde=datetime(2026, 9, 1),
        fecha_hasta=datetime(2026, 9, 30),
        estado="completado",
        busqueda="consulta",
    )

    statement = str(db.execute.call_args.args[0])
    assert "fecha_analisis >=" in statement
    assert "fecha_analisis <=" in statement
    assert "analisis.estado =" in statement
    assert "nombre_original" in statement
    assert " LIKE " in statement


def test_invalid_date_range_and_blank_search_return_422() -> None:
    db = MagicMock()
    user = make_user(1, "Administrador")
    now = datetime.now()

    with pytest.raises(HTTPException) as dates:
        list_call(db, user, fecha_desde=now, fecha_hasta=now - timedelta(days=1))
    with pytest.raises(HTTPException) as search:
        list_call(db, user, busqueda="   ")

    assert dates.value.status_code == 422
    assert search.value.status_code == 422


def test_analyst_is_scoped_to_own_history_and_cannot_filter_users() -> None:
    analyst = make_user(8, "Analista")
    db = MagicMock()
    db.scalar.return_value = 0
    db.execute.return_value.all.return_value = []

    list_call(db, analyst)
    list_statement = db.execute.call_args.args[0]
    assert "analisis.id_usuario" in str(list_statement)

    with pytest.raises(HTTPException) as denied:
        list_call(MagicMock(), analyst, id_usuario=9)
    assert denied.value.status_code == 403


def test_admin_and_investigator_can_filter_by_user() -> None:
    for role in ("Administrador", "Investigador"):
        db = MagicMock()
        db.scalar.return_value = 0
        db.execute.return_value.all.return_value = []
        response = list_call(db, make_user(1, role), id_usuario=9)
        assert response.items == []
        assert "analisis.id_usuario" in str(db.execute.call_args.args[0])


def test_detail_returns_ordered_top_three_and_explicit_unevaluated_threshold() -> None:
    owner = make_user(2, "Investigador")
    analysis = make_analysis(owner)
    people = [Persona(id_persona=i, identificador=f"P-{i}", nombre=f"Persona {i}", alias=None) for i in (1, 2, 3)]
    results = [ResultadoAnalisis(id_resultado=i, id_analisis=10, id_persona=i, similitud=Decimal(str(90 - i)), posicion=i, supera_umbral=False) for i in (1, 2, 3)]
    db = MagicMock()
    db.scalar.return_value = analysis
    db.execute.return_value.all.return_value = list(zip(results, people))

    response = get_history_detail(10, make_request("/historial/10"), db, owner)
    payload = response.model_dump()

    assert [item["posicion"] for item in payload["candidatos"]] == [1, 2, 3]
    assert all(item["estado_umbral"] == "umbral_no_evaluado" for item in payload["candidatos"])
    assert all(item["supera_umbral"] is False for item in payload["candidatos"])
    assert "ORDER BY" in str(db.execute.call_args.args[0])


def test_detail_after_cutoff_uses_persisted_threshold_decisions() -> None:
    owner = make_user(2, "Investigador")
    analysis = make_analysis(owner)
    analysis.fecha_analisis = datetime(2026, 10, 5, 0, 0)
    people = [
        Persona(id_persona=i, identificador=f"P-{i}", nombre=f"Persona {i}")
        for i in (1, 2)
    ]
    results = [
        ResultadoAnalisis(
            id_resultado=i,
            id_analisis=10,
            id_persona=i,
            similitud=Decimal("82.000" if i == 1 else "70.000"),
            posicion=i,
            supera_umbral=i == 1,
        )
        for i in (1, 2)
    ]
    db = MagicMock()
    db.scalar.return_value = analysis
    db.execute.return_value.all.return_value = list(zip(results, people))

    response = get_history_detail(10, make_request("/historial/10"), db, owner)

    assert [item.estado_umbral for item in response.candidatos] == [
        "posible_coincidencia",
        "coincidencia_insuficiente",
    ]


def test_detail_without_results_returns_empty_candidates() -> None:
    owner = make_user(2, "Investigador")
    db = MagicMock()
    db.scalar.return_value = make_analysis(owner)
    db.execute.return_value.all.return_value = []

    assert get_history_detail(10, make_request("/historial/10"), db, owner).candidatos == []


def test_missing_and_cross_analyst_detail_are_indistinguishable_404() -> None:
    analyst = make_user(8, "Analista")
    for analysis_id in (999, 10):
        db = MagicMock()
        db.scalar.return_value = None

        with pytest.raises(HTTPException) as denied:
            get_history_detail(analysis_id, make_request(f"/historial/{analysis_id}"), db, analyst)

        assert denied.value.status_code == 404
        assert denied.value.detail == "Análisis no encontrado"
        statement = db.scalar.call_args.args[0]
        assert "analisis.id_usuario" in str(statement)
        assert db.add.call_args.args[0].detalles == "analisis_no_disponible"


def test_history_routes_require_authorized_roles() -> None:
    for route in router.routes:
        dependency = route.dependant.dependencies[-1]
        assert dependency.call.__closure__[0].cell_contents == ("Administrador", "Investigador", "Analista")

    dependency = router.routes[0].dependant.dependencies[-1].call
    with pytest.raises(HTTPException) as denied:
        dependency(make_user(4, "Invitado"))
    assert denied.value.status_code == 403


def test_http_validation_rejects_invalid_state_and_pagination() -> None:
    app.dependency_overrides[get_current_user] = lambda: make_user(1, "Administrador")
    app.dependency_overrides[get_db] = lambda: MagicMock()
    try:
        client = TestClient(app)
        assert client.get("/historial?estado=desconocido").status_code == 422
        assert client.get("/historial?pagina=0").status_code == 422
        assert client.get("/historial?tamano_pagina=101").status_code == 422
    finally:
        app.dependency_overrides.clear()
