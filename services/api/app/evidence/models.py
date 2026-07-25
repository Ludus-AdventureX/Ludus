"""Evidence ledger persistence (Task 8, case_api_data).

Canonical shapes come from ``docs/product-plan/06-data-model.md`` (RetrievalTask,
RawArtifact, QualityAssessment, EvidenceItem) and the traceability chain in
``docs/product-plan/26-...`` section 2. Enum discipline:

- ``EvidenceVerdict`` / ``OriginMode`` are imported from ``app.types`` (sole
  canonical definitions); ``origin_mode`` reuses the existing PG enum and a new
  ``evidence_verdict`` PG enum is created by the Task 8 migration.
- ``stableToolName`` / ``sourceGrade`` / ``freshnessStatus`` have canonical
  wire literal sets in 06-data-model but no ``app.types`` enum yet; following
  the SIM-02A ``response_kind`` precedent they persist as CHECK-constrained
  strings (no parallel Python enum is invented). ``RetrievalTask.status``
  persists as a PG enum built directly from the canonical literal tuple
  (status-like columns use enums per the decision-os invariants suite) —
  still without declaring a parallel Python StrEnum. A CCR request to promote
  these sets into ``app.types`` is recorded in the Task 8 handoff.

Tenancy discipline: every table carries ``workspace_id`` plus the composite
``(workspace_id, decision_case_id)`` / ``(workspace_id, decision_case_id,
analysis_run_id)`` foreign keys used across the codebase, so tenant-scoped
SELECTs and the uniform CASE_NOT_FOUND anti-enumeration hold at the database
layer as well. RawArtifact and QualityAssessment rows are immutable by
construction (no updated_at, no update surface in the repository).
"""

from __future__ import annotations

from datetime import datetime
from typing import Final
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import (
    ORIGIN_MODE_ENUM,
    created_at_column,
    enum_type,
    json_list_column,
    uuid_primary_key,
    workspace_column,
)
from app.types import EvidenceVerdict, OriginMode

# Canonical wire literal sets (06-data-model.md); CHECK-enforced, not PG enums.
STABLE_TOOL_NAMES: Final[tuple[str, ...]] = (
    "search_web",
    "fetch_url",
    "crawl_site",
    "extract_document",
    "get_source_status",
)
RETRIEVAL_TASK_STATUSES: Final[tuple[str, ...]] = (
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
)
RAW_ARTIFACT_KINDS: Final[tuple[str, ...]] = (
    "web_page",
    "provider_result",
    "uploaded_file",
)
SOURCE_GRADES: Final[tuple[str, ...]] = (
    "L1_primary",
    "L2_reputable",
    "L3_industry",
    "L4_general",
    "L5_opinion",
    "L6_unverified",
)
FRESHNESS_STATUSES: Final[tuple[str, ...]] = ("fresh", "aging", "stale", "unknown")
# Evidence-to-evidence relation kinds served by the conflict/provenance layer.
EVIDENCE_RELATION_KINDS: Final[tuple[str, ...]] = (
    "same_source_group",
    "conflicts_with",
    "corroborates",
)

EVIDENCE_VERDICT_ENUM = enum_type(EvidenceVerdict, "evidence_verdict")

# PG enum over the canonical literal set (no parallel Python StrEnum): the
# decision-os invariants suite requires status-like columns to be enums.
RETRIEVAL_TASK_STATUS_ENUM = SAEnum(
    *RETRIEVAL_TASK_STATUSES,
    name="retrieval_task_status",
    native_enum=True,
)


