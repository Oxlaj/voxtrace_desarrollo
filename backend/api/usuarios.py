from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from backend.core.security import get_current_user, hash_password, require_roles
from backend.database.connection import get_db
from backend.models.rol import Rol
from backend.models.usuario import Usuario
from backend.schemas.usuario import PasswordAdminUpdate, PasswordSelfUpdate, RolRead, UsuarioCreate, UsuarioRead, UsuarioUpdate
from backend.services.audit_service import record_event

router = APIRouter(tags=["usuarios"])

def public_user(user: Usuario) -> UsuarioRead:
    return UsuarioRead(
        id_usuario=user.id_usuario,
        nombre=user.nombre,
        correo=user.correo,
        estado=user.estado,
        debe_cambiar_password=user.debe_cambiar_password,
        fecha_creacion=user.fecha_creacion,
        rol=RolRead.model_validate(user.rol),
    )

def admin_only():
    return Depends(require_roles("Administrador"))

@router.get("/roles", response_model=list[RolRead])
def list_roles(db: Session = Depends(get_db), _: Usuario = admin_only()) -> list[Rol]:
    return list(db.scalars(select(Rol).where(Rol.nombre.in_(("Administrador", "Investigador", "Analista"))).order_by(Rol.id_rol)).all())

@router.get("/usuarios", response_model=list[UsuarioRead])
def list_users(busqueda: str | None = Query(default=None, max_length=100), id_rol: int | None = Query(default=None, gt=0), estado: bool | None = None, db: Session = Depends(get_db), _: Usuario = admin_only()) -> list[UsuarioRead]:
    statement = select(Usuario).join(Rol).order_by(Usuario.id_usuario)
    if busqueda:
        pattern = f"%{busqueda.strip()}%"; statement = statement.where(or_(Usuario.nombre.ilike(pattern), Usuario.correo.ilike(pattern)))
    if id_rol is not None: statement = statement.where(Usuario.id_rol == id_rol)
    if estado is not None: statement = statement.where(Usuario.estado == estado)
    return [public_user(item) for item in db.scalars(statement).all()]

@router.get("/usuarios/{user_id}", response_model=UsuarioRead)
def get_user(user_id: int, db: Session = Depends(get_db), _: Usuario = admin_only()) -> UsuarioRead:
    user = db.get(Usuario, user_id)
    if user is None: raise HTTPException(404, "Usuario no encontrado")
    return public_user(user)

def valid_role(db: Session, role_id: int) -> Rol:
    role = db.get(Rol, role_id)
    if role is None or role.nombre not in {"Administrador", "Investigador", "Analista"}: raise HTTPException(422, "Rol no válido")
    return role

@router.post("/usuarios", response_model=UsuarioRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UsuarioCreate, request: Request, db: Session = Depends(get_db), actor: Usuario = admin_only()) -> UsuarioRead:
    role = valid_role(db, payload.id_rol)
    if db.scalar(select(Usuario).where(func.lower(Usuario.correo) == payload.correo.lower())) is not None: raise HTTPException(409, "El correo ya está registrado")
    user = Usuario(nombre=payload.nombre.strip(), correo=payload.correo.lower(), id_rol=role.id_rol, password_hash=hash_password(payload.password), estado=True, rol=role)
    db.add(user)
    try: db.commit(); db.refresh(user)
    except IntegrityError as error: db.rollback(); raise HTTPException(409, "El correo ya está registrado") from error
    except SQLAlchemyError as error: db.rollback(); raise HTTPException(500, "No se pudo crear el usuario") from error
    record_event(db, "usuario_creado", actor.id_usuario, request, f"usuario_id={user.id_usuario};rol={role.nombre}")
    return public_user(user)

def protect_last_admin(db: Session, target: Usuario, new_role: Rol, new_state: bool) -> None:
    if target.rol.nombre == "Administrador" and target.estado and (new_role.nombre != "Administrador" or not new_state):
        count = db.scalar(select(func.count()).select_from(Usuario).join(Rol).where(Rol.nombre == "Administrador", Usuario.estado.is_(True))) or 0
        if count <= 1: raise HTTPException(409, "Debe permanecer al menos un Administrador activo")

@router.patch("/usuarios/{user_id}", response_model=UsuarioRead)
def update_user(user_id: int, payload: UsuarioUpdate, request: Request, db: Session = Depends(get_db), actor: Usuario = admin_only()) -> UsuarioRead:
    user = db.get(Usuario, user_id)
    if user is None: raise HTTPException(404, "Usuario no encontrado")
    changes = payload.model_dump(exclude_unset=True); old_role = user.rol.nombre; old_state = user.estado
    role = valid_role(db, changes.get("id_rol", user.id_rol))
    new_state = changes.get("estado", user.estado); protect_last_admin(db, user, role, new_state)
    if "correo" in changes:
        duplicate = db.scalar(select(Usuario).where(func.lower(Usuario.correo) == changes["correo"].lower(), Usuario.id_usuario != user_id))
        if duplicate is not None: raise HTTPException(409, "El correo ya está registrado")
        user.correo = changes["correo"].lower()
    if "nombre" in changes: user.nombre = changes["nombre"].strip()
    user.id_rol = role.id_rol; user.rol = role; user.estado = new_state
    try: db.commit(); db.refresh(user)
    except SQLAlchemyError as error: db.rollback(); raise HTTPException(500, "No se pudo actualizar el usuario") from error
    record_event(db, "usuario_editado", actor.id_usuario, request, f"usuario_id={user_id};rol={old_role}->{role.nombre};estado={old_state}->{new_state}")
    return public_user(user)

@router.post("/usuarios/{user_id}/password", status_code=204)
def change_user_password(user_id: int, payload: PasswordAdminUpdate, request: Request, db: Session = Depends(get_db), actor: Usuario = admin_only()) -> None:
    user = db.get(Usuario, user_id)
    if user is None: raise HTTPException(404, "Usuario no encontrado")
    user.password_hash = hash_password(payload.password)
    user.debe_cambiar_password = True
    try: db.commit()
    except SQLAlchemyError as error: db.rollback(); raise HTTPException(500, "No se pudo cambiar la contraseña") from error
    record_event(db, "password_usuario_cambiado", actor.id_usuario, request, f"usuario_id={user_id}")


@router.post("/cuenta/password", status_code=204)
def change_own_password(
    payload: PasswordSelfUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> None:
    current_user.password_hash = hash_password(payload.password)
    current_user.debe_cambiar_password = False
    try:
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(500, "No se pudo cambiar la contraseña") from error
    record_event(
        db,
        "password_propio_cambiado",
        current_user.id_usuario,
        request,
        "cambio_password_obligatorio_completado",
    )
