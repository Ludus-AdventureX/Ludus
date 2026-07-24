"""Deterministic, pure causal simulation engine.

This module is intentionally free of I/O, database, and framework imports. Given identical
inputs (graph content, strategy, scenario, score definition, risk tolerance, engine version,
epsilon, maxSteps, node overrides and mode) it MUST produce byte-identical results and an
identical ``inputHash``. The propagation math follows ``docs/product-plan/09-simulation-
engine.md`` exactly: effect = ``delta * polarity * strength * edgeMultiplier * damping`` and
``relationshipQualityScore`` never enters the numeric effect.
"""

from __future__ import annotations

import hashlib
import json
import math

from app.types import NodeType, SimulationConvergenceStatus, SimulationMode

from .domain import (
    CausalEdge,
    CausalNode,
    Comparison,
    ConstraintRule,
    EdgePolarity,
    ElementStatus,
    GraphVersion,
    GraphVersionStatus,
    Normalization,
    OptionScore,
    ProfileFingerprint,
    ScenarioVersion,
    ScoreDefinition,
    SimulationAuthorizationError,
    SimulationInputError,
    SimulationResult,
    StrategyVersion,
)

# CCR-20260724-ENG-02: minor bump — the replay-identity contract gains the frozen
# profile block below; numeric propagation/scoring/convergence are UNCHANGED.
ENGINE_VERSION = "sim-engine-1.1.0"

_STRATEGY_NODE_TYPES = frozenset({NodeType.DECISION, NodeType.LEVER})
_TIE_EPSILON = 1e-9

# Edges eligible for propagation per simulation mode. Rejected edges are always excluded.
_FORMAL_EDGE_STATUSES = frozenset({ElementStatus.CONFIRMED, ElementStatus.CONDITIONAL})
_EXPERIMENTAL_EDGE_STATUSES = frozenset(
    {ElementStatus.DRAFT, ElementStatus.CONFIRMED, ElementStatus.CONDITIONAL}
)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def normalize(node: CausalNode, value: float) -> float:
    """Map a business-unit value to the engine's internal ``[0, 1]`` space."""

    bounded = clamp(value, node.min, node.max)
    span = node.max - node.min
    if node.normalization == Normalization.INVERSE_LINEAR:
        return (node.max - bounded) / span
    return (bounded - node.min) / span


def denormalize(node: CausalNode, normalized: float) -> float:
    """Map an internal ``[0, 1]`` value back to the node's business unit."""

    span = node.max - node.min
    if node.normalization == Normalization.INVERSE_LINEAR:
        return node.max - normalized * span
    return node.min + normalized * span


def eligible_edges(graph: GraphVersion, mode: SimulationMode) -> tuple[CausalEdge, ...]:
    statuses = _FORMAL_EDGE_STATUSES if mode == SimulationMode.FORMAL else _EXPERIMENTAL_EDGE_STATUSES
    return tuple(edge for edge in graph.edges if edge.status in statuses)


def stability_bound(graph: GraphVersion, scenario: ScenarioVersion, mode: SimulationMode) -> float:
    """Sufficient-convergence bound ``L = lambda * max_j sum_i(strength_ij * |multiplier_ij|)``."""

    incoming: dict[str, float] = {}
    for edge in eligible_edges(graph, mode):
        multiplier = scenario.edge_multipliers.get(edge.id, scenario.default_edge_multiplier)
        incoming[edge.target_node_id] = incoming.get(edge.target_node_id, 0.0) + edge.strength * abs(
            multiplier
        )
    peak = max(incoming.values(), default=0.0)
    return scenario.damping * peak


def assert_authorization(graph: GraphVersion, mode: SimulationMode) -> None:
    """Formal runs require a confirmed graph whose propagating nodes are all confirmed."""

    if mode != SimulationMode.FORMAL:
        return
    if graph.status != GraphVersionStatus.CONFIRMED:
        raise SimulationAuthorizationError("formal simulation requires a confirmed graph version")
    propagating: set[str] = set()
    for edge in eligible_edges(graph, mode):
        propagating.add(edge.source_node_id)
        propagating.add(edge.target_node_id)
    for node in graph.nodes:
        if node.id in propagating and node.status != ElementStatus.CONFIRMED:
            raise SimulationAuthorizationError(
                f"formal simulation requires confirmed propagating node {node.id}"
            )


