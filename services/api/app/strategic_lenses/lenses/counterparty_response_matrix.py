"""Counterparty Response Matrix lens (L3 specialist lane).

Implements the ``LensImplementation`` seam published by the Ways Coordinator in
``app.agents.lenses`` for exactly one lens type:
``counterparty_response_matrix``. The behavior contract mirrors the immutable
published pack ``method-packs/hardtech-market-direction/1.1.0``:

* prompt: ``prompts/lenses/counterparty-response-matrix.md``;
* stage-output schema branch: ``counterpartyContent`` in
  ``schemas/strategic-lens-output.schema.json``;
* seam behavior assertions: 1-2 key actors, 2-3 actions with exactly one
  ``no_action`` baseline, one-layer response depth, full
  optimal/worst/likely/window/gap/counterresponse matrix coverage,
  publication test + per-action downside asymmetry + reflexivity warning.

The shared seam module is merged on the coordinator branch, not on this lane's
baseline, so the seam types are imported when present and mirrored by
structural stand-ins otherwise. The stand-ins carry the same fields in the
same order and are replaced by the real seam types at integration; nothing
here redefines canonical schema, manifest, migrations, or other lenses.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.types import StrategicLensType

LENS_TYPE = StrategicLensType.COUNTERPARTY_RESPONSE_MATRIX
PHASE = "adversarial_stress"
SOURCE_SKILL_VERSION = "1.0.0"
CONTENT_DEF = "counterpartyContent"
PROMPT_REF = "prompts/lenses/counterparty-response-matrix.md"

# Mirrored from the published pack manifest ``lens_artifact_contract``; the
# coordinator seam owns the authoritative copy and wins on import.
_FALLBACK_ALLOWED_TOP_LEVEL_FIELDS: frozenset[str] = frozenset(
    {"lensType", "sourceSkillVersion", "phase", "references", "researchRequests", "content"}
)
_FALLBACK_FORBIDDEN_SERVER_OWNED_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "artifactId",
        "workspaceId",
        "decisionCaseId",
        "analysisRunId",
        "charterId",
        "charterVersion",
        "caseVersion",
        "caseSnapshotHash",
        "methodId",
        "methodVersion",
        "methodContentHash",
        "schemaVersion",
        "producerRole",
        "status",
        "originModes",
        "contentHash",
        "createdAt",
    }
)

try:  # pragma: no cover - taken once the coordinator seam is merged
    from app.agents.lenses import (
        ALLOWED_TOP_LEVEL_FIELDS,
        FORBIDDEN_SERVER_OWNED_FIELDS,
        LensBehaviorReport,
        LensPromptInputs,
        lens_output_contract,
        load_lens_content_schema,
    )
except ImportError:  # baseline without the shared seam: structural stand-ins
    from dataclasses import dataclass

    ALLOWED_TOP_LEVEL_FIELDS = _FALLBACK_ALLOWED_TOP_LEVEL_FIELDS
    FORBIDDEN_SERVER_OWNED_FIELDS = _FALLBACK_FORBIDDEN_SERVER_OWNED_FIELDS

    def lens_output_contract(  # pragma: no cover - baseline without the seam
        *, lens_type: str, phase: str, source_skill_version: str, content_def: str
    ) -> str:
        """Stand-in: baseline branches never run live lens calls."""
        return ""

    def load_lens_content_schema(content_def: str) -> str:  # pragma: no cover
        """Stand-in: baseline branches never run live lens calls."""
        return ""

    @dataclass(frozen=True, slots=True)
    class LensPromptInputs:  # type: ignore[no-redef]
        """Stand-in mirroring ``app.agents.lenses.LensPromptInputs``."""

        system: str
        user: str
        schema_content_def: str

    @dataclass(frozen=True, slots=True)
    class LensBehaviorReport:  # type: ignore[no-redef]
        """Stand-in mirroring ``app.agents.lenses.LensBehaviorReport``."""

        lens_type: StrategicLensType
        ok: bool
        reason_codes: tuple[str, ...] = ()
        findings: tuple[str, ...] = ()


class CounterpartyLensError(ValueError):
    """A lens request or payload violates the counterparty lane contract."""


# Reason codes: the first five mirror the seam ``behavior_assertions`` for this
# lens verbatim; the rest are lane-level envelope/discipline checks.
CODE_ACTORS = "one_to_two_key_actors"
CODE_ACTIONS = "two_to_three_actions_with_exactly_one_no_action"
CODE_DEPTH = "response_depth_is_one_layer"
CODE_MATRIX = "matrix_covers_optimal_worst_likely_window_gap_counterresponse"
CODE_PUBLICATION = "publication_test_and_per_action_downside_asymmetry_and_reflexivity"
CODE_LENS_TYPE = "lens_type_mismatch"
CODE_PHASE = "phase_must_be_adversarial_stress"
CODE_SKILL_VERSION = "source_skill_version_mismatch"
CODE_ASSUMPTIONS = "core_assumptions_must_be_registered_references"

_MATRIX_TEXT_FIELDS = (
    "optimalResponse",
    "worstResponseForUs",
    "mostLikelyResponse",
    "responseWindow",
    "optimalLikelyGap",
    "ourCounterResponse",
    "fallbackCost",
)
_DOWNSIDE_FLOORS = frozenset({"bounded", "unbounded", "unknown"})
_VULNERABILITY_LEVELS = frozenset({"none", "low", "medium", "high", "critical"})
_ACTION_TYPES = frozenset({"active", "no_action"})


def _text(value: Any) -> str | None:
    """Return the stripped string when non-empty, else None."""

    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _items(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return list(value)
    return []


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def validate_counterparty_content(
    content: Mapping[str, Any],
    *,
    registered_assumption_ids: frozenset[str] = frozenset(),
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Deterministic behavior validation of one ``counterpartyContent`` payload.

    Returns ``(reason_codes, findings)``; an empty ``reason_codes`` means the
    payload satisfies the lane behavior contract. Checks are evidence-based and
    fail closed: structural gaps yield reason codes instead of exceptions so
    the run can be blocked with explainable findings.
    """

    codes: list[str] = []
    findings: list[str] = []

    def flag(code: str, finding: str) -> None:
        if code not in codes:
            codes.append(code)
        findings.append(finding)

    content = _mapping(content)

    # -- response depth: exactly one layer, never a deep game tree -----------
    if content.get("maxResponseDepth") != 1:
        flag(CODE_DEPTH, f"maxResponseDepth must be 1, got {content.get('maxResponseDepth')!r}")

    # -- actors: 1-2 key counterparties with real response capacity ----------
    counterparties = _items(content.get("counterparties"))
    counterparty_ids: list[str] = []
    if not 1 <= len(counterparties) <= 2:
        flag(CODE_ACTORS, f"expected 1-2 counterparties, got {len(counterparties)}")
    for index, actor in enumerate(counterparties):
        actor = _mapping(actor)
        actor_id = _text(actor.get("counterpartyId"))
        if actor_id is None:
            flag(CODE_ACTORS, f"counterparties[{index}] is missing counterpartyId")
            continue
        if actor_id in counterparty_ids:
            flag(CODE_ACTORS, f"duplicate counterpartyId {actor_id!r}")
        counterparty_ids.append(actor_id)
        if _text(actor.get("identity")) is None or _text(actor.get("coreInterest")) is None:
            flag(CODE_ACTORS, f"counterparty {actor_id!r} needs identity and coreInterest")
        if not _items(actor.get("responseTools")) or not _items(actor.get("constraints")):
            flag(CODE_ACTORS, f"counterparty {actor_id!r} needs responseTools and constraints")

    # -- our actions: 2-3, materially distinct, exactly one no_action --------
    actions = _items(content.get("ourActions"))
    action_ids: list[str] = []
    no_action_count = 0
    descriptions: list[str] = []
    if not 2 <= len(actions) <= 3:
        flag(CODE_ACTIONS, f"expected 2-3 ourActions, got {len(actions)}")
    for index, action in enumerate(actions):
        action = _mapping(action)
        action_id = _text(action.get("actionId"))
        if action_id is None:
            flag(CODE_ACTIONS, f"ourActions[{index}] is missing actionId")
            continue
        if action_id in action_ids:
            flag(CODE_ACTIONS, f"duplicate actionId {action_id!r}")
        action_ids.append(action_id)
        action_type = action.get("actionType")
        if action_type not in _ACTION_TYPES:
            flag(CODE_ACTIONS, f"action {action_id!r} has invalid actionType {action_type!r}")
        elif action_type == "no_action":
            no_action_count += 1
        description = _text(action.get("description"))
        if description is None:
            flag(CODE_ACTIONS, f"action {action_id!r} needs a description")
        elif description in descriptions:
            # material-difference proxy: identical wording is not a distinct action
            flag(CODE_ACTIONS, f"action {action_id!r} duplicates another action description")
        else:
            descriptions.append(description)
        assumption_ids = [_text(item) for item in _items(action.get("coreAssumptionIds"))]
        if not assumption_ids or None in assumption_ids:
            flag(CODE_ASSUMPTIONS, f"action {action_id!r} must declare coreAssumptionIds")
        else:
            unregistered = sorted(
                aid for aid in assumption_ids if aid not in registered_assumption_ids
            )
            if unregistered:
                flag(
                    CODE_ASSUMPTIONS,
                    f"action {action_id!r} cites assumptions missing from "
                    f"references.assumptionIds: {unregistered}",
                )
    if no_action_count != 1:
        flag(CODE_ACTIONS, f"expected exactly one no_action baseline, got {no_action_count}")

    # -- matrix: one row per (counterparty, action), one layer, complete -----
    expected_pairs = {(cp, act) for cp in counterparty_ids for act in action_ids}
    seen_pairs: set[tuple[str, str]] = set()
    for index, row in enumerate(_items(content.get("responseMatrix"))):
        row = _mapping(row)
        cp_id = _text(row.get("counterpartyId"))
        act_id = _text(row.get("actionId"))
        if cp_id is None or act_id is None:
            flag(CODE_MATRIX, f"responseMatrix[{index}] is missing counterpartyId or actionId")
            continue
        pair = (cp_id, act_id)
        if pair not in expected_pairs:
            flag(CODE_MATRIX, f"responseMatrix[{index}] references unknown pair {pair!r}")
            continue
        if pair in seen_pairs:
            flag(CODE_MATRIX, f"responseMatrix[{index}] duplicates pair {pair!r}")
            continue
        seen_pairs.add(pair)
        for field_name in _MATRIX_TEXT_FIELDS:
            if _text(row.get(field_name)) is None:
                flag(CODE_MATRIX, f"responseMatrix[{index}] needs non-empty {field_name!r}")
        if not isinstance(row.get("strategyInvalidated"), bool):
            flag(CODE_MATRIX, f"responseMatrix[{index}] needs boolean strategyInvalidated")
    missing_pairs = sorted(expected_pairs - seen_pairs)
    if missing_pairs:
        flag(CODE_MATRIX, f"responseMatrix is missing pairs: {missing_pairs}")

    # -- publication test, per-action downside asymmetry, reflexivity --------
    publication = _mapping(content.get("publicationTest"))
    if not isinstance(publication.get("responseChangesIfPublished"), bool):
        flag(CODE_PUBLICATION, "publicationTest.responseChangesIfPublished must be a boolean")
    if _text(publication.get("newInformationRevealed")) is None:
        flag(CODE_PUBLICATION, "publicationTest.newInformationRevealed must be non-empty")
    if publication.get("informationAsymmetryVulnerability") not in _VULNERABILITY_LEVELS:
        flag(
            CODE_PUBLICATION,
            "publicationTest.informationAsymmetryVulnerability must be one of "
            f"{sorted(_VULNERABILITY_LEVELS)}",
        )
    if _text(publication.get("mitigation")) is None:
        flag(CODE_PUBLICATION, "publicationTest.mitigation must be non-empty")

    downside_action_ids: list[str] = []
    for index, entry in enumerate(_items(content.get("downsideAsymmetry"))):
        entry = _mapping(entry)
        act_id = _text(entry.get("actionId"))
        if act_id is None or act_id not in action_ids:
            flag(CODE_PUBLICATION, f"downsideAsymmetry[{index}] references unknown action")
            continue
        if act_id in downside_action_ids:
            flag(CODE_PUBLICATION, f"downsideAsymmetry[{index}] duplicates action {act_id!r}")
            continue
        downside_action_ids.append(act_id)
        if entry.get("downsideFloor") not in _DOWNSIDE_FLOORS:
            # no invented survival probabilities: only bounded|unbounded|unknown
            flag(
                CODE_PUBLICATION,
                f"downsideAsymmetry[{index}] downsideFloor must be one of "
                f"{sorted(_DOWNSIDE_FLOORS)}",
            )
        for field_name in ("worstCase", "exitPath", "exitCost"):
            if _text(entry.get(field_name)) is None:
                flag(CODE_PUBLICATION, f"downsideAsymmetry[{index}] needs {field_name!r}")
    missing_downside = sorted(set(action_ids) - set(downside_action_ids))
    if missing_downside:
        flag(CODE_PUBLICATION, f"downsideAsymmetry is missing actions: {missing_downside}")

    if _text(content.get("reflexivityWarning")) is None:
        flag(CODE_PUBLICATION, "reflexivityWarning must be non-empty")

    return tuple(codes), tuple(findings)


