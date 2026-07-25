"""Automated verification for the deterministic causal simulation engine.

Run (reusing the already-installed main-worktree venv, no new environment):

    E:\\Temp\\xiayu\\Documents\\adventure-x\\decision-lab\\.venv\\Scripts\\python.exe -m pytest \\
        services/api/app/simulations/tests -q

These tests live under the Simulation owner scope (services/api/app/simulations/**) so they
do not touch the QA-owned services/api/tests/** tree. They assert the graph structure
invariants, determinism/reproducibility, boundary conditions and the spherical-robot
recommendation flip required by the freeze contract.
"""

from __future__ import annotations

import dataclasses
from unittest.mock import patch

import pytest

from app.simulations import engine as engine_mod
from app.simulations import graph_builder as gb
from app.simulations.domain import (
    CausalEdge,
    CausalNode,
    Controllability,
    EdgePolarity,
    ElementStatus,
    EvidenceStatus,
    GraphInvariantError,
    GraphVersion,
    GraphVersionStatus,
    Normalization,
    OptionOutcomeMapping,
    ProfileFingerprint,
    ScenarioVersion,
    ScoreDefinition,
    SimulationAuthorizationError,
    SimulationError,
    SimulationInputError,
    StrategyVersion,
)
from app.simulations.engine import (
    ENGINE_VERSION,
    compute_input_hash,
    denormalize,
    eligible_edges,
    normalize,
    run_simulation,
    stability_bound,
)
from app.simulations.sensitivity import analyze_sensitivity
from app.types import NodeType, SimulationConvergenceStatus, SimulationMode

FORMAL = SimulationMode.FORMAL
EXPERIMENTAL = SimulationMode.EXPERIMENTAL

# CCR-ENG-02 profile enforcement: sim-engine-1.1.0 requires a verified fingerprint
# on EVERY engine call. This fixed, deterministic canonical fingerprint keeps the
# numeric suite byte-stable while satisfying the mandatory profile block.
OWNER_FP = ProfileFingerprint(
    id="00000000-0000-4000-8000-000000000001",
    version=1,
    content_hash="sha256:" + "0" * 64,
)


# --- tiny graph builders for isolated behaviors ------------------------------------------


def _node(
    node_id: str,
    node_type: NodeType,
    baseline: float,
    *,
    minimum: float = 0.0,
    maximum: float = 1.0,
    normalization: Normalization = Normalization.LINEAR,
    status: ElementStatus = ElementStatus.CONFIRMED,
    editable: bool = False,
    sensitivity_step: float | None = None,
) -> CausalNode:
    return CausalNode(
        id=node_id,
        label=node_id,
        type=node_type,
        baseline=baseline,
        min=minimum,
        max=maximum,
        unit="u",
        normalization=normalization,
        sensitivity_step=sensitivity_step,
        controllability=Controllability.CONTROLLABLE if editable else Controllability.UNCONTROLLABLE,
        evidence_status=EvidenceStatus.CONDITIONAL,
        evidence_ids=("ev",),
        status=status,
        editable=editable,
    )


def _edge(
    edge_id: str,
    source: str,
    target: str,
    polarity: EdgePolarity,
    strength: float,
    *,
    delay: int = 0,
    status: ElementStatus = ElementStatus.CONFIRMED,
    claim_ids: tuple[str, ...] = ("c",),
    assumption_ids: tuple[str, ...] = (),
) -> CausalEdge:
    return CausalEdge(
        id=edge_id,
        source_node_id=source,
        target_node_id=target,
        polarity=polarity,
        strength=strength,
        delay_steps=delay,
        relationship_quality_score=0.5,
        claim_ids=claim_ids,
        evidence_ids=("ev",) if claim_ids else (),
        assumption_ids=assumption_ids,
        status=status,
    )


def _graph(nodes, edges, status: GraphVersionStatus = GraphVersionStatus.CONFIRMED) -> GraphVersion:
    return GraphVersion(id="gv", graph_id="g", status=status, nodes=tuple(nodes), edges=tuple(edges))


