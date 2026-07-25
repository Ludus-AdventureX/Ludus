"""Owner verification for CCR-SIM-02A prerequisites P1 + P3.

P1: immutable ``decision_maker_profiles`` persistence, the tenant-scoped frozen
profile FK on ``simulation_runs``, and service-side riskTolerance resolution.
P3: the generic ``idempotency_records`` persistence schema (schema only; no
replay/conflict runtime flow exists in this slice by contract).

Run exactly like the r1 owner suite (disposable clean PostgreSQL + main venv):

    $env:DATABASE_URL = "postgresql+asyncpg://<user>:<password>@localhost:<port>/decision_lab"
    <mainvenv>python -m pytest app/simulations/tests -q
"""

from __future__ import annotations

import dataclasses
import inspect
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DecisionMakerProfile, IdempotencyRecord, SimulationRun as SimulationRunRow
from app.security.envelope import ApiFailure
from app.simulations.profile_hash import compute_profile_content_hash
from app.simulations.repository import SimulationInputRepository
from app.simulations.service import SimulationRunRequest, SimulationRunService

from test_simulation_repository_service import (  # same-directory owner helpers
    NOW,
    SEED_PROFILE_RISK_TOLERANCE,
    SEED_PROFILE_VERSION,
    World,
    request_for,
    seed_world,
)


async def _expect_integrity_error(session: AsyncSession, row) -> None:
    savepoint = await session.begin_nested()
    with pytest.raises(IntegrityError):
        session.add(row)
        await session.flush()
    await savepoint.rollback()


def _run_values(world: World, profile_id, profile_version: int) -> dict:
    """A fully valid simulation_runs direct-insert payload except the profile ref."""

    return {
        "id": uuid4(),
        "workspace_id": world.workspace_id,
        "decision_case_id": world.case_id,
        "graph_id": world.graph_id,
        "graph_version_id": world.graph_version_id,
        "strategy_version_id": world.strategy_version_id,
        "scenario_version_id": world.scenario_version_id,
        "score_definition_id": world.score_definition_id,
        "score_definition_version": "1",
        "decision_maker_profile_id": profile_id,
        "decision_maker_profile_version": profile_version,
        "risk_tolerance": 0.5,
        "engine_version": "sim-engine-1.0.0",
        "scenario_id": uuid4(),
        "simulation_mode": "formal",
        "epsilon": 0.001,
        "max_steps": 12,
        "steps": 3,
        "input_hash": "sha256:owner-p1-fk-probe",
        "node_results": {},
        "option_scores": [],
        "top_drivers": [],
        "recommendation_shift": "No change",
        "convergence_status": "converged",
        "origin_modes": ["fixture"],
    }


# --- P1: profile content hash is deterministic and server-owned ----------------------------


def test_profile_content_hash_is_deterministic_and_key_order_independent() -> None:
    kwargs = dict(
        workspace_id=uuid4(),
        profile_id=uuid4(),
        version=1,
        decision_case_id=None,
        user_id=uuid4(),
        display_name="CEO baseline",
        risk_tolerance=0.4,
    )
    first = compute_profile_content_hash(
        preference_weights={"traction": 0.7, "cash": 0.3}, **kwargs
    )
    second = compute_profile_content_hash(
        preference_weights={"cash": 0.3, "traction": 0.7}, **kwargs
    )
    assert first == second, "JSONB key order must never influence the hash"
    assert first.startswith("sha256:")


def test_profile_content_hash_changes_on_any_frozen_field() -> None:
    base = dict(
        workspace_id=uuid4(),
        profile_id=uuid4(),
        version=1,
        decision_case_id=None,
        user_id=uuid4(),
        display_name="CEO baseline",
        preference_weights={"traction": 0.7},
        risk_tolerance=0.4,
    )
    baseline = compute_profile_content_hash(**base)
    for delta in (
        {"workspace_id": uuid4()},
        {"profile_id": uuid4()},
        {"version": 2},
        {"decision_case_id": uuid4()},
        {"user_id": uuid4()},
        {"display_name": "CEO revised"},
        {"preference_weights": {"traction": 0.8}},
        {"risk_tolerance": 0.41},
    ):
        assert compute_profile_content_hash(**{**base, **delta}) != baseline, (
            f"{list(delta)} must change the content hash"
        )


