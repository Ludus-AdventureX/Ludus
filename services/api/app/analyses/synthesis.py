"""Formal output synthesis and report persistence (Task 10 Step 6, case_api_data).

Level discipline (06 报告对象 判别约束, enforced server-side, never by hidden
frontend buttons):

* ``focused`` produces a ``FocusedResearchResult`` inside a ``brief``
  ReportArtifact — and NOTHING else: no StrategicLensArtifact, no PDF/HTML
  ExportArtifact, no formal simulation. A focused run that tries to persist a
  lens is rejected before the lens repository is ever reached.
* ``full`` produces a ``StructuredReport`` inside a ``detailed``
  ReportArtifact; its ``lensArtifactIds`` must reference exactly the five
  ready artifacts of the same Workspace/Case/Run/Charter (audited by
  ``app.analyses.quality_gate.audit_full_run_lens_set``); body text can never
  substitute those references. Only full reports may create ExportArtifacts.

Report rows follow the lens-artifact persistence discipline: the worker is
the only writer, identical content replays the existing row (same hash),
different content against an existing row is a conflict that PRESERVES the
original, and a ``ready`` row can never be updated or deleted — rejected here
(repository layer) and by the database trigger from this batch's migration.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Final, Mapping, Sequence
from uuid import UUID, uuid4

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalysisRun
from app.reports.models import ExportArtifact, ReportArtifact
from app.reports.schemas import FocusedResearchResult, StructuredReport
from app.types import AnalysisRunStatus, FormalAnalysisLevel, OriginMode

# --- stable error surface (no invented wire codes; service-level guards) -----


class SynthesisError(RuntimeError):
    """Base class; carries the canonical reason code."""

    code = "synthesis_error"


class FocusedLensPersistenceRejected(SynthesisError):
    """A focused run tried to persist a strategic lens artifact."""

    code = "focused_lens_persistence_rejected"


class ReportLevelMismatch(SynthesisError):
    """Content type does not match the run's analysis level."""

    code = "report_level_mismatch"


class ReportArtifactConflict(SynthesisError):
    """Same run already holds a report with different content (original kept)."""

    code = "report_artifact_conflict"


class ReportArtifactImmutable(SynthesisError):
    """UPDATE/DELETE attempted on a ready report row (repository layer)."""

    code = "report_artifact_immutable"


class ReportPublicationBlocked(SynthesisError):
    """Publication attempted while the Run is not ready (canonical
    ``REPORT_PUBLICATION_BLOCKED`` path, 10-api error table)."""

    code = "report_publication_blocked"


class ExportNotAllowed(SynthesisError):
    """HTML/PDF export attempted outside the allowed state (canonical
    ``EXPORT_NOT_ALLOWED`` path: focused level, non-ready run, or a
    quality-gate blocked run)."""

    code = "export_not_allowed"


class SimulationNotAllowed(SynthesisError):
    """Formal simulation requested for a run whose gate is blocked."""

    code = "simulation_not_allowed"


REPORT_SCHEMA_VERSION: Final[str] = "report-1.0.0"


def canonical_report_hash(content: Mapping[str, Any]) -> str:
    """Deterministic sha256 over the canonical JSON document."""

    normalized = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- level guards -------------------------------------------------------------


def ensure_lens_persistence_allowed(analysis_level: FormalAnalysisLevel | str) -> None:
    """Reject lens persistence for focused runs BEFORE the lens repository.

    The lens repository itself is level-agnostic by contract; the pipeline is
    the layer that knows focused runs must never own lens artifacts.
    """

    level = FormalAnalysisLevel(analysis_level)
    if level is not FormalAnalysisLevel.FULL:
        raise FocusedLensPersistenceRejected(
            "focused runs never persist strategic lens artifacts"
        )


def ensure_simulation_allowed(gate_status: str) -> None:
    """Formal simulation is disabled whenever the gate blocked the run."""

    if gate_status != "passed":
        raise SimulationNotAllowed("formal simulation is disabled on a blocked run")


def report_type_for_level(analysis_level: FormalAnalysisLevel) -> str:
    return "brief" if analysis_level is FormalAnalysisLevel.FOCUSED else "detailed"


def validate_content_for_level(
    analysis_level: FormalAnalysisLevel, content: Mapping[str, Any]
) -> FocusedResearchResult | StructuredReport:
    """Parse the structured content against the level's canonical schema."""

    if analysis_level is FormalAnalysisLevel.FOCUSED:
        parsed: FocusedResearchResult | StructuredReport = (
            FocusedResearchResult.model_validate(content)
        )
        forbidden = {"lensArtifactIds", "simulationSeeds"} & set(content)
        if forbidden:
            raise ReportLevelMismatch(
                "focused output must not carry " + ", ".join(sorted(forbidden))
            )
        return parsed
    return StructuredReport.model_validate(content)