def _strategy(overrides: dict[str, float] | None = None) -> StrategyVersion:
    return StrategyVersion(id="st", version=1, node_overrides=overrides or {})


def _scenario(**kwargs) -> ScenarioVersion:
    payload = {
        "id": "sc",
        "version": 1,
        "source_lens_artifact_id": "lens",
        "source_strategic_scenario_id": "src",
        "strategy_survives": True,
    }
    payload.update(kwargs)
    return ScenarioVersion(**payload)


def _score_single(option: str, outcome_node: str) -> ScoreDefinition:
    return ScoreDefinition(
        id="sd",
        version="1",
        option_ids=(option,),
        option_outcomes=(OptionOutcomeMapping(option, outcome_node, "goal", 1.0),),
    )


# --- normalization -----------------------------------------------------------------------


def test_linear_and_inverse_linear_normalization_roundtrip():
    linear = _node("n", NodeType.EXTERNAL, 9.0, minimum=3.0, maximum=24.0)
    assert normalize(linear, 9.0) == pytest.approx((9.0 - 3.0) / 21.0)
    assert denormalize(linear, normalize(linear, 9.0)) == pytest.approx(9.0)

    inverse = _node(
        "n", NodeType.EXTERNAL, 9.0, minimum=3.0, maximum=24.0, normalization=Normalization.INVERSE_LINEAR
    )
    assert normalize(inverse, 9.0) == pytest.approx((24.0 - 9.0) / 21.0)
    assert denormalize(inverse, normalize(inverse, 14.0)) == pytest.approx(14.0)


def test_normalization_clamps_out_of_range_business_values():
    node = _node("n", NodeType.EXTERNAL, 9.0, minimum=3.0, maximum=24.0)
    assert normalize(node, -100.0) == 0.0
    assert normalize(node, 999.0) == 1.0


# --- positive / negative edges -----------------------------------------------------------


def test_positive_edge_raises_target_above_baseline():
    nodes = [
        _node("src", NodeType.EXTERNAL, 0.5, editable=True),
        _node("tgt", NodeType.OUTCOME, 0.5),
    ]
    graph = _graph(nodes, [_edge("e", "src", "tgt", EdgePolarity.POSITIVE, 0.8)])
    result = run_simulation(
        graph, _strategy(), _scenario(), _score_single("opt", "tgt"), 0.0, FORMAL,
        node_overrides={"src": 1.0}, profile=OWNER_FP,
    )
    assert result.node_results["tgt"] > 0.5


def test_negative_edge_lowers_target_below_baseline():
    nodes = [
        _node("src", NodeType.EXTERNAL, 0.5, editable=True),
        _node("tgt", NodeType.OUTCOME, 0.5),
    ]
    graph = _graph(nodes, [_edge("e", "src", "tgt", EdgePolarity.NEGATIVE, 0.8)])
    result = run_simulation(
        graph, _strategy(), _scenario(), _score_single("opt", "tgt"), 0.0, FORMAL,
        node_overrides={"src": 1.0}, profile=OWNER_FP,
    )
    assert result.node_results["tgt"] < 0.5


# --- delay -------------------------------------------------------------------------------


def test_delay_defers_impact_until_delay_steps_elapse():
    nodes = [
        _node("src", NodeType.EXTERNAL, 0.5, editable=True),
        _node("tgt", NodeType.OUTCOME, 0.5),
    ]
    graph = _graph(nodes, [_edge("e", "src", "tgt", EdgePolarity.POSITIVE, 0.8, delay=2)])
    score = _score_single("opt", "tgt")

    early = run_simulation(
        graph, _strategy(), _scenario(), score, 0.0, FORMAL, node_overrides={"src": 1.0}, max_steps=1,
        profile=OWNER_FP,
    )
    assert early.node_results["tgt"] == pytest.approx(0.5)

    settled = run_simulation(
        graph, _strategy(), _scenario(), score, 0.0, FORMAL, node_overrides={"src": 1.0}, max_steps=12,
        profile=OWNER_FP,
    )
    assert settled.node_results["tgt"] > 0.5