def _values_sql(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class RetrievalTask(Base):
    """A single stable-tool retrieval intent inside one AnalysisRun."""

    __tablename__ = "retrieval_tasks"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_retrieval_tasks_workspace_id"),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_retrieval_tasks_workspace_case",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "analysis_run_id"],
            [
                "analysis_runs.workspace_id",
                "analysis_runs.decision_case_id",
                "analysis_runs.analysis_run_id",
            ],
            name="fk_retrieval_tasks_workspace_case_run",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            f"stable_tool_name IN ({_values_sql(STABLE_TOOL_NAMES)})",
            name="stable_tool_name_canonical",
        ),
        CheckConstraint("input_hash <> ''", name="input_hash_not_empty"),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= created_at",
            name="completed_after_created",
        ),
        Index(
            "ix_retrieval_tasks_workspace_run_status",
            "workspace_id",
            "analysis_run_id",
            "status",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    stable_tool_name: Mapped[str] = mapped_column(String(40), nullable=False)
    query_summary: Mapped[str] = mapped_column(Text, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(
        RETRIEVAL_TASK_STATUS_ENUM,
        nullable=False,
        default="queued",
        server_default="queued",
    )
    created_at: Mapped[datetime] = created_at_column()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RawArtifact(Base):
    """Immutable fetched material; always written before any reference is returned.

    ``storage_provider`` is locked to ``filesystem`` and ``storage_path`` holds
    a workspace-scoped relative pointer only (10-api export/file rules); no
    absolute disk path or raw sensitive body is ever stored on this row.
    """

    __tablename__ = "raw_artifacts"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_raw_artifacts_workspace_id"),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_raw_artifacts_workspace_case",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "analysis_run_id"],
            [
                "analysis_runs.workspace_id",
                "analysis_runs.decision_case_id",
                "analysis_runs.analysis_run_id",
            ],
            name="fk_raw_artifacts_workspace_case_run",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "retrieval_task_id"],
            ["retrieval_tasks.workspace_id", "retrieval_tasks.id"],
            name="fk_raw_artifacts_workspace_retrieval_task",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"kind IN ({_values_sql(RAW_ARTIFACT_KINDS)})",
            name="kind_canonical",
        ),
        CheckConstraint("byte_size >= 0", name="byte_size_non_negative"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256_hex"),
        CheckConstraint("storage_provider = 'filesystem'", name="storage_provider_locked"),
        CheckConstraint("storage_path <> ''", name="storage_path_not_empty"),
        CheckConstraint(
            "storage_path NOT LIKE '/%' AND storage_path NOT LIKE '%..%' "
            "AND storage_path NOT LIKE '%:%'",
            name="storage_path_workspace_relative",
        ),
        CheckConstraint(
            "analysis_run_id IS NULL OR decision_case_id IS NOT NULL",
            name="run_requires_case",
        ),
        Index("ix_raw_artifacts_workspace_run", "workspace_id", "analysis_run_id"),
        Index("ix_raw_artifacts_workspace_sha256", "workspace_id", "sha256"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    analysis_run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    retrieval_task_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    connector_call_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    original_name: Mapped[str | None] = mapped_column(String(400))
    media_type: Mapped[str] = mapped_column(String(160), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_provider: Mapped[str] = mapped_column(
        String(30), nullable=False, default="filesystem", server_default="filesystem"
    )
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    origin_mode: Mapped[OriginMode] = mapped_column(ORIGIN_MODE_ENUM, nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class QualityAssessment(Base):
    """Orthogonal quality dimensions plus the blocking verdict for one artifact.

    The nine review dimensions map onto canonical fields as: authenticity,
    relevance, freshness, applicability, independence, extraction_reliability
    (numeric scores), bias -> bias_flags[], completeness ->
    completeness_warnings[], conflict -> conflict_group_ids[];
    ``source_quality`` carries the L1-L6 category projection. An L1 source
    grade never yields ``accepted`` on its own (see app/evidence/quality.py).
    """

    __tablename__ = "quality_assessments"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_quality_assessments_workspace_id"),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_quality_assessments_workspace_case",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "analysis_run_id"],
            [
                "analysis_runs.workspace_id",
                "analysis_runs.decision_case_id",
                "analysis_runs.analysis_run_id",
            ],
            name="fk_quality_assessments_workspace_case_run",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "raw_artifact_id"],
            ["raw_artifacts.workspace_id", "raw_artifacts.id"],
            name="fk_quality_assessments_workspace_raw_artifact",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "authenticity >= 0 AND authenticity <= 1", name="authenticity_range"
        ),
        CheckConstraint(
            "source_quality >= 0 AND source_quality <= 1", name="source_quality_range"
        ),
        CheckConstraint("relevance >= 0 AND relevance <= 1", name="relevance_range"),
        CheckConstraint("freshness >= 0 AND freshness <= 1", name="freshness_range"),
        CheckConstraint(
            "applicability >= 0 AND applicability <= 1", name="applicability_range"
        ),
        CheckConstraint(
            "independence >= 0 AND independence <= 1", name="independence_range"
        ),
        CheckConstraint(
            "extraction_reliability >= 0 AND extraction_reliability <= 1",
            name="extraction_reliability_range",
        ),
        Index("ix_quality_assessments_workspace_run", "workspace_id", "analysis_run_id"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    raw_artifact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    authenticity: Mapped[float] = mapped_column(Float, nullable=False)
    source_quality: Mapped[float] = mapped_column(Float, nullable=False)
    relevance: Mapped[float] = mapped_column(Float, nullable=False)
    freshness: Mapped[float] = mapped_column(Float, nullable=False)
    applicability: Mapped[float] = mapped_column(Float, nullable=False)
    independence: Mapped[float] = mapped_column(Float, nullable=False)
    extraction_reliability: Mapped[float] = mapped_column(Float, nullable=False)
    bias_flags: Mapped[list[str]] = json_list_column()
    completeness_warnings: Mapped[list[str]] = json_list_column()
    conflict_group_ids: Mapped[list[str]] = json_list_column()
    verdict: Mapped[EvidenceVerdict] = mapped_column(EVIDENCE_VERDICT_ENUM, nullable=False)
    reason_codes: Mapped[list[str]] = json_list_column()
    assessed_at: Mapped[datetime] = created_at_column()


class EvidenceItem(Base):
    """Gate-approved excerpt bound to its raw material and source records.

    ``independent_source_group_id`` is the same-source dedup group computed by
    the normalizer: N articles citing the same underlying report share one
    group and count as one independent source. 06-data-model does not name
    this column yet; the gap is recorded in the Task 8 handoff as a CCR
    request, and the column never leaks into generated wire contracts because
    the evidence router is not mounted.
    """

    __tablename__ = "evidence_items"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_evidence_items_workspace_id"),
        UniqueConstraint(
            "workspace_id",
            "decision_case_id",
            "id",
            name="uq_evidence_items_workspace_case_id",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_evidence_items_workspace_case",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "analysis_run_id"],
            [
                "analysis_runs.workspace_id",
                "analysis_runs.decision_case_id",
                "analysis_runs.analysis_run_id",
            ],
            name="fk_evidence_items_workspace_case_run",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "source_record_id"],
            ["source_records.workspace_id", "source_records.decision_case_id", "source_records.id"],
            name="fk_evidence_items_workspace_case_source",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "raw_artifact_id"],
            ["raw_artifacts.workspace_id", "raw_artifacts.id"],
            name="fk_evidence_items_workspace_raw_artifact",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "quality_assessment_id"],
            ["quality_assessments.workspace_id", "quality_assessments.id"],
            name="fk_evidence_items_workspace_quality_assessment",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"source_grade IN ({_values_sql(SOURCE_GRADES)})",
            name="source_grade_canonical",
        ),
        CheckConstraint(
            f"freshness_status IN ({_values_sql(FRESHNESS_STATUSES)})",
            name="freshness_status_canonical",
        ),
        CheckConstraint("relevance >= 0 AND relevance <= 1", name="relevance_range"),
        CheckConstraint("title <> ''", name="title_not_empty"),
        CheckConstraint("snippet <> ''", name="snippet_not_empty"),
        # conditional verdicts must carry explicit applicability limits.
        CheckConstraint(
            "verdict <> 'conditional' OR applicability_limits <> '[]'::jsonb",
            name="conditional_requires_limits",
        ),
        Index("ix_evidence_items_workspace_run", "workspace_id", "analysis_run_id"),
        Index(
            "ix_evidence_items_workspace_run_group",
            "workspace_id",
            "analysis_run_id",
            "independent_source_group_id",
        ),
        Index(
            "ix_evidence_items_workspace_run_conflict",
            "workspace_id",
            "analysis_run_id",
            "conflict_group_id",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(Text)
    source_domain: Mapped[str | None] = mapped_column(String(255))
    source_grade: Mapped[str] = mapped_column(String(20), nullable=False)
    snippet: Mapped[str] = mapped_column(Text, nullable=False)
    source_record_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_span_ids: Mapped[list[str]] = json_list_column()
    supports_claim_ids: Mapped[list[str]] = json_list_column()
    contradicts_claim_ids: Mapped[list[str]] = json_list_column()
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    freshness_status: Mapped[str] = mapped_column(
        String(10), nullable=False, default="unknown", server_default="unknown"
    )
    relevance: Mapped[float] = mapped_column(Float, nullable=False)
    bias: Mapped[str | None] = mapped_column(Text)
    conflict_group_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    independent_source_group_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    verdict: Mapped[EvidenceVerdict] = mapped_column(EVIDENCE_VERDICT_ENUM, nullable=False)
    verdict_reason_codes: Mapped[list[str]] = json_list_column()
    applicability_limits: Mapped[list[str]] = json_list_column()
    origin_mode: Mapped[OriginMode] = mapped_column(ORIGIN_MODE_ENUM, nullable=False)
    raw_artifact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    quality_assessment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class EvidenceRelation(Base):
    """Directed evidence-to-evidence relation (same-source, conflict, corroboration).

    Serves the conflict list and same-source-group queries of the provenance
    layer. Claim<->evidence direction stays on the canonical ``ClaimEvidence``
    contract (Task 10 scope) and is not duplicated here.
    """

    __tablename__ = "evidence_relations"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_evidence_relations_workspace_id"),
        UniqueConstraint(
            "workspace_id",
            "from_evidence_item_id",
            "to_evidence_item_id",
            "kind",
            name="uq_evidence_relations_workspace_pair_kind",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_evidence_relations_workspace_case",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "from_evidence_item_id"],
            [
                "evidence_items.workspace_id",
                "evidence_items.decision_case_id",
                "evidence_items.id",
            ],
            name="fk_evidence_relations_workspace_case_from",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "to_evidence_item_id"],
            [
                "evidence_items.workspace_id",
                "evidence_items.decision_case_id",
                "evidence_items.id",
            ],
            name="fk_evidence_relations_workspace_case_to",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            f"kind IN ({_values_sql(EVIDENCE_RELATION_KINDS)})",
            name="kind_canonical",
        ),
        CheckConstraint(
            "from_evidence_item_id <> to_evidence_item_id",
            name="no_self_relation",
        ),
        Index(
            "ix_evidence_relations_workspace_group",
            "workspace_id",
            "group_id",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    from_evidence_item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    to_evidence_item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    group_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    rationale: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()


__all__ = [
    "EVIDENCE_RELATION_KINDS",
    "EVIDENCE_VERDICT_ENUM",
    "EvidenceItem",
    "EvidenceRelation",
    "FRESHNESS_STATUSES",
    "QualityAssessment",
    "RAW_ARTIFACT_KINDS",
    "RawArtifact",
    "RETRIEVAL_TASK_STATUSES",
    "RetrievalTask",
    "SOURCE_GRADES",
    "STABLE_TOOL_NAMES",
]
