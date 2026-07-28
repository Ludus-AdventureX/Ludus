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

# Resource routers are RELATIVE and must live under this tenancy guard. Keep
# these includes in the integration layer; individual modules own no global app
# mount. Import after workspace_router construction to avoid import cycles.
# (Union of the release-integration mounts @ c150d72 and the READ-01 wave:
# Task 4/5 resource routers + release reports/exports + SIM-02A runs + the
# READ-01 graph-version reads and case→graph anchor resolution.)
from app.cases.routes import router as cases_router  # noqa: E402
from app.conversations.routes import router as conversations_router  # noqa: E402
from app.decisions.routes import router as decisions_router  # noqa: E402
from app.dossiers.routes import router as dossiers_router  # noqa: E402
from app.reports.routes import router as reports_router  # noqa: E402
from app.simulations.graph_reads import (  # noqa: E402
    case_anchor_router as simulation_case_anchor_router,
    router as graph_reads_router,
)
from app.simulations.routes import router as simulations_router  # noqa: E402

workspace_router.include_router(dossiers_router)
workspace_router.include_router(cases_router)
workspace_router.include_router(conversations_router)
workspace_router.include_router(reports_router)
# Release lane (1e5ec39): signoff/decision record surface; DecisionRecord is
# append-only and only the authorized human sign endpoint creates it.
workspace_router.include_router(decisions_router)
# SIM-02A run surface (CCR-20260724-SIM-02A section 10): relative /simulations/{graphId}.
workspace_router.include_router(simulations_router)
# Sandbox read projections (CCR-20260726-READ-01): graph-version reads under
# the same relative /simulations/{graphId} prefix, plus the case→graph anchor
# resolution the sandbox workspace waits on.
workspace_router.include_router(graph_reads_router)
workspace_router.include_router(simulation_case_anchor_router)
# Multi-guest collaboration lane: OWNER-only invite create/list/revoke.
# (Redemption lives on the auth router - it must work before membership.)
from app.tenancy.invites import router as invites_router  # noqa: E402

workspace_router.include_router(invites_router)
# Data rights (interlude B): OWNER export + confirmed purge.
from app.tenancy.data_rights import router as data_rights_router  # noqa: E402

workspace_router.include_router(data_rights_router)
