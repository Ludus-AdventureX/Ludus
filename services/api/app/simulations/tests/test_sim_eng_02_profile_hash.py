"""Owner verification for CCR-ENG-02: profile-aware input hash (sim-engine-1.1.0).

Covers the contract acceptance matrix (CCR-20260724-ENG-02 §8): exact engine
version, independent payload re-derivation, single-variable hash sensitivity for
profile.id / profile.version / profile.contentHash / riskTolerance, the persisted
content-hash format gate (fail-closed ``frozen_reference_incomplete`` BEFORE the
engine), single-fingerprint reuse between base run and sensitivity, historical
sim-engine-1.0.0 row immutability, zero numeric drift, and Addendum A1
non-regression. DB tests run like the r1 owner suite (disposable PostgreSQL,
main venv, transactional rollback session).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.simulations.service as service_module
from app.models import DecisionMakerProfile, SimulationRun as SimulationRunRow
from app.simulations import engine as engine_module
from app.simulations import graph_builder as gb
from app.simulations.assembly import assemble_profile_fingerprint
from app.simulations.domain import ProfileFingerprint, SimulationInputError
from app.simulations.engine import ENGINE_VERSION, compute_input_hash, run_simulation
from app.simulations.errors import FrozenReferenceError
from app.simulations.repository import SimulationInputRepository
from app.simulations.service import SimulationRunService
from app.types import SimulationMode

from test_simulation_repository_service import (  # same-directory owner helpers
    NOW,
    SEED_PROFILE_VERSION,
    request_for,
    scoped_run_count,
    seed_world,
)

FORMAL = SimulationMode.FORMAL

_VALID_HASH = "sha256:" + "ab12" * 16


def _fingerprint(**overrides) -> ProfileFingerprint:
    values = {"id": str(uuid4()), "version": 1, "content_hash": _VALID_HASH}
    values.update(overrides)
    return ProfileFingerprint(**values)


def _profile_row(**overrides) -> DecisionMakerProfile:
    """Unpersisted ORM instance for exercising the assembly format gate."""

    values = {
        "id": uuid4(),
        "workspace_id": uuid4(),
        "profile_id": uuid4(),
        "decision_case_id": None,
        "user_id": uuid4(),
        "display_name": "gate probe",
        "version": 1,
        "preference_weights": {},
        "risk_tolerance": 0.5,
        "content_hash": _VALID_HASH,
    }
    values.update(overrides)
    return DecisionMakerProfile(**values)


def _engine_hash(fixture, *, profile, risk_tolerance=None) -> str:
    return compute_input_hash(
        fixture.graph,
        fixture.strategies[gb.RESCUE_PILOT],
        fixture.scenarios["agency_pull"],
        fixture.score_definition,
        fixture.risk_tolerance if risk_tolerance is None else risk_tolerance,
        FORMAL,
        {},
        0.001,
        12,
        profile=profile,
    )


# --- engine identity ------------------------------------------------------------------


def test_engine_version_is_exactly_sim_engine_1_1_0() -> None:
    assert ENGINE_VERSION == "sim-engine-1.1.0"
    # Single authoritative constant: the result carries the same object.
    fixture = gb.spherical_robot_fixture()
    result = run_simulation(
        fixture.graph,
        fixture.strategies[gb.RESCUE_PILOT],
        fixture.scenarios["agency_pull"],
        fixture.score_definition,
        fixture.risk_tolerance,
        FORMAL,
        profile=_fingerprint(),
    )
    assert result.engine_version == "sim-engine-1.1.0"


def test_hash_payload_independent_rederivation() -> None:
    """White-box re-derivation of the exact frozen §2 payload shape."""

    fixture = gb.spherical_robot_fixture()
    fp = _fingerprint()
    strategy = fixture.strategies[gb.RESCUE_PILOT]
    payload = {
        "engineVersion": "sim-engine-1.1.0",
        "mode": FORMAL.value,
        "epsilon": 0.001,
        "maxSteps": 12,
        "riskTolerance": round(fixture.risk_tolerance + 0.0, 12),
        "profile": {"id": fp.id, "version": fp.version, "contentHash": fp.content_hash},
        "graph": engine_module._graph_fingerprint(fixture.graph),
        "strategy": {
            "id": strategy.id,
            "version": strategy.version,
            "nodeOverrides": {
                k: round(v + 0.0, 12) for k, v in sorted(strategy.node_overrides.items())
            },
        },
        "scenario": engine_module._scenario_fingerprint(fixture.scenarios["agency_pull"]),
        "scoreDefinition": engine_module._score_fingerprint(fixture.score_definition),
        "nodeOverrides": {},
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    expected = "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    assert _engine_hash(fixture, profile=fp) == expected
    # riskTolerance stays a top-level key; the profile block adds exactly three keys.
    assert set(payload["profile"]) == {"id", "version", "contentHash"}
    assert "riskTolerance" in payload


def test_profile_single_variable_hash_sensitivity() -> None:
    fixture = gb.spherical_robot_fixture()
    fp = _fingerprint()
    base = _engine_hash(fixture, profile=fp)

    # Determinism: repeated computation of the identical full input.
    assert _engine_hash(fixture, profile=dataclasses.replace(fp)) == base
    # Each identity field alone moves the hash.
    assert _engine_hash(fixture, profile=dataclasses.replace(fp, id=str(uuid4()))) != base
    assert _engine_hash(fixture, profile=dataclasses.replace(fp, version=2)) != base
    other_hash = "sha256:" + "cd34" * 16
    assert (
        _engine_hash(fixture, profile=dataclasses.replace(fp, content_hash=other_hash))
        != base
    )
    # riskTolerance alone moves the hash (top-level key preserved).
    assert _engine_hash(fixture, profile=fp, risk_tolerance=0.61) != base
    # Same riskTolerance, different profile identity → DIFFERENT hash (flips the
    # QA-pinned P2 assertion by design).
    twin = _fingerprint()
    assert twin.id != fp.id
    assert _engine_hash(fixture, profile=twin) != base


def test_numeric_results_do_not_drift_with_profile_fingerprint() -> None:
    fixture = gb.spherical_robot_fixture()
    args = (
        fixture.graph,
        fixture.strategies[gb.RESCUE_PILOT],
        fixture.scenarios["agency_pull"],
        fixture.score_definition,
        fixture.risk_tolerance,
        FORMAL,
    )
    # Profile identity is hash-only: two different fingerprints must produce
    # byte-identical numerics and different replay identities.
    first = run_simulation(*args, profile=_fingerprint())
    second = run_simulation(*args, profile=_fingerprint())
    assert second.node_results == first.node_results
    assert second.option_scores == first.option_scores
    assert second.convergence_status == first.convergence_status
    assert second.steps == first.steps
    assert second.recommended_option_id == first.recommended_option_id
    # Only the replay identity differs.
    assert second.input_hash != first.input_hash


def test_missing_or_none_profile_is_rejected_no_1_1_0_legacy_mode() -> None:
    """Fast-fix probes: sim-engine-1.1.0 has no missing-profile hash mode."""

    fixture = gb.spherical_robot_fixture()
    hash_args = (
        fixture.graph,
        fixture.strategies[gb.RESCUE_PILOT],
        fixture.scenarios["agency_pull"],
        fixture.score_definition,
        fixture.risk_tolerance,
        FORMAL,
        {},
        0.001,
        12,
    )
    run_args = hash_args[:6]
    # 1. compute_input_hash without profile -> rejected at call time.
    with pytest.raises(TypeError):
        compute_input_hash(*hash_args)
    # 2. compute_input_hash(profile=None) -> fail fast.
    with pytest.raises(SimulationInputError):
        compute_input_hash(*hash_args, profile=None)
    # 3. run_simulation without profile -> rejected at call time.
    with pytest.raises(TypeError):
        run_simulation(*run_args)
    # 4. run_simulation(profile=None) -> fail fast.
    with pytest.raises(SimulationInputError):
        run_simulation(*run_args, profile=None)


def test_sensitivity_sweeps_all_use_the_same_fingerprint(monkeypatch) -> None:
    """Fast-fix probe: base + every sweep/perturbation carry one identical fingerprint."""

    import app.simulations.sensitivity as sensitivity_module

    fixture = gb.spherical_robot_fixture()
    fingerprint = _fingerprint()
    captured: list[object] = []
    real_run = sensitivity_module.run_simulation

    def _capturing_run(*args, **kwargs):
        captured.append(kwargs.get("profile", "MISSING"))
        return real_run(*args, **kwargs)

    monkeypatch.setattr(sensitivity_module, "run_simulation", _capturing_run)
    result = sensitivity_module.analyze_sensitivity(
        fixture.graph,
        fixture.strategies[gb.RESCUE_PILOT],
        fixture.scenarios["agency_pull"],
        fixture.score_definition,
        fixture.risk_tolerance,
        FORMAL,
        profile=fingerprint,
    )
    assert result.top_drivers, "sweep must have executed"
    assert len(captured) >= 3, "base + perturbation runs expected"
    assert all(entry is fingerprint for entry in captured), (
        "every engine call (base and each sweep) must carry the identical "
        "verified fingerprint; None/anonymous profiles are forbidden"
    )


def test_bare_dict_fingerprint_is_rejected() -> None:
    fixture = gb.spherical_robot_fixture()
    with pytest.raises(SimulationInputError):
        _engine_hash(
            fixture,
            profile={"id": str(uuid4()), "version": 1, "contentHash": _VALID_HASH},
        )


# --- assembly format gate -------------------------------------------------------------


def test_fingerprint_format_gate_fails_closed() -> None:
    digest = _VALID_HASH.removeprefix("sha256:")
    for bad in (
        None,
        "",
        123,
        digest,  # missing sha256: prefix
        "sha256:" + digest.upper(),  # not lowercase
        "sha256:" + digest[:-1],  # wrong digest length
        "sha256:" + digest[:-1] + "g",  # non-hex character
        "SHA256:" + digest,  # wrongly-cased prefix
    ):
        with pytest.raises(FrozenReferenceError) as failure:
            assemble_profile_fingerprint(_profile_row(content_hash=bad))
        assert failure.value.code == "frozen_reference_incomplete"

    for bad_version in (0, -1, True):
        with pytest.raises(FrozenReferenceError) as failure:
            assemble_profile_fingerprint(_profile_row(version=bad_version))
        assert failure.value.code == "frozen_reference_incomplete"


def test_fingerprint_uses_stable_profile_id_canonical_lowercase() -> None:
    row = _profile_row()
    fingerprint = assemble_profile_fingerprint(row)
    assert fingerprint.id == str(row.profile_id)
    assert fingerprint.id != str(row.id), "row PK must never leak into the fingerprint"
    assert fingerprint.id == fingerprint.id.lower()
    assert str(UUID(fingerprint.id)) == fingerprint.id
    assert fingerprint.version == row.version
    assert fingerprint.content_hash == row.content_hash
    with pytest.raises(dataclasses.FrozenInstanceError):
        fingerprint.content_hash = "sha256:tampered"  # type: ignore[misc]


# --- service data flow ------------------------------------------------------------------


async def test_service_run_carries_profile_aware_hash_end_to_end(
    session: AsyncSession,
) -> None:
    world = await seed_world(session, f"eng02-e2e-{uuid4().hex[:6]}")
    service = SimulationRunService(session)
    view = await service.run_and_record(world.context, request_for(world))

    row = await session.scalar(
        select(SimulationRunRow).where(
            SimulationRunRow.workspace_id == world.workspace_id,
            SimulationRunRow.id == view.id,
        )
    )
    assert row is not None
    # persisted/view identity consistency (contract §8).
    assert row.engine_version == view.engine_version == "sim-engine-1.1.0"
    assert row.input_hash == view.input_hash
    assert row.decision_maker_profile_id == view.decision_maker_profile_id == world.profile_id
    assert row.decision_maker_profile_version == view.decision_maker_profile_version
    assert row.risk_tolerance == view.risk_tolerance

    # Independent re-derivation through the verified frozen inputs: the persisted
    # hash MUST include the §2 profile block sourced from the verified row.
    assembled, row_refs = await service._load_frozen_input(
        world.context, request_for(world)
    )
    fingerprint = row_refs["profile_fingerprint"]
    profile_row = await SimulationInputRepository(session).get_decision_maker_profile(
        world.workspace_id, world.profile_id, SEED_PROFILE_VERSION
    )
    assert profile_row is not None
    assert fingerprint == assemble_profile_fingerprint(profile_row)
    rederived = compute_input_hash(
        assembled.graph,
        assembled.strategy,
        assembled.scenario,
        assembled.score_definition,
        row_refs["risk_tolerance"],
        SimulationMode.FORMAL,
        {},
        0.001,
        12,
        profile=fingerprint,
    )
    assert rederived == view.input_hash
    # A different fingerprint provably changes the persisted replay identity.
    other_fingerprint = _fingerprint()
    with_other_profile = compute_input_hash(
        assembled.graph,
        assembled.strategy,
        assembled.scenario,
        assembled.score_definition,
        row_refs["risk_tolerance"],
        SimulationMode.FORMAL,
        {},
        0.001,
        12,
        profile=other_fingerprint,
    )
    assert with_other_profile != view.input_hash


async def test_preference_weights_change_moves_content_hash_and_input_hash(
    session: AsyncSession,
) -> None:
    world = await seed_world(session, f"eng02-pw-{uuid4().hex[:6]}")
    service = SimulationRunService(session)
    repository = SimulationInputRepository(session)
    baseline = await service.run_and_record(world.context, request_for(world))

    # Same riskTolerance, same display name; ONLY preferenceWeights change.
    v2 = await repository.insert_decision_maker_profile(
        workspace_id=world.workspace_id,
        profile_id=world.profile_id,
        version=2,
        user_id=world.user_id,
        display_name=f"profile-{world.profile_id.hex[:6]}",
        preference_weights={"traction": 0.2, "cash": 0.8},
        risk_tolerance=0.5,
    )
    v1 = await repository.get_decision_maker_profile(
        world.workspace_id, world.profile_id, SEED_PROFILE_VERSION
    )
    assert v1 is not None and v2.content_hash != v1.content_hash

    changed = await service.run_and_record(
        world.context, request_for(world, decision_maker_profile_version=2)
    )
    assert changed.risk_tolerance == baseline.risk_tolerance
    assert changed.input_hash != baseline.input_hash, (
        "preferenceWeights must reach the inputHash through the profile contentHash"
    )


async def test_malformed_persisted_content_hash_fails_closed_before_engine(
    session: AsyncSession, monkeypatch
) -> None:
    world = await seed_world(session, f"eng02-gate-{uuid4().hex[:6]}")
    corrupted = _profile_row(
        workspace_id=world.workspace_id,
        profile_id=world.profile_id,
        content_hash="sha256:not-hex",
    )

    async def _return_corrupted(self, workspace_id, profile_id, version):
        return corrupted

    def _engine_must_not_run(*args, **kwargs):
        raise AssertionError("engine must never run behind a failed format gate")

    monkeypatch.setattr(
        SimulationInputRepository, "get_decision_maker_profile", _return_corrupted
    )
    monkeypatch.setattr(service_module, "run_simulation", _engine_must_not_run)

    service = SimulationRunService(session)
    with pytest.raises(FrozenReferenceError) as failure:
        await service.run_and_record(world.context, request_for(world))
    assert failure.value.code == "frozen_reference_incomplete"
    assert await scoped_run_count(session, world) == 0, "zero zombie SimulationRun rows"


async def test_base_and_sensitivity_share_single_fingerprint(
    session: AsyncSession, monkeypatch
) -> None:
    world = await seed_world(session, f"eng02-sens-{uuid4().hex[:6]}")

    fingerprint_calls: list[ProfileFingerprint] = []
    real_assemble = service_module.assemble_profile_fingerprint

    def _counting_assemble(row):
        fingerprint = real_assemble(row)
        fingerprint_calls.append(fingerprint)
        return fingerprint

    captured_profiles: list[object] = []
    real_run = service_module.run_simulation

    def _capturing_run(*args, **kwargs):
        captured_profiles.append(kwargs.get("profile"))
        return real_run(*args, **kwargs)

    monkeypatch.setattr(service_module, "assemble_profile_fingerprint", _counting_assemble)
    monkeypatch.setattr(service_module, "run_simulation", _capturing_run)

    service = SimulationRunService(session)
    view = await service.run_and_record(
        world.context, request_for(world, include_sensitivity=True)
    )
    assert view.engine_version == "sim-engine-1.1.0"
    # Fingerprint assembled EXACTLY once; the base engine call received it; the
    # sensitivity sweep re-runs the unchanged numeric engine with the same
    # riskTolerance and triggers no additional profile lookup/assembly.
    assert len(fingerprint_calls) == 1
    assert captured_profiles == [fingerprint_calls[0]]


async def test_historical_1_0_0_row_is_completely_immutable(
    session: AsyncSession,
) -> None:
    world = await seed_world(session, f"eng02-hist-{uuid4().hex[:6]}")
    legacy_hash = "sha256:" + "0f" * 32
    legacy = SimulationRunRow(
        id=uuid4(),
        workspace_id=world.workspace_id,
        decision_case_id=world.case_id,
        graph_id=world.graph_id,
        graph_version_id=world.graph_version_id,
        strategy_version_id=world.strategy_version_id,
        scenario_version_id=world.scenario_version_id,
        score_definition_id=world.score_definition_id,
        score_definition_version="1",
        decision_maker_profile_id=world.profile_id,
        decision_maker_profile_version=SEED_PROFILE_VERSION,
        risk_tolerance=0.5,
        engine_version="sim-engine-1.0.0",
        scenario_id=uuid4(),
        simulation_mode=SimulationMode.FORMAL,
        epsilon=0.001,
        max_steps=12,
        steps=3,
        input_hash=legacy_hash,
        node_results={"legacy": 0.5},
        option_scores=[{"optionId": world.option_a, "score": 0.5}],
        top_drivers=[],
        recommendation_shift="No change",
        convergence_status="converged",
        origin_modes=["fixture"],
        created_at=NOW,
    )
    session.add(legacy)
    await session.flush()
    legacy_id = legacy.id

    fresh = await SimulationRunService(session).run_and_record(
        world.context, request_for(world)
    )
    assert fresh.engine_version == "sim-engine-1.1.0"
    assert fresh.input_hash != legacy_hash

    session.expire_all()
    row = await session.scalar(
        select(SimulationRunRow).where(
            SimulationRunRow.workspace_id == world.workspace_id,
            SimulationRunRow.id == legacy_id,
        )
    )
    assert row is not None
    assert row.engine_version == "sim-engine-1.0.0"
    assert row.input_hash == legacy_hash
    assert row.node_results == {"legacy": 0.5}
    assert row.steps == 3
    assert row.risk_tolerance == 0.5


# --- Addendum A1 non-regression ----------------------------------------------------------


def test_addendum_a1_fail_closed_codes_are_untouched() -> None:
    # The stable codes remain verbatim, and the 1.1.0 bump smuggles neither
    # equality scoring nor edge gating into the engine.
    from app.simulations.domain import Comparison
    from app.simulations.errors import (
        ScoreDefinitionReferenceError,
        StrategyOverrideError,
    )

    assert "=" not in {member.value for member in Comparison}
    assert StrategyOverrideError("x", code="strategy_edge_gating_unsupported").code == (
        "strategy_edge_gating_unsupported"
    )
    assert ScoreDefinitionReferenceError(
        "x", code="score_constraint_operator_unsupported"
    ).code == "score_constraint_operator_unsupported"
    # Full behavioral coverage stays in the r1 owner suite
    # (test_strategy_edge_gating_fails_fast_as_contract_dependency,
    #  test_score_equality_operator_fails_fast_as_contract_dependency).
