"""Canonical QA acceptance for the Task 12 simulation engine (lane rows SG-01..SG-09).

Independent QA evidence on top of the owner suite in
``app/simulations/tests/`` (28 tests, adopted as-is): this file re-verifies
the headline release properties from the QA matrix, including byte-level
repeat-run stability and the spherical-robot fixture contract. Skips cleanly
on baselines without ``app.simulations.engine``.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

pytest.importorskip(
    "app.simulations.engine", reason="Task 12 simulation engine not delivered yet"
)

from app.simulations import graph_builder as gb
from app.simulations.domain import GraphVersionStatus, SimulationInputError
from app.simulations.engine import ENGINE_VERSION, run_simulation
from app.simulations.sensitivity import analyze_sensitivity
from app.types import SimulationConvergenceStatus, SimulationMode

FORMAL = SimulationMode.FORMAL


def _run(fixture, *, strategy=None, scenario="agency_pull", **overrides):
    return run_simulation(
        fixture.graph,
        strategy or fixture.strategies[gb.RESCUE_PILOT],
        fixture.scenarios[scenario],
        fixture.score_definition,
        fixture.risk_tolerance,
        FORMAL,
        **overrides,
    )


def _serialize(result) -> bytes:
    """Canonical byte serialization of an entire SimulationResult."""

    payload = dataclasses.asdict(result)
    return json.dumps(payload, sort_keys=True, default=str).encode("utf-8")


# ---------------------------------------------------------------------------
# SG-01: determinism, inputHash, byte-level repeat stability
# ---------------------------------------------------------------------------


def test_repeat_runs_are_byte_identical_with_same_input_hash() -> None:
    first = _run(gb.spherical_robot_fixture())
    second = _run(gb.spherical_robot_fixture())
    assert first.input_hash == second.input_hash
    assert first.engine_version == second.engine_version == ENGINE_VERSION
    assert _serialize(first) == _serialize(second), (
        "identical frozen inputs must reproduce the full result byte-for-byte"
    )


def test_input_hash_changes_when_any_frozen_input_changes() -> None:
    fixture = gb.spherical_robot_fixture()
    baseline = _run(fixture)
    other_strategy = next(
        key for key in fixture.strategies if key != gb.RESCUE_PILOT
    )
    assert _run(fixture, strategy=fixture.strategies[other_strategy]).input_hash != baseline.input_hash
    assert _run(fixture, epsilon=0.0005).input_hash != baseline.input_hash
    assert _run(fixture, max_steps=20).input_hash != baseline.input_hash


# ---------------------------------------------------------------------------
# SG-04/SG-06: authorization and immutability boundaries
# ---------------------------------------------------------------------------


def test_formal_mode_rejects_unconfirmed_graph() -> None:
    fixture = gb.spherical_robot_fixture()
    draft_graph = dataclasses.replace(fixture.graph, status=GraphVersionStatus.DRAFT)
    with pytest.raises(Exception) as excinfo:
        run_simulation(
            draft_graph,
            fixture.strategies[gb.RESCUE_PILOT],
            fixture.scenarios["agency_pull"],
            fixture.score_definition,
            fixture.risk_tolerance,
            FORMAL,
        )
    assert "confirmed" in str(excinfo.value).lower()


def test_experimental_mode_accepts_draft_graph() -> None:
    fixture = gb.spherical_robot_fixture()
    draft_graph = dataclasses.replace(fixture.graph, status=GraphVersionStatus.DRAFT)
    result = run_simulation(
        draft_graph,
        fixture.strategies[gb.RESCUE_PILOT],
        fixture.scenarios["agency_pull"],
        fixture.score_definition,
        fixture.risk_tolerance,
        SimulationMode.EXPERIMENTAL,
    )
    assert result.mode is SimulationMode.EXPERIMENTAL


def test_scenario_version_has_no_risk_tolerance_field() -> None:
    fixture = gb.spherical_robot_fixture()
    scenario = fixture.scenarios["agency_pull"]
    field_names = {f.name for f in dataclasses.fields(scenario)}
    assert "risk_tolerance" not in field_names
    assert "riskTolerance" not in field_names


def test_invalid_numeric_inputs_are_rejected() -> None:
    fixture = gb.spherical_robot_fixture()
    with pytest.raises(SimulationInputError):
        _run(fixture, epsilon=0.0)
    with pytest.raises(SimulationInputError):
        _run(fixture, max_steps=0)
    with pytest.raises(SimulationInputError):
        run_simulation(
            fixture.graph,
            fixture.strategies[gb.RESCUE_PILOT],
            fixture.scenarios["agency_pull"],
            fixture.score_definition,
            1.5,
            FORMAL,
        )


# ---------------------------------------------------------------------------
# SG-09: spherical-robot fixture contract, hard constraint flip, sensitivity
# ---------------------------------------------------------------------------


def test_fixture_meets_minimum_size_contract() -> None:
    fixture = gb.spherical_robot_fixture()
    assert len(fixture.graph.nodes) >= 8, "fixture requires at least 8 nodes"
    assert len(fixture.graph.edges) >= 10, "fixture requires at least 10 edges"
    assert len(fixture.scenarios) >= 3, "fixture requires three scenarios"
    assert len(fixture.strategies) >= 2


def test_baseline_scenario_recommends_rescue_pilot_and_converges() -> None:
    result = _run(gb.spherical_robot_fixture())
    assert result.convergence_status is SimulationConvergenceStatus.CONVERGED
    assert result.recommended_option_id == gb.RESCUE_PILOT
    assert result.steps <= 12
    assert all(0.0 <= value <= 1.0 for value in result.node_results.values()), (
        "normalized node results must stay clamped to the unit interval"
    )


def test_procurement_scenario_flips_recommendation_away_from_rescue() -> None:
    fixture = gb.spherical_robot_fixture()
    flip_scenario = next(
        name for name in fixture.scenarios if "procurement" in name.lower()
    )
    result = _run(fixture, scenario=flip_scenario)
    assert result.recommended_option_id != gb.RESCUE_PILOT, (
        "long procurement cycle must flip the recommendation (hard constraint)"
    )


def test_sensitivity_identifies_flip_threshold_driver() -> None:
    fixture = gb.spherical_robot_fixture()
    sensitivity = analyze_sensitivity(
        fixture.graph,
        fixture.strategies[gb.RESCUE_PILOT],
        fixture.scenarios["agency_pull"],
        fixture.score_definition,
        fixture.risk_tolerance,
        FORMAL,
    )
    assert sensitivity.flip_conditions, "sensitivity must surface flip conditions"
    top = sensitivity.flip_conditions[0]
    assert "procurement" in str(top).lower(), (
        "procurement cycle is the designed top flip driver of the fixture"
    )


def test_sensitivity_is_deterministic_across_repeat_runs() -> None:
    fixture = gb.spherical_robot_fixture()

    def _analyze():
        return analyze_sensitivity(
            fixture.graph,
            fixture.strategies[gb.RESCUE_PILOT],
            fixture.scenarios["agency_pull"],
            fixture.score_definition,
            fixture.risk_tolerance,
            FORMAL,
        )

    first, second = _analyze(), _analyze()
    assert json.dumps(dataclasses.asdict(first), sort_keys=True, default=str) == json.dumps(
        dataclasses.asdict(second), sort_keys=True, default=str
    )
