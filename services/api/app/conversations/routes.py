"""Conversation HTTP handlers: case messages + quick analyses (Task 5).

Relative router; mounting under ``workspace_router`` belongs to the Contract
Lead wave. POST /cases/{decisionCaseId}/messages persists the raw user text,
generates the assistant reply through the provider-neutral ModelProvider seam,
persists the assistant's final text with provider/model/token metadata, then
runs candidate extraction which writes ONLY ``candidate_revisions`` (plus a
``conversation_revisions`` link). The endpoint never bumps a CaseVersion —
frozen contract 10-api "讨论消息".

``reasoning_content`` never reaches this module: the provider strips it inside
one call chain and no persistence/logging path here could carry it.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import httpx

from app.agents.errors import StructuredOutputError
from app.agents.model_provider import (
    ModelMessage,
    ModelProvider,
    build_model_provider_from_env,
)
from app.db import get_session
from app.dossiers.routes import map_dossier_error
from app.dossiers.service import DossierService, ProposeEntry
from app.models import Conversation, DomainEvent, Message
from app.security.csrf import require_csrf
from app.security.envelope import ApiFailure, workspace_not_found
from app.tenancy.context import WorkspaceContext, require_capability
from app.types import (
    CandidateSourceType,
    DomainEventActor,
    MessageRole,
    WorkspaceCapability,
)

from .memory_extractor import MemoryExtractor
from .quick_analysis import generate_quick_analysis, quick_analysis_projection
from .schemas import (
    CaseMessageData,
    CaseMessageRequest,
    ProposedPatchData,
    QuickAnalysisRequest,
)

router = APIRouter(tags=["conversations"])

_REPLY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["assistantMessage"],
    "properties": {"assistantMessage": {"type": "string"}},
}


def get_model_provider() -> ModelProvider:
    """App-level dependency; tests override it with a FixtureModelProvider."""

    return build_model_provider_from_env()


def _model_failure(exc: StructuredOutputError) -> ApiFailure:
    return ApiFailure(
        "MODEL_OUTPUT_INVALID",
        "The model reply failed structural validation after one repair retry.",
        http_status=502,
        retryable=True,
        details={"reason": exc.code},
    )


def _model_transport_failure(exc: httpx.HTTPError) -> ApiFailure:
    # Live-provider transport faults (TLS resets, mid-stream drops, timeouts)
    # must surface as an honest retryable envelope, never an unhandled 500
    # with an empty body (QC finding: composer POST crashed bare on a
    # DeepSeek cold-TLS ConnectError).
    return ApiFailure(
        "MODEL_UPSTREAM_UNAVAILABLE",
        "模型服务暂时不可达，请稍后重试。",
        http_status=502,
        retryable=True,
        details={"reason": type(exc).__name__},
    )


async def _get_case_conversation(
    db: AsyncSession, workspace_id: UUID, case
) -> Conversation:
    """Find or create the case-bound conversation (same Subject by FK)."""

    conversation = await db.scalar(
        select(Conversation)
        .where(
            Conversation.workspace_id == workspace_id,
            Conversation.decision_case_id == case.decision_case_id,
        )
        .order_by(Conversation.created_at)
        .limit(1)
    )
    if conversation is None:
        conversation = Conversation(
            workspace_id=workspace_id,
            decision_subject_id=case.decision_subject_id,
            decision_case_id=case.decision_case_id,
        )
        db.add(conversation)
        await db.flush()
    return conversation


@router.post(
    "/cases/{decisionCaseId}/messages",
    dependencies=[Depends(require_csrf)],
)
async def post_case_message(
    body: CaseMessageRequest,
    decision_case_id: UUID = Path(alias="decisionCaseId"),
    context: WorkspaceContext = Depends(require_capability(WorkspaceCapability.CONTRIBUTE)),
    db: AsyncSession = Depends(get_session),
    provider: ModelProvider = Depends(get_model_provider),
) -> dict[str, Any]:
    service = DossierService(db, workspace_id=context.workspace_id)
    case = await service.repository.get_case(context.workspace_id, decision_case_id)
    if case is None:
        raise workspace_not_found()
    subject = await service.repository.get_subject(
        context.workspace_id, case.decision_subject_id
    )
    if subject is None:
        raise workspace_not_found()
    base_dossier_version = await service.repository.current_dossier_version(
        context.workspace_id, subject.dossier_id
    )
    conversation = await _get_case_conversation(db, context.workspace_id, case)

    # 1. Persist the raw user message.
    user_message = Message(
        workspace_id=context.workspace_id,
        conversation_id=conversation.id,
        decision_subject_id=case.decision_subject_id,
        decision_case_id=case.decision_case_id,
        role=MessageRole.USER,
        content=body.message,
    )
    db.add(user_message)
    await db.flush()

    # 2. Assistant reply over the provider seam (final text only; any
    #    reasoning_content was already dropped inside the provider).
    try:
        completion = await provider.complete_structured(
            system=(
                "You are the decision assistant. Acknowledge the user's message, "
                "state what you would record as candidate dossier changes, and "
                "name what still needs confirmation. Reply with ONLY a JSON "
                'object like {"assistantMessage": "..."}.'
            ),
            messages=[ModelMessage(role="user", content=body.message)],
            schema=_REPLY_SCHEMA,
            tools=None,
            request_model="",
        )
        completion.require_non_empty()
    except StructuredOutputError as exc:
        raise _model_failure(exc)
    except httpx.HTTPError as exc:
        raise _model_transport_failure(exc)
    assistant_text = str(completion.content.get("assistantMessage", "")).strip()
    if not assistant_text:
        raise _model_failure(StructuredOutputError("assistantMessage missing"))

    assistant_message = Message(
        workspace_id=context.workspace_id,
        conversation_id=conversation.id,
        decision_subject_id=case.decision_subject_id,
        decision_case_id=case.decision_case_id,
        role=MessageRole.ASSISTANT,
        content=assistant_text,
        provider=provider.name,
        request_model_id=completion.request_model,
        response_model_id=completion.response_model,
        provider_response_version=completion.response_model,
        token_metadata={},
        cost_metadata={},
    )
    db.add(assistant_message)
    await db.flush()

    # 3. Candidate extraction after the reply — writes candidate_revisions only.
    candidate_id: UUID | None = None
    patch = ProposedPatchData()
    if body.propose_structured_updates:
        extractor = MemoryExtractor(provider=provider)
        try:
            extraction = await extractor.extract(body.message, case_bound=True)
        except StructuredOutputError as exc:
            raise _model_failure(exc)
        except httpx.HTTPError as exc:
            raise _model_transport_failure(exc)
        proposals = extraction.to_proposals(case_bound=True)
        if proposals:
            try:
                candidate = await service.propose(
                    ProposeEntry(
                        workspace_id=context.workspace_id,
                        decision_subject_id=case.decision_subject_id,
                        decision_case_id=case.decision_case_id,
                        proposals=proposals,
                        source_type=CandidateSourceType.CONVERSATION,
                        source_id=user_message.id,
                        base_dossier_version=base_dossier_version,
                        base_case_version=case.current_version,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - mapped to envelope codes
                raise map_dossier_error(exc)
            candidate_id = candidate.id
            # Link the source message to the candidate on the audit stream
            # (the frozen schema has no conversation_revisions table).
            db.add(
                DomainEvent(
                    workspace_id=context.workspace_id,
                    aggregate_type="conversation_message",
                    aggregate_id=user_message.id,
                    event_type="conversation.candidate_extracted",
                    actor=DomainEventActor.WORKER,
                    payload={
                        "conversationId": str(conversation.id),
                        "candidateRevisionId": str(candidate.id),
                    },
                )
            )
            counts = {"constraint": 0, "fact": 0, "assumption": 0, "unknown": 0, "judgment": 0}
            for proposal in proposals:
                statement_type = proposal["entry"]["statementType"]
                if statement_type in counts:
                    counts[statement_type] += 1
            patch = ProposedPatchData(
                constraintsAdded=counts["constraint"],
                factsAdded=counts["fact"],
                assumptionsAdded=counts["assumption"],
                unknownsAdded=counts["unknown"],
            )
    await db.commit()

    data = CaseMessageData(
        candidateRevisionId=candidate_id,
        baseDossierVersion=base_dossier_version,
        baseCaseVersion=case.current_version,
        assistantMessage=assistant_text,
        proposedPatch=patch,
    )
    return {"ok": True, "data": data.model_dump(by_alias=True, mode="json")}


@router.post(
    "/conversations/{conversationId}/quick-analyses",
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
async def create_quick_analysis(
    body: QuickAnalysisRequest | None = None,
    conversation_id: UUID = Path(alias="conversationId"),
    context: WorkspaceContext = Depends(require_capability(WorkspaceCapability.CONTRIBUTE)),
    db: AsyncSession = Depends(get_session),
    provider: ModelProvider = Depends(get_model_provider),
) -> dict[str, Any]:
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.workspace_id == context.workspace_id,
            Conversation.id == conversation_id,
        )
    )
    if conversation is None:
        raise workspace_not_found()

    service = DossierService(db, workspace_id=context.workspace_id)
    if conversation.decision_subject_id is None:
        raise workspace_not_found()
    subject = await service.repository.get_subject(
        context.workspace_id, conversation.decision_subject_id
    )
    if subject is None:
        raise workspace_not_found()
    source_dossier_version = await service.repository.current_dossier_version(
        context.workspace_id, subject.dossier_id
    )
    # Confirmed dossier entries only — candidates are structurally excluded.
    confirmed = await service.repository.list_confirmed_entries(
        context.workspace_id,
        conversation.decision_subject_id,
        decision_case_id=conversation.decision_case_id,
    )
    try:
        result = await generate_quick_analysis(
            db,
            provider,
            conversation=conversation,
            confirmed_entries=confirmed,
            source_dossier_version=source_dossier_version,
            question=body.question if body is not None else None,
        )
    except StructuredOutputError as exc:
        raise _model_failure(exc)
    except httpx.HTTPError as exc:
        raise _model_transport_failure(exc)
    await db.commit()
    return {"ok": True, "data": quick_analysis_projection(result)}
