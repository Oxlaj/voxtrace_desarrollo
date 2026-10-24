from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from backend.core.csrf import UNSAFE_METHODS, valid_csrf_token


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method.upper() in UNSAFE_METHODS and not valid_csrf_token(request):
            return JSONResponse(status_code=403, content={"detail": "Token CSRF ausente o inválido"})
        return await call_next(request)
