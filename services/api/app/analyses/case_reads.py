"""Case-scoped read projections (CCR-20260726-READ-01).

Three GET-only routes that unlock the frontend fail-closed switches:

* ``GET /cases/{decisionCaseId}/analyses`` — run anchors for a decision case
  (the case→run resolution surface `evidenceAnchorsRouteAvailable` waits on).
  NEW canonical row adjudicated by CCR-20260726-READ-01.
* ``GET /cases/{decisionCaseId}/reports`` — report list (canonical 10-api row).
* ``GET /cases/{decisionCaseId}/reports/{reportId}`` — report detail
  (canonical 10-api row).

Error discipline mirrors ``app.analyses.routes``: every scope denial — foreign
tenant, ghost id, case/report mismatch — collapses into the uniform
``CASE_NOT_FOUND`` envelope (anti-enumeration, byte-identical copy). Reads are
safe endpoints and carry no CSRF dependency (10-api CSRF scope clarification).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import AnalysisRun, DecisionCase
from app.reports.models import ReportArtifact
from app.tenancy.context import WorkspaceContext, require_workspace_context
from app.types import AnalysisRunStatus, FormalAnalysisLevel

from .routes import case_not_found

router = APIRouter(prefix="/api/workspaces/{workspaceId}")

_REPORT_STATUSES = frozenset({"draft", "ready"})
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


def _report_summary(report: ReportArtifact) -> dict[str, Any]:
    level = (
        report.analysis_level.value
        if isinstance(report.analysis_level, FormalAnalysisLevel)
        else str(report.analysis_level)
    )
    return {
        "reportId": str(report.id),
        "decisionCaseId": str(report.decision_case_id),
        "analysisRunId": str(report.analysis_run_id),
        "analysisLevel": level,
        "type": report.type,
        "status": report.status,
        "caseVersion": report.case_version,
        "contentHash": report.content_hash,
        "originModes": [mode.value for mode in report.origin_modes],
        "publishedAt": report.published_at.isoformat() if report.published_at else None,
        "createdAt": report.created_at.isoformat(),
    }


def _report_detail(report: ReportArtifact) -> dict[str, Any]:
    data = _report_summary(report)
    data["structuredContent"] = dict(report.structured_content)
    data["validation"] = dict(report.validation)
    data["sourceJudgmentSetId"] = str(report.source_judgment_set_id)
    data["sourceDissentRecordId"] = str(report.source_dissent_record_id)
    return data


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


@router.get("/cases/{decisionCaseId}/reports")
async def list_case_reports(
    decision_case_id: UUID = Path(alias="decisionCaseId"),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=_MAX_PAGE),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List a case's report artifacts by version/status (canonical row)."""

    await _require_case(db, context.workspace_id, decision_case_id)
    query = (
        select(ReportArtifact)
        .where(
            ReportArtifact.workspace_id == context.workspace_id,
            ReportArtifact.decision_case_id == decision_case_id,
        )
        .order_by(
            ReportArtifact.case_version.desc(),
            ReportArtifact.created_at.desc(),
            ReportArtifact.id,
        )
        .limit(limit)
    )
    if status is not None:
        if status not in _REPORT_STATUSES:
            # Unknown status filters yield the honest empty page, not an
            # enumeration oracle over internal states.
            return _envelope({"decisionCaseId": str(decision_case_id), "items": []})
        query = query.where(ReportArtifact.status == status)
    rows = (await db.execute(query)).scalars().all()
    return _envelope(
        {
            "decisionCaseId": str(decision_case_id),
            "items": [_report_summary(report) for report in rows],
        }
    )


@router.get("/cases/{decisionCaseId}/reports/{reportId}")
async def get_case_report(
    decision_case_id: UUID = Path(alias="decisionCaseId"),
    report_id: UUID = Path(alias="reportId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Read one report artifact (canonical row); case mismatch is the same 404."""

    await _require_case(db, context.workspace_id, decision_case_id)
    report = (
        await db.execute(
            select(ReportArtifact).where(
                ReportArtifact.workspace_id == context.workspace_id,
                ReportArtifact.decision_case_id == decision_case_id,
                ReportArtifact.id == report_id,
            )
        )
    ).scalar_one_or_none()
    if report is None:
        raise case_not_found()
    return _envelope(_report_detail(report))
