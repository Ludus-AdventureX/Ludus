"""PROTOTYPE guest bootstrap endpoint (guest alpha) — not a product contract.

``POST /api/auth/guest``:

- hidden from the generated OpenAPI schema (``include_in_schema=False``);
- hard-gated by ``ENABLE_GUEST_ALPHA`` — when unset/false the route answers
  the uniform 404 so its existence cannot be probed;
- CSRF-guarded exactly like login/register (double-submit + Origin);
- accepts NO caller input: no body, no userId/workspaceId, no credentials —
  every identity is generated server-side;
- with a valid guest session cookie it answers 200 with the SAME guest,
  workspace, and demo identifiers and creates nothing;
- otherwise it creates the guest user (non-loggable random password hash),
  session, isolated workspace, OWNER membership, and the demo scope in ONE
  transaction (any failure rolls the whole bootstrap back), then sets the
  HttpOnly session cookie.

Existing login/register flows are untouched.
"""

from __future__ import annotations

import os
import secrets
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.config import get_auth_settings
from app.auth.passwords import hash_password
from app.auth.sessions import create_user_session, resolve_active_session, utc_now
from app.auth.tokens import TokenDecodeError, decode_session_token, encode_session_token
from app.contracts.schemas import CanonicalModel
from app.db import get_session
from app.models import User, UserSession, Workspace, WorkspaceMembership
from app.prototype.guest_bootstrap import bootstrap_guest_demo, derive_demo_ids
from app.security.csrf import require_csrf
from app.security.envelope import ApiFailure
from app.types import UserStatus, WorkspaceMembershipStatus, WorkspaceRole

router = APIRouter(prefix="/api/auth", tags=["auth-guest-prototype"])

GUEST_ALPHA_FLAG = "ENABLE_GUEST_ALPHA"
GUEST_EMAIL_DOMAIN = "guest.invalid"
_GUEST_WORKSPACE_NAME = "Guest Workspace"


def guest_alpha_enabled() -> bool:
    return os.getenv(GUEST_ALPHA_FLAG, "").strip().lower() in {"1", "true", "yes", "on"}


def _guest_not_found() -> ApiFailure:
    """Uniform 404: a disabled prototype route must be indistinguishable
    from a route that does not exist."""

    return ApiFailure("NOT_FOUND", "Not Found", http_status=404)


class GuestBootstrapData(CanonicalModel):
    workspace_id: str
    decision_case_id: str
    graph_id: str
    graph_version_id: str
    strategy_version_id: str
    scenario_version_id: str
    score_definition_id: str
    decision_maker_profile_id: str
    decision_maker_profile_version: int
    reused: bool


class GuestBootstrapEnvelope(CanonicalModel):
    ok: Literal[True] = True
    data: GuestBootstrapData


def _is_guest(user: User) -> bool:
    return user.email.endswith(f"@{GUEST_EMAIL_DOMAIN}")


async def _resolve_guest_principal(
    request: Request, db: AsyncSession
) -> tuple[User, UserSession] | None:
    """Best-effort resolution of an existing, valid GUEST session.

    Any failure (no cookie, bad token, revoked/expired session, non-guest
    user) simply means "no reusable guest" — never an error.
    """

    settings = get_auth_settings()
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return None
    try:
        claims = decode_session_token(token, settings)
    except TokenDecodeError:
        return None
    session = await resolve_active_session(db, claims.session_id)
    if session is None or session.user_id != claims.user_id:
        return None
    user = await db.scalar(select(User).where(User.id == session.user_id))
    if user is None or user.status != UserStatus.ACTIVE or not _is_guest(user):
        return None
    return user, session


def _set_session_cookie(response: Response, token: str, expires_at) -> None:
    settings = get_auth_settings()
    max_age = max(int((expires_at - utc_now()).total_seconds()), 0)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def _envelope(workspace_id, ids, *, reused: bool) -> GuestBootstrapEnvelope:
    return GuestBootstrapEnvelope(
        data=GuestBootstrapData(
            workspace_id=str(workspace_id),
            decision_case_id=str(ids.case_id),
            graph_id=str(ids.graph_id),
            graph_version_id=str(ids.graph_version_id),
            strategy_version_id=str(ids.strategy_version_id),
            scenario_version_id=str(ids.scenario_version_id),
            score_definition_id=str(ids.score_definition_id),
            decision_maker_profile_id=str(ids.profile_id),
            decision_maker_profile_version=ids.profile_version,
            reused=reused,
        )
    )


@router.post(
    "/guest",
    response_model=GuestBootstrapEnvelope,
    status_code=201,
    include_in_schema=False,
    dependencies=[Depends(require_csrf)],
)
async def create_guest(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> GuestBootstrapEnvelope:
    if not guest_alpha_enabled():
        raise _guest_not_found()

    # Reuse path: a valid guest session answers its own frozen identifiers.
    existing = await _resolve_guest_principal(request, db)
    if existing is not None:
        user, _session = existing
        membership = await db.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.user_id == user.id,
                WorkspaceMembership.status == WorkspaceMembershipStatus.ACTIVE,
            )
        )
        if membership is not None:
            response.status_code = 200
            return _envelope(
                membership.workspace_id, derive_demo_ids(user.id), reused=True
            )
        # A guest without a workspace is a broken bootstrap; fall through and
        # mint a fresh guest instead of resurrecting the torso.

    # Create path: one transaction for user + session + workspace + membership
    # + demo scope; any failure rolls everything back together.
    try:
        user = User(
            id=uuid4(),
            email=f"guest-{uuid4()}@{GUEST_EMAIL_DOMAIN}",
            # Non-loggable: random throwaway secret, hashed and discarded.
            password_hash=hash_password(secrets.token_urlsafe(32)),
        )
        db.add(user)
        await db.flush()

        workspace = Workspace(
            id=uuid4(),
            name=_GUEST_WORKSPACE_NAME,
            created_by_user_id=user.id,
        )
        db.add(workspace)
        await db.flush()
        db.add(
            WorkspaceMembership(
                workspace_id=workspace.id,
                user_id=user.id,
                role=WorkspaceRole.OWNER,
                capabilities=[],
            )
        )
        session = await create_user_session(db, user.id)
        ids = await bootstrap_guest_demo(db, workspace_id=workspace.id, user_id=user.id)
        envelope = _envelope(workspace.id, ids, reused=False)
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        raise ApiFailure(
            "GUEST_BOOTSTRAP_FAILED",
            "Guest bootstrap failed; nothing was created.",
            http_status=500,
            retryable=True,
        ) from None
    except Exception:
        await db.rollback()
        raise

    token = encode_session_token(
        user_id=user.id,
        session_id=session.id,
        issued_at=utc_now(),
        expires_at=session.expires_at,
    )
    _set_session_cookie(response, token, session.expires_at)
    return envelope
