"""Formal output wire schemas (Task 10 Step 6, ways_agent_pipeline scope).

Canonical shapes: 06-data-model.md 报告对象 section — ``FocusedResearchResult``
(focused) and ``StructuredReport`` (full), with the shared Recommendation /
RecommendationQuality / ReportValidation vocabulary. These are internal
CanonicalModel views (camelCase on the wire); routes stay unmounted, so
nothing here reaches ``packages/contracts`` until the mounting wave's CCR.

Two discriminant rules live in the models themselves:

* ``FocusedResearchResult`` has NO lens/simulation/PDF surface at all;
* ``StructuredReport.lensArtifactIds`` must be exactly five distinct ids —
  the *semantic* five-artifact equality against the frozen Charter is owned
  by ``app.analyses.quality_gate`` (it needs the database), but the shape
  guard already refuses shortcuts at parse time.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator

from app.contracts.schemas import CanonicalModel, ContentHash, Identifier, NonEmptyText

# Six-dimension quality profile vocabulary (06 RecommendationQuality).
EvidenceAvailability = Literal["sufficient", "conditional", "insufficient", "blocked"]
ClaimSupport = Literal["supported", "conflicted", "assumption_only", "unsupported"]
AssumptionStability = Literal["stable", "fragile", "fatal_unknown"]
CausalReliability = Literal["confirmed", "conditional", "draft", "rejected"]
StrategicRobustness = Literal["robust", "scenario_sensitive", "flip_detected"]
ProcessQuality = Literal["passed", "warning", "blocked"]
QualityDimension = Literal[
    "evidence_availability",
    "claim_support",
    "assumption_stability",
    "causal_reliability",
    "strategic_robustness",
    "process_quality",
]


class RecommendationQuality(CanonicalModel):
    evidence_availability: EvidenceAvailability
    claim_support: ClaimSupport
    assumption_stability: AssumptionStability
    causal_reliability: CausalReliability
    strategic_robustness: StrategicRobustness
    process_quality: ProcessQuality
    weakest_dimension: QualityDimension
    rationale: list[str]


class ReportValidation(CanonicalModel):
    passed: bool
    errors: list[str]
    warnings: list[str]
    checked_at: NonEmptyText


class Threshold(CanonicalModel):
    metric: NonEmptyText
    operator: Literal[">", ">=", "<", "<=", "="]
    value: NonEmptyText
    action_if_missed: NonEmptyText


class LeadingIndicator(CanonicalModel):
    id: Identifier
    metric: NonEmptyText
    expected_direction: Literal["up", "down", "stable"]
    threshold: NonEmptyText
    check_cadence: NonEmptyText


class ActionItem(CanonicalModel):
    id: Identifier
    text: NonEmptyText
    owner: NonEmptyText
    due_at: NonEmptyText
    status: Literal["open", "done", "blocked"]


class UnknownItemEntry(CanonicalModel):
    id: Identifier
    question: NonEmptyText
    priority: Literal["low", "medium", "high", "critical"]
    acquisition_plan: str | None = None
    owner: str | None = None
    due_at: str | None = None
    status: Literal["open", "resolved", "accepted"]


class ChallengeEntry(CanonicalModel):
    """Report-embedded view of one Challenge row (counterArguments)."""

    id: Identifier
    category: Literal[
        "core_assumption",
        "counterargument",
        "failure_pattern",
        "stakeholder_resistance",
        "bias",
        "fatal_flaw",
        "blind_spot",
    ]
    text: NonEmptyText
    severity: Literal["low", "medium", "high", "critical"]
    affected_option_ids: list[Identifier]
    evidence_ids: list[Identifier]
    mitigation: str | None = None
    status: Literal["draft", "confirmed", "rejected"]


class SystemRecommendationOption(CanonicalModel):
    kind: Literal["option"]
    option_id: Identifier


class SystemRecommendationAbstain(CanonicalModel):
    kind: Literal["abstain"]
    reason_codes: list[Identifier]
    rationale: NonEmptyText


SystemRecommendation = SystemRecommendationOption | SystemRecommendationAbstain


class Recommendation(CanonicalModel):
    outcome: SystemRecommendation = Field(discriminator="kind")
    alternative_option_ids: list[Identifier]
    summary: NonEmptyText
    conditions: list[str]
    thresholds: list[Threshold]
    exit_criteria: list[str]
    risks: list[str]
    fragile_assumption_ids: list[Identifier]
    leading_indicators: list[LeadingIndicator]
    next_actions: list[ActionItem]
    review_date: NonEmptyText
    quality: RecommendationQuality


class BriefSection(CanonicalModel):
    decision: NonEmptyText
    why_now: NonEmptyText
    conditions: list[str]
    thresholds: list[Threshold]
    exit_criteria: list[str]
    review_date: NonEmptyText


class ReportSection(CanonicalModel):
    title: NonEmptyText
    summary: NonEmptyText
    claim_ids: list[Identifier]
    evidence_ids: list[Identifier]


class OptionAnalysis(CanonicalModel):
    option_id: Identifier
    summary: NonEmptyText
    benefits: list[str]
    risks: list[str]
    score: dict[str, Any] | None = None


class EvidenceReview(CanonicalModel):
    evidence_ids: list[Identifier]
    conflict_group_ids: list[Identifier]
    freshness_warnings: list[str]
    # Unadjudicable reconciliation conflicts ship inside the report
    # (18 Task 10 Step 3); entries follow ReconciliationFinding.report_entry().
    reconciliation_findings: list[dict[str, Any]] = Field(default_factory=list)


class SimulationSeeds(CanonicalModel):
    candidate_nodes: list[dict[str, Any]]
    candidate_edges: list[dict[str, Any]]


class FocusedResearchResult(CanonicalModel):
    """Focused output: brief, recommendation, evidence, adversarial residue.

    Deliberately owns NO lensArtifactIds, NO simulationSeeds and NO export
    surface — focused runs never create lens/PDF/simulation artifacts.
    """

    schema_version: NonEmptyText
    method_id: Identifier
    method_version: NonEmptyText
    method_content_hash: ContentHash
    executive_brief: BriefSection
    recommendation: Recommendation
    evidence_review: EvidenceReview
    counter_arguments: list[ChallengeEntry]
    residual_uncertainty: list[UnknownItemEntry]
    quality_gate: ReportValidation
    origin_modes: list[Literal["live", "cached", "fixture"]]


class StructuredReport(CanonicalModel):
    """Full output: complete sections plus exactly five lens references."""

    schema_version: NonEmptyText
    method_id: Identifier
    method_version: NonEmptyText
    method_content_hash: ContentHash
    executive_brief: BriefSection
    situation: ReportSection
    sections: list[ReportSection]
    options: list[OptionAnalysis]
    evidence_review: EvidenceReview
    counter_arguments: list[ChallengeEntry]
    recommendation: Recommendation
    residual_uncertainty: list[UnknownItemEntry]
    lens_artifact_ids: list[Identifier]
    simulation_seeds: SimulationSeeds
    quality_gate: ReportValidation
    origin_modes: list[Literal["live", "cached", "fixture"]]
    appendix: list[ReportSection]

    @field_validator("lens_artifact_ids")
    @classmethod
    def exactly_five_distinct_lens_artifacts(cls, values: list[str]) -> list[str]:
        # Shape-level guard only; identity/role/run equality is gate-owned.
        if len(values) != 5:
            raise ValueError("StructuredReport.lensArtifactIds must reference exactly 5 artifacts")
        if len(set(values)) != 5:
            raise ValueError("StructuredReport.lensArtifactIds must be 5 distinct artifacts")
        return values