def assert_no_server_owned_fields(payload: Mapping[str, Any]) -> None:
    """Reject any model attempt to set server-owned identity/provenance."""

    present = FORBIDDEN_SERVER_OWNED_FIELDS & set(payload)
    if present:
        raise CounterpartyLensError(f"server-owned fields in model output: {sorted(present)}")
    extra = set(payload) - ALLOWED_TOP_LEVEL_FIELDS
    if extra:
        raise CounterpartyLensError(f"unknown top-level fields in model output: {sorted(extra)}")


class CounterpartyResponseMatrixLens:
    """``LensImplementation`` for exactly the counterparty lens type."""

    lens_type: StrategicLensType = LENS_TYPE

    def build_prompt_inputs(self, request: Any) -> LensPromptInputs:
        """Assemble deterministic model inputs from a frozen ``LensRequest``.

        ``system`` is the immutable pack prompt; ``user`` carries only
        run-scoped IDs and the output contract, sorted for determinism. The
        request must already be tenant/run pinned by the coordinator.
        """

        if request.lens_type != LENS_TYPE:
            raise CounterpartyLensError(
                f"request lens type {request.lens_type!r} is not {LENS_TYPE!r}"
            )
        if _text(request.workspace_id) is None or _text(request.analysis_run_id) is None:
            raise CounterpartyLensError("request must pin workspace_id and analysis_run_id")
        prompt_text = request.prompt_text
        if _text(prompt_text) is None:
            raise CounterpartyLensError(f"request.prompt_text must carry {PROMPT_REF}")
        option_ids = tuple(sorted(request.option_ids))
        if not option_ids:
            raise CounterpartyLensError("counterparty lens requires frozen decision options")

        reference_lines = "\n".join(
            f"- {label}: {', '.join(sorted(values)) if values else '(none)'}"
            for label, values in (
                ("sourcePacketIds", request.research_packet_refs),
                ("claimIds", request.claim_refs),
                ("evidenceIds", request.evidence_refs),
                ("assumptionIds", request.assumption_refs),
                ("challengeIds", request.challenge_refs),
            )
        )
        user = (
            "## Frozen decision options\n"
            + "\n".join(f"- {option_id}" for option_id in option_ids)
            + "\n\n## Run-scoped reference IDs (cite only these)\n"
            + reference_lines
            + "\n\n"
            + lens_output_contract(
                lens_type=LENS_TYPE.value,
                phase=PHASE,
                source_skill_version=SOURCE_SKILL_VERSION,
                content_def=CONTENT_DEF,
                content_schema=load_lens_content_schema(CONTENT_DEF),
            )
        )
        return LensPromptInputs(system=prompt_text, user=user, schema_content_def=CONTENT_DEF)

    def validate_behavior(self, output: Any) -> LensBehaviorReport:
        """Check one untrusted stage output against the lane behavior contract."""

        codes: list[str] = []
        findings: list[str] = []
        if output.lens_type != LENS_TYPE:
            codes.append(CODE_LENS_TYPE)
            findings.append(f"stage output lensType is {output.lens_type!r}")
        if output.phase != PHASE:
            codes.append(CODE_PHASE)
            findings.append(f"phase must be {PHASE!r}, got {output.phase!r}")
        if output.source_skill_version != SOURCE_SKILL_VERSION:
            codes.append(CODE_SKILL_VERSION)
            findings.append(
                f"sourceSkillVersion must be {SOURCE_SKILL_VERSION!r}, "
                f"got {output.source_skill_version!r}"
            )
        references = _mapping(output.references)
        registered = frozenset(
            aid
            for aid in (_text(item) for item in _items(references.get("assumptionIds")))
            if aid is not None
        )
        content_codes, content_findings = validate_counterparty_content(
            _mapping(output.content), registered_assumption_ids=registered
        )
        for code in content_codes:
            if code not in codes:
                codes.append(code)
        findings.extend(content_findings)
        return LensBehaviorReport(
            lens_type=LENS_TYPE,
            ok=not codes,
            reason_codes=tuple(codes),
            findings=tuple(findings),
        )


LENS = CounterpartyResponseMatrixLens()
