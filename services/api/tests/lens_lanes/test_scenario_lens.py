"""Scenario-planning lens behavior tests (lane 9, staged for QA adoption).

Converted from the lane's disposable G0 smoke script into a repository test:
frozen pack schema validation, the 15 targeted behavior negatives, seam
server-owned-field rejection, deterministic simulation-seed mapping and option
coverage. No DB and no network required.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from app.agents.errors import LensBehaviorError, ServerOwnedFieldError
from app.agents.lenses import LensRegistry, LensRequest, StrategicLensStageOutput
from app.strategic_lenses.lenses.scenario_planning import (
    IMPLEMENTATION,
    build_scenario_candidates,
    validate_option_coverage,
)
from app.types import StrategicLensType

REPO_ROOT = Path(__file__).resolve().parents[4]
PACK = REPO_ROOT / "method-packs" / "hardtech-market-direction" / "1.1.0"
LENS_SCHEMA = json.loads((PACK / "schemas" / "strategic-lens-output.schema.json").read_text("utf-8"))
SEEDS_SCHEMA = json.loads((PACK / "schemas" / "simulation-seeds.schema.json").read_text("utf-8"))

AXIS_LOW_1, AXIS_HIGH_1 = "tender cycle within 12 months", "tender cycle beyond 24 months"
AXIS_LOW_2, AXIS_HIGH_2 = "household adoption stays niche", "household adoption goes mainstream"


def _signal(sid: str) -> dict:
    return {
        "signalId": sid,
        "type": "quantitative",
        "observable": f"observable metric for {sid}",
        "thresholdOrPattern": "3 consecutive monthly readings above trend",
        "cadence": "monthly",
    }


def _frame(fid: str, kind: str, axis_states: list[str], sids: list[str]) -> dict:
    return {
        "scenarioId": fid,
        "name": f"Frame {fid}",
        "kind": kind,
        "axisStates": axis_states,
        "coreLogic": f"Internally consistent structural logic for {fid}.",
        "timeline": [
            {"period": "0-12m", "turningPoint": f"First structural turning point in {fid}."},
            {"period": "12-36m", "turningPoint": f"Second structural turning point in {fid}."},
        ],
        "stakeholderStates": [
            {"stakeholder": "rescue agencies", "state": f"Procurement posture in {fid}."},
            {"stakeholder": "home consumers", "state": f"Adoption posture in {fid}."},
            {"stakeholder": "competitors", "state": f"Competitive posture in {fid}."},
        ],
        "earlySignals": [_signal(s) for s in sids],
    }


def _content() -> dict[str, Any]:
    return {
        "focusQuestion": (
            "Should the resource-constrained spherical robot venture enter the rescue "
            "market first or the home service market first?"
        ),
        "timeHorizon": "36 months (charter review window)",
        "predeterminedElements": [
            "BOM cost floor of current drivetrain generation is locked for 24 months",
            "EU machinery directive revision takes effect within the horizon",
        ],
        "keyUncertainties": [
            {
                "uncertaintyId": "unc-procurement",
                "factor": "Government rescue procurement cycle length and budget release rhythm",
                "impact": "high",
                "uncertainty": "high",
                "evidenceIds": ["ev-tender-2025", "ev-budget-cycle"],
            },
            {
                "uncertaintyId": "unc-adoption",
                "factor": "Household adoption speed for autonomous service robots",
                "impact": "high",
                "uncertainty": "high",
                "evidenceIds": ["ev-consumer-survey"],
            },
        ],
        "axes": [
            {
                "axisId": "axis-procurement",
                "uncertaintyId": "unc-procurement",
                "lowState": AXIS_LOW_1,
                "highState": AXIS_HIGH_1,
                "selectionRationale": "Highest impact x uncertainty pair on cash runway.",
            },
            {
                "axisId": "axis-adoption",
                "uncertaintyId": "unc-adoption",
                "lowState": AXIS_LOW_2,
                "highState": AXIS_HIGH_2,
                "selectionRationale": "Determines whether home revenue can fund R&D.",
            },
        ],
        "scenarios": [
            _frame("sc-steady", "baseline", [AXIS_LOW_1, AXIS_LOW_2], ["sig-s1", "sig-s2", "sig-s3"]),
            _frame("sc-frozen", "structural_break", [AXIS_HIGH_1, AXIS_LOW_2], ["sig-f1", "sig-f2", "sig-f3"]),
            _frame("sc-boom", "structural_break", [AXIS_LOW_1, AXIS_HIGH_2], ["sig-b1", "sig-b2", "sig-b3"]),
        ],
        "strategyTests": [
            {
                "scenarioId": "sc-steady",
                "optionId": "opt-rescue",
                "performance": "viable_with_adjustment",
                "failureReason": "Slow but predictable tenders compress margin, not viability.",
                "requiredAdjustment": "Pre-qualify with two regional agencies before award season.",
                "triggerSignalIds": ["sig-s1"],
            },
            {
                "scenarioId": "sc-steady",
                "optionId": "opt-home",
                "performance": "viable_with_adjustment",
                "failureReason": "Niche adoption keeps volumes below contribution breakeven.",
                "requiredAdjustment": "Restrict SKU to premium early-adopter bundle.",
                "triggerSignalIds": ["sig-s2"],
            },
            {
                "scenarioId": "sc-frozen",
                "optionId": "opt-rescue",
                "performance": "killed",
                "failureReason": "24m+ tender cycles exhaust runway before first award lands.",
                "requiredAdjustment": "Exit trigger: pivot budget to home pilot within one quarter.",
                "triggerSignalIds": ["sig-f1", "sig-f2"],
            },
            {
                "scenarioId": "sc-frozen",
                "optionId": "opt-home",
                "performance": "high_risk",
                "failureReason": "Niche adoption plus frozen tenders squeezes both channels.",
                "requiredAdjustment": "Cut burn to survival mode; renegotiate supplier terms.",
                "triggerSignalIds": ["sig-f3"],
            },
            {
                "scenarioId": "sc-boom",
                "optionId": "opt-rescue",
                "performance": "high_risk",
                "failureReason": "Opportunity cost: rescue focus forfeits the adoption window.",
                "requiredAdjustment": "License rescue IP; shift assembly line to home units.",
                "triggerSignalIds": ["sig-b1"],
            },
            {
                "scenarioId": "sc-boom",
                "optionId": "opt-home",
                "performance": "robust",
                "failureReason": "No structural failure identified in this frame.",
                "requiredAdjustment": "Scale channel partnerships ahead of demand curve.",
                "triggerSignalIds": ["sig-b2", "sig-b3"],
            },
        ],
        "strategyKilledInAtLeastOneScenario": True,
        "monitoringActions": [
            "Track quarterly tender publication volume in target rescue regions",
            "Track monthly sell-through of comparable home service robots",
        ],
        "irreducibleUnknowns": [
            "Timing of the next major disaster-driven emergency budget release",
        ],
    }


def _payload() -> dict[str, Any]:
    return {
        "lensType": "scenario_planning",
        "sourceSkillVersion": "1.0.0",
        "phase": "strategic_synthesis",
        "references": {
            "sourcePacketIds": ["rp-01"],
            "claimIds": ["cl-01"],
            "evidenceIds": ["ev-tender-2025", "ev-budget-cycle", "ev-consumer-survey"],
            "assumptionIds": ["as-01"],
            "challengeIds": [],
        },
        "researchRequests": [],
        "content": _content(),
    }


@pytest.fixture()
def payload() -> dict[str, Any]:
    return _payload()


@pytest.fixture()
def output(payload: dict[str, Any]) -> StrategicLensStageOutput:
    return StrategicLensStageOutput.from_payload(payload)


def test_pack_schema_accepts_sample(payload: dict[str, Any]) -> None:
    jsonschema.validate(payload, LENS_SCHEMA)


def test_behavior_gate_passes_sample(output: StrategicLensStageOutput) -> None:
    report = IMPLEMENTATION.validate_behavior(output)
    assert report.ok, report.reason_codes


_MUTATIONS = {
    "predetermined_elements_missing": lambda c: c.update(predeterminedElements=[]),
    "key_uncertainties_insufficient": lambda c: c.update(keyUncertainties=c["keyUncertainties"][:1]),
    "axes_count_not_two": lambda c: c.update(axes=c["axes"][:1]),
    "axes_not_distinct": lambda c: c["axes"][1].update(uncertaintyId="unc-procurement"),
    "axis_not_high_impact_high_uncertainty": lambda c: c["keyUncertainties"][0].update(
        uncertainty="medium"
    ),
    "scenario_count_out_of_range": lambda c: c.update(scenarios=c["scenarios"][:2]),
    "baseline_count_not_one": lambda c: c["scenarios"][0].update(kind="structural_break"),
    "scenario_axis_states_not_distinct": lambda c: c["scenarios"][2].update(
        axisStates=list(c["scenarios"][1]["axisStates"])
    ),
    "stakeholder_states_insufficient": lambda c: c["scenarios"][0].update(
        stakeholderStates=c["scenarios"][0]["stakeholderStates"][:2]
    ),
    "early_signals_out_of_range": lambda c: c["scenarios"][0].update(
        earlySignals=c["scenarios"][0]["earlySignals"][:2]
    ),
    "no_strategy_killed": lambda c: c["strategyTests"][2].update(performance="high_risk"),
    "strategy_matrix_incomplete": lambda c: c.update(strategyTests=c["strategyTests"][:5]),
    "trigger_signal_unresolved": lambda c: c["strategyTests"][0].update(
        triggerSignalIds=["sig-nowhere"]
    ),
    "content_evidence_not_declared": lambda c: c["keyUncertainties"][0]["evidenceIds"].append(
        "ev-invented"
    ),
    "probability_language_present": lambda c: c["scenarios"][0].update(
        coreLogic="This frame has a 70% probability of occurring."
    ),
}


@pytest.mark.parametrize("expected_code", sorted(_MUTATIONS))
def test_behavior_gate_rejects_mutation(expected_code: str) -> None:
    mutated = copy.deepcopy(_payload())
    _MUTATIONS[expected_code](mutated["content"])
    bad = StrategicLensStageOutput.from_payload(mutated)
    report = IMPLEMENTATION.validate_behavior(bad)
    assert not report.ok
    assert expected_code in report.reason_codes, report.reason_codes


def test_server_owned_field_rejected(payload: dict[str, Any]) -> None:
    with pytest.raises(ServerOwnedFieldError):
        StrategicLensStageOutput.from_payload({**payload, "workspaceId": "ws-1"})


def test_seed_candidates_match_frozen_seeds_schema(output: StrategicLensStageOutput) -> None:
    candidates = build_scenario_candidates(output, source_lens_artifact_id="lens-art-01")
    candidate_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": "#/$defs/scenarioCandidate",
        "$defs": SEEDS_SCHEMA["$defs"],
    }
    for candidate in candidates:
        jsonschema.validate(candidate, candidate_schema)
    assert [c["strategySurvives"] for c in candidates] == [True, False, True]
    assert [c["kind"] for c in candidates] == ["baseline", "structural_break", "structural_break"]
    assert [
        [d["proposedNormalizedShift"] for d in c["driverStates"]] for c in candidates
    ] == [[-0.5, -0.5], [0.5, -0.5], [-0.5, 0.5]]
    assert all("riskTolerance" not in c for c in candidates)


def test_seed_focal_never_killed_fails_closed(output: StrategicLensStageOutput) -> None:
    with pytest.raises(LensBehaviorError) as excinfo:
        build_scenario_candidates(
            output, source_lens_artifact_id="lens-art-01", focal_option_id="opt-home"
        )
    assert "focal_option_never_killed" in excinfo.value.reason_codes


def test_seed_focal_killed_marks_frame_non_survivable(output: StrategicLensStageOutput) -> None:
    focal = build_scenario_candidates(
        output, source_lens_artifact_id="lens-art-01", focal_option_id="opt-rescue"
    )
    assert [c["strategySurvives"] for c in focal] == [True, False, True]


def test_option_coverage_cross_check(output: StrategicLensStageOutput) -> None:
    assert validate_option_coverage(output, ["opt-rescue", "opt-home"]).ok
    missing = validate_option_coverage(output, ["opt-rescue", "opt-home", "opt-license"])
    assert not missing.ok
    assert "charter_option_untested" in missing.reason_codes


def test_registry_accepts_implementation() -> None:
    registry = LensRegistry()
    registry.register(IMPLEMENTATION)
    assert registry.registered() == frozenset({StrategicLensType.SCENARIO_PLANNING})


def test_prompt_inputs_deterministic() -> None:
    request = LensRequest(
        lens_type=StrategicLensType.SCENARIO_PLANNING,
        workspace_id="ws-01",
        analysis_run_id="run-01",
        prompt_text="frozen pack prompt text",
        evidence_refs=("ev-tender-2025", "ev-budget-cycle", "ev-consumer-survey"),
        option_ids=("opt-rescue", "opt-home"),
    )
    first = IMPLEMENTATION.build_prompt_inputs(request)
    second = IMPLEMENTATION.build_prompt_inputs(request)
    assert first == second
    assert first.system == "frozen pack prompt text"
    assert first.schema_content_def == "scenarioPlanningContent"
