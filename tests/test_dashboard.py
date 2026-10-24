from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.api.dashboard import dashboard_stats, router
from backend.core.security import get_current_user
from backend.main import app
from backend.models.rol import Rol
from backend.models.usuario import Usuario


def make_user(role: str, user_id: int = 7) -> Usuario:
    return Usuario(
        id_usuario=user_id,
        id_rol=1,
        nombre="Usuario Dashboard",
        correo="dashboard@example.com",
        password_hash="hidden",
        estado=True,
        rol=Rol(id_rol=1, nombre=role),
    )


def make_db() -> MagicMock:
    now = datetime.now()
    db = MagicMock()
    db.scalar.side_effect = [12, 33, 5]
    db.scalars.return_value.all.return_value = [now, now - timedelta(days=2)]
    db.execute.return_value.all.return_value = [
        (datetime(2026, 10, 4, 20, 0), False),
        (datetime(2026, 10, 5, 1, 0), True),
        (datetime(2026, 10, 5, 2, 0), False),
    ]
    return db


@pytest.mark.parametrize("role", ["Administrador", "Investigador"])
def test_global_roles_receive_real_aggregate_scope(role: str) -> None:
    response = dashboard_stats(make_db(), make_user(role))

    assert response.alcance_analisis == "global"
    assert response.total_analisis == 5
    assert response.inventario.personas == 12
    assert response.inventario.muestras == 33
    assert sum(day.cantidad for day in response.analisis_ultimos_dias) == 2
    assert response.resultados.model_dump() == {
        "posible_coincidencia": 1,
        "coincidencia_insuficiente": 1,
        "umbral_no_evaluado": 1,
    }


def test_analyst_statistics_are_scoped_to_own_analyses() -> None:
    db = make_db()

    response = dashboard_stats(db, make_user("Analista", user_id=19))

    assert response.alcance_analisis == "propio"
    analysis_count_query = str(db.scalar.call_args_list[2].args[0])
    recent_query = str(db.scalars.call_args.args[0])
    outcomes_query = str(db.execute.call_args.args[0])
    assert "analisis.id_usuario" in analysis_count_query
    assert "analisis.id_usuario" in recent_query
    assert "analisis.id_usuario" in outcomes_query


def test_empty_dashboard_returns_seven_zero_days_and_safe_counts() -> None:
    db = MagicMock()
    db.scalar.side_effect = [0, 0, 0]
    db.scalars.return_value.all.return_value = []
    db.execute.return_value.all.return_value = []

    response = dashboard_stats(db, make_user("Administrador"))

    assert len(response.analisis_ultimos_dias) == 7
    assert all(day.cantidad == 0 for day in response.analisis_ultimos_dias)
    assert response.resultados.model_dump() == {
        "posible_coincidencia": 0,
        "coincidencia_insuficiente": 0,
        "umbral_no_evaluado": 0,
    }


def test_dashboard_endpoint_allows_only_existing_application_roles() -> None:
    dependency = router.routes[0].dependant.dependencies[-1].call
    assert dependency.__closure__[0].cell_contents == (
        "Administrador",
        "Investigador",
        "Analista",
    )
    with pytest.raises(HTTPException) as denied:
        dependency(make_user("Invitado"))
    assert denied.value.status_code == 403


@pytest.mark.parametrize("role", ["Administrador", "Investigador", "Analista"])
def test_dashboard_frontend_has_dynamic_safe_charts_for_every_role(role: str) -> None:
    app.dependency_overrides[get_current_user] = lambda: make_user(role)
    try:
        client = TestClient(app)
        page = client.get("/dashboard")
        script = client.get("/static/js/dashboard.js").text
    finally:
        app.dependency_overrides.clear()

    assert page.status_code == 200
    for element_id in ("daily-chart", "outcome-chart", "inventory-chart"):
        assert f'id="{element_id}"' in page.text
    assert "/dashboard/estadisticas" in script
    assert "setInterval(loadDashboard,30000)" in script
    assert "Posible coincidencia" in script
    assert "Coincidencia insuficiente" in script
    assert "Umbral no evaluado" in script
    for forbidden in ("ruta_audio", "hash_audio", "embedding", "password", "cookie"):
        assert forbidden not in page.text.lower() + script.lower()


def test_removed_interface_labels_are_absent() -> None:
    app.dependency_overrides[get_current_user] = lambda: make_user("Administrador")
    try:
        client = TestClient(app)
        content = "".join(
            client.get(path).text
            for path in (
                "/app/personas/nueva",
                "/app/usuarios",
                "/app/usuarios/nuevo",
                "/app/usuarios/1/editar",
            )
        )
    finally:
        app.dependency_overrides.clear()

    assert "Nuevo registro" not in content
    assert "Administración" not in content
