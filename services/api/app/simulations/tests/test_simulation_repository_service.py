"""Owner verification for the DB-backed simulation repository/service.

Run (disposable clean PostgreSQL + already-installed venv; no new environment):

    $env:DATABASE_URL = "postgresql+asyncpg://<user>:<password>@localhost:<port>/decision_lab"
    <mainvenv>python -m pytest app/simulations/tests -q

Each test runs inside an outer connection transaction that is rolled back on teardown;
the service's ``commit()`` joins via a savepoint, so the database stays clean. Counts are
always scoped to the seeded workspace/case (never unscoped absolute table counts).
"""

from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.db import get_database_url
from app.models import (
    AnalysisRun,
    CausalGraph,
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
    User,
    Workspace,
    WorkspaceMembership,
)
from app.security.envelope import ApiFailure
from app.simulations.assembly import assemble_graph
from app.simulations.domain import SimulationAuthorizationError
from app.simulations.engine import compute_input_hash
from app.simulations.errors import (
    GraphScopeMismatchError,
    ScenarioParameterError,
    ScoreDefinitionReferenceError,
    StrategyOverrideError,
)
from app.simulations.repository import SimulationInputRepository
from app.simulations.service import SimulationRunRequest, SimulationRunService
from app.tenancy.context import ALL_CAPABILITIES, WorkspaceContext
from app.types import (
    EdgePolarity,
    FactorAuthorship,
    FactorControllability,
    FactorEvidenceStatus,
    FormalAnalysisLevel,
    GraphVersionStatus,
    LensProducerRole,
    SimulationConvergenceStatus,
    SimulationMode,
    StrategicLensArtifactStatus,
    StrategicLensType,
    WorkspaceRole,
)

NOW = datetime(2026, 7, 25, 8, 0, 0, tzinfo=timezone.utc)

# Frozen seeded profile facts (CCR-SIM-02A §2): the seeded workspace-global
# profile v1 carries this riskTolerance; the service resolves it server-side.
SEED_PROFILE_VERSION = 1
SEED_PROFILE_RISK_TOLERANCE = 0.5


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


@dataclass(slots=True)
class World:
    """Ids of one fully seeded tenant scope."""

    context: WorkspaceContext
    workspace_id: UUID
    user_id: UUID
    subject_id: UUID
    case_id: UUID
    analysis_run_id: UUID
    charter_id: UUID
    lens_ready_id: UUID
    graph_id: UUID
    graph_version_id: UUID
    driver_id: UUID
    lever_id: UUID
    outcome_a_id: UUID
    outcome_b_id: UUID
    edge_ids: dict[str, UUID]
    strategy_version_id: UUID
    scenario_version_id: UUID
    score_definition_id: UUID
    profile_id: UUID
    option_a: str = ""
    option_b: str = ""
    extras: dict[str, UUID] = field(default_factory=dict)


def _node_row(
    world_ws: UUID,
    version_id: UUID,
    node_id: UUID,
    label: str,
    node_type: str,
    baseline: float,
    minimum: float,
    maximum: float,
    review_status: str,
    *,
    editable: bool = True,
) -> GraphNode:
    return GraphNode(
        id=node_id,
        workspace_id=world_ws,
        graph_version_id=version_id,
        label=label,
        node_type=node_type,
        baseline_value=baseline,
        current_value=baseline,
        min_value=minimum,
        max_value=maximum,
        unit="index",
        normalization="linear",
        sensitivity_step=None,
        controllability=FactorControllability.CONTROLLABLE,
        authorship=FactorAuthorship.GENERATED,
        evidence_status=FactorEvidenceStatus.CONDITIONAL,
        evidence_quality_score=0.6,
        evidence_ids=["ev_seed"],
        assumption_ids=[],
        rationale="seeded node",
        review_status=review_status,
        editable=editable,
    )


