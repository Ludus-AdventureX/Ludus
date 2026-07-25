"""Task 10 Step 5 behavior validators for the five strategic lenses.

This module is the pure-function surface the full-run quality gate calls once
per lens (18-detailed-development-plan Task 10 Step 5, behavior table
L1072-L1076; ownership adjudicated by CCR-20260725-ANALYSIS-01 section 4.4:
the per-lens behavior contract belongs to the method-pack/ways stage-output
layer, not the HTTP wire contract).

Layering (all fail-closed):

1. JSON *shape* is owned by the published pack schema
   ``strategic-lens-output.schema.json`` and checked upstream; a payload that
   passes shape but fails behavior MUST still be rejected here.
2. Each validator below re-runs the lane-owned deterministic behavior gate on
   ``(canonical content, resolved references)`` and returns a structured
   result: pass, or a failure list with stable reason codes plus a repair
   input package. Reason codes are passed through verbatim from the shipped
   lane gates (lower_snake precedent, e.g.
   ``score_constraint_operator_unsupported`` style); the Pre-Mortem lane's
   historical ``PM_*`` codes are projected onto the same lower_snake style by
   the deterministic ``pre_mortem_`` prefix transform documented in the Task
   10 handoff.
3. Validators only judge. They never repair, complete or rewrite content
   ("Validation 不得补写"): the repair input names what failed and hands the
   frozen references back to the producing worker for a full regeneration.

No database, no network, no mutation of the inputs; every function is
deterministic for identical inputs.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.agents.errors import UnknownLensType
from app.agents.lenses import (
    LensBehaviorReport,
    StrategicLensStageOutput,
    lens_spec,
)
from app.types import StrategicLensType

from .lenses.counterparty_response_matrix import validate_counterparty_content
from .lenses.meadows_leverage_points import (
    MeadowsLensValidationError,
    validate_meadows_stage_output,
)
from .lenses.porter_five_forces import PorterFiveForcesLens
from .lenses.pre_mortem import validate_pre_mortem_output
from .lenses.scenario_planning import ScenarioPlanningLens

# Validator-layer reason codes (this module's own, lower_snake fail-closed
# precedent style). Everything else is passed through from the lane gates.
CODE_CONTENT_NOT_OBJECT = "lens_content_not_object"

# The Pre-Mortem lane shipped uppercase ``PM_*`` codes before the lower_snake
# convention settled. The projection is mechanical and total so no code is
# ever dropped or invented: ``PM_CAUSE_COUNT`` -> ``pre_mortem_cause_count``.
_PRE_MORTEM_CODE_PREFIX = "PM_"


def normalize_pre_mortem_code(code: str) -> str:
    """Project a lane ``PM_*`` blocker code onto the lower_snake style."""

    if code.startswith(_PRE_MORTEM_CODE_PREFIX):
        return "pre_mortem_" + code[len(_PRE_MORTEM_CODE_PREFIX) :].lower()
    return code.lower()


@dataclass(frozen=True, slots=True)
class ResolvedLensReferences:
    """Run-resolved reference IDs for exactly one lens artifact.

    The repository resolves the artifact's declared references against the
    frozen Run *before* calling a validator (Task 10 Step 7); validators only
    check that content-level citations stay inside these sets.
    """

    source_packet_ids: tuple[str, ...] = ()
    claim_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    assumption_ids: tuple[str, ...] = ()
    challenge_ids: tuple[str, ...] = ()

    @classmethod
    def from_wire(cls, references: Mapping[str, Sequence[str]]) -> "ResolvedLensReferences":
        """Build from the canonical camelCase reference block."""

        def ids(key: str) -> tuple[str, ...]:
            values = references.get(key, ())
            if isinstance(values, (str, bytes)):
                return ()
            return tuple(str(item) for item in values)

        return cls(
            source_packet_ids=ids("sourcePacketIds"),
            claim_ids=ids("claimIds"),
            evidence_ids=ids("evidenceIds"),
            assumption_ids=ids("assumptionIds"),
            challenge_ids=ids("challengeIds"),
        )

    def to_wire(self) -> dict[str, list[str]]:
        """Project back onto the canonical camelCase reference block."""

        return {
            "sourcePacketIds": list(self.source_packet_ids),
            "claimIds": list(self.claim_ids),
            "evidenceIds": list(self.evidence_ids),
            "assumptionIds": list(self.assumption_ids),
            "challengeIds": list(self.challenge_ids),
        }


@dataclass(frozen=True, slots=True)
class LensRepairInput:
    """The regeneration package Validation hands back to the producing worker.

    It never contains repaired or completed content - only which lens failed,
    who owns regeneration, what failed (stable codes + findings) and the
    frozen references the retry must cite ("Validation 不得补写").
    """

    lens_type: StrategicLensType
    owner_worker: str
    phase: str
    reason_codes: tuple[str, ...]
    findings: tuple[str, ...]
    resolved_references: ResolvedLensReferences


@dataclass(frozen=True, slots=True)
class LensBehaviorValidationResult:
    """Structured verdict of one lens behavior validation.

    ``passed=False`` blocks the run; ``repair_input`` is populated exactly
    when the validation failed.
    """

    lens_type: StrategicLensType
    passed: bool
    reason_codes: tuple[str, ...] = ()
    findings: tuple[str, ...] = ()
    repair_input: LensRepairInput | None = field(default=None)


def _result(
    lens_type: StrategicLensType,
    reason_codes: Sequence[str],
    findings: Sequence[str],
    references: ResolvedLensReferences,
) -> LensBehaviorValidationResult:
    codes = tuple(dict.fromkeys(reason_codes))
    if not codes:
        return LensBehaviorValidationResult(lens_type=lens_type, passed=True)
    spec = lens_spec(lens_type)
    return LensBehaviorValidationResult(
        lens_type=lens_type,
        passed=False,
        reason_codes=codes,
        findings=tuple(findings),
        repair_input=LensRepairInput(
            lens_type=lens_type,
            owner_worker=spec.owner_worker,
            phase=spec.phase,
            reason_codes=codes,
            findings=tuple(findings),
            resolved_references=references,
        ),
    )


def _content_not_object(
    lens_type: StrategicLensType,
    content: Any,
    references: ResolvedLensReferences,
) -> LensBehaviorValidationResult | None:
    if isinstance(content, Mapping):
        return None
    return _result(
        lens_type,
        (CODE_CONTENT_NOT_OBJECT,),
        (f"content must be a JSON object, got {type(content).__name__}",),
        references,
    )


def _stage_output(
    lens_type: StrategicLensType,
    content: Mapping[str, Any],
    references: ResolvedLensReferences,
) -> StrategicLensStageOutput:
    """Rebuild the seam envelope from the spec so only content/refs can fail."""

    spec = lens_spec(lens_type)
    return StrategicLensStageOutput(
        lens_type=lens_type,
        source_skill_version=spec.source_skill_version,
        phase=spec.phase,
        references=references.to_wire(),
        research_requests=(),
        content=content,
    )


def _from_report(
    report: LensBehaviorReport, references: ResolvedLensReferences
) -> LensBehaviorValidationResult:
    return _result(report.lens_type, report.reason_codes, report.findings, references)


_PORTER_GATE = PorterFiveForcesLens()
_SCENARIO_GATE = ScenarioPlanningLens()


def validate_porter_five_forces(
    content: Mapping[str, Any], references: ResolvedLensReferences
) -> LensBehaviorValidationResult:
    """L1072: >=2 markets; exactly five forces per market with >=2 resolvable
    Evidence each; boundary/direction-of-change/trend/regulatory/complementors;
    ``scoreIsNotDecisionFormula == true`` and the score never decides."""

    lens_type = StrategicLensType.PORTER_FIVE_FORCES
    guard = _content_not_object(lens_type, content, references)
    if guard is not None:
        return guard
    report = _PORTER_GATE.validate_behavior(_stage_output(lens_type, content, references))
    return _from_report(report, references)


def validate_pre_mortem(
    content: Mapping[str, Any], references: ResolvedLensReferences
) -> LensBehaviorValidationResult:
    """L1073: exactly the internal/external/systemic_hindsight perspectives;
    >=5 failure causes; exactly 3 topRisks with unique complete rank/cause
    refs, each with prevention/contingency/detectionIndicator; explicit
    verdict + rationale."""

    lens_type = StrategicLensType.PRE_MORTEM
    guard = _content_not_object(lens_type, content, references)
    if guard is not None:
        return guard
    spec = lens_spec(lens_type)
    output = {
        "lensType": lens_type.value,
        "sourceSkillVersion": spec.source_skill_version,
        "phase": spec.phase,
        "references": references.to_wire(),
        "researchRequests": [],
        "content": content,
    }
    lane_result = validate_pre_mortem_output(
        output,
        known_evidence_ids=frozenset(references.evidence_ids),
        known_assumption_ids=frozenset(references.assumption_ids),
    )
    blockers = lane_result.blockers
    return _result(
        lens_type,
        tuple(normalize_pre_mortem_code(finding.code) for finding in blockers),
        tuple(
            f"{normalize_pre_mortem_code(finding.code)} @ {finding.path}: {finding.message}"
            for finding in blockers
        ),
        references,
    )


def validate_counterparty_response_matrix(
    content: Mapping[str, Any], references: ResolvedLensReferences
) -> LensBehaviorValidationResult:
    """L1074: 1-2 key actors; 2-3 actions with exactly one ``no_action``;
    one-layer response depth; matrix covers optimal/worst/likely/window/gap/
    counterresponse; publication test + per-action downside asymmetry +
    reflexivity warning."""

    lens_type = StrategicLensType.COUNTERPARTY_RESPONSE_MATRIX
    guard = _content_not_object(lens_type, content, references)
    if guard is not None:
        return guard
    codes, findings = validate_counterparty_content(
        content, registered_assumption_ids=frozenset(references.assumption_ids)
    )
    return _result(lens_type, codes, findings, references)


def validate_scenario_planning(
    content: Mapping[str, Any], references: ResolvedLensReferences
) -> LensBehaviorValidationResult:
    """L1075: predetermined elements + >=2 key uncertainties; exactly 2 axes;
    3-4 scenarios with exactly 1 baseline and >=2 structural breaks; each
    scenario has a timeline, >=3 stakeholder states and 3-5 early signals;
    every strategy tested and at least one result is ``killed``."""

    lens_type = StrategicLensType.SCENARIO_PLANNING
    guard = _content_not_object(lens_type, content, references)
    if guard is not None:
        return guard
    report = _SCENARIO_GATE.validate_behavior(_stage_output(lens_type, content, references))
    return _from_report(report, references)


def validate_meadows_leverage_points(
    content: Mapping[str, Any], references: ResolvedLensReferences
) -> LensBehaviorValidationResult:
    """L1076: system map fully covers boundary/goals/stocks/flows/reinforcing/
    balancing/delays/actors/rules; >=3 leverage levels; >=1 ignored level 1-4
    high-leverage gap and >=1 runaway reinforcing loop; non-empty intervention
    sequence and risk tradeoffs."""

    lens_type = StrategicLensType.MEADOWS_LEVERAGE_POINTS
    guard = _content_not_object(lens_type, content, references)
    if guard is not None:
        return guard
    spec = lens_spec(lens_type)
    payload = {
        "lensType": lens_type.value,
        "sourceSkillVersion": spec.source_skill_version,
        "phase": spec.phase,
        "references": references.to_wire(),
        "researchRequests": [],
        "content": dict(content),
    }
    try:
        validate_meadows_stage_output(payload)
    except MeadowsLensValidationError as exc:
        return _result(
            lens_type,
            tuple(violation.code for violation in exc.violations),
            tuple(f"{violation.code}: {violation.message}" for violation in exc.violations),
            references,
        )
    return _result(lens_type, (), (), references)


LensBehaviorValidator = Callable[
    [Mapping[str, Any], ResolvedLensReferences], LensBehaviorValidationResult
]

# Canonical five-lens dispatch table, keyed by the sole enum authority.
LENS_BEHAVIOR_VALIDATORS: dict[StrategicLensType, LensBehaviorValidator] = {
    StrategicLensType.PORTER_FIVE_FORCES: validate_porter_five_forces,
    StrategicLensType.PRE_MORTEM: validate_pre_mortem,
    StrategicLensType.COUNTERPARTY_RESPONSE_MATRIX: validate_counterparty_response_matrix,
    StrategicLensType.SCENARIO_PLANNING: validate_scenario_planning,
    StrategicLensType.MEADOWS_LEVERAGE_POINTS: validate_meadows_leverage_points,
}


def validate_lens_behavior(
    lens_type: StrategicLensType,
    content: Mapping[str, Any],
    references: ResolvedLensReferences,
) -> LensBehaviorValidationResult:
    """Dispatch one canonical content instance to its lens behavior validator.

    Fails closed on a lens type outside the canonical five-lens set.
    """

    try:
        validator = LENS_BEHAVIOR_VALIDATORS[lens_type]
    except KeyError as exc:
        raise UnknownLensType(f"no behavior validator for lens: {lens_type!r}") from exc
    return validator(content, references)
