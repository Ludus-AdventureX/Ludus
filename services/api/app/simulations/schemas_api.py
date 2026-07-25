"""Wire DTOs for the SIM-02A run API (CCR-20260724-SIM-02A §5/§6).

``SimulationRunCreateRequest`` is the exact frozen POST body: strict camelCase,
``extra="forbid"``, and deliberately WITHOUT ``decisionCaseId`` (derived from the
path ``graphId``), ``riskTolerance`` / ``engineVersion`` / ``scoreDefinitionVersion``
(server-owned, §5 rulings 3-5), or ``includeSensitivity`` (server-fixed true).

``SimulationRunData`` is the shared POST/GET response projection built from the
service ``SimulationRunView`` — never from ORM rows, which must not cross the
HTTP boundary (§6.2).
"""

from __future__ import annotations

import math
from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator

from app.contracts.schemas import CanonicalModel, ContentHash, Identifier, NonEmptyText
from app.types import OriginMode, SimulationConvergenceStatus, SimulationMode

from .service import SimulationRunView


class SimulationRunCreateRequest(CanonicalModel):
    """Frozen POST body (§5): anchors only; every authority field is server-owned."""

    mode: SimulationMode
    graph_version_id: UUID
    strategy_version_id: UUID
    scenario_version_id: UUID
    score_definition_id: UUID
    decision_maker_profile_id: UUID
    decision_maker_profile_version: int = Field(ge=1)
    epsilon: float = Field(default=0.001, gt=0, le=0.1)
    max_steps: int = Field(default=12, ge=1, le=64)
    node_overrides: dict[str, float] = Field(default_factory=dict)

    @field_validator("node_overrides")
    @classmethod
    def node_overrides_are_finite(cls, values: dict[str, float]) -> dict[str, float]:
        for key, value in values.items():
            if not key.strip():
                raise ValueError("nodeOverrides keys must be non-empty node ids")
            if not math.isfinite(value):
                raise ValueError("nodeOverrides values must be finite numbers")
        return values


class SimulationOptionScoreData(CanonicalModel):
    option_id: Identifier
    score: float


class SimulationTopDriverData(CanonicalModel):
    node_id: Identifier
    score_delta: float


class SimulationRunData(CanonicalModel):
    """Shared POST/GET ``data`` payload (§6): frozen inputs + results, replayable."""

    simulation_run_id: Identifier
    workspace_id: Identifier
    decision_case_id: Identifier
    graph_id: Identifier
    graph_version_id: Identifier
    strategy_version_id: Identifier
    scenario_version_id: Identifier
    score_definition_id: Identifier
    score_definition_version: NonEmptyText
    decision_maker_profile_id: Identifier
    decision_maker_profile_version: int = Field(ge=1)
    risk_tolerance: float = Field(ge=0, le=1)
    engine_version: NonEmptyText
    scenario_id: Identifier
    simulation_mode: SimulationMode
    epsilon: float = Field(gt=0)
    max_steps: int = Field(gt=0)
    steps: int = Field(ge=0)
    input_hash: ContentHash
    node_results: dict[str, float]
    option_scores: list[SimulationOptionScoreData]
    top_drivers: list[SimulationTopDriverData]
    recommendation_shift: str
    recommended_option_id: Identifier | None
    convergence_status: SimulationConvergenceStatus
    origin_modes: list[OriginMode]
    created_at: datetime


def run_data_from_view(view: SimulationRunView) -> SimulationRunData:
    """Project the immutable service view onto the wire DTO (no ORM at the boundary)."""

    return SimulationRunData(
        simulation_run_id=str(view.id),
        workspace_id=str(view.workspace_id),
        decision_case_id=str(view.decision_case_id),
        graph_id=str(view.graph_id),
        graph_version_id=str(view.graph_version_id),
        strategy_version_id=str(view.strategy_version_id),
        scenario_version_id=str(view.scenario_version_id),
        score_definition_id=str(view.score_definition_id),
        score_definition_version=view.score_definition_version,
        decision_maker_profile_id=str(view.decision_maker_profile_id),
        decision_maker_profile_version=view.decision_maker_profile_version,
        risk_tolerance=view.risk_tolerance,
        engine_version=view.engine_version,
        scenario_id=str(view.scenario_id),
        simulation_mode=view.simulation_mode,
        epsilon=view.epsilon,
        max_steps=view.max_steps,
        steps=view.steps,
        input_hash=view.input_hash,
        node_results=dict(view.node_results),
        option_scores=[
            SimulationOptionScoreData(option_id=entry.option_id, score=entry.score)
            for entry in view.option_scores
        ],
        top_drivers=[
            SimulationTopDriverData(node_id=entry.node_id, score_delta=entry.score_delta)
            for entry in view.top_drivers
        ],
        recommendation_shift=view.recommendation_shift,
        recommended_option_id=view.recommended_option_id,
        convergence_status=view.convergence_status,
        origin_modes=list(view.origin_modes),
        created_at=view.created_at,
    )
