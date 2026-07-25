"""Independent QA battery for CCR-SIM-02A prerequisites P1 + P3 (qa_release).

Complements (never replaces) the owner suite in
``app/simulations/tests/test_sim_02a_profile_idempotency.py``: profile row-PK /
business-identity separation, DB check-constraint negatives, the uniform-404
profile anchor attack matrix with zero-row proof, deep canonical-JSON hash
authority with an INDEPENDENT hashlib re-derivation, pg_catalog shape of the
frozen run->profile FK (convalidated + ON DELETE RESTRICT), service-side
riskTolerance authority end to end, engine-not-run precedence for profile scope
denials, the exact idempotency persistence schema (no runtime flow, no route),
and the accepted-pending P2 engine-hash gap pinned as current behavior.

Owner seeding helpers are loaded by file path (the owner tests directory is
not a package); loading them does not modify any owner file.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import inspect
import json
import sys
from datetime import timedelta
from pathlib import Path
from typing import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio

pytest.importorskip("app.simulations.profile_hash", reason="SIM-02A P1 not delivered")

from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

import app.simulations.engine as engine_module
import app.simulations.repository as repository_module
import app.simulations.service as service_module
from app.db import Base, get_database_url
from app.models import DecisionMakerProfile, IdempotencyRecord, SimulationRun as SimulationRunRow
from app.security.envelope import ApiFailure
from app.simulations.repository import SimulationInputRepository
from app.simulations.service import SimulationRunRequest, SimulationRunService

_OWNER_TESTS = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "simulations"
    / "tests"
    / "test_simulation_repository_service.py"
)
_spec = importlib.util.spec_from_file_location("owner_sim_repo_tests_02a", _OWNER_TESTS)
owner = importlib.util.module_from_spec(_spec)
# dataclasses resolves cls.__module__ through sys.modules during class creation,
# so the module must be registered before exec (stdlib-documented pattern).
sys.modules["owner_sim_repo_tests_02a"] = owner
_spec.loader.exec_module(owner)

seed_world = owner.seed_world
request_for = owner.request_for
scoped_run_count = owner.scoped_run_count
NOW = owner.NOW
SEED_PROFILE_VERSION = owner.SEED_PROFILE_VERSION
SEED_PROFILE_RISK_TOLERANCE = owner.SEED_PROFILE_RISK_TOLERANCE

NOT_FOUND_SIGNATURE = ("CASE_NOT_FOUND", 404)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    async with engine.connect() as connection:
        outer = await connection.begin()
        async_session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield async_session
        finally:
            await async_session.close()
            await outer.rollback()
    await engine.dispose()


async def _expect_integrity_error(session: AsyncSession, row) -> None:
    savepoint = await session.begin_nested()
    with pytest.raises(IntegrityError):
        session.add(row)
        await session.flush()
    await savepoint.rollback()


async def _expect_uniform_404(service, context, request) -> tuple:
    with pytest.raises(ApiFailure) as excinfo:
        await service.run_and_record(context, request)
    return (excinfo.value.code, excinfo.value.http_status)


def _profile_row(world, **overrides) -> DecisionMakerProfile:
    values = {
        "id": uuid4(),
        "workspace_id": world.workspace_id,
        "profile_id": uuid4(),
        "decision_case_id": None,
        "user_id": world.user_id,
        "display_name": "qa direct profile",
        "version": 1,
        "preference_weights": {},
        "risk_tolerance": 0.5,
        "content_hash": f"sha256:qa-{uuid4().hex[:12]}",
    }
    values.update(overrides)
    return DecisionMakerProfile(**values)


# ---------------------------------------------------------------------------
# A: profile identity, immutability shape, DB constraint negatives
# ---------------------------------------------------------------------------


async def test_profile_row_pk_is_storage_only_and_identity_is_append_only(
    session,
) -> None:
    world = await seed_world(session, f"qa02a-id-{uuid4().hex[:6]}")
    repository = SimulationInputRepository(session)
    v1 = await repository.get_decision_maker_profile(
        world.workspace_id, world.profile_id, SEED_PROFILE_VERSION
    )
    assert v1 is not None
    v2 = await repository.insert_decision_maker_profile(
        workspace_id=world.workspace_id,
        profile_id=world.profile_id,
        version=2,
        user_id=world.user_id,
        display_name="qa v2",
        preference_weights={},
        risk_tolerance=0.4,
    )
    # Row PK is storage-only; the stable business id spans versions on new rows.
    assert v1.id != v1.profile_id and v2.id != v2.profile_id
    assert v1.profile_id == v2.profile_id and v1.id != v2.id

    # UNIQUE(workspace_id, profile_id, version): both versions are now taken.
    for version in (SEED_PROFILE_VERSION, 2):
        await _expect_integrity_error(
            session, _profile_row(world, profile_id=world.profile_id, version=version)
        )

    # Repository/service expose no profile UPDATE/DELETE surface (independent scan).
    for owner_class in (SimulationInputRepository, SimulationRunService):
        surface = [
            name
            for name in dir(owner_class)
            if not name.startswith("_") and ("update" in name or "delete" in name)
        ]
        assert surface == [], f"{owner_class.__name__} grew {surface}"


async def test_profile_db_check_and_fk_negatives_fail_closed(session) -> None:
    world = await seed_world(session, f"qa02a-ck-{uuid4().hex[:6]}")
    for overrides in (
        {"version": 0},
        {"version": -1},
        {"risk_tolerance": -0.01},
        {"risk_tolerance": 1.01},
        {"display_name": ""},
        {"content_hash": ""},
        {"workspace_id": uuid4()},  # ghost workspace FK
        {"user_id": uuid4()},  # ghost user FK
        {"decision_case_id": uuid4()},  # ghost case: composite case FK
    ):
        await _expect_integrity_error(session, _profile_row(world, **overrides))
    # risk_tolerance is INCLUSIVE [0, 1]: both boundary values are legal rows.
    for boundary in (0.0, 1.0):
        session.add(_profile_row(world, risk_tolerance=boundary))
        await session.flush()


async def test_profile_anchor_attack_matrix_uniform_404_zero_rows(session) -> None:
    world_a = await seed_world(session, f"qa02a-atk-{uuid4().hex[:6]}")
    world_b = await seed_world(session, f"qa02a-atkb-{uuid4().hex[:6]}")
    repository = SimulationInputRepository(session)
    # Real case-scoped profile in workspace B (bound to B's own case).
    b_case_scoped = uuid4()
    await repository.insert_decision_maker_profile(
        workspace_id=world_b.workspace_id,
        profile_id=b_case_scoped,
        version=1,
        user_id=world_b.user_id,
        display_name="B case-scoped",
        preference_weights={},
        risk_tolerance=0.7,
        decision_case_id=world_b.case_id,
    )
    service = SimulationRunService(session)
    before = await scoped_run_count(session, world_a)
    signatures = {
        await _expect_uniform_404(service, world_a.context, request)
        for request in (
            request_for(world_a, decision_maker_profile_id=uuid4()),
            request_for(world_a, decision_maker_profile_version=99),
            request_for(world_a, decision_maker_profile_version=0),
            request_for(world_a, decision_maker_profile_id=world_b.profile_id),
            request_for(world_a, decision_maker_profile_id=b_case_scoped),
            request_for(
                world_a,
                decision_maker_profile_id=world_b.profile_id,
                decision_maker_profile_version=SEED_PROFILE_VERSION,
            ),
        )
    }
    assert signatures == {NOT_FOUND_SIGNATURE}, (
        f"profile anchor denials must be one indistinguishable signature: {signatures}"
    )
    assert await scoped_run_count(session, world_a) == before


# ---------------------------------------------------------------------------
# B: content hash canonical-JSON authority
# ---------------------------------------------------------------------------


def test_content_hash_is_deep_key_order_independent_and_caller_hash_rejected() -> None:
    from app.simulations.profile_hash import compute_profile_content_hash

    kwargs = dict(
        workspace_id=uuid4(),
        profile_id=uuid4(),
        version=1,
        decision_case_id=None,
        user_id=uuid4(),
        display_name="deep order",
        risk_tolerance=0.5,
    )
    nested_one = {"outer": {"beta": 1.0, "alpha": {"z": 2.0, "a": 3.0}}, "solo": 0.1}
    nested_two = {"solo": 0.1, "outer": {"alpha": {"a": 3.0, "z": 2.0}, "beta": 1.0}}
    assert compute_profile_content_hash(
        preference_weights=nested_one, **kwargs
    ) == compute_profile_content_hash(preference_weights=nested_two, **kwargs), (
        "canonical JSON must sort keys at every nesting level"
    )
    # The only write path accepts no caller hash: not a parameter, and passing
    # one is a TypeError, not a silently trusted value.
    signature = inspect.signature(SimulationInputRepository.insert_decision_maker_profile)
    assert "content_hash" not in signature.parameters
    with pytest.raises(TypeError):
        SimulationInputRepository.insert_decision_maker_profile(
            object(), content_hash="sha256:forged"
        )


async def test_persisted_hash_matches_independent_recomputation(session) -> None:
    world = await seed_world(session, f"qa02a-hash-{uuid4().hex[:6]}")
    row = await session.scalar(
        select(DecisionMakerProfile).where(
            DecisionMakerProfile.workspace_id == world.workspace_id,
            DecisionMakerProfile.profile_id == world.profile_id,
            DecisionMakerProfile.version == SEED_PROFILE_VERSION,
        )
    )
    assert row is not None
    # QA re-derives the documented canonical payload with hashlib/json only —
    # deliberately NOT calling the product helper — so the frozen wire shape
    # (sorted keys, ","/":" separators, UTF-8, sha256: prefix) is pinned.
    payload = {
        "workspaceId": str(row.workspace_id),
        "profileId": str(row.profile_id),
        "version": int(row.version),
        "decisionCaseId": None if row.decision_case_id is None else str(row.decision_case_id),
        "userId": str(row.user_id),
        "displayName": row.display_name,
        "preferenceWeights": dict(row.preference_weights),
        "riskTolerance": float(row.risk_tolerance),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    expected = "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    assert row.content_hash == expected


# ---------------------------------------------------------------------------
# C: frozen run -> profile FK catalog shape + RESTRICT
# ---------------------------------------------------------------------------


async def test_run_profile_fk_catalog_shape_and_delete_restrict(session) -> None:
    catalog = (
        await session.execute(
            text(
                "SELECT c.contype, c.convalidated, c.confdeltype, ref.relname "
                "FROM pg_constraint c JOIN pg_class ref ON ref.oid = c.confrelid "
                "WHERE c.conname = 'fk_simulation_runs_workspace_profile_version'"
            )
        )
    ).all()
    assert len(catalog) == 1
    contype, convalidated, confdeltype, referenced = catalog[0]
    assert bytes(contype) == b"f" and convalidated is True
    assert bytes(confdeltype) == b"r", "profile FK must be ON DELETE RESTRICT"
    assert referenced == "decision_maker_profiles"

    # A referencing run must pin its frozen profile row against deletion.
    world = await seed_world(session, f"qa02a-restrict-{uuid4().hex[:6]}")
    service = SimulationRunService(session)
    await service.run_and_record(world.context, request_for(world))
    savepoint = await session.begin_nested()
    with pytest.raises(IntegrityError):
        await session.execute(
            delete(DecisionMakerProfile).where(
                DecisionMakerProfile.workspace_id == world.workspace_id,
                DecisionMakerProfile.profile_id == world.profile_id,
            )
        )
    await savepoint.rollback()


# ---------------------------------------------------------------------------
# D: service riskTolerance authority
# ---------------------------------------------------------------------------


def test_request_has_no_risk_tolerance_and_construction_rejects_it() -> None:
    field_names = {field.name for field in dataclasses.fields(SimulationRunRequest)}
    assert "risk_tolerance" not in field_names
    assert {"decision_maker_profile_id", "decision_maker_profile_version"} <= field_names
    with pytest.raises(TypeError):
        SimulationRunRequest(risk_tolerance=0.9)  # type: ignore[call-arg]


async def test_risk_tolerance_resolved_from_frozen_profile_end_to_end(session) -> None:
    world = await seed_world(session, f"qa02a-rt-{uuid4().hex[:6]}")
    service = SimulationRunService(session)
    baseline = await service.run_and_record(world.context, request_for(world))
    assert baseline.risk_tolerance == SEED_PROFILE_RISK_TOLERANCE
    row = await session.scalar(
        select(SimulationRunRow).where(
            SimulationRunRow.workspace_id == world.workspace_id,
            SimulationRunRow.id == baseline.id,
        )
    )
    assert row is not None and row.risk_tolerance == SEED_PROFILE_RISK_TOLERANCE
    assert row.decision_maker_profile_id == world.profile_id
    assert row.decision_maker_profile_version == SEED_PROFILE_VERSION

    # Selecting a different frozen version is the ONLY caller-reachable path
    # that moves riskTolerance; view, persisted row and hash all follow.
    await SimulationInputRepository(session).insert_decision_maker_profile(
        workspace_id=world.workspace_id,
        profile_id=world.profile_id,
        version=2,
        user_id=world.user_id,
        display_name="qa rt authority v2",
        preference_weights={},
        risk_tolerance=0.9,
    )
    moved = await service.run_and_record(
        world.context, request_for(world, decision_maker_profile_version=2)
    )
    assert moved.risk_tolerance == 0.9
    moved_row = await session.scalar(
        select(SimulationRunRow).where(
            SimulationRunRow.workspace_id == world.workspace_id,
            SimulationRunRow.id == moved.id,
        )
    )
    assert moved_row is not None and moved_row.risk_tolerance == 0.9
    assert moved.input_hash != baseline.input_hash


async def test_profile_scope_denial_precedes_engine_with_zero_rows(
    session, monkeypatch
) -> None:
    world = await seed_world(session, f"qa02a-pre-{uuid4().hex[:6]}")

    def _engine_must_not_run(*args, **kwargs):
        raise AssertionError("engine must never run for an unresolvable profile ref")

    monkeypatch.setattr(service_module, "run_simulation", _engine_must_not_run)
    service = SimulationRunService(session)
    signature = await _expect_uniform_404(
        service, world.context, request_for(world, decision_maker_profile_id=uuid4())
    )
    assert signature == NOT_FOUND_SIGNATURE
    assert await scoped_run_count(session, world) == 0


# ---------------------------------------------------------------------------
# E: idempotency_records persistence schema only
# ---------------------------------------------------------------------------


def _idempotency_row(workspace_id, **overrides) -> IdempotencyRecord:
    values = {
        "id": uuid4(),
        "workspace_id": workspace_id,
        "route_key": "simulations.runs.create",
        "idempotency_key": f"qa-key-{uuid4().hex}",
        "normalized_request_hash": "sha256:qa-p3",
        "resource_type": "simulation_run",
        "resource_id": uuid4(),
        "http_status": 201,
        "response_kind": "success",
        "created_at": NOW,
        "expires_at": NOW + timedelta(hours=48),
    }
    values.update(overrides)
    return IdempotencyRecord(**values)


async def test_idempotency_exact_schema_scope_and_constraints(session) -> None:
    # Exact persisted field set: nothing more, nothing less.
    assert {c.name for c in Base.metadata.tables["idempotency_records"].columns} == {
        "id",
        "workspace_id",
        "route_key",
        "idempotency_key",
        "normalized_request_hash",
        "resource_type",
        "resource_id",
        "http_status",
        "response_kind",
        "created_at",
        "expires_at",
    }
    # simulation_runs carries NO idempotency columns (Option A stays rejected).
    run_columns = {c.name for c in Base.metadata.tables["simulation_runs"].columns}
    assert not [c for c in run_columns if "idempot" in c]

    world_a = await seed_world(session, f"qa02a-p3a-{uuid4().hex[:6]}")
    world_b = await seed_world(session, f"qa02a-p3b-{uuid4().hex[:6]}")
    shared = f"qa-shared-{uuid4().hex}"
    session.add(_idempotency_row(world_a.workspace_id, idempotency_key=shared))
    await session.flush()
    # Duplicate inside (workspace, route, key): rejected.
    await _expect_integrity_error(
        session, _idempotency_row(world_a.workspace_id, idempotency_key=shared)
    )
    # Same key, different workspace / different route: independent operations.
    session.add(_idempotency_row(world_b.workspace_id, idempotency_key=shared))
    session.add(
        _idempotency_row(
            world_a.workspace_id, idempotency_key=shared, route_key="cases.create"
        )
    )
    # Both contract terminal outcomes persist (201 success / 409 non_converged).
    session.add(
        _idempotency_row(
            world_a.workspace_id, response_kind="non_converged", http_status=409
        )
    )
    await session.flush()

    for overrides in (
        {"response_kind": "replayed"},  # outside the frozen two-value domain
        {"response_kind": ""},
        {"http_status": 99},
        {"http_status": 600},
        {"route_key": ""},
        {"idempotency_key": ""},
        {"normalized_request_hash": ""},
        {"resource_type": ""},
        {"expires_at": NOW},  # expiry must be strictly after creation
    ):
        await _expect_integrity_error(
            session, _idempotency_row(world_a.workspace_id, **overrides)
        )
    # Ghost tenant: the workspace FK itself must reject an unknown workspace.
    await _expect_integrity_error(session, _idempotency_row(uuid4()))
    # A 201-char key fails closed one layer earlier: VARCHAR(200) truncation
    # (DBAPIError) fires before the 1..200 CHECK can even be evaluated.
    savepoint = await session.begin_nested()
    with pytest.raises((DBAPIError, IntegrityError)):
        session.add(_idempotency_row(world_a.workspace_id, idempotency_key="k" * 201))
        await session.flush()
    await savepoint.rollback()

    # Catalog shape: covering index on (workspace_id, expires_at), the unique
    # key, and NO new PostgreSQL enum for response_kind (contract-frozen string).
    index_names = {
        r[0]
        for r in (
            await session.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE tablename = 'idempotency_records'"
                )
            )
        ).all()
    }
    assert "ix_idempotency_records_workspace_expires" in index_names
    assert "uq_idempotency_records_workspace_route_key" in index_names
    enum_count = (
        await session.execute(
            text(
                "SELECT count(*) FROM pg_type WHERE typtype = 'e' AND ("
                "typname LIKE '%idempot%' OR typname LIKE '%response%' "
                "OR typname LIKE '%profile%')"
            )
        )
    ).scalar_one()
    assert enum_count == 0


def test_no_idempotency_runtime_flow_and_public_route_stays_blocked() -> None:
    # P3 is persistence only: no header parsing, replay, conflict, or
    # concurrency flow anywhere in the simulations package.
    for module in (service_module, repository_module):
        source = inspect.getsource(module)
        assert "idempotency" not in source.lower(), module.__name__
    # No route surface exists: no simulations routes module, nothing mounted.
    assert importlib.util.find_spec("app.simulations.routes") is None
    import app.main as main_module
    import app.tenancy.routes as tenancy_routes

    assert "simulation" not in inspect.getsource(main_module).lower()
    assert "simulation" not in inspect.getsource(tenancy_routes).lower()


# ---------------------------------------------------------------------------
# G: P2 (engine hash) is an accepted pending dependency, not regressed
# ---------------------------------------------------------------------------


async def test_p2_engine_hash_gap_is_pinned_pending_dependency(session) -> None:
    # Engine untouched by this slice: version pinned, hash payload unchanged,
    # profile identity/content hash NOT in the hash source yet.
    assert engine_module.ENGINE_VERSION == "sim-engine-1.0.0"
    hash_source = inspect.getsource(engine_module.compute_input_hash)
    assert "profile" not in hash_source.lower()
    assert "content_hash" not in hash_source and "contentHash" not in hash_source

    # Pinned CURRENT behavior (contract §3 gap): two different frozen profiles
    # with the SAME riskTolerance still produce the SAME inputHash. CCR-ENG-02
    # MUST flip this assertion together with the ENGINE_VERSION bump; until
    # then the public POST route stays blocked (ready_for_public_route = NO).
    world = await seed_world(session, f"qa02a-p2-{uuid4().hex[:6]}")
    service = SimulationRunService(session)
    baseline = await service.run_and_record(world.context, request_for(world))
    twin_profile = uuid4()
    await SimulationInputRepository(session).insert_decision_maker_profile(
        workspace_id=world.workspace_id,
        profile_id=twin_profile,
        version=1,
        user_id=world.user_id,
        display_name="same rt different identity",
        preference_weights={"other": 1.0},
        risk_tolerance=SEED_PROFILE_RISK_TOLERANCE,
    )
    twin = await service.run_and_record(
        world.context, request_for(world, decision_maker_profile_id=twin_profile)
    )
    assert twin.decision_maker_profile_id != baseline.decision_maker_profile_id
    assert twin.input_hash == baseline.input_hash