# --- clipping / bounds -------------------------------------------------------------------


def test_values_are_clamped_into_unit_interval():
    nodes = [
        _node("src", NodeType.EXTERNAL, 0.5, editable=True),
        _node("tgt", NodeType.OUTCOME, 0.9),
    ]
    graph = _graph(nodes, [_edge("e", "src", "tgt", EdgePolarity.POSITIVE, 1.0)])
    result = run_simulation(
        graph, _strategy(), _scenario(), _score_single("opt", "tgt"), 0.0, FORMAL,
        node_overrides={"src": 1.0}, profile=OWNER_FP,
    )
    assert result.node_results["tgt"] == 1.0
    assert all(0.0 <= value <= 1.0 for value in result.node_results.values())


# --- determinism / inputHash -------------------------------------------------------------


def test_identical_inputs_produce_identical_results_and_hash():
    first = gb.spherical_robot_fixture()
    second = gb.spherical_robot_fixture()
    run_first = run_simulation(
        first.graph, first.strategies[gb.RESCUE_PILOT], first.scenarios["agency_pull"],
        first.score_definition, first.risk_tolerance, FORMAL, profile=OWNER_FP,
    )
    run_second = run_simulation(
        second.graph, second.strategies[gb.RESCUE_PILOT], second.scenarios["agency_pull"],
        second.score_definition, second.risk_tolerance, FORMAL, profile=OWNER_FP,
    )
    assert run_first.node_results == run_second.node_results
    assert run_first.option_scores == run_second.option_scores
    assert run_first.convergence_status == run_second.convergence_status
    assert run_first.input_hash == run_second.input_hash
    assert run_first.engine_version == ENGINE_VERSION


def _hash_for(fixture, **overrides) -> str:
    kwargs = {
        "graph": fixture.graph,
        "strategy": fixture.strategies[gb.RESCUE_PILOT],
        "scenario": fixture.scenarios["agency_pull"],
        "score_definition": fixture.score_definition,
        "risk_tolerance": fixture.risk_tolerance,
        "mode": FORMAL,
        "node_overrides": {},
        "epsilon": 0.001,
        "max_steps": 12,
        "profile": OWNER_FP,
    }
    kwargs.update(overrides)
    return compute_input_hash(**kwargs)


def test_input_hash_reacts_to_every_frozen_input():
    fixture = gb.spherical_robot_fixture()
    base = _hash_for(fixture)

    assert _hash_for(fixture, epsilon=0.002) != base
    assert _hash_for(fixture, max_steps=24) != base
    assert _hash_for(fixture, risk_tolerance=0.9) != base
    assert _hash_for(fixture, mode=EXPERIMENTAL) != base
    assert _hash_for(fixture, node_overrides={"procurement_cycle_months": 14.0}) != base
    assert _hash_for(fixture, scenario=fixture.scenarios["procurement_delay"]) != base
    # Graph content hash must cover node values.
    assert _hash_for(fixture, graph=fixture.graph.with_value("procurement_cycle_months", 14.0)) != base


def test_graph_content_hash_covers_edge_topology():
    fixture = gb.spherical_robot_fixture()
    base = _hash_for(fixture)
    weaker_edges = tuple(
        dataclasses.replace(edge, strength=0.1) if edge.id == "edge_procurement_cash" else edge
        for edge in fixture.graph.edges
    )
    weaker_graph = GraphVersion(
        id=fixture.graph.id,
        graph_id=fixture.graph.graph_id,
        status=fixture.graph.status,
        nodes=fixture.graph.nodes,
        edges=weaker_edges,
    )
    assert _hash_for(fixture, graph=weaker_graph) != base


# --- convergence / non-convergence / saturation / invalid --------------------------------


