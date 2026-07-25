from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field, RootModel, field_validator, model_validator

from app.contracts.schemas import CanonicalModel, ContentHash, Identifier, NonEmptyText
from app.types import SignoffRequestStatus


class OptionSystemRecommendation(CanonicalModel):
    kind: Literal["option"]
    option_id: Identifier


class AbstainSystemRecommendation(CanonicalModel):
    kind: Literal["abstain"]
    reason_codes: list[Identifier] = Field(min_length=1)
    rationale: NonEmptyText

    @field_validator("reason_codes")
    @classmethod
    def reason_codes_are_unique(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("abstain reasonCodes must not contain duplicates")
        return values


SystemRecommendationValue = Annotated[
    OptionSystemRecommendation | AbstainSystemRecommendation,
    Field(discriminator="kind"),
]


class SystemRecommendation(RootModel[SystemRecommendationValue]):
    """A system may recommend one option or explicitly abstain, never an empty option."""


class Threshold(CanonicalModel):
    metric: NonEmptyText
    operator: Literal[">", ">=", "<", "<=", "="]
    value: NonEmptyText
    action_if_missed: NonEmptyText


class ActionItem(CanonicalModel):
    id: Identifier
    text: NonEmptyText
    owner: NonEmptyText
    due_at: date
    status: Literal["open", "done", "blocked"]


class LeadingIndicator(CanonicalModel):
    id: Identifier
    metric: NonEmptyText
    expected_direction: Literal["up", "down", "stable"]
    threshold: NonEmptyText
    check_cadence: NonEmptyText


class RecommendationQuality(CanonicalModel):
    evidence_availability: Literal["sufficient", "conditional", "insufficient", "blocked"]
    claim_support: Literal["supported", "conflicted", "assumption_only", "unsupported"]
    assumption_stability: Literal["stable", "fragile", "fatal_unknown"]
    causal_reliability: Literal["confirmed", "conditional", "draft", "rejected"]
    strategic_robustness: Literal["robust", "scenario_sensitive", "flip_detected"]
    process_quality: Literal["passed", "warning", "blocked"]
    weakest_dimension: Literal[
        "evidence_availability",
        "claim_support",
        "assumption_stability",
        "causal_reliability",
        "strategic_robustness",
        "process_quality",
    ]
    rationale: list[NonEmptyText]


class Recommendation(CanonicalModel):
    outcome: SystemRecommendation
    alternative_option_ids: list[Identifier]
    summary: NonEmptyText
    conditions: list[NonEmptyText]
    thresholds: list[Threshold]
    exit_criteria: list[NonEmptyText]
    risks: list[NonEmptyText]
    fragile_assumption_ids: list[Identifier]
    leading_indicators: list[LeadingIndicator]
    next_actions: list[ActionItem]
    review_date: date
    quality: RecommendationQuality


class SignoffPayload(CanonicalModel):
    case_version: int = Field(gt=0)
    source_analysis_run_id: Identifier
    source_report_artifact_id: Identifier
    source_judgment_set_id: Identifier
    source_dissent_record_id: Identifier
    source_causal_graph_id: Identifier | None = None
    source_causal_graph_version_id: Identifier | None = None
    source_simulation_run_id: Identifier | None = None
    system_recommendation: SystemRecommendation
    selected_option_id: Identifier
    decision_draft: NonEmptyText
    conditions: list[NonEmptyText]
    thresholds: list[Threshold]
    exit_criteria: list[NonEmptyText]
    action_items: list[ActionItem]
    leading_indicators: list[LeadingIndicator]
    accepted_unknown_ids: list[Identifier]
    review_date: date

    @model_validator(mode="after")
    def graph_and_simulation_sources_are_consistent(self) -> SignoffPayload:
        graph_pair = (self.source_causal_graph_id, self.source_causal_graph_version_id)
        if (graph_pair[0] is None) != (graph_pair[1] is None):
            raise ValueError("causal graph id and version id must be supplied together")
        if self.source_simulation_run_id is not None and graph_pair[0] is None:
            raise ValueError("a simulation source requires its causal graph source")
        return self


class SignoffRequest(CanonicalModel):
    id: Identifier
    workspace_id: Identifier
    decision_case_id: Identifier
    requested_by_user_id: Identifier
    payload: SignoffPayload
    payload_hash: ContentHash
    status: SignoffRequestStatus
    nonce_hash: ContentHash = Field(exclude=True, repr=False)
    nonce_issued_at: datetime
    expires_at: datetime
    created_at: datetime
    signed_at: datetime | None = None

    @model_validator(mode="after")
    def timestamps_match_status(self) -> SignoffRequest:
        if self.expires_at <= self.nonce_issued_at:
            raise ValueError("signoff expiry must be later than nonce issuance")
        if self.nonce_issued_at < self.created_at:
            raise ValueError("nonceIssuedAt cannot precede createdAt")
        if self.status == SignoffRequestStatus.SIGNED and self.signed_at is None:
            raise ValueError("a signed request must include signedAt")
        if self.signed_at is not None and self.signed_at < self.created_at:
            raise ValueError("signedAt cannot precede createdAt")
        return self


class SignoffSignCommand(CanonicalModel):
    signature_statement: NonEmptyText
    payload_hash: ContentHash
    nonce: NonEmptyText



class SignoffCreateRequest(CanonicalModel):
    payload: SignoffPayload


class SignoffCreated(CanonicalModel):
    signoff_request: SignoffRequest
    nonce: NonEmptyText


class SignoffNonceRotation(CanonicalModel):
    signoff_request: SignoffRequest
    nonce: NonEmptyText


class DecisionRecord(CanonicalModel):
    id: Identifier
    workspace_id: Identifier
    decision_case_id: Identifier
    case_version: int = Field(gt=0)
    record_kind: Literal["original", "revision"]
    supersedes_decision_record_id: Identifier | None = None
    signoff_request_id: Identifier
    payload: SignoffPayload
    payload_hash: ContentHash
    source_analysis_run_id: Identifier
    source_report_artifact_id: Identifier
    source_judgment_set_id: Identifier
    source_dissent_record_id: Identifier
    source_causal_graph_id: Identifier | None = None
    source_causal_graph_version_id: Identifier | None = None
    source_simulation_run_id: Identifier | None = None
    origin_modes: list[Literal["live", "cached", "fixture"]]
    system_recommendation: SystemRecommendation
    selected_option_id: Identifier
    decision_text: NonEmptyText
    conditions: list[NonEmptyText]
    thresholds: list[Threshold]
    exit_criteria: list[NonEmptyText]
    action_items: list[ActionItem]
    leading_indicators: list[LeadingIndicator]
    accepted_unknown_ids: list[Identifier]
    review_date: date
    signed_by_user_id: Identifier
    signed_at: datetime
    signature_statement: NonEmptyText
    signature_hash: ContentHash
    record_hash: ContentHash


class AssumptionResult(CanonicalModel):
    assumption_id: Identifier
    status: Literal["supported", "weakened", "falsified", "unknown"]
    observation: NonEmptyText


class ReviewCreateRequest(CanonicalModel):
    source_case_version: int = Field(gt=0)
    source_analysis_run_id: Identifier
    source_causal_graph_version_id: Identifier | None = None
    source_simulation_run_id: Identifier | None = None
    review_date: date
    outcome: Literal["on_track", "adjust", "reverse", "close"]
    recommendation_adoption: Literal["adopted", "partially_adopted", "not_adopted"]
    execution_assessment: Literal[
        "as_planned", "minor_deviation", "major_deviation", "not_executed"
    ]
    decision_process_assessment: Literal["sound", "mixed", "flawed"]
    outcome_quality: Literal["positive", "mixed", "negative", "not_yet_observable"]
    observed_indicator_values: dict[str, str]
    threshold_breaches: list[Identifier]
    external_changes: list[NonEmptyText]
    actual_outcomes: list[NonEmptyText]
    assumption_results: list[AssumptionResult]
    lessons: list[NonEmptyText]
    next_decision_changes: list[NonEmptyText]
    notes: NonEmptyText
    next_review_date: date | None = None


class Review(CanonicalModel):
    id: Identifier
    workspace_id: Identifier
    decision_case_id: Identifier
    decision_record_id: Identifier
    source_case_version: int
    source_analysis_run_id: Identifier
    source_causal_graph_version_id: Identifier | None = None
    source_simulation_run_id: Identifier | None = None
    review_date: date
    outcome: Literal["on_track", "adjust", "reverse", "close"]
    recommendation_adoption: Literal["adopted", "partially_adopted", "not_adopted"]
    execution_assessment: Literal[
        "as_planned", "minor_deviation", "major_deviation", "not_executed"
    ]
    decision_process_assessment: Literal["sound", "mixed", "flawed"]
    outcome_quality: Literal["positive", "mixed", "negative", "not_yet_observable"]
    observed_indicator_values: dict[str, str]
    threshold_breaches: list[Identifier]
    external_changes: list[NonEmptyText]
    actual_outcomes: list[NonEmptyText]
    assumption_results: list[AssumptionResult]
    lessons: list[NonEmptyText]
    next_decision_changes: list[NonEmptyText]
    notes: NonEmptyText
    next_review_date: date | None = None
    created_by: Identifier
    created_at: datetime
