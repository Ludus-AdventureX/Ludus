"""Workspace invite surface (multi-guest collaboration).

OWNER-only create/list/revoke under the tenancy guard. The plaintext token is
minted here, returned exactly once and stored only as sha256; SIGN is never in
the default grant (decision accountability does not leak by default) and
MANAGE_CONNECTORS can never be granted through an invite.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Path
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.schemas import CanonicalModel
from app.db import get_session
from app.models import WorkspaceInvite
from app.security.csrf import require_csrf
from app.security.envelope import ApiFailure
from app.tenancy.context import WorkspaceContext, require_workspace_context
from app.types import WorkspaceCapability, WorkspaceRole

router = APIRouter(tags=["invites"])

_DEFAULT_CAPABILITIES = (WorkspaceCapability.CONTRIBUTE, WorkspaceCapability.REVIEW)
# SIGN may be granted explicitly; MANAGE_CONNECTORS never travels via invite.
_INVITABLE_CAPABILITIES = frozenset(
    {WorkspaceCapability.CONTRIBUTE, WorkspaceCapability.REVIEW, WorkspaceCapability.SIGN}
)
_MAX_ACTIVE_INVITES = 10
_MAX_TTL_HOURS = 24 * 7


class InviteCreateRequest(CanonicalModel):
    capabilities: list[WorkspaceCapability] | None = None
    max_uses: int = Field(default=5, ge=1, le=50)
    ttl_hours: int = Field(default=72, ge=1, le=_MAX_TTL_HOURS)


def token_hash_of(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _envelope(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


def _require_owner(context: WorkspaceContext) -> None:
    if context.role != WorkspaceRole.OWNER:
        raise ApiFailure(
            "MEMBERSHIP_CAPABILITY_REQUIRED",
            "Only the workspace owner can manage invites.",
            http_status=403,
        )


def _invite_data(invite: WorkspaceInvite, *, token: str | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "inviteId": str(invite.id),
        "workspaceId": str(invite.workspace_id),
        "capabilities": [c.value for c in invite.granted_capabilities],
        "maxUses": invite.max_uses,
        "usedCount": invite.used_count,
        "expiresAt": invite.expires_at.isoformat(),
        "revokedAt": invite.revoked_at.isoformat() if invite.revoked_at else None,
        "createdAt": invite.created_at.isoformat() if invite.created_at else None,
    }
    if token is not None:
        # The ONE place the plaintext token ever appears.
        data["token"] = token
        data["joinUrl"] = f"/join?code={token}"
    return data


@router.post("/invites", status_code=201)
async def create_invite(
    body: InviteCreateRequest,
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
    _: None = Depends(require_csrf),
) -> dict[str, Any]:
    _require_owner(context)

    requested = body.capabilities if body.capabilities is not None else list(_DEFAULT_CAPABILITIES)
    illegal = [c for c in requested if c not in _INVITABLE_CAPABILITIES]
    if illegal:
        raise ApiFailure(
            "INVITE_CAPABILITY_NOT_ALLOWED",
            "manage_connectors cannot be granted through an invite.",
            http_status=422,
            details={"illegal": [c.value for c in illegal]},
        )

    now = datetime.now(timezone.utc)
    active = await db.scalar(
        select(func.count(WorkspaceInvite.id)).where(
            WorkspaceInvite.workspace_id == context.workspace_id,
            WorkspaceInvite.revoked_at.is_(None),
            WorkspaceInvite.expires_at > now,
        )
    )
    if int(active or 0) >= _MAX_ACTIVE_INVITES:
        raise ApiFailure(
            "INVITE_LIMIT",
            "This workspace already has the maximum number of active invites.",
            http_status=409,
        )

    token = secrets.token_urlsafe(32)
    invite = WorkspaceInvite(
        workspace_id=context.workspace_id,
        created_by_user_id=context.user_id,
        token_hash=token_hash_of(token),
        granted_capabilities=list(dict.fromkeys(requested)),
        max_uses=body.max_uses,
        used_count=0,
        expires_at=now + timedelta(hours=body.ttl_hours),
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    return _envelope(_invite_data(invite, token=token))


@router.get("/invites")
async def list_invites(
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _require_owner(context)
    rows = (
        await db.execute(
            select(WorkspaceInvite)
            .where(WorkspaceInvite.workspace_id == context.workspace_id)
            .order_by(WorkspaceInvite.created_at.desc())
            .limit(50)
        )
    ).scalars()
    return _envelope({"items": [_invite_data(r) for r in rows]})


@router.post("/invites/{inviteId}/revoke")
async def revoke_invite(
    invite_id: UUID = Path(alias="inviteId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
    _: None = Depends(require_csrf),
) -> dict[str, Any]:
    _require_owner(context)
    invite = await db.scalar(
        select(WorkspaceInvite).where(
            WorkspaceInvite.workspace_id == context.workspace_id,
            WorkspaceInvite.id == invite_id,
        )
    )
    if invite is None:
        # Same uniform-404 shape the case surface uses (anti-enumeration).
        raise ApiFailure("INVITE_NOT_FOUND", "The requested invite does not exist.", http_status=404)
    if invite.revoked_at is None:
        invite.revoked_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(invite)
    return _envelope(_invite_data(invite))
