"""Meadows leverage-points lens runtime behavior (Synthesis-owned, full mode only).

This module owns exactly one manifest server step for exactly one lens: the
``validate_stage_output_schema_and_lens_behavior`` step for
``lensType=meadows_leverage_points``. It mirrors the meadows branch of the
published method-pack schema
``urn:ludus:method:hardtech-market-direction:strategic-lens-output:1.1.0`` and
enforces the manifest behavior contract
``system_map_three_or_more_levels_high_leverage_gap_runaway_reinforcing_loop_risk_and_intervention_sequence``.

Deliberately out of scope (owned by the shared agents runtime, not this lane):
resolving references against the frozen Run, injecting identity/provenance,
computing content hashes, and persisting ``StrategicLensArtifact`` rows. The
sandbox-consumption accessor below only exposes read-only candidates for the
downstream simulation mapping; it does not import the Simulation canonical
model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Final, Literal
from collections.abc import Mapping

from pydantic import Field, StringConstraints, ValidationError, field_validator, model_validator

from app.contracts.schemas import CanonicalModel
from app.types import StrategicLensType

MEADOWS_LENS_TYPE: Final[str] = StrategicLensType.MEADOWS_LEVERAGE_POINTS.value
MEADOWS_PHASE: Final[str] = "strategic_synthesis"
MEADOWS_SOURCE_SKILL_VERSION: Final[str] = "1.0.0"

# Meadows twelve-level numbering from the source skill: 1 is the deepest
# paradigm-transcending leverage, 12 is a parameter tweak.
LEVEL_NAME_BY_LEVEL: Final[dict[int, str]] = {
    1: "transcend_paradigms",
    2: "paradigm",
    3: "goals",
    4: "self_organization",
    5: "rules",
    6: "information_flows",
    7: "reinforcing_feedback",
    8: "balancing_feedback",
    9: "delays",
    10: "stock_flow_structure",
    11: "buffers",
    12: "parameters",
}

HIGH_LEVERAGE_LEVELS: Final[frozenset[int]] = frozenset({1, 2, 3, 4})

# Fields the server injects from frozen context after validation. A model that
# self-reports any of them is rejected before schema parsing so the violation
# is explicit instead of a generic extra-field error.
SERVER_INJECTED_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "id",
        "artifactId",
        "workspaceId",
        "decisionCaseId",
        "analysisRunId",
        "charterId",
        "methodId",
        "methodVersion",
        "methodContentHash",
        "producerRole",
        "status",
        "originModes",
        "contentHash",
        "createdAt",
    }
)


def strength_band_for_level(level: int) -> str:
    """Map a Meadows level to its schema-locked strength band."""

    if level in HIGH_LEVERAGE_LEVELS:
        return "high"
    if level <= 8:
        return "medium"
    return "low"


LensId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,127}$")]
LongText = Annotated[str, StringConstraints(min_length=1, max_length=5000)]
IdArray = Annotated[list[LensId], Field(max_length=200)]
NonEmptyTextArray = Annotated[list[LongText], Field(min_length=1, max_length=50)]

LevelName = Literal[
    "transcend_paradigms",
    "paradigm",
    "goals",
    "self_organization",
    "rules",
    "information_flows",
    "reinforcing_feedback",
    "balancing_feedback",
    "delays",
    "stock_flow_structure",
    "buffers",
    "parameters",
]


class LensReferences(CanonicalModel):
    """Evidence-versus-judgment anchors resolved later against the frozen Run."""

    source_packet_ids: IdArray
    claim_ids: IdArray
    evidence_ids: IdArray
    assumption_ids: IdArray
    challenge_ids: IdArray

    @field_validator(
        "source_packet_ids",
        "claim_ids",
        "evidence_ids",
        "assumption_ids",
        "challenge_ids",
    )
    @classmethod
    def ids_are_unique(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("reference id arrays must not contain duplicates")
        return values


class ResearchRequest(CanonicalModel):
    request_id: LensId
    question: LongText
    evidence_need: Literal[
        "primary",
        "counterevidence",
        "current_market",
        "regulatory",
        "technical_test",
        "procurement",
        "stakeholder",
    ]
    priority: Literal["medium", "high", "critical"]
    affected_claim_ids: IdArray


class SystemMap(CanonicalModel):
    boundary: LongText
    stated_goal: LongText
    actual_goal: LongText
    stocks: NonEmptyTextArray
    flows: NonEmptyTextArray
    reinforcing_loops: NonEmptyTextArray
    balancing_loops: NonEmptyTextArray
    delays: NonEmptyTextArray
    actors: NonEmptyTextArray
    rules_and_incentives: NonEmptyTextArray


class LeverageIntervention(CanonicalModel):
    intervention_id: LensId
    level: Annotated[int, Field(ge=1, le=12)]
    level_name: LevelName
    strength_band: Literal["low", "medium", "high"]
    target: LongText
    action: LongText
    feasibility: Literal["low", "medium", "high"]
    expected_effect: LongText
    failure_signal: LongText

    @model_validator(mode="after")
    def level_name_and_band_match_level(self) -> LeverageIntervention:
        expected_name = LEVEL_NAME_BY_LEVEL[self.level]
        if self.level_name != expected_name:
            raise ValueError(
                f"level {self.level} requires levelName {expected_name!r}, "
                f"got {self.level_name!r}"
            )
        expected_band = strength_band_for_level(self.level)
        if self.strength_band != expected_band:
            raise ValueError(
                f"level {self.level} requires strengthBand {expected_band!r}, "
                f"got {self.strength_band!r}"
            )
        return self


class HighLeverageIntervention(LeverageIntervention):
    """An avoided level 1-4 gap; resistance and disruption risk are mandatory."""

    level: Annotated[int, Field(ge=1, le=4)]
    strength_band: Literal["high"]
    why_avoided: LongText
    disruption_risk: LongText


class RunawayLoop(CanonicalModel):
    loop: LongText
    runaway_signal: LongText
    brake: LongText


class InterventionStep(CanonicalModel):
    order: Annotated[int, Field(ge=1, le=12)]
    intervention_id: LensId
    purpose: Literal["trust_building", "information_gain", "system_change", "risk_control"]
    precondition: LongText
    failure_signal: LongText


MeadowsLevel = Annotated[int, Field(ge=1, le=12)]


class MeadowsContent(CanonicalModel):
    system_map: SystemMap
    levels_covered: Annotated[list[MeadowsLevel], Field(min_length=3, max_length=12)]
    current_interventions: Annotated[
        list[LeverageIntervention], Field(min_length=1, max_length=20)
    ]
    high_leverage_gaps: Annotated[
        list[HighLeverageIntervention], Field(min_length=1, max_length=8)
    ]
    runaway_positive_loops: Annotated[list[RunawayLoop], Field(min_length=1, max_length=10)]
    intervention_sequence: Annotated[list[InterventionStep], Field(min_length=2, max_length=12)]
    risk_tradeoffs: NonEmptyTextArray

    @field_validator("levels_covered")
    @classmethod
    def levels_are_unique(cls, values: list[int]) -> list[int]:
        if len(values) != len(set(values)):
            raise ValueError("levelsCovered must not contain duplicates")
        return values


class MeadowsStageOutput(CanonicalModel):
    """Untrusted model stage output, meadows branch of the discriminated union."""

    lens_type: Literal["meadows_leverage_points"]
    source_skill_version: Literal["1.0.0"]
    phase: Literal["strategic_synthesis"]
    references: LensReferences
    research_requests: Annotated[list[ResearchRequest], Field(max_length=10)]
    content: MeadowsContent


@dataclass(frozen=True)
class MeadowsViolation:
    """One structured schema or behavior finding; codes are stable identifiers."""

    code: str
    message: str


class MeadowsLensValidationError(ValueError):
    """Stage output failed the meadows schema or behavior contract."""

    def __init__(self, violations: tuple[MeadowsViolation, ...]) -> None:
        self.violations = violations
        summary = "; ".join(f"{item.code}: {item.message}" for item in violations)
        super().__init__(f"meadows stage output rejected: {summary}")


def check_meadows_behavior(output: MeadowsStageOutput) -> tuple[MeadowsViolation, ...]:
    """Pure behavior checks beyond field shape, mirroring the eval assertions.

    Covers: interventions on at least three distinct levels, levelsCovered
    consistency, a real level 1-4 gap, sequence referential integrity and dense
    ordering, an unpaired ``transcend_paradigms`` action, and the
    evidence-versus-judgment anchoring requirement.
    """

    violations: list[MeadowsViolation] = []
    content = output.content

    all_interventions: list[LeverageIntervention] = [
        *content.current_interventions,
        *content.high_leverage_gaps,
    ]
    seen_ids: set[str] = set()
    duplicate_ids: set[str] = set()
    for intervention in all_interventions:
        if intervention.intervention_id in seen_ids:
            duplicate_ids.add(intervention.intervention_id)
        seen_ids.add(intervention.intervention_id)
    if duplicate_ids:
        violations.append(
            MeadowsViolation(
                code="duplicate_intervention_id",
                message=(
                    "interventionId values must be unique across currentInterventions "
                    f"and highLeverageGaps: {sorted(duplicate_ids)}"
                ),
            )
        )

    actual_levels = {intervention.level for intervention in all_interventions}
    if len(actual_levels) < 3:
        violations.append(
            MeadowsViolation(
                code="interventions_cover_fewer_than_three_levels",
                message=(
                    "current and gap interventions must span at least three distinct "
                    f"Meadows levels, found {sorted(actual_levels)}"
                ),
            )
        )
    if set(content.levels_covered) != actual_levels:
        violations.append(
            MeadowsViolation(
                code="levels_covered_mismatch",
                message=(
                    f"levelsCovered {sorted(content.levels_covered)} must equal the "
                    f"distinct levels of the declared interventions {sorted(actual_levels)}"
                ),
            )
        )

    level_by_id = {item.intervention_id: item.level for item in all_interventions}
    unknown_refs = [
        step.intervention_id
        for step in content.intervention_sequence
        if step.intervention_id not in level_by_id
    ]
    if unknown_refs:
        violations.append(
            MeadowsViolation(
                code="sequence_references_unknown_intervention",
                message=(
                    "interventionSequence must only reference declared interventions; "
                    f"unknown: {sorted(set(unknown_refs))}"
                ),
            )
        )

    orders = [step.order for step in content.intervention_sequence]
    if orders != list(range(1, len(orders) + 1)):
        violations.append(
            MeadowsViolation(
                code="sequence_orders_not_dense_ascending",
                message=(
                    "interventionSequence orders must be 1..n in array order without "
                    f"gaps or duplicates, got {orders}"
                ),
            )
        )

    sequence_levels = [
        level_by_id[step.intervention_id]
        for step in content.intervention_sequence
        if step.intervention_id in level_by_id
    ]
    if 1 in sequence_levels and not any(level != 1 for level in sequence_levels):
        violations.append(
            MeadowsViolation(
                code="transcend_paradigms_unpaired",
                message=(
                    "a transcend_paradigms (level 1) step cannot stand alone; the "
                    "sequence must pair it with an executable mechanism on another level"
                ),
            )
        )

    if not output.references.evidence_ids and not output.references.assumption_ids:
        violations.append(
            MeadowsViolation(
                code="unanchored_evidence_and_assumptions",
                message=(
                    "facts must cite Evidence IDs and speculation must cite Assumption "
                    "IDs; both reference arrays are empty so the lens output is not "
                    "auditable"
                ),
            )
        )

    return tuple(violations)


def validate_meadows_stage_output(payload: Mapping[str, Any]) -> MeadowsStageOutput:
    """Validate one untrusted meadows stage output; raise with structured violations.

    Order matters: self-reported server identity fields are rejected first with
    explicit codes, then field shape, then the behavior contract.
    """

    self_reported = sorted(SERVER_INJECTED_FIELDS.intersection(payload.keys()))
    if self_reported:
        raise MeadowsLensValidationError(
            tuple(
                MeadowsViolation(
                    code=f"server_identity_self_reported:{field}",
                    message=(
                        f"field {field!r} is injected by the server from frozen context "
                        "and must not be self-reported by the model"
                    ),
                )
                for field in self_reported
            )
        )

    try:
        output = MeadowsStageOutput.model_validate(dict(payload))
    except ValidationError as exc:
        violations = tuple(
            MeadowsViolation(
                code="schema:" + ".".join(str(part) for part in error["loc"]),
                message=error["msg"],
            )
            for error in exc.errors()
        )
        raise MeadowsLensValidationError(violations) from exc

    behavior_violations = check_meadows_behavior(output)
    if behavior_violations:
        raise MeadowsLensValidationError(behavior_violations)
    return output


@dataclass(frozen=True)
class MeadowsLeverCandidate:
    """Read-only candidate for the downstream sandbox lever/edge mapping."""

    intervention_id: str
    level: int
    level_name: str
    kind: Literal["current", "high_leverage_gap"]
    target: str
    action: str
    expected_effect: str


@dataclass(frozen=True)
class MeadowsSequenceStep:
    order: int
    intervention_id: str
    purpose: str
    precondition: str
    failure_signal: str


@dataclass(frozen=True)
class MeadowsSandboxConsumption:
    """What the report/sandbox owners consume: levers/edges plus the sequence.

    This satisfies the eval consumption contract ``meadowsMustAffect:
    [simulation_lever_or_edge, intervention_sequence]`` without this lane
    touching the Simulation canonical model.
    """

    lever_candidates: tuple[MeadowsLeverCandidate, ...]
    intervention_sequence: tuple[MeadowsSequenceStep, ...]


def sandbox_consumption(output: MeadowsStageOutput) -> MeadowsSandboxConsumption:
    """Project a validated meadows output into sandbox consumption candidates."""

    levers = [
        MeadowsLeverCandidate(
            intervention_id=item.intervention_id,
            level=item.level,
            level_name=item.level_name,
            kind="current",
            target=item.target,
            action=item.action,
            expected_effect=item.expected_effect,
        )
        for item in output.content.current_interventions
    ]
    levers.extend(
        MeadowsLeverCandidate(
            intervention_id=item.intervention_id,
            level=item.level,
            level_name=item.level_name,
            kind="high_leverage_gap",
            target=item.target,
            action=item.action,
            expected_effect=item.expected_effect,
        )
        for item in output.content.high_leverage_gaps
    )
    sequence = tuple(
        MeadowsSequenceStep(
            order=step.order,
            intervention_id=step.intervention_id,
            purpose=step.purpose,
            precondition=step.precondition,
            failure_signal=step.failure_signal,
        )
        for step in sorted(output.content.intervention_sequence, key=lambda step: step.order)
    )
    return MeadowsSandboxConsumption(
        lever_candidates=tuple(levers),
        intervention_sequence=sequence,
    )
