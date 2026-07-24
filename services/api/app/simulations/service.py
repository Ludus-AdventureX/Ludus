"""DB-backed simulation run service.

Lifecycle (compute-then-insert): resolve tenant anchors, authorize the mode, assemble the
frozen Task 12 domain input deterministically, call the unchanged pure engine (which alone
computes the canonical inputHash), optionally derive single-variable sensitivity, and only
then stage ONE fully computed ``simulation_runs`` row inside a single transaction. Because
no partial "running" row ever exists, an engine failure cannot leave a zombie row behind.

Error discipline: uniform ``CASE_NOT_FOUND`` 404 (existing envelope) for every missing,
foreign-workspace, or mixed-anchor scope; stable :mod:`app.simulations.errors` domain errors
for same-tenant contract violations; ``SQLAlchemyError`` never leaks to callers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SimulationRun as SimulationRunRow
from app.simulations.schemas import SimulationRun as SimulationRunWire
from app.tenancy.context import WorkspaceContext
from app.types import (
    OriginMode,
    SimulationConvergenceStatus,
    SimulationMode,
    StrategicLensArtifactStatus,
    StrategicLensType,
)

from .assembly import (
    AssembledSimulationInput,
    assemble_graph,
    assemble_scenario,
    assemble_score_definition,
    assemble_strategy,
)
from .domain import OptionScore, TopDriver
from .engine import assert_authorization, run_simulation
from .errors import (
    GraphScopeMismatchError,
    SimulationPersistenceError,
    simulation_scope_not_found,
)
from .repository import SimulationInputRepository
from .sensitivity import analyze_sensitivity


@dataclass(frozen=True, slots=True)
class SimulationRunRequest:
    """Frozen references chosen by the caller; ids are anchors, never authority."""

    decision_case_id: UUID
    graph_version_id: UUID
    strategy_version_id: UUID
    scenario_version_id: UUID
    score_definition_id: UUID
    simulation_mode: SimulationMode
    decision_maker_profile_id: UUID
    decision_maker_profile_version: int
    risk_tolerance: float
    epsilon: float = 0.001
    max_steps: int = 12
    node_overrides: dict[str, float] | None = None
    include_sensitivity: bool = True


@dataclass(frozen=True, slots=True)
class SimulationRunView:
    """Immutable service projection of one persisted run (NOT a wire DTO, NOT ORM)."""

    id: UUID
    workspace_id: UUID
    decision_case_id: UUID
    graph_id: UUID
    graph_version_id: UUID
    strategy_version_id: UUID
    scenario_version_id: UUID
    score_definition_id: UUID
    score_definition_version: str
    decision_maker_profile_id: UUID
    decision_maker_profile_version: int
    risk_tolerance: float
    engine_version: str
    scenario_id: UUID
    simulation_mode: SimulationMode
    epsilon: float
    max_steps: int
    steps: int
    input_hash: str
    node_results: dict[str, float]
    option_scores: tuple[OptionScore, ...]
    top_drivers: tuple[TopDriver, ...]
    recommendation_shift: str
    recommended_option_id: str | None
    convergence_status: SimulationConvergenceStatus
    origin_modes: tuple[OriginMode, ...]
    created_at: datetime


class SimulationRunService:
    """Authorization-aware assembly + pure-engine execution + result persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repository = SimulationInputRepository(db)

    async def _load_frozen_input(
        self, context: WorkspaceContext, request: SimulationRunRequest
    ) -> tuple[AssembledSimulationInput, dict]:
        """Resolve + validate every frozen reference; uniform 404 on scope denial."""

        workspace_id = context.workspace_id
        case = await self._repository.get_case(workspace_id, request.decision_case_id)
        if case is None:
            raise simulation_scope_not_found()

        graph_version = await self._repository.get_graph_version(
            workspace_id, request.decision_case_id, request.graph_version_id
        )
        strategy_row = await self._repository.get_strategy_version(
            workspace_id, request.decision_case_id, request.strategy_version_id
        )
        scenario_row = await self._repository.get_scenario_version(
            workspace_id, request.decision_case_id, request.scenario_version_id
        )
        score_row = await self._repository.get_score_definition(
            workspace_id, request.decision_case_id, request.score_definition_id
        )
        if graph_version is None or strategy_row is None or scenario_row is None or score_row is None:
            raise simulation_scope_not_found()

        # Same-tenant anchors must also agree on the causal graph aggregate.
        if scenario_row.graph_id != graph_version.graph_id:
            raise GraphScopeMismatchError(
                "scenario version belongs to a different causal graph than the graph version"
            )
        if strategy_row.graph_id != graph_version.graph_id:
            raise GraphScopeMismatchError(
                "strategy version belongs to a different causal graph than the graph version"
            )
        if score_row.graph_id != graph_version.graph_id:
            raise GraphScopeMismatchError(
                "score definition belongs to a different causal graph than the graph version"
            )

        # Scenario lens provenance: same workspace/case, scenario_planning, ready.
        # Fail-closed uniform 404 (lens read-path precedent) so lens lifecycle state
        # can never be probed through this path.
        source_lens = await self._repository.get_scenario_source_lens(
            workspace_id, request.decision_case_id, scenario_row.source_lens_artifact_id
        )
        if (
            source_lens is None
            or source_lens.lens_type != StrategicLensType.SCENARIO_PLANNING
            or source_lens.status != StrategicLensArtifactStatus.READY
        ):
            raise simulation_scope_not_found()

        node_rows = await self._repository.get_graph_nodes(workspace_id, graph_version.id)
        edge_rows = await self._repository.get_graph_edges(workspace_id, graph_version.id)

        graph = assemble_graph(graph_version, node_rows, edge_rows)
        assembled = AssembledSimulationInput(
            graph=graph,
            strategy=assemble_strategy(strategy_row, graph),
            scenario=assemble_scenario(scenario_row, graph),
            score_definition=assemble_score_definition(score_row, graph, case),
        )
        row_refs = {
            "graph_id": graph_version.graph_id,
            "scenario_id": scenario_row.scenario_id,
            "score_definition_version": score_row.version,
            "origin_modes": list(dict.fromkeys(graph_version.origin_modes)),
        }
        return assembled, row_refs

    async def run_and_record(
        self, context: WorkspaceContext, request: SimulationRunRequest
    ) -> SimulationRunView:
        assembled, row_refs = await self._load_frozen_input(context, request)
        overrides = dict(request.node_overrides or {})

        # Service-level precheck, then the engine re-asserts internally (second gate).
        assert_authorization(assembled.graph, request.simulation_mode)

        result = run_simulation(
            assembled.graph,
            assembled.strategy,
            assembled.scenario,
            assembled.score_definition,
            request.risk_tolerance,
            request.simulation_mode,
            node_overrides=overrides,
            epsilon=request.epsilon,
            max_steps=request.max_steps,
        )

        top_drivers = result.top_drivers
        recommendation_shift = result.recommendation_shift
        if request.include_sensitivity:
            sensitivity = analyze_sensitivity(
                assembled.graph,
                assembled.strategy,
                assembled.scenario,
                assembled.score_definition,
                request.risk_tolerance,
                request.simulation_mode,
                node_overrides=overrides,
                epsilon=request.epsilon,
                max_steps=request.max_steps,
            )
            top_drivers = sensitivity.top_drivers
            recommendation_shift = sensitivity.recommendation_shift

        run_id = uuid4()
        created_at = datetime.now(timezone.utc)
        option_scores_json = [
            {"optionId": entry.option_id, "score": entry.score}
            for entry in result.option_scores
        ]
        top_drivers_json = [
            {"nodeId": entry.node_id, "scoreDelta": entry.score_delta}
            for entry in top_drivers
        ]

        # Wire-contract self-check before touching the database: the persisted row
        # must round-trip through the canonical SimulationRun schema exactly.
        SimulationRunWire.model_validate(
            {
                "id": str(run_id),
                "workspaceId": str(context.workspace_id),
                "decisionCaseId": str(request.decision_case_id),
                "graphId": str(row_refs["graph_id"]),
                "graphVersionId": str(request.graph_version_id),
                "strategyVersionId": str(request.strategy_version_id),
                "scenarioVersionId": str(request.scenario_version_id),
                "scoreDefinitionId": str(request.score_definition_id),
                "scoreDefinitionVersion": row_refs["score_definition_version"],
                "decisionMakerProfileId": str(request.decision_maker_profile_id),
                "decisionMakerProfileVersion": request.decision_maker_profile_version,
                "riskTolerance": request.risk_tolerance,
                "engineVersion": result.engine_version,
                "scenarioId": str(row_refs["scenario_id"]),
                "simulationMode": request.simulation_mode.value,
                "epsilon": request.epsilon,
                "maxSteps": request.max_steps,
                "steps": result.steps,
                "inputHash": result.input_hash,
                "nodeResults": result.node_results,
                "optionScores": option_scores_json,
                "topDrivers": top_drivers_json,
                "recommendationShift": recommendation_shift,
                "convergenceStatus": result.convergence_status.value,
                "originModes": [mode.value for mode in row_refs["origin_modes"]],
                "createdAt": created_at.isoformat(),
            }
        )

        row = SimulationRunRow(
            id=run_id,
            workspace_id=context.workspace_id,
            decision_case_id=request.decision_case_id,
            graph_id=row_refs["graph_id"],
            graph_version_id=request.graph_version_id,
            strategy_version_id=request.strategy_version_id,
            scenario_version_id=request.scenario_version_id,
            score_definition_id=request.score_definition_id,
            score_definition_version=row_refs["score_definition_version"],
            decision_maker_profile_id=request.decision_maker_profile_id,
            decision_maker_profile_version=request.decision_maker_profile_version,
            risk_tolerance=request.risk_tolerance,
            engine_version=result.engine_version,
            scenario_id=row_refs["scenario_id"],
            simulation_mode=request.simulation_mode,
            epsilon=request.epsilon,
            max_steps=request.max_steps,
            steps=result.steps,
            input_hash=result.input_hash,
            node_results=dict(result.node_results),
            option_scores=option_scores_json,
            top_drivers=top_drivers_json,
            recommendation_shift=recommendation_shift,
            convergence_status=result.convergence_status,
            origin_modes=list(row_refs["origin_modes"]),
            created_at=created_at,
        )

        try:
            await self._repository.insert_simulation_run(row)
            await self._db.commit()
        except SQLAlchemyError as exc:
            await self._db.rollback()
            raise SimulationPersistenceError(
                "persisting the simulation run failed; the transaction was rolled back"
            ) from exc

        return SimulationRunView(
            id=run_id,
            workspace_id=context.workspace_id,
            decision_case_id=request.decision_case_id,
            graph_id=row_refs["graph_id"],
            graph_version_id=request.graph_version_id,
            strategy_version_id=request.strategy_version_id,
            scenario_version_id=request.scenario_version_id,
            score_definition_id=request.score_definition_id,
            score_definition_version=row_refs["score_definition_version"],
            decision_maker_profile_id=request.decision_maker_profile_id,
            decision_maker_profile_version=request.decision_maker_profile_version,
            risk_tolerance=request.risk_tolerance,
            engine_version=result.engine_version,
            scenario_id=row_refs["scenario_id"],
            simulation_mode=request.simulation_mode,
            epsilon=request.epsilon,
            max_steps=request.max_steps,
            steps=result.steps,
            input_hash=result.input_hash,
            node_results=dict(result.node_results),
            option_scores=result.option_scores,
            top_drivers=tuple(top_drivers),
            recommendation_shift=recommendation_shift,
            recommended_option_id=result.recommended_option_id,
            convergence_status=result.convergence_status,
            origin_modes=tuple(row_refs["origin_modes"]),
            created_at=created_at,
        )
