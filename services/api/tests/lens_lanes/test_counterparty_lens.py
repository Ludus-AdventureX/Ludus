"""Counterparty lens lane behavior tests (L3 specialist lane owned).

These tests exercise only the counterparty lane deliverables: the
``counterparty_response_matrix`` lens implementation, the spherical-robot
positive fixture, and the missing-no-action negative fixture. They are not the
QA/Release gate suites and require no database or network. The stage-output
schema used for fixture validation is the immutable published pack copy in
``method-packs/hardtech-market-direction/1.1.0``.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from app.strategic_lenses.lenses import counterparty_response_matrix as lane
from app.types import StrategicLensType

REPO_ROOT = Path(__file__).resolve().parents[4]
PACK_DIR = REPO_ROOT / "method-packs" / "hardtech-market-direction" / "1.1.0"
SCHEMA_PATH = PACK_DIR / "schemas" / "strategic-lens-output.schema.json"
PROMPT_PATH = PACK_DIR / "prompts" / "lenses" / "counterparty-response-matrix.md"
POSITIVE_FIXTURE = (
    REPO_ROOT
    / "fixtures"
    / "spherical-robot"
    / "expected"
    / "strategic-lenses"
    / "counterparty_response_matrix.json"
)
NEGATIVE_FIXTURE = (
    REPO_ROOT
    / "fixtures"
    / "spherical-robot"
    / "negative"
    / "strategic-lenses"
    / "counterparty_response_matrix_missing_no_action.json"
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class StageOutputStub:
    """Structural stand-in for the seam ``StrategicLensStageOutput``."""

    lens_type: StrategicLensType
    source_skill_version: str
    phase: str
    references: dict[str, Any]
    research_requests: list[dict[str, Any]]
    content: dict[str, Any]

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "StageOutputStub":
        lane.assert_no_server_owned_fields(payload)
        return cls(
            lens_type=StrategicLensType(payload["lensType"]),
            source_skill_version=payload["sourceSkillVersion"],
            phase=payload["phase"],
            references=payload["references"],
            research_requests=payload["researchRequests"],
            content=payload["content"],
        )


@dataclass(frozen=True)
class RequestStub:
    """Structural stand-in for the seam ``LensRequest``."""

    lens_type: StrategicLensType = StrategicLensType.COUNTERPARTY_RESPONSE_MATRIX
    workspace_id: str = "ws-lane-test"
    analysis_run_id: str = "run-lane-test"
    prompt_text: str = "frozen counterparty prompt"
    research_packet_refs: tuple[str, ...] = ("rp-b", "rp-a")
    evidence_refs: tuple[str, ...] = ("ev-1",)
    claim_refs: tuple[str, ...] = ("cl-1",)
    assumption_refs: tuple[str, ...] = ("asm-1",)
    challenge_refs: tuple[str, ...] = ()
    option_ids: tuple[str, ...] = ("opt-rescue", "opt-household")
    upstream_lens_outputs: dict[Any, Any] = field(default_factory=dict)


@pytest.fixture(scope="module")
def schema_validator() -> Draft202012Validator:
    return Draft202012Validator(load_json(SCHEMA_PATH))


@pytest.fixture()
def positive_payload() -> dict[str, Any]:
    return load_json(POSITIVE_FIXTURE)


@pytest.fixture()
def negative_payload() -> dict[str, Any]:
    return load_json(NEGATIVE_FIXTURE)


class TestPositiveFixture:
    def test_matches_published_stage_output_schema(self, schema_validator, positive_payload):
        errors = sorted(schema_validator.iter_errors(positive_payload), key=str)
        assert not errors, [error.message for error in errors]

    def test_passes_lane_behavior_contract(self, positive_payload):
        output = StageOutputStub.from_payload(positive_payload)
        report = lane.LENS.validate_behavior(output)
        assert report.ok, (report.reason_codes, report.findings)
        assert report.lens_type is StrategicLensType.COUNTERPARTY_RESPONSE_MATRIX
        assert report.reason_codes == ()

    def test_matrix_names_at_least_one_invalidated_strategy(self, positive_payload):
        # The pack prompt requires naming actions that may fail when the
        # counter-response is infeasible or breaches a hard constraint.
        rows = positive_payload["content"]["responseMatrix"]
        assert any(row["strategyInvalidated"] for row in rows)

    def test_downside_floors_use_bounded_unbounded_unknown_only(self, positive_payload):
        floors = {
            entry["downsideFloor"] for entry in positive_payload["content"]["downsideAsymmetry"]
        }
        assert floors <= {"bounded", "unbounded", "unknown"}
        assert "unbounded" in floors  # household launch downside is not bounded


class TestNegativeFixture:
    def test_missing_no_action_fails_schema(self, schema_validator, negative_payload):
        assert any(schema_validator.iter_errors(negative_payload))

    def test_missing_no_action_fails_behavior(self, negative_payload):
        output = StageOutputStub.from_payload(negative_payload)
        report = lane.LENS.validate_behavior(output)
        assert not report.ok
        assert lane.CODE_ACTIONS in report.reason_codes


class TestEnvelopeGuards:
    def test_server_owned_field_rejected(self, positive_payload):
        payload = copy.deepcopy(positive_payload)
        payload["workspaceId"] = "ws-injected"
        with pytest.raises(lane.CounterpartyLensError, match="server-owned"):
            StageOutputStub.from_payload(payload)

    def test_unknown_top_level_field_rejected(self, positive_payload):
        payload = copy.deepcopy(positive_payload)
        payload["confidenceScore"] = 0.9
        with pytest.raises(lane.CounterpartyLensError, match="unknown top-level"):
            StageOutputStub.from_payload(payload)

    def test_wrong_phase_and_skill_version_flagged(self, positive_payload):
        output = StageOutputStub(
            lens_type=StrategicLensType.COUNTERPARTY_RESPONSE_MATRIX,
            source_skill_version="9.9.9",
            phase="strategic_synthesis",
            references=positive_payload["references"],
            research_requests=positive_payload["researchRequests"],
            content=positive_payload["content"],
        )
        report = lane.LENS.validate_behavior(output)
        assert not report.ok
        assert lane.CODE_PHASE in report.reason_codes
        assert lane.CODE_SKILL_VERSION in report.reason_codes

    def test_wrong_lens_type_flagged(self, positive_payload):
        output = StageOutputStub(
            lens_type=StrategicLensType.PRE_MORTEM,
            source_skill_version="1.0.0",
            phase="adversarial_stress",
            references=positive_payload["references"],
            research_requests=positive_payload["researchRequests"],
            content=positive_payload["content"],
        )
        report = lane.LENS.validate_behavior(output)
        assert not report.ok
        assert lane.CODE_LENS_TYPE in report.reason_codes


class TestContentBehaviors:
    def _validate(self, content: dict[str, Any], assumption_ids: tuple[str, ...] | None = None):
        registered = (
            frozenset(assumption_ids)
            if assumption_ids is not None
            else frozenset(
                {
                    "asm-procurement-cycle-9mo",
                    "asm-cert-first-mover",
                    "asm-household-willingness-to-pay",
                    "asm-runway-12mo",
                }
            )
        )
        return lane.validate_counterparty_content(
            content, registered_assumption_ids=registered
        )

    def test_depth_above_one_layer_flagged(self, positive_payload):
        content = copy.deepcopy(positive_payload["content"])
        content["maxResponseDepth"] = 2
        codes, _ = self._validate(content)
        assert lane.CODE_DEPTH in codes

    def test_more_than_two_actors_flagged(self, positive_payload):
        content = copy.deepcopy(positive_payload["content"])
        third = copy.deepcopy(content["counterparties"][0])
        third["counterpartyId"] = "cp-regulator"
        content["counterparties"].append(third)
        codes, _ = self._validate(content)
        assert lane.CODE_ACTORS in codes

    def test_missing_matrix_pair_flagged(self, positive_payload):
        content = copy.deepcopy(positive_payload["content"])
        content["responseMatrix"].pop()
        codes, findings = self._validate(content)
        assert lane.CODE_MATRIX in codes
        assert any("missing pairs" in finding for finding in findings)

    def test_duplicate_matrix_pair_flagged(self, positive_payload):
        content = copy.deepcopy(positive_payload["content"])
        content["responseMatrix"][1] = copy.deepcopy(content["responseMatrix"][0])
        codes, _ = self._validate(content)
        assert lane.CODE_MATRIX in codes

    def test_downside_asymmetry_must_cover_every_action(self, positive_payload):
        content = copy.deepcopy(positive_payload["content"])
        content["downsideAsymmetry"].pop()
        codes, findings = self._validate(content)
        assert lane.CODE_PUBLICATION in codes
        assert any("missing actions" in finding for finding in findings)

    def test_invented_survival_probability_floor_flagged(self, positive_payload):
        content = copy.deepcopy(positive_payload["content"])
        content["downsideAsymmetry"][0]["downsideFloor"] = "survival_probability_0.8"
        codes, _ = self._validate(content)
        assert lane.CODE_PUBLICATION in codes

    def test_unregistered_core_assumption_flagged(self, positive_payload):
        content = copy.deepcopy(positive_payload["content"])
        codes, findings = self._validate(content, assumption_ids=("asm-runway-12mo",))
        assert lane.CODE_ASSUMPTIONS in codes
        assert any("references.assumptionIds" in finding for finding in findings)

    def test_missing_reflexivity_warning_flagged(self, positive_payload):
        content = copy.deepcopy(positive_payload["content"])
        content["reflexivityWarning"] = "  "
        codes, _ = self._validate(content)
        assert lane.CODE_PUBLICATION in codes

    def test_identical_action_descriptions_flagged(self, positive_payload):
        content = copy.deepcopy(positive_payload["content"])
        content["ourActions"][1]["description"] = content["ourActions"][0]["description"]
        codes, _ = self._validate(content)
        assert lane.CODE_ACTIONS in codes

    def test_content_accepts_read_only_mapping(self, positive_payload):
        codes, findings = self._validate(
            MappingProxyType(positive_payload["content"])
        )
        assert codes == (), findings


class TestPromptAssembly:
    def test_prompt_inputs_are_deterministic_and_pinned(self):
        prompt_text = PROMPT_PATH.read_text(encoding="utf-8")
        request = RequestStub(prompt_text=prompt_text)
        first = lane.LENS.build_prompt_inputs(request)
        second = lane.LENS.build_prompt_inputs(request)
        assert first == second
        assert first.system == prompt_text
        assert first.schema_content_def == "counterpartyContent"
        assert "opt-household" in first.user and "opt-rescue" in first.user
        # references render sorted for determinism
        assert first.user.index("rp-a") < first.user.index("rp-b")
        assert "workspaceId" in first.user  # server-owned fields are spelled out as forbidden

    def test_prompt_output_contract_mentions_lane_constants(self):
        inputs = lane.LENS.build_prompt_inputs(RequestStub())
        assert lane.LENS_TYPE.value in inputs.user
        assert lane.PHASE in inputs.user
        assert lane.SOURCE_SKILL_VERSION in inputs.user

    def test_wrong_lens_type_request_rejected(self):
        request = RequestStub(lens_type=StrategicLensType.SCENARIO_PLANNING)
        with pytest.raises(lane.CounterpartyLensError, match="lens type"):
            lane.LENS.build_prompt_inputs(request)

    def test_missing_options_rejected(self):
        with pytest.raises(lane.CounterpartyLensError, match="decision options"):
            lane.LENS.build_prompt_inputs(RequestStub(option_ids=()))

    def test_blank_prompt_text_rejected(self):
        with pytest.raises(lane.CounterpartyLensError, match="prompt_text"):
            lane.LENS.build_prompt_inputs(RequestStub(prompt_text="   "))

    def test_missing_run_pinning_rejected(self):
        with pytest.raises(lane.CounterpartyLensError, match="workspace_id"):
            lane.LENS.build_prompt_inputs(RequestStub(analysis_run_id=""))
