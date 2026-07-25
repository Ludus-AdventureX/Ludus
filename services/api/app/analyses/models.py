"""Analysis runtime persistence (Task 9, case_api_data).

Canonical shapes: 06-data-model.md (AnalysisCharter, AnalysisEvent,
ResearchPacket, RunInterventionClassification, RunResolution). The
pre-existing ``analysis_runs`` ORM (contract_lead, app/models.py) is consumed
as-is; this module only *adds* the canonical partial unique index "at most one
active formal Run per Case" (06 数据库索引 section) by attaching an ``Index``
object to the existing table metadata — app/models.py itself is untouched.

Enum discipline follows the Task 8 precedent: ``AnalysisRunStatus`` /
``FormalAnalysisLevel`` / ``OriginMode`` PG enums are reused (never
recreated); a new ``analysis_charter_status`` PG enum is created by the Task 9
migration; canonical literal sets without an ``app.types`` enum (event
category/type, packet role, classification result, resolution kind) persist as
CHECK-constrained strings (SIM-02A ``response_kind`` precedent) — a CCR
request to promote them is recorded in the Task 9 handoff.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
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
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import (
    ANALYSIS_RUN_STATUS_ENUM,
    ORIGIN_MODE_ENUM,
    AnalysisRun,
    created_at_column,
    enum_type,
    json_list_column,
    json_object_column,
    uuid_primary_key,
    workspace_column,
)
from app.types import AnalysisRunStatus, FormalAnalysisLevel, OriginMode

# --- canonical literal sets (06-data-model.md); CHECK-enforced strings -------
ANALYSIS_EVENT_CATEGORIES: Final[tuple[str, ...]] = (
    "agent.status",
    "agent.task",
    "tool.call",
    "citation.added",
    "user.confirmation.required",
)
ANALYSIS_EVENT_TYPES: Final[tuple[str, ...]] = (
    "analysis.stage.started",
    "analysis.stage.progressed",
    "analysis.stage.completed",
    "analysis.needs_attention",
    "analysis.resumed",
    "analysis.amendment_required",
    "analysis.cancelled",
    "analysis.blocked",
    "analysis.ready",
    "research.packet.completed",
    "retrieval.completed",
    "quality.warning",
    "strategic_lens.completed",
    "tool.call.started",
    "tool.call.completed",
    "tool.call.failed",
    "fallback.cached_evidence",
    "fallback.fixture.loaded",
    "citation.added",
    "user.confirmation.required",
)
RESEARCH_PACKET_ROLES: Final[tuple[str, ...]] = (
    "research",
    "critic",
    "synthesis",
    "validation",
)
INTERVENTION_RESULTS: Final[tuple[str, ...]] = ("resolution", "amendment")
RUN_RESOLUTION_KINDS: Final[tuple[str, ...]] = (
    "source_conflict",
    "hard_constraint_confirmation",
    "provider_recovery",
)
CHARTER_FROZEN_FIELDS: Final[tuple[str, ...]] = (
    "decision_question",
    "goals",
    "options",
    "preference_weights",
    "hard_constraints",
    "material_scope",
    "connector_scope",
    "budget",
    "method",
    "analysis_level",
    "strategic_lens_set",
)
CANCELLATION_REASONS: Final[tuple[str, ...]] = (
    "user_cancelled",
    "charter_replaced",
    "operator_cancelled",
)

# Stages a Run can resume into / execute through (canonical exclusion set).
RESUMABLE_STAGES: Final[tuple[str, ...]] = (
    "planning",
    "retrieving",
    "analyzing",
    "criticizing",
    "synthesizing",
    "validating",
)
# "Active" = holds the one-active-formal-run-per-case slot.
ACTIVE_RUN_STATUSES: Final[tuple[str, ...]] = (
    "queued",
    *RESUMABLE_STAGES,
    "needs_attention",
)

CHARTER_STATUS_ENUM = SAEnum(
    "draft",
    "awaiting_confirmation",
    "confirmed",
    "superseded",
    name="analysis_charter_status",
    native_enum=True,
)

# PG enum over the canonical packet-role literal set (no parallel Python
# StrEnum): the decision-os invariants suite requires role columns to be enums.
RESEARCH_PACKET_ROLE_ENUM = SAEnum(
    *RESEARCH_PACKET_ROLES,
    name="research_packet_role",
    native_enum=True,
)


def _values_sql(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


# Canonical partial unique index on the PRE-EXISTING analysis_runs table:
# at most one active formal Run per (workspace, case). Attached here so the
# shared metadata matches the Task 9 migration without touching app/models.py.
ONE_ACTIVE_FORMAL_RUN_INDEX = Index(
    "uq_analysis_runs_one_active_per_case",
    AnalysisRun.workspace_id,
    AnalysisRun.decision_case_id,
    unique=True,
    postgresql_where=text(
        "status IN ('queued', 'planning', 'retrieving', 'analyzing', "
        "'criticizing', 'synthesizing', 'validating', 'needs_attention')"
    ),
)


class AnalysisCharter(Base):
    """Frozen analysis contract; confirmed charters are immutable.

    Draft rows may be edited in place (version increments); once ``confirmed``
    every frozen field is locked — any change goes through a replacement draft
    (``replaces_charter_id``) and the old charter is only marked
    ``superseded`` when the replacement confirms.
    """

    __tablename__ = "analysis_charters"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_analysis_charters_workspace_id"),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_analysis_charters_workspace_case",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "replaces_charter_id"],
            ["analysis_charters.workspace_id", "analysis_charters.id"],
            name="fk_analysis_charters_workspace_replaces",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "superseded_by_charter_id"],
            ["analysis_charters.workspace_id", "analysis_charters.id"],
            name="fk_analysis_charters_workspace_superseded_by",
            ondelete="RESTRICT",
        ),
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint("case_version > 0", name="case_version_positive"),
        CheckConstraint(
            "dossier_snapshot_version > 0", name="dossier_snapshot_version_positive"
        ),
        CheckConstraint(
            "status <> 'confirmed' OR confirmed_at IS NOT NULL",
            name="confirmed_requires_timestamp",
        ),
        CheckConstraint(
            "status <> 'superseded' OR superseded_by_charter_id IS NOT NULL",
            name="superseded_requires_successor",
        ),
        # focused lens set MUST be empty; full MUST be the complete five-lens set.
        CheckConstraint(
            "(analysis_level = 'focused' AND required_strategic_lens_types = '[]'::jsonb) "
            "OR (analysis_level = 'full' "
            "AND jsonb_array_length(required_strategic_lens_types) = 5)",
            name="lens_set_matches_level",
        ),
        Index(
            "ix_analysis_charters_workspace_case_status",
            "workspace_id",
            "decision_case_id",
            "status",
            "created_at",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_subject_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    case_version: Mapped[int] = mapped_column(Integer, nullable=False)
    case_snapshot_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(
        CHARTER_STATUS_ENUM, nullable=False, default="draft", server_default="draft"
    )
    analysis_level: Mapped[FormalAnalysisLevel] = mapped_column(
        enum_type(FormalAnalysisLevel, "formal_analysis_level"),
        nullable=False,
    )
    decision_question: Mapped[str] = mapped_column(Text, nullable=False)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    goals: Mapped[list[dict[str, Any]]] = json_list_column()
    constraints: Mapped[list[dict[str, Any]]] = json_list_column()
    option_ids: Mapped[list[str]] = json_list_column()
    current_inclination: Mapped[str | None] = mapped_column(Text)
    possible_biases: Mapped[list[str]] = json_list_column()
    unknown_item_ids: Mapped[list[str]] = json_list_column()
    allowed_material_ids: Mapped[list[str]] = json_list_column()
    excluded_material_ids: Mapped[list[str]] = json_list_column()
    dossier_snapshot_version: Mapped[int] = mapped_column(Integer, nullable=False)
    dossier_snapshot_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    decision_maker_profile_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    decision_maker_profile_version: Mapped[int | None] = mapped_column(Integer)
    preference_snapshot_hash: Mapped[str | None] = mapped_column(String(256))
    preference_weights: Mapped[dict[str, Any]] = json_object_column()
    analysis_directions: Mapped[list[str]] = json_list_column()
    required_strategic_lens_types: Mapped[list[str]] = json_list_column()
    method_recommendation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    method_id: Mapped[str | None] = mapped_column(String(160))
    method_version: Mapped[str | None] = mapped_column(String(64))
    method_content_hash: Mapped[str | None] = mapped_column(String(256))
    method_reasons: Mapped[list[str]] = json_list_column()
    applicability_limits: Mapped[list[str]] = json_list_column()
    alternative_methods: Mapped[list[str]] = json_list_column()
    missing_inputs: Mapped[list[str]] = json_list_column()
    formal_analysis_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    blocking_reasons: Mapped[list[str]] = json_list_column()
    allowed_connector_ids: Mapped[list[str]] = json_list_column()
    estimated_duration_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    budget: Mapped[dict[str, Any]] = json_object_column()
    replaces_charter_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    superseded_by_charter_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = created_at_column()
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AnalysisEvent(Base):
    """Append-only per-run event with a strictly increasing sequence.

    ``(analysis_run_id, sequence)`` is unique (06 数据库索引); ``id`` is the
    SSE event id and ``Last-Event-ID`` replays from the persisted sequence.
    """

    __tablename__ = "analysis_events"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_analysis_events_workspace_id"),
        # Tenant discipline: every unique constraint carries workspace_id; the
        # per-run sequence uniqueness is preserved because analysis_run_id is
        # itself workspace-unique.
        UniqueConstraint(
            "workspace_id",
            "analysis_run_id",
            "sequence",
            name="uq_analysis_events_workspace_run_sequence",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_analysis_events_workspace_case",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "analysis_run_id"],
            [
                "analysis_runs.workspace_id",
                "analysis_runs.decision_case_id",
                "analysis_runs.analysis_run_id",
            ],
            name="fk_analysis_events_workspace_case_run",
            ondelete="CASCADE",
        ),
        CheckConstraint("sequence > 0", name="sequence_positive"),
        CheckConstraint(
            f"category IN ({_values_sql(ANALYSIS_EVENT_CATEGORIES)})",
            name="category_canonical",
        ),
        CheckConstraint(
            f"type IN ({_values_sql(ANALYSIS_EVENT_TYPES)})",
            name="type_canonical",
        ),
        Index(
            "ix_analysis_events_workspace_run_sequence",
            "workspace_id",
            "analysis_run_id",
            "sequence",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    type: Mapped[str] = mapped_column(String(60), nullable=False)
    origin_mode: Mapped[OriginMode] = mapped_column(ORIGIN_MODE_ENUM, nullable=False)
    source_origin_modes: Mapped[list[str]] = json_list_column()
    payload: Mapped[dict[str, Any]] = json_object_column()
    created_at: Mapped[datetime] = created_at_column()


class ResearchPacket(Base):
    """Role-scoped factor conclusion produced during a Run stage."""

    __tablename__ = "research_packets"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_research_packets_workspace_id"),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_research_packets_workspace_case",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "analysis_run_id"],
            [
                "analysis_runs.workspace_id",
                "analysis_runs.decision_case_id",
                "analysis_runs.analysis_run_id",
            ],
            name="fk_research_packets_workspace_case_run",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "claim_support_score >= 0 AND claim_support_score <= 1",
            name="claim_support_score_range",
        ),
        CheckConstraint("conclusion <> ''", name="conclusion_not_empty"),
        Index(
            "ix_research_packets_workspace_run_role",
            "workspace_id",
            "analysis_run_id",
            "role",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(RESEARCH_PACKET_ROLE_ENUM, nullable=False)
    factor: Mapped[str | None] = mapped_column(String(400))
    framework_used: Mapped[str | None] = mapped_column(String(400))
    conclusion: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str | None] = mapped_column(String(200))
    claim_support_score: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_ids: Mapped[list[str]] = json_list_column()
    discarded_claims: Mapped[list[str]] = json_list_column()
    remaining_gaps: Mapped[list[str]] = json_list_column()
    disclaimer: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()


class RunInterventionClassification(Base):
    """Append-only classification of any mid-run input (resolution|amendment)."""

    __tablename__ = "run_intervention_classifications"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "id", name="uq_run_intervention_classifications_workspace_id"
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_run_intervention_classifications_workspace_case",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "analysis_run_id"],
            [
                "analysis_runs.workspace_id",
                "analysis_runs.decision_case_id",
                "analysis_runs.analysis_run_id",
            ],
            name="fk_run_intervention_classifications_workspace_case_run",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            f"result IN ({_values_sql(INTERVENTION_RESULTS)})",
            name="result_canonical",
        ),
        # A resolution must not change any frozen field; an amendment must.
        CheckConstraint(
            "(result = 'resolution' AND changed_frozen_fields = '[]'::jsonb) "
            "OR (result = 'amendment' AND changed_frozen_fields <> '[]'::jsonb)",
            name="result_matches_changed_fields",
        ),
        Index(
            "ix_run_intervention_classifications_workspace_run",
            "workspace_id",
            "analysis_run_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_frozen_fields: Mapped[list[str]] = json_list_column()
    reason_codes: Mapped[list[str]] = json_list_column()
    created_by: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class RunResolution(Base):
    """Append-only resolution restoring a needs_attention Run (three kinds only)."""

    __tablename__ = "run_resolutions"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_run_resolutions_workspace_id"),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_run_resolutions_workspace_case",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "analysis_run_id"],
            [
                "analysis_runs.workspace_id",
                "analysis_runs.decision_case_id",
                "analysis_runs.analysis_run_id",
            ],
            name="fk_run_resolutions_workspace_case_run",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "classification_id"],
            [
                "run_intervention_classifications.workspace_id",
                "run_intervention_classifications.id",
            ],
            name="fk_run_resolutions_workspace_classification",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"payload ->> 'kind' IN ({_values_sql(RUN_RESOLUTION_KINDS)})",
            name="payload_kind_canonical",
        ),
        CheckConstraint(
            f"resume_stage IN ({_values_sql(RESUMABLE_STAGES)})",
            name="resume_stage_resumable",
        ),
        Index(
            "ix_run_resolutions_workspace_run",
            "workspace_id",
            "analysis_run_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    classification_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    payload: Mapped[dict[str, Any]] = json_object_column()
    resume_stage: Mapped[AnalysisRunStatus] = mapped_column(
        ANALYSIS_RUN_STATUS_ENUM, nullable=False
    )
    created_by: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = created_at_column()


__all__ = [
    "ACTIVE_RUN_STATUSES",
    "ANALYSIS_EVENT_CATEGORIES",
    "ANALYSIS_EVENT_TYPES",
    "AnalysisCharter",
    "AnalysisEvent",
    "CANCELLATION_REASONS",
    "CHARTER_FROZEN_FIELDS",
    "CHARTER_STATUS_ENUM",
    "INTERVENTION_RESULTS",
    "ONE_ACTIVE_FORMAL_RUN_INDEX",
    "RESEARCH_PACKET_ROLES",
    "RESUMABLE_STAGES",
    "ResearchPacket",
    "RUN_RESOLUTION_KINDS",
    "RunInterventionClassification",
    "RunResolution",
]
