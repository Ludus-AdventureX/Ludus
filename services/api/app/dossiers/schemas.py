"""Wire schemas for the dossier + case surface (Task 4).

Field names, statuses and envelope shapes are consumed from the frozen
``docs/product-plan/10-api-and-events.md`` / ``06-data-model.md`` contracts.
This module defines no new statuses or wire fields; database columns map to
camelCase wire names via per-field aliases only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.types import (
    CandidateRevisionStatus,
    CaseOperationalStatus,
    DecisionLifecycleStage,
    DecisionType,
    DossierScope,
    DossierStatementType,
    EntryStatus,
)


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


# ---------------------------------------------------------------------------
# Subjects
# ---------------------------------------------------------------------------


class SubjectCreateRequest(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class SubjectData(ApiModel):
    subject_id: UUID = Field(alias="subjectId")
    name: str
    slug: str
    description: str | None = None
    dossier_id: UUID = Field(alias="dossierId")
    current_dossier_version: int = Field(alias="currentDossierVersion")
    status: str
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


# ---------------------------------------------------------------------------
# Cases (frozen list/create/read shapes, 10-api "创建决策项目")
# ---------------------------------------------------------------------------


class CaseCreateRequest(ApiModel):
    decision_question: str = Field(alias="decisionQuestion", min_length=1)
    initial_context: str | None = Field(alias="initialContext", default=None)
    # Optional explicit subject binding; when omitted the service creates the
    # long-term subject transparently (subject creation is also a frozen API).
    decision_subject_id: UUID | None = Field(alias="decisionSubjectId", default=None)


class CaseCreateData(ApiModel):
    decision_case_id: UUID = Field(alias="decisionCaseId")
    version: int
    title: str
    inferred_decision_type: DecisionType = Field(alias="inferredDecisionType")
    clarifying_questions: list[str] = Field(alias="clarifyingQuestions")


class CaseListItem(ApiModel):
    decision_case_id: UUID = Field(alias="decisionCaseId")
    title: str
    status: DecisionLifecycleStage
    current_version: int = Field(alias="currentVersion")
    updated_at: datetime = Field(alias="updatedAt")


class CaseListData(ApiModel):
    items: list[CaseListItem]
    next_cursor: str | None = Field(alias="nextCursor", default=None)


class ArgumentNodeData(ApiModel):
    """Frozen ArgumentNode projection (06-data-model 论证树)."""

    id: str
    workspace_id: UUID = Field(alias="workspaceId")
    decision_case_id: UUID = Field(alias="decisionCaseId")
    option_id: str | None = Field(alias="optionId", default=None)
    parent_id: str | None = Field(alias="parentId", default=None)
    type: Literal["claim", "support", "counter", "assumption", "risk"]
    text: str
    evidence_ids: list[str] = Field(alias="evidenceIds", default_factory=list)
    assumption_ids: list[str] = Field(alias="assumptionIds", default_factory=list)
    support_score: float = Field(alias="supportScore", ge=0, le=1)
    status: Literal["draft", "confirmed", "rejected"]


class CaseDetailData(ApiModel):
    decision_case_id: UUID = Field(alias="decisionCaseId")
    decision_subject_id: UUID = Field(alias="decisionSubjectId")
    title: str
    decision_question: str = Field(alias="decisionQuestion")
    inferred_decision_type: DecisionType = Field(alias="inferredDecisionType")
    status: DecisionLifecycleStage
    operational_status: CaseOperationalStatus = Field(alias="operationalStatus")
    case_version: int = Field(alias="caseVersion")
    confirmed_dossier_version: int = Field(alias="confirmedDossierVersion")
    confirmed_dossier_snapshot_hash: str | None = Field(
        alias="confirmedDossierSnapshotHash", default=None
    )
    argument_nodes: list[ArgumentNodeData] = Field(alias="argumentNodes")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class CaseVersionData(ApiModel):
    decision_case_id: UUID = Field(alias="decisionCaseId")
    version: int
    parent_version: int | None = Field(alias="parentVersion", default=None)
    dossier_version: int = Field(alias="dossierVersion")
    dossier_snapshot_hash: str = Field(alias="dossierSnapshotHash")
    snapshot: dict[str, Any]
    snapshot_hash: str = Field(alias="snapshotHash")
    reason: str
    created_by: str = Field(alias="createdBy")
    created_at: datetime = Field(alias="createdAt")


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------


class CandidateProposalData(ApiModel):
    operation: Literal["add", "update", "reclassify", "expire"]
    entry: dict[str, Any]


class CandidateData(ApiModel):
    candidate_revision_id: UUID = Field(alias="candidateRevisionId")
    decision_case_id: UUID | None = Field(alias="decisionCaseId", default=None)
    source_type: str = Field(alias="sourceType")
    source_id: str = Field(alias="sourceId")
    base_dossier_version: int = Field(alias="baseDossierVersion")
    base_case_version: int | None = Field(alias="baseCaseVersion", default=None)
    proposals: list[CandidateProposalData]
    status: CandidateRevisionStatus
    reviewed_at: datetime | None = Field(alias="reviewedAt", default=None)


class CandidateListData(ApiModel):
    items: list[CandidateData]


class CandidateConfirmRequest(ApiModel):
    base_dossier_version: int = Field(alias="baseDossierVersion", ge=1)
    base_case_version: int | None = Field(alias="baseCaseVersion", default=None, ge=1)
    # Reviewer statement-type corrections keyed by proposal index.
    statement_type_overrides: dict[int, DossierStatementType] = Field(
        alias="statementTypeOverrides", default_factory=dict
    )


class CandidateConfirmData(ApiModel):
    candidate_revision_id: UUID = Field(alias="candidateRevisionId")
    status: CandidateRevisionStatus
    dossier_version: int = Field(alias="dossierVersion")
    case_version: int | None = Field(alias="caseVersion", default=None)
    confirmed_entry_ids: list[UUID] = Field(alias="confirmedEntryIds")


class CandidateRejectRequest(ApiModel):
    reason: str | None = None


class CandidateRejectData(ApiModel):
    candidate_revision_id: UUID = Field(alias="candidateRevisionId")
    status: CandidateRevisionStatus


# ---------------------------------------------------------------------------
# Dossier entries (projection used by the case detail / dossier panel)
# ---------------------------------------------------------------------------


class DossierEntryData(ApiModel):
    id: UUID
    decision_case_id: UUID | None = Field(alias="decisionCaseId", default=None)
    scope: DossierScope
    statement_type: DossierStatementType = Field(alias="statementType")
    content: str
    status: EntryStatus
    source_type: str = Field(alias="sourceType")
    version: int
