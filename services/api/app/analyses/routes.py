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
from app.security.envelope import ApiFailure
from app.tenancy.context import WorkspaceContext, require_workspace_context
from app.types import AnalysisRunStatus

from .models import AnalysisEvent
from .repository import (
    AnalysisRuntimeRepository,
    IdempotencyConflict,
    RunAmendmentRequired,
    RunNotCancellable,
    RunNotFound,
    RunNotResumable,
    RunResolutionInvalid,
    normalized_request_hash,
)
from .state_machine import TERMINAL_STATUSES, InvalidTransition

router = APIRouter(prefix="/api/workspaces/{workspaceId}")

_SSE_POLL_SECONDS = 0.05


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
            if AnalysisRunStatus(current.status) in TERMINAL_STATUSES:
                # flush any events written together with the terminal transition
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
        raise ApiFailure(
            "ANALYSIS_RUN_NOT_RESUMABLE",
            "Run is not in needs_attention or is already terminal.",
            http_status=409,
        ) from exc
    except RunAmendmentRequired as exc:
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
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
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
