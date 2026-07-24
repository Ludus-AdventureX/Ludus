"""Strategic-lens contract seam.

This module is the stable interface the five lens specialists (lane conversations
7-11) implement against. It mirrors the *immutable published* contract from
``method-packs/hardtech-market-direction/1.1.0`` - it does not redefine or mutate
it:

* the untrusted model stage output shape (``strategic-lens-output`` schema);
* the split between model-writable fields and server-owned identity/provenance;
* the canonical five-lens set, order, owning worker, phase and trigger;
* the per-lens behavior contract each specialist must enforce.

Each specialist provides one :class:`LensImplementation` (prompt input assembly +
behavior validation) for a single ``lensType`` in ``strategic_lenses/lenses/`` on
their own branch. The Ways Coordinator owns this seam, the registry and the shared
persistence/report wiring; specialists never touch shared schema/migration/API.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.types import FULL_REQUIRED_STRATEGIC_LENSES, StrategicLensType

from .errors import ServerOwnedFieldError, UnknownLensType

# --- Version pins mirrored from the published pack (immutable) --------------------
METHOD_ID = "hardtech-market-direction"
METHOD_VERSION = "1.1.0"
LENS_OUTPUT_SCHEMA_ID = (
    "urn:ludus:method:hardtech-market-direction:strategic-lens-output:1.1.0"
)
# The schema pins ``sourceSkillVersion`` to this const.
SOURCE_SKILL_VERSION = "1.0.0"

# Model-writable top-level fields vs server-owned fields (manifest
# ``lens_artifact_contract``). A specialist that emits any server-owned field fails
# closed - the server injects identity, provenance, status, hash and timestamps.
ALLOWED_TOP_LEVEL_FIELDS: frozenset[str] = frozenset(
    {"lensType", "sourceSkillVersion", "phase", "references", "researchRequests", "content"}
)
FORBIDDEN_SERVER_OWNED_FIELDS: frozenset[str] = frozenset(
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
REFERENCE_KEYS: tuple[str, ...] = (
    "sourcePacketIds",
    "claimIds",
    "evidenceIds",
    "assumptionIds",
    "challengeIds",
)


@dataclass(frozen=True, slots=True)
class LensSpec:
    """Static, published contract facts for one lens."""

    lens_type: StrategicLensType
    phase: str
    owner_worker: str
    trigger: str
    prompt_ref: str
    content_def: str
    behavior_contract: str
    behavior_assertions: tuple[str, ...]
    required_focused: bool
    required_full: bool
    output_schema_id: str = LENS_OUTPUT_SCHEMA_ID
    source_skill_version: str = SOURCE_SKILL_VERSION


# Canonical five-lens registry. Behavior assertions are the exact acceptance bullets
# from 18-detailed-development-plan Task 10 and the manifest behavior contracts.
LENS_SPECS: dict[StrategicLensType, LensSpec] = {
    StrategicLensType.PORTER_FIVE_FORCES: LensSpec(
        lens_type=StrategicLensType.PORTER_FIVE_FORCES,
        phase="research_interpretation",
        owner_worker="research",
        trigger="after_research_packets_pass_information_gate",
        prompt_ref="prompts/lenses/porter-five-forces.md",
        content_def="porterContent",
        behavior_contract=(
            "per_market_boundary_then_five_forces_with_two_evidence_items_per_force_"
            "and_regulatory_complementor_correction"
        ),
        behavior_assertions=(
            "at_least_two_markets",
            "each_market_has_exactly_five_forces",
            "each_force_has_at_least_two_resolvable_evidence",
            "industry_boundary_change_trend_regulatory_and_complementors_present",
            "scoreIsNotDecisionFormula_is_true_and_score_does_not_decide",
        ),
        required_focused=False,
        required_full=True,
    ),
    StrategicLensType.PRE_MORTEM: LensSpec(
        lens_type=StrategicLensType.PRE_MORTEM,
        phase="adversarial_stress",
        owner_worker="critic",
        trigger="after_counterparty_matrix_for_current_preference_or_strongest_candidate",
        prompt_ref="prompts/lenses/pre-mortem.md",
        content_def="preMortemContent",
        behavior_contract=(
            "failure_is_assumed_complete_with_three_perspectives_five_causes_top_three_"
            "prevention_contingency_detection_and_verdict"
        ),
        behavior_assertions=(
            "exactly_three_perspectives_internal_external_systemic_hindsight",
            "at_least_five_failure_causes",
            "exactly_three_top_risks_with_unique_complete_cause_refs",
            "each_top_risk_has_prevention_contingency_detection_indicator",
            "explicit_verdict_and_rationale",
        ),
        required_focused=False,
        required_full=True,
    ),
    StrategicLensType.COUNTERPARTY_RESPONSE_MATRIX: LensSpec(
        lens_type=StrategicLensType.COUNTERPARTY_RESPONSE_MATRIX,
        phase="adversarial_stress",
        owner_worker="critic",
        trigger="after_safety_anchor_and_before_adversarial_review",
        prompt_ref="prompts/lenses/counterparty-response-matrix.md",
        content_def="counterpartyContent",
        behavior_contract=(
            "one_layer_only_with_no_action_baseline_optimal_worst_likely_responses_"
            "publication_test_and_reflexivity"
        ),
        behavior_assertions=(
            "one_to_two_key_actors",
            "two_to_three_actions_with_exactly_one_no_action",
            "response_depth_is_one_layer",
            "matrix_covers_optimal_worst_likely_window_gap_counterresponse",
            "publication_test_and_per_action_downside_asymmetry_and_reflexivity",
        ),
        required_focused=False,
        required_full=True,
    ),
    StrategicLensType.SCENARIO_PLANNING: LensSpec(
        lens_type=StrategicLensType.SCENARIO_PLANNING,
        phase="strategic_synthesis",
        owner_worker="synthesis",
        trigger="after_critic_packet_before_final_recommendation",
        prompt_ref="prompts/lenses/scenario-planning.md",
        content_def="scenarioPlanningContent",
        behavior_contract=(
            "three_or_four_structurally_distinct_scenarios_with_baseline_two_breaks_"
            "signals_and_at_least_one_killed_strategy"
        ),
        behavior_assertions=(
            "predetermined_elements_and_at_least_two_key_uncertainties",
            "exactly_two_axes",
            "three_to_four_scenarios_exactly_one_baseline_at_least_two_structural_breaks",
            "each_scenario_has_timeline_three_stakeholder_states_and_three_to_five_signals",
            "each_strategy_tested_and_at_least_one_result_is_killed",
        ),
        required_focused=False,
        required_full=True,
    ),
    StrategicLensType.MEADOWS_LEVERAGE_POINTS: LensSpec(
        lens_type=StrategicLensType.MEADOWS_LEVERAGE_POINTS,
        phase="strategic_synthesis",
        owner_worker="synthesis",
        trigger="after_scenario_planning_before_final_action_path",
        prompt_ref="prompts/lenses/meadows-leverage-points.md",
        content_def="meadowsContent",
        behavior_contract=(
            "system_map_three_or_more_levels_high_leverage_gap_runaway_reinforcing_loop_"
            "risk_and_intervention_sequence"
        ),
        behavior_assertions=(
            "system_map_covers_boundary_goals_stocks_flows_loops_delays_actors_rules",
            "covers_at_least_three_leverage_levels",
            "at_least_one_ignored_high_leverage_gap_level_one_to_four",
            "at_least_one_runaway_reinforcing_loop",
            "non_empty_intervention_sequence_and_risk_tradeoffs",
        ),
        required_focused=False,
        required_full=True,
    ),
}


def lens_spec(lens_type: StrategicLensType) -> LensSpec:
    try:
        return LENS_SPECS[lens_type]
    except KeyError as exc:
        raise UnknownLensType(f"unknown lens type: {lens_type!r}") from exc


@dataclass(frozen=True, slots=True)
class LensRequest:
    """Stable input handed to a lens implementation.

    ``run_context`` pins tenant/run/method; the ref tuples resolve against the
    frozen run only. ``upstream_lens_outputs`` carries the validated content of
    lenses this lens depends on (e.g. counterparty before pre-mortem, scenario
    before meadows), never another workspace or another run.
    """

    lens_type: StrategicLensType
    workspace_id: str
    analysis_run_id: str
    prompt_text: str
    research_packet_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    claim_refs: tuple[str, ...] = ()
    assumption_refs: tuple[str, ...] = ()
    challenge_refs: tuple[str, ...] = ()
    option_ids: tuple[str, ...] = ()
    upstream_lens_outputs: Mapping[StrategicLensType, Mapping[str, Any]] = field(
        default_factory=dict
    )


@dataclass(frozen=True, slots=True)
class LensPromptInputs:
    """What a lens implementation assembles for the model call."""

    system: str
    user: str
    schema_content_def: str


@dataclass(frozen=True, slots=True)
class StrategicLensStageOutput:
    """The untrusted model stage output (model-writable fields only).

    Server-owned identity/provenance fields are injected later; :func:`from_payload`
    rejects any attempt by the model to set them.
    """

    lens_type: StrategicLensType
    source_skill_version: str
    phase: str
    references: Mapping[str, Sequence[str]]
    research_requests: Sequence[Mapping[str, Any]]
    content: Mapping[str, Any]

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "StrategicLensStageOutput":
        assert_no_server_owned_fields(payload)
        extra = set(payload) - ALLOWED_TOP_LEVEL_FIELDS
        if extra:
            raise ServerOwnedFieldError(tuple(sorted(extra)))
        return cls(
            lens_type=StrategicLensType(payload["lensType"]),
            source_skill_version=str(payload["sourceSkillVersion"]),
            phase=str(payload["phase"]),
            references=dict(payload["references"]),
            research_requests=list(payload["researchRequests"]),
            content=dict(payload["content"]),
        )


@dataclass(frozen=True, slots=True)
class LensBehaviorReport:
    """Result of a lens behavior check. ``ok=False`` fails the run closed."""

    lens_type: StrategicLensType
    ok: bool
    reason_codes: tuple[str, ...] = ()
    findings: tuple[str, ...] = ()


def assert_no_server_owned_fields(payload: Mapping[str, Any]) -> None:
    """Reject model output that tries to set any server-owned field."""

    present = FORBIDDEN_SERVER_OWNED_FIELDS & set(payload)
    if present:
        raise ServerOwnedFieldError(tuple(sorted(present)))


@runtime_checkable
class LensImplementation(Protocol):
    """The seam each lens specialist implements for exactly one lens type."""

    lens_type: StrategicLensType

    def build_prompt_inputs(self, request: LensRequest) -> LensPromptInputs: ...

    def validate_behavior(
        self, output: StrategicLensStageOutput
    ) -> LensBehaviorReport: ...


class LensRegistry:
    """Registry of the five lens implementations, guarding the exact set."""

    def __init__(self) -> None:
        self._impls: dict[StrategicLensType, LensImplementation] = {}

    def register(self, impl: LensImplementation) -> None:
        lens_type = impl.lens_type
        if lens_type not in LENS_SPECS:
            raise UnknownLensType(f"unknown lens type: {lens_type!r}")
        if lens_type in self._impls:
            raise ValueError(f"lens already registered: {lens_type}")
        self._impls[lens_type] = impl

    def get(self, lens_type: StrategicLensType) -> LensImplementation:
        try:
            return self._impls[lens_type]
        except KeyError as exc:
            raise UnknownLensType(f"no implementation for lens: {lens_type!r}") from exc

    def registered(self) -> frozenset[StrategicLensType]:
        return frozenset(self._impls)

    def require_full_set(self) -> None:
        """Fail closed unless all five canonical lenses are registered."""

        missing = set(FULL_REQUIRED_STRATEGIC_LENSES) - set(self._impls)
        if missing:
            raise UnknownLensType(
                f"missing lens implementations for full delivery: {sorted(missing)}"
            )