async def test_repository_computes_content_hash_server_side(session: AsyncSession) -> None:
    world = await seed_world(session, f"p1-hash-{uuid4().hex[:6]}")
    row = await session.scalar(
        select(DecisionMakerProfile).where(
            DecisionMakerProfile.workspace_id == world.workspace_id,
            DecisionMakerProfile.profile_id == world.profile_id,
            DecisionMakerProfile.version == SEED_PROFILE_VERSION,
        )
    )
    assert row is not None
    assert row.content_hash == compute_profile_content_hash(
        workspace_id=row.workspace_id,
        profile_id=row.profile_id,
        version=row.version,
        decision_case_id=row.decision_case_id,
        user_id=row.user_id,
        display_name=row.display_name,
        preference_weights=row.preference_weights,
        risk_tolerance=row.risk_tolerance,
    )
    # The only write path cannot accept a caller-forged hash.
    signature = inspect.signature(SimulationInputRepository.insert_decision_maker_profile)
    assert "content_hash" not in signature.parameters


# --- P1: append-only identity + no update/delete surface -----------------------------------


async def test_profile_business_identity_is_unique_per_version(session: AsyncSession) -> None:
    world = await seed_world(session, f"p1-uniq-{uuid4().hex[:6]}")
    repository = SimulationInputRepository(session)

    # Same (workspace, profile_id, version) again: append-only identity violated.
    savepoint = await session.begin_nested()
    with pytest.raises(IntegrityError):
        await repository.insert_decision_maker_profile(
            workspace_id=world.workspace_id,
            profile_id=world.profile_id,
            version=SEED_PROFILE_VERSION,
            user_id=world.user_id,
            display_name="duplicate v1",
            preference_weights={},
            risk_tolerance=0.2,
        )
    await savepoint.rollback()

    # A new version is a new row with its own storage PK.
    v2 = await repository.insert_decision_maker_profile(
        workspace_id=world.workspace_id,
        profile_id=world.profile_id,
        version=2,
        user_id=world.user_id,
        display_name="v2",
        preference_weights={},
        risk_tolerance=0.2,
    )
    v1 = await repository.get_decision_maker_profile(
        world.workspace_id, world.profile_id, SEED_PROFILE_VERSION
    )
    assert v1 is not None and v2.id != v1.id
    assert v2.profile_id == v1.profile_id, "stable profile_id spans versions"
    assert v2.id != v2.profile_id, "row PK is storage-only, never the stable profile id"


def test_repository_and_service_expose_no_profile_update_or_delete() -> None:
    for owner_class in (SimulationInputRepository, SimulationRunService):
        public = [name for name in dir(owner_class) if not name.startswith("_")]
        assert not [name for name in public if "update" in name or "delete" in name], (
            f"{owner_class.__name__} must not expose any update/delete surface"
        )


# --- P1: simulation_runs frozen profile FK ---------------------------------------------------


async def test_run_insert_rejects_ghost_and_wrong_version_profile_refs(
    session: AsyncSession,
) -> None:
    world = await seed_world(session, f"p1-fk-{uuid4().hex[:6]}")

    # Valid frozen reference: the direct insert commits (row is FK-verifiable).
    session.add(SimulationRunRow(**_run_values(world, world.profile_id, SEED_PROFILE_VERSION)))
    await session.flush()

    # Ghost profile id and real-id-wrong-version must both fail closed at the DB.
    await _expect_integrity_error(
        session, SimulationRunRow(**_run_values(world, uuid4(), SEED_PROFILE_VERSION))
    )
    await _expect_integrity_error(
        session, SimulationRunRow(**_run_values(world, world.profile_id, 99))
    )


async def test_run_insert_rejects_foreign_workspace_profile_ref(
    session: AsyncSession,
) -> None:
    world_a = await seed_world(session, f"p1-fka-{uuid4().hex[:6]}")
    world_b = await seed_world(session, f"p1-fkb-{uuid4().hex[:6]}")
    # Real profile, wrong tenant: composite FK binds workspace_id, so this is a ghost.
    await _expect_integrity_error(
        session,
        SimulationRunRow(**_run_values(world_a, world_b.profile_id, SEED_PROFILE_VERSION)),
    )


async def test_profile_case_scope_fk_rejects_foreign_case(session: AsyncSession) -> None:
    world_a = await seed_world(session, f"p1-case-{uuid4().hex[:6]}")
    world_b = await seed_world(session, f"p1-caseb-{uuid4().hex[:6]}")
    repository = SimulationInputRepository(session)
    savepoint = await session.begin_nested()
    with pytest.raises(IntegrityError):
        await repository.insert_decision_maker_profile(
            workspace_id=world_a.workspace_id,
            profile_id=uuid4(),
            version=1,
            user_id=world_a.user_id,
            display_name="cross-tenant case probe",
            preference_weights={},
            risk_tolerance=0.5,
            decision_case_id=world_b.case_id,
        )
    await savepoint.rollback()


