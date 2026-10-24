import asyncio
from getpass import getpass

from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

from backend.core.config import settings
from backend.core.security import get_current_user, require_roles, verify_password
from backend.database.connection import SessionLocal
from backend.main import app
from backend.models.usuario import Usuario


async def check_session_and_authorization(cookie_value: str) -> tuple[bool, bool]:
    db = SessionLocal()
    result = {"user": False, "role": False}
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/integration-probe",
        "headers": [
            (
                b"cookie",
                f"{settings.session_cookie_name}={cookie_value}".encode(),
            )
        ],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("testclient", 1),
        "scheme": "http",
        "root_path": "",
        "http_version": "1.1",
    }

    async def probe_app(probe_scope, receive, send):
        request = Request(probe_scope)
        current_user = get_current_user(request, db)
        authorized_user = require_roles("Administrador")(current_user)
        result["user"] = authorized_user.id_usuario > 0
        result["role"] = authorized_user.rol.nombre == "Administrador"
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        return None

    middleware = SessionMiddleware(
        probe_app,
        secret_key=settings.session_secret,
        session_cookie=settings.session_cookie_name,
        https_only=settings.session_cookie_secure,
        same_site=settings.session_cookie_samesite,
        max_age=settings.session_max_age_seconds,
    )

    try:
        await middleware(scope, receive, send)
    except Exception:
        result["user"] = False
        result["role"] = False
    finally:
        db.close()

    return result["user"], result["role"]


def main() -> None:
    email = input("Correo del Administrador: ").strip()
    password = getpass("Contraseña: ")
    client = TestClient(app)
    errors = False

    try:
        valid_response = client.post(
            "/auth/login",
            json={"correo": email, "password": password},
        )
        response_status = valid_response.status_code
        if response_status == 200:
            response_category = "200"
            safe_detail = "login_aceptado"
        elif response_status == 401:
            response_category = "401"
            safe_detail = "Credenciales inválidas"
        elif response_status == 422:
            response_category = "422"
            safe_detail = "validacion_de_entrada"
        elif response_status == 500:
            response_category = "500"
            safe_detail = "error_de_servidor"
        else:
            response_category = "otro"
            safe_detail = "detalle_omitido_por_seguridad"

        diagnostic_db = SessionLocal()
        diagnostic_user = diagnostic_db.scalar(
            select(Usuario).where(Usuario.correo == email)
        )
        user_found = diagnostic_user is not None
        password_verified = user_found and verify_password(
            password,
            diagnostic_user.password_hash,
        )
        diagnostic_db.close()

        valid_login = valid_response.status_code == 200
        session_created = settings.session_cookie_name in client.cookies

        if valid_login and session_created:
            cookie_value = client.cookies.get(settings.session_cookie_name)
            user_recovered, admin_role_recognized = asyncio.run(
                check_session_and_authorization(cookie_value)
            )
        else:
            user_recovered = False
            admin_role_recognized = False

        wrong_response = client.post(
            "/auth/login",
            json={"correo": email, "password": password + "-incorrecta"},
        )
        wrong_status_code = wrong_response.status_code
        wrong_password_rejected = wrong_response.status_code == 401
    except Exception:
        valid_login = False
        session_created = False
        user_recovered = False
        admin_role_recognized = False
        wrong_password_rejected = False
        errors = True
        response_status = 0
        response_category = "error_de_ejecucion"
        safe_detail = "detalle_omitido_por_seguridad"
        user_found = False
        password_verified = False
        wrong_status_code = 0

    print(f"login_status_code={response_status}")
    print(f"login_categoria={response_category}")
    print(f"login_detalle_seguro={safe_detail}")
    print(f"usuario_encontrado_postgresql={user_found}")
    print(f"verify_password_directo={password_verified}")
    print(f"contrasena_incorrecta_status_code={wrong_status_code}")
    print(f"login_valido={valid_login}")
    print(f"sesion_creada={session_created}")
    print(f"usuario_recuperado={user_recovered}")
    print(f"rol_administrador_reconocido={admin_role_recognized}")
    print(f"contrasena_incorrecta_rechazada={wrong_password_rejected}")
    print(f"errores={errors}")


if __name__ == "__main__":
    main()
