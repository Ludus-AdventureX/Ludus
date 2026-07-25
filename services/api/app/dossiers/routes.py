"""Dossier-side HTTP handlers: subjects + candidate review (Task 4).

The router is RELATIVE. Mounting under ``workspace_router`` (the only owner of
``/api/workspaces/{workspaceId}`` and ``require_workspace_context``) belongs to
the Contract Lead's integration wave; this module performs no membership
parsing of its own. Every scope denial collapses into the uniform 404.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import DecisionSubject
from app.security.csrf import require_csrf
from app.security.envelope import ApiFailure, workspace_not_found
from app.tenancy.context import (
    WorkspaceContext,
    require_capability,
    require_workspace_context,
)
from app.types import WorkspaceCapability

from .schemas import (
    CandidateConfirmData,
    CandidateConfirmRequest,
    CandidateData,
    CandidateListData,
    CandidateRejectData,
    CandidateRejectRequest,
    SubjectCreateRequest,
    SubjectData,
)
from .service import (
    CandidateNotReviewableError,
    ConfirmEntry,
    DossierNotFoundError,
    DossierService,
    DossierVersionConflictError,
    RejectEntry,
)

router = APIRouter(tags=["dossiers"])


def map_dossier_error(exc: Exception) -> ApiFailure:
    """Type/code-based mapping only; scope denials collapse into uniform 404."""

    if isinstance(exc, DossierNotFoundError):
        return workspace_not_found()
    if isinstance(exc, DossierVersionConflictError):
        return ApiFailure(
            "DOSSIER_VERSION_CONFLICT",
            "The base version is stale; reload the dossier and retry.",
            http_status=409,
            details={"expected": exc.expected, "actual": exc.actual},
        )
    if isinstance(exc, CandidateNotReviewableError):
        return ApiFailure(
            "CANDIDATE_ALREADY_REVIEWED",
            "This candidate revision has already been reviewed.",
            http_status=409,
        )
    raise exc


def _envelope(data: Any, event_id: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"ok": True, "data": data}
    if event_id is not None:
        body["eventId"] = event_id
    return body


def generate_slug(name: str, *, suffix: str) -> str:
    """Server-generated stable slug (10-api: client MUST NOT send slug)."""

    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    stem = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-") or "subject"
    return f"{stem[:80]}-{suffix}"


@router.post("/subjects", status_code=201, dependencies=[Depends(require_csrf)])
async def create_subject(
    body: SubjectCreateRequest,
    context: WorkspaceContext = Depends(require_capability(WorkspaceCapability.CONTRIBUTE)),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    subject = DecisionSubject(
        workspace_id=context.workspace_id,
        name=body.name,
        slug=generate_slug(body.name, suffix=uuid4().hex[:8]),
        description=body.description,
    )
    db.add(subject)
    await db.flush()
    service = DossierService(db, workspace_id=context.workspace_id)
    current_version = await service.repository.current_dossier_version(
        context.workspace_id, subject.dossier_id
    )
    await db.commit()
    data = SubjectData(
        subjectId=subject.id,
        name=subject.name,
        slug=subject.slug,
        description=subject.description,
        dossierId=subject.dossier_id,
        currentDossierVersion=current_version,
        status=subject.status.value,
        createdAt=subject.created_at,
        updatedAt=subject.updated_at,
    )
    return _envelope(data.model_dump(by_alias=True, mode="json"), "evt_subject_created")


@router.get("/subjects/{subjectId}")
async def read_subject(
    subject_id: UUID = Path(alias="subjectId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    subject = await db.scalar(
        select(DecisionSubject).where(
            DecisionSubject.workspace_id == context.workspace_id,
            DecisionSubject.id == subject_id,
        )
    )
    if subject is None:
        # Cross-workspace access is answered as not-found (10-api: 一律按不存在返回 404).
        raise workspace_not_found()
    service = DossierService(db, workspace_id=context.workspace_id)
    current_version = await service.repository.current_dossier_version(
        context.workspace_id, subject.dossier_id
    )
    data = SubjectData(
        subjectId=subject.id,
        name=subject.name,
        slug=subject.slug,
        description=subject.description,
        dossierId=subject.dossier_id,
        currentDossierVersion=current_version,
        status=subject.status.value,
        createdAt=subject.created_at,
        updatedAt=subject.updated_at,
    )
    return _envelope(data.model_dump(by_alias=True, mode="json"))


def _candidate_projection(candidate) -> dict[str, Any]:
    return CandidateData(
        candidateRevisionId=candidate.id,
        decisionCaseId=candidate.decision_case_id,
        sourceType=candidate.source_type.value,
        sourceId=str(candidate.source_id),
        baseDossierVersion=candidate.base_dossier_version,
        baseCaseVersion=candidate.base_case_version,
        proposals=candidate.proposals,
        status=candidate.status,
        reviewedAt=candidate.reviewed_at,
    ).model_dump(by_alias=True, mode="json")


@router.get("/cases/{decisionCaseId}/candidates")
async def list_candidates(
    decision_case_id: UUID = Path(alias="decisionCaseId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    service = DossierService(db, workspace_id=context.workspace_id)
    case = await service.repository.get_case(context.workspace_id, decision_case_id)
    if case is None:
        raise workspace_not_found()
    candidates = await service.repository.list_candidates(
        context.workspace_id, decision_case_id
    )
    data = CandidateListData(items=[_candidate_projection(item) for item in candidates])
    return _envelope(data.model_dump(by_alias=True, mode="json"))


@router.post(
    "/cases/{decisionCaseId}/candidates/{candidateId}/confirm",
    dependencies=[Depends(require_csrf)],
)
async def confirm_candidate(
    body: CandidateConfirmRequest,
    decision_case_id: UUID = Path(alias="decisionCaseId"),
    candidate_id: UUID = Path(alias="candidateId"),
    context: WorkspaceContext = Depends(require_capability(WorkspaceCapability.REVIEW)),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    service = DossierService(db, workspace_id=context.workspace_id)
    case = await service.repository.get_case(context.workspace_id, decision_case_id)
    candidate = await service.repository.get_candidate(context.workspace_id, candidate_id)
    if case is None or candidate is None or candidate.decision_case_id != decision_case_id:
        raise workspace_not_found()
    try:
        outcome = await service.confirm(
            ConfirmEntry(
                workspace_id=context.workspace_id,
                candidate_revision_id=candidate_id,
                base_dossier_version=body.base_dossier_version,
                base_case_version=body.base_case_version,
                statement_type_overrides=body.statement_type_overrides,
                created_by=str(context.user_id),
            )
        )
    except Exception as exc:  # noqa: BLE001 - mapped to canonical envelope codes
        raise map_dossier_error(exc)
    await db.commit()
    case_version = outcome["case_version"]
    data = CandidateConfirmData(
        candidateRevisionId=candidate_id,
        status=outcome["candidate"].status,
        dossierVersion=outcome["dossier_version"].version,
        caseVersion=case_version.version if case_version is not None else None,
        confirmedEntryIds=[entry.id for entry in outcome["entries"]],
    )
    return _envelope(
        data.model_dump(by_alias=True, mode="json"), "evt_candidate_confirmed"
    )


@router.post(
    "/cases/{decisionCaseId}/candidates/{candidateId}/reject",
    dependencies=[Depends(require_csrf)],
)
async def reject_candidate(
    body: CandidateRejectRequest | None = None,
    decision_case_id: UUID = Path(alias="decisionCaseId"),
    candidate_id: UUID = Path(alias="candidateId"),
    context: WorkspaceContext = Depends(require_capability(WorkspaceCapability.REVIEW)),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    service = DossierService(db, workspace_id=context.workspace_id)
    case = await service.repository.get_case(context.workspace_id, decision_case_id)
    candidate = await service.repository.get_candidate(context.workspace_id, candidate_id)
    if case is None or candidate is None or candidate.decision_case_id != decision_case_id:
        raise workspace_not_found()
    try:
        rejected = await service.reject(
            RejectEntry(
                workspace_id=context.workspace_id,
                candidate_revision_id=candidate_id,
                reason=body.reason if body is not None else None,
            )
        )
    except Exception as exc:  # noqa: BLE001 - mapped to canonical envelope codes
        raise map_dossier_error(exc)
    await db.commit()
    data = CandidateRejectData(candidateRevisionId=candidate_id, status=rejected.status)
    return _envelope(
        data.model_dump(by_alias=True, mode="json"), "evt_candidate_rejected"
    )
