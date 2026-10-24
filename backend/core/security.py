from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.models.usuario import Usuario

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> Usuario:
    user_id = request.session.get("user_id")
    if not isinstance(user_id, int):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticación requerida",
        )

    user = db.get(Usuario, user_id)
    if user is None or not user.estado:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesión inválida",
        )

    return user

def require_password_changed(
    current_user: Usuario = Depends(get_current_user),
) -> Usuario:
    if current_user.debe_cambiar_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debes cambiar tu contraseña antes de continuar",
        )

    return current_user

def require_roles(*allowed_roles: str) -> Callable:
    def role_dependency(
    current_user: Usuario = Depends(require_password_changed),
) -> Usuario:
        role_name = current_user.rol.nombre
        if role_name not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para esta operación",
            )
        return current_user

    return role_dependency
