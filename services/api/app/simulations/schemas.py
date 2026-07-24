from __future__ import annotations

import math
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.contracts.schemas import CanonicalModel, ContentHash, Identifier, NonEmptyText
from app.types import (
    ConstraintComparison,
    EdgePolarity,
    FactorAuthorship,
    FactorControllability,
    FactorEvidenceStatus,
    GraphBranchStatus,
    GraphVersionStatus,
    NodeType,
    OriginMode,
    SimulationConvergenceStatus,
    SimulationMode,
)


class SimulationOptionScore(CanonicalModel):
    option_id: Identifier
    score: float


class SimulationTopDriver(CanonicalModel):
    node_id: Identifier
    score_delta: float


class SimulationRun(CanonicalModel):
    id: Identifier
    workspace_id: Identifier
    decision_case_id: Identifier
    graph_id: Identifier
    graph_version_id: Identifier
    strategy_version_id: Identifier
    scenario_version_id: Identifier
    score_definition_id: Identifier
    score_definition_version: NonEmptyText
    decision_maker_profile_id: Identifier
    decision_maker_profile_version: int = Field(gt=0)
    risk_tolerance: float = Field(ge=0, le=1)
    engine_version: NonEmptyText
    scenario_id: Identifier
    simulation_mode: SimulationMode
    epsilon: float = Field(gt=0)
    max_steps: int = Field(gt=0)
    steps: int = Field(ge=0)
    input_hash: ContentHash
    node_results: dict[str, float]
    option_scores: list[SimulationOptionScore]
    top_drivers: list[SimulationTopDriver]
    recommendation_shift: str
    convergence_status: SimulationConvergenceStatus
    origin_modes: list[OriginMode]
    created_at: datetime

    @field_validator("origin_modes")
    @classmethod
    def origin_modes_are_unique(cls, values: list[OriginMode]) -> list[OriginMode]:
        if len(values) != len(set(values)):
            raise ValueError("originModes must not contain duplicates")
        return values

    @model_validator(mode="after")
    def replay_numbers_are_finite_and_bounded(self) -> SimulationRun:
        if self.steps > self.max_steps:
            raise ValueError("steps cannot exceed maxSteps")
        numeric_values = [
            self.risk_tolerance,
            self.epsilon,
            *self.node_results.values(),
            *(item.score for item in self.option_scores),
            *(item.score_delta for item in self.top_drivers),
        ]
        if not all(math.isfinite(value) for value in numeric_values):
            raise ValueError("simulation replay fields must contain only finite numbers")
        return self


# --- CCR-20260724-SIM-01: canonical graph/scenario wire types ----------------
# These wire types are canonical contracts for the graph aggregate. They are
# not yet referenced by any route and are intentionally NOT registered in the
# generated OpenAPI catalog until the graph API slice lands via its own CCR.


class GraphProvenanceRef(CanonicalModel):
    object_type: Literal["claim", "evidence", "assumption", "user"]
    object_id: Identifier


class CausalGraph(CanonicalModel):
    id: Identifier
    workspace_id: Identifier
    decision_case_id: Identifier
    report_artifact_id: Identifier
    current_graph_version_id: Identifier | None = None
    title: NonEmptyText
    origin_modes: list[OriginMode]
    created_at: datetime
    updated_at: datetime


class CausalNode(CanonicalModel):
    id: Identifier
    label: NonEmptyText
    type: NodeType
    baseline: float
    current: float
    min: float
    max: float
    unit: str | None = None
    normalization: Literal["linear", "inverse_linear"]
    sensitivity_step: float | None = Field(default=None, gt=0)
    controllability: FactorControllability
    authorship: FactorAuthorship
    evidence_status: FactorEvidenceStatus
    evidence_quality_score: float = Field(ge=0, le=1)
    evidence_ids: list[Identifier]
    assumption_ids: list[Identifier]
    rationale: NonEmptyText
    status: Literal["draft", "confirmed", "rejected"]
    editable: bool

    @model_validator(mode="after")
    def business_values_are_finite_and_bounded(self) -> CausalNode:
        values = [self.baseline, self.current, self.min, self.max]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("node business values must be finite")
        if not self.min < self.max:
            raise ValueError("min must be strictly below max")
        if not (self.min <= self.baseline <= self.max and self.min <= self.current <= self.max):
            raise ValueError("baseline and current must lie within [min, max]")
        return self


class CausalEdge(CanonicalModel):
    id: Identifier
    source_node_id: Identifier
    target_node_id: Identifier
    polarity: EdgePolarity
    strength: float = Field(ge=0, le=1)
    delay_steps: int = Field(ge=0)
    authorship: FactorAuthorship
    evidence_status: FactorEvidenceStatus
    relationship_quality_score: float = Field(ge=0, le=1)
    rationale: NonEmptyText
    claim_ids: list[Identifier]
    evidence_ids: list[Identifier]
    assumption_ids: list[Identifier]
    status: Literal["draft", "confirmed", "rejected", "conditional"]