def test_stable_graph_converges():
    fixture = gb.spherical_robot_fixture()
    result = run_simulation(
        fixture.graph, fixture.strategies[gb.RESCUE_PILOT], fixture.scenarios["agency_pull"],
        fixture.score_definition, fixture.risk_tolerance, FORMAL, profile=OWNER_FP,
    )
    assert result.convergence_status == SimulationConvergenceStatus.CONVERGED
    # This acyclic fixture converges even though its worst-target incoming sum makes the
    # sufficient bound L exceed 1; L < 1 is sufficient, not necessary, for convergence.
    assert result.stability_bound >= 0.0


def test_strong_feedback_loop_does_not_converge_cleanly():
    nodes = [
        _node("a", NodeType.INTERMEDIATE, 0.5),
        _node("b", NodeType.INTERMEDIATE, 0.5),
    ]
    edges = [
        _edge("ab", "a", "b", EdgePolarity.POSITIVE, 1.0),
        _edge("ba", "b", "a", EdgePolarity.POSITIVE, 1.0),
    ]
    graph = _graph(nodes, edges)
    scenario = _scenario(damping=1.0, node_shifts={"a": 0.3})
    result = run_simulation(
        graph, _strategy(), scenario, _score_single("opt", "b"), 0.0, FORMAL, profile=OWNER_FP
    )
    assert stability_bound(graph, scenario, FORMAL) >= 1.0
    assert result.convergence_status in {
        SimulationConvergenceStatus.SATURATED,
        SimulationConvergenceStatus.MAX_STEPS,
    }
    assert result.convergence_status != SimulationConvergenceStatus.CONVERGED
    assert result.recommended_option_id is None


def test_non_finite_propagation_is_reported_invalid_and_abstains():
    nodes = [
        _node("src", NodeType.EXTERNAL, 0.5, editable=True),
        _node("tgt", NodeType.OUTCOME, 0.5),
    ]
    graph = _graph(nodes, [_edge("e", "src", "tgt", EdgePolarity.POSITIVE, 0.8)])
    with patch.object(engine_mod, "normalize", return_value=float("nan")):
        result = run_simulation(
            graph, _strategy(), _scenario(), _score_single("opt", "tgt"), 0.0, FORMAL,
            profile=OWNER_FP,
        )
    assert result.convergence_status == SimulationConvergenceStatus.INVALID
    assert result.recommended_option_id is None


def test_non_finite_inputs_are_rejected_at_construction():
    with pytest.raises(SimulationError):
        _node("n", NodeType.EXTERNAL, float("nan"))
    with pytest.raises(SimulationError):
        _scenario(edge_multipliers={"e": float("inf")})


# --- hard constraints & spherical-robot flip ---------------------------------------------


def test_baseline_recommends_rescue_pilot():
    fixture = gb.spherical_robot_fixture()
    result = run_simulation(
        fixture.graph, fixture.strategies[gb.RESCUE_PILOT], fixture.scenarios["agency_pull"],
        fixture.score_definition, fixture.risk_tolerance, FORMAL, profile=OWNER_FP,
    )
    assert result.convergence_status == SimulationConvergenceStatus.CONVERGED
    assert result.recommended_option_id == gb.RESCUE_PILOT


def test_long_procurement_cycle_triggers_hard_constraint_and_flips_recommendation():
    fixture = gb.spherical_robot_fixture()
    # A long procurement cycle is a held external intervention (delta vs the frozen
    # baseline), which propagates; it is not a baseline edit.
    result = run_simulation(
        fixture.graph, fixture.strategies[gb.RESCUE_PILOT], fixture.scenarios["agency_pull"],
        fixture.score_definition, fixture.risk_tolerance, FORMAL,
        node_overrides={"procurement_cycle_months": 14.0}, profile=OWNER_FP,
    )
    assert result.node_results["cash_safety"] < 0.45
    assert result.recommended_option_id == gb.CONTINUE_RESEARCH


