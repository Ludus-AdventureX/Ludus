"""Analysis runtime routes (Task 9; relative, UNMOUNTED).

Mounting belongs to the integration layer; ``app.main`` is untouched and none
of these paths reach the generated contracts. Endpoints:

- ``GET  /api/workspaces/{workspaceId}/analyses/{analysisRunId}/events``:
  SSE stream of canonical ``AnalysisEvent`` envelopes; ``event:`` equals the
  canonical category, ``data:`` is the full envelope, ``id:`` is the event id
  and replay uses ``Last-Event-ID`` against the persisted per-run sequence.
- ``POST .../analyses/{analysisRunId}/resolutions``: classification-first
  intervention; only the three canonical payload kinds with an empty
  changed-frozen-fields diff append a RunResolution and resume the run to its
  persisted ``lastResumableStage``; frozen-field changes (lens set included)
  return 409 RUN_AMENDMENT_REQUIRED. Idempotency per CCR-20260725-ANALYSIS-01
  §2.1/§2.2 (consumed read-only @ d6675693fd2b7709d9ed4756489e633c49c869ee):
  the ``Idempotency-Key`` HTTP header is mandatory (never a body field); same
  key + same normalized body replays the original success with
  ``meta.idempotencyReplay: true``; same key + different body answers 409
  ``IDEMPOTENCY_CONFLICT``. ``ANALYSIS_TRANSITION_INVALID`` (409) is the
  defense-in-depth backstop for races that surface an out-of-matrix
  transition after the specific guards passed; it never replaces a more
  specific code.
- ``POST .../analyses/{analysisRunId}/cancel``: idempotent cooperative
  cancellation of queued / executing / needs_attention runs.

Tenancy: ``require_workspace_context`` first, then uniform CASE_NOT_FOUND for
missing/foreign run ids (anti-enumeration).

CSRF (CCR-20260726-MOUNT-02 M8, closing the MOUNT-01 M8 stop-report): every
unsafe write on this router (resolutions, cancel, charter create/PATCH/
replacements/confirm, run create) carries ``Depends(require_csrf)`` — the
SIM-02A double-submit parity the Task 9 handoff r4 addendum recommended. The
dependency is declared after the workspace context so an unauthenticated
caller still answers 401 before any CSRF 403. Safe reads (run status, SSE,
strategic-lenses) stay CSRF-free.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import AnalysisRun
from app.security.csrf import require_csrf
from app.security.envelope import ApiFailure
from app.tenancy.context import WorkspaceContext, require_workspace_context
from app.types import AnalysisRunStatus, FormalAnalysisLevel

from .lens_artifact_reads import LensArtifactView, StrategicLensArtifactReadService
from .models import AnalysisCharter, AnalysisEvent
from .repository import (
    AnalysisRuntimeRepository,
    CharterImmutable,
    CharterNotConfirmed,
    CharterNotFound,
    IdempotencyConflict,
    RunAlreadyActive,
    RunAmendmentRequired,
    RunNotCancellable,
    RunNotFound,
    RunNotResumable,
    RunResolutionInvalid,
    normalized_request_hash,
)
from .state_machine import TERMINAL_STATUSES, InvalidCharter, InvalidTransition

router = APIRouter(prefix="/api/workspaces/{workspaceId}")

_SSE_POLL_SECONDS = 0.05

# Statuses that end an SSE stream. This is the canonical terminal set PLUS
# needs_attention: a parked run is not terminal (a resolution can resume it),
# but nothing further will be emitted until a human acts, so keeping the stream
# open leaves the browser's EventSource hanging on a 50ms server-side poll
# forever. Closing lets the client re-read the run and show the parked state;
# a resume opens a new stream and Last-Event-ID replays without a gap.
_STREAM_CLOSING_STATUSES = frozenset(
    {*TERMINAL_STATUSES, AnalysisRunStatus.NEEDS_ATTENTION}
)


def case_not_found() -> ApiFailure:
    return ApiFailure(
        "CASE_NOT_FOUND",
        "Case material not found.",
        http_status=404,
    )


def _idempotency_conflict() -> ApiFailure:
    """§2.2/§5: same Idempotency-Key reused with a different normalized body."""

    return ApiFailure(
        "IDEMPOTENCY_CONFLICT",
        "This Idempotency-Key was already used with a different request body.",
        http_status=409,
    )


def transition_invalid() -> ApiFailure:
    """CCR-20260725-ANALYSIS-01 §5: the single NEW reserved backstop code.

    Raised only when an API-reachable request implies a run transition outside
    the canonical §1.4 matrix and no more specific code applies (e.g. a race
    between the state check and the act). It MUST NOT replace the specific
    codes, so every route maps the dedicated exceptions first.
    """

    return ApiFailure(
        "ANALYSIS_TRANSITION_INVALID",
        "The implied run state transition is outside the canonical matrix.",
        http_status=409,
    )


def validate_idempotency_key(value: str | None) -> str:
    """Mandatory Idempotency-Key header (§2.1); format per SIM-02A precedent.

    Length bounds mirror the ``idempotency_records`` CHECK constraint
    (1..200); format details are IMPLEMENTATION_FREE per §2.2.
    """

    if value is None or not value.strip() or len(value) > 200:
        raise ApiFailure(
            "VALIDATION_FAILED",
            "The Idempotency-Key header is required and must be 1-200 characters.",
            http_status=422,
            details={"header": "Idempotency-Key"},
        )
    return value


def _envelope(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


def _event_envelope(event: AnalysisEvent) -> dict[str, Any]:
    return {
        "id": str(event.id),
        "sequence": event.sequence,
        "workspaceId": str(event.workspace_id),
        "decisionCaseId": str(event.decision_case_id),
        "analysisRunId": str(event.analysis_run_id),
        "category": event.category,
        "type": event.type,
        "originMode": event.origin_mode.value,
        "sourceOriginModes": list(event.source_origin_modes),
        "createdAt": event.created_at.isoformat(),
        "payload": dict(event.payload),
    }


def _sse_frame(event: AnalysisEvent) -> str:
    envelope = json.dumps(_event_envelope(event), ensure_ascii=False)
    return f"id: {str(event.id)}\nevent: {event.category}\ndata: {envelope}\n\n"


async def _resolve_last_event_sequence(
    repo: AnalysisRuntimeRepository,
    workspace_id: UUID,
    analysis_run_id: UUID,
    last_event_id: str | None,
) -> int:
    """Map a Last-Event-ID (event id) onto its persisted sequence; 0 when absent."""

    if not last_event_id:
        return 0
    events = await repo.list_events_after(workspace_id, analysis_run_id, 0)
    for event in events:
        if str(event.id) == last_event_id:
            return event.sequence
    return 0


@router.get("/analyses/{analysisRunId}/events")
async def stream_run_events(
    request: Request,
    analysis_run_id: UUID = Path(alias="analysisRunId"),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    repo = AnalysisRuntimeRepository(db)
    run = await repo.get_run(context.workspace_id, analysis_run_id)
    if run is None:
        raise case_not_found()
    start_after = await _resolve_last_event_sequence(
        repo, context.workspace_id, analysis_run_id, last_event_id
    )

    async def event_stream():
        cursor = start_after
        while True:
            events = await repo.list_events_after(
                context.workspace_id, analysis_run_id, cursor
            )
            for event in events:
                cursor = event.sequence
                yield _sse_frame(event)
            current = await repo.get_run(context.workspace_id, analysis_run_id)
            if current is None:
                return
            if AnalysisRunStatus(current.status) in _STREAM_CLOSING_STATUSES:
                # flush any events written together with the closing transition
                tail = await repo.list_events_after(
                    context.workspace_id, analysis_run_id, cursor
                )
                for event in tail:
                    cursor = event.sequence
                    yield _sse_frame(event)
                return
            if await request.is_disconnected():
                return
            await asyncio.sleep(_SSE_POLL_SECONDS)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _resolution_success_data(
    analysis_run_id: UUID,
    classification_id: UUID,
    classification_result: str,
    changed_frozen_fields: list[str],
    resolution_id: UUID,
    resumed_stage: str,
) -> dict[str, Any]:
    """The §2.1 frozen success ``data`` shape (single builder so a replay is
    byte-identical to the original response)."""

    return {
        "analysisRunId": str(analysis_run_id),
        "classification": {
            "classificationId": str(classification_id),
            "result": classification_result,
            "changedFrozenFields": changed_frozen_fields,
        },
        "resolutionId": str(resolution_id),
        "status": resumed_stage,
        "resumedFrom": resumed_stage,
    }


async def _replay_resolution_response(
    repo: AnalysisRuntimeRepository,
    workspace_id: UUID,
    resolution_id: UUID,
    http_status: int,
) -> JSONResponse:
    """§2.2 replay: original status, same body, ``meta.idempotencyReplay: true``."""

    replay = await repo.load_resolution_replay(workspace_id, resolution_id)
    if replay is None:
        # The recorded resource vanished (should be impossible: resolutions are
        # append-only); fail closed rather than fabricate a success.
        raise case_not_found()
    resolution, classification, resumed_event = replay
    resumed_stage = AnalysisRunStatus(resolution.resume_stage).value
    body = {
        "ok": True,
        "data": _resolution_success_data(
            resolution.analysis_run_id,
            classification.id,
            classification.result,
            list(classification.changed_frozen_fields),
            resolution.id,
            resumed_stage,
        ),
        "eventId": str(resumed_event.id) if resumed_event is not None else None,
        "meta": {"idempotencyReplay": True},
    }
    return JSONResponse(status_code=http_status, content=body)


@router.post("/analyses/{analysisRunId}/resolutions")
async def post_run_resolution(
    body: dict[str, Any],
    analysis_run_id: UUID = Path(alias="analysisRunId"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> Any:
    repo = AnalysisRuntimeRepository(db)
    key = validate_idempotency_key(idempotency_key)
    if "idempotencyKey" in body or "idempotency_key" in body:
        # §2.1: the key travels ONLY via the Idempotency-Key header.
        raise ApiFailure(
            "VALIDATION_FAILED",
            "The idempotency key must be sent as the Idempotency-Key header, "
            "not in the request body.",
            http_status=422,
            details={"header": "Idempotency-Key"},
        )
    request_hash = normalized_request_hash(body)
    try:
        stored = await repo.check_resolution_idempotency(
            context.workspace_id, key, request_hash
        )
    except IdempotencyConflict as exc:
        raise _idempotency_conflict() from exc
    if stored is not None:
        return await _replay_resolution_response(
            repo, context.workspace_id, stored.resource_id, stored.http_status
        )

    payload = body.get("payload")
    if not isinstance(payload, dict):
        raise ApiFailure(
            "RUN_RESOLUTION_INVALID",
            "Resolution payload is missing or malformed.",
            http_status=422,
        )
    proposed = body.get("proposedCharterChanges")
    try:
        classification, resolution, record = await repo.classify_and_resolve(
            context.workspace_id,
            analysis_run_id,
            payload=payload,
            created_by=context.user_id,
            proposed_charter_changes=proposed if isinstance(proposed, dict) else None,
        )
    except RunNotFound as exc:
        raise case_not_found() from exc
    except RunNotResumable as exc:
        # §2.2 (QA-P2): a same-key duplicate that lost the concurrency race
        # reaches here AFTER the winner committed — the entry pre-check saw no
        # record yet, the run row lock serialized both flows, and the loser
        # re-read a resumed run. Re-check the idempotency record so the
        # duplicate replays the winner's success instead of answering 409.
        try:
            stored = await repo.check_resolution_idempotency(
                context.workspace_id, key, request_hash
            )
        except IdempotencyConflict as conflict:
            raise _idempotency_conflict() from conflict
        if stored is not None:
            return await _replay_resolution_response(
                repo, context.workspace_id, stored.resource_id, stored.http_status
            )
        raise ApiFailure(
            "ANALYSIS_RUN_NOT_RESUMABLE",
            "Run is not in needs_attention or is already terminal.",
            http_status=409,
        ) from exc
    except RunAmendmentRequired as exc:
        # §2.3 (QA-P1): the append-only classification and its
        # analysis.amendment_required event must survive this 409 under the
        # production session lifecycle — commit them before raising.
        await db.commit()
        raise ApiFailure(
            "RUN_AMENDMENT_REQUIRED",
            "Input changes charter frozen fields; create a replacement charter "
            "and a new run.",
            http_status=409,
            details={
                "changedFrozenFields": exc.changed_frozen_fields,
                "classificationId": str(exc.classification_id),
                "replacementUrl": (
                    f"/api/workspaces/{context.workspace_id}/analysis-charters/"
                    "{charterId}/replacements"
                ),
            },
        ) from exc
    except RunResolutionInvalid as exc:
        raise ApiFailure(
            "RUN_RESOLUTION_INVALID",
            "Resolution payload is outside the allowed kinds or frozen scope.",
            http_status=422,
        ) from exc
    except InvalidTransition as exc:
        # §5 backstop only: every specific code above is mapped first.
        raise transition_invalid() from exc

    await repo.record_resolution_idempotency(
        context.workspace_id,
        idempotency_key=key,
        request_hash=request_hash,
        resolution_id=resolution.id,
        http_status=200,
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        # Loser of a concurrent same-key race: the winner's record + resolution
        # committed first, so answer per §2.2 (replay or conflict).
        await db.rollback()
        if "uq_idempotency_records_workspace_route_key" not in str(exc):
            raise
        try:
            stored = await repo.check_resolution_idempotency(
                context.workspace_id, key, request_hash
            )
        except IdempotencyConflict as conflict:
            raise _idempotency_conflict() from conflict
        if stored is None:
            raise
        return await _replay_resolution_response(
            repo, context.workspace_id, stored.resource_id, stored.http_status
        )
    return {
        "ok": True,
        "data": _resolution_success_data(
            analysis_run_id,
            classification.id,
            classification.result,
            list(classification.changed_frozen_fields),
            resolution.id,
            record.to_status.value,
        ),
        "eventId": str(record.event_id),
    }


@router.post("/analyses/{analysisRunId}/cancel")
async def post_run_cancel(
    body: dict[str, Any] | None = None,
    analysis_run_id: UUID = Path(alias="analysisRunId"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> dict[str, Any]:
    # MOUNT-01 M9 / 10-api L953: cancel is a POST that MUST carry the
    # Idempotency-Key header (the key travels ONLY in the header, resolutions
    # precedent). Cancel is naturally idempotent — the canonical terminal state
    # converges on replay — so requiring the header honors the guarantee
    # without an idempotency_records row.
    validate_idempotency_key(idempotency_key)
    if isinstance(body, dict) and ("idempotencyKey" in body or "idempotency_key" in body):
        raise ApiFailure(
            "VALIDATION_FAILED",
            "The idempotency key must be sent as the Idempotency-Key header, "
            "not in the request body.",
            http_status=422,
            details={"header": "Idempotency-Key"},
        )
    repo = AnalysisRuntimeRepository(db)
    reason = "user_cancelled"
    if isinstance(body, dict) and isinstance(body.get("reason"), str):
        reason = body["reason"]
    try:
        run = await repo.cancel(context.workspace_id, analysis_run_id, reason=reason)
    except RunNotFound as exc:
        raise case_not_found() from exc
    except RunNotCancellable as exc:
        raise ApiFailure(
            "ANALYSIS_RUN_NOT_CANCELLABLE",
            "Only queued, executing, or needs_attention runs can be cancelled.",
            http_status=409,
        ) from exc
    except InvalidTransition as exc:
        # §5 backstop only: RunNotCancellable is mapped first.
        raise transition_invalid() from exc
    await db.commit()
    return _envelope(
        {
            "analysisRunId": str(analysis_run_id),
            "status": AnalysisRunStatus(run.status).value,
            "cancelledAt": run.cancelled_at.isoformat() if run.cancelled_at else None,
        }
    )


# ---------------------------------------------------------------------------
# MOUNT-01 M3/M4/M5 follow-up (Task 9 owner): Charter lifecycle + Run creation
# + run status + strategic-lens read HTTP handlers. Relative and UNMOUNTED —
# mounting + contract regeneration belong to MOUNT-02. Every handler consumes
# the shipped repository / lens read service as-is (zero domain/repository/
# state-machine change) and answers the {ok,data} envelope; cross-tenant and
# missing ids collapse into the uniform CASE_NOT_FOUND 404 (anti-enumeration).
# ---------------------------------------------------------------------------

_CHARTER_CREATE_REQUIRED = (
    "decisionSubjectId",
    "caseVersion",
    "caseSnapshotHash",
    "analysisLevel",
    "decisionQuestion",
    "dossierSnapshotVersion",
    "dossierSnapshotHash",
)

_CHARTER_EDIT_MAP = {
    "decisionQuestion": "decision_question",
    "goals": "goals",
    "constraints": "constraints",
    "optionIds": "option_ids",
    "preferenceWeights": "preference_weights",
    "requiredStrategicLensTypes": "required_strategic_lens_types",
    "allowedConnectorIds": "allowed_connector_ids",
    "budget": "budget",
    "formalAnalysisAllowed": "formal_analysis_allowed",
    "methodId": "method_id",
    "methodVersion": "method_version",
    "methodContentHash": "method_content_hash",
    "caseVersion": "case_version",
    "caseSnapshotHash": "case_snapshot_hash",
    "dossierSnapshotVersion": "dossier_snapshot_version",
    "dossierSnapshotHash": "dossier_snapshot_hash",
}


def _validation_failed(
    message: str, *, details: dict[str, Any] | None = None
) -> ApiFailure:
    return ApiFailure("VALIDATION_FAILED", message, http_status=422, details=details or {})


def _charter_not_confirmed() -> ApiFailure:
    return ApiFailure(
        "CHARTER_NOT_CONFIRMED",
        "The analysis charter is not confirmed.",
        http_status=409,
    )


def _charter_immutable(
    message: str = "Confirmed or superseded charters cannot be edited.",
) -> ApiFailure:
    return ApiFailure("CHARTER_IMMUTABLE", message, http_status=409)


def _lens_not_found() -> ApiFailure:
    # Byte-identical to the lens read service denial so run-missing,
    # artifact-missing, and cross-tenant reads cannot be told apart.
    return ApiFailure(
        "CASE_NOT_FOUND",
        "Decision case, analysis run, or artifact not found.",
        http_status=404,
    )


def _origin_mode_values(modes: Any) -> list[str]:
    return [mode.value if hasattr(mode, "value") else str(mode) for mode in modes]


def _charter_data(charter: AnalysisCharter) -> dict[str, Any]:
    level = (
        charter.analysis_level.value
        if isinstance(charter.analysis_level, FormalAnalysisLevel)
        else str(charter.analysis_level)
    )
    return {
        "charterId": str(charter.id),
        "decisionSubjectId": str(charter.decision_subject_id),
        "decisionCaseId": str(charter.decision_case_id),
        "version": charter.version,
        "status": charter.status,
        "analysisLevel": level,
        "decisionQuestion": charter.decision_question,
        "caseVersion": charter.case_version,
        "caseSnapshotHash": charter.case_snapshot_hash,
        "dossierSnapshotVersion": charter.dossier_snapshot_version,
        "dossierSnapshotHash": charter.dossier_snapshot_hash,
        "goals": list(charter.goals),
        "constraints": list(charter.constraints),
        "optionIds": list(charter.option_ids),
        "preferenceWeights": dict(charter.preference_weights),
        "requiredStrategicLensTypes": list(charter.required_strategic_lens_types),
        "methodId": charter.method_id,
        "methodVersion": charter.method_version,
        "methodContentHash": charter.method_content_hash,
        "formalAnalysisAllowed": charter.formal_analysis_allowed,
        "allowedConnectorIds": list(charter.allowed_connector_ids),
        "budget": dict(charter.budget),
        "replacesCharterId": (
            str(charter.replaces_charter_id) if charter.replaces_charter_id else None
        ),
        "supersededByCharterId": (
            str(charter.superseded_by_charter_id)
            if charter.superseded_by_charter_id
            else None
        ),
        "confirmedAt": charter.confirmed_at.isoformat() if charter.confirmed_at else None,
        "createdAt": charter.created_at.isoformat(),
    }


def _run_data(run: AnalysisRun, workspace_id: UUID) -> dict[str, Any]:
    level = (
        run.analysis_level.value
        if isinstance(run.analysis_level, FormalAnalysisLevel)
        else str(run.analysis_level)
    )
    return {
        "analysisRunId": str(run.analysis_run_id),
        "decisionCaseId": str(run.decision_case_id),
        "charterId": str(run.charter_id),
        "charterVersion": run.charter_version,
        "analysisLevel": level,
        "status": AnalysisRunStatus(run.status).value,
        "progress": run.progress,
        "originModes": _origin_mode_values(run.origin_modes),
        "caseVersion": run.case_version,
        "caseSnapshotHash": run.case_snapshot_hash,
        "methodId": run.method_id,
        "methodVersion": run.method_version,
        "attempt": run.attempt,
        "maxAttempts": run.max_attempts,
        "runManifestId": str(run.run_manifest_id),
        "runManifestHash": run.run_manifest_hash,
        "lastResumableStage": (
            AnalysisRunStatus(run.last_resumable_stage).value
            if run.last_resumable_stage
            else None
        ),
        "strategicLensArtifactIds": list(run.strategic_lens_artifact_ids),
        "supersedesAnalysisRunId": (
            str(run.supersedes_analysis_run_id)
            if run.supersedes_analysis_run_id
            else None
        ),
        "supersededByAnalysisRunId": (
            str(run.superseded_by_analysis_run_id)
            if run.superseded_by_analysis_run_id
            else None
        ),
        "cancellationReason": run.cancellation_reason,
        "startedAt": run.started_at.isoformat() if run.started_at else None,
        "heartbeatAt": run.heartbeat_at.isoformat() if run.heartbeat_at else None,
        "completedAt": run.completed_at.isoformat() if run.completed_at else None,
        "cancelledAt": run.cancelled_at.isoformat() if run.cancelled_at else None,
        "createdAt": run.created_at.isoformat(),
        "eventsUrl": (
            f"/api/workspaces/{workspace_id}/analyses/{run.analysis_run_id}/events"
        ),
    }


def _lens_summary(view: LensArtifactView) -> dict[str, Any]:
    return {
        "id": str(view.strategic_lens_artifact_id),
        "lensType": view.lens_type.value,
        "producerRole": view.producer_role.value,
        "status": view.status.value,
        "methodId": view.method_id,
        "methodVersion": view.method_version,
        "methodContentHash": view.method_content_hash,
        "promptVersion": view.prompt_version,
        "schemaVersion": view.schema_version,
        "contentHash": view.content_hash,
        "originModes": _origin_mode_values(view.origin_modes),
        "referenceCounts": {
            "claimCount": len(view.claim_refs),
            "evidenceCount": len(view.evidence_refs),
            "assumptionCount": len(view.assumption_refs),
        },
        "validationAcceptedAt": (
            view.validation_accepted_at.isoformat()
            if view.validation_accepted_at
            else None
        ),
        "createdAt": view.created_at.isoformat(),
    }


def _lens_detail(view: LensArtifactView) -> dict[str, Any]:
    data = _lens_summary(view)
    data.update(
        {
            "decisionCaseId": str(view.decision_case_id),
            "analysisRunId": str(view.analysis_run_id),
            "charterId": str(view.charter_id),
            "claimRefs": list(view.claim_refs),
            "evidenceRefs": list(view.evidence_refs),
            "assumptionRefs": list(view.assumption_refs),
            "content": view.payload,
        }
    )
    return data


def _charter_changes_from_body(body: dict[str, Any]) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    for wire, column in _CHARTER_EDIT_MAP.items():
        if wire in body:
            changes[column] = body[wire]
    if "analysisLevel" in body:
        changes["analysis_level"] = FormalAnalysisLevel(body["analysisLevel"])
    return changes


@router.post("/cases/{decisionCaseId}/analysis-charters", status_code=201)
async def create_analysis_charter(
    body: dict[str, Any],
    decision_case_id: UUID = Path(alias="decisionCaseId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> JSONResponse:
    """Create a draft charter from the method-route result (10-api §方法路由)."""

    missing = [field for field in _CHARTER_CREATE_REQUIRED if not body.get(field)]
    if missing:
        raise _validation_failed(
            "Charter draft is missing required fields.",
            details={"missingFields": missing},
        )
    try:
        values: dict[str, Any] = {
            "workspace_id": context.workspace_id,
            "decision_subject_id": UUID(str(body["decisionSubjectId"])),
            "decision_case_id": decision_case_id,
            "case_version": int(body["caseVersion"]),
            "case_snapshot_hash": str(body["caseSnapshotHash"]),
            "analysis_level": FormalAnalysisLevel(body["analysisLevel"]),
            "decision_question": str(body["decisionQuestion"]),
            "dossier_snapshot_version": int(body["dossierSnapshotVersion"]),
            "dossier_snapshot_hash": str(body["dossierSnapshotHash"]),
            "goals": list(body.get("goals", [])),
            "constraints": list(body.get("constraints", [])),
            "option_ids": [str(option) for option in body.get("optionIds", [])],
            "preference_weights": dict(body.get("preferenceWeights", {})),
            "required_strategic_lens_types": [
                str(lens) for lens in body.get("requiredStrategicLensTypes", [])
            ],
            "allowed_connector_ids": [
                str(cid) for cid in body.get("allowedConnectorIds", [])
            ],
            "budget": dict(body.get("budget", {})),
            "formal_analysis_allowed": bool(body.get("formalAnalysisAllowed", False)),
        }
        for wire, column in (
            ("methodId", "method_id"),
            ("methodVersion", "method_version"),
            ("methodContentHash", "method_content_hash"),
        ):
            if body.get(wire) is not None:
                values[column] = str(body[wire])
    except (ValueError, TypeError) as exc:
        raise _validation_failed(f"Charter draft field is malformed: {exc}") from exc

    repo = AnalysisRuntimeRepository(db)
    try:
        charter = await repo.create_charter_draft(**values)
        await db.commit()
    except InvalidCharter as exc:
        await db.rollback()
        raise _validation_failed(str(exc)) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise _validation_failed(
            "Charter draft violates a persistence constraint."
        ) from exc
    return JSONResponse(status_code=201, content=_envelope(_charter_data(charter)))


@router.patch("/analysis-charters/{charterId}")
async def patch_analysis_charter(
    body: dict[str, Any],
    charter_id: UUID = Path(alias="charterId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> dict[str, Any]:
    """Edit a draft charter in place (confirmed/superseded reject with 409)."""

    try:
        changes = _charter_changes_from_body(body)
    except (ValueError, TypeError) as exc:
        raise _validation_failed(f"Charter edit field is malformed: {exc}") from exc
    if not changes:
        raise _validation_failed("No editable charter fields were supplied.")
    repo = AnalysisRuntimeRepository(db)
    try:
        charter = await repo.update_draft_charter(
            context.workspace_id, charter_id, **changes
        )
        await db.commit()
    except CharterNotFound as exc:
        raise case_not_found() from exc
    except CharterImmutable as exc:
        raise _charter_immutable() from exc
    except InvalidCharter as exc:
        await db.rollback()
        raise _validation_failed(str(exc)) from exc
    return _envelope(_charter_data(charter))


@router.post("/analysis-charters/{charterId}/replacements", status_code=201)
async def create_charter_replacement(
    body: dict[str, Any] | None = None,
    charter_id: UUID = Path(alias="charterId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> JSONResponse:
    """Clone a confirmed charter into a new draft carrying the amendment."""

    try:
        changes = _charter_changes_from_body(body or {})
    except (ValueError, TypeError) as exc:
        raise _validation_failed(f"Replacement field is malformed: {exc}") from exc
    repo = AnalysisRuntimeRepository(db)
    try:
        charter = await repo.create_replacement_draft(
            context.workspace_id, charter_id, changes=changes
        )
        await db.commit()
    except CharterNotFound as exc:
        raise case_not_found() from exc
    except CharterNotConfirmed as exc:
        raise _charter_not_confirmed() from exc
    except InvalidCharter as exc:
        await db.rollback()
        raise _validation_failed(str(exc)) from exc
    return JSONResponse(status_code=201, content=_envelope(_charter_data(charter)))


@router.post("/analysis-charters/{charterId}/confirm")
async def confirm_analysis_charter(
    charter_id: UUID = Path(alias="charterId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> dict[str, Any]:
    """Freeze a charter (draft -> awaiting_confirmation -> confirmed)."""

    repo = AnalysisRuntimeRepository(db)
    charter = await repo.get_charter(context.workspace_id, charter_id)
    if charter is None:
        raise case_not_found()
    try:
        if charter.status == "draft":
            await repo.submit_charter(context.workspace_id, charter_id)
        charter = await repo.confirm_charter(context.workspace_id, charter_id)
        await db.commit()
    except CharterNotFound as exc:
        raise case_not_found() from exc
    except InvalidCharter as exc:
        await db.rollback()
        raise _validation_failed(str(exc)) from exc
    except InvalidTransition as exc:
        await db.rollback()
        raise _charter_immutable("Charter is not in a confirmable state.") from exc
    return _envelope(_charter_data(charter))


@router.post("/analysis-charters/{charterId}/runs", status_code=201)
async def create_analysis_run(
    body: dict[str, Any] | None = None,
    charter_id: UUID = Path(alias="charterId"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
    _csrf: None = Depends(require_csrf),
) -> JSONResponse:
    """Create a queued Run from a confirmed charter (Idempotency-Key header)."""

    key = validate_idempotency_key(idempotency_key)
    body = body or {}
    if "idempotencyKey" in body or "idempotency_key" in body:
        raise _validation_failed(
            "The idempotency key must be sent as the Idempotency-Key header, "
            "not in the request body.",
            details={"header": "Idempotency-Key"},
        )
    missing = [
        field
        for field in ("cynefinGateResultId", "runManifestHash")
        if not body.get(field)
    ]
    if missing:
        raise _validation_failed(
            "Run creation is missing required fields.",
            details={"missingFields": missing},
        )
    try:
        cynefin_gate_result_id = UUID(str(body["cynefinGateResultId"]))
        run_manifest_hash = str(body["runManifestHash"])
        supersedes = body.get("supersedesAnalysisRunId")
        supersedes_id = UUID(str(supersedes)) if supersedes else None
    except (ValueError, TypeError) as exc:
        raise _validation_failed(f"Run creation field is malformed: {exc}") from exc

    repo = AnalysisRuntimeRepository(db)
    try:
        run, created = await repo.create_queued_run(
            workspace_id=context.workspace_id,
            charter_id=charter_id,
            idempotency_key=key,
            run_manifest_hash=run_manifest_hash,
            cynefin_gate_result_id=cynefin_gate_result_id,
            supersedes_analysis_run_id=supersedes_id,
        )
        await db.commit()
    except CharterNotFound as exc:
        raise case_not_found() from exc
    except CharterNotConfirmed as exc:
        raise _charter_not_confirmed() from exc
    except RunAlreadyActive as exc:
        await db.rollback()
        raise ApiFailure(
            "ANALYSIS_RUN_ALREADY_ACTIVE",
            "Another formal analysis run is already active for this case.",
            http_status=409,
            details={"existingAnalysisRunId": str(exc.existing_analysis_run_id)},
        ) from exc

    if not created:
        # §2.2 replay: a reused key must carry the same creation request. The run
        # persists the meaningful body (charter + manifest + cynefin gate +
        # supersedes target); a mismatch is a reused key with a different body
        # -> IDEMPOTENCY_CONFLICT. supersedesAnalysisRunId joined the compare
        # set per CCR-20260726-MOUNT-02 addendum ⑦ (P3 combination-only fix):
        # a same-key retry that only changes the supersedes target must 409,
        # never silently replay the original run.
        if (
            run.charter_id != charter_id
            or run.run_manifest_hash != run_manifest_hash
            or run.cynefin_gate_result_id != cynefin_gate_result_id
            or run.supersedes_analysis_run_id != supersedes_id
        ):
            raise _idempotency_conflict()
        return JSONResponse(
            status_code=201,
            content={
                "ok": True,
                "data": _run_data(run, context.workspace_id),
                "meta": {"idempotencyReplay": True},
            },
        )
    return JSONResponse(
        status_code=201, content=_envelope(_run_data(run, context.workspace_id))
    )


@router.get("/analyses/{analysisRunId}")
async def get_analysis_run(
    analysis_run_id: UUID = Path(alias="analysisRunId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Read the current AnalysisRun status (10-api §AnalysisRun 状态)."""

    repo = AnalysisRuntimeRepository(db)
    run = await repo.get_run(context.workspace_id, analysis_run_id)
    if run is None:
        raise case_not_found()
    return _envelope(_run_data(run, context.workspace_id))


