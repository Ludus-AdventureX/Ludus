"""Workspace tenancy context: the only doorway into workspace-scoped routes.

Contract (docs/product-plan/26 section 8 and AGENTS.md section 5):

- roles persist as ``owner | member`` only;
- ``owner`` projects the full ``contribute/review/sign/manage_connectors``
  capability set, ``member`` projects exactly the granted subset;
- authorization is re-read from WorkspaceMembership on every request and is
  never trusted from the JWT;
- any denial (unknown workspace, foreign workspace, inactive membership or
  workspace) is a uniform 404 that leaks nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import AuthenticatedPrincipal, require_authenticated_principal
from app.db import get_session
from app.models import Workspace, WorkspaceMembership
from app.security.envelope import ApiFailure, workspace_not_found
from app.types import (
    WorkspaceCapability,
    WorkspaceMembershipStatus,
    WorkspaceRole,
    WorkspaceStatus,
)

ALL_CAPABILITIES: frozenset[WorkspaceCapability] = frozenset(WorkspaceCapability)


@dataclass(frozen=True)
class WorkspaceContext:
    user_id: UUID
    workspace_id: UUID
    role: WorkspaceRole
    capabilities: frozenset[WorkspaceCapability]

    def has_capability(self, capability: WorkspaceCapability) -> bool:
        return capability in self.capabilities


def project_capabilities(
    role: WorkspaceRole,
    granted: list[WorkspaceCapability],
) -> frozenset[WorkspaceCapability]:
    if role == WorkspaceRole.OWNER:
        return ALL_CAPABILITIES
    return frozenset(granted)


async def require_workspace_context(
    workspace_id: UUID = Path(alias="workspaceId"),
    principal: AuthenticatedPrincipal = Depends(require_authenticated_principal),
    db: AsyncSession = Depends(get_session),
) -> WorkspaceContext:
    membership = await db.scalar(
        select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == principal.user.id,
            WorkspaceMembership.status == WorkspaceMembershipStatus.ACTIVE,
        )
    )
    if membership is None:
        raise workspace_not_found()

    workspace = await db.scalar(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.status == WorkspaceStatus.ACTIVE,
        )
    )
    if workspace is None:
        raise workspace_not_found()

    return WorkspaceContext(
        user_id=principal.user.id,
        workspace_id=workspace_id,
        role=membership.role,
        capabilities=project_capabilities(membership.role, membership.capabilities),
    )


def require_capability(capability: WorkspaceCapability):
    """Dependency factory: 403 when the projected capability set lacks one."""

    async def _check(
        context: WorkspaceContext = Depends(require_workspace_context),
    ) -> WorkspaceContext:
        if not context.has_capability(capability):
            raise ApiFailure(
                "MEMBERSHIP_CAPABILITY_REQUIRED",
                "The current membership lacks the capability required for this action.",
                http_status=403,
                details={"requiredCapability": capability.value},
            )
        return context

    return _check
