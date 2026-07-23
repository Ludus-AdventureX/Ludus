"""UserSession lifecycle: creation, atomic revocation, active resolution."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.config import AuthSettings, get_auth_settings
from app.models import UserSession


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def create_user_session(
    db: AsyncSession,
    user_id: UUID,
    *,
    settings: AuthSettings | None = None,
) -> UserSession:
    settings = settings or get_auth_settings()
    now = utc_now()
    session = UserSession(
        user_id=user_id,
        expires_at=now + timedelta(minutes=settings.session_ttl_minutes),
        last_seen_at=now,
    )
    db.add(session)
    await db.flush()
    return session


async def revoke_user_session(db: AsyncSession, session_id: UUID) -> bool:
    """Atomically set ``revoked_at``; idempotent for already-revoked rows."""

    result = await db.execute(
        update(UserSession)
        .where(UserSession.id == session_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=utc_now())
    )
    return result.rowcount > 0


async def resolve_active_session(db: AsyncSession, session_id: UUID) -> UserSession | None:
    """Return the session only if it exists, is unrevoked, and is unexpired."""

    session = await db.scalar(select(UserSession).where(UserSession.id == session_id))
    if session is None:
        return None
    if session.revoked_at is not None:
        return None
    if session.expires_at <= utc_now():
        return None
    return session


async def touch_session(db: AsyncSession, session_id: UUID) -> None:
    """Best-effort last-seen bump; never widens session validity."""

    await db.execute(
        update(UserSession)
        .where(UserSession.id == session_id)
        .values(last_seen_at=utc_now())
    )
