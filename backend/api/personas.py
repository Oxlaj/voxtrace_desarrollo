import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.core.security import require_roles
from backend.database.connection import get_db
from backend.models.persona import Persona
from backend.models.audio import Audio
from backend.models.resultado_analisis import ResultadoAnalisis
from backend.models.usuario import Usuario
from backend.schemas.persona import PersonaCreate, PersonaRead, PersonaUpdate
from backend.services.person_registration_service import register_with_sample
from backend.services.audit_service import (
    PERSON_CREATED,
    PERSON_DELETED,
    PERSON_ERROR,
    PERSON_UPDATED,
    record_event,
)

router = APIRouter(prefix="/personas", tags=["personas"])


@router.post("/con-muestra", response_model=PersonaRead, status_code=201)
async def create_persona_with_sample(
    request: Request,
    persona: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("Administrador", "Investigador")),
) -> PersonaRead:
    try:
        payload = PersonaCreate.model_validate_json(persona)
    except ValidationError as error:
        await file.close()
        raise HTTPException(422, detail=json.loads(error.json())) from error
    return await register_with_sample(payload, file, request, db, current_user)


@router.get("", response_model=list[PersonaRead])
def list_personas(
    search: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("Administrador", "Investigador", "Analista")),
) -> list[Persona]:
    statement = select(Persona).order_by(Persona.id_persona)
    if search:
        pattern = f"%{search}%"
        statement = statement.where(
            or_(
                Persona.nombre.ilike(pattern),
                Persona.identificador.ilike(pattern),
                Persona.alias.ilike(pattern),
            )
        )
    return list(db.scalars(statement).all())


@router.post("", response_model=PersonaRead, status_code=status.HTTP_201_CREATED)
def create_persona(
    payload: PersonaCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("Administrador", "Investigador")),
) -> Persona:
    existing = db.scalar(
        select(Persona).where(Persona.identificador == payload.identificador)
    )
    if existing is not None:
        record_event(db, PERSON_ERROR, current_user.id_usuario, request, "identificador_duplicado")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El identificador ya está registrado",
        )

    persona = Persona(**payload.model_dump())
    db.add(persona)
    try:
        db.commit()
        db.refresh(persona)
    except SQLAlchemyError as error:
        db.rollback()
        record_event(db, PERSON_ERROR, current_user.id_usuario, request, "persistencia_bd")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo registrar la persona",
        ) from error
    record_event(db, PERSON_CREATED, current_user.id_usuario, request, "persona_creada")
    return persona


@router.get("/{persona_id}", response_model=PersonaRead)
def get_persona(
    persona_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(
        require_roles("Administrador", "Investigador", "Analista")
    ),
) -> Persona:
    persona = db.get(Persona, persona_id)
    if persona is None:
        record_event(db, PERSON_ERROR, current_user.id_usuario, request, "persona_no_encontrada")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Persona no encontrada")
    return persona


@router.patch("/{persona_id}", response_model=PersonaRead)
def update_persona(
    persona_id: int,
    payload: PersonaUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("Administrador", "Investigador")),
) -> Persona:
    persona = db.get(Persona, persona_id)
    if persona is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Persona no encontrada")

    updates = payload.model_dump(exclude_unset=True)
    if "identificador" in updates:
        duplicate = db.scalar(
            select(Persona).where(
                Persona.identificador == updates["identificador"],
                Persona.id_persona != persona_id,
            )
        )
        if duplicate is not None:
            record_event(db, PERSON_ERROR, current_user.id_usuario, request, "identificador_duplicado")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El identificador ya está registrado",
            )

    for field, value in updates.items():
        setattr(persona, field, value)
    try:
        db.commit()
        db.refresh(persona)
    except SQLAlchemyError as error:
        db.rollback()
        record_event(db, PERSON_ERROR, current_user.id_usuario, request, "persistencia_bd")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo editar la persona",
        ) from error
    record_event(db, PERSON_UPDATED, current_user.id_usuario, request, f"persona_id={persona_id}")
    return persona


@router.delete("/{persona_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_persona(
    persona_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles("Administrador")),
) -> None:
    persona = db.get(Persona, persona_id)
    if persona is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Persona no encontrada")

    has_audio = db.scalar(
        select(Audio.id_audio).where(Audio.id_persona == persona_id).limit(1)
    ) is not None
    has_result = db.scalar(
        select(ResultadoAnalisis.id_resultado)
        .where(ResultadoAnalisis.id_persona == persona_id)
        .limit(1)
    ) is not None
    if has_audio or has_result:
        record_event(db, PERSON_ERROR, current_user.id_usuario, request, f"eliminacion_bloqueada;persona_id={persona_id}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No es posible eliminar la persona porque posee información asociada que debe conservarse.",
        )

    try:
        db.delete(persona)
        db.commit()
    except (IntegrityError, SQLAlchemyError) as error:
        db.rollback()
        record_event(db, PERSON_ERROR, current_user.id_usuario, request, f"eliminacion_no_completada;persona_id={persona_id}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No es posible eliminar la persona porque posee información asociada que debe conservarse.",
        ) from error
    record_event(db, PERSON_DELETED, current_user.id_usuario, request, f"persona_id={persona_id}")
