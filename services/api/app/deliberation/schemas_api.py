"""Wire DTOs for the deliberation council (CCR-20260804-DELIB-01, Wave 1).

Strict camelCase ``CanonicalModel`` views transcribed from the CCR ruling.
No router is mounted in this wave, so these shapes do not reach the
generated contracts yet; Wave 2 mounts the routes and regenerates.

Probability ban (§7): every free-text field that can carry model output is
scanned by ``_assert_no_probability_claim`` — "成功概率"/"结论正确概率" or any
percentaged probability assertion is rejected at the schema boundary. Numbers
are only ever engine outputs (outcomeScore/strength/flipThreshold).
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, model_validator

from app.contracts.schemas import CanonicalModel, Identifier, NonEmptyText
from app.types import OriginMode

_PROBABILITY_CLAIM_PATTERN = re.compile(
    r"成功概率|结论正确概率|正确的概率|成功率\s*[:：]?\s*\d|概率\s*[:：]?\s*\d+\s*%",
)


def _assert_no_probability_claim(*values: str | None) -> None:
    for value in values:
        if value and _PROBABILITY_CLAIM_PATTERN.search(value):
            raise ValueError("deliberation outputs must not carry probability claims (§7)")


class DeliberationRunStatus(StrEnum):
    PREPARING = "preparing"
    RUNNING = "running"
    AWAITING_USER = "awaiting_user"
    COMPLETE = "complete"
    CANCELLED = "cancelled"


class DeliberationFactorProvenance(StrEnum):
    OBJECTIVE = "objective"
    SUBJECTIVE = "subjective"


class SubjectiveEvidenceStatus(StrEnum):
    # Subjective factors NEVER impersonate supported/conditional (§10).
    ASSUMED = "assumed"
    UNKNOWN = "unknown"


class DeliberationRoundKind(StrEnum):
    OPENING = "opening"
    CHALLENGE = "challenge"
    VERDICT = "verdict"


class DeliberationSpeaker(StrEnum):
    WITNESS = "witness"
    MODERATOR = "moderator"
    USER = "user"


class DeliberationMessageKind(StrEnum):
    STATEMENT = "statement"
    CHALLENGE = "challenge"
    REBUTTAL = "rebuttal"
    PROPOSAL = "proposal"
    INTERVENTION = "intervention"
    NOMINATION = "nomination"
    VERDICT_SUMMARY = "verdict_summary"


class DeliberationProposalKind(StrEnum):
    FACTOR_STRENGTH = "factor_strength"
    EDGE_VALIDITY = "edge_validity"
    NEW_FACTOR = "new_factor"


class DeliberationProposalStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class DeliberationNominationStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class ResponsibilityActor(StrEnum):
    HUMAN = "human"
    ANALYSIS = "analysis"
    UNKNOWN = "unknown"


MAX_DELIBERATION_ROUNDS = 5


class DeliberationAnchorView(CanonicalModel):
    id: Identifier
    decision_case_id: Identifier
    status: DeliberationRunStatus
    current_round_seq: int = Field(ge=0)
    max_rounds: int = Field(ge=1, le=MAX_DELIBERATION_ROUNDS)
    created_at: datetime
    updated_at: datetime


class DeliberationFactorView(CanonicalModel):
    id: Identifier
    deliberation_run_id: Identifier
    provenance: DeliberationFactorProvenance
    label: NonEmptyText
    strength: float = Field(ge=0.0, le=1.0)
    source_factor_id: str | None = None
    statement: str | None = None
    author_user_id: str | None = None
    dossier_assumption_id: str | None = None
    evidence_status: SubjectiveEvidenceStatus | None = None

    @model_validator(mode="after")
    def _enforce_provenance_invariants(self) -> "DeliberationFactorView":
        if self.provenance is DeliberationFactorProvenance.OBJECTIVE:
            if not self.source_factor_id:
                raise ValueError("objective factor must reference its source factor")
        else:
            if not self.statement or not self.author_user_id:
                raise ValueError("subjective factor requires statement and human author")
            if self.evidence_status is None:
                raise ValueError("subjective factor must carry assumed/unknown status")
        return self


class DeliberationRoundView(CanonicalModel):
    id: Identifier
    deliberation_run_id: Identifier
    seq: int = Field(ge=1)
    kind: DeliberationRoundKind
    status: Literal["active", "complete"]
    started_at: datetime
    ended_at: datetime | None = None


class DeliberationMessageView(CanonicalModel):
    id: Identifier
    deliberation_run_id: Identifier
    round_id: Identifier
    speaker: DeliberationSpeaker
    speaker_factor_id: str | None = None
    kind: DeliberationMessageKind
    content: NonEmptyText
    structured_payload: dict[str, Any] | None = None
    stamp_actor: ResponsibilityActor
    stamp_note: str | None = None
    origin_mode: OriginMode
    source_origin_modes: list[OriginMode]
    created_at: datetime

    @model_validator(mode="after")
    def _enforce_speaker_invariants(self) -> "DeliberationMessageView":
        if self.speaker is DeliberationSpeaker.WITNESS and not self.speaker_factor_id:
            raise ValueError("witness message must reference its factor")
        _assert_no_probability_claim(self.content, self.stamp_note)
        return self


class FactorSandboxProjection(CanonicalModel):
    """Deterministic engine preview — never a model output."""

    outcome_score: float = Field(ge=0.0, le=1.0)
    verdict: Literal["proceed", "hold"]
    flip_threshold: float = Field(ge=0.0, le=1.0)
    top_drivers: list[dict[str, Any]] = Field(default_factory=list)


class DeliberationProposalView(CanonicalModel):
    id: Identifier
    deliberation_run_id: Identifier
    proposer_factor_id: Identifier
    kind: DeliberationProposalKind
    before: dict[str, Any]
    after: dict[str, Any]
    status: DeliberationProposalStatus
    engine_preview: FactorSandboxProjection | None = None
    decided_at: datetime | None = None


class DeliberationNominationView(CanonicalModel):
    id: Identifier
    deliberation_run_id: Identifier
    rationale: NonEmptyText
    target_description: NonEmptyText
    status: DeliberationNominationStatus
    confirmed_factor_id: str | None = None

    @model_validator(mode="after")
    def _confirmed_requires_factor(self) -> "DeliberationNominationView":
        if self.status is DeliberationNominationStatus.CONFIRMED and not self.confirmed_factor_id:
            raise ValueError("confirmed nomination must reference the created factor")
        if self.status is not DeliberationNominationStatus.CONFIRMED and self.confirmed_factor_id:
            raise ValueError("nomination factor must not exist before confirmation")
        return self


class ConditionProjectionView(CanonicalModel):
    accepted_proposal_ids: list[str]
    projection: FactorSandboxProjection
    condition: NonEmptyText

    @model_validator(mode="after")
    def _no_probability_in_condition(self) -> "ConditionProjectionView":
        _assert_no_probability_claim(self.condition)
        return self


class FlipConditionView(CanonicalModel):
    factor_id: Identifier
    label: NonEmptyText
    flip_value: float = Field(ge=0.0, le=1.0)
    score_delta: float


class DissentEntryView(CanonicalModel):
    factor_id: Identifier
    witness_label: NonEmptyText
    original_stance: NonEmptyText
    overturned_basis: NonEmptyText


class AssumptionLedgerEntryView(CanonicalModel):
    factor_id: Identifier
    label: NonEmptyText
    provenance: DeliberationFactorProvenance
    evidence_status: SubjectiveEvidenceStatus | None = None
    final_strength: float = Field(ge=0.0, le=1.0)


DELIBERATION_DISCLAIMER = "沙盘与议会不代表精确预测。"


class DeliberationOutcomeView(CanonicalModel):
    id: Identifier
    deliberation_run_id: Identifier
    condition_projections: list[ConditionProjectionView]
    flip_conditions: list[FlipConditionView]
    dissent_log: list[DissentEntryView]
    assumption_ledger: list[AssumptionLedgerEntryView]
    disclaimer: NonEmptyText = DELIBERATION_DISCLAIMER
    created_at: datetime


class DeliberationRunDetailView(CanonicalModel):
    id: Identifier
    workspace_id: Identifier
    decision_case_id: Identifier
    status: DeliberationRunStatus
    current_round_seq: int = Field(ge=0)
    max_rounds: int = Field(ge=1, le=MAX_DELIBERATION_ROUNDS)
    factor_snapshot_hash: NonEmptyText
    origin_modes: list[OriginMode]
    factors: list[DeliberationFactorView]
    rounds: list[DeliberationRoundView]
    pending_proposal_count: int = Field(ge=0)
    pending_nomination_count: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime


class DeliberationEventView(CanonicalModel):
    """Envelope mirrors AnalysisEvent field-for-field (10-api §SSE 事件)."""

    id: Identifier
    sequence: int = Field(ge=1)
    workspace_id: Identifier
    decision_case_id: Identifier
    deliberation_run_id: Identifier
    category: Literal[
        "deliberation.round",
        "deliberation.message",
        "deliberation.proposal",
        "deliberation.nomination",
        "deliberation.outcome",
    ]
    type: NonEmptyText
    origin_mode: OriginMode
    source_origin_modes: list[OriginMode]
    created_at: datetime
    payload: dict[str, Any]


# --- Write-side request bodies (Wave 2 mounts the routes) ------------------


class SubjectiveFactorDeclaration(CanonicalModel):
    label: NonEmptyText
    statement: NonEmptyText
    strength: float = Field(ge=0.0, le=1.0)
    dossier_assumption_id: str | None = None

    @model_validator(mode="after")
    def _no_probability_in_statement(self) -> "SubjectiveFactorDeclaration":
        _assert_no_probability_claim(self.statement)
        return self


class CreateDeliberationRequest(CanonicalModel):
    subjective_factors: list[SubjectiveFactorDeclaration] = Field(default_factory=list)
    max_rounds: int = Field(default=3, ge=1, le=MAX_DELIBERATION_ROUNDS)


class DeliberationInterventionRequest(CanonicalModel):
    kind: Literal["interject", "challenge_witness", "declare_subjective_factor", "reopen_round"]
    text: str | None = None
    target_factor_id: str | None = None
    subjective_factor: SubjectiveFactorDeclaration | None = None

    @model_validator(mode="after")
    def _enforce_kind_payload(self) -> "DeliberationInterventionRequest":
        if self.kind == "interject" and not self.text:
            raise ValueError("interject requires text")
        if self.kind == "challenge_witness" and not (self.target_factor_id and self.text):
            raise ValueError("challenge_witness requires target factor and question")
        if self.kind == "declare_subjective_factor" and self.subjective_factor is None:
            raise ValueError("declare_subjective_factor requires the full declaration")
        return self


class ProposalDecisionRequest(CanonicalModel):
    decision: Literal["accepted", "rejected"]


class NominationDecisionRequest(CanonicalModel):
    decision: Literal["confirmed", "rejected"]
    subjective_factor: SubjectiveFactorDeclaration | None = None

    @model_validator(mode="after")
    def _confirmed_requires_declaration(self) -> "NominationDecisionRequest":
        if self.decision == "confirmed" and self.subjective_factor is None:
            raise ValueError("confirming a nomination requires the subjective factor declaration")
        return self