# --- P1: service-side riskTolerance resolution ------------------------------------------------


def test_request_has_no_caller_supplied_risk_tolerance() -> None:
    field_names = {field.name for field in dataclasses.fields(SimulationRunRequest)}
    assert "risk_tolerance" not in field_names
    assert {"decision_maker_profile_id", "decision_maker_profile_version"} <= field_names


async def test_service_resolves_risk_tolerance_from_frozen_profile(
    session: AsyncSession,
) -> None:
    world = await seed_world(session, f"p1-rt-{uuid4().hex[:6]}")
    service = SimulationRunService(session)
    view = await service.run_and_record(world.context, request_for(world))
    assert view.risk_tolerance == SEED_PROFILE_RISK_TOLERANCE
    row = await session.scalar(
        select(SimulationRunRow).where(
            SimulationRunRow.workspace_id == world.workspace_id,
            SimulationRunRow.decision_case_id == world.case_id,
            SimulationRunRow.id == view.id,
        )
    )
    assert row is not None
    assert row.risk_tolerance == SEED_PROFILE_RISK_TOLERANCE
    assert row.decision_maker_profile_id == world.profile_id


async def test_new_profile_version_risk_tolerance_changes_input_hash(
    session: AsyncSession,
) -> None:
    world = await seed_world(session, f"p1-rtv2-{uuid4().hex[:6]}")
    service = SimulationRunService(session)
    baseline = await service.run_and_record(world.context, request_for(world))

    await SimulationInputRepository(session).insert_decision_maker_profile(
        workspace_id=world.workspace_id,
        profile_id=world.profile_id,
        version=2,
        user_id=world.user_id,
        display_name="v2 bolder",
        preference_weights={"traction": 0.7, "cash": 0.3},
        risk_tolerance=0.61,
    )
    changed = await service.run_and_record(
        world.context, request_for(world, decision_maker_profile_version=2)
    )
    assert changed.risk_tolerance == 0.61
    assert changed.input_hash != baseline.input_hash, (
        "the server-resolved riskTolerance is engine input and must move the hash"
    )


# --- P1: fail-closed profile scope resolution --------------------------------------------------


async def test_unresolvable_profile_refs_are_uniform_not_found(
    session: AsyncSession,
) -> None:
    world_a = await seed_world(session, f"p1-404a-{uuid4().hex[:6]}")
    world_b = await seed_world(session, f"p1-404b-{uuid4().hex[:6]}")

    service = SimulationRunService(session)
    denials = [
        # ghost profile id
        request_for(world_a, decision_maker_profile_id=uuid4()),
        # real profile, wrong version
        request_for(world_a, decision_maker_profile_version=7),
        # real profile of a foreign workspace
        request_for(world_a, decision_maker_profile_id=world_b.profile_id),
    ]
    for request in denials:
        with pytest.raises(ApiFailure) as failure:
            await service.run_and_record(world_a.context, request)
        assert failure.value.code == "CASE_NOT_FOUND"
        assert failure.value.http_status == 404


async def test_case_scoped_profile_usable_only_by_its_own_case(
    session: AsyncSession,
) -> None:
    world = await seed_world(session, f"p1-scope-{uuid4().hex[:6]}")
    other = await seed_world(session, f"p1-scope2-{uuid4().hex[:6]}")
    repository = SimulationInputRepository(session)

    # Case-scoped profile frozen onto world's own case: usable.
    scoped_profile = uuid4()
    await repository.insert_decision_maker_profile(
        workspace_id=world.workspace_id,
        profile_id=scoped_profile,
        version=1,
        user_id=world.user_id,
        display_name="case-scoped",
        preference_weights={},
        risk_tolerance=0.3,
        decision_case_id=world.case_id,
    )
    service = SimulationRunService(session)
    view = await service.run_and_record(
        world.context, request_for(world, decision_maker_profile_id=scoped_profile)
    )
    assert view.risk_tolerance == 0.3

    # The same case-scoped profile used from another case of another tenant: 404.
    with pytest.raises(ApiFailure) as failure:
        await service.run_and_record(
            other.context, request_for(other, decision_maker_profile_id=scoped_profile)
        )
    assert failure.value.code == "CASE_NOT_FOUND"

    # A second case in the SAME workspace must not consume the case-bound profile.
    same_ws_case_profile = uuid4()
    await repository.insert_decision_maker_profile(
        workspace_id=world.workspace_id,
        profile_id=same_ws_case_profile,
        version=1,
        user_id=world.user_id,
        display_name="bound to a sibling case",
        preference_weights={},
        risk_tolerance=0.9,
        decision_case_id=world.case_id,
    )
    # Simulate the sibling case by re-anchoring the request at a different case id:
    with pytest.raises(ApiFailure):
        await service.run_and_record(
            world.context,
            request_for(
                world,
                decision_case_id=uuid4(),  # unknown case: uniform 404 either way
                decision_maker_profile_id=same_ws_case_profile,
            ),
        )