def test_sensitivity_reports_procurement_as_top_flip_driver():
    fixture = gb.spherical_robot_fixture()
    sensitivity = analyze_sensitivity(
        fixture.graph, fixture.strategies[gb.RESCUE_PILOT], fixture.scenarios["agency_pull"],
        fixture.score_definition, fixture.risk_tolerance, FORMAL, profile=OWNER_FP,
    )
    assert sensitivity.base_recommended_option_id == gb.RESCUE_PILOT
    assert sensitivity.flip_conditions, "expected at least one flip condition"
    top_flip = sensitivity.flip_conditions[0]
    assert top_flip.node_id == "procurement_cycle_months"
    assert top_flip.to_option == gb.CONTINUE_RESEARCH
    assert 9.0 < top_flip.threshold <= 24.0
    assert sensitivity.business_steps["procurement_cycle_months"] == pytest.approx(2.1)


def test_sensitivity_business_step_defaults_to_ten_percent_of_range():
    nodes = [
        _node("driver", NodeType.EXTERNAL, 50.0, minimum=0.0, maximum=100.0, editable=True),
        _node("out", NodeType.OUTCOME, 0.5),
    ]
    graph = _graph(nodes, [_edge("e", "driver", "out", EdgePolarity.POSITIVE, 0.5)])
    result = analyze_sensitivity(
        graph, _strategy(), _scenario(), _score_single("opt", "out"), 0.0, FORMAL,
        profile=OWNER_FP,
    )
    assert result.business_steps["driver"] == pytest.approx(10.0)


# --- ScenarioVersion contract ------------------------------------------------------------


def test_scenario_version_never_carries_risk_tolerance():
    fields = {field.name for field in dataclasses.fields(ScenarioVersion)}
    assert "risk_tolerance" not in fields
    assert {
        "source_lens_artifact_id",
        "source_strategic_scenario_id",
        "strategy_survives",
        "early_warning_signals",
    } <= fields


def test_scenario_node_shifts_must_be_normalized_deltas():
    with pytest.raises(SimulationInputError):
        _scenario(node_shifts={"procurement_cycle_months": 14.0})


def test_scenario_requires_source_lens_and_frame_ids():
    with pytest.raises(SimulationInputError):
        _scenario(source_lens_artifact_id="")
    with pytest.raises(SimulationInputError):
        _scenario(source_strategic_scenario_id="")


# --- formal vs experimental origin / authorization ---------------------------------------


def test_formal_run_requires_confirmed_graph_version():
    nodes = [_node("src", NodeType.EXTERNAL, 0.5), _node("tgt", NodeType.OUTCOME, 0.5)]
    draft = _graph(nodes, [_edge("e", "src", "tgt", EdgePolarity.POSITIVE, 0.5)], status=GraphVersionStatus.DRAFT)
    with pytest.raises(SimulationAuthorizationError):
        run_simulation(
            draft, _strategy(), _scenario(), _score_single("opt", "tgt"), 0.0, FORMAL,
            profile=OWNER_FP,
        )


def test_formal_run_requires_confirmed_propagating_nodes():
    nodes = [
        _node("src", NodeType.EXTERNAL, 0.5, status=ElementStatus.DRAFT),
        _node("tgt", NodeType.OUTCOME, 0.5),
    ]
    graph = _graph(nodes, [_edge("e", "src", "tgt", EdgePolarity.POSITIVE, 0.5)])
    with pytest.raises(SimulationAuthorizationError):
        run_simulation(
            graph, _strategy(), _scenario(), _score_single("opt", "tgt"), 0.0, FORMAL,
            profile=OWNER_FP,
        )


