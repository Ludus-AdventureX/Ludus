from __future__ import annotations

import math
from datetime import datetime

from pydantic import Field, field_validator, model_validator

from app.contracts.schemas import CanonicalModel, ContentHash, Identifier, NonEmptyText
from app.types import OriginMode, SimulationConvergenceStatus, SimulationMode


class SimulationOptionScore(CanonicalModel):
    option_id: Identifier
    score: float


class SimulationTopDriver(CanonicalModel):
    node_id: Identifier
    score_delta: float


class SimulationRun(CanonicalModel):
    id: Identifier
    workspace_id: Identifier
    decision_case_id: Identifier
    graph_id: Identifier
    graph_version_id: Identifier
    strategy_version_id: Identifier
    scenario_version_id: Identifier
    score_definition_id: Identifier
    score_definition_version: NonEmptyText
    decision_maker_profile_id: Identifier
    decision_maker_profile_version: int = Field(gt=0)
    risk_tolerance: float = Field(ge=0, le=1)
    engine_version: NonEmptyText
    scenario_id: Identifier
    simulation_mode: SimulationMode
    epsilon: float = Field(gt=0)
    max_steps: int = Field(gt=0)
    steps: int = Field(ge=0)
    input_hash: ContentHash
    node_results: dict[str, float]
    option_scores: list[SimulationOptionScore]
    top_drivers: list[SimulationTopDriver]
    recommendation_shift: str
    convergence_status: SimulationConvergenceStatus
    origin_modes: list[OriginMode]
    created_at: datetime

    @field_validator("origin_modes")
    @classmethod
    def origin_modes_are_unique(cls, values: list[OriginMode]) -> list[OriginMode]:
        if len(values) != len(set(values)):
            raise ValueError("originModes must not contain duplicates")
        return values

    @model_validator(mode="after")
    def replay_numbers_are_finite_and_bounded(self) -> SimulationRun:
        if self.steps > self.max_steps:
            raise ValueError("steps cannot exceed maxSteps")
        numeric_values = [
            self.risk_tolerance,
            self.epsilon,
            *self.node_results.values(),
            *(item.score for item in self.option_scores),
            *(item.score_delta for item in self.top_drivers),
        ]
        if not all(math.isfinite(value) for value in numeric_values):
            raise ValueError("simulation replay fields must contain only finite numbers")
        return self
