"""Devil's-advocate challenges and the adversarial feedback arc (Task 10 Step 4).

Canonical shape: 06-data-model.md ``Challenge``. Behavioral law (18-plan Task
10 Step 4): every IMPORTANT finding raised by the Critic/Safety Anchor MUST
produce exactly one of the three dispositions — ``accepted_change``,
``rejected_with_reason`` or ``escalated`` — a finding can never be silently
absorbed. A fatal defect sends the run back to synthesis (it is NOT a
disposition; the arc re-runs after synthesis regenerates), and at least two
important non-fatal findings are expected to visibly change the report body,
its conditions, or the corresponding quality status.

Enum discipline: challenge category/severity/status and the disposition set
persist as CHECK-constrained strings (SIM-02A precedent, same as Task 9's
event/packet literal sets).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Sequence
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Enum as SAEnum,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import (
    created_at_column,
    json_list_column,
    uuid_primary_key,
    workspace_column,
)

# --- canonical literal sets (06-data-model.md); CHECK-enforced strings -------
CHALLENGE_CATEGORIES: Final[tuple[str, ...]] = (
    "core_assumption",
    "counterargument",
    "failure_pattern",
    "stakeholder_resistance",
    "bias",
    "fatal_flaw",
    "blind_spot",
)
CHALLENGE_SEVERITIES: Final[tuple[str, ...]] = ("low", "medium", "high", "critical")
# GeneratedContentStatus (06 shared literal): draft | confirmed | rejected.
# PG enum, no parallel Python StrEnum (Task 9 packet-role precedent): the
# decision-os invariants suite requires status columns to be enums.
CHALLENGE_STATUSES: Final[tuple[str, ...]] = ("draft", "confirmed", "rejected")
GENERATED_CONTENT_STATUS_ENUM = SAEnum(
    *CHALLENGE_STATUSES,
    name="generated_content_status",
    native_enum=True,
)

# The closed disposition set of the adversarial feedback arc (18 Task 10 Step 4).
CHALLENGE_DISPOSITIONS: Final[tuple[str, ...]] = (
    "accepted_change",
    "rejected_with_reason",
    "escalated",
)

# Severities whose findings are "important": they enter the mandatory arc.
IMPORTANT_SEVERITIES: Final[frozenset[str]] = frozenset({"high", "critical"})


def _check_in(column: str, values: Sequence[str]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


class Challenge(Base):
    """One adversarial finding with its mandatory disposition trail."""

    __tablename__ = "challenges"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_challenges_workspace_id"),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_challenges_workspace_case",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "analysis_run_id"],
            [
                "analysis_runs.workspace_id",
                "analysis_runs.decision_case_id",
                "analysis_runs.analysis_run_id",
            ],
            name="fk_challenges_workspace_case_run",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            _check_in("category", CHALLENGE_CATEGORIES), name="challenge_category_valid"
        ),
        CheckConstraint(
            _check_in("severity", CHALLENGE_SEVERITIES), name="challenge_severity_valid"
        ),
        CheckConstraint(
            "disposition IS NULL OR "
            + _check_in("disposition", CHALLENGE_DISPOSITIONS),
            name="challenge_disposition_valid",
        ),
        # A rejection is only legal WITH a reason (the arc never swallows).
        CheckConstraint(
            "disposition <> 'rejected_with_reason' OR disposition_reason <> ''",
            name="challenge_rejection_requires_reason",
        ),
        # Important findings must not be confirmed without a disposition.
        CheckConstraint(
            "status <> 'confirmed' OR severity IN ('low', 'medium') "
            "OR disposition IS NOT NULL",
            name="challenge_important_confirmed_requires_disposition",
        ),
        Index("ix_challenges_workspace_run", "workspace_id", "analysis_run_id"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    affected_option_ids: Mapped[list[str]] = json_list_column()
    evidence_ids: Mapped[list[str]] = json_list_column()
    mitigation: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        GENERATED_CONTENT_STATUS_ENUM, nullable=False, default="draft", server_default="draft"
    )
    # Adversarial arc trail (Step 4): disposition + reason + what it changed.
    disposition: Mapped[str | None] = mapped_column(String(32))
    disposition_reason: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    resulting_change: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_column()


# --- the pure arc evaluation consumed by the quality gate --------------------


class AdversarialArcViolation(Exception):
    """An important finding escaped the mandatory disposition arc."""

    def __init__(self, reason_codes: Sequence[str], findings: Sequence[str]) -> None:
        super().__init__("; ".join(findings) or "adversarial arc violated")
        self.reason_codes = tuple(reason_codes)
        self.findings = tuple(findings)


@dataclass(frozen=True, slots=True)
class ChallengeFinding:
    """In-memory view of one Challenge row for the pure arc computation."""

    challenge_id: str
    category: str
    severity: str
    disposition: str | None
    disposition_reason: str = ""
    changed_report: bool = False  # accepted_change visibly altered body/conditions


@dataclass(frozen=True, slots=True)
class AdversarialArcResult:
    """Outcome of evaluating the feedback arc over one run's findings.

    ``return_to_synthesis`` is raised by an undispositioned fatal defect —
    the run must go back to the synthesis stage, nothing downstream may run.
    """

    important_total: int
    accepted_changes: int
    rejected_with_reason: int
    escalated: int
    return_to_synthesis: bool
    reason_codes: tuple[str, ...]
    findings: tuple[str, ...]

    @property
    def arc_complete(self) -> bool:
        return not self.reason_codes and not self.return_to_synthesis


def evaluate_adversarial_arc(
    findings: Sequence[ChallengeFinding],
) -> AdversarialArcResult:
    """Check every important finding produced a disposition (Step 4).

    * missing disposition on an important finding -> arc incomplete;
    * ``rejected_with_reason`` without a reason -> arc incomplete;
    * a fatal defect (critical ``fatal_flaw``) that was not resolved by an
      accepted change -> the run returns to synthesis;
    * fewer than two important non-fatal findings visibly changing the
      report -> warning-grade reason code (the gate scores it, 18 Task 10
      Step 4 "至少两条重要非致命发现改变正文、条件或相应质量状态").
    """

    reason_codes: list[str] = []
    notes: list[str] = []
    important = [item for item in findings if item.severity in IMPORTANT_SEVERITIES]
    accepted = rejected = escalated = 0
    changed_by_nonfatal = 0
    return_to_synthesis = False

    for item in important:
        is_fatal = item.category == "fatal_flaw" and item.severity == "critical"
        if item.disposition is None:
            if is_fatal:
                return_to_synthesis = True
                notes.append(
                    f"fatal defect {item.challenge_id} undispositioned: back to synthesis"
                )
            else:
                reason_codes.append("challenge_without_disposition")
                notes.append(f"important finding {item.challenge_id} has no disposition")
            continue
        if item.disposition not in CHALLENGE_DISPOSITIONS:
            reason_codes.append("challenge_disposition_unknown")
            notes.append(
                f"finding {item.challenge_id} carries unknown disposition {item.disposition!r}"
            )
            continue
        if item.disposition == "accepted_change":
            accepted += 1
            if not is_fatal and item.changed_report:
                changed_by_nonfatal += 1
        elif item.disposition == "rejected_with_reason":
            if not item.disposition_reason.strip():
                reason_codes.append("challenge_rejection_without_reason")
                notes.append(f"finding {item.challenge_id} rejected without a reason")
                continue
            rejected += 1
        else:
            escalated += 1
        if is_fatal and item.disposition != "accepted_change":
            # A fatal flaw can only leave the arc through a change that
            # resolves it; rejecting or escalating does not neutralize it.
            return_to_synthesis = True
            notes.append(
                f"fatal defect {item.challenge_id} not resolved by accepted_change: "
                "back to synthesis"
            )

    if important and changed_by_nonfatal < 2:
        # Warning-grade: scores down adversarial pressure without blocking.
        reason_codes.append("adversarial_low_report_impact")
        notes.append(
            "fewer than two important non-fatal findings changed the report "
            f"({changed_by_nonfatal} did)"
        )

    return AdversarialArcResult(
        important_total=len(important),
        accepted_changes=accepted,
        rejected_with_reason=rejected,
        escalated=escalated,
        return_to_synthesis=return_to_synthesis,
        reason_codes=tuple(dict.fromkeys(reason_codes)),
        findings=tuple(notes),
    )
