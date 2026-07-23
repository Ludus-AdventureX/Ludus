from __future__ import annotations

import pytest

from app.methods.router import CynefinOverrideError, evaluate_cynefin_gate


@pytest.mark.parametrize(
    ("domain", "action", "level", "formal", "override_required"),
    [
        ("clear", "proceed_quick", "quick", False, True),
        ("complicated", "proceed_focused", "focused", True, False),
        ("complex", "proceed_full", "full", True, False),
        ("chaotic", "stabilize_first", "quick", False, True),
        ("disorder", "clarify_scope", "quick", False, True),
    ],
)
def test_cynefin_defaults_are_manifest_locked(
    domain: str,
    action: str,
    level: str,
    formal: bool,
    override_required: bool,
) -> None:
    result = evaluate_cynefin_gate(domain)

    assert result.default_action == action
    assert result.recommended_analysis_level == level
    assert result.formal_analysis_allowed is formal
    assert result.override_required is override_required


def test_complex_gate_requires_safe_to_fail_and_review_contract() -> None:
    result = evaluate_cynefin_gate("complex")

    assert result.safe_to_fail_probes
    assert result.review_triggers


def test_chaotic_formal_override_requires_auditable_human_identity() -> None:
    with pytest.raises(CynefinOverrideError):
        evaluate_cynefin_gate("chaotic", requested_level="full")

    result = evaluate_cynefin_gate(
        "chaotic",
        requested_level="focused",
        override_user_id="user-1",
        override_reason="人类确认先做有界试验",
    )

    assert result.formal_analysis_allowed is True
    assert result.overridden_by_user_id == "user-1"
    assert result.override_reason


def test_partial_override_fields_are_rejected() -> None:
    with pytest.raises(CynefinOverrideError):
        evaluate_cynefin_gate("disorder", override_user_id="user-1")

def test_complex_gate_honors_requested_focused_level() -> None:
    result = evaluate_cynefin_gate("complex", requested_level="focused")

    assert result.recommended_analysis_level == "focused"
    assert result.default_action == "proceed_focused"
    assert result.formal_analysis_allowed is True


def test_unknown_requested_analysis_level_is_rejected() -> None:
    with pytest.raises(CynefinOverrideError, match="unsupported requested analysis level"):
        evaluate_cynefin_gate("complex", requested_level="deep")
