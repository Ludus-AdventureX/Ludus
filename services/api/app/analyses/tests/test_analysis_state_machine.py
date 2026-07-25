"""Task 9 owner tests: state machine legality matrix (pure logic, no DB)."""

from __future__ import annotations

import pytest

from app.analyses.state_machine import (
    CANCELLABLE_STATUSES,
    EXECUTING_STAGES,
    FULL_LENS_SET,
    InvalidCharter,
    InvalidTransition,
    RunStateMachine,
    TERMINAL_STATUSES,
    diff_frozen_fields,
    next_stage,
    normalize_lens_set,
    validate_charter_transition,
)
from app.types import AnalysisRunStatus

S = AnalysisRunStatus


@pytest.fixture
def machine() -> RunStateMachine:
    return RunStateMachine()


# --- legal path matrix ---------------------------------------------------------


def test_full_legal_pipeline_path(machine) -> None:
    machine.validate_transition(S.QUEUED, S.PLANNING)
    for index, stage in enumerate(EXECUTING_STAGES[:-1]):
        machine.validate_transition(stage, EXECUTING_STAGES[index + 1])
    machine.validate_transition(S.VALIDATING, S.READY, quality_gate_passed=True)


def test_validating_can_block_on_quality_gate(machine) -> None:
    machine.validate_transition(S.VALIDATING, S.BLOCKED)


@pytest.mark.parametrize("stage", EXECUTING_STAGES)
def test_every_executing_stage_can_enter_needs_attention(machine, stage) -> None:
    machine.validate_transition(stage, S.NEEDS_ATTENTION)


@pytest.mark.parametrize("status", sorted(CANCELLABLE_STATUSES, key=lambda s: s.value))
def test_every_active_status_is_cancellable(machine, status) -> None:
    machine.validate_transition(status, S.CANCELLED)


@pytest.mark.parametrize("stage", EXECUTING_STAGES)
def test_needs_attention_resumes_exactly_to_last_resumable_stage(machine, stage) -> None:
    machine.validate_transition(
        S.NEEDS_ATTENTION, stage, last_resumable_stage=stage
    )


# --- illegal transitions (exhaustive high-signal negatives) ---------------------


def test_analysis_cannot_publish_before_quality_gate(machine) -> None:
    # The plan's canonical example: synthesizing -> ready is illegal.
    with pytest.raises(InvalidTransition):
        machine.validate_transition(S.SYNTHESIZING, S.READY)


def test_validating_to_ready_without_quality_gate_is_illegal(machine) -> None:
    with pytest.raises(InvalidTransition):
        machine.validate_transition(S.VALIDATING, S.READY, quality_gate_passed=False)


@pytest.mark.parametrize("terminal", sorted(TERMINAL_STATUSES, key=lambda s: s.value))
@pytest.mark.parametrize(
    "target", [S.PLANNING, S.VALIDATING, S.READY, S.CANCELLED, S.NEEDS_ATTENTION]
)
def test_terminal_states_never_transition(machine, terminal, target) -> None:
    with pytest.raises(InvalidTransition):
        machine.validate_transition(terminal, target)


def test_cancelled_forbids_publication_flavored_targets(machine) -> None:
    with pytest.raises(InvalidTransition):
        machine.validate_transition(S.CANCELLED, S.READY)


def test_stage_skipping_is_illegal(machine) -> None:
    with pytest.raises(InvalidTransition):
        machine.validate_transition(S.PLANNING, S.ANALYZING)
    with pytest.raises(InvalidTransition):
        machine.validate_transition(S.RETRIEVING, S.CRITICIZING)


def test_backward_stage_movement_is_illegal(machine) -> None:
    with pytest.raises(InvalidTransition):
        machine.validate_transition(S.CRITICIZING, S.ANALYZING)


def test_queued_is_never_a_target(machine) -> None:
    with pytest.raises(InvalidTransition):
        machine.validate_transition(S.PLANNING, S.QUEUED)


def test_queued_must_start_at_planning(machine) -> None:
    with pytest.raises(InvalidTransition):
        machine.validate_transition(S.QUEUED, S.RETRIEVING)


