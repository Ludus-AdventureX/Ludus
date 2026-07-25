"""QA adversarial suite for the Task 10 lens behavior validators (r1 gate).

Independent QA additions on top of the owner suite: adversarial negatives that
specifically attack the schema-pass/behavior-fail layering claim, structural
assertions that ``LensRepairInput`` has no content write path, and a
regression guard for the ``normalize_pre_mortem_code`` projection. No DB, no
network.
"""

from __future__ import annotations

import copy
import dataclasses
import inspect
import re

import pytest
from jsonschema import Draft202012Validator

from app.strategic_lenses.lenses import pre_mortem as pre_mortem_lane
from app.strategic_lenses.validators import (
    LensBehaviorValidationResult,
    LensRepairInput,
    normalize_pre_mortem_code,
    validate_counterparty_response_matrix,
    validate_meadows_leverage_points,
    validate_porter_five_forces,
    validate_pre_mortem,
    validate_scenario_planning,
)
from app.types import StrategicLensType
from tests.test_strategic_lens_validators import (
    COUNTERPARTY_FIXTURE,
    PRE_MORTEM_FIXTURE,
    envelope,
    load_json,
    meadows_content,
    meadows_references_wire,
    meadows_refs,
    porter_content,
    porter_references_wire,
    porter_refs,
    refs_of,
    scenario_content,
    scenario_references_wire,
    scenario_refs,
)
from tests.test_strategic_lens_validators import (
    PACK_SCHEMA_PATH,
)


@pytest.fixture(scope="module")
def pack_validator() -> Draft202012Validator:
    return Draft202012Validator(load_json(PACK_SCHEMA_PATH))


def assert_schema_pass(validator: Draft202012Validator, payload: dict) -> None:
    errors = sorted(validator.iter_errors(payload), key=str)
    assert not errors, [error.message for error in errors]


class TestAdversarialSchemaPassBehaviorFail:
    """Every case here is proven schema-valid first, then must fail behavior."""

    def test_porter_float_threat_score_smuggled_past_json_integer(self, pack_validator) -> None:
        # JSON Schema "integer" accepts 4.0; the ordinal contract must not.
        content = porter_content()
        content["marketAnalyses"][0]["forces"][0]["threatScore"] = 4.0
        payload = envelope(
            StrategicLensType.PORTER_FIVE_FORCES,
            "research_interpretation",
            porter_references_wire(),
            content,
        )
        assert_schema_pass(pack_validator, payload)
        result = validate_porter_five_forces(content, porter_refs())
        assert not result.passed
        assert "threat_score_not_ordinal_1_to_5" in result.reason_codes

    def test_porter_cross_type_reference_smuggling(self, pack_validator) -> None:
        # Claim/assumption IDs are schema-valid id strings but are NOT
        # resolved evidence; citing them as force evidence must fail.
        content = porter_content()
        content["marketAnalyses"][0]["forces"][0]["evidenceIds"] = [
            "claim-sr-001",
            "asm-sr-001",
        ]
        payload = envelope(
            StrategicLensType.PORTER_FIVE_FORCES,
            "research_interpretation",
            porter_references_wire(),
            content,
        )
        assert_schema_pass(pack_validator, payload)
        result = validate_porter_five_forces(content, porter_refs())
        assert not result.passed
        assert "force_evidence_not_in_references" in result.reason_codes

    def test_pre_mortem_risk_arithmetic_smuggling(self, pack_validator) -> None:
        # 17 is inside the schema's 1-25 riskScore window but is not 4*4.
        payload = load_json(PRE_MORTEM_FIXTURE)
        payload["content"]["failureCauses"][0]["riskScore"] = 17
        assert_schema_pass(pack_validator, payload)
        result = validate_pre_mortem(payload["content"], refs_of(payload))
        assert not result.passed
        assert "pre_mortem_risk_arithmetic" in result.reason_codes

    def test_pre_mortem_fatal_uncontrollable_cause_averaged_into_continue(
        self, pack_validator
    ) -> None:
        # "continue" is a schema-legal verdict; with the fixture's fatal
        # uncontrollable PM-C2 on the table it must be judged a failure.
        payload = load_json(PRE_MORTEM_FIXTURE)
        payload["content"]["verdict"] = "continue"
        assert_schema_pass(pack_validator, payload)
        result = validate_pre_mortem(payload["content"], refs_of(payload))
        assert not result.passed
        assert "pre_mortem_fatal_cause_averaged_away" in result.reason_codes

    def test_counterparty_matrix_row_redirected_to_unknown_actor(self, pack_validator) -> None:
        # Row count stays inside the schema window (6 = 2x3); redirecting one
        # row to a ghost actor keeps the shape valid but breaks pair coverage.
        payload = load_json(COUNTERPARTY_FIXTURE)
        payload["content"]["responseMatrix"][0]["counterpartyId"] = "cp-ghost"
        assert_schema_pass(pack_validator, payload)
        result = validate_counterparty_response_matrix(payload["content"], refs_of(payload))
        assert not result.passed
        assert (
            "matrix_covers_optimal_worst_likely_window_gap_counterresponse"
            in result.reason_codes
        )

    def test_scenario_cross_frame_duplicate_signal_id(self, pack_validator) -> None:
        # Uniqueness across frames is a behavior rule the shape cannot express.
        content = scenario_content()
        content["scenarios"][1]["earlySignals"][0]["signalId"] = "sig-s1"
        payload = envelope(
            StrategicLensType.SCENARIO_PLANNING,
            "strategic_synthesis",
            scenario_references_wire(),
            content,
        )
        assert_schema_pass(pack_validator, payload)
        result = validate_scenario_planning(content, scenario_refs())
        assert not result.passed
        assert "signal_id_duplicate" in result.reason_codes

    def test_meadows_non_dense_sequence_orders(self, pack_validator) -> None:
        content = meadows_content()
        content["interventionSequence"][2]["order"] = 4  # 1,2,4: gap, schema-legal
        payload = envelope(
            StrategicLensType.MEADOWS_LEVERAGE_POINTS,
            "strategic_synthesis",
            meadows_references_wire(),
            content,
        )
        assert_schema_pass(pack_validator, payload)
        result = validate_meadows_leverage_points(content, meadows_refs())
        assert not result.passed
        assert "sequence_orders_not_dense_ascending" in result.reason_codes


