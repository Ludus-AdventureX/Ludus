"""Deliberation council routes (CCR-20260804-DELIB-01, Wave 2).

Mounted with the §M7 precedent: absolute /api/workspaces/{workspaceId}
prefix + per-route require_workspace_context guard. Every read/write:

- resolves tenancy first (uniform 404 for missing/foreign workspaces);
- answers foreign/missing deliberation ids with the same CASE_NOT_FOUND 404
  as every other read surface (anti-enumeration);
- writes carry CSRF (double-submit) after the workspace context dependency;
- the SSE stream mirrors the analyses envelope verbatim (event: = category,
  data: = full DeliberationEvent envelope, Last-Event-ID replay from the
  persisted per-run sequence).
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import (
    DeliberationEvent,
    DeliberationFactor,
    DeliberationMessage,
    DeliberationNomination,
    DeliberationOutcome,
    DeliberationProposal,
    DeliberationRound,
    DeliberationRun,
)
from app.security.csrf import require_csrf
from app.security.envelope import ApiFailure
from app.tenancy.context import WorkspaceContext, require_workspace_context
from app.types import DeliberationRunStatus, OriginMode

from .repository import DeliberationNotFound, DeliberationRepository
from .schemas_api import (
    CreateDeliberationRequest,
    DeliberationAnchorView,
    DeliberationInterventionRequest,
    DeliberationMessageView,
    DeliberationNominationView,
    DeliberationOutcomeView,
    DeliberationProposalView,
    DeliberationRoundView,
    DeliberationFactorView,
    DeliberationRunDetailView,
    NominationDecisionRequest,
    ProposalDecisionRequest,
)
from .service import DeliberationService, DeliberationServiceError, load_case_basis

router = APIRouter(prefix="/api/workspaces/{workspaceId}")

_SSE_POLL_SECONDS = 1.0
_STREAM_CLOSING_STATUSES = {
    DeliberationRunStatus.COMPLETE,
    DeliberationRunStatus.CANCELLED,
}


def case_not_found() -> ApiFailure:
    """Uniform 404: missing, foreign, and cross-tenant reads are identical."""

    return ApiFailure("CASE_NOT_FOUND", "Case material not found.", http_status=404)


def _envelope(data: object) -> dict[str, object]:
    return {"ok": True, "data": data}


def _origin_mode_from_env() -> OriginMode:
    return OriginMode.FIXTURE if os.getenv("FIXTURE_MODE", "false").lower() == "true" else OriginMode.LIVE


def _service(repo: DeliberationRepository) -> DeliberationService:
    return DeliberationService(repo, origin_mode=_origin_mode_from_env())


# --- view builders -----------------------------------------------------------


def _anchor_view(run: DeliberationRun) -> dict[str, Any]:
    return DeliberationAnchorView(
        id=str(run.id),
        decision_case_id=str(run.decision_case_id),
        status=run.status.value,
        current_round_seq=run.current_round_seq,
        max_rounds=run.max_rounds,
        created_at=run.created_at,
        updated_at=run.updated_at,
    ).model_dump(by_alias=True)


def _factor_view(factor: DeliberationFactor) -> dict[str, Any]:
    return DeliberationFactorView(
        id=str(factor.id),
        deliberation_run_id=str(factor.deliberation_run_id),
        provenance=factor.provenance.value,
        label=factor.label,
        strength=factor.strength,
        source_factor_id=factor.source_factor_id,
        statement=factor.statement,
        author_user_id=str(factor.author_user_id) if factor.author_user_id else None,
        dossier_assumption_id=factor.dossier_assumption_id,
        evidence_status=factor.evidence_status.value if factor.evidence_status else None,
    ).model_dump(by_alias=True)


def _round_view(round_row: DeliberationRound) -> dict[str, Any]:
    return DeliberationRoundView(
        id=str(round_row.id),
        deliberation_run_id=str(round_row.deliberation_run_id),
        seq=round_row.seq,
        kind=round_row.kind.value,
        status=round_row.status,
        started_at=round_row.started_at,
        ended_at=round_row.ended_at,
    ).model_dump(by_alias=True)


def _message_view(message: DeliberationMessage) -> dict[str, Any]:
    return DeliberationMessageView(
        id=str(message.id),
        deliberation_run_id=str(message.deliberation_run_id),
        round_id=str(message.round_id),
        speaker=message.speaker.value,
        speaker_factor_id=message.speaker_factor_id,
        kind=message.kind.value,
        content=message.content,
        structured_payload=message.structured_payload,
        stamp_actor=message.stamp_actor.value,
        stamp_note=message.stamp_note,
        origin_mode=message.origin_mode.value,
        source_origin_modes=[m.value for m in message.source_origin_modes],
        created_at=message.created_at,
    ).model_dump(by_alias=True)


def _proposal_view(proposal: DeliberationProposal) -> dict[str, Any]:
    return DeliberationProposalView(
        id=str(proposal.id),
        deliberation_run_id=str(proposal.deliberation_run_id),
        proposer_factor_id=proposal.proposer_factor_id,
        kind=proposal.kind.value,
        before=proposal.before,
        after=proposal.after,
        status=proposal.status.value,
        engine_preview={
            "outcomeScore": proposal.engine_preview.get("outcomeScore"),
            "verdict": proposal.engine_preview.get("verdict"),
            "flipThreshold": proposal.engine_preview.get("flipThreshold"),
        }
        if proposal.engine_preview
        else None,
        decided_at=proposal.decided_at,
    ).model_dump(by_alias=True)


def _nomination_view(nomination: DeliberationNomination) -> dict[str, Any]:
    return DeliberationNominationView(
        id=str(nomination.id),
        deliberation_run_id=str(nomination.deliberation_run_id),
        rationale=nomination.rationale,
        target_description=nomination.target_description,
        status=nomination.status.value,
        confirmed_factor_id=nomination.confirmed_factor_id,
    ).model_dump(by_alias=True)


# --- case-scoped ops -----------------------------------------------------------


@router.post("/cases/{decisionCaseId}/deliberations")
async def create_deliberation(
    body: CreateDeliberationRequest,
    decision_case_id: UUID = Path(alias="decisionCaseId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
    _: None = Depends(require_csrf),
) -> dict[str, Any]:
    repo = DeliberationRepository(db)
    service = _service(repo)
    packets, influences = await load_case_basis(db, context.workspace_id, decision_case_id)
    try:
        run = await service.create_run(
            workspace_id=context.workspace_id,
            decision_case_id=decision_case_id,
            user_id=context.user_id,
            packets=packets,
            influences=influences,
            subjective_declarations=[m.model_dump(by_alias=True) for m in body.subjective_factors],
            max_rounds=body.max_rounds,
        )
    except DeliberationServiceError as error:
        raise ApiFailure(error.code, error.message, http_status=error.http_status) from error
    await db.commit()
    return _envelope(_anchor_view(run))


@router.get("/cases/{decisionCaseId}/deliberations")
async def list_deliberations(
    decision_case_id: UUID = Path(alias="decisionCaseId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = DeliberationRepository(db)
    runs = await repo.list_runs_for_case(context.workspace_id, decision_case_id)
    return _envelope({"items": [_anchor_view(run) for run in runs]})


# --- run-scoped reads ------------------------------------------------------------


async def _require_run(
    repo: DeliberationRepository, workspace_id: UUID, run_id: UUID
) -> DeliberationRun:
    run = await repo.get_run(workspace_id, run_id)
    if run is None:
        raise case_not_found()
    return run


@router.get("/deliberations/{deliberationRunId}")
async def get_deliberation(
    deliberation_run_id: UUID = Path(alias="deliberationRunId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = DeliberationRepository(db)
    run = await _require_run(repo, context.workspace_id, deliberation_run_id)
    factors = await repo.list_factors(context.workspace_id, deliberation_run_id)
    rounds = (
        await db.execute(
            select(DeliberationRound)
            .where(
                DeliberationRound.workspace_id == context.workspace_id,
                DeliberationRound.deliberation_run_id == deliberation_run_id,
            )
            .order_by(DeliberationRound.seq)
        )
    ).scalars().all()
    proposals = await repo.list_proposals(context.workspace_id, deliberation_run_id)
    nominations = await repo.list_nominations(context.workspace_id, deliberation_run_id)
    pending_proposals = [p for p in proposals if p.status.value == "pending"]
    pending_nominations = [n for n in nominations if n.status.value == "pending"]
    view = DeliberationRunDetailView(
        id=str(run.id),
        workspace_id=str(run.workspace_id),
        decision_case_id=str(run.decision_case_id),
        status=run.status.value,
        current_round_seq=run.current_round_seq,
        max_rounds=run.max_rounds,
        factor_snapshot_hash=run.factor_snapshot_hash,
        origin_modes=[m.value for m in run.origin_modes],
        factors=[DeliberationFactorView(**_factor_view(f)) for f in factors],
        rounds=[DeliberationRoundView(**_round_view(r)) for r in rounds],
        pending_proposal_count=len(pending_proposals),
        pending_nomination_count=len(pending_nominations),
        pending_proposals=[
            DeliberationProposalView(**_proposal_view(p)) for p in pending_proposals
        ],
        pending_nominations=[
            DeliberationNominationView(**_nomination_view(n)) for n in pending_nominations
        ],
        created_at=run.created_at,
        updated_at=run.updated_at,
    )
    return _envelope(view.model_dump(by_alias=True))


@router.get("/deliberations/{deliberationRunId}/messages")
async def list_deliberation_messages(
    deliberation_run_id: UUID = Path(alias="deliberationRunId"),
    limit: int = Query(default=50, ge=1, le=200),
    before: UUID | None = Query(default=None),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = DeliberationRepository(db)
    await _require_run(repo, context.workspace_id, deliberation_run_id)
    messages = await repo.list_messages(
        context.workspace_id, deliberation_run_id, limit=limit, before_id=before
    )
    return _envelope({
        "items": [_message_view(m) for m in messages],
        "nextCursor": str(messages[0].id) if messages else None,
    })


@router.get("/deliberations/{deliberationRunId}/outcome")
async def get_deliberation_outcome(
    deliberation_run_id: UUID = Path(alias="deliberationRunId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    repo = DeliberationRepository(db)
    await _require_run(repo, context.workspace_id, deliberation_run_id)
    outcome = await repo.get_outcome(context.workspace_id, deliberation_run_id)
    if outcome is None:
        # Honest 404 until the verdict round produces the outcome.
        raise case_not_found()
    return _envelope(_outcome_view(outcome))


def _outcome_view(outcome: DeliberationOutcome) -> dict[str, Any]:
    return DeliberationOutcomeView(
        id=str(outcome.id),
        deliberation_run_id=str(outcome.deliberation_run_id),
        condition_projections=outcome.condition_projections,
        flip_conditions=outcome.flip_conditions,
        dissent_log=outcome.dissent_log,
        assumption_ledger=outcome.assumption_ledger,
        disclaimer=outcome.disclaimer,
        created_at=outcome.created_at,
    ).model_dump(by_alias=True)


# --- SSE -------------------------------------------------------------------------


def _event_envelope(event: DeliberationEvent) -> dict[str, Any]:
    return {
        "id": str(event.id),
        "sequence": event.sequence,
        "workspaceId": str(event.workspace_id),
        "decisionCaseId": str(event.decision_case_id),
        "deliberationRunId": str(event.deliberation_run_id),
        "category": event.category.value,
        "type": event.type,
        "originMode": event.origin_mode.value,
        "sourceOriginModes": [m.value for m in event.source_origin_modes],
        "createdAt": event.created_at.isoformat(),
        "payload": dict(event.payload),
    }


def _sse_frame(event: DeliberationEvent) -> str:
    envelope = json.dumps(_event_envelope(event), ensure_ascii=False)
    return f"id: {str(event.id)}\nevent: {event.category.value}\ndata: {envelope}\n\n"


@router.get("/deliberations/{deliberationRunId}/events")
async def stream_deliberation_events(
    request: Request,
    deliberation_run_id: UUID = Path(alias="deliberationRunId"),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    repo = DeliberationRepository(db)
    await _require_run(repo, context.workspace_id, deliberation_run_id)
    start_after = 0
    if last_event_id:
        for event in await repo.list_events_after(context.workspace_id, deliberation_run_id, 0):
            if str(event.id) == last_event_id:
                start_after = event.sequence
                break

    async def event_stream():
        cursor = start_after
        while True:
            events = await repo.list_events_after(
                context.workspace_id, deliberation_run_id, cursor
            )
            for event in events:
                cursor = event.sequence
                yield _sse_frame(event)
            current = await repo.get_run(context.workspace_id, deliberation_run_id)
            if current is None:
                return
            if DeliberationRunStatus(current.status) in _STREAM_CLOSING_STATUSES:
                tail = await repo.list_events_after(
                    context.workspace_id, deliberation_run_id, cursor
                )
                for event in tail:
                    cursor = event.sequence
                    yield _sse_frame(event)
                return
            if await request.is_disconnected():
                return
            await asyncio.sleep(_SSE_POLL_SECONDS)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# --- writes (interventions + decisions) ------------------------------------------


@router.post("/deliberations/{deliberationRunId}/interventions")
async def post_deliberation_intervention(
    body: DeliberationInterventionRequest,
    deliberation_run_id: UUID = Path(alias="deliberationRunId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
    _: None = Depends(require_csrf),
) -> dict[str, Any]:
    repo = DeliberationRepository(db)
    service = _service(repo)
    try:
        result = await service.intervene(
            workspace_id=context.workspace_id,
            run_id=deliberation_run_id,
            user_id=context.user_id,
            kind=body.kind,
            text=body.text,
            target_factor_id=body.target_factor_id,
            subjective_factor=(
                body.subjective_factor.model_dump(by_alias=True)
                if body.subjective_factor is not None
                else None
            ),
        )
    except DeliberationNotFound:
        raise case_not_found() from None
    except DeliberationServiceError as error:
        raise ApiFailure(error.code, error.message, http_status=error.http_status) from error
    await db.commit()
    return _envelope(result)


@router.post("/deliberations/{deliberationRunId}/proposals/{proposalId}/decision")
async def post_proposal_decision(
    body: ProposalDecisionRequest,
    deliberation_run_id: UUID = Path(alias="deliberationRunId"),
    proposal_id: UUID = Path(alias="proposalId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
    _: None = Depends(require_csrf),
) -> dict[str, Any]:
    repo = DeliberationRepository(db)
    service = _service(repo)
    try:
        proposal = await service.decide_proposal(
            workspace_id=context.workspace_id,
            run_id=deliberation_run_id,
            proposal_id=proposal_id,
            decision=body.decision,
        )
    except DeliberationNotFound:
        raise case_not_found() from None
    except DeliberationServiceError as error:
        raise ApiFailure(error.code, error.message, http_status=error.http_status) from error
    await db.commit()
    return _envelope(_proposal_view(proposal))


@router.post("/deliberations/{deliberationRunId}/nominations/{nominationId}/decision")
async def post_nomination_decision(
    body: NominationDecisionRequest,
    deliberation_run_id: UUID = Path(alias="deliberationRunId"),
    nomination_id: UUID = Path(alias="nominationId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
    _: None = Depends(require_csrf),
) -> dict[str, Any]:
    repo = DeliberationRepository(db)
    service = _service(repo)
    try:
        nomination = await service.decide_nomination(
            workspace_id=context.workspace_id,
            run_id=deliberation_run_id,
            nomination_id=nomination_id,
            decision=body.decision,
            user_id=context.user_id,
            subjective_factor=(
                body.subjective_factor.model_dump(by_alias=True)
                if body.subjective_factor is not None
                else None
            ),
        )
    except DeliberationNotFound:
        raise case_not_found() from None
    except DeliberationServiceError as error:
        raise ApiFailure(error.code, error.message, http_status=error.http_status) from error
    await db.commit()
    return _envelope(_nomination_view(nomination))
