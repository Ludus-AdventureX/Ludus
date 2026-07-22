from __future__ import annotations

from enum import StrEnum
from typing import Final, TypeAlias
from uuid import UUID

UserId: TypeAlias = UUID
WorkspaceId: TypeAlias = UUID
DecisionSubjectId: TypeAlias = UUID
InitiativeId: TypeAlias = UUID
DecisionCaseId: TypeAlias = UUID
AnalysisRunId: TypeAlias = UUID


class StatementType(StrEnum):
    FACT = "fact"
    EVIDENCE = "evidence"
    ASSUMPTION = "assumption"
    JUDGMENT = "judgment"
    PREFERENCE = "preference"
    UNKNOWN = "unknown"


class DossierStatementType(StrEnum):
    FACT = "fact"
    EVIDENCE = "evidence"
    ASSUMPTION = "assumption"
    JUDGMENT = "judgment"
    PREFERENCE = "preference"
    UNKNOWN = "unknown"
    CONSTRAINT = "constraint"


class EntryStatus(StrEnum):
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CONFLICTED = "conflicted"


class EvidenceVerdict(StrEnum):
    ACCEPTED = "accepted"
    CONDITIONAL = "conditional"
    LEAD_ONLY = "lead_only"
    REJECTED = "rejected"


class AnalysisLevel(StrEnum):
    QUICK = "quick"
    FOCUSED = "focused"
    FULL = "full"


class AnalysisRunStatus(StrEnum):
    QUEUED = "queued"
    PLANNING = "planning"
    RETRIEVING = "retrieving"
    ANALYZING = "analyzing"
    CRITICIZING = "criticizing"
    SYNTHESIZING = "synthesizing"
    VALIDATING = "validating"
    READY = "ready"
    BLOCKED = "blocked"
    NEEDS_ATTENTION = "needs_attention"
    CANCELLED = "cancelled"


# The detailed plan used the shorter symbol before the canonical contract repair.
# It remains the same Enum object, not a second wire value set.
AnalysisStatus = AnalysisRunStatus


class DecisionLifecycleStage(StrEnum):
    DRAFT = "draft"
    SCOPED = "scoped"
    READY = "ready"
    RUNNING = "running"
    REVIEW = "review"
    PENDING_SIGNOFF = "pending_signoff"
    DECIDED = "decided"
    MONITORING = "monitoring"


DecisionStatus = DecisionLifecycleStage


class CaseOperationalStatus(StrEnum):
    OK = "ok"
    BLOCKED = "blocked"
    NEEDS_ATTENTION = "needs_attention"
    CANCELLED = "cancelled"
    REOPENED = "reopened"
    ARCHIVED = "archived"


class NodeType(StrEnum):
    DECISION = "decision"
    LEVER = "lever"
    CONSTRAINT = "constraint"
    EXTERNAL = "external"
    UNKNOWN = "unknown"
    INTERMEDIATE = "intermediate"
    OUTCOME = "outcome"
    INDICATOR = "indicator"


class StrategicLensType(StrEnum):
    PORTER_FIVE_FORCES = "porter_five_forces"
    PRE_MORTEM = "pre_mortem"
    COUNTERPARTY_RESPONSE_MATRIX = "counterparty_response_matrix"
    SCENARIO_PLANNING = "scenario_planning"
    MEADOWS_LEVERAGE_POINTS = "meadows_leverage_points"


FULL_REQUIRED_STRATEGIC_LENSES: Final[tuple[StrategicLensType, ...]] = (
    StrategicLensType.PORTER_FIVE_FORCES,
    StrategicLensType.PRE_MORTEM,
    StrategicLensType.COUNTERPARTY_RESPONSE_MATRIX,
    StrategicLensType.SCENARIO_PLANNING,
    StrategicLensType.MEADOWS_LEVERAGE_POINTS,
)


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class WorkspaceStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class WorkspaceRole(StrEnum):
    OWNER = "owner"
    MEMBER = "member"


class WorkspaceCapability(StrEnum):
    CONTRIBUTE = "contribute"
    REVIEW = "review"
    SIGN = "sign"
    MANAGE_CONNECTORS = "manage_connectors"


class WorkspaceMembershipStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class SubjectStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class InitiativeStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class DecisionType(StrEnum):
    MARKET_DIRECTION = "market_direction"
    MARKET_ENTRY = "market_entry"
    TECHNOLOGY_ROUTE = "technology_route"
    RESOURCE_ALLOCATION = "resource_allocation"
    UNKNOWN = "unknown"


class DossierScope(StrEnum):
    SUBJECT = "subject"
    CASE = "case"


class DossierSourceType(StrEnum):
    USER = "user"
    AI_CANDIDATE = "ai_candidate"
    EVIDENCE = "evidence"
    ANALYSIS_CANDIDATE = "analysis_candidate"
    SIMULATION_CANDIDATE = "simulation_candidate"


class CandidateSourceType(StrEnum):
    CONVERSATION = "conversation"
    ANALYSIS = "analysis"
    SIMULATION = "simulation"


class CandidateRevisionStatus(StrEnum):
    PENDING = "pending"
    PARTIALLY_ACCEPTED = "partially_accepted"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class QuickAnalysisFormality(StrEnum):
    NON_FORMAL = "non_formal"


class DomainEventActor(StrEnum):
    USER = "user"
    SYSTEM = "system"
    WORKER = "worker"