class TestRepairInputHasNoContentWritePath:
    def _failing_result(self) -> LensBehaviorValidationResult:
        content = porter_content()
        content["scoreIsNotDecisionFormula"] = False
        return validate_porter_five_forces(content, porter_refs())

    def test_repair_input_field_set_is_closed(self) -> None:
        fields = {f.name for f in dataclasses.fields(LensRepairInput)}
        assert fields == {
            "lens_type",
            "owner_worker",
            "phase",
            "reason_codes",
            "findings",
            "resolved_references",
        }
        assert "content" not in fields

    def test_repair_input_and_result_are_frozen(self) -> None:
        result = self._failing_result()
        repair = result.repair_input
        assert repair is not None
        with pytest.raises(dataclasses.FrozenInstanceError):
            repair.findings = ()  # type: ignore[misc]
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.passed = True  # type: ignore[misc]
        with pytest.raises(dataclasses.FrozenInstanceError):
            repair.resolved_references.evidence_ids = ()  # type: ignore[misc]

    def test_validators_never_mutate_content_on_pass_or_fail(self) -> None:
        passing = meadows_content()
        passing_copy = copy.deepcopy(passing)
        assert validate_meadows_leverage_points(passing, meadows_refs()).passed
        assert passing == passing_copy

        failing = porter_content()
        failing["marketAnalyses"][0]["forces"][0]["threatScore"] = 4.0
        failing_copy = copy.deepcopy(failing)
        assert not validate_porter_five_forces(failing, porter_refs()).passed
        assert failing == failing_copy


class TestPreMortemProjectionRegressionGuard:
    def _shipped_pm_codes(self) -> set[str]:
        source = inspect.getsource(pre_mortem_lane)
        return set(re.findall(r'"(PM_[A-Z_]+)"', source))

    def test_projection_is_total_collision_free_and_invertible(self) -> None:
        raw = self._shipped_pm_codes()
        assert raw, "expected shipped PM_* codes in the pre_mortem lane"
        projected = {normalize_pre_mortem_code(code) for code in raw}
        assert len(projected) == len(raw)  # collision-free
        for code in raw:
            forward = normalize_pre_mortem_code(code)
            assert forward == "pre_mortem_" + code[len("PM_") :].lower()
            assert "PM_" + forward[len("pre_mortem_") :].upper() == code  # invertible