def test_blocked_only_from_validating(machine) -> None:
    for stage in (S.QUEUED, S.PLANNING, S.SYNTHESIZING, S.NEEDS_ATTENTION):
        with pytest.raises(InvalidTransition):
            machine.validate_transition(
                stage, S.BLOCKED, last_resumable_stage=S.PLANNING
            )


def test_needs_attention_only_from_executing_stages(machine) -> None:
    with pytest.raises(InvalidTransition):
        machine.validate_transition(S.QUEUED, S.NEEDS_ATTENTION)


def test_resume_to_wrong_stage_is_illegal(machine) -> None:
    with pytest.raises(InvalidTransition):
        machine.validate_transition(
            S.NEEDS_ATTENTION, S.SYNTHESIZING, last_resumable_stage=S.RETRIEVING
        )


def test_resume_without_persisted_stage_is_illegal(machine) -> None:
    with pytest.raises(InvalidTransition):
        machine.validate_transition(
            S.NEEDS_ATTENTION, S.PLANNING, last_resumable_stage=None
        )


def test_needs_attention_cannot_go_terminal_except_cancel(machine) -> None:
    with pytest.raises(InvalidTransition):
        machine.validate_transition(
            S.NEEDS_ATTENTION, S.READY, last_resumable_stage=S.VALIDATING
        )
    machine.validate_transition(S.NEEDS_ATTENTION, S.CANCELLED)


def test_next_stage_sequence_is_canonical() -> None:
    assert next_stage(S.PLANNING) == S.RETRIEVING
    assert next_stage(S.VALIDATING) is None


# --- charter machine ------------------------------------------------------------


def test_charter_legal_lifecycle() -> None:
    validate_charter_transition("draft", "awaiting_confirmation")
    validate_charter_transition("awaiting_confirmation", "confirmed")
    validate_charter_transition("confirmed", "superseded")


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("draft", "confirmed"),
        ("draft", "superseded"),
        ("confirmed", "draft"),
        ("confirmed", "awaiting_confirmation"),
        ("superseded", "confirmed"),
        ("superseded", "draft"),
    ],
)
def test_charter_illegal_edges(current: str, target: str) -> None:
    with pytest.raises(InvalidTransition):
        validate_charter_transition(current, target)


def test_focused_lens_set_must_be_empty() -> None:
    assert normalize_lens_set("focused", []) == []
    with pytest.raises(InvalidCharter):
        normalize_lens_set("focused", ["porter_five_forces"])


def test_full_lens_set_normalizes_to_canonical_five(monkeypatch) -> None:
    shuffled = [
        "meadows_leverage_points",
        "porter_five_forces",
        "scenario_planning",
        "pre_mortem",
        "counterparty_response_matrix",
    ]
    assert normalize_lens_set("full", shuffled) == list(FULL_LENS_SET)


@pytest.mark.parametrize(
    "bad_set",
    [
        [],
        ["porter_five_forces"],
        ["porter_five_forces", "pre_mortem", "counterparty_response_matrix",
         "scenario_planning"],
        ["porter_five_forces", "pre_mortem", "counterparty_response_matrix",
         "scenario_planning", "meadows_leverage_points", "porter_five_forces"],
        ["porter_five_forces", "pre_mortem", "counterparty_response_matrix",
         "scenario_planning", "swot"],
    ],
)
def test_full_lens_set_rejects_partial_duplicate_or_foreign_sets(bad_set) -> None:
    with pytest.raises(InvalidCharter):
        normalize_lens_set("full", bad_set)


def test_quick_is_not_a_formal_level() -> None:
    with pytest.raises(InvalidCharter):
        normalize_lens_set("quick", [])


def test_diff_frozen_fields_detects_lens_set_change() -> None:
    old = {"strategic_lens_set": list(FULL_LENS_SET), "budget": {"a": 1}}
    new = {"strategic_lens_set": list(FULL_LENS_SET[:-1])}
    assert diff_frozen_fields(old, new) == ["strategic_lens_set"]


def test_diff_frozen_fields_ignores_untouched_and_equal_fields() -> None:
    old = {"budget": {"a": 1}, "decision_question": "q"}
    assert diff_frozen_fields(old, {"budget": {"a": 1}}) == []
    assert diff_frozen_fields(old, {}) == []
    assert diff_frozen_fields(old, {"budget": {"a": 2}}) == ["budget"]