def test_eligible_edges_differ_between_formal_and_experimental():
    nodes = [
        _node("src", NodeType.EXTERNAL, 0.5),
        _node("mid", NodeType.INTERMEDIATE, 0.5),
        _node("tgt", NodeType.OUTCOME, 0.5),
    ]
    edges = [
        _edge("confirmed", "src", "tgt", EdgePolarity.POSITIVE, 0.5, status=ElementStatus.CONFIRMED),
        _edge(
            "draft", "mid", "tgt", EdgePolarity.POSITIVE, 0.5, status=ElementStatus.DRAFT,
            claim_ids=(), assumption_ids=("asm",),
        ),
        _edge("rejected", "src", "mid", EdgePolarity.POSITIVE, 0.5, status=ElementStatus.REJECTED),
    ]
    graph = _graph(nodes, edges)
    formal_ids = {edge.id for edge in eligible_edges(graph, FORMAL)}
    experimental_ids = {edge.id for edge in eligible_edges(graph, EXPERIMENTAL)}
    assert formal_ids == {"confirmed"}
    assert experimental_ids == {"confirmed", "draft"}
    assert "rejected" not in experimental_ids


# --- from-report draft -> confirmed version ----------------------------------------------


def test_build_from_report_produces_immutable_draft():
    nodes = (
        _node("src", NodeType.EXTERNAL, 0.5),
        _node("tgt", NodeType.OUTCOME, 0.5),
    )
    edges = (_edge("e", "src", "tgt", EdgePolarity.POSITIVE, 0.5),)
    draft = gb.build_from_report(nodes, edges)
    assert draft.status == GraphVersionStatus.DRAFT
    assert all(node.status == ElementStatus.DRAFT for node in draft.nodes)
    assert all(edge.status == ElementStatus.DRAFT for edge in draft.edges)


def test_confirm_graph_version_confirms_reviewed_elements():
    nodes = (
        _node("src", NodeType.EXTERNAL, 0.5),
        _node("tgt", NodeType.OUTCOME, 0.5),
    )
    edges = (_edge("e", "src", "tgt", EdgePolarity.POSITIVE, 0.5),)
    draft = gb.build_from_report(nodes, edges)
    confirmed = gb.confirm_graph_version(
        draft,
        version_id="gv_confirmed",
        confirm_node_ids=frozenset({"src", "tgt"}),
        confirm_edge_ids=frozenset({"e"}),
    )
    assert confirmed.status == GraphVersionStatus.CONFIRMED
    assert all(node.status == ElementStatus.CONFIRMED for node in confirmed.nodes)
    assert all(edge.status == ElementStatus.CONFIRMED for edge in confirmed.edges)


def test_confirm_graph_version_refuses_edges_without_claims():
    nodes = (
        _node("src", NodeType.EXTERNAL, 0.5),
        _node("tgt", NodeType.OUTCOME, 0.5),
    )
    edges = (
        _edge("assumption_edge", "src", "tgt", EdgePolarity.POSITIVE, 0.5, status=ElementStatus.DRAFT, claim_ids=(), assumption_ids=("asm",)),
    )
    draft = gb.build_from_report(nodes, edges)
    with pytest.raises(GraphInvariantError):
        gb.confirm_graph_version(
            draft,
            version_id="gv_confirmed",
            confirm_node_ids=frozenset({"src", "tgt"}),
            confirm_edge_ids=frozenset({"assumption_edge"}),
        )


# --- graph invariants --------------------------------------------------------------------


def test_graph_rejects_duplicate_and_dangling_references():
    node = _node("a", NodeType.EXTERNAL, 0.5)
    with pytest.raises(GraphInvariantError):
        GraphVersion(
            id="g", graph_id="g", status=GraphVersionStatus.CONFIRMED, nodes=(node, node), edges=()
        )
    with pytest.raises(GraphInvariantError):
        _graph([node], [_edge("e", "a", "missing", EdgePolarity.POSITIVE, 0.5)])


def test_spherical_robot_graph_meets_fixture_floor():
    graph = gb.spherical_robot_confirmed_graph()
    assert len(graph.nodes) >= 8
    assert len(graph.edges) >= 10
    assert graph.status == GraphVersionStatus.CONFIRMED
    assert any(node.id == "procurement_cycle_months" for node in graph.nodes)
