"""Formal quality gate (Task 10 Step 5, case_api_data scope).

The runtime gate keeps exactly FOUR orthogonal checks (18-plan Task 10 Step 5
+ 04-decision-methodology 流程质量 row): evidence sufficiency, adversarial
pressure, logic consistency and synthesis deviation risk. Their multiplicative
value decides deliverability ONLY — it is not a probability and never a
competing total score. Any severe failure of one check moves the AnalysisRun
to ``blocked`` (only legal from ``validating``, CCR-20260725-ANALYSIS-01
section 1.4); the frontend may then show clearly marked draft details and
repair actions, full runs may keep an HTML draft, but PDF and formal
simulation stay disabled.

The user-visible six-dimension quality profile (``RecommendationQuality``) is
an explanatory *projection* of these checks plus simulation results — never a
second scoring system:

* evidence sufficiency      -> evidence_availability / claim_support
* adversarial pressure      -> assumption_stability
* logic consistency         -> causal_reliability
* synthesis deviation risk  -> strategic_robustness (with cross-scenario
                               results) / process_quality (with the overall
                               verdict)

The full gate additionally calls the merged five-lens behavior validators
(``app.strategic_lenses.validators``, import-only) one by one; a payload whose
JSON schema passed but whose behavior fails MUST NOT reach ``ready``
("schema 过但行为败→不得 ready"), and Validation never writes repaired content.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import prod
from typing import Any, Final, Mapping, Sequence
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum as SAEnum,
    Float,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    select,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import (
    StrategicLensArtifact,
    created_at_column,
    json_list_column,
    json_object_column,
    uuid_primary_key,
    workspace_column,
)
from app.strategic_lenses.validators import (
    LensBehaviorValidationResult,
    LensRepairInput,
    ResolvedLensReferences,
    validate_lens_behavior,
)
from app.types import (
    FULL_REQUIRED_STRATEGIC_LENSES,
    LensProducerRole,
    StrategicLensArtifactStatus,
    StrategicLensType,
)

from .claims import ClaimSupportAssessment, ReconciliationOutcome
from .devils_advocate import AdversarialArcResult

# --- the four orthogonal checks (closed set) ---------------------------------
QUALITY_GATE_CHECKS: Final[tuple[str, ...]] = (
    "evidence_sufficiency",
    "adversarial_pressure",
    "logic_consistency",
    "synthesis_deviation",
)
CHECK_STATUSES: Final[tuple[str, ...]] = ("passed", "warning", "severe_failure")

# PG enum for the gate verdict column, no parallel Python StrEnum (Task 9
# packet-role precedent): the decision-os invariants suite requires it.
QUALITY_GATE_STATUSES: Final[tuple[str, ...]] = ("passed", "blocked")
QUALITY_GATE_STATUS_ENUM = SAEnum(
    *QUALITY_GATE_STATUSES, name="quality_gate_status", native_enum=True
)

# Canonical producer mapping (types.py LensProducerRole docstring; 18 Task 9
# Step 5): Research -> porter; Critic -> pre_mortem + counterparty;
# Synthesis -> scenario + meadows. Validation checks, never produces.
EXPECTED_PRODUCER_BY_LENS: Final[dict[StrategicLensType, LensProducerRole]] = {
    StrategicLensType.PORTER_FIVE_FORCES: LensProducerRole.RESEARCH,
    StrategicLensType.PRE_MORTEM: LensProducerRole.CRITIC,
    StrategicLensType.COUNTERPARTY_RESPONSE_MATRIX: LensProducerRole.CRITIC,
    StrategicLensType.SCENARIO_PLANNING: LensProducerRole.SYNTHESIS,
    StrategicLensType.MEADOWS_LEVERAGE_POINTS: LensProducerRole.SYNTHESIS,
}


def _check_in(column: str, values: Sequence[str]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


class QualityGateResult(Base):
    """Persisted verdict of one formal gate evaluation for one Run."""

    __tablename__ = "quality_gate_results"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_quality_gate_results_workspace_id"),
        UniqueConstraint(
            "workspace_id",
            "analysis_run_id",
            name="uq_quality_gate_results_workspace_run",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_quality_gate_results_workspace_case",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "analysis_run_id"],
            [
                "analysis_runs.workspace_id",
                "analysis_runs.decision_case_id",
                "analysis_runs.analysis_run_id",
            ],
            name="fk_quality_gate_results_workspace_case_run",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            _check_in("evidence_sufficiency_status", CHECK_STATUSES),
            name="gate_evidence_status_valid",
        ),
        CheckConstraint(
            _check_in("adversarial_pressure_status", CHECK_STATUSES),
            name="gate_adversarial_status_valid",
        ),
        CheckConstraint(
            _check_in("logic_consistency_status", CHECK_STATUSES),
            name="gate_logic_status_valid",
        ),
        CheckConstraint(
            _check_in("synthesis_deviation_status", CHECK_STATUSES),
            name="gate_synthesis_status_valid",
        ),
        CheckConstraint(
            "evidence_sufficiency_score >= 0 AND evidence_sufficiency_score <= 1 AND "
            "adversarial_pressure_score >= 0 AND adversarial_pressure_score <= 1 AND "
            "logic_consistency_score >= 0 AND logic_consistency_score <= 1 AND "
            "synthesis_deviation_score >= 0 AND synthesis_deviation_score <= 1 AND "
            "multiplicative_value >= 0 AND multiplicative_value <= 1",
            name="gate_scores_in_unit_interval",
        ),
        # A blocked verdict can never be deliverable, in either direction.
        CheckConstraint(
            "(status = 'passed') = deliverable",
            name="gate_blocked_never_deliverable",
        ),
        Index("ix_quality_gate_results_workspace_case", "workspace_id", "decision_case_id"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(QUALITY_GATE_STATUS_ENUM, nullable=False)
    evidence_sufficiency_score: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_sufficiency_status: Mapped[str] = mapped_column(String(16), nullable=False)
    adversarial_pressure_score: Mapped[float] = mapped_column(Float, nullable=False)
    adversarial_pressure_status: Mapped[str] = mapped_column(String(16), nullable=False)
    logic_consistency_score: Mapped[float] = mapped_column(Float, nullable=False)
    logic_consistency_status: Mapped[str] = mapped_column(String(16), nullable=False)
    synthesis_deviation_score: Mapped[float] = mapped_column(Float, nullable=False)
    synthesis_deviation_status: Mapped[str] = mapped_column(String(16), nullable=False)
    multiplicative_value: Mapped[float] = mapped_column(Float, nullable=False)
    deliverable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason_codes: Mapped[list[str]] = json_list_column()
    # Explanatory six-dimension projection (RecommendationQuality shape).
    quality_profile: Mapped[dict[str, Any]] = json_object_column()
    checked_at: Mapped[datetime] = created_at_column()


# --- pure gate computation ----------------------------------------------------


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    """Verdict of one orthogonal check."""

    check: str
    score: float
    status: str  # passed | warning | severe_failure
    reason_codes: tuple[str, ...] = ()
    findings: tuple[str, ...] = ()

    @property
    def severe(self) -> bool:
        return self.status == "severe_failure"


@dataclass(frozen=True, slots=True)
class LogicAudit:
    """Deterministic coherence findings handed to the logic check.

    ``recommendation_contradicted`` marks a recommendation that relies on a
    claim whose opposing evidence prevailed — that is a severe logic failure.
    """

    contradiction_pairs: tuple[tuple[str, str], ...] = ()
    circular_reference_ids: tuple[str, ...] = ()
    recommendation_contradicted: bool = False


@dataclass(frozen=True, slots=True)
class SynthesisAudit:
    """Deterministic drift findings handed to the deviation check."""

    orphan_citation_ids: tuple[str, ...] = ()  # cited in body, absent from ledger
    uncited_core_claim_ids: tuple[str, ...] = ()  # core claims the body ignores
    recommendation_beyond_evidence: bool = False  # recommendation cites nothing
    scenario_strategy_flips: tuple[str, ...] = ()  # strategies killed by scenarios
    recommended_strategy_flipped: bool = False


@dataclass(frozen=True, slots=True)
class GateSubject:
    """Everything one gate evaluation may look at (no hidden inputs)."""

    analysis_level: str
    claim_assessments: Sequence[ClaimSupportAssessment]
    core_claim_ids: frozenset[str]
    adversarial: AdversarialArcResult
    reconciliation: ReconciliationOutcome | None = None
    logic: LogicAudit = LogicAudit()
    synthesis: SynthesisAudit = SynthesisAudit()
    lens_verdicts: Sequence[LensBehaviorValidationResult] = ()
    lens_set_reason_codes: Sequence[str] = ()


@dataclass(frozen=True, slots=True)
class QualityGateEvaluation:
    """Full gate verdict: four orthogonal checks + projection, one status."""

    status: str  # passed | blocked
    checks: tuple[CheckOutcome, ...]
    multiplicative_value: float
    deliverable: bool
    reason_codes: tuple[str, ...]
    quality_profile: dict[str, Any]
    return_to_synthesis: bool
    repair_inputs: tuple[LensRepairInput, ...] = ()

    @property
    def pdf_allowed(self) -> bool:
        # PDF and formal simulation are always disabled on a blocked run.
        return self.status == "passed"

    @property
    def simulation_allowed(self) -> bool:
        return self.status == "passed"

    def check(self, name: str) -> CheckOutcome:
        for outcome in self.checks:
            if outcome.check == name:
                return outcome
        raise KeyError(name)


def _evidence_check(subject: GateSubject) -> CheckOutcome:
    codes: list[str] = []
    findings: list[str] = []
    status = "passed"
    core = [item for item in subject.claim_assessments if item.claim_id in subject.core_claim_ids]
    for assessment in core:
        if assessment.claim_support in ("unsupported", "assumption_only"):
            # Step 1 red light: a core claim without accepted/conditional
            # evidence blocks the run.
            codes.append("core_claim_unsupported")
            findings.append(
                f"core claim {assessment.claim_id} is {assessment.claim_support}"
            )
            status = "severe_failure"
        elif assessment.claim_support == "conflicted" and status != "severe_failure":
            codes.append("core_claim_conflicted")
            findings.append(f"core claim {assessment.claim_id} is conflicted")
            status = "warning"
    if core:
        score = min(assessment.support_score for assessment in core)
    else:
        # No core claims at all: nothing carries the recommendation.
        codes.append("core_claim_missing")
        findings.append("run produced no core claims")
        status = "severe_failure"
        score = 0.0
    if status == "severe_failure":
        score = min(score, 0.0)
    return CheckOutcome(
        check="evidence_sufficiency",
        score=max(0.0, min(score, 1.0)),
        status=status,
        reason_codes=tuple(dict.fromkeys(codes)),
        findings=tuple(findings),
    )


def _adversarial_check(subject: GateSubject) -> CheckOutcome:
    arc = subject.adversarial
    codes: list[str] = list(arc.reason_codes)
    findings: list[str] = list(arc.findings)
    if arc.return_to_synthesis:
        codes.insert(0, "fatal_flaw_returns_to_synthesis")
        status = "severe_failure"
    elif any(
        code in ("challenge_without_disposition", "challenge_rejection_without_reason")
        for code in codes
    ):
        status = "severe_failure"
    elif codes:
        status = "warning"
    else:
        status = "passed"
    if status == "severe_failure":
        score = 0.0
    elif arc.important_total == 0:
        # Zero adversarial pressure is itself a warning: nobody pushed back.
        codes.append("adversarial_no_important_findings")
        findings.append("no important adversarial findings were raised")
        status = "warning" if status == "passed" else status
        score = 0.5
    else:
        dispositioned = arc.accepted_changes + arc.rejected_with_reason + arc.escalated
        score = dispositioned / arc.important_total
        if status == "warning":
            score = min(score, 0.75)
    return CheckOutcome(
        check="adversarial_pressure",
        score=max(0.0, min(score, 1.0)),
        status=status,
        reason_codes=tuple(dict.fromkeys(codes)),
        findings=tuple(findings),
    )


def _logic_check(subject: GateSubject) -> CheckOutcome:
    codes: list[str] = []
    findings: list[str] = []
    status = "passed"
    score = 1.0
    if subject.logic.recommendation_contradicted:
        codes.append("recommendation_contradicts_evidence")
        findings.append("recommendation relies on a claim whose opposition prevailed")
        status = "severe_failure"
        score = 0.0
    if subject.logic.circular_reference_ids:
        codes.append("circular_claim_reference")
        findings.append(
            "circular claim references: " + ", ".join(subject.logic.circular_reference_ids)
        )
        if status == "passed":
            status = "warning"
        score = min(score, 0.6)
    if subject.logic.contradiction_pairs:
        codes.append("internal_contradiction")
        findings.append(f"{len(subject.logic.contradiction_pairs)} contradiction pair(s) in body")
        if status == "passed":
            status = "warning"
        score = min(score, 0.6)
    unresolved = subject.reconciliation.unresolved if subject.reconciliation else ()
    if unresolved:
        # Unadjudicable factual conflicts already downgraded the claims and
        # MUST surface in the report; here they cost logic confidence.
        codes.append("unresolved_factual_conflict")
        findings.extend(finding.detail for finding in unresolved)
        if status == "passed":
            status = "warning"
        score = min(score, 0.5)
    return CheckOutcome(
        check="logic_consistency",
        score=max(0.0, min(score, 1.0)),
        status=status,
        reason_codes=tuple(dict.fromkeys(codes)),
        findings=tuple(findings),
    )


def _synthesis_check(subject: GateSubject) -> CheckOutcome:
    codes: list[str] = []
    findings: list[str] = []
    status = "passed"
    score = 1.0
    audit = subject.synthesis
    if audit.recommendation_beyond_evidence:
        codes.append("synthesis_beyond_evidence")
        findings.append("recommendation is not grounded in any ledger citation")
        status = "severe_failure"
        score = 0.0
    if audit.orphan_citation_ids:
        codes.append("synthesis_orphan_citation")
        findings.append("orphan citations: " + ", ".join(audit.orphan_citation_ids))
        if status == "passed":
            status = "warning"
        score = min(score, 0.6)
    if audit.uncited_core_claim_ids:
        codes.append("synthesis_core_claim_uncited")
        findings.append(
            "core claims missing from the body: " + ", ".join(audit.uncited_core_claim_ids)
        )
        if status == "passed":
            status = "warning"
        score = min(score, 0.7)
    if audit.recommended_strategy_flipped:
        codes.append("recommended_strategy_flip_detected")
        findings.append("the recommended strategy is killed in at least one scenario")
        if status == "passed":
            status = "warning"
        score = min(score, 0.4)
    # Behavior-failed lenses are synthesis-side deviation: content shipped
    # that does not satisfy the frozen behavior contract.
    failed_lenses = [verdict for verdict in subject.lens_verdicts if not verdict.passed]
    if failed_lenses or subject.lens_set_reason_codes:
        for verdict in failed_lenses:
            codes.append("lens_behavior_failed")
            findings.append(
                f"{verdict.lens_type.value} failed behavior: "
                + ", ".join(verdict.reason_codes)
            )
        codes.extend(subject.lens_set_reason_codes)
        status = "severe_failure"
        score = 0.0
    return CheckOutcome(
        check="synthesis_deviation",
        score=max(0.0, min(score, 1.0)),
        status=status,
        reason_codes=tuple(dict.fromkeys(codes)),
        findings=tuple(findings),
    )


def _project_quality_profile(
    subject: GateSubject, checks: Mapping[str, CheckOutcome], status: str
) -> dict[str, Any]:
    """Six-dimension explanatory projection — never a second scoring system."""

    evidence = checks["evidence_sufficiency"]
    adversarial = checks["adversarial_pressure"]
    logic = checks["logic_consistency"]
    synthesis = checks["synthesis_deviation"]

    if evidence.severe:
        evidence_availability = "blocked"
    elif evidence.status == "warning":
        evidence_availability = "conditional"
    else:
        evidence_availability = "sufficient" if evidence.score >= 0.5 else "insufficient"

    core = [item for item in subject.claim_assessments if item.claim_id in subject.core_claim_ids]
    if any(item.claim_support == "unsupported" for item in core) or not core:
        claim_support = "unsupported"
    elif any(item.claim_support == "assumption_only" for item in core):
        claim_support = "assumption_only"
    elif any(item.claim_support == "conflicted" for item in core):
        claim_support = "conflicted"
    else:
        claim_support = "supported"

    if adversarial.severe:
        assumption_stability = "fatal_unknown"
    elif adversarial.status == "warning":
        assumption_stability = "fragile"
    else:
        assumption_stability = "stable"

    if logic.severe:
        causal_reliability = "rejected"
    elif logic.status == "warning":
        causal_reliability = "conditional"
    else:
        causal_reliability = "confirmed"

    if subject.synthesis.recommended_strategy_flipped:
        strategic_robustness = "flip_detected"
    elif synthesis.status != "passed" or subject.synthesis.scenario_strategy_flips:
        strategic_robustness = "scenario_sensitive"
    else:
        strategic_robustness = "robust"

    if status == "blocked":
        process_quality = "blocked"
    elif any(outcome.status == "warning" for outcome in checks.values()):
        process_quality = "warning"
    else:
        process_quality = "passed"

    dimension_scores = {
        "evidence_availability": evidence.score,
        "claim_support": evidence.score,
        "assumption_stability": adversarial.score,
        "causal_reliability": logic.score,
        "strategic_robustness": synthesis.score,
        "process_quality": min(outcome.score for outcome in checks.values()),
    }
    weakest_dimension = min(dimension_scores, key=dimension_scores.get)

    rationale = [
        f"{outcome.check}: {outcome.status}"
        + (f" ({', '.join(outcome.reason_codes)})" if outcome.reason_codes else "")
        for outcome in checks.values()
    ]
    return {
        "evidenceAvailability": evidence_availability,
        "claimSupport": claim_support,
        "assumptionStability": assumption_stability,
        "causalReliability": causal_reliability,
        "strategicRobustness": strategic_robustness,
        "processQuality": process_quality,
        "weakestDimension": weakest_dimension,
        "rationale": rationale,
    }


class ReportQualityGate:
    """Formal gate: four orthogonal checks over one run's gate subject."""

    def evaluate(self, subject: GateSubject) -> QualityGateEvaluation:
        checks = {
            "evidence_sufficiency": _evidence_check(subject),
            "adversarial_pressure": _adversarial_check(subject),
            "logic_consistency": _logic_check(subject),
            "synthesis_deviation": _synthesis_check(subject),
        }
        severe = any(outcome.severe for outcome in checks.values())
        status = "blocked" if severe else "passed"
        multiplicative_value = prod(outcome.score for outcome in checks.values())
        reason_codes = tuple(
            dict.fromkeys(
                code for outcome in checks.values() for code in outcome.reason_codes
            )
        )
        repair_inputs = tuple(
            verdict.repair_input
            for verdict in subject.lens_verdicts
            if verdict.repair_input is not None
        )
        return QualityGateEvaluation(
            status=status,
            checks=tuple(checks.values()),
            # the multiplicative value only decides deliverability
            multiplicative_value=multiplicative_value,
            deliverable=status == "passed",
            reason_codes=reason_codes,
            quality_profile=_project_quality_profile(subject, checks, status),
            return_to_synthesis=subject.adversarial.return_to_synthesis,
            repair_inputs=repair_inputs,
        )


