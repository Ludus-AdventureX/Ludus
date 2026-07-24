"""Deterministic ORM -> Task 12 domain assembly.

The pure engine stays free of ORM/session imports; this module is the single boundary that
turns tenant-scoped rows into the frozen, immutable Task 12 domain value objects. Assembly
is deterministic: nodes/edges are totally ordered by their unique primary key (this baseline
has no node_key/edge_key column), JSONB payloads are defensively copied, and map keys are
normalized to sorted insertion order, so repeated assembly of the same frozen input is
byte-for-byte equivalent.

JSONB shapes (score definition rules, early-warning signals) are validated item-by-item
through the canonical wire schemas from ``app.simulations.schemas`` — consumed, never
redefined — before they are translated into engine domain objects.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from pydantic import ValidationError

from app.models import (
    DecisionCase,
    GraphEdge,
    GraphNode,
    GraphVersion as GraphVersionRow,
    ScenarioVersion as ScenarioVersionRow,
    ScoreDefinition as ScoreDefinitionRow,
    StrategyVersion as StrategyVersionRow,
)
from app.simulations.schemas import (
    ConstraintRule as ConstraintRuleWire,
    OptionOutcomeMapping as OptionOutcomeMappingWire,
    RiskWeight as RiskWeightWire,
    ScenarioEarlyWarningSignal as EarlyWarningSignalWire,
)
from app.types import NodeType

from .domain import (
    CausalEdge,
    CausalNode,
    Comparison,
    ConstraintRule,
    EarlyWarningSignal,
    ElementStatus,
    GraphVersion,
    Normalization,
    OptionOutcomeMapping,
    RiskWeight,
    ScenarioVersion,
    ScoreDefinition,
    StrategyVersion,
)
from .errors import (
    ScenarioParameterError,
    ScoreDefinitionReferenceError,
    StrategyOverrideError,
)

_STRATEGY_OVERRIDABLE_TYPES = frozenset({NodeType.DECISION, NodeType.LEVER})


@dataclass(frozen=True, slots=True)
class AssembledSimulationInput:
    """One frozen, validated engine input set (immutable domain objects only)."""

    graph: GraphVersion
    strategy: StrategyVersion
    scenario: ScenarioVersion
    score_definition: ScoreDefinition


def _sorted_copy(values: dict[str, float]) -> dict[str, float]:
    """Defensive copy with normalized (sorted) key insertion order."""

    return {key: float(values[key]) for key in sorted(values)}


def assemble_node(row: GraphNode) -> CausalNode:
    return CausalNode(
        id=str(row.id),
        label=row.label,
        type=NodeType(row.node_type),
        baseline=float(row.baseline_value),
        min=float(row.min_value),
        max=float(row.max_value),
        unit=row.unit or "",
        normalization=Normalization(row.normalization),
        sensitivity_step=(
            float(row.sensitivity_step) if row.sensitivity_step is not None else None
        ),
        controllability=row.controllability,
        authorship=row.authorship.value,
        evidence_status=row.evidence_status,
        evidence_quality_score=float(row.evidence_quality_score),
        evidence_ids=tuple(row.evidence_ids),
        assumption_ids=tuple(row.assumption_ids),
        rationale=row.rationale,
        status=ElementStatus(row.review_status),
        editable=bool(row.editable),
    )


def assemble_edge(row: GraphEdge) -> CausalEdge:
    return CausalEdge(
        id=str(row.id),
        source_node_id=str(row.source_node_id),
        target_node_id=str(row.target_node_id),
        polarity=row.polarity,
        strength=float(row.strength),
        delay_steps=int(row.delay_steps),
        relationship_quality_score=float(row.relationship_quality_score),
        claim_ids=tuple(row.claim_ids),
        evidence_ids=tuple(row.evidence_ids),
        assumption_ids=tuple(row.assumption_ids),
        status=ElementStatus(row.review_status),
    )


def assemble_graph(
    version_row: GraphVersionRow,
    node_rows: list[GraphNode],
    edge_rows: list[GraphEdge],
) -> GraphVersion:
    """Deterministic graph assembly; never trusts database row order."""

    ordered_nodes = sorted(node_rows, key=lambda row: str(row.id))
    ordered_edges = sorted(edge_rows, key=lambda row: str(row.id))
    return GraphVersion(
        id=str(version_row.id),
        graph_id=str(version_row.graph_id),
        status=version_row.status,
        nodes=tuple(assemble_node(row) for row in ordered_nodes),
        edges=tuple(assemble_edge(row) for row in ordered_edges),
    )


def assemble_strategy(row: StrategyVersionRow, graph: GraphVersion) -> StrategyVersion:
    """Validate and freeze strategy overrides against the exact graph version."""

    if row.enabled_edge_ids:
        # CONTRACT_DEPENDENCY: enabled_edge_ids exists on the canonical contract but
        # sim-engine-1.0.0 has no edge-gating semantics; silently ignoring it would
        # change results relative to the persisted intent, so it fails fast.
        raise StrategyOverrideError(
            "strategy enabledEdgeIds are not executable by sim-engine-1.0.0",
            code="strategy_edge_gating_unsupported",
        )

    nodes_by_id = {node.id: node for node in graph.nodes}
    overrides: dict[str, float] = {}
    for node_id in sorted(dict(row.node_overrides)):
        raw_value = row.node_overrides[node_id]
        node = nodes_by_id.get(node_id)
        if node is None:
            raise StrategyOverrideError(
                f"strategy override references unknown node {node_id}"
            )
        if node.type not in _STRATEGY_OVERRIDABLE_TYPES:
            raise StrategyOverrideError(
                f"strategy may only override decision/lever nodes, not {node_id} ({node.type})"
            )
        value = float(raw_value)
        if not math.isfinite(value):
            raise StrategyOverrideError(
                f"strategy override for {node_id} must be a finite business value"
            )
        if not (node.min <= value <= node.max):
            raise StrategyOverrideError(
                f"strategy override for {node_id} must lie within [{node.min}, {node.max}]"
            )
        overrides[node_id] = value

    return StrategyVersion(id=str(row.id), version=row.version, node_overrides=overrides)


def _assemble_early_warning_signals(
    payload: list[dict],
) -> tuple[EarlyWarningSignal, ...]:
    signals: list[EarlyWarningSignal] = []
    for index, item in enumerate(payload):
        try:
            wire = EarlyWarningSignalWire.model_validate(dict(item))
        except ValidationError as exc:
            raise ScenarioParameterError(
                f"scenario earlyWarningSignals[{index}] is not canonical: {exc.errors()[0]['msg']}"
            ) from exc
        signals.append(
            EarlyWarningSignal(
                signal_id=wire.signal_id,
                type=wire.type,
                observable=wire.observable,
                threshold_or_pattern=wire.threshold_or_pattern,
                cadence=wire.cadence,
            )
        )
    return tuple(signals)


def assemble_scenario(row: ScenarioVersionRow, graph: GraphVersion) -> ScenarioVersion:
    """Validate and freeze scenario shifts/multipliers against the exact graph version."""

    node_ids = {node.id for node in graph.nodes}
    edge_ids = {edge.id for edge in graph.edges}

    node_shifts: dict[str, float] = {}
    for node_id in sorted(dict(row.node_shifts)):
        if node_id not in node_ids:
            raise ScenarioParameterError(f"scenario shifts unknown node {node_id}")
        value = float(row.node_shifts[node_id])
        if not math.isfinite(value) or not (-1.0 <= value <= 1.0):
            raise ScenarioParameterError(
                f"scenario nodeShift for {node_id} must be a normalized delta in [-1, 1]"
            )
        node_shifts[node_id] = value

    edge_multipliers: dict[str, float] = {}
    for edge_id in sorted(dict(row.edge_multipliers)):
        if edge_id not in edge_ids:
            raise ScenarioParameterError(f"scenario multiplies unknown edge {edge_id}")
        value = float(row.edge_multipliers[edge_id])
        if not math.isfinite(value) or value < 0:
            raise ScenarioParameterError(
                f"scenario edgeMultiplier for {edge_id} must be finite and non-negative"
            )
        edge_multipliers[edge_id] = value

    return ScenarioVersion(
        id=str(row.id),
        version=row.version,
        source_lens_artifact_id=str(row.source_lens_artifact_id),
        source_strategic_scenario_id=row.source_strategic_scenario_id,
        strategy_survives=bool(row.strategy_survives),
        early_warning_signals=_assemble_early_warning_signals(list(row.early_warning_signals)),
        default_edge_multiplier=float(row.default_edge_multiplier),
        edge_multipliers=edge_multipliers,
        node_shifts=node_shifts,
        damping=float(row.damping),
    )


def assemble_score_definition(
    row: ScoreDefinitionRow,
    graph: GraphVersion,
    case: DecisionCase,
) -> ScoreDefinition:
    """Validate every JSONB reference item-by-item; never wait for engine luck."""

    if not row.content_hash:
        raise ScoreDefinitionReferenceError("score definition is missing contentHash")

    node_ids = {node.id for node in graph.nodes}
    frozen_option_ids = {str(option_id) for option_id in case.option_ids}

    def require_option(option_id: str, where: str) -> None:
        if option_id not in frozen_option_ids:
            raise ScoreDefinitionReferenceError(
                f"{where} references option {option_id} outside the frozen case option set"
            )

    def require_node(node_id: str, where: str) -> None:
        if node_id not in node_ids:
            raise ScoreDefinitionReferenceError(
                f"{where} references node {node_id} missing from the graph version"
            )

    outcomes: list[OptionOutcomeMapping] = []
    for index, item in enumerate(list(row.option_outcome_mappings)):
        try:
            wire = OptionOutcomeMappingWire.model_validate(dict(item))
        except ValidationError as exc:
            raise ScoreDefinitionReferenceError(
                f"optionOutcomeMappings[{index}] is not canonical: {exc.errors()[0]['msg']}"
            ) from exc
        require_option(wire.option_id, f"optionOutcomeMappings[{index}]")
        require_node(wire.outcome_node_id, f"optionOutcomeMappings[{index}]")
        outcomes.append(
            OptionOutcomeMapping(
                option_id=wire.option_id,
                outcome_node_id=wire.outcome_node_id,
                goal_id=wire.goal_id,
                goal_weight=float(wire.weight),
            )
        )

    risks: list[RiskWeight] = []
    for index, item in enumerate(list(row.risk_weights)):
        try:
            wire = RiskWeightWire.model_validate(dict(item))
        except ValidationError as exc:
            raise ScoreDefinitionReferenceError(
                f"riskWeights[{index}] is not canonical: {exc.errors()[0]['msg']}"
            ) from exc
        require_option(wire.option_id, f"riskWeights[{index}]")
        require_node(wire.risk_node_id, f"riskWeights[{index}]")
        risks.append(
            RiskWeight(
                option_id=wire.option_id,
                risk_node_id=wire.risk_node_id,
                weight=float(wire.weight),
            )
        )

    rules: list[ConstraintRule] = []
    for index, item in enumerate(list(row.constraint_rules)):
        try:
            wire = ConstraintRuleWire.model_validate(dict(item))
        except ValidationError as exc:
            raise ScoreDefinitionReferenceError(
                f"constraintRules[{index}] is not canonical: {exc.errors()[0]['msg']}"
            ) from exc
        require_option(wire.option_id, f"constraintRules[{index}]")
        require_node(wire.constraint_node_id, f"constraintRules[{index}]")
        # CONTRACT_DEPENDENCY: canonical ConstraintComparison includes EQ "="; the
        # engine's comparison fall-through would silently treat "=" as "<=", so
        # equality rules are rejected until the engine contract covers them.
        if wire.operator.value not in {member.value for member in Comparison}:
            raise ScoreDefinitionReferenceError(
                f"constraintRules[{index}] operator {wire.operator.value!r} is not "
                "executable by sim-engine-1.0.0",
                code="score_constraint_operator_unsupported",
            )
        rules.append(
            ConstraintRule(
                id=f"rule_{index}",
                option_id=wire.option_id,
                constraint_node_id=wire.constraint_node_id,
                comparison=Comparison(wire.operator.value),
                threshold=float(wire.threshold),
                penalty=float(wire.penalty),
            )
        )

    scored_options = sorted(
        {mapping.option_id for mapping in outcomes}
        | {risk.option_id for risk in risks}
        | {rule.option_id for rule in rules}
    )
    if not scored_options:
        raise ScoreDefinitionReferenceError(
            "score definition does not reference any frozen case option"
        )

    return ScoreDefinition(
        id=str(row.id),
        version=row.version,
        option_ids=tuple(scored_options),
        option_outcomes=tuple(outcomes),
        risk_weights=tuple(risks),
        constraint_rules=tuple(rules),
    )
