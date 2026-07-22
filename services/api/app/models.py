from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
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
    CandidateRevisionStatus,
    CandidateSourceType,
    CaseOperationalStatus,
    DecisionLifecycleStage,
    DecisionType,
    DomainEventActor,
    DossierScope,
    DossierSourceType,
    DossierStatementType,
    EntryStatus,
    InitiativeStatus,
    MessageRole,
    QuickAnalysisFormality,
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
