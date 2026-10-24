from getpass import getpass

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.core.security import hash_password
from backend.database.connection import SessionLocal
from backend.models.rol import Rol
from backend.models.usuario import Usuario

ADMIN_ROLE = "Administrador"


def create_admin(db: Session, name: str, email: str, password: str) -> Usuario:
    normalized_name = name.strip()
    normalized_email = email.strip().lower()

    if not normalized_name:
        raise ValueError("El nombre es obligatorio")
    if not normalized_email:
        raise ValueError("El correo es obligatorio")
    if not password:
        raise ValueError("La contraseña es obligatoria")

    try:
        existing_user = db.scalar(
            select(Usuario).where(Usuario.correo == normalized_email)
        )
        if existing_user is not None:
            raise ValueError("El correo ya está registrado")

        role = db.scalar(select(Rol).where(Rol.nombre == ADMIN_ROLE))
        if role is None:
            role = Rol(nombre=ADMIN_ROLE, descripcion="Acceso administrativo")
            db.add(role)
            db.flush()

        user = Usuario(
            id_rol=role.id_rol,
            nombre=normalized_name,
            correo=normalized_email,
            password_hash=hash_password(password),
            estado=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    except (SQLAlchemyError, ValueError):
        db.rollback()
        raise


def main() -> None:
    print("Creación del primer usuario Administrador")
    name = input("Nombre: ")
    email = input("Correo: ")
    password = getpass("Contraseña: ")
    confirmation = getpass("Confirmar contraseña: ")

    if password != confirmation:
        raise SystemExit("Las contraseñas no coinciden")

    db = SessionLocal()
    try:
        user = create_admin(db, name, email, password)
        print(f"Administrador creado para {user.correo}.")
    except (SQLAlchemyError, ValueError) as error:
        print(f"No se pudo crear el Administrador: {error}")
        raise SystemExit(1) from error
    finally:
        db.close()


if __name__ == "__main__":
    main()
