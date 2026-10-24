"""Initialize ONLY local voxtrace_test; run as python -m scripts.init_voxtrace_test.

Requires explicit DATABASE_URL and DATABASE_SCHEMA environment variables.
Does not create a database/schema, seed data, or manage Alembic revisions.
"""
import os
import secrets

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool


def validate_url(raw: str) -> URL:
    url = make_url(raw)
    if (
        url.drivername != "postgresql+psycopg"
        or url.host not in {"127.0.0.1", "localhost"}
        or url.port != 5432
        or url.database != "voxtrace_test"
        or url.username != "voxtrace_tester"
        or not url.password
        or url.password == "password"
        or url.query
    ):
        raise ValueError("DATABASE_URL no cumple el destino local exclusivo requerido")
    return url


def main() -> None:
    raw_url = os.environ.get("DATABASE_URL")
    if not raw_url or os.environ.get("DATABASE_SCHEMA") != "voxtrace":
        raise SystemExit("Se requieren DATABASE_URL explícita y DATABASE_SCHEMA=voxtrace")
    try:
        url = validate_url(raw_url)
    except (ValueError, TypeError, SQLAlchemyError):
        raise SystemExit("DATABASE_URL inválida; no se realizó ninguna conexión") from None

    # Config requires a session secret even for model imports. This ephemeral
    # value is only for this process, never a database credential or server change.
    if not os.environ.get("SESSION_SECRET"):
        os.environ["SESSION_SECRET"] = secrets.token_urlsafe(48)

    from backend.core.config import settings

    # Check effective settings BEFORE importing connection.py: it constructs a
    # separate engine on import, even though engines connect lazily. A cached
    # settings object must never introduce the default voxtrace_db destination.
    try:
        effective_url = validate_url(settings.database_url)
    except (ValueError, TypeError, SQLAlchemyError):
        raise SystemExit("La configuración efectiva de DATABASE_URL no es válida") from None
    if settings.database_schema != "voxtrace" or effective_url != url:
        raise SystemExit("La configuración efectiva no coincide con el destino validado")

    from backend.database.connection import Base
    from backend.models import (
        Analisis, Audio, Embedding, Log, Persona, ResultadoAnalisis, Rol, Usuario,
    )

    expected = {"analisis", "audio", "embedding", "log", "persona", "resultado_analisis", "rol", "usuario"}
    imported = (Analisis, Audio, Embedding, Log, Persona, ResultadoAnalisis, Rol, Usuario)
    if {model.__table__.name for model in imported} != expected or set(Base.metadata.tables) != {f"voxtrace.{name}" for name in expected}:
        raise SystemExit("Los modelos registrados no corresponden a las ocho tablas esperadas")

    # Pin the actual transport to IPv4 loopback, including when URL says localhost.
    # Reject URL query parameters above so host/service/options cannot override it.
    engine = create_engine(url, poolclass=NullPool, connect_args={
        "hostaddr": "127.0.0.1", "connect_timeout": 5,
    })
    try:
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
                    raise ValueError("La conexión real no corresponde al destino autorizado")
                exists = connection.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'voxtrace')"))
                if exists is not True:
                    raise ValueError("El esquema voxtrace no existe")
                # Reject views/sequences as well: initialization requires a clean
                # schema, including no foreign or partitioned tables.
                relations = connection.scalar(text("""
                    SELECT count(*) FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'voxtrace'
                """))
                if relations != 0:
                    raise ValueError("El esquema voxtrace contiene relaciones; inicialización abortada")
                Base.metadata.create_all(bind=connection, checkfirst=False)
        print("Ocho tablas creadas exclusivamente en voxtrace_test.voxtrace")
    except ValueError as error:
        raise SystemExit(str(error)) from None
    except SQLAlchemyError:
        # Never print exceptions which could include credentials or connection URL.
        raise SystemExit("No se pudo inicializar voxtrace_test; revise conexión y permisos") from None
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
