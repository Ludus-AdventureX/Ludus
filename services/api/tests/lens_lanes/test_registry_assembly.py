"""Five-lens registry assembly and seam-compatibility tests (Coordinator-owned).

Verifies the explicit registry builds the exact canonical five-lens set, every
implementation satisfies the shared ``LensImplementation`` protocol, the two
adapter-wrapped lanes (pre_mortem, meadows) keep their fixture verdicts intact
through the seam, and prompt assembly stays deterministic per lens. No DB.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agents.lenses import (
    LENS_SPECS,
    LensImplementation,
    LensRequest,
    StrategicLensStageOutput,
)
from app.strategic_lenses.registry import build_lens_registry
from app.types import FULL_REQUIRED_STRATEGIC_LENSES, StrategicLensType

REPO_ROOT = Path(__file__).resolve().parents[4]
FIXTURES = REPO_ROOT / "fixtures" / "spherical-robot"


def _load(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


def test_registry_builds_exact_five_lens_set() -> None:
    registry = build_lens_registry()
    assert registry.registered() == frozenset(FULL_REQUIRED_STRATEGIC_LENSES)
    registry.require_full_set()


def test_every_implementation_satisfies_seam_protocol() -> None:
    registry = build_lens_registry()
    for lens_type in FULL_REQUIRED_STRATEGIC_LENSES:
        impl = registry.get(lens_type)
        assert isinstance(impl, LensImplementation)
        assert impl.lens_type == lens_type


@pytest.mark.parametrize("lens_type", list(FULL_REQUIRED_STRATEGIC_LENSES))
def test_prompt_assembly_is_deterministic(lens_type: StrategicLensType) -> None:
    registry = build_lens_registry()
    impl = registry.get(lens_type)
    request = LensRequest(
        lens_type=lens_type,
        workspace_id="ws-01",
        analysis_run_id="run-01",
        prompt_text=f"frozen prompt for {lens_type.value}",
        research_packet_refs=("rp-1", "rp-2"),
        evidence_refs=("ev-1", "ev-2"),
        option_ids=("opt-rescue", "opt-home"),
    )
    first = impl.build_prompt_inputs(request)
    second = impl.build_prompt_inputs(request)
    assert first == second
    assert first.system == f"frozen prompt for {lens_type.value}"
    assert first.schema_content_def == LENS_SPECS[lens_type].content_def


@pytest.mark.parametrize("lens_type", list(FULL_REQUIRED_STRATEGIC_LENSES))
def test_every_lens_user_message_carries_output_contract(lens_type: StrategicLensType) -> None:
    """Every lens must tell the model about the full top-level schema.

    Live full runs previously lost all five lenses to ``KeyError: 'references'``
    because the user prompts never mentioned the references field. This test
    pins the shared contract into every lane so a future prompt edit cannot
    silently drop it again.
    """

    registry = build_lens_registry()
    impl = registry.get(lens_type)
    request = LensRequest(
        lens_type=lens_type,
        workspace_id="ws-01",
        analysis_run_id="run-01",
        prompt_text=f"frozen prompt for {lens_type.value}",
        research_packet_refs=("rp-1", "rp-2"),
        evidence_refs=("ev-1", "ev-2"),
        option_ids=("opt-rescue", "opt-home"),
    )
    user = impl.build_prompt_inputs(request).user
    assert "Output contract (MANDATORY)" in user
    assert '"references"' in user or "references:" in user
    for key in ("sourcePacketIds", "claimIds", "evidenceIds", "assumptionIds", "challengeIds"):
        assert key in user
    # The content-branch schema definition must ride in the same message: the
    # published prompts only cite the schema URN, so without this the model
    # free-styles content and every behavior gate rejects the shape.
    content_def = LENS_SPECS[lens_type].content_def
    assert content_def in user
    assert "$defs" in user or "type\": \"object" in user
    # Lenses whose gates demand nested array-element fields (porter, scenario,
    # meadows) must also carry a complete gate-passing content example.
    if lens_type in (
        StrategicLensType.PORTER_FIVE_FORCES,
        StrategicLensType.SCENARIO_PLANNING,
        StrategicLensType.MEADOWS_LEVERAGE_POINTS,
    ):
        assert "Example content" in user
        assert "ev-sample-" in user


def test_pre_mortem_adapter_keeps_fixture_verdicts() -> None:
    registry = build_lens_registry()
    impl = registry.get(StrategicLensType.PRE_MORTEM)

    expected = _load(FIXTURES / "expected" / "strategic-lenses" / "pre_mortem.json")
    good = impl.validate_behavior(StrategicLensStageOutput.from_payload(expected))
    assert good.ok, good.reason_codes

    negative = _load(
        FIXTURES / "negative" / "strategic-lenses" / "pre_mortem_missing_top_risk_control.json"
    )
    bad = impl.validate_behavior(StrategicLensStageOutput.from_payload(negative))
    assert not bad.ok
    assert "PM_TOP_RISK_CONTROL_MISSING" in bad.reason_codes


def test_counterparty_fixtures_hold_through_seam() -> None:
    registry = build_lens_registry()
    impl = registry.get(StrategicLensType.COUNTERPARTY_RESPONSE_MATRIX)

    expected = _load(
        FIXTURES / "expected" / "strategic-lenses" / "counterparty_response_matrix.json"
    )
    good = impl.validate_behavior(StrategicLensStageOutput.from_payload(expected))
    assert good.ok, good.reason_codes

    negative = _load(
        FIXTURES
        / "negative"
        / "strategic-lenses"
        / "counterparty_response_matrix_missing_no_action.json"
    )
    bad = impl.validate_behavior(StrategicLensStageOutput.from_payload(negative))
    assert not bad.ok


def test_meadows_adapter_rejects_behavior_violation() -> None:
    registry = build_lens_registry()
    impl = registry.get(StrategicLensType.MEADOWS_LEVERAGE_POINTS)
    # Minimal envelope with schema-shaped but behavior-empty content must fail
    # closed through the adapter rather than raising an unhandled error.
    payload = {
        "lensType": "meadows_leverage_points",
        "sourceSkillVersion": "1.0.0",
        "phase": "strategic_synthesis",
        "references": {
            "sourcePacketIds": [],
            "claimIds": [],
            "evidenceIds": ["ev-1"],
            "assumptionIds": [],
            "challengeIds": [],
        },
        "researchRequests": [],
        "content": {},
    }
    report = impl.validate_behavior(StrategicLensStageOutput.from_payload(payload))
    assert not report.ok
    assert report.reason_codes
