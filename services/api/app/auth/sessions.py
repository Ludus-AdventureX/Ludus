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


# P0 issues exactly one cookie token per UserSession, at creation time, and
# token_version starts at 1 with no re-issue flow. The JWT claim set is
# contract-locked to {sub, session_id, iat, exp}, so the version cannot ride
# in the token itself: any bump of token_version is an administrative
# invalidation and must reject every token minted for the session.
ISSUED_TOKEN_VERSION = 1


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
        token_version=ISSUED_TOKEN_VERSION,
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
    """Return the session only if unrevoked, unexpired, and version-current."""

    session = await db.scalar(select(UserSession).where(UserSession.id == session_id))
    if session is None:
        return None
    if session.revoked_at is not None:
        return None
    if session.expires_at <= utc_now():
        return None
    if session.token_version != ISSUED_TOKEN_VERSION:
        # Administrative token_version bump: outstanding tokens die before exp.
        return None
    return session


async def touch_session(db: AsyncSession, session_id: UUID) -> None:
    """Best-effort last-seen bump; never widens session validity."""

    await db.execute(
        update(UserSession)
        .where(UserSession.id == session_id)
        .values(last_seen_at=utc_now())
    )
