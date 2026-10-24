from datetime import datetime
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.api.personas import get_persona, router
from backend.models.log import Log
from backend.models.persona import Persona
from backend.models.usuario import Usuario


def make_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/personas/4",
            "headers": [],
            "query_string": b"",
            "client": ("192.0.2.50", 50000),
        }
    )


def make_user() -> Usuario:
    return Usuario(id_usuario=7, id_rol=1, nombre="Admin", correo="admin@example.com", password_hash="hidden", estado=True)


def test_get_existing_person_returns_person_without_audit_error() -> None:
    person = Persona(id_persona=4, nombre="Persona 4", identificador="P-004", fecha_registro=datetime.now())
    db = MagicMock()
    db.get.return_value = person

    assert get_persona(4, make_request(), db, make_user()) is person
    db.add.assert_not_called()


def test_get_missing_person_returns_404_and_audits_authorized_user() -> None:
    db = MagicMock()
    db.get.return_value = None

    with pytest.raises(HTTPException) as captured:
        get_persona(4, make_request(), db, make_user())

    assert captured.value.status_code == 404
    event = db.add.call_args.args[0]
    assert isinstance(event, Log)
    assert event.id_usuario == 7
    assert event.accion == "error_persona"
    assert event.detalles == "persona_no_encontrada"
    db.commit.assert_called_once_with()


def test_get_person_route_requires_all_read_roles() -> None:
    route = next(route for route in router.routes if route.path == "/personas/{persona_id}" and "GET" in route.methods)
    dependency = route.dependant.dependencies[-1]

    assert dependency.call.__name__ == "role_dependency"
    assert dependency.call.__closure__[0].cell_contents == ("Administrador", "Investigador", "Analista")
