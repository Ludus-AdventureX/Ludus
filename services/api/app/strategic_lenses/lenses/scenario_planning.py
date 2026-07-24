"""Scenario Planning strategic lens (lane 9, synthesis worker).

Implements the ``LensImplementation`` seam from ``app.agents.lenses`` for exactly
one lens type: ``scenario_planning``. Everything here is a deterministic pure
function over the frozen method-pack contract
(``method-packs/hardtech-market-direction/1.1.0``):

* prompt-input assembly from the frozen :class:`LensRequest` (no live IO);
* the behavior contract from 18-detailed-development-plan Task 10 / the seam's
  ``behavior_assertions`` for ``scenario_planning``;
* the contract-allowed simulation seed mapping: ``scenarioCandidate`` entries per
  ``simulation-seeds.schema.json`` ``$defs/scenarioCandidate``. This lane never
  creates or mutates the Simulation canonical graph, ``candidateNodes`` or
  ``candidateEdges`` - those belong to the simulation/graph owner.

Scenarios are resilience frames, not probabilistic forecasts: any probability
language inside the content fails the behavior gate.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from app.agents.errors import LensBehaviorError
from app.agents.lenses import (
    LensBehaviorReport,
    LensPromptInputs,
    LensRequest,
    StrategicLensStageOutput,
    lens_spec,
)
from app.types import StrategicLensType

LENS_TYPE = StrategicLensType.SCENARIO_PLANNING
SPEC = lens_spec(LENS_TYPE)

# Deterministic normalized shifts used by the seed mapping when a scenario's axis
# state text exactly matches the declared axis pole. Anything unresolved maps to
# 0.0 instead of guessing - the sandbox owner can raise precision later without
# this lane inventing numbers the model never asserted.
_HIGH_POLE_SHIFT = 0.5
_LOW_POLE_SHIFT = -0.5
_UNRESOLVED_SHIFT = 0.0

# The contract forbids writing scenario/success probabilities anywhere in the
# frame. Deterministic marker scan over every string in ``content``.
_PROBABILITY_MARKERS: tuple[str, ...] = (
    "概率",
    "probability",
    "% chance",
    "chance of success",
    "成功率",
)

# ``text`` fields in the simulation-seeds schema cap at 500 chars.
_SEED_TEXT_MAX = 500


def _clip(value: str, limit: int = _SEED_TEXT_MAX) -> str:
    return value if len(value) <= limit else value[:limit]


def _iter_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _iter_strings(item)
    elif isinstance(value, Sequence):
        for item in value:
            yield from _iter_strings(item)


class ScenarioPlanningLens:
    """Seam implementation for the ``scenario_planning`` lens."""

    lens_type: StrategicLensType = LENS_TYPE

    # -- prompt assembly ---------------------------------------------------------

    def build_prompt_inputs(self, request: LensRequest) -> LensPromptInputs:
        """Assemble deterministic model inputs from the frozen request.

        The system prompt is the published pack prompt text (loaded by the
        coordinator from ``method-packs``, never re-read from ``ways``). The user
        message only exposes frozen-run reference IDs, candidate option IDs and
        validated upstream lens content (e.g. Porter) - nothing outside the run.
        """

        if request.lens_type is not LENS_TYPE:
            raise LensBehaviorError(
                f"scenario_planning lens received request for {request.lens_type}",
                reason_codes=("wrong_lens_type",),
            )
        upstream = {
            str(lens): dict(content)
            for lens, content in sorted(
                request.upstream_lens_outputs.items(), key=lambda kv: str(kv[0])
            )
        }
        user_payload = {
            "task": "scenario_planning",
            "workspaceId": request.workspace_id,
            "analysisRunId": request.analysis_run_id,
            "candidateOptionIds": sorted(request.option_ids),
            "references": {
                "sourcePacketIds": sorted(request.research_packet_refs),
                "evidenceIds": sorted(request.evidence_refs),
                "claimIds": sorted(request.claim_refs),
                "assumptionIds": sorted(request.assumption_refs),
                "challengeIds": sorted(request.challenge_refs),
            },
            "upstreamLensContent": upstream,
            "outputContract": {
                "schemaId": SPEC.output_schema_id,
                "contentDef": SPEC.content_def,
                "phase": SPEC.phase,
                "sourceSkillVersion": SPEC.source_skill_version,
            },
        }
        return LensPromptInputs(
            system=request.prompt_text,
            user=json.dumps(user_payload, ensure_ascii=False, sort_keys=True),
            schema_content_def=SPEC.content_def,
        )

    # -- behavior contract -------------------------------------------------------

    def validate_behavior(self, output: StrategicLensStageOutput) -> LensBehaviorReport:
        """Enforce the Task 10 behavior contract for ``scenario_planning``.

        JSON-schema shape is checked upstream by the structured-output layer;
        this gate fails closed on behavior, never repairs or completes a frame.
        """

        codes: list[str] = []
        findings: list[str] = []

        def fail(code: str, finding: str) -> None:
            if code not in codes:
                codes.append(code)
            findings.append(finding)

        if output.lens_type is not LENS_TYPE:
            fail("wrong_lens_type", f"lensType is {output.lens_type}")
        if output.phase != SPEC.phase:
            fail("wrong_phase", f"phase is {output.phase!r}, expected {SPEC.phase!r}")
        if output.source_skill_version != SPEC.source_skill_version:
            fail(
                "wrong_source_skill_version",
                f"sourceSkillVersion is {output.source_skill_version!r}",
            )

        content = output.content
        declared_evidence = set(output.references.get("evidenceIds", ()))

        # 1. predetermined elements and >= 2 key uncertainties
        if not content.get("predeterminedElements"):
            fail("predetermined_elements_missing", "predeterminedElements is empty")
        uncertainties = list(content.get("keyUncertainties", ()))
        if len(uncertainties) < 2:
            fail(
                "key_uncertainties_insufficient",
                f"{len(uncertainties)} key uncertainties, need >= 2",
            )
        uncertainty_by_id: dict[str, Mapping[str, Any]] = {}
        for unc in uncertainties:
            unc_id = unc.get("uncertaintyId", "")
            if unc_id in uncertainty_by_id:
                fail("uncertainty_id_duplicate", f"duplicate uncertaintyId {unc_id!r}")
            uncertainty_by_id[unc_id] = unc
            undeclared = set(unc.get("evidenceIds", ())) - declared_evidence
            if undeclared:
                # facts must cite declared evidence; speculation belongs in
                # assumption refs, not in silently-invented evidence IDs.
                fail(
                    "content_evidence_not_declared",
                    f"uncertainty {unc_id!r} cites undeclared evidence {sorted(undeclared)}",
                )

        # 2. exactly two axes, on distinct high-impact/high-uncertainty factors
        axes = list(content.get("axes", ()))
        if len(axes) != 2:
            fail("axes_count_not_two", f"{len(axes)} axes, need exactly 2")
        axis_uncertainty_ids: list[str] = []
        for axis in axes:
            ref = axis.get("uncertaintyId", "")
            axis_uncertainty_ids.append(ref)
            unc = uncertainty_by_id.get(ref)
            if unc is None:
                fail("axis_uncertainty_ref_unresolved", f"axis references unknown {ref!r}")
            elif not (unc.get("impact") == "high" and unc.get("uncertainty") == "high"):
                fail(
                    "axis_not_high_impact_high_uncertainty",
                    f"axis uncertainty {ref!r} is {unc.get('impact')}/{unc.get('uncertainty')}",
                )
        if len(axes) == 2 and axis_uncertainty_ids[0] == axis_uncertainty_ids[1]:
            fail("axes_not_distinct", "both axes reference the same uncertainty")

        # 3. 3-4 scenarios, exactly one baseline, >= 2 structural breaks
        scenarios = list(content.get("scenarios", ()))
        if not 3 <= len(scenarios) <= 4:
            fail("scenario_count_out_of_range", f"{len(scenarios)} scenarios, need 3-4")
        kinds = [frame.get("kind") for frame in scenarios]
        if kinds.count("baseline") != 1:
            fail("baseline_count_not_one", f"{kinds.count('baseline')} baseline frames")
        if kinds.count("structural_break") < 2:
            fail(
                "structural_breaks_insufficient",
                f"{kinds.count('structural_break')} structural breaks, need >= 2",
            )
        scenario_ids: set[str] = set()
        signal_ids: set[str] = set()
        seen_axis_states: set[tuple[str, ...]] = set()
        for frame in scenarios:
            frame_id = frame.get("scenarioId", "")
            if frame_id in scenario_ids:
                fail("scenario_id_duplicate", f"duplicate scenarioId {frame_id!r}")
            scenario_ids.add(frame_id)
            axis_states = tuple(frame.get("axisStates", ()))
            if axis_states in seen_axis_states:
                # same axis-state combination = numeric variant of the same
                # logic, which the contract forbids as a distinct frame.
                fail(
                    "scenario_axis_states_not_distinct",
                    f"scenario {frame_id!r} repeats axis states {axis_states!r}",
                )
            seen_axis_states.add(axis_states)

            # 4. per-frame timeline, >= 3 stakeholder states, 3-5 early signals
            if len(frame.get("timeline", ())) < 2:
                fail("timeline_turning_points_insufficient", f"scenario {frame_id!r}")
            if len(frame.get("stakeholderStates", ())) < 3:
                fail("stakeholder_states_insufficient", f"scenario {frame_id!r}")
            signals = list(frame.get("earlySignals", ()))
            if not 3 <= len(signals) <= 5:
                fail("early_signals_out_of_range", f"scenario {frame_id!r}")
            for signal in signals:
                signal_id = signal.get("signalId", "")
                if signal_id in signal_ids:
                    fail("signal_id_duplicate", f"duplicate signalId {signal_id!r}")
                signal_ids.add(signal_id)

        # 5. every strategy tested in every frame; at least one result killed
        tests = list(content.get("strategyTests", ()))
        tested_options = {test.get("optionId", "") for test in tests}
        seen_cells: set[tuple[str, str]] = set()
        performances: list[str] = []
        for test in tests:
            cell = (test.get("scenarioId", ""), test.get("optionId", ""))
            if cell[0] not in scenario_ids:
                fail("strategy_test_scenario_unresolved", f"unknown scenarioId {cell[0]!r}")
            if cell in seen_cells:
                fail("strategy_test_duplicate", f"duplicate test cell {cell!r}")
            seen_cells.add(cell)
            performances.append(test.get("performance", ""))
            unresolved = set(test.get("triggerSignalIds", ())) - signal_ids
            if unresolved:
                fail(
                    "trigger_signal_unresolved",
                    f"test {cell!r} cites unknown signals {sorted(unresolved)}",
                )
        for option_id in sorted(tested_options):
            missing = scenario_ids - {c[0] for c in seen_cells if c[1] == option_id}
            if missing:
                fail(
                    "strategy_matrix_incomplete",
                    f"option {option_id!r} untested in scenarios {sorted(missing)}",
                )
        if "killed" not in performances:
            fail("no_strategy_killed", "no strategy test result is 'killed'")
        if content.get("strategyKilledInAtLeastOneScenario") is not True:
            fail(
                "killed_flag_not_true",
                "strategyKilledInAtLeastOneScenario must be true",
            )

        if not content.get("monitoringActions"):
            fail("monitoring_actions_missing", "monitoringActions is empty")
        if not content.get("irreducibleUnknowns"):
            fail("irreducible_unknowns_missing", "irreducibleUnknowns is empty")

        # scenarios are resilience frames, never probability forecasts
        lowered = (text.lower() for text in _iter_strings(dict(content)))
        if any(marker in text for text in lowered for marker in _PROBABILITY_MARKERS):
            fail("probability_language_present", "content contains probability language")

        return LensBehaviorReport(
            lens_type=LENS_TYPE,
            ok=not codes,
            reason_codes=tuple(codes),
            findings=tuple(findings),
        )


def validate_option_coverage(
    output: StrategicLensStageOutput, option_ids: Sequence[str]
) -> LensBehaviorReport:
    """Cross-check tested options against the frozen Charter option set.

    Kept outside :meth:`ScenarioPlanningLens.validate_behavior` because the seam
    protocol validates the output alone; the runner calls this with the frozen
    request's ``option_ids`` before accepting the artifact.
    """

    tested = {test.get("optionId", "") for test in output.content.get("strategyTests", ())}
    expected = set(option_ids)
    codes: list[str] = []
    findings: list[str] = []
    if expected - tested:
        codes.append("charter_option_untested")
        findings.append(f"untested charter options: {sorted(expected - tested)}")
    if expected and (tested - expected):
        codes.append("unknown_option_tested")
        findings.append(f"tested unknown options: {sorted(tested - expected)}")
    return LensBehaviorReport(
        lens_type=LENS_TYPE, ok=not codes, reason_codes=tuple(codes), findings=tuple(findings)
    )


def build_scenario_candidates(
    output: StrategicLensStageOutput,
    *,
    source_lens_artifact_id: str,
    focal_option_id: str | None = None,
) -> tuple[dict[str, Any], ...]:
    """Map a behavior-valid frame set to ``scenarioCandidate`` simulation seeds.

    This is the only simulation surface this lane emits (simulation-seeds schema
    ``$defs/scenarioCandidate``). It never builds nodes/edges and never creates a
    ``ScenarioVersion``: the user must review a ready frame in graph bulk review
    before the server freezes an immutable ScenarioVersion from it. Risk
    tolerance is intentionally absent - it lives in Charter/Profile/Strategy/
    ScoreDefinition, never in scenario data.

    ``strategySurvives`` is derived from the frame's own strategy tests: with a
    ``focal_option_id`` it reflects that option's fate in the frame, otherwise a
    frame counts as non-survivable when any tested strategy is ``killed`` there.
    """

    report = ScenarioPlanningLens().validate_behavior(output)
    if not report.ok:
        raise LensBehaviorError(
            "cannot map seeds from a frame set that fails the behavior contract",
            reason_codes=report.reason_codes,
        )

    content = output.content
    uncertainty_by_id = {
        unc["uncertaintyId"]: unc for unc in content.get("keyUncertainties", ())
    }
    axes = list(content.get("axes", ()))
    killed_cells = {
        (test["scenarioId"], test["optionId"])
        for test in content.get("strategyTests", ())
        if test.get("performance") == "killed"
    }

    candidates: list[dict[str, Any]] = []
    for frame in content.get("scenarios", ()):
        frame_id = frame["scenarioId"]
        if focal_option_id is not None:
            survives = (frame_id, focal_option_id) not in killed_cells
        else:
            survives = not any(cell[0] == frame_id for cell in killed_cells)

        axis_states = list(frame.get("axisStates", ()))
        driver_states: list[dict[str, Any]] = []
        for index, axis in enumerate(axes):
            uncertainty = uncertainty_by_id[axis["uncertaintyId"]]
            state = axis_states[index] if index < len(axis_states) else "unspecified"
            if state == axis.get("highState"):
                shift = _HIGH_POLE_SHIFT
            elif state == axis.get("lowState"):
                shift = _LOW_POLE_SHIFT
            else:
                shift = _UNRESOLVED_SHIFT
            driver_states.append(
                {
                    "driverLabel": _clip(str(uncertainty["factor"])),
                    "state": str(state),
                    "proposedNormalizedShift": shift,
                    # facts keep their evidence refs; the shift itself is a
                    # deterministic mapping, so no assumption IDs are invented.
                    "evidenceIds": sorted(set(uncertainty.get("evidenceIds", ()))),
                    "assumptionIds": [],
                }
            )

        candidates.append(
            {
                "sourceLensArtifactId": source_lens_artifact_id,
                "sourceStrategicScenarioId": frame_id,
                "name": _clip(str(frame["name"])),
                "kind": frame["kind"],
                "coreLogic": frame["coreLogic"],
                "strategySurvives": survives,
                "earlySignals": [
                    {
                        "signalId": signal["signalId"],
                        "type": signal["type"],
                        "observable": signal["observable"],
                        "thresholdOrPattern": signal["thresholdOrPattern"],
                        "cadence": signal["cadence"],
                    }
                    for signal in frame.get("earlySignals", ())
                ],
                "driverStates": driver_states,
            }
        )

    if not any(not candidate["strategySurvives"] for candidate in candidates):
        # seeds schema requires >= 1 non-survivable frame; with a focal option
        # that never dies the mapping must fail closed, not fabricate one.
        raise LensBehaviorError(
            "no scenario candidate has strategySurvives=false for the focal option",
            reason_codes=("focal_option_never_killed",),
        )
    return tuple(candidates)


# Singleton for the coordinator's registry wiring.
IMPLEMENTATION = ScenarioPlanningLens()