def assert_inputs_belong_together(
    graph: GraphVersion,
    strategy: StrategyVersion,
    scenario: ScenarioVersion,
    score_definition: ScoreDefinition,
) -> None:
    """Referential integrity: every strategy/scenario/score reference must exist in graph."""

    node_ids = {node.id for node in graph.nodes}
    node_types = {node.id: node.type for node in graph.nodes}
    edge_ids = {edge.id for edge in graph.edges}

    for node_id in strategy.node_overrides:
        if node_id not in node_ids:
            raise SimulationInputError(f"strategy overrides unknown node {node_id}")
        if node_types[node_id] not in _STRATEGY_NODE_TYPES:
            raise SimulationInputError(
                f"strategy may only override decision/lever nodes, not {node_id}"
            )
    for node_id in scenario.node_shifts:
        if node_id not in node_ids:
            raise SimulationInputError(f"scenario shifts unknown node {node_id}")
    for edge_id in scenario.edge_multipliers:
        if edge_id not in edge_ids:
            raise SimulationInputError(f"scenario multiplies unknown edge {edge_id}")
    for mapping in score_definition.option_outcomes:
        if mapping.outcome_node_id not in node_ids:
            raise SimulationInputError(f"score references unknown outcome node {mapping.outcome_node_id}")
        if mapping.option_id not in score_definition.option_ids:
            raise SimulationInputError(f"score outcome references unknown option {mapping.option_id}")
    for risk in score_definition.risk_weights:
        if risk.risk_node_id not in node_ids:
            raise SimulationInputError(f"score references unknown risk node {risk.risk_node_id}")
    for rule in score_definition.constraint_rules:
        if rule.constraint_node_id not in node_ids:
            raise SimulationInputError(
                f"constraint references unknown node {rule.constraint_node_id}"
            )


def build_interventions(
    graph: GraphVersion, strategy: StrategyVersion, node_overrides: dict[str, float]
) -> dict[str, float]:
    """Merge strategy (decision/lever) and explicit user overrides into held interventions.

    Explicit user overrides win over the strategy for the same node. Values are clamped into
    the node's business range so their normalized form stays in ``[0, 1]``.
    """

    merged: dict[str, float] = {}
    for node_id, value in strategy.node_overrides.items():
        node = graph.node(node_id)
        merged[node_id] = clamp(value, node.min, node.max)
    for node_id, value in node_overrides.items():
        node = graph.node(node_id)
        merged[node_id] = clamp(value, node.min, node.max)
    return merged


def _constraint_triggered(rule: ConstraintRule, normalized_state: dict[str, float]) -> bool:
    value = normalized_state[rule.constraint_node_id]
    if rule.comparison == Comparison.GREATER_THAN:
        return value > rule.threshold
    if rule.comparison == Comparison.GREATER_OR_EQUAL:
        return value >= rule.threshold
    if rule.comparison == Comparison.LESS_THAN:
        return value < rule.threshold
    return value <= rule.threshold


def score_options(
    score_definition: ScoreDefinition,
    normalized_state: dict[str, float],
    risk_tolerance: float,
) -> tuple[OptionScore, ...]:
    """Score every option from the explicit versioned ScoreDefinition.

    ``option_score = sum(goal_weight * outcome_value) - risk_tolerance * sum(risk_weight *
    risk_value) - constraint_penalty``. Scoring never guesses meaning from node labels.
    """

    scores: list[OptionScore] = []
    for option_id in score_definition.option_ids:
        benefit = sum(
            mapping.goal_weight * normalized_state[mapping.outcome_node_id]
            for mapping in score_definition.option_outcomes
            if mapping.option_id == option_id
        )
        risk = risk_tolerance * sum(
            weight.weight * normalized_state[weight.risk_node_id]
            for weight in score_definition.risk_weights
            if weight.option_id == option_id
        )
        penalty = sum(
            rule.penalty
            for rule in score_definition.constraint_rules
            if rule.option_id == option_id and _constraint_triggered(rule, normalized_state)
        )
        scores.append(OptionScore(option_id=option_id, score=benefit - risk - penalty))
    return tuple(scores)


def recommend_option(
    option_scores: tuple[OptionScore, ...], convergence_status: SimulationConvergenceStatus
) -> str | None:
    """Pick the top option, or abstain (None) for non-converged runs or unbroken ties."""

    if convergence_status != SimulationConvergenceStatus.CONVERGED:
        return None
    if not option_scores:
        return None
    best = max(entry.score for entry in option_scores)
    winners = sorted(
        entry.option_id for entry in option_scores if abs(entry.score - best) <= _TIE_EPSILON
    )
    return winners[0] if len(winners) == 1 else None


def _round_floats(value: float) -> float:
    # Guard against -0.0 and platform noise leaking into the hash payload.
    return round(value + 0.0, 12)


