from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.connection import SessionLocal
from backend.models.rol import Rol


BASE_ROLES: dict[str, str] = {
    "Administrador": "Acceso administrativo",
    "Investigador": "Investigación y gestión de análisis",
    "Analista": "Análisis y consulta autorizada",
}


@dataclass(frozen=True)
class BootstrapResult:
    created: tuple[str, ...]
    descriptions_completed: tuple[str, ...]
    existing: tuple[str, ...]


def bootstrap_roles(db: Session) -> BootstrapResult:
    """Garantiza los roles base mediante una única transacción idempotente."""
    try:
        roles = list(
            db.scalars(select(Rol).where(Rol.nombre.in_(tuple(BASE_ROLES)))).all()
        )
        by_name = {role.nombre: role for role in roles}
        created: list[str] = []
        completed: list[str] = []
        existing: list[str] = []

        for name, description in BASE_ROLES.items():
            role = by_name.get(name)
            if role is None:
                db.add(Rol(nombre=name, descripcion=description))
                created.append(name)
            else:
                existing.append(name)
                if not role.descripcion or not role.descripcion.strip():
                    role.descripcion = description
                    completed.append(name)

        db.commit()
        return BootstrapResult(
            created=tuple(created),
            descriptions_completed=tuple(completed),
            existing=tuple(existing),
        )
    except Exception:
        db.rollback()
        raise


def main() -> None:
    db = SessionLocal()
    try:
        result = bootstrap_roles(db)
        print(
            "Roles base verificados. "
            f"Creados: {len(result.created)}; "
            f"existentes: {len(result.existing)}; "
            f"descripciones completadas: {len(result.descriptions_completed)}."
        )
    except Exception as error:
        print(f"No se pudieron garantizar los roles base ({type(error).__name__}).")
        raise SystemExit(1) from error
    finally:
        db.close()


if __name__ == "__main__":
    main()
