"""Claims and claim-evidence links (Task 10 Step 2-3, case_api_data scope).

Canonical shapes: 06-data-model.md (``Claim``, ``ClaimEvidence``). Two rules
are behavioral law here, not style:

* supporting and opposing evidence are computed **separately** — support is
  never a majority vote over source row counts (04-decision-methodology
  命题支撑 row: "支持证据与反对证据分开记录，不按来源条数多数投票");
* fact reconciliation compares numbers only on the same metric and time
  window, and classifies divergence into exactly four canonical categories
  (18-plan Task 10 Step 3): factual conflict, definition (口径) mismatch,
  freshness gap, and source divergence. Conflicts the pipeline cannot
  adjudicate are written into the report payload and *downgrade* the claim
  status — they are never silently dropped.

Enum discipline follows the Task 8/9 precedent: ``entry_status`` and
``evidence_verdict`` PG enums are reused (never recreated); canonical literal
sets without an ``app.types`` PG enum (statement type, importance, source,
link direction) persist as CHECK-constrained strings (SIM-02A precedent).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Sequence
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import (
    created_at_column,
    enum_type,
    json_list_column,
    json_object_column,
    updated_at_column,
    uuid_primary_key,
    workspace_column,
)
from app.types import EntryStatus, EvidenceVerdict, StatementType

# --- canonical literal sets (06-data-model.md); CHECK-enforced strings -------
CLAIM_IMPORTANCE: Final[tuple[str, ...]] = ("core", "supporting")
CLAIM_SOURCES: Final[tuple[str, ...]] = ("user", "ai", "tool", "imported")
CLAIM_EVIDENCE_DIRECTIONS: Final[tuple[str, ...]] = ("supporting", "opposing")

# Verdicts that make a supporting link *count* toward claim support. A
# ``lead_only`` or ``rejected`` link is kept for audit but never supports.
_SUPPORT_BEARING_VERDICTS: Final[frozenset[EvidenceVerdict]] = frozenset(
    {EvidenceVerdict.ACCEPTED, EvidenceVerdict.CONDITIONAL}
)


def _check_in(column: str, values: Sequence[str]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


class Claim(Base):
    """One analysis proposition with strictly canonical 06 fields."""

    __tablename__ = "claims"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_claims_workspace_id"),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_claims_workspace_case",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "analysis_run_id"],
            [
                "analysis_runs.workspace_id",
                "analysis_runs.decision_case_id",
                "analysis_runs.analysis_run_id",
            ],
            name="fk_claims_workspace_case_run",
            ondelete="CASCADE",
        ),
        CheckConstraint(_check_in("importance", CLAIM_IMPORTANCE), name="claim_importance_valid"),
        CheckConstraint(_check_in("source", CLAIM_SOURCES), name="claim_source_valid"),
        CheckConstraint(
            "support_score >= 0 AND support_score <= 1", name="claim_support_score_range"
        ),
        Index("ix_claims_workspace_run", "workspace_id", "analysis_run_id"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    analysis_run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    statement_type: Mapped[StatementType] = mapped_column(
        enum_type(StatementType, "statement_type"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    # ResponsibilityStamp is a closed 06 object; stored as-is.
    responsibility: Mapped[dict[str, Any]] = json_object_column()
    source_span_ids: Mapped[list[str]] = json_list_column()
    supporting_evidence_ids: Mapped[list[str]] = json_list_column()
    opposing_evidence_ids: Mapped[list[str]] = json_list_column()
    assumption_ids: Mapped[list[str]] = json_list_column()
    support_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    scope: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[EntryStatus] = mapped_column(
        enum_type(EntryStatus, "entry_status"),
        nullable=False,
        default=EntryStatus.CANDIDATE,
        server_default=EntryStatus.CANDIDATE.value,
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class ClaimEvidence(Base):
    """Directional claim<->evidence link with strength, rationale, verdict."""

    __tablename__ = "claim_evidence"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_claim_evidence_workspace_id"),
        UniqueConstraint(
            "workspace_id",
            "claim_id",
            "evidence_id",
            "direction",
            name="uq_claim_evidence_workspace_link",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "claim_id"],
            ["claims.workspace_id", "claims.id"],
            name="fk_claim_evidence_workspace_claim",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "evidence_id"],
            ["evidence_items.workspace_id", "evidence_items.id"],
            name="fk_claim_evidence_workspace_evidence",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            _check_in("direction", CLAIM_EVIDENCE_DIRECTIONS),
            name="claim_evidence_direction_valid",
        ),
        CheckConstraint(
            "support_strength >= 0 AND support_strength <= 1",
            name="claim_evidence_strength_range",
        ),
        Index("ix_claim_evidence_workspace_claim", "workspace_id", "claim_id"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    claim_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    evidence_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    support_strength: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    verdict: Mapped[EvidenceVerdict] = mapped_column(
        enum_type(EvidenceVerdict, "evidence_verdict"), nullable=False
    )
    created_at: Mapped[datetime] = created_at_column()


# --- support computation (Step 2): separate sides, never a majority vote ----


@dataclass(frozen=True, slots=True)
class EvidenceLink:
    """In-memory view of one ClaimEvidence row used by the pure computation."""

    evidence_id: str
    direction: str
    support_strength: float
    verdict: EvidenceVerdict
    rationale: str = ""


@dataclass(frozen=True, slots=True)
class ClaimSupportAssessment:
    """Separated support/opposition computation for one claim.

    ``claim_support`` uses the canonical four-value RecommendationQuality
    projection: supported / conflicted / assumption_only / unsupported.
    """

    claim_id: str
    support_score: float
    opposition_score: float
    supporting_evidence_ids: tuple[str, ...]
    opposing_evidence_ids: tuple[str, ...]
    claim_support: str
    reason_codes: tuple[str, ...] = ()


def _side_score(links: Sequence[EvidenceLink]) -> float:
    """Aggregate one side without vote counting.

    The side score is the strongest single support-bearing link, softly lifted
    by independent corroboration — NOT ``len(links)`` and NOT an average, so
    ten weak L5 opinions can never outvote one strong opposing L1 primary.
    """

    bearing = [
        link
        for link in links
        if link.verdict in _SUPPORT_BEARING_VERDICTS and link.support_strength > 0
    ]
    if not bearing:
        return 0.0
    strengths = sorted((link.support_strength for link in bearing), reverse=True)
    score = strengths[0]
    for extra in strengths[1:]:
        # each additional independent link closes at most half the remaining
        # gap, weighted by its own strength — corroboration, not vote count
        score += (1.0 - score) * 0.5 * extra
    return min(score, 1.0)


def assess_claim_support(
    claim_id: str,
    links: Sequence[EvidenceLink],
    *,
    has_assumptions: bool = False,
) -> ClaimSupportAssessment:
    """Compute both sides separately and project the canonical support state."""

    supporting = [link for link in links if link.direction == "supporting"]
    opposing = [link for link in links if link.direction == "opposing"]
    support_score = _side_score(supporting)
    opposition_score = _side_score(opposing)

    reason_codes: list[str] = []
    if support_score > 0 and opposition_score > 0:
        claim_support = "conflicted"
        reason_codes.append("claim_conflicting_evidence")
    elif support_score > 0:
        claim_support = "supported"
    elif has_assumptions:
        claim_support = "assumption_only"
        reason_codes.append("claim_assumption_only")
    else:
        claim_support = "unsupported"
        reason_codes.append("claim_unsupported")

    return ClaimSupportAssessment(
        claim_id=claim_id,
        support_score=support_score,
        opposition_score=opposition_score,
        supporting_evidence_ids=tuple(
            link.evidence_id for link in supporting if link.verdict in _SUPPORT_BEARING_VERDICTS
        ),
        opposing_evidence_ids=tuple(
            link.evidence_id for link in opposing if link.verdict in _SUPPORT_BEARING_VERDICTS
        ),
        claim_support=claim_support,
        reason_codes=tuple(reason_codes),
    )


# --- fact reconciliation (Step 3): four canonical divergence categories -----

RECONCILIATION_CATEGORIES: Final[tuple[str, ...]] = (
    "factual_conflict",  # 事实冲突: same metric/period/definition, incompatible numbers
    "definition_mismatch",  # 口径差异: same metric name, different measurement definition
    "freshness_gap",  # 时效差异: same metric/definition, different periods
    "source_divergence",  # 来源差异: values compatible within tolerance, sources differ
)


@dataclass(frozen=True, slots=True)
class FactObservation:
    """One numeric observation extracted from an evidence item."""

    evidence_id: str
    metric: str
    value: float
    unit: str
    period: str
    definition: str
    source_domain: str
    claim_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReconciliationFinding:
    """One classified divergence between two observations of the same metric."""

    metric: str
    category: str
    evidence_ids: tuple[str, ...]
    detail: str
    resolvable: bool
    affected_claim_ids: tuple[str, ...] = ()

    def report_entry(self) -> dict[str, Any]:
        """Serialize for the report payload (unresolved conflicts must ship)."""

        return {
            "metric": self.metric,
            "category": self.category,
            "evidenceIds": list(self.evidence_ids),
            "detail": self.detail,
            "resolvable": self.resolvable,
            "affectedClaimIds": list(self.affected_claim_ids),
        }


@dataclass(frozen=True, slots=True)
class ReconciliationOutcome:
    findings: tuple[ReconciliationFinding, ...]
    downgraded_claim_ids: tuple[str, ...]

    @property
    def unresolved(self) -> tuple[ReconciliationFinding, ...]:
        return tuple(finding for finding in self.findings if not finding.resolvable)


# Relative numeric tolerance under which two observations merely diverge by
# source, not by fact. Operational parameter (IMPLEMENTATION_FREE).
_SOURCE_TOLERANCE: Final[float] = 0.05


def _classify_pair(a: FactObservation, b: FactObservation) -> ReconciliationFinding | None:
    if a.metric != b.metric or a.unit != b.unit:
        return None  # not comparable at all; never "reconciled" implicitly
    pair_ids = (a.evidence_id, b.evidence_id)
    claim_ids = tuple(dict.fromkeys(a.claim_ids + b.claim_ids))
    if a.definition != b.definition:
        return ReconciliationFinding(
            metric=a.metric,
            category="definition_mismatch",
            evidence_ids=pair_ids,
            detail=f"definitions differ: {a.definition!r} vs {b.definition!r}",
            resolvable=True,
            affected_claim_ids=claim_ids,
        )
    if a.period != b.period:
        return ReconciliationFinding(
            metric=a.metric,
            category="freshness_gap",
            evidence_ids=pair_ids,
            detail=f"periods differ: {a.period!r} vs {b.period!r}",
            resolvable=True,
            affected_claim_ids=claim_ids,
        )
    baseline = max(abs(a.value), abs(b.value), 1e-9)
    relative_gap = abs(a.value - b.value) / baseline
    if relative_gap <= _SOURCE_TOLERANCE:
        if a.source_domain == b.source_domain:
            return None  # same source repeating itself is not a divergence
        return ReconciliationFinding(
            metric=a.metric,
            category="source_divergence",
            evidence_ids=pair_ids,
            detail=(
                f"values agree within tolerance ({a.value} vs {b.value}) "
                f"across sources {a.source_domain!r} / {b.source_domain!r}"
            ),
            resolvable=True,
            affected_claim_ids=claim_ids,
        )
    # Same metric, same definition, same period, incompatible numbers:
    # a genuine factual conflict the pipeline cannot adjudicate on its own.
    return ReconciliationFinding(
        metric=a.metric,
        category="factual_conflict",
        evidence_ids=pair_ids,
        detail=f"incompatible values for {a.period!r}: {a.value} vs {b.value}",
        resolvable=False,
        affected_claim_ids=claim_ids,
    )


def reconcile_facts(observations: Sequence[FactObservation]) -> ReconciliationOutcome:
    """Pairwise-compare observations per metric and classify divergences.

    Unresolvable conflicts (``factual_conflict``) are returned for the report
    AND name the claims that must be downgraded to ``conflicted`` — the caller
    persists both effects in the same transaction.
    """

    findings: list[ReconciliationFinding] = []
    downgraded: dict[str, None] = {}
    by_metric: dict[str, list[FactObservation]] = {}
    for observation in observations:
        by_metric.setdefault(f"{observation.metric}|{observation.unit}", []).append(observation)
    for group in by_metric.values():
        for index, left in enumerate(group):
            for right in group[index + 1 :]:
                finding = _classify_pair(left, right)
                if finding is None:
                    continue
                findings.append(finding)
                if not finding.resolvable:
                    for claim_id in finding.affected_claim_ids:
                        downgraded[claim_id] = None
    return ReconciliationOutcome(
        findings=tuple(findings), downgraded_claim_ids=tuple(downgraded)
    )