def _graph_fingerprint(graph: GraphVersion) -> dict:
    return {
        "id": graph.id,
        "graphId": graph.graph_id,
        "status": graph.status.value,
        "nodes": [
            {
                "id": node.id,
                "type": node.type.value,
                "baseline": _round_floats(node.baseline),
                "min": _round_floats(node.min),
                "max": _round_floats(node.max),
                "normalization": node.normalization.value,
                "status": node.status.value,
            }
            for node in sorted(graph.nodes, key=lambda item: item.id)
        ],
        "edges": [
            {
                "id": edge.id,
                "source": edge.source_node_id,
                "target": edge.target_node_id,
                "polarity": edge.polarity.value,
                "strength": _round_floats(edge.strength),
                "delaySteps": edge.delay_steps,
                "status": edge.status.value,
            }
            for edge in sorted(graph.edges, key=lambda item: item.id)
        ],
    }


def _scenario_fingerprint(scenario: ScenarioVersion) -> dict:
    return {
        "id": scenario.id,
        "version": scenario.version,
        "sourceLensArtifactId": scenario.source_lens_artifact_id,
        "sourceStrategicScenarioId": scenario.source_strategic_scenario_id,
        "strategySurvives": scenario.strategy_survives,
        "defaultEdgeMultiplier": _round_floats(scenario.default_edge_multiplier),
        "edgeMultipliers": {k: _round_floats(v) for k, v in sorted(scenario.edge_multipliers.items())},
        "nodeShifts": {k: _round_floats(v) for k, v in sorted(scenario.node_shifts.items())},
        "damping": _round_floats(scenario.damping),
    }


def _score_fingerprint(score_definition: ScoreDefinition) -> dict:
    return {
        "id": score_definition.id,
        "version": score_definition.version,
        "optionIds": list(score_definition.option_ids),
        "optionOutcomes": [
            {
                "optionId": mapping.option_id,
                "outcomeNodeId": mapping.outcome_node_id,
                "goalId": mapping.goal_id,
                "goalWeight": _round_floats(mapping.goal_weight),
            }
            for mapping in score_definition.option_outcomes
        ],
        "riskWeights": [
            {"optionId": w.option_id, "riskNodeId": w.risk_node_id, "weight": _round_floats(w.weight)}
            for w in score_definition.risk_weights
        ],
        "constraintRules": [
            {
                "id": rule.id,
                "optionId": rule.option_id,
                "constraintNodeId": rule.constraint_node_id,
                "comparison": rule.comparison.value,
                "threshold": _round_floats(rule.threshold),
                "penalty": _round_floats(rule.penalty),
            }
            for rule in score_definition.constraint_rules
        ],
    }


