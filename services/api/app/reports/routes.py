
"""Report and export read surface.

ReportArtifact rows are produced by the internal report publisher only; this
router deliberately exposes no generic client-side "create report" endpoint.
Every read is workspace/case scoped and every export mutation is CSRF guarded.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse, Response
from pydantic import Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.analyses.models import AnalysisEvent, ResearchPacket
from app.analyses.synthesis import (
    ExportNotAllowed,
    ReportPublicationBlocked,
    SynthesisError,
    create_export_artifact,
)
from app.contracts.schemas import CanonicalModel
from app.db import get_session
from app.models import AnalysisRun, DecisionCase
from app.reports.models import ExportArtifact, ReportArtifact
from app.security.csrf import require_csrf
from app.security.envelope import ApiFailure
from app.simulations.factor_sandbox import edges_from_influences, factors_from_packets, simulate
from app.tenancy.context import WorkspaceContext, require_workspace_context
from app.types import OriginMode

router = APIRouter(tags=["reports"])


class ExportCreateRequest(CanonicalModel):
    type: Literal["html", "pdf"]


class SandboxPreviewRequest(CanonicalModel):
    # Layer-1 what-if inputs: user-edited factor strengths in [0,1] keyed by
    # factor id. Empty = baseline. Anchors only; the factor graph itself is
    # server-derived from the case's latest analysis (never client-supplied).
    node_overrides: dict[str, float] = Field(default_factory=dict)


class ExportRetryRequest(CanonicalModel):
    renderer_version: str | None = Field(default=None, max_length=64)


def _envelope(data: Any, event_id: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": True, "data": data}
    if event_id:
        payload["eventId"] = event_id
    return payload


def _not_found() -> ApiFailure:
    # Combination fix (READ-01 reconcile, disclosed): the c150d72 version called
    # workspace_not_found("CASE_NOT_FOUND", ...) but that helper takes ZERO
    # arguments - every missing/foreign-case path raised TypeError (500) and no
    # release-lane test covered the 404 branch; the READ-01 uniform-404 matrix
    # caught it. Copy matches the analyses-domain case_not_found() byte-for-byte
    # so the case-scoped anti-enumeration surface stays ONE copy.
    return ApiFailure(
        "CASE_NOT_FOUND",
        "Case material not found.",
        http_status=404,
    )


def _report_blocked(exc: Exception) -> ApiFailure:
    return ApiFailure(
        "REPORT_PUBLICATION_BLOCKED",
        str(exc),
        http_status=409,
    )


async def _case_exists(db: AsyncSession, context: WorkspaceContext, decision_case_id: UUID) -> None:
    exists = await db.scalar(
        select(DecisionCase.decision_case_id).where(
            DecisionCase.workspace_id == context.workspace_id,
            DecisionCase.decision_case_id == decision_case_id,
        )
    )
    if exists is None:
        raise _not_found()


async def _report_for_case(
    db: AsyncSession,
    context: WorkspaceContext,
    decision_case_id: UUID,
    report_id: UUID,
) -> ReportArtifact:
    report = await db.scalar(
        select(ReportArtifact).where(
            ReportArtifact.workspace_id == context.workspace_id,
            ReportArtifact.decision_case_id == decision_case_id,
            ReportArtifact.id == report_id,
        )
    )
    if report is None:
        raise _not_found()
    return report


async def _export_for_workspace(
    db: AsyncSession,
    context: WorkspaceContext,
    export_artifact_id: UUID,
) -> ExportArtifact:
    artifact = await db.scalar(
        select(ExportArtifact).where(
            ExportArtifact.workspace_id == context.workspace_id,
            ExportArtifact.id == export_artifact_id,
        )
    )
    if artifact is None:
        raise _not_found()
    return artifact


async def _export_ids(db: AsyncSession, context: WorkspaceContext, report_id: UUID) -> list[str]:
    rows = (
        await db.execute(
            select(ExportArtifact.id)
            .where(
                ExportArtifact.workspace_id == context.workspace_id,
                ExportArtifact.report_artifact_id == report_id,
            )
            .order_by(ExportArtifact.created_at, ExportArtifact.id)
        )
    ).scalars()
    return [str(row) for row in rows]


def _origin_values(values: Any) -> list[str]:
    return [getattr(value, "value", str(value)) for value in (values or [])]


async def _report_data(
    db: AsyncSession,
    context: WorkspaceContext,
    report: ReportArtifact,
) -> dict[str, Any]:
    return {
        "id": str(report.id),
        "workspaceId": str(report.workspace_id),
        "analysisRunId": str(report.analysis_run_id),
        "sourceJudgmentSetId": str(report.source_judgment_set_id),
        "sourceDissentRecordId": str(report.source_dissent_record_id),
        "decisionCaseId": str(report.decision_case_id),
        "caseVersion": report.case_version,
        "analysisLevel": getattr(report.analysis_level, "value", str(report.analysis_level)),
        "type": report.type,
        "status": report.status,
        "structuredContent": report.structured_content,
        "originModes": _origin_values(report.origin_modes),
        "exportArtifactIds": await _export_ids(db, context, report.id),
        "createdAt": report.created_at.isoformat(),
        "validation": report.validation,
        "publishedAt": report.published_at.isoformat() if report.published_at else None,
    }


def _export_data(export: ExportArtifact) -> dict[str, Any]:
    return {
        "id": str(export.id),
        "workspaceId": str(export.workspace_id),
        "reportArtifactId": str(export.report_artifact_id),
        "analysisRunId": str(export.analysis_run_id),
        "decisionCaseId": str(export.decision_case_id),
        "caseVersion": export.case_version,
        "type": export.type,
        "status": export.status,
        "storageProvider": export.storage_provider,
        "storagePath": export.storage_path,
        "sha256": export.sha256,
        "byteSize": export.byte_size,
        "mediaType": export.media_type,
        "rendererVersion": export.renderer_version,
        "originModes": _origin_values(export.origin_modes),
        "errorCode": export.error_code,
        "createdAt": export.created_at.isoformat(),
    }


def _gate_status(report: ReportArtifact) -> str:
    validation = report.validation or {}
    return "passed" if validation.get("passed") is True else "blocked"


@router.get("/cases/{decisionCaseId}/reports")
async def list_case_reports(
    decision_case_id: UUID = Path(alias="decisionCaseId"),
    status: Literal["draft", "ready"] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _case_exists(db, context, decision_case_id)
    query = select(ReportArtifact).where(
        ReportArtifact.workspace_id == context.workspace_id,
        ReportArtifact.decision_case_id == decision_case_id,
    )
    if status is not None:
        query = query.where(ReportArtifact.status == status)
    reports = (
        await db.execute(query.order_by(ReportArtifact.created_at.desc()).limit(limit))
    ).scalars()
    items = [await _report_data(db, context, report) for report in reports]
    return _envelope({"items": items, "nextCursor": None})


@router.get("/cases/{decisionCaseId}/reports/{reportId}")
async def read_case_report(
    decision_case_id: UUID = Path(alias="decisionCaseId"),
    report_id: UUID = Path(alias="reportId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    report = await _report_for_case(db, context, decision_case_id, report_id)
    return _envelope(await _report_data(db, context, report))


@router.post(
    "/cases/{decisionCaseId}/reports/{reportId}/exports",
    status_code=202,
    dependencies=[Depends(require_csrf)],
)
async def create_report_export(
    body: ExportCreateRequest,
    decision_case_id: UUID = Path(alias="decisionCaseId"),
    report_id: UUID = Path(alias="reportId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> JSONResponse:
    report = await _report_for_case(db, context, decision_case_id, report_id)
    try:
        export_id = await create_export_artifact(
            db,
            workspace_id=context.workspace_id,
            report_artifact_id=report.id,
            export_type=body.type,
            renderer_version="ludus-report-renderer/0.1.0",
            gate_status=_gate_status(report),
            origin_modes=tuple(report.origin_modes or (OriginMode.LIVE,)),
        )
        await db.commit()
    except (ExportNotAllowed, ReportPublicationBlocked, SynthesisError) as exc:
        await db.rollback()
        raise _report_blocked(exc) from exc
    artifact = await _export_for_workspace(db, context, export_id)
    return JSONResponse(status_code=202, content=_envelope(_export_data(artifact)))


@router.get("/exports/{exportArtifactId}")
async def read_export_artifact(
    export_artifact_id: UUID = Path(alias="exportArtifactId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return _envelope(_export_data(await _export_for_workspace(db, context, export_artifact_id)))


@router.get("/exports/{exportArtifactId}/content")
async def read_export_content(
    export_artifact_id: UUID = Path(alias="exportArtifactId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> Response:
    artifact = await _export_for_workspace(db, context, export_artifact_id)
    if artifact.status != "ready" or not artifact.storage_path:
        raise ApiFailure(
            "EXPORT_CONTENT_NOT_READY",
            "The export content is not ready for download.",
            http_status=409,
        )
    # The renderer/storage worker is outside this route. Avoid accepting or
    # resolving arbitrary client-visible paths here; until the storage service
    # attaches a workspace-scoped reader, fail closed rather than leaking files.
    raise ApiFailure(
        "EXPORT_CONTENT_UNAVAILABLE",
        "The export storage reader is not configured for this artifact.",
        http_status=409,
    )


@router.post(
    "/exports/{exportArtifactId}/retry",
    dependencies=[Depends(require_csrf)],
)
async def retry_export_artifact(
    body: ExportRetryRequest,
    export_artifact_id: UUID = Path(alias="exportArtifactId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    artifact = await _export_for_workspace(db, context, export_artifact_id)
    if artifact.status != "failed":
        raise ApiFailure(
            "EXPORT_RETRY_NOT_ALLOWED",
            "Only failed exports can be retried.",
            http_status=409,
        )
    await db.execute(
        update(ExportArtifact)
        .where(
            ExportArtifact.workspace_id == context.workspace_id,
            ExportArtifact.id == export_artifact_id,
            ExportArtifact.status == "failed",
        )
        .values(
            status="pending",
            error_code=None,
            renderer_version=body.renderer_version or artifact.renderer_version,
        )
    )
    await db.commit()
    refreshed = await _export_for_workspace(db, context, export_artifact_id)
    return _envelope(_export_data(refreshed))

async def _latest_run_packets(
    db: AsyncSession, context: WorkspaceContext, decision_case_id: UUID
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(packets, influences) from the case's most recent analysis run.

    The sandbox is a what-if calculator, so it seeds from whatever factors the
    latest run produced - a blocked run's factors are just as steerable. The
    factor->factor influence edges ride the retrieving stage-completed event
    (deterministically admitted by the worker, never fabricated here).
    """

    run_id = await db.scalar(
        select(AnalysisRun.analysis_run_id)
        .where(
            AnalysisRun.workspace_id == context.workspace_id,
            AnalysisRun.decision_case_id == decision_case_id,
        )
        .order_by(AnalysisRun.created_at.desc())
        .limit(1)
    )
    if run_id is None:
        return [], []
    rows = (
        await db.execute(
            select(ResearchPacket)
            .where(
                ResearchPacket.workspace_id == context.workspace_id,
                ResearchPacket.analysis_run_id == run_id,
            )
            .order_by(ResearchPacket.created_at, ResearchPacket.id)
        )
    ).scalars()
    packets = [
        {
            "factor": p.factor,
            "conclusion": p.conclusion,
            "direction": p.direction,
            "claim_support_score": p.claim_support_score,
        }
        for p in rows
    ]
    influences: list[dict[str, Any]] = []
    event_payloads = (
        await db.execute(
            select(AnalysisEvent.payload)
            .where(
                AnalysisEvent.workspace_id == context.workspace_id,
                AnalysisEvent.analysis_run_id == run_id,
                AnalysisEvent.type == "analysis.stage.completed",
            )
            .order_by(AnalysisEvent.sequence.desc())
        )
    ).scalars()
    for payload in event_payloads:
        if isinstance(payload, dict) and payload.get("stage") == "retrieving":
            raw = payload.get("influences")
            if isinstance(raw, list):
                influences = [e for e in raw if isinstance(e, dict)]
            break
    return packets, influences


