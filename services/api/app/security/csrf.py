"""Double-submit CSRF protection for cookie-based mutations.

Contract (docs/product-plan/10-api-and-events.md, section 认证、session 与
CSRF): ``GET /api/auth/csrf`` issues a random token as both a readable
same-site cookie and a response body value; every cookie mutation must echo
the token in the CSRF header, and the server verifies the exact ``Origin``
(falling back to a same-origin ``Referer`` when Origin is absent) plus a
constant-time cookie/header comparison.
"""

from __future__ import annotations

import secrets
from urllib.parse import urlsplit

from fastapi import Request, Response

from app.auth.config import AuthSettings, get_auth_settings
from app.security.envelope import ApiFailure

_TOKEN_BYTES = 32


def _csrf_failure() -> ApiFailure:
    return ApiFailure(
        "CSRF_VALIDATION_FAILED",
        "The request is missing a valid same-origin CSRF proof. Refresh the token and retry.",
        http_status=403,
    )


def _origin_of(url: str) -> str | None:
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}".lower()


def _allowed_origins(request: Request, settings: AuthSettings) -> set[str]:
    if settings.allowed_origins:
        return {origin.rstrip("/").lower() for origin in settings.allowed_origins}
    same_origin = _origin_of(str(request.url))
    return {same_origin} if same_origin else set()


def _verify_browser_origin(request: Request, settings: AuthSettings) -> bool:
    allowed = _allowed_origins(request, settings)
    if not allowed:
        return False
    origin_header = request.headers.get("origin")
    if origin_header is not None:
        return origin_header.rstrip("/").lower() in allowed
    referer = request.headers.get("referer")
    if referer is not None:
        return _origin_of(referer) in allowed
    # Neither Origin nor Referer: not an acceptable browser mutation context.
    return False


def issue_csrf_token(response: Response, settings: AuthSettings | None = None) -> str:
    settings = settings or get_auth_settings()
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=token,
        httponly=False,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    return token


async def require_csrf(request: Request) -> None:
    """FastAPI dependency guarding every cookie-mutating endpoint."""

    settings = get_auth_settings()
    if not _verify_browser_origin(request, settings):
        raise _csrf_failure()
    cookie_token = request.cookies.get(settings.csrf_cookie_name)
    header_token = request.headers.get(settings.csrf_header_name)
    if not cookie_token or not header_token:
        raise _csrf_failure()
    if not secrets.compare_digest(cookie_token, header_token):
        raise _csrf_failure()