class GraphVersion(CanonicalModel):
    id: Identifier
    workspace_id: Identifier
    graph_id: Identifier
    decision_case_id: Identifier
    case_version: int = Field(gt=0)
    source_report_artifact_id: Identifier
    version: int = Field(gt=0)
    branch_id: Identifier | None = None
    parent_version_id: Identifier | None = None
    source_graph_version_id: Identifier | None = None
    status: GraphVersionStatus
    provenance: list[GraphProvenanceRef]
    origin_modes: list[OriginMode]
    title: NonEmptyText
    content_hash: ContentHash
    nodes: list[CausalNode]
    edges: list[CausalEdge]
    created_by: Identifier
    created_at: datetime
    confirmed_at: datetime | None = None

    @model_validator(mode="after")
    def confirmed_requires_timestamp_and_resolvable_edges(self) -> GraphVersion:
        if self.status is GraphVersionStatus.CONFIRMED and self.confirmed_at is None:
            raise ValueError("confirmed graph versions must carry confirmedAt")
        node_ids = {node.id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("node ids must be unique within a graph version")
        edge_ids = {edge.id for edge in self.edges}
        if len(edge_ids) != len(self.edges):
            raise ValueError("edge ids must be unique within a graph version")
        for edge in self.edges:
            if edge.source_node_id not in node_ids or edge.target_node_id not in node_ids:
                raise ValueError("edges must reference nodes of the same graph version")
        return self


class StrategyVersion(CanonicalModel):
    id: Identifier
    workspace_id: Identifier
    graph_id: Identifier
    decision_case_id: Identifier
    version: int = Field(gt=0)
    option_id: Identifier
    node_overrides: dict[Identifier, float]
    enabled_edge_ids: list[Identifier]

    @field_validator("node_overrides")
    @classmethod
    def overrides_are_finite(cls, values: dict[str, float]) -> dict[str, float]:
        if not all(math.isfinite(value) for value in values.values()):
            raise ValueError("node overrides must be finite business values")
        return values


class ScenarioEarlyWarningSignal(CanonicalModel):
    signal_id: Identifier
    type: Literal["quantitative", "structural", "behavioral"]
    observable: NonEmptyText
    threshold_or_pattern: NonEmptyText
    cadence: NonEmptyText


class ScenarioVersion(CanonicalModel):
    """riskTolerance is forbidden here by contract (AGENTS section 10);
    CanonicalModel(extra="forbid") rejects it on the wire.
    """

    id: Identifier
    workspace_id: Identifier
    graph_id: Identifier
    decision_case_id: Identifier
    source_lens_artifact_id: Identifier
    source_strategic_scenario_id: Identifier
    scenario_id: Identifier
    version: int = Field(gt=0)
    name: NonEmptyText
    description: NonEmptyText
    default_edge_multiplier: float = Field(ge=0)
    edge_multipliers: dict[Identifier, float]
    node_shifts: dict[Identifier, float]
    strategy_survives: bool
    early_warning_signals: list[ScenarioEarlyWarningSignal]
    damping: float = Field(gt=0, le=1)
    created_at: datetime

    @model_validator(mode="after")
    def multipliers_and_shifts_are_bounded(self) -> ScenarioVersion:
        if not all(
            math.isfinite(value) and value >= 0 for value in self.edge_multipliers.values()
        ):
            raise ValueError("edge multipliers must be finite and non-negative")
        if not all(
            math.isfinite(value) and -1 <= value <= 1 for value in self.node_shifts.values()
        ):
            raise ValueError("node shifts are normalized deltas within [-1, 1]")
        return self


class OptionOutcomeMapping(CanonicalModel):
    option_id: Identifier
    outcome_node_id: Identifier
    goal_id: Identifier
    weight: float = Field(ge=0)


class RiskWeight(CanonicalModel):
    option_id: Identifier
    risk_node_id: Identifier
    weight: float = Field(ge=0)


class ConstraintRule(CanonicalModel):
    option_id: Identifier
    constraint_node_id: Identifier
    operator: ConstraintComparison
    threshold: float
    penalty: float = Field(ge=0)

    @field_validator("threshold")
    @classmethod
    def threshold_is_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("constraint thresholds must be finite")
        return value


class ScoreDefinition(CanonicalModel):
    id: Identifier
    workspace_id: Identifier
    graph_id: Identifier
    decision_case_id: Identifier
    version: NonEmptyText
    option_outcome_mappings: list[OptionOutcomeMapping]
    risk_weights: list[RiskWeight]
    constraint_rules: list[ConstraintRule]
    content_hash: ContentHash


class GraphBranch(CanonicalModel):
    id: Identifier
    workspace_id: Identifier
    graph_id: Identifier
    name: NonEmptyText
    base_graph_version_id: Identifier
    head_graph_version_id: Identifier
    status: GraphBranchStatus
