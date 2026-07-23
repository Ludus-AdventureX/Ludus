"""Request-scoped authentication dependency.

Every failure mode (missing cookie, bad token, unknown/revoked/expired
session, disabled user) raises the same 401 ``SESSION_REVOKED_OR_EXPIRED``
failure so that account and session state cannot be probed.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.config import get_auth_settings
from app.auth.sessions import resolve_active_session, touch_session
from app.auth.tokens import TokenDecodeError, decode_session_token
from app.db import get_session
from app.models import User, UserSession
from app.security.envelope import session_rejected
from app.types import UserStatus


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    user: User
    session: UserSession


async def require_authenticated_principal(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> AuthenticatedPrincipal:
    settings = get_auth_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise session_rejected()
    try:
        claims = decode_session_token(token, settings)
    except TokenDecodeError:
        raise session_rejected() from None

    session = await resolve_active_session(db, claims.session_id)
    if session is None or session.user_id != claims.user_id:
        raise session_rejected()

    user = await db.scalar(select(User).where(User.id == session.user_id))
    if user is None or user.status != UserStatus.ACTIVE:
        raise session_rejected()

    # Persist the last-seen bump immediately: read-only routes never commit,
    # and expire_on_commit=False keeps the loaded objects usable afterwards.
    await touch_session(db, session.id)
    await db.commit()
    return AuthenticatedPrincipal(user=user, session=session)
