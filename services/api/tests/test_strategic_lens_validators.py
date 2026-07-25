"""Task 10 Step 5 behavior-validator tests for the five strategic lenses.

Pure-function coverage of ``app.strategic_lenses.validators`` against the
behavior table in 18-detailed-development-plan L1072-L1076: one complete
positive sample per lens (schema-checked against the published pack schema)
plus at least one negative sample per hard assertion. No DB, no network.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from app.agents.errors import UnknownLensType
from app.strategic_lenses.validators import (
    CODE_CONTENT_NOT_OBJECT,
    LENS_BEHAVIOR_VALIDATORS,
    ResolvedLensReferences,
    normalize_pre_mortem_code,
    validate_counterparty_response_matrix,
    validate_lens_behavior,
    validate_meadows_leverage_points,
    validate_porter_five_forces,
    validate_pre_mortem,
    validate_scenario_planning,
)
from app.types import FULL_REQUIRED_STRATEGIC_LENSES, StrategicLensType

REPO_ROOT = Path(__file__).resolve().parents[3]
PACK_SCHEMA_PATH = (
    REPO_ROOT
    / "method-packs"
    / "hardtech-market-direction"
    / "1.1.0"
    / "schemas"
    / "strategic-lens-output.schema.json"
)
FIXTURES = REPO_ROOT / "fixtures" / "spherical-robot"
PRE_MORTEM_FIXTURE = FIXTURES / "expected" / "strategic-lenses" / "pre_mortem.json"
COUNTERPARTY_FIXTURE = (
    FIXTURES / "expected" / "strategic-lenses" / "counterparty_response_matrix.json"
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def pack_schema_validator() -> Draft202012Validator:
    return Draft202012Validator(load_json(PACK_SCHEMA_PATH))


def assert_pack_schema_ok(validator: Draft202012Validator, payload: dict[str, Any]) -> None:
    errors = sorted(validator.iter_errors(payload), key=str)
    assert not errors, [error.message for error in errors]


def envelope(
    lens_type: StrategicLensType,
    phase: str,
    references: dict[str, list[str]],
    content: dict[str, Any],
) -> dict[str, Any]:
    return {
        "lensType": lens_type.value,
        "sourceSkillVersion": "1.0.0",
        "phase": phase,
        "references": references,
        "researchRequests": [],
        "content": content,
    }


# --- Porter Five Forces golden sample (spherical-robot, lane-7 style) -------------

PORTER_EVIDENCE_IDS = tuple(f"ev-sr-{i:03d}" for i in range(1, 21))
OPTION_RESCUE = "option-rescue-market"
OPTION_HOME = "option-home-service-market"
PORTER_FORCE_IDS = ("buyer_power", "new_entrants", "rivalry", "substitutes", "supplier_power")


def porter_force(force_id: str, start: int, score: int = 3) -> dict[str, Any]:
    return {
        "forceId": force_id,
        "threatScore": score,
        "keyIndicators": [f"{force_id} concentration", f"{force_id} growth"],
        "evidenceIds": [PORTER_EVIDENCE_IDS[start], PORTER_EVIDENCE_IDS[start + 1]],
        "reasoning": f"{force_id} pressure grounded in gated evidence.",
        "directionOfChange": "stable",
    }


def porter_market(option_id: str, offset: int) -> dict[str, Any]:
    return {
        "optionId": option_id,
        "industryBoundary": {
            "coreValue": "Mobile spherical robot platform for the segment.",
            "upstream": ["drive units", "battery packs", "sensor suppliers"],
            "downstream": ["fire departments" if "rescue" in option_id else "families"],
            "adjacentMarkets": ["inspection robots"],
            "crossIndustrySubstitutes": ["drones", "fixed cameras"],
            "boundaryRisk": "Too-wide 'robotics' framing hides segment buyers.",
        },
        "forces": [
            porter_force(force_id, offset + i * 2)
            for i, force_id in enumerate(PORTER_FORCE_IDS)
        ],
        "averageThreatScore": 3.0,
        "changingTrend": "Public procurement standards for rescue robotics are "
        "tightening, shifting entry barriers year over year.",
        "regulatoryAssessment": "Safety certification and emergency-services "
        "procurement rules assessed separately, not averaged as a sixth force.",
        "complementors": ["thermal cameras", "incident-management software"],
    }


def porter_content() -> dict[str, Any]:
    return {
        "marketAnalyses": [porter_market(OPTION_RESCUE, 0), porter_market(OPTION_HOME, 10)],
        "crossMarketComparison": "Rescue shows weaker buyer power but tighter "
        "regulatory gates than home service; profiles differ per force.",
        "strategicImplications": [
            {
                "optionId": OPTION_RESCUE,
                "strategy": "focus",
                "logic": "High entry barriers plus concentrated buyers reward a "
                "focused rescue niche, per rivalry and buyer-power evidence.",
                "conditions": ["Certification achieved within 12 months."],
            }
        ],
        "scoreIsNotDecisionFormula": True,
    }


def porter_references_wire() -> dict[str, list[str]]:
    return {
        "sourcePacketIds": ["rp-sr-001", "rp-sr-002"],
        "claimIds": ["claim-sr-001"],
        "evidenceIds": list(PORTER_EVIDENCE_IDS),
        "assumptionIds": ["asm-sr-001"],
        "challengeIds": [],
    }


def porter_refs() -> ResolvedLensReferences:
    return ResolvedLensReferences.from_wire(porter_references_wire())


# --- Scenario planning golden sample (spherical-robot, lane-9 style) --------------

AXIS_LOW_1, AXIS_HIGH_1 = "tender cycle within 12 months", "tender cycle beyond 24 months"
AXIS_LOW_2, AXIS_HIGH_2 = "household adoption stays niche", "household adoption goes mainstream"


def scenario_signal(sid: str) -> dict[str, Any]:
    return {
        "signalId": sid,
        "type": "quantitative",
        "observable": f"observable metric for {sid}",
        "thresholdOrPattern": "3 consecutive monthly readings above trend",
        "cadence": "monthly",
    }


def scenario_frame(fid: str, kind: str, axis_states: list[str], sids: list[str]) -> dict[str, Any]:
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
        "earlySignals": [scenario_signal(s) for s in sids],
    }


def scenario_test(
    scenario_id: str, option_id: str, performance: str, signals: list[str]
) -> dict[str, Any]:
    return {
        "scenarioId": scenario_id,
        "optionId": option_id,
        "performance": performance,
        "failureReason": f"Structural outcome for {option_id} in {scenario_id}.",
        "requiredAdjustment": f"Adjustment path for {option_id} in {scenario_id}.",
        "triggerSignalIds": signals,
    }


def scenario_content() -> dict[str, Any]:
    return {
        "focusQuestion": "Should the venture enter the rescue market first or the home "
        "service market first?",
        "timeHorizon": "36 months (charter review window)",
        "predeterminedElements": [
            "BOM cost floor of current drivetrain generation is locked for 24 months",
            "EU machinery directive revision takes effect within the horizon",
        ],
        "keyUncertainties": [
            {
                "uncertaintyId": "unc-procurement",
                "factor": "Government rescue procurement cycle length and budget rhythm",
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
            scenario_frame(
                "sc-steady", "baseline", [AXIS_LOW_1, AXIS_LOW_2], ["sig-s1", "sig-s2", "sig-s3"]
            ),
            scenario_frame(
                "sc-frozen",
                "structural_break",
                [AXIS_HIGH_1, AXIS_LOW_2],
                ["sig-f1", "sig-f2", "sig-f3"],
            ),
            scenario_frame(
                "sc-boom",
                "structural_break",
                [AXIS_LOW_1, AXIS_HIGH_2],
                ["sig-b1", "sig-b2", "sig-b3"],
            ),
        ],
        "strategyTests": [
            scenario_test("sc-steady", "opt-rescue", "viable_with_adjustment", ["sig-s1"]),
            scenario_test("sc-steady", "opt-home", "viable_with_adjustment", ["sig-s2"]),
            scenario_test("sc-frozen", "opt-rescue", "killed", ["sig-f1", "sig-f2"]),
            scenario_test("sc-frozen", "opt-home", "high_risk", ["sig-f3"]),
            scenario_test("sc-boom", "opt-rescue", "high_risk", ["sig-b1"]),
            scenario_test("sc-boom", "opt-home", "robust", ["sig-b2", "sig-b3"]),
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


def scenario_references_wire() -> dict[str, list[str]]:
    return {
        "sourcePacketIds": ["rp-01"],
        "claimIds": ["cl-01"],
        "evidenceIds": ["ev-tender-2025", "ev-budget-cycle", "ev-consumer-survey"],
        "assumptionIds": ["as-01"],
        "challengeIds": [],
    }


def scenario_refs() -> ResolvedLensReferences:
    return ResolvedLensReferences.from_wire(scenario_references_wire())


# --- Meadows golden sample (spherical-robot, lane-11 payload) ----------------------


def meadows_intervention(
    intervention_id: str, level: int, level_name: str, band: str
) -> dict[str, Any]:
    return {
        "interventionId": intervention_id,
        "level": level,
        "levelName": level_name,
        "strengthBand": band,
        "target": f"target of {intervention_id}",
        "action": f"deterministic action of {intervention_id}",
        "feasibility": "medium",
        "expectedEffect": f"expected effect of {intervention_id}",
        "failureSignal": f"failure signal of {intervention_id}",
    }


def meadows_sequence_step(order: int, intervention_id: str, purpose: str) -> dict[str, Any]:
    return {
        "order": order,
        "interventionId": intervention_id,
        "purpose": purpose,
        "precondition": f"precondition before {intervention_id}",
        "failureSignal": f"failure signal while running {intervention_id}",
    }


def meadows_content() -> dict[str, Any]:
    gap = meadows_intervention("MI-3-goal", 3, "goals", "high")
    gap["whyAvoided"] = "Founders carry sunk-cost attachment to the dual-market story."
    gap["disruptionRisk"] = "Narrowing the goal may trigger household-line attrition."
    return {
        "systemMap": {
            "boundary": "Market-entry system of the spherical robot venture over 18 months.",
            "statedGoal": "Explore rescue and household markets in parallel.",
            "actualGoal": "Resource flows show the actual goal is extending the cash runway.",
            "stocks": ["cash reserve", "deployable engineer hours", "rescue validation data"],
            "flows": ["monthly R&D spend", "pilot repayments", "tender-driven lead inflow"],
            "reinforcingLoops": [
                "R1: rescue pilot success -> endorsements -> more pilots -> more data",
                "R2: household marketing spend -> exposure -> presales -> more budget",
            ],
            "balancingLoops": ["B1: R&D spend up -> runway down -> hiring freeze"],
            "delays": ["9-18 month rescue procurement payment delay"],
            "actors": ["founding team", "emergency-management buyers", "seed investors"],
            "rulesAndIncentives": ["certification is mandatory before public tenders"],
        },
        "levelsCovered": [3, 5, 6, 12],
        "currentInterventions": [
            meadows_intervention("MI-12-price", 12, "parameters", "low"),
            meadows_intervention("MI-6-dashboard", 6, "information_flows", "medium"),
            meadows_intervention("MI-5-gate", 5, "rules", "medium"),
        ],
        "highLeverageGaps": [gap],
        "runawayPositiveLoops": [
            {
                "loop": "R2 keeps pulling scarce cash from rescue validation.",
                "runawaySignal": "Marketing spend grows >20% MoM while pilot data stalls.",
                "brake": "Freeze marketing increments and route them back to pilots.",
            }
        ],
        "interventionSequence": [
            meadows_sequence_step(1, "MI-6-dashboard", "information_gain"),
            meadows_sequence_step(2, "MI-5-gate", "trust_building"),
            meadows_sequence_step(3, "MI-3-goal", "system_change"),
        ],
        "riskTradeoffs": [
            "High-leverage goal narrowing is hard to reverse once the line is cut.",
            "Low-leverage price cuts act fast but erode brand position and margin.",
        ],
    }


def meadows_references_wire() -> dict[str, list[str]]:
    return {
        "sourcePacketIds": ["SP-research-1"],
        "claimIds": ["CL-rescue-first"],
        "evidenceIds": ["EV-rescue-tender-2026Q2", "EV-cash-runway-model"],
        "assumptionIds": ["AS-household-presale-conversion"],
        "challengeIds": ["CH-critic-2"],
    }


def meadows_refs() -> ResolvedLensReferences:
    return ResolvedLensReferences.from_wire(meadows_references_wire())


# --- Fixture-backed golden samples --------------------------------------------------


@pytest.fixture()
def pre_mortem_payload() -> dict[str, Any]:
    return load_json(PRE_MORTEM_FIXTURE)


@pytest.fixture()
def counterparty_payload() -> dict[str, Any]:
    return load_json(COUNTERPARTY_FIXTURE)


def refs_of(payload: dict[str, Any]) -> ResolvedLensReferences:
    return ResolvedLensReferences.from_wire(payload["references"])


# --- Porter -------------------------------------------------------------------------


class TestPorterFiveForces:
    def test_positive_sample_passes(self, pack_schema_validator) -> None:
        payload = envelope(
            StrategicLensType.PORTER_FIVE_FORCES,
            "research_interpretation",
            porter_references_wire(),
            porter_content(),
        )
        assert_pack_schema_ok(pack_schema_validator, payload)
        result = validate_porter_five_forces(porter_content(), porter_refs())
        assert result.passed, (result.reason_codes, result.findings)
        assert result.reason_codes == ()
        assert result.repair_input is None

    @pytest.mark.parametrize(
        ("expected_code", "mutate"),
        [
            (
                "fewer_than_two_markets",
                lambda c: c.update(marketAnalyses=c["marketAnalyses"][:1]),
            ),
            (
                "missing_canonical_force",
                lambda c: c["marketAnalyses"][0]["forces"].pop(),
            ),
            (
                "force_evidence_below_minimum",
                lambda c: c["marketAnalyses"][0]["forces"][0].update(
                    evidenceIds=[PORTER_EVIDENCE_IDS[0]]
                ),
            ),
            (
                "force_evidence_not_in_references",
                lambda c: c["marketAnalyses"][0]["forces"][0].update(
                    evidenceIds=["ev-not-resolved-001", "ev-not-resolved-002"]
                ),
            ),
            (
                "industry_boundary_incomplete",
                lambda c: c["marketAnalyses"][0]["industryBoundary"].update(boundaryRisk=" "),
            ),
            (
                "changing_trend_missing",
                lambda c: c["marketAnalyses"][1].update(changingTrend=""),
            ),
            (
                "regulatory_assessment_missing",
                lambda c: c["marketAnalyses"][0].update(regulatoryAssessment=""),
            ),
            (
                "complementors_missing",
                lambda c: c["marketAnalyses"][0].update(complementors=[]),
            ),
            (
                "score_presented_as_decision_formula",
                lambda c: c.update(scoreIsNotDecisionFormula=False),
            ),
        ],
    )
    def test_negative_sample_fails(self, expected_code, mutate) -> None:
        content = porter_content()
        mutate(content)
        result = validate_porter_five_forces(content, porter_refs())
        assert not result.passed
        assert expected_code in result.reason_codes, result.reason_codes
        assert result.repair_input is not None

    def test_schema_pass_but_behavior_fail_is_rejected(self, pack_schema_validator) -> None:
        # A "weighted" average inside the schema's 1-5 range: shape passes,
        # behavior must still fail (validator/schema layering).
        content = porter_content()
        content["marketAnalyses"][0]["averageThreatScore"] = 4.7
        payload = envelope(
            StrategicLensType.PORTER_FIVE_FORCES,
            "research_interpretation",
            porter_references_wire(),
            content,
        )
        assert_pack_schema_ok(pack_schema_validator, payload)
        result = validate_porter_five_forces(content, porter_refs())
        assert not result.passed
        assert "average_score_is_not_descriptive_mean" in result.reason_codes


# --- Pre-Mortem ----------------------------------------------------------------------


class TestPreMortem:
    def test_positive_sample_passes(self, pack_schema_validator, pre_mortem_payload) -> None:
        assert_pack_schema_ok(pack_schema_validator, pre_mortem_payload)
        result = validate_pre_mortem(
            pre_mortem_payload["content"], refs_of(pre_mortem_payload)
        )
        assert result.passed, (result.reason_codes, result.findings)
        assert result.repair_input is None

    @pytest.mark.parametrize(
        ("expected_code", "mutate"),
        [
            (
                "pre_mortem_perspective_set",
                lambda c: c.update(perspectives=["internal", "external"]),
            ),
            (
                "pre_mortem_cause_count",
                lambda c: c.update(failureCauses=c["failureCauses"][:4]),
            ),
            (
                "pre_mortem_top_risk_count",
                lambda c: c.update(topRisks=c["topRisks"][:2]),
            ),
            (
                "pre_mortem_top_risk_rank_duplicate",
                lambda c: c["topRisks"][1].update(rank=1),
            ),
            (
                "pre_mortem_top_risk_cause_ref",
                lambda c: c["topRisks"][0].update(causeId="PM-ghost-cause"),
            ),
            (
                "pre_mortem_top_risk_cause_duplicate",
                lambda c: c["topRisks"][1].update(causeId=c["topRisks"][0]["causeId"]),
            ),
            (
                "pre_mortem_top_risk_control_missing",
                lambda c: c["topRisks"][0].update(detectionIndicator="  "),
            ),
            (
                "pre_mortem_verdict",
                lambda c: c.update(verdict="proceed"),
            ),
            (
                "pre_mortem_verdict_rationale",
                lambda c: c.update(verdictRationale=" "),
            ),
        ],
    )
    def test_negative_sample_fails(self, pre_mortem_payload, expected_code, mutate) -> None:
        content = copy.deepcopy(pre_mortem_payload["content"])
        mutate(content)
        result = validate_pre_mortem(content, refs_of(pre_mortem_payload))
        assert not result.passed
        assert expected_code in result.reason_codes, result.reason_codes
        assert result.repair_input is not None

    def test_all_reason_codes_are_lower_snake(self, pre_mortem_payload) -> None:
        content = copy.deepcopy(pre_mortem_payload["content"])
        content.update(perspectives=["internal"], failureCauses=[], topRisks=[], verdict="x")
        result = validate_pre_mortem(content, refs_of(pre_mortem_payload))
        assert not result.passed
        assert all(code == code.lower() for code in result.reason_codes), result.reason_codes
        assert all(code.startswith("pre_mortem_") for code in result.reason_codes)

    def test_code_normalization_is_mechanical(self) -> None:
        assert normalize_pre_mortem_code("PM_CAUSE_COUNT") == "pre_mortem_cause_count"
        assert normalize_pre_mortem_code("PM_TOP_RISK_RANK") == "pre_mortem_top_risk_rank"


# --- Counterparty response matrix ------------------------------------------------------


def _third_actor(content: dict[str, Any]) -> None:
    extra = copy.deepcopy(content["counterparties"][0])
    extra["counterpartyId"] = "cp-regulator"
    content["counterparties"].append(extra)


def _fourth_action(content: dict[str, Any]) -> None:
    extra = copy.deepcopy(content["ourActions"][0])
    extra["actionId"] = "act-extra"
    extra["description"] = "A fourth materially distinct move outside the 2-3 window."
    content["ourActions"].append(extra)


def _no_action_removed(content: dict[str, Any]) -> None:
    for action in content["ourActions"]:
        if action["actionType"] == "no_action":
            action["actionType"] = "active"


class TestCounterpartyResponseMatrix:
    def test_positive_sample_passes(self, pack_schema_validator, counterparty_payload) -> None:
        assert_pack_schema_ok(pack_schema_validator, counterparty_payload)
        result = validate_counterparty_response_matrix(
            counterparty_payload["content"], refs_of(counterparty_payload)
        )
        assert result.passed, (result.reason_codes, result.findings)
        assert result.repair_input is None

    @pytest.mark.parametrize(
        ("expected_code", "mutate"),
        [
            ("one_to_two_key_actors", _third_actor),
            ("two_to_three_actions_with_exactly_one_no_action", _fourth_action),
            ("two_to_three_actions_with_exactly_one_no_action", _no_action_removed),
            (
                "response_depth_is_one_layer",
                lambda c: c.update(maxResponseDepth=2),
            ),
            (
                "matrix_covers_optimal_worst_likely_window_gap_counterresponse",
                lambda c: c["responseMatrix"].pop(),
            ),
            (
                "publication_test_and_per_action_downside_asymmetry_and_reflexivity",
                lambda c: c["publicationTest"].update(newInformationRevealed=" "),
            ),
            (
                "publication_test_and_per_action_downside_asymmetry_and_reflexivity",
                lambda c: c["downsideAsymmetry"].pop(),
            ),
            (
                "publication_test_and_per_action_downside_asymmetry_and_reflexivity",
                lambda c: c.update(reflexivityWarning="  "),
            ),
        ],
    )
    def test_negative_sample_fails(self, counterparty_payload, expected_code, mutate) -> None:
        content = copy.deepcopy(counterparty_payload["content"])
        mutate(content)
        result = validate_counterparty_response_matrix(content, refs_of(counterparty_payload))
        assert not result.passed
        assert expected_code in result.reason_codes, result.reason_codes
        assert result.repair_input is not None

    def test_unresolved_core_assumption_fails(self, counterparty_payload) -> None:
        refs = refs_of(counterparty_payload)
        starved = ResolvedLensReferences(
            source_packet_ids=refs.source_packet_ids,
            claim_ids=refs.claim_ids,
            evidence_ids=refs.evidence_ids,
            assumption_ids=("asm-runway-12mo",),
            challenge_ids=refs.challenge_ids,
        )
        result = validate_counterparty_response_matrix(
            counterparty_payload["content"], starved
        )
        assert not result.passed
        assert "core_assumptions_must_be_registered_references" in result.reason_codes


# --- Scenario planning ------------------------------------------------------------------


class TestScenarioPlanning:
    def test_positive_sample_passes(self, pack_schema_validator) -> None:
        payload = envelope(
            StrategicLensType.SCENARIO_PLANNING,
            "strategic_synthesis",
            scenario_references_wire(),
            scenario_content(),
        )
        assert_pack_schema_ok(pack_schema_validator, payload)
        result = validate_scenario_planning(scenario_content(), scenario_refs())
        assert result.passed, (result.reason_codes, result.findings)
        assert result.repair_input is None

    @pytest.mark.parametrize(
        ("expected_code", "mutate"),
        [
            (
                "predetermined_elements_missing",
                lambda c: c.update(predeterminedElements=[]),
            ),
            (
                "key_uncertainties_insufficient",
                lambda c: c.update(keyUncertainties=c["keyUncertainties"][:1]),
            ),
            (
                "axes_count_not_two",
                lambda c: c.update(axes=c["axes"][:1]),
            ),
            (
                "scenario_count_out_of_range",
                lambda c: c.update(scenarios=c["scenarios"][:2]),
            ),
            (
                "baseline_count_not_one",
                lambda c: c["scenarios"][0].update(kind="structural_break"),
            ),
            (
                "structural_breaks_insufficient",
                lambda c: c["scenarios"][1].update(kind="baseline"),
            ),
            (
                "timeline_turning_points_insufficient",
                lambda c: c["scenarios"][0].update(timeline=c["scenarios"][0]["timeline"][:1]),
            ),
            (
                "stakeholder_states_insufficient",
                lambda c: c["scenarios"][0].update(
                    stakeholderStates=c["scenarios"][0]["stakeholderStates"][:2]
                ),
            ),
            (
                "early_signals_out_of_range",
                lambda c: c["scenarios"][0].update(
                    earlySignals=c["scenarios"][0]["earlySignals"][:2]
                ),
            ),
            (
                "strategy_matrix_incomplete",
                lambda c: c.update(strategyTests=c["strategyTests"][:5]),
            ),
            (
                "no_strategy_killed",
                lambda c: c["strategyTests"][2].update(performance="high_risk"),
            ),
        ],
    )
    def test_negative_sample_fails(self, expected_code, mutate) -> None:
        content = scenario_content()
        mutate(content)
        result = validate_scenario_planning(content, scenario_refs())
        assert not result.passed
        assert expected_code in result.reason_codes, result.reason_codes
        assert result.repair_input is not None

    def test_schema_pass_but_behavior_fail_is_rejected(self, pack_schema_validator) -> None:
        # Downgrading the only "killed" verdict keeps the shape valid but the
        # per-strategy stress requirement must still fail the lens.
        content = scenario_content()
        content["strategyTests"][2]["performance"] = "robust"
        payload = envelope(
            StrategicLensType.SCENARIO_PLANNING,
            "strategic_synthesis",
            scenario_references_wire(),
            content,
        )
        assert_pack_schema_ok(pack_schema_validator, payload)
        result = validate_scenario_planning(content, scenario_refs())
        assert not result.passed
        assert "no_strategy_killed" in result.reason_codes


# --- Meadows leverage points ---------------------------------------------------------


def _two_level_rebuild(content: dict[str, Any]) -> None:
    # Interventions span only levels {12, 3}; levelsCovered keeps the schema
    # minimum of three entries, so the coverage failure is a behavior verdict.
    price = content["currentInterventions"][0]
    second = copy.deepcopy(price)
    second["interventionId"] = "MI-12-price-b"
    content["currentInterventions"] = [price, second]
    content["interventionSequence"] = [
        meadows_sequence_step(1, "MI-12-price", "risk_control"),
        meadows_sequence_step(2, "MI-3-goal", "system_change"),
    ]
    content["levelsCovered"] = [3, 5, 12]


class TestMeadowsLeveragePoints:
    def test_positive_sample_passes(self, pack_schema_validator) -> None:
        payload = envelope(
            StrategicLensType.MEADOWS_LEVERAGE_POINTS,
            "strategic_synthesis",
            meadows_references_wire(),
            meadows_content(),
        )
        assert_pack_schema_ok(pack_schema_validator, payload)
        result = validate_meadows_leverage_points(meadows_content(), meadows_refs())
        assert result.passed, (result.reason_codes, result.findings)
        assert result.repair_input is None

    @pytest.mark.parametrize(
        ("expected_code", "mutate"),
        [
            (
                "interventions_cover_fewer_than_three_levels",
                _two_level_rebuild,
            ),
            (
                "levels_covered_mismatch",
                lambda c: c.update(levelsCovered=[3, 5, 6]),
            ),
            (
                "sequence_references_unknown_intervention",
                lambda c: c["interventionSequence"][0].update(interventionId="MI-ghost"),
            ),
        ],
    )
    def test_behavior_negative_sample_fails(self, expected_code, mutate) -> None:
        content = meadows_content()
        mutate(content)
        result = validate_meadows_leverage_points(content, meadows_refs())
        assert not result.passed
        assert expected_code in result.reason_codes, result.reason_codes
        assert result.repair_input is not None

    @pytest.mark.parametrize(
        ("schema_path_fragment", "mutate"),
        [
            ("systemMap", lambda c: c["systemMap"].update(stocks=[])),
            ("highLeverageGaps", lambda c: c.update(highLeverageGaps=[])),
            ("runawayPositiveLoops", lambda c: c.update(runawayPositiveLoops=[])),
            ("interventionSequence", lambda c: c.update(interventionSequence=[])),
            ("riskTradeoffs", lambda c: c.update(riskTradeoffs=[])),
        ],
    )
    def test_shape_gap_fails_closed(self, schema_path_fragment, mutate) -> None:
        # Coverage assertions locked into the canonical shape mirror still
        # fail closed through the validator with stable path-coded reasons.
        content = meadows_content()
        mutate(content)
        result = validate_meadows_leverage_points(content, meadows_refs())
        assert not result.passed
        assert any(
            code.startswith("schema:") and schema_path_fragment in code
            for code in result.reason_codes
        ), result.reason_codes
        assert result.repair_input is not None


# --- Cross-cutting validator surface ---------------------------------------------------


class TestValidatorSurface:
    def test_dispatch_table_covers_exactly_the_canonical_five(self) -> None:
        assert set(LENS_BEHAVIOR_VALIDATORS) == set(FULL_REQUIRED_STRATEGIC_LENSES)

    def test_dispatcher_routes_each_lens(self) -> None:
        samples = {
            StrategicLensType.PORTER_FIVE_FORCES: (porter_content(), porter_refs()),
            StrategicLensType.SCENARIO_PLANNING: (scenario_content(), scenario_refs()),
            StrategicLensType.MEADOWS_LEVERAGE_POINTS: (meadows_content(), meadows_refs()),
        }
        for lens_type, (content, refs) in samples.items():
            direct = LENS_BEHAVIOR_VALIDATORS[lens_type](content, refs)
            dispatched = validate_lens_behavior(lens_type, content, refs)
            assert dispatched == direct
            assert dispatched.lens_type is lens_type

    def test_unknown_lens_type_fails_closed(self) -> None:
        with pytest.raises(UnknownLensType):
            validate_lens_behavior(None, {}, ResolvedLensReferences())  # type: ignore[arg-type]

    @pytest.mark.parametrize("lens_type", list(FULL_REQUIRED_STRATEGIC_LENSES))
    def test_non_object_content_fails_closed(self, lens_type) -> None:
        result = validate_lens_behavior(lens_type, [], ResolvedLensReferences())
        assert not result.passed
        assert result.reason_codes == (CODE_CONTENT_NOT_OBJECT,)

    def test_repair_input_names_producer_and_keeps_frozen_references(self) -> None:
        content = porter_content()
        content["scoreIsNotDecisionFormula"] = False
        refs = porter_refs()
        result = validate_porter_five_forces(content, refs)
        assert not result.passed
        repair = result.repair_input
        assert repair is not None
        assert repair.lens_type is StrategicLensType.PORTER_FIVE_FORCES
        assert repair.owner_worker == "research"
        assert repair.phase == "research_interpretation"
        assert repair.reason_codes == result.reason_codes
        assert repair.findings == result.findings
        assert repair.resolved_references == refs
        # The repair input routes regeneration; it never carries repaired content.
        assert not hasattr(repair, "content")

    def test_validator_judges_but_never_repairs_input(self) -> None:
        content = scenario_content()
        content["scenarios"] = content["scenarios"][:2]
        frozen_copy = copy.deepcopy(content)
        result = validate_scenario_planning(content, scenario_refs())
        assert not result.passed
        assert content == frozen_copy  # judged, not touched

    def test_validation_is_deterministic(self) -> None:
        first = validate_meadows_leverage_points(meadows_content(), meadows_refs())
        second = validate_meadows_leverage_points(meadows_content(), meadows_refs())
        assert first == second

    def test_resolved_references_wire_round_trip(self) -> None:
        wire = porter_references_wire()
        refs = ResolvedLensReferences.from_wire(wire)
        assert refs.to_wire() == wire
