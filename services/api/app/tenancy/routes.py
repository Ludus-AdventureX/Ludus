"""Workspace-scoped router mount point.

This module exposes the shared ``workspace_router`` whose single dependency is
``require_workspace_context``. Resource routers are included here so every
``/api/workspaces/{workspaceId}/...`` path is tenancy-guarded with the uniform
404 denial by construction.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.tenancy.context import require_workspace_context

workspace_router = APIRouter(
    prefix="/api/workspaces/{workspaceId}",
    dependencies=[Depends(require_workspace_context)],
    tags=["workspaces"],
)

# Resource routers are RELATIVE and must live under this tenancy guard. Keep
# these includes in the integration layer; individual modules own no global app
# mount. Import after workspace_router construction to avoid import cycles.
from app.cases.routes import router as cases_router  # noqa: E402
from app.conversations.routes import router as conversations_router  # noqa: E402
from app.dossiers.routes import router as dossiers_router  # noqa: E402
from app.reports.routes import router as reports_router  # noqa: E402
from app.simulations.routes import router as simulations_router  # noqa: E402

workspace_router.include_router(dossiers_router)
workspace_router.include_router(cases_router)
workspace_router.include_router(conversations_router)
workspace_router.include_router(reports_router)
# SIM-02A run surface (CCR-20260724-SIM-02A section 10): relative /simulations/{graphId}.
workspace_router.include_router(simulations_router)
