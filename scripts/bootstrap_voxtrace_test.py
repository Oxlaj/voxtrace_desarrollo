"""Seed ONLY local voxtrace_test: python -m scripts.bootstrap_voxtrace_test.

Requires explicit DATABASE_URL and DATABASE_SCHEMA=voxtrace. Existing scripts
are reused as functions; their CLI entry points and SessionLocal are never used.
"""
import os
import secrets
import warnings
from getpass import GetPassWarning, getpass

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from scripts.init_voxtrace_test import validate_url


def main() -> None:
    engine = None
    try:
        raw_url = os.environ.get("DATABASE_URL")
        if not raw_url or os.environ.get("DATABASE_SCHEMA") != "voxtrace":
            raise ValueError("Missing explicit test configuration")
        url = validate_url(raw_url)

        # Only satisfies model-import settings; no server is started or changed.
        if not os.environ.get("SESSION_SECRET"):
            os.environ["SESSION_SECRET"] = secrets.token_urlsafe(48)
        from backend.core.config import settings

        if settings.database_schema != "voxtrace" or validate_url(settings.database_url) != url:
            raise ValueError("Effective settings differ from validated configuration")

        # Validate settings before imports that construct the backend engine.
        from scripts.bootstrap_roles import bootstrap_roles
        from scripts.create_admin import create_admin

        name = input("Nombre del administrador de pruebas: ").strip()
        email = input("Correo del administrador de pruebas: ").strip()
        # Refuse getpass's fallback to potentially echoed input.
        with warnings.catch_warnings():
            warnings.simplefilter("error", GetPassWarning)
            password = getpass("Contraseña del administrador de pruebas: ")
            confirmation = getpass("Confirmar contraseña: ")
        if not name or not email or not password or password != confirmation:
            raise ValueError("Invalid administrator input")

        engine = create_engine(url, poolclass=NullPool, connect_args={
            "hostaddr": "127.0.0.1", "connect_timeout": 5,
        })
        with engine.connect() as connection:
            with connection.begin():
                identity = connection.execute(text("""
                    SELECT current_database() AS database_name,
                           current_user AS user_name, session_user AS login_name,
                           host(inet_server_addr()) AS server_host,
                           inet_server_port() AS server_port
                """)).mappings().one()
                if dict(identity) != {
                    "database_name": "voxtrace_test", "user_name": "voxtrace_tester",
                    "login_name": "voxtrace_tester", "server_host": "127.0.0.1",
                    "server_port": 5432,
                }:
                    raise ValueError("Real connection identity differs")
                if connection.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'voxtrace')")) is not True:
                    raise ValueError("Schema voxtrace is missing")
                expected = {"rol", "usuario", "persona", "audio", "embedding", "analisis", "resultado_analisis", "log"}
                tables = set(connection.scalars(text("""
                    SELECT c.relname FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'voxtrace' AND c.relkind IN ('r', 'p')
                """)).all())
                if tables != expected:
                    raise ValueError("Expected test tables are missing or differ")

                # No write occurs above. Savepoints contain the existing helper
                # commits; only this outer transaction commits both operations.
                # Binding directly to this Connection prevents session pooling
                # from switching to a different, unvalidated connection.
                with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                    bootstrap_roles(db)
                    create_admin(db, name, email, password)
        print("Roles y administrador de pruebas creados en voxtrace_test.voxtrace.")
    except (KeyboardInterrupt, EOFError):
        raise SystemExit("Inicialización de pruebas cancelada.") from None
    except Exception:
        # Do not display exception text, URLs, passwords, SQL or tracebacks.
        # A lost COMMIT reply can leave a committed operation: inspect manually.
        raise SystemExit(
            "No se completó la inicialización de pruebas. Revise configuración, "
            "identidad local, tablas, permisos y datos. Si se perdió la conexión "
            "al confirmar, compruebe el resultado antes de repetir."
        ) from None
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                pass  # Do not expose connection details during cleanup.


if __name__ == "__main__":
    main()
