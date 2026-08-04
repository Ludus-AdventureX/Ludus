"""Auth runtime configuration sourced from environment variables.

Values are non-secret development defaults; production deployments must
override at least ``AUTH_JWT_SECRET`` and ``AUTH_COOKIE_SECURE`` via the
environment (see the CONTRACT_CHANGE_REQUEST asking the Contract Lead to add
the ``AUTH_*`` placeholders to ``.env.example``).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Public, well-known default. Running with it means anyone can forge session
# tokens for any user, so startup fails closed instead of silently carrying it.
_INSECURE_DEFAULT_JWT_SECRET = "dev-insecure-jwt-secret-change-me"


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTH_", extra="ignore")

    jwt_secret: str = _INSECURE_DEFAULT_JWT_SECRET
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
    # P2-001 login rate limiting (doc 22): sliding window over minute slices,
    # enforced per client IP and per normalized account before authentication.
    login_rate_window_minutes: int = 15
    login_rate_ip_max_attempts: int = 20
    login_rate_account_max_attempts: int = 5

    @model_validator(mode="after")
    def _reject_insecure_jwt_default(self) -> "AuthSettings":
        if self.jwt_secret == _INSECURE_DEFAULT_JWT_SECRET:
            raise ValueError(
                "AUTH_JWT_SECRET must be configured; refusing to start with the "
                "public development default secret (forged-session risk)."
            )
        return self


@lru_cache(maxsize=1)
def get_auth_settings() -> AuthSettings:
    return AuthSettings()