def _edge_row(
    world_ws: UUID,
    version_id: UUID,
    edge_id: UUID,
    source: UUID,
    target: UUID,
    polarity: EdgePolarity,
    strength: float,
    review_status: str,
) -> GraphEdge:
    return GraphEdge(
        id=edge_id,
        workspace_id=world_ws,
        graph_version_id=version_id,
        source_node_id=source,
        target_node_id=target,
        polarity=polarity,
        strength=strength,
        delay_steps=0,
        authorship=FactorAuthorship.GENERATED,
        evidence_status=FactorEvidenceStatus.CONDITIONAL,
        relationship_quality_score=0.6,
        rationale="seeded edge",
        claim_ids=["claim_seed"],
        evidence_ids=["ev_seed"],
        assumption_ids=[],
        review_status=review_status,
    )


async def seed_world(
    session: AsyncSession,
    slug: str,
    *,
    graph_status: GraphVersionStatus = GraphVersionStatus.CONFIRMED,
) -> World:
    ws_id, user_id, subject_id, case_id = uuid4(), uuid4(), uuid4(), uuid4()
    run_id, charter_id, lens_ready_id = uuid4(), uuid4(), uuid4()
    graph_id, version_id = uuid4(), uuid4()
    driver_id, lever_id, outcome_a_id, outcome_b_id = uuid4(), uuid4(), uuid4(), uuid4()
    e1, e2, e3 = uuid4(), uuid4(), uuid4()
    strategy_id, scenario_id_row, score_id = uuid4(), uuid4(), uuid4()
    option_a, option_b = str(uuid4()), str(uuid4())
    review = "confirmed" if graph_status == GraphVersionStatus.CONFIRMED else "draft"

    session.add(User(id=user_id, email=f"owner-{slug}@example.test", password_hash="x"))
    await session.flush()
    session.add(Workspace(id=ws_id, name=f"ws-{slug}", created_by_user_id=user_id))
    await session.flush()
    session.add(
        WorkspaceMembership(
            id=uuid4(), workspace_id=ws_id, user_id=user_id, role=WorkspaceRole.OWNER
        )
    )
    session.add(
        DecisionSubject(id=subject_id, workspace_id=ws_id, name=f"subject-{slug}", slug=slug)
    )
    await session.flush()
    session.add(
        DecisionCase(
            decision_case_id=case_id,
            workspace_id=ws_id,
            decision_subject_id=subject_id,
            title=f"case-{slug}",
            decision_question="rescue or research?",
            option_ids=[option_a, option_b],
        )
    )
    await session.flush()
    session.add(
        AnalysisRun(
            analysis_run_id=run_id,
            workspace_id=ws_id,
            decision_case_id=case_id,
            charter_id=charter_id,
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
            idempotency_key=f"idem-{slug}",
        )
    )
    await session.flush()
    session.add(
        StrategicLensArtifact(
            strategic_lens_artifact_id=lens_ready_id,
            workspace_id=ws_id,
            decision_case_id=case_id,
            analysis_run_id=run_id,
            charter_id=charter_id,
            lens_type=StrategicLensType.SCENARIO_PLANNING,
            producer_role=LensProducerRole.SYNTHESIS,
            status=StrategicLensArtifactStatus.READY,
            method_id="hardtech-market-direction",
            method_version="1.1.0",
            method_content_hash="sha256:method",
            prompt_version="1",
            schema_version="1",
            content_hash="sha256:lens",
            validation_accepted_at=NOW,
        )
    )
    await session.flush()
    session.add(
        CausalGraph(
            id=graph_id,
            workspace_id=ws_id,
            decision_case_id=case_id,
            report_artifact_id=uuid4(),
            title=f"graph-{slug}",
        )
    )
    await session.flush()
    session.add(
        GraphVersionRow(
            id=version_id,
            workspace_id=ws_id,
            graph_id=graph_id,
            decision_case_id=case_id,
            case_version=1,
            source_report_artifact_id=uuid4(),
            version=1,
            status=graph_status,
            title=f"graph-{slug}-v1",
            content_hash="sha256:graph",
            created_by=user_id,
            confirmed_at=NOW if graph_status == GraphVersionStatus.CONFIRMED else None,
        )
    )
    await session.flush()

    node_rows = [
        _node_row(ws_id, version_id, driver_id, "driver", "external", 0.5, 0.0, 1.0, review),
        _node_row(ws_id, version_id, lever_id, "lever", "lever", 50.0, 0.0, 100.0, review),
        _node_row(ws_id, version_id, outcome_a_id, "outcome-a", "outcome", 0.6, 0.0, 1.0, review),
        _node_row(ws_id, version_id, outcome_b_id, "outcome-b", "outcome", 0.4, 0.0, 1.0, review),
    ]
    # Deliberately insert in reverse id order so DB insertion order can never be
    # mistaken for the deterministic assembly order.
    for row in sorted(node_rows, key=lambda item: str(item.id), reverse=True):
        session.add(row)
    await session.flush()
    edge_rows = [
        _edge_row(ws_id, version_id, e1, driver_id, outcome_a_id, EdgePolarity.POSITIVE, 0.8, review),
        _edge_row(ws_id, version_id, e2, driver_id, outcome_b_id, EdgePolarity.NEGATIVE, 0.5, review),
        _edge_row(ws_id, version_id, e3, lever_id, outcome_a_id, EdgePolarity.POSITIVE, 0.3, review),
    ]
    for row in sorted(edge_rows, key=lambda item: str(item.id), reverse=True):
        session.add(row)
    await session.flush()

    session.add(
        StrategyVersionRow(
            id=strategy_id,
            workspace_id=ws_id,
            graph_id=graph_id,
            decision_case_id=case_id,
            version=1,
            option_id=UUID(option_a),
            node_overrides={},
            enabled_edge_ids=[],
        )
    )
    session.add(
        ScenarioVersionRow(
            id=scenario_id_row,
            workspace_id=ws_id,
            graph_id=graph_id,
            decision_case_id=case_id,
            source_lens_artifact_id=lens_ready_id,
            source_strategic_scenario_id="scenario_base_frame",
            scenario_id=uuid4(),
            version=1,
            name="base",
            description="baseline external assumptions",
            default_edge_multiplier=1.0,
            edge_multipliers={},
            node_shifts={},
            strategy_survives=True,
            early_warning_signals=[
                {
                    "signalId": "signal_seed",
                    "type": "structural",
                    "observable": "procurement wait",
                    "thresholdOrPattern": "> 90 days",
                    "cadence": "monthly",
                }
            ],
            damping=0.85,
        )
    )
    session.add(
        ScoreDefinitionRow(
            id=score_id,
            workspace_id=ws_id,
            graph_id=graph_id,
            decision_case_id=case_id,
            version="1",
            option_outcome_mappings=[
                {
                    "optionId": option_a,
                    "outcomeNodeId": str(outcome_a_id),
                    "goalId": "goal_traction",
                    "weight": 1.0,
                },
                {
                    "optionId": option_b,
                    "outcomeNodeId": str(outcome_b_id),
                    "goalId": "goal_traction",
                    "weight": 1.0,
                },
            ],
            risk_weights=[],
            constraint_rules=[],
            content_hash="sha256:score",
        )
    )
    await session.flush()

    # Workspace-global frozen profile v1 (decision_case_id NULL): the only
    # riskTolerance authority for runs in this world (CCR-SIM-02A §2).
    profile_id = uuid4()
    await SimulationInputRepository(session).insert_decision_maker_profile(
        workspace_id=ws_id,
        profile_id=profile_id,
        version=SEED_PROFILE_VERSION,
        user_id=user_id,
        display_name=f"profile-{slug}",
        preference_weights={"traction": 0.7, "cash": 0.3},
        risk_tolerance=SEED_PROFILE_RISK_TOLERANCE,
    )

    context = WorkspaceContext(
        user_id=user_id,
        workspace_id=ws_id,
        role=WorkspaceRole.OWNER,
        capabilities=ALL_CAPABILITIES,
    )
    return World(
        context=context,
        workspace_id=ws_id,
        user_id=user_id,
        subject_id=subject_id,
        case_id=case_id,
        analysis_run_id=run_id,
        charter_id=charter_id,
        lens_ready_id=lens_ready_id,
        graph_id=graph_id,
        graph_version_id=version_id,
        driver_id=driver_id,
        lever_id=lever_id,
        outcome_a_id=outcome_a_id,
        outcome_b_id=outcome_b_id,
        edge_ids={"e1": e1, "e2": e2, "e3": e3},
        strategy_version_id=strategy_id,
        scenario_version_id=scenario_id_row,
        score_definition_id=score_id,
        profile_id=profile_id,
        option_a=option_a,
        option_b=option_b,
    )


