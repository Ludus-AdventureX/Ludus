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
  return 409 RUN_AMENDMENT_REQUIRED.
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
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.security.envelope import ApiFailure
from app.tenancy.context import WorkspaceContext, require_workspace_context
from app.types import AnalysisRunStatus

from .models import AnalysisEvent
from .repository import (
    AnalysisRuntimeRepository,
    RunAmendmentRequired,
    RunNotCancellable,
    RunNotFound,
    RunNotResumable,
    RunResolutionInvalid,
)
from .state_machine import TERMINAL_STATUSES

router = APIRouter(prefix="/api/workspaces/{workspaceId}")

_SSE_POLL_SECONDS = 0.05


def case_not_found() -> ApiFailure:
    return ApiFailure(
        "CASE_NOT_FOUND",
        "Case material not found.",
        http_status=404,
    )


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


@router.post("/analyses/{analysisRunId}/resolutions")
async def post_run_resolution(
    body: dict[str, Any],
    analysis_run_id: UUID = Path(alias="analysisRunId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = AnalysisRuntimeRepository(db)
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
    await db.commit()
    return _envelope(
        {
            "analysisRunId": str(analysis_run_id),
            "classification": {
                "classificationId": str(classification.id),
                "result": classification.result,
                "changedFrozenFields": list(classification.changed_frozen_fields),
            },
            "resolutionId": str(resolution.id),
            "status": record.to_status.value,
            "resumedFrom": record.to_status.value,
        }
    )


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
    await db.commit()
    return _envelope(
        {
            "analysisRunId": str(analysis_run_id),
            "status": AnalysisRunStatus(run.status).value,
            "cancelledAt": run.cancelled_at.isoformat() if run.cancelled_at else None,
        }
    )
