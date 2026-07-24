"""Deterministic behavior tests for the Porter Five Forces lens (lane 7).

Colocated with the implementation on the lens branch; QA-owned suites live in
``services/api/tests/**`` and are not touched here. No network, no model, no DB.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from app.agents.errors import SchemaValidationError, ServerOwnedFieldError
from app.agents.lenses import (
    LensImplementation,
    LensRequest,
    StrategicLensStageOutput,
)
from app.strategic_lenses.lenses.porter_five_forces import (
    CANONICAL_FORCE_IDS,
    PorterFiveForcesLens,
    porter_five_forces_lens,
)
from app.types import StrategicLensType

WS = "ws-spherical-robot"
RUN = "run-porter-golden"

# Frozen spherical-robot golden inputs: rescue vs household service markets.
OPTION_RESCUE = "option-rescue-market"
OPTION_HOME = "option-home-service-market"
EVIDENCE_IDS = tuple(f"ev-sr-{i:03d}" for i in range(1, 21))


def make_request(**overrides: Any) -> LensRequest:
    base: dict[str, Any] = {
        "lens_type": StrategicLensType.PORTER_FIVE_FORCES,
        "workspace_id": WS,
        "analysis_run_id": RUN,
        "prompt_text": "# Porter Five Forces Lens\n(published pack prompt)",
        "research_packet_refs": ("rp-sr-001", "rp-sr-002"),
        "evidence_refs": EVIDENCE_IDS,
        "claim_refs": ("claim-sr-001",),
        "assumption_refs": ("asm-sr-001",),
        "option_ids": (OPTION_RESCUE, OPTION_HOME),
    }
    base.update(overrides)
    return LensRequest(**base)


def make_force(force_id: str, start: int, score: int = 3) -> dict[str, Any]:
    return {
        "forceId": force_id,
        "threatScore": score,
        "keyIndicators": [f"{force_id} concentration", f"{force_id} growth"],
        "evidenceIds": [EVIDENCE_IDS[start], EVIDENCE_IDS[start + 1]],
        "reasoning": f"{force_id} pressure grounded in gated evidence.",
        "directionOfChange": "stable",
    }


def make_market(option_id: str, offset: int) -> dict[str, Any]:
    forces = [
        make_force(force_id, offset + i * 2)
        for i, force_id in enumerate(sorted(CANONICAL_FORCE_IDS))
    ]
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
        "forces": forces,
        "averageThreatScore": 3.0,
        "changingTrend": "Public procurement standards for rescue robotics are "
        "tightening, shifting entry barriers year over year.",
        "regulatoryAssessment": "Safety certification and emergency-services "
        "procurement rules assessed separately, not averaged as a sixth force.",
        "complementors": ["thermal cameras", "incident-management software"],
    }


def make_payload(**content_overrides: Any) -> dict[str, Any]:
    content: dict[str, Any] = {
        "marketAnalyses": [
            make_market(OPTION_RESCUE, 0),
            make_market(OPTION_HOME, 10),
        ],
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
    content.update(content_overrides)
    return {
        "lensType": "porter_five_forces",
        "sourceSkillVersion": "1.0.0",
        "phase": "research_interpretation",
        "references": {
            "sourcePacketIds": ["rp-sr-001", "rp-sr-002"],
            "claimIds": ["claim-sr-001"],
            "evidenceIds": list(EVIDENCE_IDS),
            "assumptionIds": ["asm-sr-001"],
            "challengeIds": [],
        },
        "researchRequests": [],
        "content": content,
    }


def make_output(**content_overrides: Any) -> StrategicLensStageOutput:
    return StrategicLensStageOutput.from_payload(make_payload(**content_overrides))


@pytest.fixture()
def lens() -> PorterFiveForcesLens:
    return porter_five_forces_lens()


class TestSeamConformance:
    def test_implements_lens_implementation_protocol(self, lens) -> None:
        assert isinstance(lens, LensImplementation)
        assert lens.lens_type is StrategicLensType.PORTER_FIVE_FORCES

    def test_server_owned_fields_rejected_at_seam(self) -> None:
        payload = make_payload()
        payload["analysisRunId"] = RUN
        with pytest.raises(ServerOwnedFieldError):
            StrategicLensStageOutput.from_payload(payload)


class TestBuildPromptInputs:
    def test_golden_request_assembles_prompt(self, lens) -> None:
        inputs = lens.build_prompt_inputs(make_request())
        assert inputs.system.startswith("# Porter Five Forces Lens")
        assert OPTION_RESCUE in inputs.user and OPTION_HOME in inputs.user
        assert EVIDENCE_IDS[0] in inputs.user
        assert inputs.schema_content_def == "porterContent"

    def test_deterministic_assembly(self, lens) -> None:
        first = lens.build_prompt_inputs(make_request())
        second = lens.build_prompt_inputs(make_request())
        assert first == second

    @pytest.mark.parametrize(
        ("overrides", "finding"),
        [
            ({"prompt_text": "  "}, "missing_published_prompt_text"),
            (
                {"option_ids": (OPTION_RESCUE,)},
                "fewer_than_two_frozen_market_options",
            ),
            ({"research_packet_refs": ()}, "no_frozen_research_packets"),
            ({"evidence_refs": ()}, "no_frozen_evidence_to_link"),
        ],
    )
    def test_unsupported_input_fails_closed(self, lens, overrides, finding) -> None:
        with pytest.raises(SchemaValidationError) as excinfo:
            lens.build_prompt_inputs(make_request(**overrides))
        assert finding in excinfo.value.findings

    def test_wrong_lens_type_request_rejected(self, lens) -> None:
        with pytest.raises(SchemaValidationError):
            lens.build_prompt_inputs(
                make_request(lens_type=StrategicLensType.PRE_MORTEM)
            )


class TestSphericalRobotPositiveBehavior:
    def test_golden_output_passes(self, lens) -> None:
        report = lens.validate_behavior(make_output())
        assert report.ok, report.findings
        assert report.reason_codes == ()
        assert report.lens_type is StrategicLensType.PORTER_FIVE_FORCES

    def test_validation_is_deterministic(self, lens) -> None:
        assert lens.validate_behavior(make_output()) == lens.validate_behavior(
            make_output()
        )


class TestFiveForcesCompleteness:
    def test_missing_force_fails(self, lens) -> None:
        payload = make_payload()
        payload["content"]["marketAnalyses"][0]["forces"].pop()
        report = lens.validate_behavior(
            StrategicLensStageOutput.from_payload(payload)
        )
        assert not report.ok
        assert "missing_canonical_force" in report.reason_codes

    def test_duplicated_force_fails(self, lens) -> None:
        payload = make_payload()
        forces = payload["content"]["marketAnalyses"][0]["forces"]
        forces[1] = copy.deepcopy(forces[0])
        report = lens.validate_behavior(
            StrategicLensStageOutput.from_payload(payload)
        )
        assert not report.ok
        assert "duplicated_force" in report.reason_codes

    def test_sixth_regulation_force_fails(self, lens) -> None:
        payload = make_payload()
        rogue = make_force("rivalry", 0)
        rogue["forceId"] = "regulation"
        payload["content"]["marketAnalyses"][0]["forces"][0] = rogue
        report = lens.validate_behavior(
            StrategicLensStageOutput.from_payload(payload)
        )
        assert not report.ok
        assert "non_canonical_sixth_force" in report.reason_codes

    def test_single_market_fails(self, lens) -> None:
        payload = make_payload(marketAnalyses=[make_market(OPTION_RESCUE, 0)])
        report = lens.validate_behavior(
            StrategicLensStageOutput.from_payload(payload)
        )
        assert not report.ok
        assert "fewer_than_two_markets" in report.reason_codes

    def test_duplicate_market_option_fails(self, lens) -> None:
        payload = make_payload(
            marketAnalyses=[make_market(OPTION_RESCUE, 0), make_market(OPTION_RESCUE, 10)]
        )
        report = lens.validate_behavior(
            StrategicLensStageOutput.from_payload(payload)
        )
        assert not report.ok
        assert "duplicate_market_option" in report.reason_codes


class TestEvidenceLinking:
    def test_single_evidence_per_force_fails(self, lens) -> None:
        payload = make_payload()
        payload["content"]["marketAnalyses"][0]["forces"][0]["evidenceIds"] = [
            EVIDENCE_IDS[0]
        ]
        report = lens.validate_behavior(
            StrategicLensStageOutput.from_payload(payload)
        )
        assert not report.ok
        assert "force_evidence_below_minimum" in report.reason_codes

    def test_duplicated_evidence_ids_do_not_count_twice(self, lens) -> None:
        payload = make_payload()
        payload["content"]["marketAnalyses"][0]["forces"][0]["evidenceIds"] = [
            EVIDENCE_IDS[0],
            EVIDENCE_IDS[0],
        ]
        report = lens.validate_behavior(
            StrategicLensStageOutput.from_payload(payload)
        )
        assert not report.ok
        assert "force_evidence_below_minimum" in report.reason_codes

    def test_undeclared_evidence_id_fails(self, lens) -> None:
        payload = make_payload()
        payload["content"]["marketAnalyses"][0]["forces"][0]["evidenceIds"] = [
            "ev-not-in-run-001",
            "ev-not-in-run-002",
        ]
        report = lens.validate_behavior(
            StrategicLensStageOutput.from_payload(payload)
        )
        assert not report.ok
        assert "force_evidence_not_in_references" in report.reason_codes


class TestBoundaryTrendRegulatory:
    def test_empty_boundary_field_fails(self, lens) -> None:
        payload = make_payload()
        payload["content"]["marketAnalyses"][0]["industryBoundary"]["boundaryRisk"] = " "
        report = lens.validate_behavior(
            StrategicLensStageOutput.from_payload(payload)
        )
        assert not report.ok
        assert "industry_boundary_incomplete" in report.reason_codes

    def test_missing_trend_fails(self, lens) -> None:
        payload = make_payload()
        payload["content"]["marketAnalyses"][1]["changingTrend"] = ""
        report = lens.validate_behavior(
            StrategicLensStageOutput.from_payload(payload)
        )
        assert not report.ok
        assert "changing_trend_missing" in report.reason_codes

    def test_missing_regulatory_assessment_fails(self, lens) -> None:
        payload = make_payload()
        payload["content"]["marketAnalyses"][0]["regulatoryAssessment"] = ""
        report = lens.validate_behavior(
            StrategicLensStageOutput.from_payload(payload)
        )
        assert not report.ok
        assert "regulatory_assessment_missing" in report.reason_codes

    def test_missing_complementors_fails(self, lens) -> None:
        payload = make_payload()
        payload["content"]["marketAnalyses"][0]["complementors"] = []
        report = lens.validate_behavior(
            StrategicLensStageOutput.from_payload(payload)
        )
        assert not report.ok
        assert "complementors_missing" in report.reason_codes


class TestNoFakeScores:
    def test_average_must_be_descriptive_mean(self, lens) -> None:
        payload = make_payload()
        # A "weighted" average that no declared formula produced.
        payload["content"]["marketAnalyses"][0]["averageThreatScore"] = 4.7
        report = lens.validate_behavior(
            StrategicLensStageOutput.from_payload(payload)
        )
        assert not report.ok
        assert "average_score_is_not_descriptive_mean" in report.reason_codes

    def test_score_is_not_decision_formula_flag_required(self, lens) -> None:
        payload = make_payload(scoreIsNotDecisionFormula=False)
        report = lens.validate_behavior(
            StrategicLensStageOutput.from_payload(payload)
        )
        assert not report.ok
        assert "score_presented_as_decision_formula" in report.reason_codes

    def test_success_probability_language_fails(self, lens) -> None:
        payload = make_payload()
        payload["content"]["strategicImplications"][0]["logic"] = (
            "Rescue entry has an 80% chance of success based on the average score."
        )
        report = lens.validate_behavior(
            StrategicLensStageOutput.from_payload(payload)
        )
        assert not report.ok
        assert "fake_probability_language" in report.reason_codes

    def test_unconditional_implication_fails(self, lens) -> None:
        payload = make_payload()
        payload["content"]["strategicImplications"][0]["conditions"] = []
        report = lens.validate_behavior(
            StrategicLensStageOutput.from_payload(payload)
        )
        assert not report.ok
        assert "implication_conditions_missing" in report.reason_codes


class TestWrongEnvelope:
    def test_wrong_phase_fails(self, lens) -> None:
        payload = make_payload()
        payload["phase"] = "adversarial_stress"
        report = lens.validate_behavior(
            StrategicLensStageOutput.from_payload(payload)
        )
        assert not report.ok
        assert "wrong_phase" in report.reason_codes

    def test_other_lens_output_rejected(self, lens) -> None:
        payload = make_payload()
        payload["lensType"] = "pre_mortem"
        report = lens.validate_behavior(
            StrategicLensStageOutput.from_payload(payload)
        )
        assert not report.ok
        assert report.reason_codes == ("lens_type_mismatch",)

    def test_market_analyses_missing_fails(self, lens) -> None:
        payload = make_payload()
        del payload["content"]["marketAnalyses"]
        report = lens.validate_behavior(
            StrategicLensStageOutput.from_payload(payload)
        )
        assert not report.ok
        assert "market_analyses_missing" in report.reason_codes
