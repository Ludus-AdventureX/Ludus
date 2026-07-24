"""Porter Five Forces lens implementation (lane 7, Research worker).

Implements the ``LensImplementation`` seam from ``app.agents.lenses`` for
``lensType == porter_five_forces`` only:

* ``build_prompt_inputs`` assembles the model call strictly from the frozen
  ``LensRequest`` (published prompt text + frozen reference IDs). Unsupported
  input - a missing prompt, fewer than two frozen market options, or no frozen
  evidence/research packets to link against - fails closed *before* any model
  call instead of letting the model improvise an industry analysis.
* ``validate_behavior`` deterministically enforces the published behavior
  contract (manifest ``lens_protocols[porter_five_forces]`` and quality gate
  ``LQ-FIVEFORCES``) on the untrusted stage output. It never repairs content;
  a failing report sends the run back to the research worker.

The JSON *shape* is owned by ``strategic-lens-output.schema.json`` (validated
by the shared runtime); this module checks the *behavior* on top of the shape,
so it re-checks structure defensively but its own value is the semantic rules:
per-market boundary, five canonical forces exactly once, two resolvable
evidence items per force, a real changing trend, regulatory/complementor
correction, and the "average score is descriptive only" red line.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.agents.errors import SchemaValidationError
from app.agents.lenses import (
    LensBehaviorReport,
    LensPromptInputs,
    LensRequest,
    LensSpec,
    StrategicLensStageOutput,
    lens_spec,
)
from app.types import StrategicLensType

# Canonical force set from the published schema (forces items enum).
CANONICAL_FORCE_IDS: frozenset[str] = frozenset(
    {"rivalry", "new_entrants", "substitutes", "supplier_power", "buyer_power"}
)
MIN_EVIDENCE_PER_FORCE = 2
MIN_MARKETS = 2
# Descriptive average must stay an arithmetic mean of the five ordinal scores;
# anything else is a hidden formula pretending to be a validated score.
AVERAGE_SCORE_TOLERANCE = 1e-6

# Phrases that would turn an ordinal threat profile into a fake probability or
# a validated-looking decision score. Checked on comparison/implication prose.
_FAKE_CERTAINTY_MARKERS: tuple[str, ...] = (
    "probability of success",
    "success probability",
    "chance of success",
    "% chance",
    "成功概率",
    "成功率",
    "胜率",
)


class PorterFiveForcesLens:
    """``LensImplementation`` for the ``porter_five_forces`` lens type."""

    lens_type: StrategicLensType = StrategicLensType.PORTER_FIVE_FORCES

    def __init__(self) -> None:
        self._spec: LensSpec = lens_spec(self.lens_type)

    # -- prompt assembly ---------------------------------------------------------

    def build_prompt_inputs(self, request: LensRequest) -> LensPromptInputs:
        """Assemble the model call from the frozen request, failing closed on
        unsupported input instead of letting the model guess an industry."""

        if request.lens_type is not self.lens_type:
            raise SchemaValidationError(
                "porter lens received a request for "
                f"{request.lens_type!r}",
                findings=("lens_type_mismatch",),
            )
        problems: list[str] = []
        if not request.prompt_text.strip():
            problems.append("missing_published_prompt_text")
        if len(request.option_ids) < MIN_MARKETS:
            problems.append("fewer_than_two_frozen_market_options")
        if not request.research_packet_refs:
            problems.append("no_frozen_research_packets")
        if not request.evidence_refs:
            problems.append("no_frozen_evidence_to_link")
        if problems:
            raise SchemaValidationError(
                "unsupported input for porter_five_forces lens: "
                + ", ".join(problems),
                findings=tuple(problems),
            )

        user = "\n".join(
            (
                "## Frozen run inputs (IDs resolve only inside this run)",
                f"marketOptionIds: {_format_ids(request.option_ids)}",
                f"researchPacketIds: {_format_ids(request.research_packet_refs)}",
                f"evidenceIds: {_format_ids(request.evidence_refs)}",
                f"claimIds: {_format_ids(request.claim_refs)}",
                f"assumptionIds: {_format_ids(request.assumption_refs)}",
                "",
                "Analyze each market option separately. Cite only the evidence",
                "IDs listed above; submit researchRequests instead of guessing",
                "when evidence for a force is missing.",
            )
        )
        return LensPromptInputs(
            system=request.prompt_text,
            user=user,
            schema_content_def=self._spec.content_def,
        )

    # -- behavior validation -----------------------------------------------------

    def validate_behavior(
        self, output: StrategicLensStageOutput
    ) -> LensBehaviorReport:
        """Deterministically check the LQ-FIVEFORCES behavior contract."""

        reasons: list[str] = []
        findings: list[str] = []

        if output.lens_type is not self.lens_type:
            return LensBehaviorReport(
                lens_type=self.lens_type,
                ok=False,
                reason_codes=("lens_type_mismatch",),
                findings=(f"stage output is for {output.lens_type!r}",),
            )
        if output.phase != self._spec.phase:
            reasons.append("wrong_phase")
            findings.append(
                f"phase must be {self._spec.phase!r}, got {output.phase!r}"
            )
        if output.source_skill_version != self._spec.source_skill_version:
            reasons.append("wrong_source_skill_version")

        content = output.content
        declared_evidence = frozenset(output.references.get("evidenceIds", ()))
        analyses = content.get("marketAnalyses")
        if not isinstance(analyses, Sequence) or isinstance(analyses, (str, bytes)):
            return LensBehaviorReport(
                lens_type=self.lens_type,
                ok=False,
                reason_codes=(*reasons, "market_analyses_missing"),
                findings=(*findings, "content.marketAnalyses is absent or not a list"),
            )

        # at_least_two_markets
        if len(analyses) < MIN_MARKETS:
            reasons.append("fewer_than_two_markets")
            findings.append(
                f"expected >= {MIN_MARKETS} market analyses, got {len(analyses)}"
            )
        seen_options: set[str] = set()
        for index, market in enumerate(analyses):
            if not isinstance(market, Mapping):
                reasons.append("market_analysis_not_object")
                findings.append(f"marketAnalyses[{index}] is not an object")
                continue
            label = str(market.get("optionId", f"marketAnalyses[{index}]"))
            if label in seen_options:
                reasons.append("duplicate_market_option")
                findings.append(f"market option {label} analyzed twice")
            seen_options.add(label)
            self._check_market(
                market, label, declared_evidence, reasons, findings
            )

        self._check_cross_market_and_implications(content, reasons, findings)

        # scoreIsNotDecisionFormula_is_true_and_score_does_not_decide
        if content.get("scoreIsNotDecisionFormula") is not True:
            reasons.append("score_presented_as_decision_formula")
            findings.append(
                "scoreIsNotDecisionFormula must be literally true; the average"
                " threat score is descriptive only"
            )

        deduped = tuple(dict.fromkeys(reasons))
        return LensBehaviorReport(
            lens_type=self.lens_type,
            ok=not deduped,
            reason_codes=deduped,
            findings=tuple(findings),
        )

    # -- per-market checks -------------------------------------------------------

    def _check_market(
        self,
        market: Mapping[str, Any],
        label: str,
        declared_evidence: frozenset[str],
        reasons: list[str],
        findings: list[str],
    ) -> None:
        # each_market_option_has_its_own_defensible_industry_boundary
        boundary = market.get("industryBoundary")
        if not isinstance(boundary, Mapping):
            reasons.append("industry_boundary_missing")
            findings.append(f"{label}: industryBoundary is absent")
        else:
            for key in (
                "coreValue",
                "upstream",
                "downstream",
                "crossIndustrySubstitutes",
                "boundaryRisk",
            ):
                if not _non_empty(boundary.get(key)):
                    reasons.append("industry_boundary_incomplete")
                    findings.append(f"{label}: industryBoundary.{key} is empty")

        # all_five_forces_exist_exactly_once_per_market
        forces = market.get("forces")
        force_scores: list[int] = []
        if not isinstance(forces, Sequence) or isinstance(forces, (str, bytes)):
            reasons.append("forces_missing")
            findings.append(f"{label}: forces is absent or not a list")
        else:
            seen: dict[str, int] = {}
            for force in forces:
                if not isinstance(force, Mapping):
                    reasons.append("force_not_object")
                    findings.append(f"{label}: a force entry is not an object")
                    continue
                force_id = str(force.get("forceId", ""))
                seen[force_id] = seen.get(force_id, 0) + 1
                self._check_force(
                    force, force_id, label, declared_evidence, reasons, findings
                )
                score = force.get("threatScore")
                if isinstance(score, int) and 1 <= score <= 5:
                    force_scores.append(score)
                else:
                    reasons.append("threat_score_not_ordinal_1_to_5")
                    findings.append(
                        f"{label}/{force_id}: threatScore must be an integer 1-5"
                    )
            missing = CANONICAL_FORCE_IDS - set(seen)
            duplicated = {fid for fid, count in seen.items() if count > 1}
            unknown = set(seen) - CANONICAL_FORCE_IDS
            if missing:
                reasons.append("missing_canonical_force")
                findings.append(f"{label}: missing forces {sorted(missing)}")
            if duplicated:
                reasons.append("duplicated_force")
                findings.append(f"{label}: duplicated forces {sorted(duplicated)}")
            if unknown:
                # e.g. a sixth "regulation" force averaged in with the five.
                reasons.append("non_canonical_sixth_force")
                findings.append(
                    f"{label}: non-canonical forces {sorted(unknown)}; regulation"
                    " and complementors are corrections, not a sixth force"
                )

        # average_score_is_not_used_as_the_market_decision_formula: the stored
        # average must be exactly the descriptive mean of the five ordinal
        # scores - any other number is an undeclared formula.
        average = market.get("averageThreatScore")
        if len(force_scores) == len(CANONICAL_FORCE_IDS):
            expected = sum(force_scores) / len(force_scores)
            if (
                not isinstance(average, (int, float))
                or abs(float(average) - expected) > AVERAGE_SCORE_TOLERANCE
            ):
                reasons.append("average_score_is_not_descriptive_mean")
                findings.append(
                    f"{label}: averageThreatScore {average!r} != mean of force"
                    f" scores {expected:.4f}"
                )

        # industry_boundary_change_trend_regulatory_and_complementors_present
        if not _non_empty(market.get("changingTrend")):
            reasons.append("changing_trend_missing")
            findings.append(
                f"{label}: no changing technology/policy/demand trend identified"
            )
        if not _non_empty(market.get("regulatoryAssessment")):
            reasons.append("regulatory_assessment_missing")
            findings.append(f"{label}: regulatoryAssessment is empty")
        if not _non_empty(market.get("complementors")):
            reasons.append("complementors_missing")
            findings.append(f"{label}: complementors are empty")

    def _check_force(
        self,
        force: Mapping[str, Any],
        force_id: str,
        label: str,
        declared_evidence: frozenset[str],
        reasons: list[str],
        findings: list[str],
    ) -> None:
        # each_force_has_at_least_two_resolvable_evidence
        evidence_ids = force.get("evidenceIds")
        if not isinstance(evidence_ids, Sequence) or isinstance(
            evidence_ids, (str, bytes)
        ):
            reasons.append("force_evidence_missing")
            findings.append(f"{label}/{force_id}: evidenceIds is not a list")
            return
        unique_ids = [str(eid) for eid in dict.fromkeys(evidence_ids)]
        if len(unique_ids) < MIN_EVIDENCE_PER_FORCE:
            reasons.append("force_evidence_below_minimum")
            findings.append(
                f"{label}/{force_id}: {len(unique_ids)} unique evidence IDs,"
                f" need >= {MIN_EVIDENCE_PER_FORCE}"
            )
        # Every cited ID must also be declared in references.evidenceIds so the
        # server can resolve it against the frozen run (evidence linking).
        unresolvable = [eid for eid in unique_ids if eid not in declared_evidence]
        if unresolvable:
            reasons.append("force_evidence_not_in_references")
            findings.append(
                f"{label}/{force_id}: evidence not declared in"
                f" references.evidenceIds: {unresolvable}"
            )
        if not _non_empty(force.get("keyIndicators")):
            reasons.append("force_key_indicators_missing")
            findings.append(f"{label}/{force_id}: keyIndicators are empty")
        if not _non_empty(force.get("reasoning")):
            reasons.append("force_reasoning_missing")
            findings.append(f"{label}/{force_id}: reasoning is empty")

    # -- cross-market checks -----------------------------------------------------

    def _check_cross_market_and_implications(
        self,
        content: Mapping[str, Any],
        reasons: list[str],
        findings: list[str],
    ) -> None:
        comparison = content.get("crossMarketComparison")
        if not _non_empty(comparison):
            reasons.append("cross_market_comparison_missing")
            findings.append("crossMarketComparison is empty")

        implications = content.get("strategicImplications")
        if not isinstance(implications, Sequence) or isinstance(
            implications, (str, bytes)
        ) or not implications:
            reasons.append("strategic_implications_missing")
            findings.append("strategicImplications is absent or empty")
            implications = ()

        prose: list[str] = [str(comparison or "")]
        for item in implications:
            if not isinstance(item, Mapping):
                reasons.append("strategic_implication_not_object")
                findings.append("a strategicImplications entry is not an object")
                continue
            # strategic implications must be conditional, evidence-linked logic
            if not _non_empty(item.get("logic")):
                reasons.append("implication_logic_missing")
                findings.append(
                    f"implication for {item.get('optionId')!r} has no logic chain"
                )
            if not _non_empty(item.get("conditions")):
                reasons.append("implication_conditions_missing")
                findings.append(
                    f"implication for {item.get('optionId')!r} is unconditional"
                )
            prose.append(str(item.get("logic", "")))

        # no fake probability anywhere in comparison/implication prose
        lowered = "\n".join(prose).lower()
        hits = [marker for marker in _FAKE_CERTAINTY_MARKERS if marker in lowered]
        if hits:
            reasons.append("fake_probability_language")
            findings.append(
                "ordinal threat profile presented as success probability:"
                f" {hits}"
            )


def _non_empty(value: Any) -> bool:
    """True for a non-blank string or a sequence with at least one non-blank item."""

    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Sequence):
        return any(_non_empty(item) for item in value)
    return False


def _format_ids(ids: Sequence[str]) -> str:
    return ", ".join(ids) if ids else "(none)"


def porter_five_forces_lens() -> PorterFiveForcesLens:
    """Factory the Ways Coordinator registers into the shared ``LensRegistry``."""

    return PorterFiveForcesLens()