def request_for(world: World, **overrides) -> SimulationRunRequest:
    payload = {
        "decision_case_id": world.case_id,
        "graph_version_id": world.graph_version_id,
        "strategy_version_id": world.strategy_version_id,
        "scenario_version_id": world.scenario_version_id,
        "score_definition_id": world.score_definition_id,
        "simulation_mode": SimulationMode.FORMAL,
        "decision_maker_profile_id": world.profile_id,
        "decision_maker_profile_version": SEED_PROFILE_VERSION,
        "include_sensitivity": False,
    }
    payload.update(overrides)
    return SimulationRunRequest(**payload)


async def scoped_run_count(session: AsyncSession, world: World) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(SimulationRunRow)
            .where(
                SimulationRunRow.workspace_id == world.workspace_id,
                SimulationRunRow.decision_case_id == world.case_id,
            )
        )
        or 0
    )


# --- deterministic assembly ----------------------------------------------------------------


async def test_assembly_is_deterministic_and_ignores_db_insert_order(session: AsyncSession):
    world = await seed_world(session, "assembly")
    repository = SimulationInputRepository(session)
    version = await repository.get_graph_version(
        world.workspace_id, world.case_id, world.graph_version_id
    )
    assert version is not None
    nodes = await repository.get_graph_nodes(world.workspace_id, world.graph_version_id)
    edges = await repository.get_graph_edges(world.workspace_id, world.graph_version_id)

    first = assemble_graph(version, nodes, edges)
    second = assemble_graph(version, list(reversed(nodes)), list(reversed(edges)))
    assert first == second
    assert [node.id for node in first.nodes] == sorted(node.id for node in first.nodes)
    assert [edge.id for edge in first.edges] == sorted(edge.id for edge in first.edges)


