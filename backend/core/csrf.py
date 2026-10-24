import hmac
import secrets

from fastapi import Request

CSRF_SESSION_KEY = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def ensure_csrf_token(request: Request) -> str:
    token = request.session.get(CSRF_SESSION_KEY)
    if not isinstance(token, str) or not token:
        token = new_csrf_token()
        request.session[CSRF_SESSION_KEY] = token
    return token


def rotate_csrf_token(request: Request) -> str:
    token = new_csrf_token()
    request.session[CSRF_SESSION_KEY] = token
    return token


def valid_csrf_token(request: Request) -> bool:
    session_token = request.session.get(CSRF_SESSION_KEY)
    supplied_token = request.headers.get(CSRF_HEADER_NAME)
    return (
        isinstance(session_token, str)
        and bool(session_token)
        and isinstance(supplied_token, str)
        and bool(supplied_token)
        and hmac.compare_digest(session_token, supplied_token)
    )
