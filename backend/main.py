from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from backend.core.csrf_middleware import CSRFMiddleware

from backend.api.personas import router as personas_router
from backend.api.muestras import router as muestras_router
from backend.api.analisis import router as analisis_router
from backend.api.historial import router as historial_router
from backend.api.reportes import router as reportes_router
from backend.api.web import router as web_router
from backend.core.config import settings
from backend.api.auth import router as auth_router
from backend.api.usuarios import router as usuarios_router
from backend.api.auditoria import router as auditoria_router
from backend.api.dashboard import router as dashboard_router

app = FastAPI(title=settings.app_name)
app.add_middleware(CSRFMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie=settings.session_cookie_name,
    https_only=settings.session_cookie_secure,
    same_site=settings.session_cookie_samesite,
    max_age=settings.session_max_age_seconds,
)
app.include_router(auth_router)
app.include_router(usuarios_router)
app.include_router(auditoria_router)
app.include_router(dashboard_router)
app.include_router(personas_router)
app.include_router(muestras_router)
app.include_router(analisis_router)
app.include_router(historial_router)
app.include_router(reportes_router)
app.include_router(web_router)
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}