async def test_same_input_twice_is_hash_and_result_identical(session: AsyncSession):
    world = await seed_world(session, "determinism")
    service = SimulationRunService(session)
    before = await scoped_run_count(session, world)
    first = await service.run_and_record(world.context, request_for(world))
    second = await service.run_and_record(world.context, request_for(world))
    assert first.input_hash == second.input_hash
    assert first.node_results == second.node_results
    assert first.option_scores == second.option_scores
    assert first.steps == second.steps
    assert first.convergence_status == second.convergence_status
    assert first.convergence_status == SimulationConvergenceStatus.CONVERGED
    assert first.recommended_option_id == world.option_a
    assert await scoped_run_count(session, world) == before + 2


async def test_simulation_run_persists_round_trip(session: AsyncSession):
    world = await seed_world(session, "roundtrip")
    service = SimulationRunService(session)
    view = await service.run_and_record(world.context, request_for(world))
    row = await session.scalar(
        select(SimulationRunRow).where(
            SimulationRunRow.workspace_id == world.workspace_id,
            SimulationRunRow.decision_case_id == world.case_id,
            SimulationRunRow.id == view.id,
        )
    )
    assert row is not None
    assert row.input_hash == view.input_hash
    assert row.steps == view.steps
    assert row.simulation_mode == SimulationMode.FORMAL
    assert row.convergence_status == view.convergence_status
    assert row.node_results == view.node_results
    assert row.graph_version_id == world.graph_version_id
    assert row.scenario_version_id == world.scenario_version_id


# --- inputHash reacts to every frozen input -------------------------------------------------


