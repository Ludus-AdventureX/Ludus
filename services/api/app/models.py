from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    ForeignKeyConstraint,
    Float,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.types import (
    AnalysisRunStatus,
    CandidateRevisionStatus,
    CandidateSourceType,
    CaseOperationalStatus,
    ConnectorStatus,
    DecisionLifecycleStage,
    DecisionType,
    DeliberationEventCategory,
    DeliberationFactorProvenance,
    DeliberationMessageKind,
    DeliberationNominationStatus,
    DeliberationProposalKind,
    DeliberationProposalStatus,
    DeliberationRoundKind,
    DeliberationRunStatus,
    DeliberationSpeaker,
    DomainEventActor,
    DossierScope,
    DossierSourceType,
    DossierStatementType,
    EdgePolarity,
    EntryStatus,
    FactorAuthorship,
    FactorControllability,
    FactorEvidenceStatus,
    FormalAnalysisLevel,
    GraphBranchStatus,
    GraphVersionStatus,
    InitiativeStatus,
    LensProducerRole,
    MessageRole,
    OriginMode,
    QuickAnalysisFormality,
    ResponsibilityActor,
    SignoffRequestStatus,
    SimulationConvergenceStatus,
    SimulationMode,
    SourceKind,
    SourceScope,
    StrategicLensArtifactStatus,
    StrategicLensType,
    SubjectStatus,
    UserStatus,
    WorkspaceCapability,
    WorkspaceMembershipStatus,
    WorkspaceRole,
    WorkspaceStatus,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def enum_type(enum_class: type[Any], name: str) -> SAEnum:
    return SAEnum(
        enum_class,
        name=name,
        native_enum=True,
        validate_strings=True,
        values_callable=lambda values: [item.value for item in values],
    )


def uuid_primary_key():
    return mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )


def workspace_column():
    return mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )


def created_at_column():
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )


def updated_at_column():
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )


def json_list_column():
    return mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )


def json_object_column():
    return mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )


