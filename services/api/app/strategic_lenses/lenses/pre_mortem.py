"""Pre-Mortem strategic lens runtime behavior validation.

This module owns the Critic-produced ``pre_mortem`` branch of the compiled
``strategic-lens-output`` union. It enforces the behavior gates that the JSON
Schema alone cannot express:

- exactly the three canonical failure-observation perspectives, each actually
  used by at least one failure cause;
- at least five substantive failure causes with cause/evidence/assumption
  discipline (label-only causes are rejected);
- ordinal risk arithmetic (``riskScore == likelihoodScore * impactScore``;
  scores are prioritization ordinals, never probabilities);
- exactly three top risks with unique ranks and unique, resolvable cause
  references, each carrying distinct prevention/contingency controls plus an
  observable detection indicator, and drawn from the highest-ranked causes;
- a fatal, unpreventable cause can never be averaged away into ``continue``;
- ``validate_first`` verdicts must state the missing validation information,
  which keeps the lens compatible with a downstream system abstain.

The module never resolves references against the database and never injects
identity/provenance fields; the shared harness owns persistence. Findings are
returned as structured blockers so Validation can consume them verbatim.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from app.types import StrategicLensType

PRE_MORTEM_LENS_TYPE = StrategicLensType.PRE_MORTEM.value
REQUIRED_PHASE = "adversarial_stress"
REQUIRED_PERSPECTIVES = frozenset({"internal", "external", "systemic_hindsight"})
MIN_FAILURE_CAUSES = 5
TOP_RISK_COUNT = 3
ALLOWED_VERDICTS = frozenset({"continue", "modify", "abandon", "validate_first"})
# Ordinal ceiling for a fatal cause; paired with uncontrollable it must not be
# silently outvoted by lower-risk averages (prompt rule 6).
FATAL_IMPACT_SCORE = 5
# Causes that are only generic risk labels carry no analyzable content. The
# prompt forbids them explicitly; keep the deny list small and literal.
LABEL_ONLY_CAUSES = frozenset(
    {
        "市场风险",
        "执行风险",
        "技术风险",
        "财务风险",
        "market risk",
        "execution risk",
        "technology risk",
        "financial risk",
    }
)


@dataclass(frozen=True)
class PreMortemFinding:
    """One structured behavior finding for Validation consumption."""

    code: str
    severity: str  # "blocker" | "warning"
    message: str
    path: str


@dataclass(frozen=True)
class PreMortemBehaviorResult:
    """Deterministic outcome of the Pre-Mortem behavior gate."""

    passed: bool
    findings: tuple[PreMortemFinding, ...] = field(default_factory=tuple)

    @property
    def blockers(self) -> tuple[PreMortemFinding, ...]:
        return tuple(f for f in self.findings if f.severity == "blocker")

    @property
    def warnings(self) -> tuple[PreMortemFinding, ...]:
        return tuple(f for f in self.findings if f.severity == "warning")


class _FindingCollector:
    def __init__(self) -> None:
        self._findings: list[PreMortemFinding] = []

    def blocker(self, code: str, message: str, path: str) -> None:
        self._findings.append(PreMortemFinding(code, "blocker", message, path))

    def warning(self, code: str, message: str, path: str) -> None:
        self._findings.append(PreMortemFinding(code, "warning", message, path))

    def result(self) -> PreMortemBehaviorResult:
        findings = tuple(self._findings)
        passed = not any(f.severity == "blocker" for f in findings)
        return PreMortemBehaviorResult(passed=passed, findings=findings)


def _as_mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _is_probability_like(value: Any) -> bool:
    return isinstance(value, float) and not value.is_integer()


def _check_envelope(output: Mapping[str, Any], findings: _FindingCollector) -> None:
    if output.get("lensType") != PRE_MORTEM_LENS_TYPE:
        findings.blocker(
            "PM_LENS_TYPE",
            f"lensType must be {PRE_MORTEM_LENS_TYPE!r}, got {output.get('lensType')!r}",
            "lensType",
        )
    if output.get("phase") != REQUIRED_PHASE:
        findings.blocker(
            "PM_PHASE",
            f"phase must be {REQUIRED_PHASE!r}, got {output.get('phase')!r}",
            "phase",
        )
    forbidden_identity = (
        "id",
        "artifactId",
        "workspaceId",
        "decisionCaseId",
        "analysisRunId",
        "charterId",
        "status",
        "contentHash",
        "createdAt",
        "producerRole",
    )
    for key in forbidden_identity:
        if key in output:
            findings.blocker(
                "PM_MODEL_SELF_REPORTED_IDENTITY",
                f"model output must not self-report server-owned field {key!r}",
                key,
            )


def _check_references(
    output: Mapping[str, Any],
    findings: _FindingCollector,
    known_evidence_ids: frozenset[str] | None,
    known_assumption_ids: frozenset[str] | None,
) -> None:
    references = _as_mapping(output.get("references"))
    if references is None:
        findings.blocker("PM_REFERENCES", "references block is missing", "references")
        return
    evidence_ids = [v for v in _as_list(references.get("evidenceIds")) if isinstance(v, str)]
    assumption_ids = [v for v in _as_list(references.get("assumptionIds")) if isinstance(v, str)]
    overlap = sorted(set(evidence_ids) & set(assumption_ids))
    if overlap:
        findings.blocker(
            "PM_EVIDENCE_ASSUMPTION_OVERLAP",
            f"the same ID cannot be cited as both evidence and assumption: {overlap}",
            "references",
        )
    if not evidence_ids and not assumption_ids:
        findings.blocker(
            "PM_UNGROUNDED",
            "pre-mortem must cite at least one Evidence ID or Assumption ID",
            "references",
        )
    if known_evidence_ids is not None:
        unknown = sorted(set(evidence_ids) - known_evidence_ids)
        if unknown:
            findings.blocker(
                "PM_UNKNOWN_EVIDENCE_ID",
                f"evidence IDs not present in the frozen Run ledger: {unknown}",
                "references.evidenceIds",
            )
    if known_assumption_ids is not None:
        unknown = sorted(set(assumption_ids) - known_assumption_ids)
        if unknown:
            findings.blocker(
                "PM_UNKNOWN_ASSUMPTION_ID",
                f"assumption IDs not present in the frozen Run ledger: {unknown}",
                "references.assumptionIds",
            )


def _check_failure_framing(content: Mapping[str, Any], findings: _FindingCollector) -> None:
    horizon = content.get("failureHorizon")
    statement = content.get("failureStatement")
    if not isinstance(horizon, str) or not horizon.strip():
        findings.blocker("PM_HORIZON", "failureHorizon must state an explicit future point", "content.failureHorizon")
    if not isinstance(statement, str) or not statement.strip():
        findings.blocker(
            "PM_FAILURE_STATEMENT",
            "failureStatement must assert the failure as already final",
            "content.failureStatement",
        )
    perspectives = _as_list(content.get("perspectives"))
    if set(perspectives) != REQUIRED_PERSPECTIVES or len(perspectives) != len(REQUIRED_PERSPECTIVES):
        findings.blocker(
            "PM_PERSPECTIVE_SET",
            "perspectives must be exactly internal, external, systemic_hindsight",
            "content.perspectives",
        )


def _check_failure_causes(
    content: Mapping[str, Any], findings: _FindingCollector
) -> dict[str, Mapping[str, Any]]:
    causes = _as_list(content.get("failureCauses"))
    if len(causes) < MIN_FAILURE_CAUSES:
        findings.blocker(
            "PM_CAUSE_COUNT",
            f"at least {MIN_FAILURE_CAUSES} failure causes required, got {len(causes)}",
            "content.failureCauses",
        )
    causes_by_id: dict[str, Mapping[str, Any]] = {}
    used_perspectives: set[str] = set()
    for index, item in enumerate(causes):
        cause = _as_mapping(item)
        path = f"content.failureCauses[{index}]"
        if cause is None:
            findings.blocker("PM_CAUSE_SHAPE", "failure cause must be an object", path)
            continue
        cause_id = cause.get("causeId")
        if not isinstance(cause_id, str) or not cause_id:
            findings.blocker("PM_CAUSE_ID", "causeId must be a non-empty string", path)
        elif cause_id in causes_by_id:
            findings.blocker("PM_CAUSE_ID_DUPLICATE", f"duplicate causeId {cause_id!r}", path)
        else:
            causes_by_id[cause_id] = cause
        perspective = cause.get("perspective")
        if perspective in REQUIRED_PERSPECTIVES:
            used_perspectives.add(perspective)
        cause_text = cause.get("cause")
        if isinstance(cause_text, str) and cause_text.strip().lower() in LABEL_ONLY_CAUSES:
            findings.blocker(
                "PM_LABEL_ONLY_CAUSE",
                f"cause is a generic risk label, not an analyzable failure cause: {cause_text!r}",
                f"{path}.cause",
            )
        consequences = _as_list(cause.get("downstreamConsequences"))
        if not consequences:
            findings.blocker(
                "PM_NO_DOWNSTREAM",
                "each cause must trace at least one downstream consequence",
                f"{path}.downstreamConsequences",
            )
        likelihood = cause.get("likelihoodScore")
        impact = cause.get("impactScore")
        risk = cause.get("riskScore")
        if _is_probability_like(likelihood) or _is_probability_like(impact):
            findings.blocker(
                "PM_PROBABILITY_SMUGGLING",
                "likelihood/impact are 1-5 ordinals, not probabilities",
                path,
            )
        if (
            isinstance(likelihood, int)
            and isinstance(impact, int)
            and isinstance(risk, int)
            and risk != likelihood * impact
        ):
            findings.blocker(
                "PM_RISK_ARITHMETIC",
                f"riskScore must equal likelihoodScore*impactScore ({likelihood}*{impact}), got {risk}",
                f"{path}.riskScore",
            )
    missing = REQUIRED_PERSPECTIVES - used_perspectives
    if missing:
        findings.blocker(
            "PM_PERSPECTIVE_COVERAGE",
            f"failure causes must cover all three perspectives; missing {sorted(missing)}",
            "content.failureCauses",
        )
    return causes_by_id


def _check_top_risks(
    content: Mapping[str, Any],
    causes_by_id: dict[str, Mapping[str, Any]],
    findings: _FindingCollector,
) -> None:
    top_risks = _as_list(content.get("topRisks"))
    if len(top_risks) != TOP_RISK_COUNT:
        findings.blocker(
            "PM_TOP_RISK_COUNT",
            f"exactly {TOP_RISK_COUNT} top risks required, got {len(top_risks)}",
            "content.topRisks",
        )
    seen_ranks: set[int] = set()
    seen_cause_ids: set[str] = set()
    for index, item in enumerate(top_risks):
        risk = _as_mapping(item)
        path = f"content.topRisks[{index}]"
        if risk is None:
            findings.blocker("PM_TOP_RISK_SHAPE", "top risk must be an object", path)
            continue
        rank = risk.get("rank")
        if not isinstance(rank, int) or rank not in (1, 2, 3):
            findings.blocker("PM_TOP_RISK_RANK", f"rank must be 1..3, got {rank!r}", f"{path}.rank")
        elif rank in seen_ranks:
            findings.blocker("PM_TOP_RISK_RANK_DUPLICATE", f"duplicate rank {rank}", f"{path}.rank")
        else:
            seen_ranks.add(rank)
        cause_id = risk.get("causeId")
        if not isinstance(cause_id, str) or cause_id not in causes_by_id:
            findings.blocker(
                "PM_TOP_RISK_CAUSE_REF",
                f"top risk must reference an existing causeId, got {cause_id!r}",
                f"{path}.causeId",
            )
        elif cause_id in seen_cause_ids:
            findings.blocker(
                "PM_TOP_RISK_CAUSE_DUPLICATE",
                f"top risks must reference distinct causes, duplicate {cause_id!r}",
                f"{path}.causeId",
            )
        else:
            seen_cause_ids.add(cause_id)
        prevention = risk.get("prevention")
        contingency = risk.get("contingency")
        detection = risk.get("detectionIndicator")
        for control_name, control in (
            ("prevention", prevention),
            ("contingency", contingency),
            ("detectionIndicator", detection),
        ):
            if not isinstance(control, str) or not control.strip():
                findings.blocker(
                    "PM_TOP_RISK_CONTROL_MISSING",
                    f"top risk {rank!r} is missing its {control_name} control",
                    f"{path}.{control_name}",
                )
        if (
            isinstance(prevention, str)
            and isinstance(contingency, str)
            and prevention.strip()
            and prevention.strip() == contingency.strip()
        ):
            findings.blocker(
                "PM_TOP_RISK_CONTROL_DUPLICATED",
                "prevention and contingency must be different actions",
                f"{path}.contingency",
            )

    # Top risks must actually be the highest-ranked causes. Ties at the
    # boundary are tolerated: every selected cause must score at least as high
    # as the third-highest riskScore among all causes.
    scored = sorted(
        (
            cause.get("riskScore")
            for cause in causes_by_id.values()
            if isinstance(cause.get("riskScore"), int)
        ),
        reverse=True,
    )
    if len(scored) >= TOP_RISK_COUNT and len(seen_cause_ids) == TOP_RISK_COUNT:
        threshold = scored[TOP_RISK_COUNT - 1]
        underranked = sorted(
            cause_id
            for cause_id in seen_cause_ids
            if isinstance(causes_by_id[cause_id].get("riskScore"), int)
            and causes_by_id[cause_id]["riskScore"] < threshold
        )
        if underranked:
            findings.blocker(
                "PM_TOP_RISK_NOT_HIGHEST",
                f"top risks must be drawn from the highest riskScore causes; underranked: {underranked}",
                "content.topRisks",
            )


def _check_verdict(
    content: Mapping[str, Any],
    causes_by_id: dict[str, Mapping[str, Any]],
    findings: _FindingCollector,
) -> None:
    verdict = content.get("verdict")
    rationale = content.get("verdictRationale")
    if verdict not in ALLOWED_VERDICTS:
        findings.blocker(
            "PM_VERDICT",
            f"verdict must be one of {sorted(ALLOWED_VERDICTS)}, got {verdict!r}",
            "content.verdict",
        )
    if not isinstance(rationale, str) or not rationale.strip():
        findings.blocker(
            "PM_VERDICT_RATIONALE",
            "verdict requires an explicit rationale",
            "content.verdictRationale",
        )
    additional = _as_list(content.get("additionalInformationNeeded"))
    if verdict == "validate_first" and not additional:
        findings.blocker(
            "PM_MISSING_EVIDENCE_LIST",
            "validate_first requires the missing validation information to be listed",
            "content.additionalInformationNeeded",
        )
    # Prompt rule 6: a fatal cause that cannot be prevented must not be
    # averaged away. "continue" with such a cause on the table is a blocker;
    # modify/abandon/validate_first remain available, so the gate stays
    # compatible with a downstream system abstain instead of forcing a pick.
    fatal_uncontrollable = sorted(
        cause_id
        for cause_id, cause in causes_by_id.items()
        if cause.get("impactScore") == FATAL_IMPACT_SCORE
        and cause.get("controllability") == "uncontrollable"
    )
    if verdict == "continue" and fatal_uncontrollable:
        findings.blocker(
            "PM_FATAL_CAUSE_AVERAGED_AWAY",
            "verdict 'continue' cannot stand while fatal uncontrollable causes exist: "
            f"{fatal_uncontrollable}",
            "content.verdict",
        )


def validate_pre_mortem_output(
    output: Mapping[str, Any],
    *,
    known_evidence_ids: frozenset[str] | None = None,
    known_assumption_ids: frozenset[str] | None = None,
) -> PreMortemBehaviorResult:
    """Run the Pre-Mortem behavior gate over one untrusted stage output.

    ``known_evidence_ids``/``known_assumption_ids`` are optional frozen-Run
    ledgers supplied by the shared harness; when omitted, only internal
    consistency is enforced and reference resolution stays with the harness.
    """

    findings = _FindingCollector()
    _check_envelope(output, findings)
    _check_references(output, findings, known_evidence_ids, known_assumption_ids)
    content = _as_mapping(output.get("content"))
    if content is None:
        findings.blocker("PM_CONTENT", "content block is missing", "content")
        return findings.result()
    _check_failure_framing(content, findings)
    causes_by_id = _check_failure_causes(content, findings)
    _check_top_risks(content, causes_by_id, findings)
    _check_verdict(content, causes_by_id, findings)
    return findings.result()


def _load_output(path: Path) -> Mapping[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError(f"stage output must be a JSON object: {path}")
    return document


def _report(label: str, result: PreMortemBehaviorResult) -> None:
    status = "PASS" if result.passed else "FAIL"
    print(f"{label}: {status}")
    for finding in result.findings:
        print(f"  [{finding.severity}] {finding.code} @ {finding.path}: {finding.message}")


def main(argv: list[str] | None = None) -> int:
    """Fixture self-check harness for this lens only (not a QA test)."""

    parser = argparse.ArgumentParser(description="Pre-Mortem lens behavior self-check")
    parser.add_argument("expected", type=Path, help="expected fixture that must PASS")
    parser.add_argument(
        "--negative",
        type=Path,
        default=None,
        help="negative fixture that must FAIL with at least one blocker",
    )
    args = parser.parse_args(argv)

    expected_result = validate_pre_mortem_output(_load_output(args.expected))
    _report(f"expected {args.expected.name}", expected_result)
    exit_code = 0 if expected_result.passed else 1

    if args.negative is not None:
        negative_result = validate_pre_mortem_output(_load_output(args.negative))
        _report(f"negative {args.negative.name}", negative_result)
        if negative_result.passed:
            print("  negative fixture unexpectedly passed the behavior gate")
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