def compute_input_hash(
    graph: GraphVersion,
    strategy: StrategyVersion,
    scenario: ScenarioVersion,
    score_definition: ScoreDefinition,
    risk_tolerance: float,
    mode: SimulationMode,
    node_overrides: dict[str, float],
    epsilon: float,
    max_steps: int,
    *,
    profile: ProfileFingerprint | None = None,
) -> str:
    """SHA-256 over the canonical JSON of every frozen input; replay-exact only.

    CCR-ENG-02: when a verified :class:`ProfileFingerprint` is supplied (the service
    ALWAYS supplies it for every persisted run), the payload gains exactly one nested
    top-level ``profile`` object; ``riskTolerance`` stays a separate top-level key
    with unchanged Task 12 semantics. Bare dicts are rejected: the fingerprint must
    be the assembly-verified value object, never caller-constructed data.
    """

    if profile is not None and not isinstance(profile, ProfileFingerprint):
        raise SimulationInputError(
            "profile must be the assembly-verified ProfileFingerprint value object"
        )

    payload = {
        "engineVersion": ENGINE_VERSION,
        "mode": mode.value,
        "epsilon": _round_floats(epsilon),
        "maxSteps": max_steps,
        "riskTolerance": _round_floats(risk_tolerance),
        "graph": _graph_fingerprint(graph),
        "strategy": {
            "id": strategy.id,
            "version": strategy.version,
            "nodeOverrides": {
                k: _round_floats(v) for k, v in sorted(strategy.node_overrides.items())
            },
        },
        "scenario": _scenario_fingerprint(scenario),
        "scoreDefinition": _score_fingerprint(score_definition),
        "nodeOverrides": {k: _round_floats(v) for k, v in sorted(node_overrides.items())},
    }
    if profile is not None:
        payload["profile"] = {
            "id": profile.id,
            "version": profile.version,
            "contentHash": profile.content_hash,
        }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def run_simulation(
    graph: GraphVersion,
    strategy: StrategyVersion,
    scenario: ScenarioVersion,
    score_definition: ScoreDefinition,
    risk_tolerance: float,
    mode: SimulationMode,
    node_overrides: dict[str, float] | None = None,
    epsilon: float = 0.001,
    max_steps: int = 12,
    *,
    profile: ProfileFingerprint | None = None,
) -> SimulationResult:
    """Run the deterministic propagation and produce an immutable :class:`SimulationResult`."""

    if epsilon <= 0:
        raise SimulationInputError("epsilon must be positive")
    if max_steps <= 0:
        raise SimulationInputError("maxSteps must be positive")
    if not (0.0 <= risk_tolerance <= 1.0):
        raise SimulationInputError("riskTolerance must be in [0, 1]")

    overrides = dict(node_overrides or {})
    assert_authorization(graph, mode)
    assert_inputs_belong_together(graph, strategy, scenario, score_definition)

    interventions = build_interventions(graph, strategy, overrides)
    edges = eligible_edges(graph, mode)
    nodes_by_id = {node.id: node for node in graph.nodes}
    max_delay = max((edge.delay_steps for edge in edges), default=0)

    input_hash = compute_input_hash(
        graph, strategy, scenario, score_definition, risk_tolerance, mode, overrides, epsilon, max_steps,
        profile=profile,
    )

    # t = 0 initialization.
    state: dict[int, dict[str, float]] = {0: {}}
    for node in graph.nodes:
        if node.id in interventions:
            state[0][node.id] = normalize(node, interventions[node.id])
        else:
            state[0][node.id] = clamp(
                normalize(node, node.baseline) + scenario.node_shifts.get(node.id, 0.0), 0.0, 1.0
            )

    delayed: dict[int, dict[str, float]] = {}
    clamp_active: dict[int, bool] = {}
    stable_rounds = 0
    completed_steps = 0
    convergence = SimulationConvergenceStatus.MAX_STEPS
    invalid = False

    for t in range(max_steps):
        for edge in edges:
            source_value = state[t][edge.source_node_id]
            source_node = nodes_by_id[edge.source_node_id]
            delta = source_value - normalize(source_node, source_node.baseline)
            polarity = 1.0 if edge.polarity == EdgePolarity.POSITIVE else -1.0
            multiplier = scenario.edge_multipliers.get(edge.id, scenario.default_edge_multiplier)
            impact = delta * polarity * edge.strength * multiplier * scenario.damping
            bucket = delayed.setdefault(t + edge.delay_steps + 1, {})
            bucket[edge.target_node_id] = bucket.get(edge.target_node_id, 0.0) + impact

        due = delayed.get(t + 1, {})
        state[t + 1] = {}
        max_abs_change = 0.0
        round_clamped = False
        for node in graph.nodes:
            if node.id in interventions:
                raw = normalize(node, interventions[node.id])
            else:
                raw = (
                    normalize(node, node.baseline)
                    + scenario.node_shifts.get(node.id, 0.0)
                    + due.get(node.id, 0.0)
                )
            if not math.isfinite(raw):
                invalid = True
                break
            next_value = clamp(raw, 0.0, 1.0)
            if node.id not in interventions and (raw < 0.0 or raw > 1.0):
                round_clamped = True
            max_abs_change = max(max_abs_change, abs(next_value - state[t][node.id]))
            state[t + 1][node.id] = next_value

        if invalid:
            convergence = SimulationConvergenceStatus.INVALID
            break

        completed_steps = t + 1
        clamp_active[completed_steps] = round_clamped
        stable_rounds = stable_rounds + 1 if max_abs_change < epsilon else 0
        if stable_rounds >= max_delay + 1:
            window = range(max(1, completed_steps - max_delay), completed_steps + 1)
            saturated = any(clamp_active.get(step, False) for step in window)
            convergence = (
                SimulationConvergenceStatus.SATURATED
                if saturated
                else SimulationConvergenceStatus.CONVERGED
            )
            break

    final_state = state[completed_steps]
    option_scores = score_options(score_definition, final_state, risk_tolerance)
    recommended = recommend_option(option_scores, convergence)
    node_business = {
        node.id: denormalize(node, final_state[node.id]) for node in graph.nodes
    }

    return SimulationResult(
        mode=mode,
        steps=completed_steps,
        convergence_status=convergence,
        stability_bound=stability_bound(graph, scenario, mode),
        node_results=dict(final_state),
        node_business_values=node_business,
        option_scores=option_scores,
        recommended_option_id=recommended,
        top_drivers=(),
        recommendation_shift="",
        input_hash=input_hash,
        engine_version=ENGINE_VERSION,
    )