async def test_graph_content_change_changes_input_hash(session: AsyncSession):
    # Node ids ARE the primary keys at this baseline, so a persisted "same graph,
    # one value changed" cannot exist with identical ids; the content->hash chain
    # is therefore asserted at the assembly boundary with a domain-level delta.
    world = await seed_world(session, "graphhash")
    service = SimulationRunService(session)
    base = await service.run_and_record(world.context, request_for(world))

    assembled, _ = await service._load_frozen_input(world.context, request_for(world))
    changed = assembled.graph.with_value(str(world.driver_id), 0.75)
    changed_hash = compute_input_hash(
        changed,
        assembled.strategy,
        assembled.scenario,
        assembled.score_definition,
        0.5,
        SimulationMode.FORMAL,
        {},
        0.001,
        12,
    )
    assert changed_hash != base.input_hash


async def test_strategy_change_changes_input_hash(session: AsyncSession):
    world = await seed_world(session, "strathash")
    service = SimulationRunService(session)
    base = await service.run_and_record(world.context, request_for(world))

    strategy_v2 = uuid4()
    session.add(
        StrategyVersionRow(
            id=strategy_v2,
            workspace_id=world.workspace_id,
            graph_id=world.graph_id,
            decision_case_id=world.case_id,
            version=2,
            option_id=UUID(world.option_a),
            node_overrides={str(world.lever_id): 60.0},
            enabled_edge_ids=[],
        )
    )
    await session.flush()
    changed = await service.run_and_record(
        world.context, request_for(world, strategy_version_id=strategy_v2)
    )
    assert changed.input_hash != base.input_hash


async def test_scenario_change_changes_input_hash(session: AsyncSession):
    world = await seed_world(session, "scenhash")
    service = SimulationRunService(session)
    base = await service.run_and_record(world.context, request_for(world))

    scenario_v2 = uuid4()
    session.add(
        ScenarioVersionRow(
            id=scenario_v2,
            workspace_id=world.workspace_id,
            graph_id=world.graph_id,
            decision_case_id=world.case_id,
            source_lens_artifact_id=world.lens_ready_id,
            source_strategic_scenario_id="scenario_base_frame",
            scenario_id=uuid4(),
            version=2,
            name="damped",
            description="lower damping variant",
            default_edge_multiplier=1.0,
            edge_multipliers={},
            node_shifts={str(world.driver_id): 0.2},
            strategy_survives=False,
            early_warning_signals=[],
            damping=0.8,
        )
    )
    await session.flush()
    changed = await service.run_and_record(
        world.context, request_for(world, scenario_version_id=scenario_v2)
    )
    assert changed.input_hash != base.input_hash


async def test_score_definition_change_changes_input_hash(session: AsyncSession):
    world = await seed_world(session, "scorehash")
    service = SimulationRunService(session)
    base = await service.run_and_record(world.context, request_for(world))

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
                    "outcomeNodeId": str(world.outcome_a_id),
                    "goalId": "goal_traction",
                    "weight": 2.0,
                },
                {
                    "optionId": world.option_b,
                    "outcomeNodeId": str(world.outcome_b_id),
                    "goalId": "goal_traction",
                    "weight": 1.0,
                },
            ],
            risk_weights=[],
            constraint_rules=[],
            content_hash="sha256:score-v2",
        )
    )
    await session.flush()
    changed = await service.run_and_record(
        world.context, request_for(world, score_definition_id=score_v2)
    )
    assert changed.input_hash != base.input_hash


# --- tenancy and mixed anchors ---------------------------------------------------------------


async def test_foreign_workspace_anchors_are_uniform_not_found(session: AsyncSession):
    world_a = await seed_world(session, "tenant-a")
    world_b = await seed_world(session, "tenant-b")
    service = SimulationRunService(session)

    foreign_requests = [
        request_for(world_b),  # whole case belongs to B, context is A
        request_for(world_a, graph_version_id=world_b.graph_version_id),
        request_for(world_a, strategy_version_id=world_b.strategy_version_id),
        request_for(world_a, scenario_version_id=world_b.scenario_version_id),
        request_for(world_a, score_definition_id=world_b.score_definition_id),
    ]
    for request in foreign_requests:
        with pytest.raises(ApiFailure) as failure:
            await service.run_and_record(world_a.context, request)
        assert failure.value.code == "CASE_NOT_FOUND"
        assert failure.value.http_status == 404


