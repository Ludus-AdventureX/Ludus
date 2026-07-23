"""Workspace-scoped router mount point.

This module owns no business endpoints yet. It exposes the shared
``workspace_router`` whose single dependency is ``require_workspace_context``;
Task 4+ resource routers (subjects, cases, conversations, ...) must be
included here so that every ``/api/workspaces/{workspaceId}/...`` path is
tenancy-guarded with the uniform 404 denial by construction. QA suites can
attach probe routes to a copy of this router to exercise cross-tenant
isolation before business resources land.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.tenancy.context import require_workspace_context

workspace_router = APIRouter(
    prefix="/api/workspaces/{workspaceId}",
    dependencies=[Depends(require_workspace_context)],
    tags=["workspaces"],
)
