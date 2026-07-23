"""Auth runtime configuration sourced from environment variables.

Values are non-secret development defaults; production deployments must
override at least ``AUTH_JWT_SECRET`` and ``AUTH_COOKIE_SECURE`` via the
environment (see the CONTRACT_CHANGE_REQUEST asking the Contract Lead to add
the ``AUTH_*`` placeholders to ``.env.example``).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTH_", extra="ignore")

    jwt_secret: str = "dev-insecure-jwt-secret-change-me"
    jwt_algorithm: Literal["HS256"] = "HS256"
    session_ttl_minutes: int = 720
    session_cookie_name: str = "decision_lab_session"
    csrf_cookie_name: str = "decision_lab_csrf"
    csrf_header_name: str = "X-CSRF-Token"
    # Development default keeps the golden path working over plain HTTP;
    # production configuration must set AUTH_COOKIE_SECURE=true.
    cookie_secure: bool = False
    # Empty list means "same origin as the request URL" for CSRF checks.
    allowed_origins: list[str] = []


@lru_cache(maxsize=1)
def get_auth_settings() -> AuthSettings:
    return AuthSettings()