async def test_scenario_from_other_graph_is_scope_mismatch(session: AsyncSession):
    world = await seed_world(session, "mismatch")
    other_graph = uuid4()
    session.add(
        CausalGraph(
            id=other_graph,
            workspace_id=world.workspace_id,
            decision_case_id=world.case_id,
            report_artifact_id=uuid4(),
            title="second graph",
        )
    )
    await session.flush()
    scenario_other = uuid4()
    session.add(
        ScenarioVersionRow(
            id=scenario_other,
            workspace_id=world.workspace_id,
            graph_id=other_graph,
            decision_case_id=world.case_id,
            source_lens_artifact_id=world.lens_ready_id,
            source_strategic_scenario_id="scenario_other_frame",
            scenario_id=uuid4(),
            version=1,
            name="other-graph scenario",
            description="anchored to a different causal graph",
            default_edge_multiplier=1.0,
            edge_multipliers={},
            node_shifts={},
            strategy_survives=True,
            early_warning_signals=[],
            damping=0.85,
        )
    )
    await session.flush()
    service = SimulationRunService(session)
    with pytest.raises(GraphScopeMismatchError):
        await service.run_and_record(
            world.context, request_for(world, scenario_version_id=scenario_other)
        )


async def test_scenario_with_non_ready_lens_source_is_uniform_not_found(session: AsyncSession):
    world = await seed_world(session, "lensdraft")
    draft_lens = uuid4()
    session.add(
        StrategicLensArtifact(
            strategic_lens_artifact_id=draft_lens,
            workspace_id=world.workspace_id,
            decision_case_id=world.case_id,
            analysis_run_id=world.analysis_run_id,
            charter_id=world.charter_id,
            lens_type=StrategicLensType.SCENARIO_PLANNING,
            producer_role=LensProducerRole.SYNTHESIS,
            status=StrategicLensArtifactStatus.DRAFT,
            method_id="hardtech-market-direction",
            method_version="1.1.0",
            method_content_hash="sha256:method",
            prompt_version="1",
            schema_version="1",
            content_hash="sha256:lens-draft",
        )
    )
    await session.flush()
    scenario_draft_lens = uuid4()
    session.add(
        ScenarioVersionRow(
            id=scenario_draft_lens,
            workspace_id=world.workspace_id,
            graph_id=world.graph_id,
            decision_case_id=world.case_id,
            source_lens_artifact_id=draft_lens,
            source_strategic_scenario_id="scenario_draft_frame",
            scenario_id=uuid4(),
            version=1,
            name="draft-lens scenario",
            description="source lens is not ready",
            default_edge_multiplier=1.0,
            edge_multipliers={},
            node_shifts={},
            strategy_survives=True,
            early_warning_signals=[],
            damping=0.85,
        )
    )
    await session.flush()
    service = SimulationRunService(session)
    with pytest.raises(ApiFailure) as failure:
        await service.run_and_record(
            world.context, request_for(world, scenario_version_id=scenario_draft_lens)
        )
    assert failure.value.code == "CASE_NOT_FOUND"


# --- strategy override contract --------------------------------------------------------------


async def _strategy_variant(
    session: AsyncSession, world: World, overrides: dict, enabled_edges: list[str] | None = None
) -> UUID:
    strategy_id = uuid4()
    session.add(
        StrategyVersionRow(
            id=strategy_id,
            workspace_id=world.workspace_id,
            graph_id=world.graph_id,
            decision_case_id=world.case_id,
            version=2,
            option_id=UUID(world.option_a),
            node_overrides=overrides,
            enabled_edge_ids=enabled_edges or [],
        )
    )
    await session.flush()
    return strategy_id


async def test_strategy_override_unknown_node_rejected(session: AsyncSession):
    world = await seed_world(session, "strat-unknown")
    strategy = await _strategy_variant(session, world, {str(uuid4()): 1.0})
    service = SimulationRunService(session)
    with pytest.raises(StrategyOverrideError):
        await service.run_and_record(
            world.context, request_for(world, strategy_version_id=strategy)
        )


