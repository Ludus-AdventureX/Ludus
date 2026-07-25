"""Charter and Run state machines (Task 9) — pure, deterministic logic.

Wire truth: 06-data-model.md. ``AnalysisRunStatus`` comes from ``app.types``
(imported, never redefined). This module owns only legality decisions; all
persistence/event side effects live in ``repository.py``.

Run machine:

    queued -> planning -> retrieving -> analyzing -> criticizing
           -> synthesizing -> validating -> ready | blocked
    every executing stage -> needs_attention | cancelled
    queued -> cancelled
    needs_attention -> (exactly lastResumableStage) | cancelled

``ready`` is reachable only from ``validating`` AND only when the formal
quality gate passed. ``blocked`` is the quality-gate terminal (only from
``validating``); neither resolution nor cancel reopens it. ``cancelled`` is
terminal and forbids any later publication-flavored transition.
"""

from __future__ import annotations

from typing import Final

from app.types import AnalysisRunStatus

from .models import CHARTER_FROZEN_FIELDS


class InvalidTransition(Exception):
    """A state transition that the canonical contract forbids."""

    def __init__(self, current: str, target: str, reason: str) -> None:
        super().__init__(f"{current} -> {target}: {reason}")
        self.current = current
        self.target = target
        self.reason = reason


class InvalidCharter(Exception):
    """Charter shape or lifecycle violates the canonical contract."""


EXECUTING_STAGES: Final[tuple[AnalysisRunStatus, ...]] = (
    AnalysisRunStatus.PLANNING,
    AnalysisRunStatus.RETRIEVING,
    AnalysisRunStatus.ANALYZING,
    AnalysisRunStatus.CRITICIZING,
    AnalysisRunStatus.SYNTHESIZING,
    AnalysisRunStatus.VALIDATING,
)
TERMINAL_STATUSES: Final[frozenset[AnalysisRunStatus]] = frozenset(
    {
        AnalysisRunStatus.READY,
        AnalysisRunStatus.BLOCKED,
        AnalysisRunStatus.CANCELLED,
    }
)
CANCELLABLE_STATUSES: Final[frozenset[AnalysisRunStatus]] = frozenset(
    {AnalysisRunStatus.QUEUED, *EXECUTING_STAGES, AnalysisRunStatus.NEEDS_ATTENTION}
)

_STAGE_INDEX = {stage: index for index, stage in enumerate(EXECUTING_STAGES)}


def next_stage(stage: AnalysisRunStatus) -> AnalysisRunStatus | None:
    """The next sequential executing stage, or None after ``validating``."""

    index = _STAGE_INDEX.get(stage)
    if index is None or index + 1 >= len(EXECUTING_STAGES):
        return None
    return EXECUTING_STAGES[index + 1]


class RunStateMachine:
    """Legality gate for every AnalysisRun transition."""

    def validate_transition(
        self,
        current: AnalysisRunStatus,
        target: AnalysisRunStatus,
        *,
        quality_gate_passed: bool = False,
        last_resumable_stage: AnalysisRunStatus | None = None,
    ) -> None:
        if current in TERMINAL_STATUSES:
            raise InvalidTransition(
                current.value, target.value, "terminal states never transition"
            )
        if target == AnalysisRunStatus.QUEUED:
            raise InvalidTransition(
                current.value, target.value, "queued is entry-only, never a target"
            )
        if target == AnalysisRunStatus.CANCELLED:
            if current in CANCELLABLE_STATUSES:
                return
            raise InvalidTransition(
                current.value, target.value, "only active runs can be cancelled"
            )
        if target == AnalysisRunStatus.READY:
            if current != AnalysisRunStatus.VALIDATING:
                raise InvalidTransition(
                    current.value, target.value, "ready is reachable only from validating"
                )
            if not quality_gate_passed:
                raise InvalidTransition(
                    current.value,
                    target.value,
                    "ready requires the formal quality gate to pass",
                )
            return
        if target == AnalysisRunStatus.BLOCKED:
            if current != AnalysisRunStatus.VALIDATING:
                raise InvalidTransition(
                    current.value,
                    target.value,
                    "blocked is the validating quality-gate terminal only",
                )
            return
        if target == AnalysisRunStatus.NEEDS_ATTENTION:
            if current in EXECUTING_STAGES:
                return
            raise InvalidTransition(
                current.value,
                target.value,
                "only executing stages can enter needs_attention",
            )
        if current == AnalysisRunStatus.NEEDS_ATTENTION:
            if last_resumable_stage is None:
                raise InvalidTransition(
                    current.value, target.value, "no persisted lastResumableStage"
                )
            if target != last_resumable_stage:
                raise InvalidTransition(
                    current.value,
                    target.value,
                    "needs_attention may resume only to the persisted lastResumableStage",
                )
            return
        if current == AnalysisRunStatus.QUEUED:
            if target == AnalysisRunStatus.PLANNING:
                return
            raise InvalidTransition(
                current.value, target.value, "queued may only start at planning"
            )
        # sequential stage advance only
        if current in _STAGE_INDEX and target in _STAGE_INDEX:
            if _STAGE_INDEX[target] == _STAGE_INDEX[current] + 1:
                return
            raise InvalidTransition(
                current.value, target.value, "stages advance strictly one step forward"
            )
        raise InvalidTransition(current.value, target.value, "no legal edge")


# --- Charter machine ----------------------------------------------------------

CHARTER_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    "draft": frozenset({"awaiting_confirmation"}),
    "awaiting_confirmation": frozenset({"confirmed", "draft"}),
    "confirmed": frozenset({"superseded"}),
    "superseded": frozenset(),
}

# The exact full-level lens set (canonical order preserved for normalization).
FULL_LENS_SET: Final[tuple[str, ...]] = (
    "porter_five_forces",
    "pre_mortem",
    "counterparty_response_matrix",
    "scenario_planning",
    "meadows_leverage_points",
)


def validate_charter_transition(current: str, target: str) -> None:
    allowed = CHARTER_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise InvalidTransition(current, target, "charter lifecycle edge not allowed")


def normalize_lens_set(analysis_level: str, lens_set: list[str]) -> list[str]:
    """Enforce the canonical lens-set rule and normalize full to the five-set.

    focused: the set MUST be empty. full: any input equal to the complete
    five-lens set (in any order) normalizes to canonical order; anything else
    fails closed.
    """

    if analysis_level == "focused":
        if lens_set:
            raise InvalidCharter(
                "focused charters must carry an empty strategic lens set"
            )
        return []
    if analysis_level == "full":
        if set(lens_set) != set(FULL_LENS_SET) or len(lens_set) != len(FULL_LENS_SET):
            raise InvalidCharter(
                "full charters must carry exactly the complete five-lens set"
            )
        return list(FULL_LENS_SET)
    raise InvalidCharter(f"unknown formal analysis level: {analysis_level!r}")


def diff_frozen_fields(
    old_values: dict[str, object], new_values: dict[str, object]
) -> list[str]:
    """Compare charter frozen fields; the diff drives resolution vs amendment.

    Keys are the canonical ``CharterFrozenField`` names; only keys present in
    ``new_values`` are compared, so a partial intervention payload never
    reports untouched fields.
    """

    changed = [
        name
        for name in CHARTER_FROZEN_FIELDS
        if name in new_values and new_values[name] != old_values.get(name)
    ]
    return changed
