"""Blocking information quality gateway (Task 8).

Deterministic rules only; no model calls. The gateway consumes evidence
candidates (already normalized and same-source-grouped), computes the
orthogonal quality dimensions, and returns one of the four canonical
verdicts from ``app.types.EvidenceVerdict``:

- ``accepted``: may support a core claim.
- ``conditional``: usable only together with the returned applicability
  limits (the gateway always emits at least one limit for this verdict).
- ``lead_only``: never enters the Worker evidence set; it may only seed the
  next retrieval round (``triggers_next_retrieval`` is set).
- ``rejected``: excluded entirely.

Source levels L1-L6 are a *category*, not a score: the orthogonal dimensions
are computed independently, and an L1 grade never yields ``accepted`` on its
own (independence/corroboration still gates it down to ``conditional``).
Every verdict carries machine reason codes plus actionable remediation steps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Final
from uuid import UUID

from app.types import EvidenceVerdict

from .normalizer import (
    IndependentSourceGrouping,
    SourceIdentity,
    group_independent_sources,
)

SOURCE_GRADE_QUALITY: Final[dict[str, float]] = {
    "L1_primary": 1.0,
    "L2_reputable": 0.85,
    "L3_industry": 0.7,
    "L4_general": 0.5,
    "L5_opinion": 0.3,
    "L6_unverified": 0.1,
}

# Deterministic freshness banding (retrieval-relative).
_FRESH_DAYS = 180
_AGING_DAYS = 540

# Blocking thresholds.
_REJECT_AUTHENTICITY = 0.3
_REJECT_EXTRACTION = 0.3
_REJECT_RELEVANCE = 0.2
_LEAD_ONLY_AUTHENTICITY = 0.5
_ACCEPT_MIN_DIMENSION = 0.6
_CORE_MIN_INDEPENDENT_SOURCES = 2

# Reason codes with their actionable remediation steps.
REMEDIATIONS: Final[dict[str, str]] = {
    "authenticity_below_floor": "Discard the artifact and refetch from a verifiable origin.",
    "extraction_unreliable": "Re-extract the document with a higher-fidelity parser.",
    "irrelevant_to_scope": "Narrow the retrieval query to the decision scope.",
    "unverifiable_source": "Find a verifiable primary or reputable source for the same claim.",
    "single_independent_source": (
        "Retrieve at least one additional independent source for the core claim."
    ),
    "same_source_citations_collapsed": (
        "The citing articles share one underlying report; corroborate with a "
        "different root source."
    ),
    "stale_evidence": "Check for a newer edition or re-confirm the finding is still valid.",
    "bias_flagged": "Balance with a source holding no stake in the outcome.",
    "completeness_warning": "Fetch the full document instead of the partial extract.",
    "conflicting_evidence_present": "Resolve or explicitly scope the conflicting evidence.",
    "dimension_below_acceptance": "Raise the failing quality dimension or keep the limits.",
    "l1_requires_corroboration": (
        "L1 category alone is insufficient; add an independent corroborating source."
    ),
}


@dataclass(frozen=True)
class EvidenceCandidate:
    """One gate input: normalized artifact metadata plus scoring signals.

    ``supports_core_claim`` marks candidates intended to support a core
    proposition (06-data-model Claim.importance == "core"); the gate is
    stricter for those. ``verifiable`` is False when neither the origin nor
    the content hash chain can be independently checked (for example an
    anonymous social media post).
    """

    candidate_key: str
    source_grade: str
    identity: SourceIdentity
    supports_core_claim: bool = True
    verifiable: bool = True
    authenticity: float = 0.5
    relevance: float = 0.5
    applicability: float = 0.5
    extraction_reliability: float = 0.5
    published_at: datetime | None = None
    retrieved_at: datetime | None = None
    bias_flags: tuple[str, ...] = ()
    completeness_warnings: tuple[str, ...] = ()
    in_conflict_group: bool = False


@dataclass(frozen=True)
class DimensionScores:
    """Orthogonal quality dimensions (canonical QualityAssessment fields)."""

    authenticity: float
    source_quality: float
    relevance: float
    freshness: float
    applicability: float
    independence: float
    extraction_reliability: float
    freshness_status: str


@dataclass(frozen=True)
class GateDecision:
    """Gate output for one candidate."""

    candidate_key: str
    verdict: EvidenceVerdict
    dimensions: DimensionScores
    independent_source_group_id: UUID
    independent_source_count: int
    reason_codes: tuple[str, ...]
    remediation_actions: tuple[str, ...]
    applicability_limits: tuple[str, ...]
    triggers_next_retrieval: bool

    @property
    def enters_worker_evidence_set(self) -> bool:
        return self.verdict in (EvidenceVerdict.ACCEPTED, EvidenceVerdict.CONDITIONAL)


@dataclass(frozen=True)
class GateResult:
    """Gate output for one batch evaluated together (one claim context)."""

    decisions: dict[str, GateDecision] = field(default_factory=dict)
    grouping: IndependentSourceGrouping = field(
        default_factory=IndependentSourceGrouping
    )

    @property
    def independent_source_count(self) -> int:
        return self.grouping.independent_source_count

    @property
    def verdict(self) -> EvidenceVerdict:
        """Most permissive verdict the batch can jointly support."""

        order = [
            EvidenceVerdict.ACCEPTED,
            EvidenceVerdict.CONDITIONAL,
            EvidenceVerdict.LEAD_ONLY,
            EvidenceVerdict.REJECTED,
        ]
        best = EvidenceVerdict.REJECTED
        for decision in self.decisions.values():
            if order.index(decision.verdict) < order.index(best):
                best = decision.verdict
        return best


def _freshness(published_at: datetime | None, retrieved_at: datetime | None) -> tuple[float, str]:
    if published_at is None:
        return 0.5, "unknown"
    anchor = retrieved_at or datetime.now(timezone.utc)
    age = anchor - published_at
    if age <= timedelta(days=_FRESH_DAYS):
        return 1.0, "fresh"
    if age <= timedelta(days=_AGING_DAYS):
        return 0.6, "aging"
    return 0.2, "stale"


def _independence(group_size: int, independent_count: int) -> float:
    """Score independence: alone in a group and corroborated by other groups."""

    within = 1.0 if group_size == 1 else 1.0 / group_size
    across = min(independent_count, _CORE_MIN_INDEPENDENT_SOURCES) / (
        _CORE_MIN_INDEPENDENT_SOURCES
    )
    return round(within * 0.5 + across * 0.5, 4)


class InformationQualityGate:
    """Deterministic blocking gate over one batch of evidence candidates."""

    def evaluate(self, candidates: list[EvidenceCandidate]) -> GateResult:
        grouping = group_independent_sources([c.identity for c in candidates])
        independent_count = grouping.independent_source_count
        decisions: dict[str, GateDecision] = {}
        for candidate in candidates:
            group = grouping.group_by_candidate[candidate.candidate_key]
            group_size = len(grouping.members_by_group[group])
            decisions[candidate.candidate_key] = self._decide(
                candidate,
                group_id=group,
                group_size=group_size,
                independent_count=independent_count,
            )
        return GateResult(decisions=decisions, grouping=grouping)

    def _decide(
        self,
        candidate: EvidenceCandidate,
        *,
        group_id: UUID,
        group_size: int,
        independent_count: int,
    ) -> GateDecision:
        if candidate.source_grade not in SOURCE_GRADE_QUALITY:
            raise ValueError(f"unknown source grade: {candidate.source_grade!r}")

        freshness_score, freshness_status = _freshness(
            candidate.published_at, candidate.retrieved_at
        )
        dimensions = DimensionScores(
            authenticity=candidate.authenticity,
            source_quality=SOURCE_GRADE_QUALITY[candidate.source_grade],
            relevance=candidate.relevance,
            freshness=freshness_score,
            applicability=candidate.applicability,
            independence=_independence(group_size, independent_count),
            extraction_reliability=candidate.extraction_reliability,
            freshness_status=freshness_status,
        )

        reasons: list[str] = []
        limits: list[str] = []

        # 1) Hard rejection floors.
        if candidate.authenticity < _REJECT_AUTHENTICITY:
            reasons.append("authenticity_below_floor")
        if candidate.extraction_reliability < _REJECT_EXTRACTION:
            reasons.append("extraction_unreliable")
        if candidate.relevance < _REJECT_RELEVANCE:
            reasons.append("irrelevant_to_scope")
        if reasons:
            return self._decision(
                candidate, EvidenceVerdict.REJECTED, dimensions, group_id,
                independent_count, reasons, limits,
            )

        # 2) Unverifiable material can never support a core claim: lead only.
        if candidate.supports_core_claim and (
            not candidate.verifiable
            or candidate.source_grade == "L6_unverified"
            or candidate.authenticity < _LEAD_ONLY_AUTHENTICITY
        ):
            reasons.append("unverifiable_source")
            return self._decision(
                candidate, EvidenceVerdict.LEAD_ONLY, dimensions, group_id,
                independent_count, reasons, limits,
            )

        # 3) Conditional triggers (each adds a mandatory applicability limit).
        if candidate.supports_core_claim and (
            independent_count < _CORE_MIN_INDEPENDENT_SOURCES
        ):
            reasons.append(
                "same_source_citations_collapsed"
                if group_size > 1
                else "single_independent_source"
            )
            limits.append(
                "Only one independent root source supports this claim; treat the "
                "finding as unconfirmed until corroborated."
            )
        if freshness_status == "stale":
            reasons.append("stale_evidence")
            limits.append("Evidence is stale; validity beyond its period is unproven.")
        if candidate.bias_flags:
            reasons.append("bias_flagged")
            limits.append(
                "Source carries declared bias flags: " + ", ".join(candidate.bias_flags)
            )
        if candidate.completeness_warnings:
            reasons.append("completeness_warning")
            limits.append(
                "Extraction is incomplete; conclusions from missing sections are unsupported."
            )
        if candidate.in_conflict_group:
            reasons.append("conflicting_evidence_present")
            limits.append("Conflicting evidence exists; scope the claim to where it holds.")

        below_acceptance = [
            name
            for name, value in (
                ("authenticity", dimensions.authenticity),
                ("relevance", dimensions.relevance),
                ("applicability", dimensions.applicability),
                ("extraction_reliability", dimensions.extraction_reliability),
            )
            if value < _ACCEPT_MIN_DIMENSION
        ]
        if below_acceptance:
            reasons.append("dimension_below_acceptance")
            limits.append(
                "Quality dimensions below acceptance threshold: "
                + ", ".join(below_acceptance)
            )

        if reasons:
            # No auto-accept for L1 either: reaching here with reasons means
            # conditional, whatever the category says.
            if candidate.source_grade == "L1_primary" and (
                independent_count < _CORE_MIN_INDEPENDENT_SOURCES
            ):
                reasons.append("l1_requires_corroboration")
            return self._decision(
                candidate, EvidenceVerdict.CONDITIONAL, dimensions, group_id,
                independent_count, reasons, limits,
            )

        return self._decision(
            candidate, EvidenceVerdict.ACCEPTED, dimensions, group_id,
            independent_count, reasons, limits,
        )

    def _decision(
        self,
        candidate: EvidenceCandidate,
        verdict: EvidenceVerdict,
        dimensions: DimensionScores,
        group_id: UUID,
        independent_count: int,
        reasons: list[str],
        limits: list[str],
    ) -> GateDecision:
        if verdict == EvidenceVerdict.CONDITIONAL and not limits:
            raise AssertionError("conditional verdicts must carry applicability limits")
        return GateDecision(
            candidate_key=candidate.candidate_key,
            verdict=verdict,
            dimensions=dimensions,
            independent_source_group_id=group_id,
            independent_source_count=independent_count,
            reason_codes=tuple(reasons),
            remediation_actions=tuple(
                REMEDIATIONS[code] for code in reasons if code in REMEDIATIONS
            ),
            applicability_limits=tuple(limits),
            triggers_next_retrieval=verdict == EvidenceVerdict.LEAD_ONLY,
        )