async def test_strategy_override_non_lever_rejected(session: AsyncSession):
    world = await seed_world(session, "strat-outcome")
    strategy = await _strategy_variant(session, world, {str(world.outcome_a_id): 0.5})
    service = SimulationRunService(session)
    with pytest.raises(StrategyOverrideError):
        await service.run_and_record(
            world.context, request_for(world, strategy_version_id=strategy)
        )


async def test_strategy_override_out_of_bounds_rejected(session: AsyncSession):
    world = await seed_world(session, "strat-bounds")
    strategy = await _strategy_variant(session, world, {str(world.lever_id): 500.0})
    service = SimulationRunService(session)
    with pytest.raises(StrategyOverrideError):
        await service.run_and_record(
            world.context, request_for(world, strategy_version_id=strategy)
        )


async def test_strategy_edge_gating_fails_fast_as_contract_dependency(session: AsyncSession):
    world = await seed_world(session, "strat-edges")
    strategy = await _strategy_variant(
        session, world, {}, enabled_edges=[str(world.edge_ids["e1"])]
    )
    service = SimulationRunService(session)
    with pytest.raises(StrategyOverrideError) as failure:
        await service.run_and_record(
            world.context, request_for(world, strategy_version_id=strategy)
        )
    assert failure.value.code == "strategy_edge_gating_unsupported"


# --- scenario parameter contract -------------------------------------------------------------


async def _scenario_variant(session: AsyncSession, world: World, **columns) -> UUID:
    scenario_id = uuid4()
    payload = {
        "id": scenario_id,
        "workspace_id": world.workspace_id,
        "graph_id": world.graph_id,
        "decision_case_id": world.case_id,
        "source_lens_artifact_id": world.lens_ready_id,
        "source_strategic_scenario_id": "scenario_variant",
        "scenario_id": uuid4(),
        "version": 2,
        "name": "variant",
        "description": "variant scenario",
        "default_edge_multiplier": 1.0,
        "edge_multipliers": {},
        "node_shifts": {},
        "strategy_survives": True,
        "early_warning_signals": [],
        "damping": 0.85,
    }
    payload.update(columns)
    session.add(ScenarioVersionRow(**payload))
    await session.flush()
    return scenario_id


async def test_scenario_unknown_node_shift_rejected(session: AsyncSession):
    world = await seed_world(session, "scen-node")
    scenario = await _scenario_variant(session, world, node_shifts={str(uuid4()): 0.2})
    service = SimulationRunService(session)
    with pytest.raises(ScenarioParameterError):
        await service.run_and_record(
            world.context, request_for(world, scenario_version_id=scenario)
        )


async def test_scenario_unknown_edge_multiplier_rejected(session: AsyncSession):
    world = await seed_world(session, "scen-edge")
    scenario = await _scenario_variant(session, world, edge_multipliers={str(uuid4()): 1.2})
    service = SimulationRunService(session)
    with pytest.raises(ScenarioParameterError):
        await service.run_and_record(
            world.context, request_for(world, scenario_version_id=scenario)
        )


async def test_scenario_business_unit_shift_rejected(session: AsyncSession):
    world = await seed_world(session, "scen-unit")
    scenario = await _scenario_variant(
        session, world, node_shifts={str(world.driver_id): 14.0}
    )
    service = SimulationRunService(session)
    with pytest.raises(ScenarioParameterError):
        await service.run_and_record(
            world.context, request_for(world, scenario_version_id=scenario)
        )


# --- score definition contract ---------------------------------------------------------------


async def _score_variant(session: AsyncSession, world: World, **columns) -> UUID:
    score_id = uuid4()
    payload = {
        "id": score_id,
        "workspace_id": world.workspace_id,
        "graph_id": world.graph_id,
        "decision_case_id": world.case_id,
        "version": "2",
        "option_outcome_mappings": [
            {
                "optionId": world.option_a,
                "outcomeNodeId": str(world.outcome_a_id),
                "goalId": "goal_traction",
                "weight": 1.0,
            }
        ],
        "risk_weights": [],
        "constraint_rules": [],
        "content_hash": "sha256:score-variant",
    }
    payload.update(columns)
    session.add(ScoreDefinitionRow(**payload))
    await session.flush()
    return score_id


