from unittest.mock import MagicMock

from starlette.requests import Request

from backend.models.log import Log
from backend.services.audit_service import LOGIN_FAILURE, add_event, client_ip


def make_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/test",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("192.0.2.10", 50000),
            "scheme": "http",
            "root_path": "",
            "http_version": "1.1",
        }
    )


def test_audit_event_contains_only_safe_technical_fields() -> None:
    db = MagicMock()
    request = make_request()

    add_event(db, LOGIN_FAILURE, None, request, "credenciales_invalidas")

    event = db.add.call_args.args[0]
    assert isinstance(event, Log)
    assert event.id_usuario is None
    assert event.accion == LOGIN_FAILURE
    assert event.direccion_ip == "192.0.2.10"
    assert event.detalles == "credenciales_invalidas"
    assert all(secret not in event.detalles.lower() for secret in ("password", "hash", "cookie"))


def test_client_ip_is_optional() -> None:
    request = Request({"type": "http", "headers": []})

    assert client_ip(request) is None
