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
from app.agents.conversation_fixtures import with_conversation_fixture_fallback
from app.agents.model_provider import (
    ModelMessage,
    ModelProvider,
    build_model_provider_from_env,
    build_model_provider_from_connector,
)
from app.db import get_session
from app.dossiers.routes import map_dossier_error
from app.dossiers.service import DossierService, ProposeEntry
from app.models import Conversation, DomainEvent, Message, WorkspaceConnector
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
    """App-level dependency; tests override it with a FixtureModelProvider.

    A fixture DEPLOYMENT (no model key) gets the deterministic conversation
    fallback bound here, so chat and clarifier degrade honestly instead of
    502-ing on every message. Test overrides bypass this function entirely.
    """

    return with_conversation_fixture_fallback(build_model_provider_from_env())


async def _resolve_workspace_provider(
    workspace_id: UUID, db: AsyncSession
) -> ModelProvider | None:
    """Load workspace custom model connector and build a provider if configured."""

    from app.connectors.crypto import crypto_available, decrypt_secret

    if not crypto_available():
        return None
    row = (
        await db.execute(
            select(WorkspaceConnector).where(
                WorkspaceConnector.workspace_id == workspace_id,
                WorkspaceConnector.provider == "model",
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    try:
        api_key = decrypt_secret(
            row.ciphertext, row.nonce, row.key_version,
            workspace_id=str(workspace_id), provider="model",
        )
    except Exception:
        return None
    config = row.config or {}
    base_url = config.get("base_url", "")
    model_name = config.get("model_name", "")
    if not base_url or not model_name:
        return None
    return build_model_provider_from_connector(
        base_url=base_url, api_key=api_key, model_name=model_name,
    )


def _model_failure(exc: StructuredOutputError) -> ApiFailure:
    return ApiFailure(
        "MODEL_OUTPUT_INVALID",
        "模型未能给出符合结构要求的回应（已自动重试一次）。已保存的内容不受影响，可稍后重试。",
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


@router.get("/cases/{decisionCaseId}/messages")
async def list_case_messages(
    decision_case_id: UUID = Path(alias="decisionCaseId"),
    context: WorkspaceContext = Depends(require_capability(WorkspaceCapability.CONTRIBUTE)),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return persisted conversation messages for one case (most recent 50)."""

    rows = (
        await db.execute(
            select(Message)
            .where(
                Message.workspace_id == context.workspace_id,
                Message.decision_case_id == decision_case_id,
            )
            .order_by(Message.created_at)
            .limit(50)
        )
    ).scalars().all()
    items = [
        {
            "role": msg.role.value if hasattr(msg.role, "value") else str(msg.role),
            "content": msg.content,
            "createdAt": msg.created_at.isoformat() if msg.created_at else None,
        }
        for msg in rows
    ]
    return {"ok": True, "data": {"items": items}}


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
    # Prefer workspace-configured model over env default
    ws_provider = await _resolve_workspace_provider(context.workspace_id, db)
    if ws_provider is not None:
        provider = ws_provider

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
    # The note must survive a model failure: commit it BEFORE the provider
    # call, otherwise the dependency-scoped session rolls it back and the UI's
    # "已发送" becomes a lie (the exact defect reported in the alpha test).
    await db.commit()

    # 2. Assistant reply over the provider seam (final text only; any
    #    reasoning_content was already dropped inside the provider).
    try:
        completion = await provider.complete_structured(
            system=(
                "你是 Ludus 决策助手。你的职责是帮助决策人厘清问题边界、暴露假设、"
                "识别关键取舍。\n\n"
                "行为规则：\n"
                "1. 始终使用用户的语言回复（用户中文你就中文）。\n"
                "2. 认真倾听用户的判断、担忧和追问，回应时：\n"
                "   - 确认你理解了什么\n"
                "   - 指出你会记录为候选档案变更的内容（事实/约束/假设/未知项）\n"
                "   - 追问仍需确认的关键信息\n"
                "3. 不要给出最终结论或建议——那是深度分析的工作。\n"
                "4. 如果用户的表述暗含未说出的假设或风险，温和地指出。\n"
                "5. 保持简洁、具体、有建设性。不说废话、不重复用户原文。\n\n"
                "输出格式：只输出一个 JSON 对象 {\"assistantMessage\": \"你的回复\"}，"
                "不要输出其他任何内容。"
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
    # Extraction is a best-effort ENRICHMENT: if the model's candidate JSON
    # fails the strict schema (or the upstream hiccups), the user still gets
    # the persisted note + assistant reply with zero candidates this turn
    # (QC finding: a strict-schema miss here was failing the WHOLE message
    # POST with 502 even though the reply had already succeeded).
    candidate_id: UUID | None = None
    patch = ProposedPatchData()
    extraction = None
    if body.propose_structured_updates:
        extractor = MemoryExtractor(provider=provider)
        try:
            extraction = await extractor.extract(body.message, case_bound=True)
        except (StructuredOutputError, httpx.HTTPError):
            extraction = None
    if extraction is not None:
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

    # Best-effort profile extraction in a SEPARATE session (the request session
    # closes when the response returns, so a fire-and-forget task cannot reuse it).
    import asyncio
    asyncio.ensure_future(_update_case_profiles(
        provider, context.workspace_id, decision_case_id
    ))

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


# --- Profile extraction + read endpoint ----------------------------------------

from .profile_extractor import extract_profiles  # noqa: E402


async def _update_case_profiles(
    provider: ModelProvider,
    workspace_id: UUID,
    decision_case_id: UUID,
) -> None:
    """Best-effort: extract profiles from history and upsert.

    Uses its own session because the request session is closed by the time
    this fire-and-forget coroutine runs.
    """
    import logging
    from app.db import async_session_factory

    try:
        async with async_session_factory() as db:
            rows = (
                await db.execute(
                    select(Message)
                    .where(
                        Message.workspace_id == workspace_id,
                        Message.decision_case_id == decision_case_id,
                    )
                    .order_by(Message.created_at)
                    .limit(50)
                )
            ).scalars().all()
            if not rows:
                return
            messages = [
                {"role": msg.role.value if hasattr(msg.role, "value") else str(msg.role),
                 "content": msg.content}
                for msg in rows
            ]
            profiles = await extract_profiles(provider, messages)
            if profiles is None:
                return
            for profile_type, content in [
                ("decision_maker", profiles.get("decisionMaker", {})),
                ("question", profiles.get("question", {})),
            ]:
                existing = (
                    await db.execute(
                        sa_text(
                            "SELECT 1 FROM case_profiles "
                            "WHERE workspace_id = :ws AND decision_case_id = :cid AND profile_type = :pt"
                        ),
                        {"ws": workspace_id, "cid": decision_case_id, "pt": profile_type},
                    )
                ).scalar_one_or_none()
                import json as _json
                if existing:
                    await db.execute(
                        sa_text(
                            "UPDATE case_profiles SET content = CAST(:content AS jsonb), "
                            "version = version + 1, updated_at = now() "
                            "WHERE workspace_id = :ws AND decision_case_id = :cid "
                            "AND profile_type = :pt"
                        ),
                        {"content": _json.dumps(content, ensure_ascii=False),
                         "ws": workspace_id, "cid": decision_case_id, "pt": profile_type},
                    )
                else:
                    await db.execute(
                        sa_text(
                            "INSERT INTO case_profiles (workspace_id, decision_case_id, profile_type, content) "
                            "VALUES (:ws, :cid, :pt, CAST(:content AS jsonb))"
                        ),
                        {"ws": workspace_id, "cid": decision_case_id, "pt": profile_type,
                         "content": _json.dumps(content, ensure_ascii=False)},
                    )
            await db.commit()
    except Exception:
        logging.getLogger(__name__).warning(
            "profile extraction failed for case %s", decision_case_id, exc_info=True
        )


from sqlalchemy import text as sa_text  # noqa: E402


@router.get("/cases/{decisionCaseId}/profiles")
async def get_case_profiles(
    decision_case_id: UUID = Path(alias="decisionCaseId"),
    context: WorkspaceContext = Depends(require_capability(WorkspaceCapability.CONTRIBUTE)),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return the latest extracted profiles for one case."""

    rows = (
        await db.execute(
            sa_text(
                "SELECT profile_type, content, version FROM case_profiles "
                "WHERE workspace_id = :ws AND decision_case_id = :cid"
            ),
            {"ws": context.workspace_id, "cid": decision_case_id},
        )
    ).all()
    result: dict[str, Any] = {}
    for row in rows:
        result[row[0]] = {"content": row[1], "version": row[2]}
    return {"ok": True, "data": result}
