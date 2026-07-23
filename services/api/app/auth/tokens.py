"""Short-lived JWT encoding bound to a revocable UserSession.

Plan contract (docs/product-plan/18-detailed-development-plan.md Task 3
Step 2): the JWT carries only ``sub``, ``session_id``, ``iat`` and ``exp``.
Authorization is never read from the token; every request revalidates the
referenced UserSession row and re-reads WorkspaceMembership.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

import jwt

from app.auth.config import AuthSettings, get_auth_settings


class TokenDecodeError(Exception):
    """The bearer token is malformed, expired, or has invalid claims."""


@dataclass(frozen=True)
class SessionTokenClaims:
    user_id: UUID
    session_id: UUID
    issued_at: datetime
    expires_at: datetime


def encode_session_token(
    *,
    user_id: UUID,
    session_id: UUID,
    issued_at: datetime,
    expires_at: datetime,
    settings: AuthSettings | None = None,
) -> str:
    settings = settings or get_auth_settings()
    payload = {
        "sub": str(user_id),
        "session_id": str(session_id),
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_session_token(token: str, settings: AuthSettings | None = None) -> SessionTokenClaims:
    settings = settings or get_auth_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "session_id", "iat", "exp"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenDecodeError("session token rejected") from exc
    try:
        return SessionTokenClaims(
            user_id=UUID(str(payload["sub"])),
            session_id=UUID(str(payload["session_id"])),
            issued_at=datetime.fromtimestamp(int(payload["iat"]), tz=timezone.utc),
            expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise TokenDecodeError("session token claims invalid") from exc