async def test_score_unknown_outcome_node_rejected(session: AsyncSession):
    world = await seed_world(session, "score-node")
    score = await _score_variant(
        session,
        world,
        option_outcome_mappings=[
            {
                "optionId": world.option_a,
                "outcomeNodeId": str(uuid4()),
                "goalId": "goal_traction",
                "weight": 1.0,
            }
        ],
    )
    service = SimulationRunService(session)
    with pytest.raises(ScoreDefinitionReferenceError):
        await service.run_and_record(
            world.context, request_for(world, score_definition_id=score)
        )


async def test_score_option_outside_frozen_case_set_rejected(session: AsyncSession):
    world = await seed_world(session, "score-option")
    score = await _score_variant(
        session,
        world,
        option_outcome_mappings=[
            {
                "optionId": str(uuid4()),
                "outcomeNodeId": str(world.outcome_a_id),
                "goalId": "goal_traction",
                "weight": 1.0,
            }
        ],
    )
    service = SimulationRunService(session)
    with pytest.raises(ScoreDefinitionReferenceError):
        await service.run_and_record(
            world.context, request_for(world, score_definition_id=score)
        )


async def test_score_equality_operator_fails_fast_as_contract_dependency(session: AsyncSession):
    world = await seed_world(session, "score-eq")
    score = await _score_variant(
        session,
        world,
        constraint_rules=[
            {
                "optionId": world.option_a,
                "constraintNodeId": str(world.outcome_b_id),
                "operator": "=",
                "threshold": 0.4,
                "penalty": 1.0,
            }
        ],
    )
    service = SimulationRunService(session)
    with pytest.raises(ScoreDefinitionReferenceError) as failure:
        await service.run_and_record(
            world.context, request_for(world, score_definition_id=score)
        )
    assert failure.value.code == "score_constraint_operator_unsupported"


# --- formal / experimental authorization ------------------------------------------------------


async def test_formal_rejects_draft_graph_version(session: AsyncSession):
    world = await seed_world(session, "formal-draft", graph_status=GraphVersionStatus.DRAFT)
    service = SimulationRunService(session)
    with pytest.raises(SimulationAuthorizationError):
        await service.run_and_record(world.context, request_for(world))


async def test_experimental_accepts_contract_allowed_draft_graph(session: AsyncSession):
    world = await seed_world(session, "exp-draft", graph_status=GraphVersionStatus.DRAFT)
    service = SimulationRunService(session)
    view = await service.run_and_record(
        world.context, request_for(world, simulation_mode=SimulationMode.EXPERIMENTAL)
    )
    assert view.simulation_mode == SimulationMode.EXPERIMENTAL
    assert view.convergence_status == SimulationConvergenceStatus.CONVERGED
    row = await session.scalar(
        select(SimulationRunRow).where(
            SimulationRunRow.workspace_id == world.workspace_id,
            SimulationRunRow.decision_case_id == world.case_id,
            SimulationRunRow.id == view.id,
        )
    )
    assert row is not None
    assert row.simulation_mode == SimulationMode.EXPERIMENTAL


# --- failure discipline -----------------------------------------------------------------------


async def test_engine_failure_leaves_no_zombie_rows(session: AsyncSession, monkeypatch):
    world = await seed_world(session, "zombie")
    service = SimulationRunService(session)
    before = await scoped_run_count(session, world)

    def boom(*args, **kwargs):
        raise SimulationAuthorizationError("forced engine failure for the zombie test")

    monkeypatch.setattr("app.simulations.service.run_simulation", boom)
    with pytest.raises(SimulationAuthorizationError):
        await service.run_and_record(world.context, request_for(world))
    assert await scoped_run_count(session, world) == before


async def test_view_is_immutable_and_not_an_orm_object(session: AsyncSession):
    world = await seed_world(session, "view")
    service = SimulationRunService(session)
    view = await service.run_and_record(world.context, request_for(world))
    assert not isinstance(view, SimulationRunRow)
    with pytest.raises(dataclasses.FrozenInstanceError):
        view.input_hash = "sha256:tampered"  # type: ignore[misc]
