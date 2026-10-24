from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.security import get_current_user, verify_password
from backend.core.csrf import ensure_csrf_token, rotate_csrf_token
from backend.database.connection import get_db
from backend.models.usuario import Usuario
from backend.services.audit_service import LOGIN_FAILURE, LOGIN_SUCCESS, LOGOUT, record_event

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    correo: EmailStr
    password: str


class CurrentUserResponse(BaseModel):
    id_usuario: int
    nombre: str
    correo: EmailStr
    rol: str


class CsrfTokenResponse(BaseModel):
    csrf_token: str


@router.get("/csrf", response_model=CsrfTokenResponse)
def csrf_token(request: Request) -> CsrfTokenResponse:
    return CsrfTokenResponse(csrf_token=ensure_csrf_token(request))


@router.get("/me", response_model=CurrentUserResponse)
def authenticated_user(
    current_user: Usuario = Depends(get_current_user),
) -> CurrentUserResponse:
    return CurrentUserResponse(
        id_usuario=current_user.id_usuario,
        nombre=current_user.nombre,
        correo=current_user.correo,
        rol=current_user.rol.nombre,
    )


@router.post("/login")
def login(
    credentials: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, str | bool]:
    user = db.scalar(select(Usuario).where(Usuario.correo == credentials.correo))
    if user is None or not user.estado or not verify_password(
        credentials.password,
        user.password_hash,
    ):
        record_event(db, LOGIN_FAILURE, user.id_usuario if user else None, request, "credenciales_invalidas")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas",
        )

    request.session.clear()
    request.session["user_id"] = user.id_usuario
    rotate_csrf_token(request)
    record_event(db, LOGIN_SUCCESS, user.id_usuario, request, "autenticacion_exitosa")
    return {
    "message": "Sesión iniciada",
    "debe_cambiar_password": user.debe_cambiar_password,
}


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)) -> dict[str, str]:
    user_id = request.session.get("user_id")
    record_event(db, LOGOUT, user_id if isinstance(user_id, int) else None, request, "sesion_cerrada")
    request.session.clear()
    return {"message": "Sesión cerrada"}