@router.get("/analyses/{analysisRunId}/strategic-lenses")
async def list_run_strategic_lenses(
    analysis_run_id: UUID = Path(alias="analysisRunId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List the run's ready strategic-lens artifacts in canonical order."""

    repo = AnalysisRuntimeRepository(db)
    run = await repo.get_run(context.workspace_id, analysis_run_id)
    if run is None:
        raise _lens_not_found()
    service = StrategicLensArtifactReadService(db)
    views = await service.list_ready_for_run(
        context, run.decision_case_id, analysis_run_id
    )
    return _envelope([_lens_summary(view) for view in views])


@router.get("/analyses/{analysisRunId}/strategic-lenses/{artifactId}")
async def get_run_strategic_lens(
    analysis_run_id: UUID = Path(alias="analysisRunId"),
    artifact_id: UUID = Path(alias="artifactId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Read one ready strategic-lens artifact (full detail)."""

    repo = AnalysisRuntimeRepository(db)
    run = await repo.get_run(context.workspace_id, analysis_run_id)
    if run is None:
        raise _lens_not_found()
    service = StrategicLensArtifactReadService(db)
    view = await service.get_ready_artifact(
        context, run.decision_case_id, analysis_run_id, artifact_id
    )
    return _envelope(_lens_detail(view))