# --- full-run five-lens audit (wire-level exact set + behavior re-check) -----


@dataclass(frozen=True, slots=True)
class LensSetAudit:
    """Wire-level five-artifact audit + per-lens behavior verdicts."""

    ok: bool
    reason_codes: tuple[str, ...]
    findings: tuple[str, ...]
    behavior_verdicts: tuple[LensBehaviorValidationResult, ...] = ()
    ready_artifact_ids: tuple[str, ...] = ()


async def audit_full_run_lens_set(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    decision_case_id: UUID,
    analysis_run_id: UUID,
    charter_id: UUID,
    frozen_lens_types: Sequence[str],
    referenced_artifact_ids: Sequence[str] | None = None,
) -> LensSetAudit:
    """Audit the persisted lens set of one full Run against its frozen Charter.

    Reasons are stable lower_snake codes; ``strategic_lens_incomplete`` mirrors
    the canonical wire failure (10-api ``STRATEGIC_LENS_INCOMPLETE``). The
    behavior validators re-run on every ready artifact — a schema-passing but
    behavior-failing payload keeps the run out of ``ready`` and is reported
    with its repair input; nothing is repaired or rewritten here.
    """

    codes: list[str] = []
    findings: list[str] = []

    frozen = [StrategicLensType(value) for value in frozen_lens_types]
    if sorted(frozen) != sorted(FULL_REQUIRED_STRATEGIC_LENSES):
        codes.append("strategic_lens_set_not_canonical")
        findings.append("frozen charter lens set is not the canonical five-lens set")

    rows = (
        await session.execute(
            select(StrategicLensArtifact).where(
                StrategicLensArtifact.workspace_id == workspace_id,
                StrategicLensArtifact.analysis_run_id == analysis_run_id,
            )
        )
    ).scalars().all()

    ready = [row for row in rows if row.status is StrategicLensArtifactStatus.READY]
    ready_types = [row.lens_type for row in ready]

    if len(ready_types) != len(set(ready_types)):
        codes.append("strategic_lens_duplicate_type")
        findings.append("more than one ready artifact for the same lens type")
    missing = [lens.value for lens in frozen if lens not in ready_types]
    if missing:
        codes.append("strategic_lens_incomplete")
        findings.append("missing ready lens artifacts: " + ", ".join(missing))
    extra = [lens.value for lens in set(ready_types) if lens not in frozen]
    if extra:
        codes.append("strategic_lens_outside_charter")
        findings.append("ready artifacts outside the frozen set: " + ", ".join(extra))

    behavior_verdicts: list[LensBehaviorValidationResult] = []
    for row in ready:
        if row.decision_case_id != decision_case_id:
            codes.append("strategic_lens_cross_case")
            findings.append(f"artifact {row.strategic_lens_artifact_id} belongs to another case")
        if row.charter_id != charter_id:
            codes.append("strategic_lens_cross_charter")
            findings.append(
                f"artifact {row.strategic_lens_artifact_id} was frozen under another charter"
            )
        expected_role = EXPECTED_PRODUCER_BY_LENS[row.lens_type]
        if row.producer_role is not expected_role:
            codes.append("strategic_lens_wrong_producer_role")
            findings.append(
                f"{row.lens_type.value} produced by {row.producer_role.value}, "
                f"expected {expected_role.value}"
            )
        payload = row.payload or {}
        references = ResolvedLensReferences.from_wire(payload.get("references", {}))
        verdict = validate_lens_behavior(
            row.lens_type, payload.get("content", {}), references
        )
        behavior_verdicts.append(verdict)
        if not verdict.passed:
            codes.append("lens_behavior_failed")
            findings.append(
                f"{row.lens_type.value} passed schema but failed behavior: "
                + ", ".join(verdict.reason_codes)
            )

    if referenced_artifact_ids is not None:
        referenced = {str(item) for item in referenced_artifact_ids}
        persisted = {str(row.strategic_lens_artifact_id) for row in ready}
        if referenced != persisted or len(referenced_artifact_ids) != 5:
            # Body text can never substitute the five exact references.
            codes.append("strategic_lens_reference_mismatch")
            findings.append(
                "report lensArtifactIds do not exactly reference the five ready artifacts"
            )

    unique_codes = tuple(dict.fromkeys(codes))
    return LensSetAudit(
        ok=not unique_codes,
        reason_codes=unique_codes,
        findings=tuple(findings),
        behavior_verdicts=tuple(behavior_verdicts),
        ready_artifact_ids=tuple(str(row.strategic_lens_artifact_id) for row in ready),
    )
