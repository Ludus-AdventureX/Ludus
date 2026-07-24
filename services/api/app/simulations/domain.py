"""Internal domain value objects for the deterministic causal simulation engine.

The canonical graph wire schemas (GraphVersion / CausalNode / CausalEdge /
StrategyVersion / ScenarioVersion / ScoreDefinition / OptionOutcomeMapping / RiskWeight /
ConstraintRule / GraphBranch) exist on main since CCR-20260724-SIM-01 and live in
``app.simulations.schemas``. The dataclasses below are a separate, engine-internal layer:

* They are *engine-internal* immutable value objects — NOT ORM rows and NOT wire DTOs.
  They perform no I/O and import no database/framework code, keeping the engine a
  deterministic pure function per ``09-simulation-engine.md`` and ``26`` invariants.
* They are assembled deterministically by the assembly layer
  (``app.simulations.assembly``) from already-validated canonical persistence/wire data;
  callers never hand-build them from untrusted input.
* Canonical enum authority is ``app.types``: ``NodeType``, ``SimulationMode``,
  ``SimulationConvergenceStatus``, ``EdgePolarity``, ``GraphVersionStatus``,
  ``FactorControllability`` (imported as ``Controllability``) and
  ``FactorEvidenceStatus`` (imported as ``EvidenceStatus``) — pure import aliases,
  never parallel enums.
* ``ElementStatus``, ``Normalization`` and ``Comparison`` remain engine-internal.
* ``Comparison`` is the currently executable operator subset (``>``, ``>=``, ``<``,
  ``<=``). The canonical ``ConstraintComparison`` additionally defines ``=``, which the
  engine does NOT execute; the assembly layer fails closed with
  ``score_constraint_operator_unsupported``.
* Strategy edge gating is NOT implemented: non-empty ``enabledEdgeIds`` fail closed with
  ``strategy_edge_gating_unsupported``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum

from app.types import NodeType, SimulationConvergenceStatus, SimulationMode
from app.types import EdgePolarity, GraphVersionStatus
from app.types import FactorControllability as Controllability
from app.types import FactorEvidenceStatus as EvidenceStatus


def _require_finite(label: str, *values: float) -> None:
    for value in values:
        if not math.isfinite(value):
            raise SimulationError(f"{label} must be a finite number, got {value!r}")

# --- Engine-internal enums --------------------------------------------------------------
# CCR-20260724-SIM-01 promoted EdgePolarity, GraphVersionStatus, FactorControllability and
# FactorEvidenceStatus to app.types with verbatim-identical values; they are imported above
# (the latter two under their original domain API names). The three enums below were NOT
# promoted verbatim and stay engine-internal:
# - ElementStatus: no canonical element-status enum exists; the DB persists the bulk-review
#   state as CHECK-locked strings (graph_nodes/graph_edges.review_status).
# - Normalization: the canonical wire contract uses a Literal, the DB a CHECK-locked string.
# - Comparison: canonical ConstraintComparison adds EQ "=", which sim-engine-1.0.0 scoring
#   does not evaluate; adopting it would silently misroute "=" to "<=" in the engine's
#   comparison fall-through. "=" rules are rejected fail-fast at the assembly boundary.


class ElementStatus(StrEnum):
    """Confirmation status shared by nodes and edges inside a graph version."""

    DRAFT = "draft"
    CONFIRMED = "confirmed"
    CONDITIONAL = "conditional"
    REJECTED = "rejected"


class Normalization(StrEnum):
    LINEAR = "linear"
    INVERSE_LINEAR = "inverse_linear"


class Comparison(StrEnum):
    GREATER_THAN = ">"
    GREATER_OR_EQUAL = ">="
    LESS_THAN = "<"
    LESS_OR_EQUAL = "<="


# --- Errors ------------------------------------------------------------------------------


class SimulationError(ValueError):
    """Base class for deterministic, structured simulation input/authorization errors."""


class GraphInvariantError(SimulationError):
    """A graph structure invariant was violated (ids, references, evidence rules)."""


class SimulationAuthorizationError(SimulationError):
    """A formal run was requested against a non-authorized graph/node set."""


class SimulationInputError(SimulationError):
    """Simulation inputs (strategy/scenario/score) do not belong to the graph."""


# --- Graph value objects -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CausalNode:
    id: str
    label: str
    type: NodeType
    baseline: float
    min: float
    max: float
    unit: str
    normalization: Normalization = Normalization.LINEAR
    sensitivity_step: float | None = None
    controllability: Controllability = Controllability.UNCONTROLLABLE
    authorship: str = "generated"
    evidence_status: EvidenceStatus = EvidenceStatus.UNKNOWN
    evidence_quality_score: float = 0.0
    evidence_ids: tuple[str, ...] = ()
    assumption_ids: tuple[str, ...] = ()
    rationale: str = ""
    status: ElementStatus = ElementStatus.CONFIRMED
    editable: bool = False

    def __post_init__(self) -> None:
        if not self.id:
            raise GraphInvariantError("node id must be non-empty")
        _require_finite(f"node {self.id} bounds", self.min, self.max, self.baseline)
        if self.sensitivity_step is not None:
            _require_finite(f"node {self.id} sensitivityStep", self.sensitivity_step)
        if self.min >= self.max:
            raise GraphInvariantError(f"node {self.id}: min must be strictly below max")
        if not (self.min <= self.baseline <= self.max):
            raise GraphInvariantError(f"node {self.id}: baseline must lie within [min, max]")
        if not (0.0 <= self.evidence_quality_score <= 1.0):
            raise GraphInvariantError(f"node {self.id}: evidenceQualityScore must be in [0, 1]")
        if self.sensitivity_step is not None and self.sensitivity_step <= 0:
            raise GraphInvariantError(f"node {self.id}: sensitivityStep must be positive")
        # 09: a factor without traceable evidence may only be assumed/unknown.
        if self.evidence_status == EvidenceStatus.SUPPORTED and not self.evidence_ids:
            raise GraphInvariantError(
                f"node {self.id}: supported evidenceStatus requires non-empty evidenceIds"
            )


@dataclass(frozen=True, slots=True)
class CausalEdge:
    id: str
    source_node_id: str
    target_node_id: str
    polarity: EdgePolarity
    strength: float
    delay_steps: int = 0
    relationship_quality_score: float = 0.0
    claim_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    assumption_ids: tuple[str, ...] = ()
    status: ElementStatus = ElementStatus.DRAFT

    def __post_init__(self) -> None:
        if not self.id:
            raise GraphInvariantError("edge id must be non-empty")
        _require_finite(f"edge {self.id} strength", self.strength, self.relationship_quality_score)
        if self.source_node_id == self.target_node_id:
            raise GraphInvariantError(f"edge {self.id}: self-loops are not allowed")
        if not (0.0 <= self.strength <= 1.0):
            raise GraphInvariantError(f"edge {self.id}: strength must be in [0, 1]")
        if not (0.0 <= self.relationship_quality_score <= 1.0):
            raise GraphInvariantError(
                f"edge {self.id}: relationshipQualityScore must be in [0, 1]"
            )
        if self.delay_steps < 0:
            raise GraphInvariantError(f"edge {self.id}: delaySteps must be >= 0")
        # 09: assumption-only edges are canonical draft with non-empty assumptionIds; they
        # must never be silently promoted. A confirmed edge must carry traceable claims.
        if not self.claim_ids and not self.evidence_ids and not self.assumption_ids:
            raise GraphInvariantError(
                f"edge {self.id}: must reference at least one claim/evidence/assumption"
            )
        if self.status == ElementStatus.CONFIRMED and not self.claim_ids:
            raise GraphInvariantError(
                f"edge {self.id}: confirmed edges require non-empty claimIds"
            )


@dataclass(frozen=True, slots=True)
class GraphVersion:
    id: str
    graph_id: str
    status: GraphVersionStatus
    nodes: tuple[CausalNode, ...]
    edges: tuple[CausalEdge, ...]

    def __post_init__(self) -> None:
        node_ids = [node.id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise GraphInvariantError("duplicate node ids in graph version")
        edge_ids = [edge.id for edge in self.edges]
        if len(edge_ids) != len(set(edge_ids)):
            raise GraphInvariantError("duplicate edge ids in graph version")
        known = set(node_ids)
        for edge in self.edges:
            if edge.source_node_id not in known:
                raise GraphInvariantError(f"edge {edge.id}: unknown source {edge.source_node_id}")
            if edge.target_node_id not in known:
                raise GraphInvariantError(f"edge {edge.id}: unknown target {edge.target_node_id}")

    def node(self, node_id: str) -> CausalNode:
        for candidate in self.nodes:
            if candidate.id == node_id:
                return candidate
        raise GraphInvariantError(f"unknown node id {node_id}")

    def with_value(self, node_id: str, value: float) -> GraphVersion:
        """Return a new immutable graph version with one node's baseline replaced.

        Used for stress tests and sensitivity perturbations. The original version is never
        mutated, preserving version immutability.
        """

        target = self.node(node_id)
        clamped = min(max(value, target.min), target.max)
        from dataclasses import replace

        new_nodes = tuple(
            replace(node, baseline=clamped) if node.id == node_id else node for node in self.nodes
        )
        return GraphVersion(
            id=self.id, graph_id=self.graph_id, status=self.status, nodes=new_nodes, edges=self.edges
        )


# --- Strategy / Scenario / Score value objects -------------------------------------------


@dataclass(frozen=True, slots=True)
class StrategyVersion:
    """Active decision/lever overrides chosen by the decision maker (business units)."""

    id: str
    version: int
    node_overrides: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.version <= 0:
            raise SimulationInputError("strategy version must be positive")


@dataclass(frozen=True, slots=True)
class EarlyWarningSignal:
    signal_id: str
    type: str
    observable: str
    threshold_or_pattern: str
    cadence: str


@dataclass(frozen=True, slots=True)
class ScenarioVersion:
    """Immutable external/unknown assumption set.

    Per ``09`` and ``26`` this MUST NOT carry ``riskTolerance``; risk tolerance belongs to
    the frozen Profile/Charter/Strategy/ScoreDefinition. ``node_shifts`` are normalized
    ``[-1, 1]`` deltas, never business units.
    """

    id: str
    version: int
    source_lens_artifact_id: str
    source_strategic_scenario_id: str
    strategy_survives: bool
    early_warning_signals: tuple[EarlyWarningSignal, ...] = ()
    default_edge_multiplier: float = 1.0
    edge_multipliers: dict[str, float] = field(default_factory=dict)
    node_shifts: dict[str, float] = field(default_factory=dict)
    damping: float = 0.85

    def __post_init__(self) -> None:
        if self.version <= 0:
            raise SimulationInputError("scenario version must be positive")
        if not self.source_lens_artifact_id:
            raise SimulationInputError("scenario requires sourceLensArtifactId")
        if not self.source_strategic_scenario_id:
            raise SimulationInputError("scenario requires sourceStrategicScenarioId")
        if not (0.0 < self.damping <= 1.0):
            raise SimulationInputError("scenario damping must be in (0, 1]")
        _require_finite("defaultEdgeMultiplier", self.default_edge_multiplier)
        if self.default_edge_multiplier < 0:
            raise SimulationInputError("defaultEdgeMultiplier must be non-negative")
        for node_id, shift in self.node_shifts.items():
            if not (-1.0 <= shift <= 1.0):
                raise SimulationInputError(
                    f"scenario nodeShift for {node_id} must be a normalized delta in [-1, 1]"
                )
        for edge_id, multiplier in self.edge_multipliers.items():
            _require_finite(f"scenario edgeMultiplier for {edge_id}", multiplier)
            if multiplier < 0:
                raise SimulationInputError(
                    f"scenario edgeMultiplier for {edge_id} must be non-negative"
                )


@dataclass(frozen=True, slots=True)
class OptionOutcomeMapping:
    option_id: str
    outcome_node_id: str
    goal_id: str
    goal_weight: float

    def __post_init__(self) -> None:
        _require_finite(f"option {self.option_id} goalWeight", self.goal_weight)


@dataclass(frozen=True, slots=True)
class RiskWeight:
    option_id: str
    risk_node_id: str
    weight: float

    def __post_init__(self) -> None:
        _require_finite(f"option {self.option_id} riskWeight", self.weight)


@dataclass(frozen=True, slots=True)
class ConstraintRule:
    id: str
    option_id: str
    constraint_node_id: str
    comparison: Comparison
    threshold: float
    penalty: float

    def __post_init__(self) -> None:
        _require_finite(f"constraint {self.id}", self.threshold, self.penalty)
        if self.penalty < 0:
            raise SimulationInputError(f"constraint {self.id}: penalty must be non-negative")


@dataclass(frozen=True, slots=True)
class ScoreDefinition:
    id: str
    version: str
    option_ids: tuple[str, ...]
    option_outcomes: tuple[OptionOutcomeMapping, ...]
    risk_weights: tuple[RiskWeight, ...] = ()
    constraint_rules: tuple[ConstraintRule, ...] = ()

    def __post_init__(self) -> None:
        if not self.option_ids:
            raise SimulationInputError("score definition requires at least one option")
        if len(self.option_ids) != len(set(self.option_ids)):
            raise SimulationInputError("score definition has duplicate option ids")


# --- Result value objects ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OptionScore:
    option_id: str
    score: float


@dataclass(frozen=True, slots=True)
class TopDriver:
    node_id: str
    score_delta: float


@dataclass(frozen=True, slots=True)
class FlipCondition:
    node_id: str
    threshold: float
    from_option: str
    to_option: str


@dataclass(frozen=True, slots=True)
class SimulationResult:
    mode: SimulationMode
    steps: int
    convergence_status: SimulationConvergenceStatus
    stability_bound: float
    node_results: dict[str, float]
    node_business_values: dict[str, float]
    option_scores: tuple[OptionScore, ...]
    recommended_option_id: str | None
    top_drivers: tuple[TopDriver, ...]
    recommendation_shift: str
    input_hash: str
    engine_version: str

    def score_for(self, option_id: str) -> float:
        for entry in self.option_scores:
            if entry.option_id == option_id:
                return entry.score
        raise KeyError(option_id)