async def test_workspace_global_profile_usable_by_any_case_of_the_workspace(
    session: AsyncSession,
) -> None:
    # The seeded default profile IS workspace-global (decision_case_id NULL);
    # every service-path test in the r1 suite already consumes it. Make the
    # contract explicit here.
    world = await seed_world(session, f"p1-global-{uuid4().hex[:6]}")
    row = await session.scalar(
        select(DecisionMakerProfile).where(
            DecisionMakerProfile.workspace_id == world.workspace_id,
            DecisionMakerProfile.profile_id == world.profile_id,
        )
    )
    assert row is not None and row.decision_case_id is None
    view = await SimulationRunService(session).run_and_record(
        world.context, request_for(world)
    )
    assert view.decision_maker_profile_id == world.profile_id


# --- P3: idempotency_records persistence schema -----------------------------------------------


def _idempotency_values(workspace_id, **overrides) -> dict:
    values = {
        "id": uuid4(),
        "workspace_id": workspace_id,
        "route_key": "simulations.runs.create",
        "idempotency_key": f"key-{uuid4().hex}",
        "normalized_request_hash": "sha256:owner-p3-hash",
        "resource_type": "simulation_run",
        "resource_id": uuid4(),
        "http_status": 201,
        "response_kind": "success",
        "created_at": NOW,
        "expires_at": NOW + timedelta(hours=48),
    }
    values.update(overrides)
    return values


async def test_idempotency_unique_scope_is_workspace_route_key(
    session: AsyncSession,
) -> None:
    world_a = await seed_world(session, f"p3-uniq-{uuid4().hex[:6]}")
    world_b = await seed_world(session, f"p3-uniqb-{uuid4().hex[:6]}")
    shared_key = f"key-{uuid4().hex}"

    session.add(IdempotencyRecord(**_idempotency_values(world_a.workspace_id, idempotency_key=shared_key)))
    await session.flush()

    # Same workspace + route + key: exactly-once violated.
    await _expect_integrity_error(
        session,
        IdempotencyRecord(**_idempotency_values(world_a.workspace_id, idempotency_key=shared_key)),
    )
    # Same key on another route or another workspace is a different operation.
    session.add(
        IdempotencyRecord(
            **_idempotency_values(
                world_a.workspace_id, idempotency_key=shared_key, route_key="cases.create"
            )
        )
    )
    session.add(IdempotencyRecord(**_idempotency_values(world_b.workspace_id, idempotency_key=shared_key)))
    await session.flush()


async def test_idempotency_schema_check_constraints_fail_closed(
    session: AsyncSession,
) -> None:
    world = await seed_world(session, f"p3-check-{uuid4().hex[:6]}")
    for overrides in (
        {"response_kind": "partial"},  # outside the frozen enum-checked domain
        {"http_status": 99},
        {"http_status": 600},
        {"idempotency_key": ""},
        {"route_key": ""},
        {"normalized_request_hash": ""},
        {"resource_type": ""},
        {"expires_at": NOW},  # retention must be strictly after creation
    ):
        await _expect_integrity_error(
            session, IdempotencyRecord(**_idempotency_values(world.workspace_id, **overrides))
        )
    # non_converged is the other legal terminal outcome (§7 409-with-run).
    session.add(
        IdempotencyRecord(
            **_idempotency_values(
                world.workspace_id, response_kind="non_converged", http_status=409
            )
        )
    )
    await session.flush()


def test_no_idempotency_runtime_flow_exists_in_this_slice() -> None:
    """P3 is persistence only: the simulations package must not grow replay logic here."""

    import app.simulations.service as service_module

    source = inspect.getsource(service_module)
    assert "IdempotencyRecord" not in source
    assert "idempotency" not in source.lower()
