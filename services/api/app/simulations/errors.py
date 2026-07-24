"""Stable domain errors for the DB-backed simulation repository/service.

Every class extends the existing Task 12 ``SimulationError`` hierarchy so callers keep one
except-surface, and carries a stable machine ``code`` so later API work (CCR-SIM-02) can map
categories without string matching. No new HTTP error code is introduced here: uniform
scope denial reuses the existing ``CASE_NOT_FOUND`` ApiFailure exactly like the lens
read-path precedent, and everything else stays an in-process domain error.
"""

from __future__ import annotations

from app.security.envelope import ApiFailure

from .domain import SimulationError


def simulation_scope_not_found() -> ApiFailure:
    """Uniform 404 for missing, foreign-workspace, or mixed-anchor simulation scopes.

    One code and one message for every denial reason (missing case, foreign graph version,
    cross-tenant strategy/scenario/score id, non-consumable lens source), so existence can
    never be probed through error shape.
    """

    return ApiFailure(
        "CASE_NOT_FOUND",
        "Decision case, analysis run, or artifact not found.",
        http_status=404,
    )


class SimulationRepositoryError(SimulationError):
    """Base for repository/service level domain rejections."""

    code = "simulation_input_rejected"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class FrozenReferenceError(SimulationRepositoryError):
    """A frozen input reference is incomplete or not usable for this run."""

    code = "frozen_reference_incomplete"


class GraphScopeMismatchError(SimulationRepositoryError):
    """Graph/strategy/scenario/score anchors do not belong to the same causal graph."""

    code = "graph_scope_mismatch"


class StrategyOverrideError(SimulationRepositoryError):
    """Strategy node overrides violate the graph contract."""

    code = "strategy_override_invalid"


class ScenarioParameterError(SimulationRepositoryError):
    """Scenario shifts/multipliers reference unknown elements or illegal values."""

    code = "scenario_parameter_invalid"


class ScoreDefinitionReferenceError(SimulationRepositoryError):
    """ScoreDefinition JSONB references unknown nodes/options or unsupported operators."""

    code = "score_definition_reference_invalid"


class FormalAuthorizationError(SimulationRepositoryError):
    """The referenced graph version is not authorized for a formal run."""

    code = "formal_authorization_rejected"


class SimulationPersistenceError(SimulationRepositoryError):
    """Persisting a computed simulation run failed in a controlled way."""

    code = "simulation_persistence_failed"
