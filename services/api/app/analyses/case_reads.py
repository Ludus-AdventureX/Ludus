"""Case-scoped read projections (CCR-20260726-READ-01).

ONE GET-only route that unlocks the evidence-anchors fail-closed switch:

* ``GET /cases/{decisionCaseId}/analyses`` — run anchors for a decision case
  (the case→run resolution surface `evidenceAnchorsRouteAvailable` waits on).
  NEW canonical row adjudicated by CCR-20260726-READ-01.

The case reports list/detail rows land through the release-integration lane's
``app.reports.routes`` (c150d72) — this module deliberately does NOT duplicate
that surface (reconcile adjudication recorded in the CCR).

Error discipline mirrors ``app.analyses.routes``: every scope denial — foreign
tenant, ghost id — collapses into the uniform ``CASE_NOT_FOUND`` envelope
(anti-enumeration, byte-identical copy). Reads are safe endpoints and carry no
CSRF dependency (10-api CSRF scope clarification).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import AnalysisRun, DecisionCase
from app.tenancy.context import WorkspaceContext, require_workspace_context
from app.types import AnalysisRunStatus, FormalAnalysisLevel

from .routes import case_not_found

router = APIRouter(prefix="/api/workspaces/{workspaceId}")

_MAX_PAGE = 200


async def _require_case(
    db: AsyncSession, workspace_id: UUID, decision_case_id: UUID
) -> DecisionCase:
    """Load the case inside the tenant scope or collapse to the uniform 404."""

    case = (
        await db.execute(
            select(DecisionCase).where(
                DecisionCase.workspace_id == workspace_id,
                DecisionCase.decision_case_id == decision_case_id,
            )
        )
    ).scalar_one_or_none()
    if case is None:
        raise case_not_found()
    return case


def _envelope(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


def _run_anchor(run: AnalysisRun) -> dict[str, Any]:
    """Anchor projection ONLY: enough to key the mounted run-scoped reads.

    Deliberately no manifest/stage/progress detail here — the full status
    projection stays on ``GET /analyses/{analysisRunId}``.
    """

    level = (
        run.analysis_level.value
        if isinstance(run.analysis_level, FormalAnalysisLevel)
        else str(run.analysis_level)
    )
    return {
        "analysisRunId": str(run.analysis_run_id),
        "decisionCaseId": str(run.decision_case_id),
        "charterId": str(run.charter_id),
        "analysisLevel": level,
        "status": AnalysisRunStatus(run.status).value,
        "caseVersion": run.case_version,
        "createdAt": run.created_at.isoformat(),
        "completedAt": run.completed_at.isoformat() if run.completed_at else None,
    }


@router.get("/cases/{decisionCaseId}/analyses")
async def list_case_analysis_runs(
    decision_case_id: UUID = Path(alias="decisionCaseId"),
    limit: int = Query(default=50, ge=1, le=_MAX_PAGE),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Run-anchor list for one decision case (CCR-20260726-READ-01 §1)."""

    await _require_case(db, context.workspace_id, decision_case_id)
    rows = (
        (
            await db.execute(
                select(AnalysisRun)
                .where(
                    AnalysisRun.workspace_id == context.workspace_id,
                    AnalysisRun.decision_case_id == decision_case_id,
                )
                .order_by(AnalysisRun.created_at.desc(), AnalysisRun.analysis_run_id)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return _envelope(
        {
            "decisionCaseId": str(decision_case_id),
            "items": [_run_anchor(run) for run in rows],
        }
    )
