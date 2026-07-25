"""Canonical case list/create/read routes (Task 4, first-priority delivery).

Frozen wire contract: docs/product-plan/10-api-and-events.md "创建决策项目" —
POST /cases, GET /cases (workspace-bounded list with status filters + cursor),
GET /cases/{decisionCaseId} (canonical DecisionCase + confirmed DossierVersion
reference + caseVersion + ArgumentNode[] projection), and
GET /cases/{decisionCaseId}/versions/{version}.

The router is RELATIVE; mounting under ``workspace_router`` belongs to the
Contract Lead wave. Once mounted, the frontend may flip
``caseListRouteAvailable``.
"""

from __future__ import annotations

import base64
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import DecisionCase, DecisionSubject
from app.security.csrf import require_csrf
from app.security.envelope import ApiFailure, workspace_not_found
from app.tenancy.context import (
    WorkspaceContext,
    require_capability,
    require_workspace_context,
)
from app.types import (
    CaseOperationalStatus,
    DecisionLifecycleStage,
    DecisionType,
    EntryStatus,
    WorkspaceCapability,
)

from app.dossiers.routes import generate_slug
from app.dossiers.schemas import (
    ArgumentNodeData,
    CaseCreateData,
    CaseCreateRequest,
    CaseDetailData,
    CaseListData,
    CaseListItem,
    CaseVersionData,
)
from app.dossiers.service import DossierService

router = APIRouter(tags=["cases"])

# Frozen clarifying questions from the canonical create-case example (10-api).
_CLARIFYING_QUESTIONS = [
    "这个决定最重要的成功指标是什么？",
    "哪些风险是不可接受的？",
    "目前已有的一手客户证据有哪些？",
]

_DECISION_TYPE_KEYWORDS: list[tuple[DecisionType, tuple[str, ...]]] = [
    (DecisionType.MARKET_DIRECTION, ("市场方向", "哪个市场", "还是家庭", "priorit", "market direction")),
    (DecisionType.MARKET_ENTRY, ("进入市场", "market entry", "要不要进入")),
    (DecisionType.TECHNOLOGY_ROUTE, ("技术路线", "technology route", "技术方案")),
    (DecisionType.RESOURCE_ALLOCATION, ("资源分配", "resource allocation", "预算分配")),
]


def infer_decision_type(question: str) -> DecisionType:
    """Deterministic keyword inference; unknown when nothing matches."""

    lowered = question.lower()
    for decision_type, keywords in _DECISION_TYPE_KEYWORDS:
        if any(keyword in lowered or keyword in question for keyword in keywords):
            return decision_type
    return DecisionType.UNKNOWN


def derive_title(question: str) -> str:
    """Deterministic short title from the decision question."""

    stem = question.strip().replace("\n", " ")
    return (stem[:60] + "…") if len(stem) > 60 else stem


def _envelope(data: Any, event_id: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"ok": True, "data": data}
    if event_id is not None:
        body["eventId"] = event_id
    return body


def _encode_cursor(updated_at: datetime, case_id: UUID) -> str:
    raw = f"{updated_at.isoformat()}|{case_id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        timestamp, case_id = raw.split("|", 1)
        return datetime.fromisoformat(timestamp), UUID(case_id)
    except (ValueError, TypeError) as exc:
        raise ApiFailure(
            "VALIDATION_FAILED",
            "The pagination cursor is malformed.",
            http_status=422,
        ) from exc