@router.get("/cases/{decisionCaseId}/sandbox")
async def get_factor_sandbox_baseline(
    decision_case_id: UUID = Path(alias="decisionCaseId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Baseline what-if state: the case's factors at their analysed strength."""

    await _case_exists(db, context, decision_case_id)
    packets, influences = await _latest_run_packets(db, context, decision_case_id)
    factors = factors_from_packets(packets)
    if not factors:
        return _envelope({"available": False, "factors": [], "topDrivers": []})
    result = simulate(factors, edges=edges_from_influences(influences, factors))
    result["available"] = True
    return _envelope(result)


@router.post("/cases/{decisionCaseId}/sandbox/preview")
async def factor_sandbox_preview(
    body: SandboxPreviewRequest,
    decision_case_id: UUID = Path(alias="decisionCaseId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
    _: None = Depends(require_csrf),
) -> dict[str, Any]:
    """Layer-1 deterministic re-propagation under user factor overrides.

    Pure compute over server-derived factors - no persistence, instantly
    reproducible. Deep re-analysis (Layer 3) is a separate analysis run the
    client launches; this endpoint never fabricates a live model verdict.
    """

    await _case_exists(db, context, decision_case_id)
    packets, influences = await _latest_run_packets(db, context, decision_case_id)
    factors = factors_from_packets(packets)
    if not factors:
        return _envelope({"available": False, "factors": [], "topDrivers": []})
    result = simulate(factors, body.node_overrides, edges=edges_from_influences(influences, factors))
    result["available"] = True
    return _envelope(result)