WORKSPACE_CAPABILITY_ENUM = enum_type(WorkspaceCapability, "workspace_capability")
ORIGIN_MODE_ENUM = enum_type(OriginMode, "origin_mode")
ANALYSIS_RUN_STATUS_ENUM = enum_type(AnalysisRunStatus, "analysis_run_status")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id: Mapped[UUID] = uuid_primary_key()
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        enum_type(UserStatus, "user_status"),
        nullable=False,
        default=UserStatus.ACTIVE,
        server_default=UserStatus.ACTIVE.value,
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[UUID] = uuid_primary_key()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[WorkspaceStatus] = mapped_column(
        enum_type(WorkspaceStatus, "workspace_status"),
        nullable=False,
        default=WorkspaceStatus.ACTIVE,
        server_default=WorkspaceStatus.ACTIVE.value,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class WorkspaceMembership(Base):
    __tablename__ = "workspace_memberships"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "user_id",
            name="uq_workspace_memberships_workspace_user",
        ),
        Index("ix_workspace_memberships_user_status", "user_id", "status"),
        Index("ix_workspace_memberships_workspace_status", "workspace_id", "status"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[WorkspaceRole] = mapped_column(
        enum_type(WorkspaceRole, "workspace_role"),
        nullable=False,
    )
    capabilities: Mapped[list[WorkspaceCapability]] = mapped_column(
        ARRAY(WORKSPACE_CAPABILITY_ENUM),
        nullable=False,
        default=list,
        server_default=text("'{}'::workspace_capability[]"),
    )
    status: Mapped[WorkspaceMembershipStatus] = mapped_column(
        enum_type(WorkspaceMembershipStatus, "workspace_membership_status"),
        nullable=False,
        default=WorkspaceMembershipStatus.ACTIVE,
        server_default=WorkspaceMembershipStatus.ACTIVE.value,
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class WorkspaceInvite(Base):
    """Invite-code grant for multi-guest collaboration.

    The plaintext token appears exactly once (create response) and only its
    sha256 lands here; redemption is bounded by expiry, max_uses and
    revocation, and every failure mode collapses into the same uniform 404
    (anti-enumeration, same discipline as the case surface).
    """

    __tablename__ = "workspace_invites"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_workspace_invites_token_hash"),
        Index("ix_workspace_invites_workspace", "workspace_id", "revoked_at"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    created_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    granted_capabilities: Mapped[list[WorkspaceCapability]] = mapped_column(
        ARRAY(WORKSPACE_CAPABILITY_ENUM),
        nullable=False,
        default=list,
        server_default=text("'{}'::workspace_capability[]"),
    )
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created_at_column()


class MentorReview(Base):
    """Structured mentor feedback on a student's decision case (R3).

    The mentor sees the full thinking chain (trace/report/signoff/calibration)
    and answers three things: how good was the THINKING (1-5), what blind spot
    remains, and what single next step they suggest. Append-only.
    """

    __tablename__ = "mentor_reviews"
    __table_args__ = (
        Index("ix_mentor_reviews_workspace_case", "workspace_id", "decision_case_id"),
        CheckConstraint("quality_score >= 1 AND quality_score <= 5", name="ck_mentor_reviews_score_range"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    author_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    quality_score: Mapped[int] = mapped_column(Integer, nullable=False)
    blind_spots: Mapped[str] = mapped_column(Text, nullable=False)
    next_step: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class UserSession(Base):
    __tablename__ = "user_sessions"
    __table_args__ = (
        CheckConstraint("token_version > 0", name="token_version_positive"),
        Index("ix_user_sessions_user_revoked_expires", "user_id", "revoked_at", "expires_at"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = created_at_column()
    created_at: Mapped[datetime] = created_at_column()


class DecisionSubject(Base):
    __tablename__ = "decision_subjects"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_subject_workspace_id"),
        UniqueConstraint("workspace_id", "slug", name="uq_subject_workspace_slug"),
        UniqueConstraint("workspace_id", "dossier_id", name="uq_subject_workspace_dossier"),
        UniqueConstraint(
            "workspace_id",
            "id",
            "dossier_id",
            name="uq_subject_workspace_id_dossier",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    dossier_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    status: Mapped[SubjectStatus] = mapped_column(
        enum_type(SubjectStatus, "subject_status"),
        nullable=False,
        default=SubjectStatus.ACTIVE,
        server_default=SubjectStatus.ACTIVE.value,
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class Initiative(Base):
    __tablename__ = "initiatives"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_initiative_workspace_id"),
        UniqueConstraint(
            "workspace_id",
            "decision_subject_id",
            "id",
            name="uq_initiatives_workspace_subject_id",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_subject_id"],
            ["decision_subjects.workspace_id", "decision_subjects.id"],
            name="fk_initiatives_workspace_subject",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_subject_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[InitiativeStatus] = mapped_column(
        enum_type(InitiativeStatus, "initiative_status"),
        nullable=False,
        default=InitiativeStatus.ACTIVE,
        server_default=InitiativeStatus.ACTIVE.value,
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class DecisionCase(Base):
    __tablename__ = "decision_cases"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "decision_case_id",
            name="uq_decision_cases_workspace_id",
        ),
        UniqueConstraint(
            "workspace_id",
            "decision_subject_id",
            "decision_case_id",
            name="uq_decision_cases_workspace_subject_id",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_subject_id"],
            ["decision_subjects.workspace_id", "decision_subjects.id"],
            name="fk_decision_cases_workspace_subject",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_subject_id", "initiative_id"],
            ["initiatives.workspace_id", "initiatives.decision_subject_id", "initiatives.id"],
            name="fk_decision_cases_workspace_subject_initiative",
            ondelete="RESTRICT",
        ),
        CheckConstraint("current_version > 0", name="current_version_positive"),
        Index(
            "ix_decision_cases_workspace_status_updated",
            "workspace_id",
            "status",
            "updated_at",
        ),
    )

    decision_case_id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_subject_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    initiative_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    decision_question: Mapped[str] = mapped_column(Text, nullable=False)
    inferred_decision_type: Mapped[DecisionType] = mapped_column(
        enum_type(DecisionType, "decision_type"),
        nullable=False,
        default=DecisionType.UNKNOWN,
        server_default=DecisionType.UNKNOWN.value,
    )
    status: Mapped[DecisionLifecycleStage] = mapped_column(
        enum_type(DecisionLifecycleStage, "decision_lifecycle_stage"),
        nullable=False,
        default=DecisionLifecycleStage.DRAFT,
        server_default=DecisionLifecycleStage.DRAFT.value,
    )
    operational_status: Mapped[CaseOperationalStatus] = mapped_column(
        enum_type(CaseOperationalStatus, "case_operational_status"),
        nullable=False,
        default=CaseOperationalStatus.OK,
        server_default=CaseOperationalStatus.OK.value,
    )
    summary: Mapped[dict[str, Any]] = json_object_column()
    five_w_one_h: Mapped[dict[str, Any]] = json_object_column()
    goals: Mapped[list[dict[str, Any]]] = json_list_column()
    constraints: Mapped[list[dict[str, Any]]] = json_list_column()
    stakeholders: Mapped[list[dict[str, Any]]] = json_list_column()
    selected_dossier_entry_ids: Mapped[list[str]] = json_list_column()
    case_entry_ids: Mapped[list[str]] = json_list_column()
    assumption_ids: Mapped[list[str]] = json_list_column()
    option_ids: Mapped[list[str]] = json_list_column()
    charter_ids: Mapped[list[str]] = json_list_column()
    analysis_run_ids: Mapped[list[str]] = json_list_column()
    report_artifact_ids: Mapped[list[str]] = json_list_column()
    causal_graph_ids: Mapped[list[str]] = json_list_column()
    current_decision_record_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class CaseProfile(Base):
    """Per-(case, profile_type) decision-maker profile snapshot.

    Written and read via raw SQL in the conversations lane (routes.py) and
    consumed by the analysis worker; the ORM model mirrors that schema so
    Alembic autogenerate stays in sync with the running code (the migration
    drift surfaced in the 2026-08-05 audit was a missing model, not an orphan
    table).
    """

    __tablename__ = "case_profiles"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "decision_case_id",
            "profile_type",
            name="uq_case_profiles_workspace_case_type",
        ),
        Index("ix_case_profiles_workspace_case", "workspace_id", "decision_case_id"),
        ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_case_profiles_workspace",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    profile_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(
        JSONB(astext_type=Text()),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (
        UniqueConstraint("workspace_id", "analysis_run_id", name="uq_analysis_runs_workspace_id"),
        UniqueConstraint(
            "workspace_id",
            "decision_case_id",
            "analysis_run_id",
            name="uq_analysis_runs_workspace_case_id",
        ),
        UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_analysis_runs_workspace_idempotency",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_analysis_runs_workspace_case",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "supersedes_analysis_run_id"],
            [
                "analysis_runs.workspace_id",
                "analysis_runs.decision_case_id",
                "analysis_runs.analysis_run_id",
            ],
            name="fk_analysis_runs_workspace_supersedes",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "superseded_by_analysis_run_id"],
            [
                "analysis_runs.workspace_id",
                "analysis_runs.decision_case_id",
                "analysis_runs.analysis_run_id",
            ],
            name="fk_analysis_runs_workspace_superseded_by",
            ondelete="RESTRICT",
        ),
        CheckConstraint("charter_version > 0", name="charter_version_positive"),
        CheckConstraint("case_version > 0", name="case_version_positive"),
        CheckConstraint("dossier_snapshot_version > 0", name="dossier_snapshot_version_positive"),
        CheckConstraint("progress >= 0 AND progress <= 1", name="progress_range"),
        CheckConstraint("attempt > 0", name="attempt_positive"),
        CheckConstraint("max_attempts > 0", name="max_attempts_positive"),
        CheckConstraint("attempt <= max_attempts", name="attempt_within_max"),
        CheckConstraint(
            "last_resumable_stage IS NULL OR last_resumable_stage IN "
            "('planning', 'retrieving', 'analyzing', 'criticizing', 'synthesizing', 'validating')",
            name="last_resumable_stage_valid",
        ),
        Index("ix_analysis_runs_workspace_case_status", "workspace_id", "decision_case_id", "status"),
    )

    analysis_run_id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    charter_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    charter_version: Mapped[int] = mapped_column(Integer, nullable=False)
    run_manifest_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    run_manifest_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    cynefin_gate_result_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    analysis_level: Mapped[FormalAnalysisLevel] = mapped_column(
        enum_type(FormalAnalysisLevel, "formal_analysis_level"),
        nullable=False,
    )
    status: Mapped[AnalysisRunStatus] = mapped_column(
        ANALYSIS_RUN_STATUS_ENUM,
        nullable=False,
        default=AnalysisRunStatus.QUEUED,
        server_default=AnalysisRunStatus.QUEUED.value,
    )
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    origin_modes: Mapped[list[OriginMode]] = mapped_column(
        ARRAY(ORIGIN_MODE_ENUM),
        nullable=False,
        default=list,
        server_default=text("'{}'::origin_mode[]"),
    )
    case_version: Mapped[int] = mapped_column(Integer, nullable=False)
    case_snapshot_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    dossier_snapshot_version: Mapped[int] = mapped_column(Integer, nullable=False)
    dossier_snapshot_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    method_id: Mapped[str] = mapped_column(String(160), nullable=False)
    method_version: Mapped[str] = mapped_column(String(64), nullable=False)
    method_content_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stage_results: Mapped[dict[str, Any]] = json_object_column()
    strategic_lens_artifact_ids: Mapped[list[str]] = json_list_column()
    last_resumable_stage: Mapped[AnalysisRunStatus | None] = mapped_column(
        ANALYSIS_RUN_STATUS_ENUM
    )
    interruption_classification_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    supersedes_analysis_run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    superseded_by_analysis_run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    cancellation_reason: Mapped[str | None] = mapped_column(String(80))
    # Grey-goo 原则⑮ complexity adaptivity (CCR-20260802-P2W2): internal
    # state only - a downgrade changes budget/iteration depth, never the
    # five-lens artifact contract.
    complexity_downgraded: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    downgrade_chain: Mapped[list[str]] = json_list_column()
    created_at: Mapped[datetime] = created_at_column()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StrategicLensArtifact(Base):
    """Immutable persisted output of one strategic lens (CCR-20260724-Ways-01).

    Identity, method snapshot, originModes, contentHash, and createdAt are
    server-injected from the frozen run context (AGENTS section 7); the model
    layer must reject any self-reported identity fields. claim/evidence/
    assumption references are JSON reference lists resolved and validated by
    the server against run-frozen objects before insertion. ``ready`` requires
    Validation acceptance, witnessed by ``validation_accepted_at``.
    """

    __tablename__ = "strategic_lens_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "strategic_lens_artifact_id",
            name="uq_strategic_lens_artifacts_workspace_id",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_strategic_lens_artifacts_workspace_case",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "analysis_run_id"],
            [
                "analysis_runs.workspace_id",
                "analysis_runs.decision_case_id",
                "analysis_runs.analysis_run_id",
            ],
            name="fk_strategic_lens_artifacts_workspace_case_run",
            ondelete="CASCADE",
        ),
        # Only one Validation-accepted artifact per lens per run; drafts and
        # rejected artifacts keep their audit history without colliding.
        Index(
            "uq_strategic_lens_artifacts_ready_per_run_lens",
            "workspace_id",
            "analysis_run_id",
            "lens_type",
            unique=True,
            postgresql_where=text("status = 'ready'"),
        ),
        CheckConstraint(
            "status <> 'ready' OR validation_accepted_at IS NOT NULL",
            name="ready_requires_validation_acceptance",
        ),
        CheckConstraint("content_hash <> ''", name="content_hash_not_empty"),
        Index(
            "ix_strategic_lens_artifacts_workspace_run",
            "workspace_id",
            "analysis_run_id",
        ),
    )

    strategic_lens_artifact_id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    charter_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    lens_type: Mapped[StrategicLensType] = mapped_column(
        enum_type(StrategicLensType, "strategic_lens_type"),
        nullable=False,
    )
    producer_role: Mapped[LensProducerRole] = mapped_column(
        enum_type(LensProducerRole, "lens_producer_role"),
        nullable=False,
    )
    status: Mapped[StrategicLensArtifactStatus] = mapped_column(
        enum_type(StrategicLensArtifactStatus, "strategic_lens_artifact_status"),
        nullable=False,
        default=StrategicLensArtifactStatus.DRAFT,
        server_default=StrategicLensArtifactStatus.DRAFT.value,
    )
    method_id: Mapped[str] = mapped_column(String(160), nullable=False)
    method_version: Mapped[str] = mapped_column(String(64), nullable=False)
    method_content_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    origin_modes: Mapped[list[OriginMode]] = mapped_column(
        ARRAY(ORIGIN_MODE_ENUM),
        nullable=False,
        default=list,
        server_default=text("'{}'::origin_mode[]"),
    )
    content_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    payload: Mapped[dict[str, Any]] = json_object_column()
    claim_refs: Mapped[list[str]] = json_list_column()
    evidence_refs: Mapped[list[str]] = json_list_column()
    assumption_refs: Mapped[list[str]] = json_list_column()
    validation_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()


class SourceRecord(Base):
    __tablename__ = "source_records"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_source_records_workspace_id"),
        UniqueConstraint(
            "workspace_id",
            "decision_case_id",
            "id",
            name="uq_source_records_workspace_case_id",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_source_records_workspace_case",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "analysis_run_id"],
            [
                "analysis_runs.workspace_id",
                "analysis_runs.decision_case_id",
                "analysis_runs.analysis_run_id",
            ],
            name="fk_source_records_workspace_case_run",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "frozen_from_source_record_id"],
            ["source_records.workspace_id", "source_records.decision_case_id", "source_records.id"],
            name="fk_source_records_workspace_case_frozen_from",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(source_scope = 'pre_run' AND analysis_run_id IS NULL "
            "AND frozen_from_source_record_id IS NULL AND frozen_at IS NULL) OR "
            "(source_scope = 'run_frozen' AND analysis_run_id IS NOT NULL "
            "AND frozen_from_source_record_id IS NOT NULL AND frozen_at IS NOT NULL)",
            name="source_scope_fields_consistent",
        ),
        CheckConstraint(
            "kind NOT IN ('human_input', 'case_snapshot') OR raw_artifact_id IS NULL",
            name="raw_artifact_matches_source_kind",
        ),
        Index(
            "ix_source_records_workspace_case_scope",
            "workspace_id",
            "decision_case_id",
            "source_scope",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_scope: Mapped[SourceScope] = mapped_column(
        enum_type(SourceScope, "source_scope"),
        nullable=False,
    )
    analysis_run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    frozen_from_source_record_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    kind: Mapped[SourceKind] = mapped_column(
        enum_type(SourceKind, "source_kind"),
        nullable=False,
    )
    canonical_uri: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    source_version: Mapped[str] = mapped_column(String(160), nullable=False)
    origin_mode: Mapped[OriginMode] = mapped_column(ORIGIN_MODE_ENUM, nullable=False)
    raw_artifact_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = created_at_column()


class SourceSpan(Base):
    __tablename__ = "source_spans"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_source_spans_workspace_id"),
        UniqueConstraint(
            "workspace_id",
            "decision_case_id",
            "id",
            name="uq_source_spans_workspace_case_id",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_source_spans_workspace_case",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "source_record_id"],
            ["source_records.workspace_id", "source_records.decision_case_id", "source_records.id"],
            name="fk_source_spans_workspace_case_source",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "analysis_run_id"],
            [
                "analysis_runs.workspace_id",
                "analysis_runs.decision_case_id",
                "analysis_runs.analysis_run_id",
            ],
            name="fk_source_spans_workspace_case_run",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "frozen_from_source_span_id"],
            ["source_spans.workspace_id", "source_spans.decision_case_id", "source_spans.id"],
            name="fk_source_spans_workspace_case_frozen_from",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(source_scope = 'pre_run' AND analysis_run_id IS NULL "
            "AND frozen_from_source_span_id IS NULL) OR "
            "(source_scope = 'run_frozen' AND analysis_run_id IS NOT NULL "
            "AND frozen_from_source_span_id IS NOT NULL)",
            name="source_scope_fields_consistent",
        ),
        CheckConstraint("locator <> '{}'::jsonb", name="locator_not_empty"),
        CheckConstraint("length(quote) > 0", name="quote_not_empty"),
        Index(
            "ix_source_spans_workspace_case_scope",
            "workspace_id",
            "decision_case_id",
            "source_scope",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_record_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_scope: Mapped[SourceScope] = mapped_column(
        enum_type(SourceScope, "source_scope"),
        nullable=False,
    )
    analysis_run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    frozen_from_source_span_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    locator: Mapped[dict[str, Any]] = json_object_column()
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    quote_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    context_before: Mapped[str | None] = mapped_column(Text)
    context_after: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()


class CausalGraph(Base):
    """Stable graph aggregate (CCR-20260724-SIM-01); versions are immutable.

    current_graph_version_id is a service-maintained projection pointer and is
    deliberately not a database FK to avoid a creation cycle with
    graph_versions; the service validates it on every write.
    """

    __tablename__ = "causal_graphs"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_causal_graphs_workspace_id"),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_causal_graphs_workspace_case",
            ondelete="CASCADE",
        ),
        Index("ix_causal_graphs_workspace_case", "workspace_id", "decision_case_id"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    report_artifact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    current_graph_version_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    origin_modes: Mapped[list[OriginMode]] = mapped_column(
        ARRAY(ORIGIN_MODE_ENUM),
        nullable=False,
        default=list,
        server_default=text("'{}'::origin_mode[]"),
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class GraphVersion(Base):
    """Immutable saved graph snapshot; formal runs only reference confirmed ones.

    branch_id is service-validated (no FK) to avoid a circular dependency with
    graph_branches, whose base/head columns reference graph_versions. There is
    deliberately no confirmed partial unique index (B-correction): multiple
    confirmed versions per graph are the normal history model.
    """

    __tablename__ = "graph_versions"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_graph_versions_workspace_id"),
        UniqueConstraint(
            "workspace_id", "graph_id", "version", name="uq_graph_versions_workspace_graph_version"
        ),
        ForeignKeyConstraint(
            ["workspace_id", "graph_id"],
            ["causal_graphs.workspace_id", "causal_graphs.id"],
            name="fk_graph_versions_workspace_graph",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_graph_versions_workspace_case",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "parent_version_id"],
            ["graph_versions.workspace_id", "graph_versions.id"],
            name="fk_graph_versions_workspace_parent",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "source_graph_version_id"],
            ["graph_versions.workspace_id", "graph_versions.id"],
            name="fk_graph_versions_workspace_source",
            ondelete="RESTRICT",
        ),
        CheckConstraint("version > 0", name="graph_version_positive"),
        CheckConstraint("case_version > 0", name="graph_case_version_positive"),
        CheckConstraint(
            "status <> 'confirmed' OR confirmed_at IS NOT NULL",
            name="confirmed_requires_timestamp",
        ),
        Index("ix_graph_versions_workspace_graph_status", "workspace_id", "graph_id", "status"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    graph_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    case_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_report_artifact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    branch_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    parent_version_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    source_graph_version_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[GraphVersionStatus] = mapped_column(
        enum_type(GraphVersionStatus, "graph_version_status"),
        nullable=False,
        default=GraphVersionStatus.DRAFT,
        server_default=GraphVersionStatus.DRAFT.value,
    )
    provenance: Mapped[list[dict[str, Any]]] = json_list_column()
    origin_modes: Mapped[list[OriginMode]] = mapped_column(
        ARRAY(ORIGIN_MODE_ENUM),
        nullable=False,
        default=list,
        server_default=text("'{}'::origin_mode[]"),
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    created_by: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = created_at_column()
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GraphNode(Base):
    """Per-version immutable node copy. Business units persisted as-is;
    normalization to [0, 1] happens only inside the pure engine.
    """

    __tablename__ = "graph_nodes"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "graph_version_id",
            "id",
            name="uq_graph_nodes_workspace_version_id",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "graph_version_id"],
            ["graph_versions.workspace_id", "graph_versions.id"],
            name="fk_graph_nodes_workspace_version",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "node_type IN ('decision', 'lever', 'constraint', 'external', 'unknown', "
            "'intermediate', 'outcome', 'indicator')",
            name="node_type_valid",
        ),
        CheckConstraint("min_value < max_value", name="node_bounds_ordered"),
        CheckConstraint(
            "baseline_value >= min_value AND baseline_value <= max_value",
            name="node_baseline_in_bounds",
        ),
        CheckConstraint(
            "current_value >= min_value AND current_value <= max_value",
            name="node_current_in_bounds",
        ),
        CheckConstraint(
            "sensitivity_step IS NULL OR sensitivity_step > 0",
            name="node_sensitivity_step_positive",
        ),
        CheckConstraint(
            "evidence_quality_score >= 0 AND evidence_quality_score <= 1",
            name="node_evidence_quality_range",
        ),
        CheckConstraint(
            "normalization IN ('linear', 'inverse_linear')",
            name="node_normalization_valid",
        ),
        CheckConstraint(
            "review_status IN ('draft', 'confirmed', 'rejected')",
            name="node_status_valid",
        ),
        Index("ix_graph_nodes_workspace_version", "workspace_id", "graph_version_id"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    graph_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    label: Mapped[str] = mapped_column(String(240), nullable=False)
    # NodeType stays the canonical Python enum; the six new PG enums of this
    # CCR are fixed, so node_type is a CHECK-constrained string column.
    node_type: Mapped[str] = mapped_column(String(16), nullable=False)
    baseline_value: Mapped[float] = mapped_column(Float, nullable=False)
    current_value: Mapped[float] = mapped_column(Float, nullable=False)
    min_value: Mapped[float] = mapped_column(Float, nullable=False)
    max_value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(80))
    normalization: Mapped[str] = mapped_column(String(20), nullable=False)
    sensitivity_step: Mapped[float | None] = mapped_column(Float)
    controllability: Mapped[FactorControllability] = mapped_column(
        enum_type(FactorControllability, "factor_controllability"),
        nullable=False,
    )
    authorship: Mapped[FactorAuthorship] = mapped_column(
        enum_type(FactorAuthorship, "factor_authorship"),
        nullable=False,
    )
    evidence_status: Mapped[FactorEvidenceStatus] = mapped_column(
        enum_type(FactorEvidenceStatus, "factor_evidence_status"),
        nullable=False,
    )
    evidence_quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_ids: Mapped[list[str]] = json_list_column()
    assumption_ids: Mapped[list[str]] = json_list_column()
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    # Wire field name is "status"; the DB column is review_status because the
    # bulk-review state is a CHECK-locked string (the CCR fixes PG enums at
    # six) while lifecycle status columns stay PG-enum-backed.
    review_status: Mapped[str] = mapped_column(String(16), nullable=False)
    editable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )


class GraphEdge(Base):
    """Per-version immutable edge; strength and relationship quality are
    separate contracts and never merged (AGENTS section 10).
    """

    __tablename__ = "graph_edges"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "graph_version_id",
            "id",
            name="uq_graph_edges_workspace_version_id",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "graph_version_id"],
            ["graph_versions.workspace_id", "graph_versions.id"],
            name="fk_graph_edges_workspace_version",
            ondelete="CASCADE",
        ),
        # Same-version composite FKs: an edge can only connect nodes that
        # belong to the same immutable graph version (B-correction).
        ForeignKeyConstraint(
            ["workspace_id", "graph_version_id", "source_node_id"],
            [
                "graph_nodes.workspace_id",
                "graph_nodes.graph_version_id",
                "graph_nodes.id",
            ],
            name="fk_graph_edges_same_version_source",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "graph_version_id", "target_node_id"],
            [
                "graph_nodes.workspace_id",
                "graph_nodes.graph_version_id",
                "graph_nodes.id",
            ],
            name="fk_graph_edges_same_version_target",
            ondelete="CASCADE",
        ),
        CheckConstraint("strength >= 0 AND strength <= 1", name="edge_strength_range"),
        CheckConstraint("delay_steps >= 0", name="edge_delay_steps_non_negative"),
        CheckConstraint(
            "relationship_quality_score >= 0 AND relationship_quality_score <= 1",
            name="edge_relationship_quality_range",
        ),
        CheckConstraint(
            "review_status IN ('draft', 'confirmed', 'rejected', 'conditional')",
            name="edge_status_valid",
        ),
        CheckConstraint(
            "source_node_id <> target_node_id",
            name="no_self_loop",
        ),
        Index("ix_graph_edges_workspace_version", "workspace_id", "graph_version_id"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    graph_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_node_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    target_node_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    polarity: Mapped[EdgePolarity] = mapped_column(
        enum_type(EdgePolarity, "edge_polarity"),
        nullable=False,
    )
    strength: Mapped[float] = mapped_column(Float, nullable=False)
    delay_steps: Mapped[int] = mapped_column(Integer, nullable=False)
    authorship: Mapped[FactorAuthorship] = mapped_column(
        enum_type(FactorAuthorship, "factor_authorship"),
        nullable=False,
    )
    evidence_status: Mapped[FactorEvidenceStatus] = mapped_column(
        enum_type(FactorEvidenceStatus, "factor_evidence_status"),
        nullable=False,
    )
    relationship_quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    claim_ids: Mapped[list[str]] = json_list_column()
    evidence_ids: Mapped[list[str]] = json_list_column()
    assumption_ids: Mapped[list[str]] = json_list_column()
    # See GraphNode.review_status for the naming rationale.
    review_status: Mapped[str] = mapped_column(String(16), nullable=False)


class StrategyVersion(Base):
    """Immutable set of decision/lever overrides for one option.

    node_overrides / enabled_edge_ids are JSONB node/edge references validated
    item-by-item by the service against the referenced graph version before
    persistence; the database does not resolve JSONB references.
    """

    __tablename__ = "strategy_versions"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_strategy_versions_workspace_id"),
        UniqueConstraint(
            "workspace_id",
            "graph_id",
            "option_id",
            "version",
            name="uq_strategy_versions_workspace_graph_option_version",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "graph_id"],
            ["causal_graphs.workspace_id", "causal_graphs.id"],
            name="fk_strategy_versions_workspace_graph",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_strategy_versions_workspace_case",
            ondelete="CASCADE",
        ),
        CheckConstraint("version > 0", name="strategy_version_positive"),
        Index("ix_strategy_versions_workspace_graph", "workspace_id", "graph_id"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    graph_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    option_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    node_overrides: Mapped[dict[str, Any]] = json_object_column()
    enabled_edge_ids: Mapped[list[str]] = json_list_column()
    created_at: Mapped[datetime] = created_at_column()


class ScenarioVersion(Base):
    """Immutable external-assumption set projected from an accepted
    scenario_planning lens frame. riskTolerance is deliberately absent:
    it belongs to the frozen Profile/Charter/ScoreDefinition contract
    (AGENTS section 10), never to the scenario.

    edge_multipliers / node_shifts are JSONB references validated item-by-item
    by the service against the referenced graph version.
    """

    __tablename__ = "scenario_versions"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_scenario_versions_workspace_id"),
        UniqueConstraint(
            "workspace_id",
            "scenario_id",
            "version",
            name="uq_scenario_versions_workspace_scenario_version",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "graph_id"],
            ["causal_graphs.workspace_id", "causal_graphs.id"],
            name="fk_scenario_versions_workspace_graph",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_scenario_versions_workspace_case",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "source_lens_artifact_id"],
            [
                "strategic_lens_artifacts.workspace_id",
                "strategic_lens_artifacts.strategic_lens_artifact_id",
            ],
            name="fk_scenario_versions_workspace_source_lens",
            ondelete="RESTRICT",
        ),
        CheckConstraint("version > 0", name="scenario_version_positive"),
        CheckConstraint(
            "default_edge_multiplier >= 0",
            name="scenario_default_multiplier_non_negative",
        ),
        CheckConstraint("damping > 0 AND damping <= 1", name="scenario_damping_range"),
        Index("ix_scenario_versions_workspace_graph", "workspace_id", "graph_id"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    graph_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_lens_artifact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_strategic_scenario_id: Mapped[str] = mapped_column(String(240), nullable=False)
    scenario_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    default_edge_multiplier: Mapped[float] = mapped_column(Float, nullable=False)
    edge_multipliers: Mapped[dict[str, Any]] = json_object_column()
    node_shifts: Mapped[dict[str, Any]] = json_object_column()
    strategy_survives: Mapped[bool] = mapped_column(Boolean, nullable=False)
    early_warning_signals: Mapped[list[dict[str, Any]]] = json_list_column()
    damping: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class ScoreDefinition(Base):
    """Versioned scoring contract; mappings/weights/rules are JSONB whose
    node/option references are validated item-by-item by the service.
    ConstraintRule operators use ConstraintComparison wire values only.
    """

    __tablename__ = "score_definitions"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_score_definitions_workspace_id"),
        ForeignKeyConstraint(
            ["workspace_id", "graph_id"],
            ["causal_graphs.workspace_id", "causal_graphs.id"],
            name="fk_score_definitions_workspace_graph",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_score_definitions_workspace_case",
            ondelete="CASCADE",
        ),
        CheckConstraint("content_hash <> ''", name="score_definition_content_hash_not_empty"),
        Index("ix_score_definitions_workspace_graph", "workspace_id", "graph_id"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    graph_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    option_outcome_mappings: Mapped[list[dict[str, Any]]] = json_list_column()
    risk_weights: Mapped[list[dict[str, Any]]] = json_list_column()
    constraint_rules: Mapped[list[dict[str, Any]]] = json_list_column()
    content_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class GraphBranch(Base):
    """Named branch over immutable graph versions; rollback creates a new
    current version from a historical one and never deletes history.
    """

    __tablename__ = "graph_branches"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_graph_branches_workspace_id"),
        UniqueConstraint(
            "workspace_id", "graph_id", "name", name="uq_graph_branches_workspace_graph_name"
        ),
        ForeignKeyConstraint(
            ["workspace_id", "graph_id"],
            ["causal_graphs.workspace_id", "causal_graphs.id"],
            name="fk_graph_branches_workspace_graph",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "base_graph_version_id"],
            ["graph_versions.workspace_id", "graph_versions.id"],
            name="fk_graph_branches_workspace_base_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "head_graph_version_id"],
            ["graph_versions.workspace_id", "graph_versions.id"],
            name="fk_graph_branches_workspace_head_version",
            ondelete="RESTRICT",
        ),
        CheckConstraint("name <> ''", name="branch_name_not_empty"),
        Index("ix_graph_branches_workspace_graph", "workspace_id", "graph_id"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    graph_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    base_graph_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    head_graph_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[GraphBranchStatus] = mapped_column(
        enum_type(GraphBranchStatus, "graph_branch_status"),
        nullable=False,
        default=GraphBranchStatus.ACTIVE,
        server_default=GraphBranchStatus.ACTIVE.value,
    )
    created_at: Mapped[datetime] = created_at_column()


class DecisionMakerProfile(Base):
    """Immutable, versioned decision-maker preference snapshot (CCR-20260724-SIM-02A §2).

    Append-only: a new version is a new inserted row; neither the repository nor the
    service exposes an UPDATE or DELETE path. ``(workspace_id, profile_id, version)``
    is the business identity referenced by simulation_runs; the row UUID ``id`` is
    storage-only and never doubles as the stable profile id. ``content_hash`` is
    always computed server-side over the frozen payload (canonical JSON, sorted
    keys, UTF-8); caller-supplied hashes are never authoritative.
    """

    __tablename__ = "decision_maker_profiles"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "id", name="uq_decision_maker_profiles_workspace_id"
        ),
        UniqueConstraint(
            "workspace_id",
            "profile_id",
            "version",
            name="uq_decision_maker_profiles_workspace_profile_version",
        ),
        # decision_case_id NULL = workspace-global profile; non-NULL binds the
        # profile to exactly one case. RESTRICT: frozen replay inputs never vanish.
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_decision_maker_profiles_workspace_case",
            ondelete="RESTRICT",
        ),
        CheckConstraint("version > 0", name="profile_version_positive"),
        CheckConstraint(
            "risk_tolerance >= 0 AND risk_tolerance <= 1",
            name="profile_risk_tolerance_range",
        ),
        CheckConstraint("display_name <> ''", name="profile_display_name_not_empty"),
        CheckConstraint("content_hash <> ''", name="profile_content_hash_not_empty"),
        Index(
            "ix_decision_maker_profiles_workspace_case",
            "workspace_id",
            "decision_case_id",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    profile_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    decision_case_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    preference_weights: Mapped[dict[str, Any]] = json_object_column()
    risk_tolerance: Mapped[float] = mapped_column(Float, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class IdempotencyRecord(Base):
    """Generic idempotent-POST replay record (CCR-20260724-SIM-02A §4).

    Persistence schema only in this slice: header parsing, replay/conflict runtime
    flow, and route wiring land with the SIM-02A implementation wave. Unique key
    scope is ``(workspace_id, route_key, idempotency_key)``; ``response_kind`` is a
    contract-frozen enum-checked string (no PG enum by design); rows past
    ``expires_at`` (created_at + 48h retention) are purgeable.
    """

    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "route_key",
            "idempotency_key",
            name="uq_idempotency_records_workspace_route_key",
        ),
        CheckConstraint("route_key <> ''", name="idempotency_route_key_not_empty"),
        CheckConstraint(
            "char_length(idempotency_key) BETWEEN 1 AND 200",
            name="idempotency_key_length",
        ),
        CheckConstraint(
            "normalized_request_hash <> ''",
            name="idempotency_request_hash_not_empty",
        ),
        CheckConstraint(
            "resource_type <> ''", name="idempotency_resource_type_not_empty"
        ),
        CheckConstraint(
            "http_status >= 100 AND http_status <= 599",
            name="idempotency_http_status_range",
        ),
        CheckConstraint(
            "response_kind IN ('success', 'non_converged')",
            name="idempotency_response_kind_enum",
        ),
        CheckConstraint("expires_at > created_at", name="idempotency_expiry_after_creation"),
        Index(
            "ix_idempotency_records_workspace_expires",
            "workspace_id",
            "expires_at",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    route_key: Mapped[str] = mapped_column(String(120), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_request_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = created_at_column()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SimulationRun(Base):
    __tablename__ = "simulation_runs"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_simulation_runs_workspace_id"),
        UniqueConstraint(
            "workspace_id",
            "decision_case_id",
            "id",
            name="uq_simulation_runs_workspace_case_id",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_simulation_runs_workspace_case",
            ondelete="CASCADE",
        ),
        # CCR-20260724-SIM-01: frozen simulation inputs are tenant-scoped
        # references; RESTRICT so historical replay inputs can never vanish.
        ForeignKeyConstraint(
            ["workspace_id", "graph_version_id"],
            ["graph_versions.workspace_id", "graph_versions.id"],
            name="fk_simulation_runs_workspace_graph_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "strategy_version_id"],
            ["strategy_versions.workspace_id", "strategy_versions.id"],
            name="fk_simulation_runs_workspace_strategy_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "scenario_version_id"],
            ["scenario_versions.workspace_id", "scenario_versions.id"],
            name="fk_simulation_runs_workspace_scenario_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "score_definition_id"],
            ["score_definitions.workspace_id", "score_definitions.id"],
            name="fk_simulation_runs_workspace_score_definition",
            ondelete="RESTRICT",
        ),
        # CCR-20260724-SIM-02A §2: the decision-maker profile reference is a
        # tenant-scoped frozen input like the four SIM-01 FKs above; RESTRICT so
        # the profile a run was scored with can never vanish from history.
        ForeignKeyConstraint(
            [
                "workspace_id",
                "decision_maker_profile_id",
                "decision_maker_profile_version",
            ],
            [
                "decision_maker_profiles.workspace_id",
                "decision_maker_profiles.profile_id",
                "decision_maker_profiles.version",
            ],
            name="fk_simulation_runs_workspace_profile_version",
            ondelete="RESTRICT",
        ),
        CheckConstraint("decision_maker_profile_version > 0", name="profile_version_positive"),
        CheckConstraint("risk_tolerance >= 0 AND risk_tolerance <= 1", name="risk_tolerance_range"),
        CheckConstraint(
            "epsilon > 0 AND epsilon < 'Infinity'::double precision",
            name="epsilon_finite_positive",
        ),
        CheckConstraint("max_steps > 0", name="max_steps_positive"),
        CheckConstraint("steps >= 0 AND steps <= max_steps", name="steps_range"),
        Index(
            "ix_simulation_runs_workspace_case_created",
            "workspace_id",
            "decision_case_id",
            "created_at",
        ),
        Index("ix_simulation_runs_workspace_input_hash", "workspace_id", "input_hash"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    graph_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    graph_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    strategy_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    scenario_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    score_definition_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    score_definition_version: Mapped[str] = mapped_column(String(80), nullable=False)
    decision_maker_profile_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    decision_maker_profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_tolerance: Mapped[float] = mapped_column(Float, nullable=False)
    engine_version: Mapped[str] = mapped_column(String(80), nullable=False)
    scenario_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    simulation_mode: Mapped[SimulationMode] = mapped_column(
        enum_type(SimulationMode, "simulation_mode"),
        nullable=False,
    )
    epsilon: Mapped[float] = mapped_column(Float, nullable=False)
    max_steps: Mapped[int] = mapped_column(Integer, nullable=False)
    steps: Mapped[int] = mapped_column(Integer, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    node_results: Mapped[dict[str, float]] = json_object_column()
    option_scores: Mapped[list[dict[str, Any]]] = json_list_column()
    top_drivers: Mapped[list[dict[str, Any]]] = json_list_column()
    recommendation_shift: Mapped[str] = mapped_column(Text, nullable=False)
    convergence_status: Mapped[SimulationConvergenceStatus] = mapped_column(
        enum_type(SimulationConvergenceStatus, "simulation_convergence_status"),
        nullable=False,
    )
    origin_modes: Mapped[list[OriginMode]] = mapped_column(
        ARRAY(ORIGIN_MODE_ENUM),
        nullable=False,
        default=list,
        server_default=text("'{}'::origin_mode[]"),
    )
    created_at: Mapped[datetime] = created_at_column()


class SignoffRequest(Base):
    __tablename__ = "signoff_requests"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_signoff_requests_workspace_id"),
        UniqueConstraint(
            "workspace_id",
            "decision_case_id",
            "id",
            name="uq_signoff_requests_workspace_case_id",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_signoff_requests_workspace_case",
            ondelete="CASCADE",
        ),
        CheckConstraint("expires_at > nonce_issued_at", name="expiry_after_nonce"),
        CheckConstraint("status <> 'signed' OR signed_at IS NOT NULL", name="signed_has_timestamp"),
        Index(
            "ix_signoff_requests_workspace_case_status",
            "workspace_id",
            "decision_case_id",
            "status",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    requested_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[SignoffRequestStatus] = mapped_column(
        enum_type(SignoffRequestStatus, "signoff_request_status"),
        nullable=False,
        default=SignoffRequestStatus.PENDING,
        server_default=SignoffRequestStatus.PENDING.value,
    )
    nonce_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    nonce_issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = created_at_column()
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DecisionRecord(Base):
    __tablename__ = "decision_records"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_decision_records_workspace_id"),
        UniqueConstraint(
            "workspace_id",
            "decision_case_id",
            "id",
            name="uq_decision_records_workspace_case_id",
        ),
        UniqueConstraint(
            "workspace_id",
            "signoff_request_id",
            name="uq_decision_records_workspace_signoff_request",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_decision_records_workspace_case",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "signoff_request_id"],
            ["signoff_requests.workspace_id", "signoff_requests.decision_case_id", "signoff_requests.id"],
            name="fk_decision_records_workspace_signoff_request",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "supersedes_decision_record_id"],
            ["decision_records.workspace_id", "decision_records.decision_case_id", "decision_records.id"],
            name="fk_decision_records_workspace_supersedes",
            ondelete="RESTRICT",
        ),
        CheckConstraint("case_version > 0", name="decision_record_case_version_positive"),
        CheckConstraint(
            "record_kind IN ('original', 'revision')",
            name="decision_record_kind_valid",
        ),
        CheckConstraint(
            "(record_kind = 'original' AND supersedes_decision_record_id IS NULL) "
            "OR (record_kind = 'revision' AND supersedes_decision_record_id IS NOT NULL)",
            name="decision_record_revision_supersedes",
        ),
        CheckConstraint("payload_hash <> ''", name="decision_record_payload_hash_not_empty"),
        CheckConstraint("signature_hash <> ''", name="decision_record_signature_hash_not_empty"),
        CheckConstraint("record_hash <> ''", name="decision_record_record_hash_not_empty"),
        Index("ix_decision_records_workspace_case_created", "workspace_id", "decision_case_id", "created_at"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    case_version: Mapped[int] = mapped_column(Integer, nullable=False)
    record_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    supersedes_decision_record_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    signoff_request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    source_analysis_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_report_artifact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_judgment_set_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_dissent_record_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_causal_graph_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    source_causal_graph_version_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    source_simulation_run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    origin_modes: Mapped[list[OriginMode]] = mapped_column(
        ARRAY(ORIGIN_MODE_ENUM), nullable=False, default=list, server_default=text("'{}'::origin_mode[]")
    )
    system_recommendation: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    selected_option_id: Mapped[str] = mapped_column(String(200), nullable=False)
    decision_text: Mapped[str] = mapped_column(Text, nullable=False)
    conditions: Mapped[list[dict[str, Any]]] = json_list_column()
    thresholds: Mapped[list[dict[str, Any]]] = json_list_column()
    exit_criteria: Mapped[list[dict[str, Any]]] = json_list_column()
    action_items: Mapped[list[dict[str, Any]]] = json_list_column()
    leading_indicators: Mapped[list[dict[str, Any]]] = json_list_column()
    accepted_unknown_ids: Mapped[list[str]] = json_list_column()
    review_date: Mapped[str] = mapped_column(String(32), nullable=False)
    signed_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    signature_statement: Mapped[str] = mapped_column(Text, nullable=False)
    signature_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    record_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class DecisionReview(Base):
    __tablename__ = "decision_reviews"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_decision_reviews_workspace_id"),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_decision_reviews_workspace_case",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "decision_record_id"],
            ["decision_records.workspace_id", "decision_records.decision_case_id", "decision_records.id"],
            name="fk_decision_reviews_workspace_decision_record",
            ondelete="CASCADE",
        ),
        CheckConstraint("source_case_version > 0", name="decision_review_case_version_positive"),
        CheckConstraint(
            "outcome IN ('on_track', 'adjust', 'reverse', 'close')",
            name="decision_review_outcome_valid",
        ),
        CheckConstraint(
            "recommendation_adoption IN ('adopted', 'partially_adopted', 'not_adopted')",
            name="decision_review_recommendation_adoption_valid",
        ),
        CheckConstraint(
            "execution_assessment IN ('as_planned', 'minor_deviation', 'major_deviation', 'not_executed')",
            name="decision_review_execution_assessment_valid",
        ),
        CheckConstraint(
            "decision_process_assessment IN ('sound', 'mixed', 'flawed')",
            name="decision_review_process_assessment_valid",
        ),
        CheckConstraint(
            "outcome_quality IN ('positive', 'mixed', 'negative', 'not_yet_observable')",
            name="decision_review_outcome_quality_valid",
        ),
        Index("ix_decision_reviews_workspace_decision_created", "workspace_id", "decision_record_id", "created_at"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    decision_record_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_case_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_analysis_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_causal_graph_version_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    source_simulation_run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    review_date: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    recommendation_adoption: Mapped[str] = mapped_column(String(24), nullable=False)
    execution_assessment: Mapped[str] = mapped_column(String(32), nullable=False)
    decision_process_assessment: Mapped[str] = mapped_column(String(16), nullable=False)
    outcome_quality: Mapped[str] = mapped_column(String(24), nullable=False)
    observed_indicator_values: Mapped[dict[str, Any]] = json_object_column()
    threshold_breaches: Mapped[list[str]] = json_list_column()
    external_changes: Mapped[list[str]] = json_list_column()
    actual_outcomes: Mapped[list[str]] = json_list_column()
    assumption_results: Mapped[list[dict[str, Any]]] = json_list_column()
    lessons: Mapped[list[str]] = json_list_column()
    next_decision_changes: Mapped[list[str]] = json_list_column()
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    next_review_date: Mapped[str | None] = mapped_column(String(32))
    created_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = created_at_column()


class DecisionLifecycleEvent(Base):
    __tablename__ = "decision_lifecycle_events"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_decision_lifecycle_events_workspace_id"),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_decision_lifecycle_events_workspace_case",
            ondelete="CASCADE",
        ),
        CheckConstraint("payload_hash <> ''", name="decision_lifecycle_event_payload_hash_not_empty"),
        Index("ix_decision_lifecycle_events_workspace_case_created", "workspace_id", "decision_case_id", "created_at"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    from_stage: Mapped[DecisionLifecycleStage] = mapped_column(
        enum_type(DecisionLifecycleStage, "decision_lifecycle_stage"), nullable=False
    )
    to_stage: Mapped[DecisionLifecycleStage] = mapped_column(
        enum_type(DecisionLifecycleStage, "decision_lifecycle_stage"), nullable=False
    )
    actor_type: Mapped[DomainEventActor] = mapped_column(
        enum_type(DomainEventActor, "domain_event_actor"), nullable=False
    )
    actor_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    command_type: Mapped[str] = mapped_column(String(80), nullable=False)
    command_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class CaseVersion(Base):
    __tablename__ = "case_versions"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "decision_case_id",
            "version",
            name="uq_case_versions_workspace_case_version",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_case_versions_workspace_case",
            ondelete="CASCADE",
        ),
        CheckConstraint("version > 0", name="version_positive"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version: Mapped[int | None] = mapped_column(Integer)
    dossier_version: Mapped[int] = mapped_column(Integer, nullable=False)
    dossier_snapshot_hash: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class DossierVersion(Base):
    __tablename__ = "dossier_versions"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "dossier_id",
            "version",
            name="uq_dossier_versions_workspace_dossier_version",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_subject_id", "dossier_id"],
            [
                "decision_subjects.workspace_id",
                "decision_subjects.id",
                "decision_subjects.dossier_id",
            ],
            name="fk_dossier_versions_workspace_subject_dossier",
            ondelete="CASCADE",
        ),
        CheckConstraint("version > 0", name="version_positive"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    dossier_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    decision_subject_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version: Mapped[int | None] = mapped_column(Integer)
    entry_ids: Mapped[list[str]] = json_list_column()
    snapshot_hash: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class DossierEntry(Base):
    __tablename__ = "dossier_entries"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_dossier_entries_workspace_id"),
        ForeignKeyConstraint(
            ["workspace_id", "decision_subject_id"],
            ["decision_subjects.workspace_id", "decision_subjects.id"],
            name="fk_dossier_entries_workspace_subject",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_subject_id", "decision_case_id"],
            [
                "decision_cases.workspace_id",
                "decision_cases.decision_subject_id",
                "decision_cases.decision_case_id",
            ],
            name="fk_dossier_entries_workspace_subject_case",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "(scope = 'subject' AND decision_case_id IS NULL) OR "
            "(scope = 'case' AND decision_case_id IS NOT NULL)",
            name="scope_matches_case",
        ),
        CheckConstraint("version > 0", name="version_positive"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_subject_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    decision_case_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    scope: Mapped[DossierScope] = mapped_column(
        enum_type(DossierScope, "dossier_scope"),
        nullable=False,
    )
    statement_type: Mapped[DossierStatementType] = mapped_column(
        enum_type(DossierStatementType, "dossier_statement_type"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[EntryStatus] = mapped_column(
        enum_type(EntryStatus, "entry_status"),
        nullable=False,
        default=EntryStatus.CANDIDATE,
        server_default=EntryStatus.CANDIDATE.value,
    )
    source_type: Mapped[DossierSourceType] = mapped_column(
        enum_type(DossierSourceType, "dossier_source_type"),
        nullable=False,
    )
    source_ref: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_conversations_workspace_id"),
        UniqueConstraint(
            "workspace_id",
            "id",
            "decision_subject_id",
            name="uq_conversations_workspace_id_subject",
        ),
        UniqueConstraint(
            "workspace_id",
            "id",
            "decision_case_id",
            name="uq_conversations_workspace_id_case",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_subject_id"],
            ["decision_subjects.workspace_id", "decision_subjects.id"],
            name="fk_conversations_workspace_subject",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_subject_id", "decision_case_id"],
            [
                "decision_cases.workspace_id",
                "decision_cases.decision_subject_id",
                "decision_cases.decision_case_id",
            ],
            name="fk_conversations_workspace_subject_case",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "decision_case_id IS NULL OR decision_subject_id IS NOT NULL",
            name="case_requires_subject",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_subject_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    decision_case_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_messages_workspace_id"),
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            name="fk_messages_workspace_conversation",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id", "decision_subject_id"],
            [
                "conversations.workspace_id",
                "conversations.id",
                "conversations.decision_subject_id",
            ],
            name="fk_messages_workspace_conversation_subject",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id", "decision_case_id"],
            [
                "conversations.workspace_id",
                "conversations.id",
                "conversations.decision_case_id",
            ],
            name="fk_messages_workspace_conversation_case",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_subject_id"],
            ["decision_subjects.workspace_id", "decision_subjects.id"],
            name="fk_messages_workspace_subject",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_subject_id", "decision_case_id"],
            [
                "decision_cases.workspace_id",
                "decision_cases.decision_subject_id",
                "decision_cases.decision_case_id",
            ],
            name="fk_messages_workspace_subject_case",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "decision_case_id IS NULL OR decision_subject_id IS NOT NULL",
            name="message_case_requires_subject",
        ),
        Index(
            "ix_messages_workspace_conversation_created",
            "workspace_id",
            "conversation_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    conversation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    decision_subject_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    decision_case_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    role: Mapped[MessageRole] = mapped_column(
        enum_type(MessageRole, "message_role"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(80))
    request_model_id: Mapped[str | None] = mapped_column(String(160))
    response_model_id: Mapped[str | None] = mapped_column(String(160))
    provider_response_version: Mapped[str | None] = mapped_column(String(160))
    token_metadata: Mapped[dict[str, Any]] = json_object_column()
    cost_metadata: Mapped[dict[str, Any]] = json_object_column()
    created_at: Mapped[datetime] = created_at_column()


class CandidateRevision(Base):
    __tablename__ = "candidate_revisions"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_candidate_revisions_workspace_id"),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_candidate_revisions_workspace_case",
            ondelete="CASCADE",
        ),
        CheckConstraint("base_dossier_version > 0", name="base_dossier_version_positive"),
        Index("ix_candidate_revisions_workspace_status", "workspace_id", "status"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    source_type: Mapped[CandidateSourceType] = mapped_column(
        enum_type(CandidateSourceType, "candidate_source_type"),
        nullable=False,
    )
    source_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    base_dossier_version: Mapped[int] = mapped_column(Integer, nullable=False)
    base_case_version: Mapped[int | None] = mapped_column(Integer)
    proposals: Mapped[list[dict[str, Any]]] = json_list_column()
    status: Mapped[CandidateRevisionStatus] = mapped_column(
        enum_type(CandidateRevisionStatus, "candidate_revision_status"),
        nullable=False,
        default=CandidateRevisionStatus.PENDING,
        server_default=CandidateRevisionStatus.PENDING.value,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QuickAnalysisResult(Base):
    __tablename__ = "quick_analysis_results"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_quick_analysis_results_workspace_id"),
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            name="fk_quick_analysis_workspace_conversation",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id", "decision_case_id"],
            [
                "conversations.workspace_id",
                "conversations.id",
                "conversations.decision_case_id",
            ],
            name="fk_quick_analysis_workspace_conversation_case",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_quick_analysis_workspace_case",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    conversation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    decision_case_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    formality: Mapped[QuickAnalysisFormality] = mapped_column(
        enum_type(QuickAnalysisFormality, "quick_analysis_formality"),
        nullable=False,
        default=QuickAnalysisFormality.NON_FORMAL,
        server_default=QuickAnalysisFormality.NON_FORMAL.value,
    )
    judgment: Mapped[str] = mapped_column(Text, nullable=False)
    counter_arguments: Mapped[list[str]] = json_list_column()
    key_unknowns: Mapped[list[str]] = json_list_column()
    next_actions: Mapped[list[str]] = json_list_column()
    created_at: Mapped[datetime] = created_at_column()


class DomainEvent(Base):
    __tablename__ = "domain_events"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_domain_events_workspace_id"),
        Index(
            "ix_domain_events_workspace_aggregate_created",
            "workspace_id",
            "aggregate_type",
            "aggregate_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(160), nullable=False)
    actor: Mapped[DomainEventActor] = mapped_column(
        enum_type(DomainEventActor, "domain_event_actor"),
        nullable=False,
    )
    actor_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    payload: Mapped[dict[str, Any]] = json_object_column()
    created_at: Mapped[datetime] = created_at_column()


class WorkspaceConnector(Base):
    """BYOK read-only connector credential (AGENTS section 12).

    Stores ONLY ciphertext + nonce + key version + display mask; the plaintext
    key exists in memory during one provider call and never persists.
    """

    __tablename__ = "workspace_connectors"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_workspace_connectors_workspace_id"),
        UniqueConstraint(
            "workspace_id", "provider",
            name="uq_workspace_connectors_workspace_provider",
        ),
        CheckConstraint(
            "provider IN ('exa', 'firecrawl', 'tavily', 'model', 'mcp')",
            name="ck_workspace_connectors_provider_in_catalog",
        ),
        Index("ix_workspace_connectors_workspace", "workspace_id"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    mask: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[ConnectorStatus] = mapped_column(
        enum_type(ConnectorStatus, "connector_status"),
        nullable=False,
        default=ConnectorStatus.AVAILABLE,
        server_default=ConnectorStatus.AVAILABLE.value,
    )
    created_at: Mapped[datetime] = created_at_column()
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RetrievalCoverage(Base):
    """Per-run frozen search-coverage index (grey-goo §3; CCR-20260802-P2W2).

    One row per distinct query executed for a run. A repeat query inside the
    same run reuses the frozen row (idempotent) instead of re-hitting the
    provider; the worker's ``_retrieve_once`` is the only writer.
    """

    __tablename__ = "retrieval_coverage"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "analysis_run_id",
            "result_hash",
            name="uq_retrieval_coverage_run_hash",
        ),
        Index("ix_retrieval_coverage_workspace_run", "workspace_id", "analysis_run_id"),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "analysis_run_id"],
            [
                "analysis_runs.workspace_id",
                "analysis_runs.decision_case_id",
                "analysis_runs.analysis_run_id",
            ],
            name="fk_retrieval_coverage_workspace_case_run",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    keywords: Mapped[list[str]] = json_list_column()
    queried_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    result_summary: Mapped[str] = mapped_column(Text, nullable=False)
    result_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    frozen: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    origin_mode: Mapped[OriginMode] = mapped_column(
        ORIGIN_MODE_ENUM,
        nullable=False,
        default=OriginMode.LIVE,
        server_default=OriginMode.LIVE.value,
    )
    created_at: Mapped[datetime] = created_at_column()


class EvidenceFunnelAudit(Base):
    """Persisted TDD discard record (grey-goo 原则⑩; CCR-20260802-P2W2).

    The evidence funnel's audit (admitted / discarded with factor+reason+check
    / warnings / tier counts / opposing count / low-trust share) is written
    per retrieving stage so the E page can show "what was filtered out and
    why" instead of only the survivors.
    """

    __tablename__ = "evidence_funnel_audits"
    __table_args__ = (
        Index("ix_evidence_funnel_audits_workspace_run", "workspace_id", "analysis_run_id"),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "analysis_run_id"],
            [
                "analysis_runs.workspace_id",
                "analysis_runs.decision_case_id",
                "analysis_runs.analysis_run_id",
            ],
            name="fk_evidence_funnel_audits_workspace_case_run",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    admitted: Mapped[int] = mapped_column(Integer, nullable=False)
    discarded: Mapped[list[dict[str, Any]]] = json_list_column()
    warnings: Mapped[list[str]] = json_list_column()
    tier_counts: Mapped[dict[str, int]] = json_object_column()
    opposing_count: Mapped[int] = mapped_column(Integer, nullable=False)
    low_tier_share: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = created_at_column()


# --- Deliberation council (CCR-20260804-DELIB-01) -------------------------
#
# Long-horizon deliberation layer over the factor sandbox: one witness agent
# per factor, one moderator, user interventions between rounds. Every number
# is adjudicated by the deterministic engine (simulate()); agents never
# self-report numeric results. Subjective factors enter only as
# assumed/unknown with a Human signature; nominations never auto-activate.


class DeliberationRun(Base):
    __tablename__ = "deliberation_runs"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_deliberation_runs_workspace_id",
        ),
        Index("ix_deliberation_runs_workspace_case", "workspace_id", "decision_case_id"),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_deliberation_runs_workspace_case",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "max_rounds >= 1 AND max_rounds <= 5",
            name="ck_deliberation_runs_max_rounds_budget",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[DeliberationRunStatus] = mapped_column(
        enum_type(DeliberationRunStatus, "deliberation_run_status"),
        nullable=False,
        default=DeliberationRunStatus.PREPARING,
        server_default=DeliberationRunStatus.PREPARING.value,
    )
    current_round_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    max_rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=3, server_default=text("3"))
    factor_snapshot_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    origin_modes: Mapped[list[OriginMode]] = mapped_column(
        ARRAY(ORIGIN_MODE_ENUM), nullable=False, default=list, server_default=text("'{}'::origin_mode[]")
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class DeliberationFactor(Base):
    __tablename__ = "deliberation_factors"
    __table_args__ = (
        Index("ix_deliberation_factors_workspace_run", "workspace_id", "deliberation_run_id"),
        ForeignKeyConstraint(
            ["workspace_id", "deliberation_run_id"],
            ["deliberation_runs.workspace_id", "deliberation_runs.id"],
            name="fk_deliberation_factors_run",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "provenance <> 'objective' OR source_factor_id IS NOT NULL",
            name="ck_deliberation_factors_objective_requires_source",
        ),
        CheckConstraint(
            "provenance <> 'subjective' OR (statement IS NOT NULL AND author_user_id IS NOT NULL AND evidence_status IS NOT NULL)",
            name="ck_deliberation_factors_subjective_requires_human_stamp",
        ),
        CheckConstraint(
            "strength >= 0 AND strength <= 1",
            name="ck_deliberation_factors_strength_range",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    deliberation_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    provenance: Mapped[DeliberationFactorProvenance] = mapped_column(
        enum_type(DeliberationFactorProvenance, "deliberation_factor_provenance"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(240), nullable=False)
    strength: Mapped[float] = mapped_column(Float, nullable=False)
    source_factor_id: Mapped[str | None] = mapped_column(String(240))
    statement: Mapped[str | None] = mapped_column(Text)
    author_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    dossier_assumption_id: Mapped[str | None] = mapped_column(String(240))
    evidence_status: Mapped[FactorEvidenceStatus | None] = mapped_column(
        enum_type(FactorEvidenceStatus, "factor_evidence_status")
    )
    created_at: Mapped[datetime] = created_at_column()


class DeliberationRound(Base):
    __tablename__ = "deliberation_rounds"
    __table_args__ = (
        UniqueConstraint("workspace_id", "deliberation_run_id", "seq", name="uq_deliberation_rounds_run_seq"),
        ForeignKeyConstraint(
            ["workspace_id", "deliberation_run_id"],
            ["deliberation_runs.workspace_id", "deliberation_runs.id"],
            name="fk_deliberation_rounds_run",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    deliberation_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[DeliberationRoundKind] = mapped_column(
        enum_type(DeliberationRoundKind, "deliberation_round_kind"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        SAEnum("active", "complete", name="deliberation_round_status"),
        nullable=False,
        default="active",
        server_default="active",
    )
    started_at: Mapped[datetime] = created_at_column()
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeliberationMessage(Base):
    __tablename__ = "deliberation_messages"
    __table_args__ = (
        Index("ix_deliberation_messages_workspace_run", "workspace_id", "deliberation_run_id"),
        ForeignKeyConstraint(
            ["workspace_id", "deliberation_run_id"],
            ["deliberation_runs.workspace_id", "deliberation_runs.id"],
            name="fk_deliberation_messages_run",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "speaker <> 'witness' OR speaker_factor_id IS NOT NULL",
            name="ck_deliberation_messages_witness_requires_factor",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    deliberation_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    round_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    speaker: Mapped[DeliberationSpeaker] = mapped_column(
        enum_type(DeliberationSpeaker, "deliberation_speaker"), nullable=False
    )
    speaker_factor_id: Mapped[str | None] = mapped_column(String(240))
    kind: Mapped[DeliberationMessageKind] = mapped_column(
        enum_type(DeliberationMessageKind, "deliberation_message_kind"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB(astext_type=Text))
    stamp_actor: Mapped[ResponsibilityActor] = mapped_column(
        enum_type(ResponsibilityActor, "responsibility_actor"), nullable=False
    )
    stamp_note: Mapped[str | None] = mapped_column(Text)
    origin_mode: Mapped[OriginMode] = mapped_column(
        ORIGIN_MODE_ENUM, nullable=False, default=OriginMode.FIXTURE, server_default=OriginMode.FIXTURE.value
    )
    source_origin_modes: Mapped[list[OriginMode]] = mapped_column(
        ARRAY(ORIGIN_MODE_ENUM), nullable=False, default=list, server_default=text("'{}'::origin_mode[]")
    )
    created_at: Mapped[datetime] = created_at_column()


class DeliberationProposal(Base):
    __tablename__ = "deliberation_proposals"
    __table_args__ = (
        Index("ix_deliberation_proposals_workspace_run", "workspace_id", "deliberation_run_id"),
        ForeignKeyConstraint(
            ["workspace_id", "deliberation_run_id"],
            ["deliberation_runs.workspace_id", "deliberation_runs.id"],
            name="fk_deliberation_proposals_run",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status <> 'accepted' OR decided_at IS NOT NULL",
            name="ck_deliberation_proposals_decided_requires_timestamp",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    deliberation_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    proposer_factor_id: Mapped[str] = mapped_column(String(240), nullable=False)
    kind: Mapped[DeliberationProposalKind] = mapped_column(
        enum_type(DeliberationProposalKind, "deliberation_proposal_kind"), nullable=False
    )
    before: Mapped[dict[str, Any]] = json_object_column()
    after: Mapped[dict[str, Any]] = json_object_column()
    status: Mapped[DeliberationProposalStatus] = mapped_column(
        enum_type(DeliberationProposalStatus, "deliberation_proposal_status"),
        nullable=False,
        default=DeliberationProposalStatus.PENDING,
        server_default=DeliberationProposalStatus.PENDING.value,
    )
    engine_preview: Mapped[dict[str, Any] | None] = mapped_column(JSONB(astext_type=Text))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()


class DeliberationNomination(Base):
    __tablename__ = "deliberation_nominations"
    __table_args__ = (
        Index("ix_deliberation_nominations_workspace_run", "workspace_id", "deliberation_run_id"),
        ForeignKeyConstraint(
            ["workspace_id", "deliberation_run_id"],
            ["deliberation_runs.workspace_id", "deliberation_runs.id"],
            name="fk_deliberation_nominations_run",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status <> 'confirmed' OR confirmed_factor_id IS NOT NULL",
            name="ck_deliberation_nominations_confirmed_requires_factor",
        ),
        CheckConstraint(
            "status = 'confirmed' OR confirmed_factor_id IS NULL",
            name="ck_deliberation_nominations_no_factor_before_confirmation",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    deliberation_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    target_description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[DeliberationNominationStatus] = mapped_column(
        enum_type(DeliberationNominationStatus, "deliberation_nomination_status"),
        nullable=False,
        default=DeliberationNominationStatus.PENDING,
        server_default=DeliberationNominationStatus.PENDING.value,
    )
    confirmed_factor_id: Mapped[str | None] = mapped_column(String(240))
    created_at: Mapped[datetime] = created_at_column()


class DeliberationOutcome(Base):
    __tablename__ = "deliberation_outcomes"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "deliberation_run_id", name="uq_deliberation_outcomes_one_per_run"
        ),
        ForeignKeyConstraint(
            ["workspace_id", "deliberation_run_id"],
            ["deliberation_runs.workspace_id", "deliberation_runs.id"],
            name="fk_deliberation_outcomes_run",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    deliberation_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    condition_projections: Mapped[list[dict[str, Any]]] = json_list_column()
    flip_conditions: Mapped[list[dict[str, Any]]] = json_list_column()
    dissent_log: Mapped[list[dict[str, Any]]] = json_list_column()
    assumption_ledger: Mapped[list[dict[str, Any]]] = json_list_column()
    disclaimer: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class DeliberationEvent(Base):
    """Persisted SSE stream (envelope mirrors AnalysisEvent; Last-Event-ID
    replay reads this table by per-run monotonic sequence)."""

    __tablename__ = "deliberation_events"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "deliberation_run_id", "sequence",
            name="uq_deliberation_events_run_sequence",
        ),
        Index("ix_deliberation_events_workspace_run", "workspace_id", "deliberation_run_id"),
        ForeignKeyConstraint(
            ["workspace_id", "deliberation_run_id"],
            ["deliberation_runs.workspace_id", "deliberation_runs.id"],
            name="fk_deliberation_events_run",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    deliberation_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[DeliberationEventCategory] = mapped_column(
        enum_type(DeliberationEventCategory, "deliberation_event_category"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(120), nullable=False)
    origin_mode: Mapped[OriginMode] = mapped_column(
        ORIGIN_MODE_ENUM, nullable=False, default=OriginMode.FIXTURE, server_default=OriginMode.FIXTURE.value
    )
    source_origin_modes: Mapped[list[OriginMode]] = mapped_column(
        ARRAY(ORIGIN_MODE_ENUM), nullable=False, default=list, server_default=text("'{}'::origin_mode[]")
    )
    payload: Mapped[dict[str, Any]] = json_object_column()
    created_at: Mapped[datetime] = created_at_column()
