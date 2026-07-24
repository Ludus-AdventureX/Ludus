"""Independent QA battery for the DB-backed simulation repository/service (qa_release).

Complements (never replaces) the owner suite in
``app/simulations/tests/test_simulation_repository_service.py``: cross-tenant
real-ID attacks, mixed-anchor anti-enumeration, lens provenance lifecycle,
deterministic UUID ordering, JSONB defensive copies, the two Addendum-A1
accepted fail-closed gaps, full-path inputHash sensitivity, zero-zombie-row
failure paths, SQLAlchemy error mapping, and the frozen result view.

Owner seeding helpers are loaded by file path (the owner tests directory is
not a package); loading them does not modify any owner file.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import sys
from pathlib import Path
from typing import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

pytest.importorskip("app.simulations.service", reason="repository/service not delivered")

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

import app.simulations.service as service_module
from app.db import get_database_url
from app.models import (
    AnalysisRun,
    DecisionCase,
    DecisionSubject,
    GraphEdge,
    GraphNode,
    GraphVersion as GraphVersionRow,
    ScenarioVersion as ScenarioVersionRow,
    ScoreDefinition as ScoreDefinitionRow,
    SimulationRun as SimulationRunRow,
    StrategicLensArtifact,
    StrategyVersion as StrategyVersionRow,
)
from app.security.envelope import ApiFailure
from app.simulations import domain
from app.simulations.assembly import (
    assemble_graph,
    assemble_scenario,
    assemble_score_definition,
    assemble_strategy,
)
from app.simulations.domain import SimulationAuthorizationError
from app.simulations.errors import (
    FormalAuthorizationError,
    ScoreDefinitionReferenceError,
    SimulationPersistenceError,
    StrategyOverrideError,
)
from app.simulations.repository import SimulationInputRepository
from app.simulations.service import SimulationRunService, SimulationRunView
from app.types import (
    EdgePolarity,
    FactorControllability,
    FactorEvidenceStatus,
    FormalAnalysisLevel,
    GraphVersionStatus,
    LensProducerRole,
    SimulationMode,
    StrategicLensArtifactStatus,
    StrategicLensType,
)

_OWNER_TESTS = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "simulations"
    / "tests"
    / "test_simulation_repository_service.py"
)
_spec = importlib.util.spec_from_file_location("owner_sim_repo_tests", _OWNER_TESTS)
owner = importlib.util.module_from_spec(_spec)
# dataclasses resolves cls.__module__ through sys.modules during class creation,
# so the module must be registered before exec (stdlib-documented pattern).
sys.modules["owner_sim_repo_tests"] = owner
_spec.loader.exec_module(owner)

seed_world = owner.seed_world
request_for = owner.request_for
scoped_run_count = owner.scoped_run_count
NOW = owner.NOW

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


def _signature(exc: ApiFailure) -> tuple:
    return (exc.code, exc.http_status)


async def _expect_uniform_404(service, context, request) -> tuple:
    with pytest.raises(ApiFailure) as excinfo:
        await service.run_and_record(context, request)
    return _signature(excinfo.value)


# ---------------------------------------------------------------------------
# 四: cross-tenant real IDs, ghosts, and mixed anchors
# ---------------------------------------------------------------------------


async def test_cross_tenant_real_ids_and_ghosts_are_uniform_404(session) -> None:
    world_a = await seed_world(session, f"qa-a-{uuid4().hex[:6]}")
    world_b = await seed_world(session, f"qa-b-{uuid4().hex[:6]}")
    service = SimulationRunService(session)

    signatures = set()
    # real-but-foreign anchors, one field at a time
    for overrides in (
        {"decision_case_id": world_b.case_id},
        {"graph_version_id": world_b.graph_version_id},
        {"strategy_version_id": world_b.strategy_version_id},
        {"scenario_version_id": world_b.scenario_version_id},
        {"score_definition_id": world_b.score_definition_id},
        # ghosts
        {"decision_case_id": uuid4()},
        {"graph_version_id": uuid4()},
        {"strategy_version_id": uuid4()},
        {"scenario_version_id": uuid4()},
        {"score_definition_id": uuid4()},
        # mixed valid anchors across tenants (graph A, strategy B, scenario A, score B)
        {
            "strategy_version_id": world_b.strategy_version_id,
            "score_definition_id": world_b.score_definition_id,
        },
    ):
        signatures.add(
            await _expect_uniform_404(
                service, world_a.context, request_for(world_a, **overrides)
            )
        )
    assert signatures == {NOT_FOUND_SIGNATURE}, (
        "foreign real IDs, ghosts and mixed anchors must be indistinguishable"
    )
    assert await scoped_run_count(session, world_a) == 0
    assert await scoped_run_count(session, world_b) == 0


async def test_same_workspace_other_case_anchor_is_uniform_404(session) -> None:
    world = await seed_world(session, f"qa-case-{uuid4().hex[:6]}")
    other_subject, other_case = uuid4(), uuid4()
    session.add(
        DecisionSubject(
            id=other_subject,
            workspace_id=world.workspace_id,
            name="other subject",
            slug=f"other-{uuid4().hex[:8]}",
        )
    )
    await session.flush()
    session.add(
        DecisionCase(
            decision_case_id=other_case,
            workspace_id=world.workspace_id,
            decision_subject_id=other_subject,
            title="other case",
            decision_question="different question?",
            option_ids=[str(uuid4())],
        )
    )
    await session.flush()

    service = SimulationRunService(session)
    signature = await _expect_uniform_404(
        service, world.context, request_for(world, decision_case_id=other_case)
    )
    assert signature == NOT_FOUND_SIGNATURE, (
        "versions anchored to another case in the same workspace stay hidden"
    )
    assert await scoped_run_count(session, world) == 0


# ---------------------------------------------------------------------------
# 五: scenario source lens provenance
# ---------------------------------------------------------------------------


async def _lens_row(world, *, status, lens_type, case_id=None, run_id=None) -> UUID:
    lens_id = uuid4()
    return lens_id, StrategicLensArtifact(
        strategic_lens_artifact_id=lens_id,
        workspace_id=world.workspace_id,
        decision_case_id=case_id or world.case_id,
        analysis_run_id=run_id or world.analysis_run_id,
        charter_id=world.charter_id,
        lens_type=lens_type,
        producer_role=LensProducerRole.SYNTHESIS,
        status=status,
        method_id="hardtech-market-direction",
        method_version="1.1.0",
        method_content_hash="sha256:method",
        prompt_version="1",
        schema_version="1",
        content_hash=f"sha256:lens-{lens_id.hex[:10]}",
        validation_accepted_at=(
            NOW if status == StrategicLensArtifactStatus.READY else None
        ),
    )


async def _scenario_pointing_at(session, world, lens_id) -> UUID:
    scenario_id = uuid4()
    session.add(
        ScenarioVersionRow(
            id=scenario_id,
            workspace_id=world.workspace_id,
            graph_id=world.graph_id,
            decision_case_id=world.case_id,
            source_lens_artifact_id=lens_id,
            source_strategic_scenario_id="qa_frame",
            scenario_id=uuid4(),
            version=2,
            name="qa-lens-probe",
            description="lens provenance probe",
            default_edge_multiplier=1.0,
            edge_multipliers={},
            node_shifts={},
            strategy_survives=True,
            early_warning_signals=[],
            damping=0.85,
        )
    )
    await session.flush()
    return scenario_id


async def test_lens_provenance_wrong_status_type_or_case_is_uniform_404(session) -> None:
    world = await seed_world(session, f"qa-lens-{uuid4().hex[:6]}")
    draft_id, draft_row = await _lens_row(
        world,
        status=StrategicLensArtifactStatus.DRAFT,
        lens_type=StrategicLensType.SCENARIO_PLANNING,
    )
    rejected_id, rejected_row = await _lens_row(
        world,
        status=StrategicLensArtifactStatus.REJECTED,
        lens_type=StrategicLensType.SCENARIO_PLANNING,
    )
    wrong_type_id, wrong_type_row = await _lens_row(
        world,
        status=StrategicLensArtifactStatus.READY,
        lens_type=StrategicLensType.PORTER_FIVE_FORCES,
    )
    # a real ready scenario_planning lens anchored to ANOTHER case in the same
    # workspace: insertable (composite FK is workspace-scoped), must still 404
    other_subject, other_case = uuid4(), uuid4()
    session.add(
        DecisionSubject(
            id=other_subject,
            workspace_id=world.workspace_id,
            name="lens sibling subject",
            slug=f"lens-sib-{uuid4().hex[:8]}",
        )
    )
    await session.flush()
    session.add(
        DecisionCase(
            decision_case_id=other_case,
            workspace_id=world.workspace_id,
            decision_subject_id=other_subject,
            title="lens sibling case",
            decision_question="sibling?",
            option_ids=[str(uuid4())],
        )
    )
    await session.flush()
    other_run = uuid4()
    session.add(
        AnalysisRun(
            analysis_run_id=other_run,
            workspace_id=world.workspace_id,
            decision_case_id=other_case,
            charter_id=uuid4(),
            charter_version=1,
            run_manifest_id=uuid4(),
            run_manifest_hash="sha256:manifest",
            cynefin_gate_result_id=uuid4(),
            analysis_level=FormalAnalysisLevel.FULL,
            case_version=1,
            case_snapshot_hash="sha256:case",
            dossier_snapshot_version=1,
            dossier_snapshot_hash="sha256:dossier",
            method_id="hardtech-market-direction",
            method_version="1.1.0",
            method_content_hash="sha256:method",
            idempotency_key=f"idem-lens-sib-{uuid4().hex[:8]}",
        )
    )
    await session.flush()
    other_case_lens_id, other_case_lens_row = await _lens_row(
        world,
        status=StrategicLensArtifactStatus.READY,
        lens_type=StrategicLensType.SCENARIO_PLANNING,
        case_id=other_case,
        run_id=other_run,
    )
    session.add_all([draft_row, rejected_row, wrong_type_row, other_case_lens_row])
    await session.flush()

    service = SimulationRunService(session)
    signatures = set()
    for lens_id in (draft_id, rejected_id, wrong_type_id, other_case_lens_id):
        scenario_id = await _scenario_pointing_at(session, world, lens_id)
        signatures.add(
            await _expect_uniform_404(
                service,
                world.context,
                request_for(world, scenario_version_id=scenario_id),
            )
        )
    assert signatures == {NOT_FOUND_SIGNATURE}, (
        "draft/rejected/wrong-type/other-case lens sources must be indistinguishable"
    )
    assert await scoped_run_count(session, world) == 0
    # the legal ready scenario_planning source still executes
    view = await service.run_and_record(world.context, request_for(world))
    assert view.input_hash.startswith("sha256:")


# ---------------------------------------------------------------------------
# 六 A/B: UUID ordering determinism and JSONB defensive copies
# ---------------------------------------------------------------------------


async def test_repository_orders_by_uuid_and_assembly_ignores_input_order(session) -> None:
    world = await seed_world(session, f"qa-order-{uuid4().hex[:6]}")
    repository = SimulationInputRepository(session)
    nodes = await repository.get_graph_nodes(world.workspace_id, world.graph_version_id)
    edges = await repository.get_graph_edges(world.workspace_id, world.graph_version_id)
    assert [str(row.id) for row in nodes] == sorted(str(row.id) for row in nodes)
    assert [str(row.id) for row in edges] == sorted(str(row.id) for row in edges)

    version_row = await repository.get_graph_version(
        world.workspace_id, world.case_id, world.graph_version_id
    )
    forward = assemble_graph(version_row, nodes, edges)
    shuffled = assemble_graph(version_row, list(reversed(nodes)), list(reversed(edges)))
    assert forward == shuffled, "assembly must not depend on row input order"
    assert [node.id for node in forward.nodes] == sorted(node.id for node in forward.nodes)


async def test_jsonb_defensive_copies_protect_assembled_objects(session) -> None:
    world = await seed_world(session, f"qa-copy-{uuid4().hex[:6]}")
    repository = SimulationInputRepository(session)
    version_row = await repository.get_graph_version(
        world.workspace_id, world.case_id, world.graph_version_id
    )
    nodes = await repository.get_graph_nodes(world.workspace_id, world.graph_version_id)
    edges = await repository.get_graph_edges(world.workspace_id, world.graph_version_id)
    graph = assemble_graph(version_row, nodes, edges)
    case = await repository.get_case(world.workspace_id, world.case_id)

    strategy_row = await repository.get_strategy_version(
        world.workspace_id, world.case_id, world.strategy_version_id
    )
    strategy_row.node_overrides = {str(world.lever_id): 60.0}
    scenario_row = await repository.get_scenario_version(
        world.workspace_id, world.case_id, world.scenario_version_id
    )
    scenario_row.node_shifts = {str(world.driver_id): 0.2}
    scenario_row.edge_multipliers = {str(world.edge_ids["e1"]): 1.1}
    score_row = await repository.get_score_definition(
        world.workspace_id, world.case_id, world.score_definition_id
    )

    strategy = assemble_strategy(strategy_row, graph)
    scenario = assemble_scenario(scenario_row, graph)
    score = assemble_score_definition(score_row, graph, case)

    # consumer/fixture-side mutation of the source JSONB objects
    strategy_row.node_overrides[str(world.lever_id)] = 999.0
    strategy_row.node_overrides["injected"] = 1.0
    scenario_row.node_shifts[str(world.driver_id)] = -0.9
    scenario_row.edge_multipliers[str(world.edge_ids["e1"])] = 0.0
    score_row.option_outcome_mappings.append({"optionId": "evil"})
    score_row.risk_weights.append({"optionId": "evil"})
    score_row.constraint_rules.append({"optionId": "evil"})

    assert strategy.node_overrides == {str(world.lever_id): 60.0}
    assert scenario.node_shifts == {str(world.driver_id): 0.2}
    assert scenario.edge_multipliers == {str(world.edge_ids["e1"]): 1.1}
    assert len(score.option_outcomes) == 2
    assert len(score.risk_weights) == 0
    assert len(score.constraint_rules) == 0


# ---------------------------------------------------------------------------
# Addendum A1 accepted fail-closed gaps (must PASS, engine must not run)
# ---------------------------------------------------------------------------


async def test_equality_operator_fails_closed_before_engine_and_db(
    session, monkeypatch
) -> None:
    world = await seed_world(session, f"qa-eq-{uuid4().hex[:6]}")
    score_id = uuid4()
    session.add(
        ScoreDefinitionRow(
            id=score_id,
            workspace_id=world.workspace_id,
            graph_id=world.graph_id,
            decision_case_id=world.case_id,
            version="2",
            option_outcome_mappings=[
                {
                    "optionId": world.option_a,
                    "outcomeNodeId": str(world.outcome_a_id),
                    "goalId": "goal",
                    "weight": 1.0,
                }
            ],
            risk_weights=[],
            constraint_rules=[
                {
                    "optionId": world.option_a,
                    "constraintNodeId": str(world.outcome_a_id),
                    "operator": "=",
                    "threshold": 0.5,
                    "penalty": 1.0,
                }
            ],
            content_hash="sha256:score-eq",
        )
    )
    await session.flush()

    def _engine_must_not_run(*args, **kwargs):
        raise AssertionError("engine executed despite unsupported '=' operator")

    monkeypatch.setattr(service_module, "run_simulation", _engine_must_not_run)
    service = SimulationRunService(session)
    with pytest.raises(ScoreDefinitionReferenceError) as excinfo:
        await service.run_and_record(
            world.context, request_for(world, score_definition_id=score_id)
        )
    assert excinfo.value.code == "score_constraint_operator_unsupported"
    assert "'<='" not in str(excinfo.value), "'=' must never degrade into '<='"
    assert await scoped_run_count(session, world) == 0


async def test_enabled_edge_ids_fail_closed_before_engine_and_db(
    session, monkeypatch
) -> None:
    world = await seed_world(session, f"qa-gate-{uuid4().hex[:6]}")
    strategy_id = uuid4()
    session.add(
        StrategyVersionRow(
            id=strategy_id,
            workspace_id=world.workspace_id,
            graph_id=world.graph_id,
            decision_case_id=world.case_id,
            version=2,
            option_id=UUID(world.option_a),
            node_overrides={},
            enabled_edge_ids=[str(world.edge_ids["e1"])],
        )
    )
    await session.flush()

    def _engine_must_not_run(*args, **kwargs):
        raise AssertionError("engine executed despite enabledEdgeIds gating")

    monkeypatch.setattr(service_module, "run_simulation", _engine_must_not_run)
    service = SimulationRunService(session)
    with pytest.raises(StrategyOverrideError) as excinfo:
        await service.run_and_record(
            world.context, request_for(world, strategy_version_id=strategy_id)
        )
    assert excinfo.value.code == "strategy_edge_gating_unsupported"
    assert await scoped_run_count(session, world) == 0


# ---------------------------------------------------------------------------
# 八: inputHash over the full persisted path
# ---------------------------------------------------------------------------


async def test_persisted_graph_v2_changes_input_hash_via_full_service_path(
    session,
) -> None:
    world = await seed_world(session, f"qa-hash-{uuid4().hex[:6]}")
    service = SimulationRunService(session)
    first = await service.run_and_record(world.context, request_for(world))
    again = await service.run_and_record(world.context, request_for(world))
    assert first.input_hash == again.input_hash
    assert first.node_results == again.node_results
    assert first.option_scores == again.option_scores
    assert first.steps == again.steps
    assert first.convergence_status == again.convergence_status

    # real persisted v2 with changed content, exercised through the service
    version2 = uuid4()
    session.add(
        GraphVersionRow(
            id=version2,
            workspace_id=world.workspace_id,
            graph_id=world.graph_id,
            decision_case_id=world.case_id,
            case_version=1,
            source_report_artifact_id=uuid4(),
            version=2,
            status=GraphVersionStatus.CONFIRMED,
            title="qa graph v2",
            content_hash="sha256:graph-v2",
            created_by=world.user_id,
            confirmed_at=NOW,
        )
    )
    await session.flush()
    node_map: dict[UUID, UUID] = {}
    repository = SimulationInputRepository(session)
    for row in await repository.get_graph_nodes(
        world.workspace_id, world.graph_version_id
    ):
        clone_id = uuid4()
        node_map[row.id] = clone_id
        session.add(
            owner._node_row(
                world.workspace_id,
                version2,
                clone_id,
                row.label,
                row.node_type,
                float(row.baseline_value),
                float(row.min_value),
                float(row.max_value),
                "confirmed",
            )
        )
    await session.flush()
    for row in await repository.get_graph_edges(
        world.workspace_id, world.graph_version_id
    ):
        session.add(
            owner._edge_row(
                world.workspace_id,
                version2,
                uuid4(),
                node_map[row.source_node_id],
                node_map[row.target_node_id],
                row.polarity,
                # one strength deliberately changed: 0.8 -> 0.7 on the first edge
                0.7 if float(row.strength) == 0.8 else float(row.strength),
                "confirmed",
            )
        )
    await session.flush()
    # v2-scoped strategy/scenario (empty overrides/shifts) remain valid anchors
    # because they carry no node references; the score definition DOES reference
    # node UUIDs, and under Addendum A1 UUID identity the v2 clones have new ids,
    # so a v2-scoped score definition is created for the full service path.
    score_v2 = uuid4()
    session.add(
        ScoreDefinitionRow(
            id=score_v2,
            workspace_id=world.workspace_id,
            graph_id=world.graph_id,
            decision_case_id=world.case_id,
            version="2",
            option_outcome_mappings=[
                {
                    "optionId": world.option_a,
                    "outcomeNodeId": str(node_map[world.outcome_a_id]),
                    "goalId": "goal_traction",
                    "weight": 1.0,
                },
                {
                    "optionId": world.option_b,
                    "outcomeNodeId": str(node_map[world.outcome_b_id]),
                    "goalId": "goal_traction",
                    "weight": 1.0,
                },
            ],
            risk_weights=[],
            constraint_rules=[],
            content_hash="sha256:score",  # identical hash: graph change alone must move the inputHash
        )
    )
    await session.flush()
    v2_view = await service.run_and_record(
        world.context,
        request_for(world, graph_version_id=version2, score_definition_id=score_v2),
    )
    assert v2_view.input_hash != first.input_hash, (
        "a persisted v2 graph with changed content must change the inputHash"
    )
    assert await scoped_run_count(session, world) == 3


async def test_run_level_parameters_each_change_input_hash(session) -> None:
    world = await seed_world(session, f"qa-params-{uuid4().hex[:6]}")
    service = SimulationRunService(session)
    baseline = await service.run_and_record(world.context, request_for(world))
    hashes = {baseline.input_hash}

    # SIM-02A P1: riskTolerance is no longer a request field. The only way a
    # caller moves it is by selecting a different frozen profile version; the
    # server-resolved value is engine input, so the hash must move through the
    # FULL service path.
    await SimulationInputRepository(session).insert_decision_maker_profile(
        workspace_id=world.workspace_id,
        profile_id=world.profile_id,
        version=2,
        user_id=world.user_id,
        display_name="qa rt v2",
        preference_weights={"traction": 0.7, "cash": 0.3},
        risk_tolerance=0.61,
    )
    for overrides in (
        {"decision_maker_profile_version": 2},  # frozen riskTolerance 0.5 -> 0.61
        {"epsilon": 0.002},
        {"max_steps": 17},
    ):
        view = await service.run_and_record(
            world.context, request_for(world, **overrides)
        )
        assert view.input_hash not in hashes, f"{overrides} must change the inputHash"
        hashes.add(view.input_hash)

    # SIM-02A P1: ghost profile version / ghost profile id are no longer silent
    # metadata - the frozen reference must resolve, so both collapse into the
    # uniform 404 with zero persisted rows for the failed attempts.
    persisted_before = await scoped_run_count(session, world)
    signatures = set()
    for overrides in (
        {"decision_maker_profile_version": 99},
        {"decision_maker_profile_id": uuid4()},
    ):
        signatures.add(
            await _expect_uniform_404(
                service, world.context, request_for(world, **overrides)
            )
        )
    assert signatures == {NOT_FOUND_SIGNATURE}
    assert await scoped_run_count(session, world) == persisted_before


# ---------------------------------------------------------------------------
# 九: compute-then-insert lifecycle, zero zombie rows, error mapping
# ---------------------------------------------------------------------------


async def test_sensitivity_failure_leaves_no_zombie_rows(session, monkeypatch) -> None:
    world = await seed_world(session, f"qa-sens-{uuid4().hex[:6]}")

    def _broken_sensitivity(*args, **kwargs):
        raise RuntimeError("forced sensitivity failure")

    monkeypatch.setattr(service_module, "analyze_sensitivity", _broken_sensitivity)
    service = SimulationRunService(session)
    with pytest.raises(RuntimeError):
        await service.run_and_record(
            world.context, request_for(world, include_sensitivity=True)
        )
    assert await scoped_run_count(session, world) == 0


async def test_wire_self_check_failure_leaves_no_zombie_rows(
    session, monkeypatch
) -> None:
    world = await seed_world(session, f"qa-wire-{uuid4().hex[:6]}")

    class _BrokenWire:
        @staticmethod
        def model_validate(payload):
            raise ValueError("forced canonical self-check failure")

    monkeypatch.setattr(service_module, "SimulationRunWire", _BrokenWire)
    service = SimulationRunService(session)
    with pytest.raises(ValueError):
        await service.run_and_record(world.context, request_for(world))
    assert await scoped_run_count(session, world) == 0


async def test_insert_failure_maps_rolls_back_and_session_survives(
    session, monkeypatch
) -> None:
    world = await seed_world(session, f"qa-persist-{uuid4().hex[:6]}")

    async def _broken_insert(self, row):
        raise SQLAlchemyError("simulated infrastructure failure")

    monkeypatch.setattr(
        SimulationInputRepository, "insert_simulation_run", _broken_insert
    )
    service = SimulationRunService(session)
    with pytest.raises(SimulationPersistenceError) as excinfo:
        await service.run_and_record(world.context, request_for(world))
    assert not isinstance(excinfo.value, SQLAlchemyError)
    assert excinfo.value.code == "simulation_persistence_failed"
    rendered = str(excinfo.value)
    assert "asyncpg" not in rendered and "IntegrityError" not in rendered

    # session/connection must remain usable after rollback
    assert await session.scalar(select(func.count()).select_from(SimulationRunRow)) >= 0
    assert await scoped_run_count(session, world) == 0


# ---------------------------------------------------------------------------
# 三 D / 七 / 九: enum authority, formal double gate, frozen view
# ---------------------------------------------------------------------------


def test_enum_authority_is_app_types_with_engine_internal_exceptions() -> None:
    assert domain.Controllability is FactorControllability
    assert domain.EvidenceStatus is FactorEvidenceStatus
    assert domain.EdgePolarity is EdgePolarity
    assert domain.GraphVersionStatus is GraphVersionStatus
    for engine_internal in (domain.ElementStatus, domain.Normalization, domain.Comparison):
        assert engine_internal.__module__ == "app.simulations.domain"
    assert {member.value for member in domain.Comparison} == {">", ">=", "<", "<="}
    # registered envelope mapping for the future route layer
    assert FormalAuthorizationError.code == "formal_authorization_rejected"


async def test_formal_double_gate_rejects_even_if_service_precheck_is_bypassed(
    session, monkeypatch
) -> None:
    world = await seed_world(
        session, f"qa-formal-{uuid4().hex[:6]}", graph_status=GraphVersionStatus.DRAFT
    )
    service = SimulationRunService(session)
    with pytest.raises(SimulationAuthorizationError):
        await service.run_and_record(world.context, request_for(world))
    assert await scoped_run_count(session, world) == 0

    # bypass the service-level precheck: the engine's internal gate must still hold
    monkeypatch.setattr(service_module, "assert_authorization", lambda *a, **k: None)
    with pytest.raises(SimulationAuthorizationError):
        await service.run_and_record(world.context, request_for(world))
    assert await scoped_run_count(session, world) == 0


async def test_experimental_run_is_side_effect_free_and_view_is_frozen(session) -> None:
    world = await seed_world(
        session, f"qa-exp-{uuid4().hex[:6]}", graph_status=GraphVersionStatus.DRAFT
    )
    service = SimulationRunService(session)
    view = await service.run_and_record(
        world.context, request_for(world, simulation_mode=SimulationMode.EXPERIMENTAL)
    )
    assert view.simulation_mode is SimulationMode.EXPERIMENTAL
    assert await scoped_run_count(session, world) == 1

    # frozen projection, not an ORM row
    assert isinstance(view, SimulationRunView)
    assert not isinstance(view, SimulationRunRow)
    assert dataclasses.is_dataclass(view)
    with pytest.raises(dataclasses.FrozenInstanceError):
        view.input_hash = "sha256:tampered"  # type: ignore[misc]
    assert isinstance(view.option_scores, tuple)
    assert isinstance(view.top_drivers, tuple)
    assert isinstance(view.origin_modes, tuple)

    # frozen inputs untouched: graph stays draft, case options unchanged,
    # no frozen-input rows were updated or deleted
    repository = SimulationInputRepository(session)
    version_row = await repository.get_graph_version(
        world.workspace_id, world.case_id, world.graph_version_id
    )
    assert version_row.status == GraphVersionStatus.DRAFT
    assert version_row.confirmed_at is None
    case = await repository.get_case(world.workspace_id, world.case_id)
    assert set(case.option_ids) == {world.option_a, world.option_b}
    for model, expected in (
        (GraphNode, 4),
        (GraphEdge, 3),
        (StrategyVersionRow, 1),
        (ScenarioVersionRow, 1),
        (ScoreDefinitionRow, 1),
        (StrategicLensArtifact, 1),
    ):
        count = await session.scalar(
            select(func.count())
            .select_from(model)
            .where(model.workspace_id == world.workspace_id)
        )
        assert count == expected, f"{model.__name__} rows must be untouched"