@router.post("/cases", status_code=201, dependencies=[Depends(require_csrf)])
async def create_case(
    body: CaseCreateRequest,
    context: WorkspaceContext = Depends(require_capability(WorkspaceCapability.CONTRIBUTE)),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    service = DossierService(db, workspace_id=context.workspace_id)

    if body.decision_subject_id is not None:
        subject = await service.repository.get_subject(
            context.workspace_id, body.decision_subject_id
        )
        if subject is None:
            raise workspace_not_found()
    else:
        # No explicit subject: create the long-term memory boundary alongside
        # the case (subject creation is itself a frozen canonical API).
        title = derive_title(body.decision_question)
        subject = DecisionSubject(
            workspace_id=context.workspace_id,
            name=title[:200],
            slug=generate_slug(title, suffix=uuid4().hex[:8]),
            description=body.initial_context,
        )
        db.add(subject)
        await db.flush()

    case = DecisionCase(
        workspace_id=context.workspace_id,
        decision_subject_id=subject.id,
        title=derive_title(body.decision_question),
        decision_question=body.decision_question,
        inferred_decision_type=infer_decision_type(body.decision_question),
        summary={"short": body.initial_context or "", "openQuestions": [], "keyAssumptions": []},
    )
    db.add(case)
    await db.flush()
    await db.commit()

    data = CaseCreateData(
        decisionCaseId=case.decision_case_id,
        version=case.current_version,
        title=case.title,
        inferredDecisionType=case.inferred_decision_type,
        clarifyingQuestions=list(_CLARIFYING_QUESTIONS),
    )
    return _envelope(data.model_dump(by_alias=True, mode="json"), "evt_case_created")


@router.get("/cases")
async def list_cases(
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
    status: DecisionLifecycleStage | None = Query(default=None),
    operational_status: CaseOperationalStatus | None = Query(
        default=None, alias="operationalStatus"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
) -> dict[str, Any]:
    # Workspace-bounded by construction: the filter is part of the query,
    # never applied after a global scan (10-api 列表查询纪律).
    statement = (
        select(DecisionCase)
        .where(DecisionCase.workspace_id == context.workspace_id)
        .order_by(DecisionCase.updated_at.desc(), DecisionCase.decision_case_id.desc())
        .limit(limit + 1)
    )
    if status is not None:
        statement = statement.where(DecisionCase.status == status)
    if operational_status is not None:
        statement = statement.where(DecisionCase.operational_status == operational_status)
    if cursor is not None:
        after_updated, after_id = _decode_cursor(cursor)
        statement = statement.where(
            (DecisionCase.updated_at < after_updated)
            | (
                (DecisionCase.updated_at == after_updated)
                & (DecisionCase.decision_case_id < after_id)
            )
        )
    rows = list(await db.scalars(statement))
    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        tail = rows[-1]
        next_cursor = _encode_cursor(tail.updated_at, tail.decision_case_id)
    data = CaseListData(
        items=[
            CaseListItem(
                decisionCaseId=row.decision_case_id,
                title=row.title,
                status=row.status,
                currentVersion=row.current_version,
                updatedAt=row.updated_at,
            )
            for row in rows
        ],
        nextCursor=next_cursor,
    )
    return _envelope(data.model_dump(by_alias=True, mode="json"))


def build_argument_nodes(case: DecisionCase, entries: list) -> list[ArgumentNodeData]:
    """Project the confirmed canonical state onto ArgumentNode[] (06-data-model).

    The tree is derived from the same canonical projection the dossier panel
    reads — no second set of tree node DTOs is maintained. The decision
    question is the root claim; confirmed judgments become supports, confirmed
    assumptions/unknowns become assumption/risk leaves.
    """

    root_id = f"arg-root-{case.decision_case_id}"
    nodes: list[ArgumentNodeData] = [
        ArgumentNodeData(
            id=root_id,
            workspaceId=case.workspace_id,
            decisionCaseId=case.decision_case_id,
            type="claim",
            text=case.decision_question,
            supportScore=0.5,
            status="confirmed",
        )
    ]
    type_map = {
        "judgment": "support",
        "fact": "support",
        "evidence": "support",
        "constraint": "risk",
        "assumption": "assumption",
        "unknown": "risk",
        "preference": "support",
    }
    for entry in entries:
        if entry.status != EntryStatus.CONFIRMED:
            continue
        nodes.append(
            ArgumentNodeData(
                id=f"arg-entry-{entry.id}",
                workspaceId=case.workspace_id,
                decisionCaseId=case.decision_case_id,
                parentId=root_id,
                type=type_map.get(entry.statement_type.value, "support"),
                text=entry.content,
                supportScore=0.5,
                status="confirmed",
            )
        )
    return nodes


@router.get("/cases/{decisionCaseId}")
async def read_case(
    decision_case_id: UUID = Path(alias="decisionCaseId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
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
    confirmed_version = await service.repository.current_dossier_version(
        context.workspace_id, subject.dossier_id
    )
    dossier_snapshot_hash: str | None = None
    version_row = await service.repository.get_dossier_version(
        context.workspace_id, subject.dossier_id, confirmed_version
    )
    if version_row is not None:
        dossier_snapshot_hash = version_row.snapshot_hash
    entries = await service.repository.list_confirmed_entries(
        context.workspace_id,
        case.decision_subject_id,
        decision_case_id=decision_case_id,
    )
    data = CaseDetailData(
        decisionCaseId=case.decision_case_id,
        decisionSubjectId=case.decision_subject_id,
        title=case.title,
        decisionQuestion=case.decision_question,
        inferredDecisionType=case.inferred_decision_type,
        status=case.status,
        operationalStatus=case.operational_status,
        caseVersion=case.current_version,
        confirmedDossierVersion=confirmed_version,
        confirmedDossierSnapshotHash=dossier_snapshot_hash,
        argumentNodes=build_argument_nodes(case, entries),
        createdAt=case.created_at,
        updatedAt=case.updated_at,
    )
    return _envelope(data.model_dump(by_alias=True, mode="json"))


@router.get("/cases/{decisionCaseId}/versions/{version}")
async def read_case_version(
    decision_case_id: UUID = Path(alias="decisionCaseId"),
    version: int = Path(ge=1),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    service = DossierService(db, workspace_id=context.workspace_id)
    case = await service.repository.get_case(context.workspace_id, decision_case_id)
    if case is None:
        raise workspace_not_found()
    row = await service.repository.get_case_version(
        context.workspace_id, decision_case_id, version
    )
    if row is None:
        raise workspace_not_found()
    data = CaseVersionData(
        decisionCaseId=row.decision_case_id,
        version=row.version,
        parentVersion=row.parent_version,
        dossierVersion=row.dossier_version,
        dossierSnapshotHash=row.dossier_snapshot_hash,
        snapshot=row.snapshot,
        snapshotHash=row.snapshot_hash,
        reason=row.reason,
        createdBy=row.created_by,
        createdAt=row.created_at,
    )
    return _envelope(data.model_dump(by_alias=True, mode="json"))