# --- report persistence (worker is the only writer) ---------------------------


async def _load_run(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    decision_case_id: UUID,
    analysis_run_id: UUID,
) -> Any:
    row = (
        await session.execute(
            select(AnalysisRun).where(
                AnalysisRun.workspace_id == workspace_id,
                AnalysisRun.decision_case_id == decision_case_id,
                AnalysisRun.analysis_run_id == analysis_run_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise SynthesisError("analysis run not found")
    return row


async def persist_report_artifact(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    decision_case_id: UUID,
    analysis_run_id: UUID,
    source_judgment_set_id: UUID,
    source_dissent_record_id: UUID,
    case_version: int,
    content: Mapping[str, Any],
    validation: Mapping[str, Any],
    origin_modes: Sequence[OriginMode] = (OriginMode.LIVE,),
) -> ReportArtifact:
    """Persist one report artifact for the run, idempotently.

    * content is validated against the level's canonical schema first;
    * same run + same canonical hash -> the existing row is returned as-is;
    * same run + different hash -> :class:`ReportArtifactConflict`, the
      original row is preserved untouched.
    """

    run = await _load_run(
        session,
        workspace_id=workspace_id,
        decision_case_id=decision_case_id,
        analysis_run_id=analysis_run_id,
    )
    level = FormalAnalysisLevel(run.analysis_level)
    parsed = validate_content_for_level(level, content)
    document = parsed.model_dump(by_alias=True, mode="json")
    content_hash = canonical_report_hash(document)

    existing = (
        await session.execute(
            select(ReportArtifact).where(
                ReportArtifact.workspace_id == workspace_id,
                ReportArtifact.analysis_run_id == analysis_run_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.content_hash == content_hash:
            return existing  # idempotent replay of the original row
        raise ReportArtifactConflict(
            "a report with different content already exists for this run"
        )

    row_id = uuid4()
    await session.execute(
        insert(ReportArtifact).values(
            id=row_id,
            workspace_id=workspace_id,
            analysis_run_id=analysis_run_id,
            source_judgment_set_id=source_judgment_set_id,
            source_dissent_record_id=source_dissent_record_id,
            decision_case_id=decision_case_id,
            case_version=case_version,
            analysis_level=level,
            type=report_type_for_level(level),
            status="draft",
            structured_content=document,
            content_hash=content_hash,
            origin_modes=list(dict.fromkeys(origin_modes)),
            validation=dict(validation),
        )
    )
    created = (
        await session.execute(
            select(ReportArtifact).where(
                ReportArtifact.workspace_id == workspace_id, ReportArtifact.id == row_id
            )
        )
    ).scalar_one()
    return created


async def publish_report_artifact(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    report_artifact_id: UUID,
    gate_status: str,
) -> None:
    """Flip a draft report to ready; only legal on a ready Run with a passed gate."""

    report = (
        await session.execute(
            select(ReportArtifact).where(
                ReportArtifact.workspace_id == workspace_id,
                ReportArtifact.id == report_artifact_id,
            )
        )
    ).scalar_one_or_none()
    if report is None:
        raise SynthesisError("report artifact not found")
    if gate_status != "passed":
        raise ReportPublicationBlocked("quality gate blocked this run")
    run = (
        await session.execute(
            select(AnalysisRun.status).where(
                AnalysisRun.workspace_id == workspace_id,
                AnalysisRun.analysis_run_id == report.analysis_run_id,
            )
        )
    ).scalar_one()
    if AnalysisRunStatus(run) is not AnalysisRunStatus.READY:
        raise ReportPublicationBlocked("run is not ready; publication is blocked")
    if report.status == "ready":
        return  # replaying a publication is not an error
    await session.execute(
        update(ReportArtifact)
        .where(
            ReportArtifact.workspace_id == workspace_id,
            ReportArtifact.id == report_artifact_id,
            ReportArtifact.status == "draft",
        )
        .values(status="ready", published_at=datetime.now(timezone.utc))
    )


async def update_report_artifact(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    report_artifact_id: UUID,
    values: Mapping[str, Any],
) -> None:
    """Repository-layer mutation guard: ready rows are immutable."""

    status = (
        await session.execute(
            select(ReportArtifact.status).where(
                ReportArtifact.workspace_id == workspace_id,
                ReportArtifact.id == report_artifact_id,
            )
        )
    ).scalar_one_or_none()
    if status is None:
        raise SynthesisError("report artifact not found")
    if status == "ready":
        raise ReportArtifactImmutable("ready report artifacts can never be updated")
    await session.execute(
        update(ReportArtifact)
        .where(
            ReportArtifact.workspace_id == workspace_id,
            ReportArtifact.id == report_artifact_id,
        )
        .values(**values)
    )


async def delete_report_artifact(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    report_artifact_id: UUID,
) -> None:
    """Repository-layer deletion guard: ready rows are immutable."""

    status = (
        await session.execute(
            select(ReportArtifact.status).where(
                ReportArtifact.workspace_id == workspace_id,
                ReportArtifact.id == report_artifact_id,
            )
        )
    ).scalar_one_or_none()
    if status is None:
        raise SynthesisError("report artifact not found")
    if status == "ready":
        raise ReportArtifactImmutable("ready report artifacts can never be deleted")
    await session.execute(
        delete(ReportArtifact).where(
            ReportArtifact.workspace_id == workspace_id,
            ReportArtifact.id == report_artifact_id,
        )
    )


# --- exports (full level only; PDF always disabled on blocked runs) ----------

_MEDIA_TYPE_BY_EXPORT: Final[dict[str, str]] = {
    "html": "text/html",
    "pdf": "application/pdf",
}


async def create_export_artifact(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    report_artifact_id: UUID,
    export_type: str,
    renderer_version: str,
    gate_status: str,
    origin_modes: Sequence[OriginMode] = (OriginMode.LIVE,),
) -> UUID:
    """Create one HTML/PDF export row after every canonical guard passes.

    Guard order (all fail-closed):

    1. the report must exist and be a ``full``/``detailed`` artifact —
       focused never exports (:class:`ExportNotAllowed`);
    2. a blocked gate disables PDF (and formal exports generally); the HTML
       *draft* a full run may keep is not an ExportArtifact;
    3. the Run must be ``ready`` and the report published ``ready``.
    """

    if export_type not in _MEDIA_TYPE_BY_EXPORT:
        raise ExportNotAllowed(f"unknown export type {export_type!r}")
    report = (
        await session.execute(
            select(ReportArtifact).where(
                ReportArtifact.workspace_id == workspace_id,
                ReportArtifact.id == report_artifact_id,
            )
        )
    ).scalar_one_or_none()
    if report is None:
        raise SynthesisError("report artifact not found")
    if FormalAnalysisLevel(report.analysis_level) is not FormalAnalysisLevel.FULL:
        raise ExportNotAllowed("focused reports never create export artifacts")
    if gate_status != "passed":
        raise ExportNotAllowed("exports are disabled while the quality gate blocks the run")
    run_status = (
        await session.execute(
            select(AnalysisRun.status).where(
                AnalysisRun.workspace_id == workspace_id,
                AnalysisRun.analysis_run_id == report.analysis_run_id,
            )
        )
    ).scalar_one()
    if AnalysisRunStatus(run_status) is not AnalysisRunStatus.READY:
        raise ReportPublicationBlocked("run is not ready; export is blocked")
    if report.status != "ready":
        raise ReportPublicationBlocked("report is not published; export is blocked")

    export_id = uuid4()
    await session.execute(
        insert(ExportArtifact).values(
            id=export_id,
            workspace_id=workspace_id,
            report_artifact_id=report_artifact_id,
            analysis_run_id=report.analysis_run_id,
            decision_case_id=report.decision_case_id,
            case_version=report.case_version,
            type=export_type,
            status="pending",
            media_type=_MEDIA_TYPE_BY_EXPORT[export_type],
            renderer_version=renderer_version,
            origin_modes=list(dict.fromkeys(origin_modes)),
        )
    )
    return export_id


# --- content assembly helpers --------------------------------------------------


def build_report_validation(
    *, passed: bool, errors: Sequence[str] = (), warnings: Sequence[str] = ()
) -> dict[str, Any]:
    """Canonical ReportValidation document (Validation only reports — a failed
    validation never writes content, it can only leave the run blocked)."""

    return {
        "passed": passed,
        "errors": list(errors),
        "warnings": list(warnings),
        "checkedAt": _utc_now_iso(),
    }


def compose_focused_result(document: Mapping[str, Any]) -> FocusedResearchResult:
    """Validate a focused output document (zero lens/PDF/simulation surface)."""

    return FocusedResearchResult.model_validate(document)


def compose_structured_report(
    document: Mapping[str, Any], *, ready_lens_artifact_ids: Sequence[str]
) -> StructuredReport:
    """Validate a full output document against the five persisted artifacts.

    The report body (or inline lens prose) can never substitute the five
    references: ``lensArtifactIds`` must equal the ready artifact id set.
    """

    report = StructuredReport.model_validate(document)
    if set(report.lens_artifact_ids) != {str(item) for item in ready_lens_artifact_ids}:
        raise ReportLevelMismatch(
            "StructuredReport.lensArtifactIds must exactly reference the five "
            "ready artifacts of this run"
        )
    return report
