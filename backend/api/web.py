from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from backend.core.security import get_current_user, require_password_changed, require_roles
from backend.core.csrf import ensure_csrf_token
from backend.models.usuario import Usuario
from backend.core.config import settings

router = APIRouter(tags=["frontend"])
templates = Jinja2Templates(directory=Path("frontend/templates"))


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="login.html", context={"csrf_token": ensure_csrf_token(request)})


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(
    request: Request,
    current_user: Usuario = Depends(require_password_changed),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"current_user": current_user, "csrf_token": ensure_csrf_token(request)},
    )


@router.get("/app/personas", response_class=HTMLResponse)
def personas_page(
    request: Request,
    current_user: Usuario = Depends(
        require_roles("Administrador", "Investigador", "Analista")
    ),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="personas.html",
        context={"current_user": current_user, "csrf_token": ensure_csrf_token(request)},
    )


@router.get("/app/personas/nueva", response_class=HTMLResponse)
def new_person_page(
    request: Request,
    current_user: Usuario = Depends(
        require_roles("Administrador", "Investigador")
    ),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="persona_form.html",
        context={"current_user": current_user, "csrf_token": ensure_csrf_token(request)},
    )


@router.get("/app/personas/{persona_id}/muestras", response_class=HTMLResponse)
def samples_page(
    persona_id: int,
    request: Request,
    current_user: Usuario = Depends(require_roles("Administrador", "Investigador", "Analista")),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="muestras.html",
        context={
            "current_user": current_user,
            "csrf_token": ensure_csrf_token(request),
            "persona_id": persona_id,
        },
    )


@router.get("/app/analizar", response_class=HTMLResponse)
def analyze_page(
    request: Request,
    current_user: Usuario = Depends(require_roles("Administrador", "Investigador", "Analista")),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="analizar.html",
        context={"current_user": current_user, "csrf_token": ensure_csrf_token(request), "maximum_size": settings.max_audio_size_mb},
    )


@router.get("/app/historial", response_class=HTMLResponse)
def history_page(
    request: Request,
    current_user: Usuario = Depends(require_roles("Administrador", "Investigador", "Analista")),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="historial.html",
        context={"current_user": current_user, "csrf_token": ensure_csrf_token(request)},
    )


@router.get("/app/historial/{analysis_id}", response_class=HTMLResponse)
def history_detail_page(
    analysis_id: int,
    request: Request,
    current_user: Usuario = Depends(require_roles("Administrador", "Investigador", "Analista")),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="historial_detalle.html",
        context={"current_user": current_user, "csrf_token": ensure_csrf_token(request), "analysis_id": analysis_id},
    )


@router.get("/app/usuarios", response_class=HTMLResponse)
def users_page(request: Request, current_user: Usuario = Depends(require_roles("Administrador"))) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="usuarios.html", context={"current_user": current_user, "csrf_token": ensure_csrf_token(request)})


@router.get("/app/usuarios/nuevo", response_class=HTMLResponse)
def new_user_page(request: Request, current_user: Usuario = Depends(require_roles("Administrador"))) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="usuario_form.html", context={"current_user": current_user, "csrf_token": ensure_csrf_token(request), "user_id": None})


@router.get("/app/usuarios/{user_id}/editar", response_class=HTMLResponse)
def edit_user_page(user_id: int, request: Request, current_user: Usuario = Depends(require_roles("Administrador"))) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="usuario_form.html", context={"current_user": current_user, "csrf_token": ensure_csrf_token(request), "user_id": user_id})


@router.get("/app/auditoria", response_class=HTMLResponse)
def audit_page(request: Request, current_user: Usuario = Depends(require_roles("Administrador"))) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="auditoria.html", context={"current_user": current_user, "csrf_token": ensure_csrf_token(request)})

@router.get("/app/cambiar-password", response_class=HTMLResponse)
def change_password_page(
    request: Request,
    current_user: Usuario = Depends(get_current_user),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="cambiar_password.html",
        context={
            "current_user": current_user,
            "csrf_token": ensure_csrf_token(request),
        },
    )
