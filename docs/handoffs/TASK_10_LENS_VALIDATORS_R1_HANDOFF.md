# TASK 10 LENS VALIDATORS R1 HANDOFF

- Lane: Task 10 precursor - five strategic lens behavior validators (pure functions only)
- Role: Ways/Agent-Pipeline Owner (Fable5)
- Branch: `codex/task-10-lens-validators-r1`
- Base: `51ae45c900ae4efa01b72d5d6842adb74ad50c91` (live `git ls-remote origin refs/heads/main`
  at Gate 0; exact match with the authorized `51ae45c` baseline - **no deviation**)
- Date: 2026-07-25 (Asia/Shanghai)
- ready_for_qa: **YES**

## 1. Scope actually delivered

| Path | Change |
|---|---|
| `services/api/app/strategic_lenses/validators.py` | NEW - Task 10 Step 5 pure behavior validators for the canonical five lenses |
| `services/api/tests/test_strategic_lens_validators.py` | NEW - 67 tests: 1 complete positive sample per lens (pack-schema-checked) + >=1 negative per behavior assertion + validator-surface tests |
| `docs/handoffs/TASK_10_LENS_VALIDATORS_R1_HANDOFF.md` | NEW - this handoff |
| `HEAD` / `HISTORY` | lifecycle (kickoff archive + completion flip), append-only |

Zero migration / zero DB / zero route / zero worker / zero contract-surface change, as
tasked. Forbidden territories untouched (`app/evidence|analyses|workers|connectors`,
`app/simulations`, migrations, routes, existing repository/service files, `apps/web`,
`packages/contracts`).

## 2. Consumed read-only inputs

- `docs/product-plan/18-detailed-development-plan.md` Task 10 Step 5 behavior table
  (L1068-L1078), executed verbatim (assertion matrix in section 5).
- **CCR-20260725-ANALYSIS-01**: NOT on main at Gate 0. Consumed read-only via
  `git show` from the contract lane branch `codex/ccr-guest-analysis-contracts`,
  exact SHA **`d6675693fd2b7709d9ed4756489e633c49c869ee`** (branch tip; the CCR file was
  introduced by commit `5ffccf8` on that branch, unchanged at the tip). Applied rulings:
  section 4.4 (per-lens behavior validators belong to the method-pack/ways stage-output
  contract owned by Task 10, not the HTTP wire contract; wire-level exact-set gate +
  `STRATEGIC_LENS_INCOMPLETE` stay with 10-api), section 5 (no new HTTP error codes
  invented here; the two verbatim lower-snake SIM codes untouched).
- `06-data-model.md` lens sections, `app/models.py` canonical `StrategicLensArtifact`
  ORM, `app/strategic_lenses/**` existing code (audited first - see section 3),
  `app/types.py` as sole enum authority (`StrategicLensType`,
  `FULL_REQUIRED_STRATEGIC_LENSES` imported, never redeclared).
- Fixtures: `fixtures/spherical-robot/expected/strategic-lenses/{pre_mortem,counterparty_response_matrix}.json`
  reused as the positive samples for those two lenses (read-only).

## 3. Audit result: schema gap fill = NONE (schemas.py not created)

Audit of the wire schema surface before writing any code:

- All five canonical lens content schemas already exist in the immutable published pack
  `method-packs/hardtech-market-direction/1.1.0/schemas/strategic-lens-output.schema.json`
  `$defs`: `porterContent`, `preMortemContent`, `counterpartyContent`,
  `scenarioPlanningContent`, `meadowsContent` (schema id
  `urn:ludus:method:hardtech-market-direction:strategic-lens-output:1.1.0`).
- The meadows lane additionally ships a canonical pydantic mirror
  (`MeadowsContent`/`MeadowsStageOutput` in
  `app/strategic_lenses/lenses/meadows_leverage_points.py`).
- `app/strategic_lenses/schemas.py` does not exist on main and creating it would have
  parallel-defined already-published types, which the task forbids.

**Conclusion: zero missing lens content schemas; no schemas.py written. Schema 补齐项: 无.**

## 4. Validator design (validators.py)

- One pure function per lens, uniform signature:
  `validate_<lens>(content: Mapping, references: ResolvedLensReferences) -> LensBehaviorValidationResult`,
  plus the dispatch table `LENS_BEHAVIOR_VALIDATORS` and `validate_lens_behavior(...)`
  (fails closed with `UnknownLensType` outside the canonical five).
- Input = canonical content instance + run-resolved references
  (`ResolvedLensReferences.from_wire/to_wire` round-trips the canonical camelCase block).
  Per Task 10 Step 7 the repository resolves references BEFORE validation; validators only
  check content citations stay inside the resolved sets.
- Output = structured result: `passed` / deduped stable `reason_codes` + `findings` +
  `repair_input` (`LensRepairInput`: lens type, owner worker, phase, failed codes,
  findings, the frozen resolved references). The repair input routes regeneration to the
  producing worker and NEVER carries repaired or completed content - "Validation 不得补写"
  is structural: there is no code path that writes content.
- Layering: JSON shape is owned by the published pack schema upstream; each validator
  re-runs the lane-owned deterministic behavior gate on top, so schema-pass /
  behavior-fail is always judged a failure (explicit layering tests:
  `test_schema_pass_but_behavior_fail_is_rejected` for porter + scenario). The meadows
  validator defensively revalidates the canonical pydantic mirror, so shape gaps also
  fail closed there (stable `schema:<path>` codes).
- Behavior logic is delegated to the already-shipped lane gates
  (porter/scenario lens classes, `validate_pre_mortem_output`,
  `validate_counterparty_content`, `validate_meadows_stage_output`) - single source of
  truth, no parallel re-implementation, codes stay stable.
- Deterministic, no I/O, no mutation of inputs (tested).

## 5. Assertion coverage matrix (plan L1072-L1076, verbatim)

Positive samples: `TestPorterFiveForces::test_positive_sample_passes`,
`TestPreMortem::test_positive_sample_passes`,
`TestCounterpartyResponseMatrix::test_positive_sample_passes`,
`TestScenarioPlanning::test_positive_sample_passes`,
`TestMeadowsLeveragePoints::test_positive_sample_passes` - each positive payload is also
validated against the published pack JSON schema in the same test.
Negative tests below are the parametrized `test_negative_sample_fails[...]` cases
(parameter id = reason code / mutation shown).

### porter_five_forces
| Assertion | Negative sample(s) -> reason code |
|---|---|
| >=2 markets | `fewer_than_two_markets` |
| every market exactly the five canonical forces | `missing_canonical_force` |
| every force >=2 resolvable Evidence | `force_evidence_below_minimum`; `force_evidence_not_in_references` |
| industry boundary present/complete | `industry_boundary_incomplete` |
| direction of change / trend | `changing_trend_missing` |
| regulatory | `regulatory_assessment_missing` |
| complementors | `complementors_missing` |
| `scoreIsNotDecisionFormula == true`, score never decides | `score_presented_as_decision_formula`; layering test -> `average_score_is_not_descriptive_mean` |

### pre_mortem
| Assertion | Negative sample(s) -> reason code |
|---|---|
| exactly internal/external/systemic_hindsight | `pre_mortem_perspective_set` |
| >=5 failure causes | `pre_mortem_cause_count` |
| topRisks exactly 3 | `pre_mortem_top_risk_count` |
| rank refs unique/complete | `pre_mortem_top_risk_rank_duplicate` |
| cause refs unique/complete | `pre_mortem_top_risk_cause_ref`; `pre_mortem_top_risk_cause_duplicate` |
| each top risk prevention/contingency/detectionIndicator | `pre_mortem_top_risk_control_missing` |
| explicit verdict | `pre_mortem_verdict` |
| explicit rationale | `pre_mortem_verdict_rationale` |

### counterparty_response_matrix
| Assertion | Negative sample(s) -> reason code |
|---|---|
| 1-2 key actors | `one_to_two_key_actors` (third actor) |
| 2-3 actions, exactly one `no_action` | `two_to_three_actions_with_exactly_one_no_action` (fourth action; no_action removed) |
| response depth one layer | `response_depth_is_one_layer` |
| matrix covers optimal/worst/likely/window/gap/counterresponse | `matrix_covers_optimal_worst_likely_window_gap_counterresponse` (missing pair) |
| publication test + per-action downside asymmetry + reflexivity warning | `publication_test_and_per_action_downside_asymmetry_and_reflexivity` (blank publication field; missing downside action; blank reflexivity) |
| (lane discipline) core assumptions resolved | `core_assumptions_must_be_registered_references` (`test_unresolved_core_assumption_fails`) |

### scenario_planning
| Assertion | Negative sample(s) -> reason code |
|---|---|
| predetermined elements present | `predetermined_elements_missing` |
| >=2 key uncertainties | `key_uncertainties_insufficient` |
| exactly 2 axes | `axes_count_not_two` |
| 3-4 scenarios | `scenario_count_out_of_range` |
| exactly 1 baseline | `baseline_count_not_one` |
| >=2 structural breaks | `structural_breaks_insufficient` |
| per-scenario timeline | `timeline_turning_points_insufficient` |
| >=3 stakeholder states | `stakeholder_states_insufficient` |
| 3-5 early signals | `early_signals_out_of_range` |
| every strategy tested in every frame | `strategy_matrix_incomplete` |
| >=1 result `killed` | `no_strategy_killed` (+ layering test) |

### meadows_leverage_points
| Assertion | Negative sample(s) -> reason code |
|---|---|
| system map full coverage (boundary/goals/stocks/flows/reinforcing/balancing/delays/actors/rules) | `schema:content.systemMap.*` via `test_shape_gap_fails_closed[systemMap]` (coverage is locked into the canonical shape mirror; validator fails it closed) |
| >=3 leverage levels | `interventions_cover_fewer_than_three_levels` (behavior-only rebuild) |
| >=1 ignored level 1-4 high-leverage gap | `schema:content.highLeverageGaps` (empty gaps fail closed) |
| >=1 runaway reinforcing loop | `schema:content.runawayPositiveLoops` |
| non-empty intervention sequence | `schema:content.interventionSequence` |
| non-empty risk tradeoffs | `schema:content.riskTradeoffs` |
| (lane discipline) levelsCovered consistency / sequence integrity | `levels_covered_mismatch`; `sequence_references_unknown_intervention` |

Cross-cutting: `TestValidatorSurface` covers dispatch-table exactness, dispatcher routing,
`UnknownLensType` fail-closed, non-object content (`lens_content_not_object`, all five),
repair-input structure (producer routing + frozen references, no content member),
input immutability, determinism, and reference wire round-trip.

## 6. Reason code catalog (for contract-lane adoption)

Style: lower_snake, aligned with the fail-closed precedent
(`score_constraint_operator_unsupported` style). All codes are emitted by
`validators.py`; per CCR-20260725-ANALYSIS-01 section 4.4 they live in the
method-pack/ways stage-output contract, NOT the HTTP error table.

**Validator layer (new in this lane):**
`lens_content_not_object`. (Unknown lens type raises `UnknownLensType`, runtime code
`unknown_lens_type` - pre-existing.)

**porter_five_forces (pass-through from the shipped lane gate):**
`fewer_than_two_markets`, `duplicate_market_option`, `market_analyses_missing`,
`market_analysis_not_object`, `industry_boundary_missing`,
`industry_boundary_incomplete`, `forces_missing`, `force_not_object`,
`missing_canonical_force`, `duplicated_force`, `non_canonical_sixth_force`,
`threat_score_not_ordinal_1_to_5`, `average_score_is_not_descriptive_mean`,
`changing_trend_missing`, `regulatory_assessment_missing`, `complementors_missing`,
`force_evidence_missing`, `force_evidence_below_minimum`,
`force_evidence_not_in_references`, `force_key_indicators_missing`,
`force_reasoning_missing`, `cross_market_comparison_missing`,
`strategic_implications_missing`, `strategic_implication_not_object`,
`implication_logic_missing`, `implication_conditions_missing`,
`fake_probability_language`, `score_presented_as_decision_formula`.
(`lens_type_mismatch`, `wrong_phase`, `wrong_source_skill_version` are unreachable via
validators.py - the envelope is synthesized from the published spec.)

**pre_mortem (deterministic projection of the shipped `PM_*` lane codes:**
`pre_mortem_` + lowercase suffix, total, no hand-maintained table; exposed as
`normalize_pre_mortem_code`)**:**
`pre_mortem_evidence_assumption_overlap`, `pre_mortem_ungrounded`,
`pre_mortem_horizon`, `pre_mortem_failure_statement`, `pre_mortem_perspective_set`,
`pre_mortem_cause_count`, `pre_mortem_cause_shape`, `pre_mortem_cause_id`,
`pre_mortem_cause_id_duplicate`, `pre_mortem_label_only_cause`,
`pre_mortem_no_downstream`, `pre_mortem_probability_smuggling`,
`pre_mortem_risk_arithmetic`, `pre_mortem_perspective_coverage`,
`pre_mortem_top_risk_count`, `pre_mortem_top_risk_shape`, `pre_mortem_top_risk_rank`,
`pre_mortem_top_risk_rank_duplicate`, `pre_mortem_top_risk_cause_ref`,
`pre_mortem_top_risk_cause_duplicate`, `pre_mortem_top_risk_control_missing`,
`pre_mortem_top_risk_control_duplicated`, `pre_mortem_top_risk_not_highest`,
`pre_mortem_verdict`, `pre_mortem_verdict_rationale`,
`pre_mortem_missing_evidence_list`, `pre_mortem_fatal_cause_averaged_away`.
(Projections of `PM_LENS_TYPE`, `PM_PHASE`, `PM_MODEL_SELF_REPORTED_IDENTITY`,
`PM_REFERENCES`, `PM_CONTENT`, `PM_UNKNOWN_EVIDENCE_ID`, `PM_UNKNOWN_ASSUMPTION_ID`
exist mechanically but are unreachable via validators.py: envelope/references are
synthesized from spec + resolved sets. The lane's own adapter surface continues to emit
the original `PM_*` codes unchanged - no shipped code was renamed.)

**counterparty_response_matrix (pass-through):**
`one_to_two_key_actors`, `two_to_three_actions_with_exactly_one_no_action`,
`response_depth_is_one_layer`,
`matrix_covers_optimal_worst_likely_window_gap_counterresponse`,
`publication_test_and_per_action_downside_asymmetry_and_reflexivity`,
`core_assumptions_must_be_registered_references`.

**scenario_planning (pass-through):**
`predetermined_elements_missing`, `key_uncertainties_insufficient`,
`uncertainty_id_duplicate`, `content_evidence_not_declared`, `axes_count_not_two`,
`axis_uncertainty_ref_unresolved`, `axis_not_high_impact_high_uncertainty`,
`axes_not_distinct`, `scenario_count_out_of_range`, `baseline_count_not_one`,
`structural_breaks_insufficient`, `scenario_id_duplicate`,
`scenario_axis_states_not_distinct`, `timeline_turning_points_insufficient`,
`stakeholder_states_insufficient`, `early_signals_out_of_range`, `signal_id_duplicate`,
`strategy_test_scenario_unresolved`, `strategy_test_duplicate`,
`trigger_signal_unresolved`, `strategy_matrix_incomplete`, `no_strategy_killed`,
`killed_flag_not_true`, `monitoring_actions_missing`, `irreducible_unknowns_missing`,
`probability_language_present`.

**meadows_leverage_points (pass-through):**
behavior codes `duplicate_intervention_id`,
`interventions_cover_fewer_than_three_levels`, `levels_covered_mismatch`,
`sequence_references_unknown_intervention`, `sequence_orders_not_dense_ascending`,
`transcend_paradigms_unpaired`, `unanchored_evidence_and_assumptions`; defensive shape
layer `schema:<json-path>` (path-stable) and
`server_identity_self_reported:<field>` (unreachable via validators.py).

## 7. Acceptance gate results

- New test file: `pytest tests/test_strategic_lens_validators.py -q -W error -rxX` =
  **67 passed / 0 failed** (no DB, no network).
- Opening baseline (recorded BEFORE any code, fresh disposable PG16 `ludus-pg-task10`
  @55446, `alembic upgrade head` + `alembic check` clean):
  `pytest tests app/simulations/tests -q -W error -rxX` = **482 passed**.
- Closing full run, same command/DB: **549 passed / 0 failed / 0 xfailed / 0 xpassed** =
  482 baseline + 67 new, **zero regression**.
- `ruff check services/api`: 1 finding - pre-existing `F401` in
  `services/api/tests/test_sim_02a_profile_idempotency_qa.py:41` (file byte-identical to
  base `51ae45c`, QA-owned, outside this lane's write scope; surfaced by ruff 0.15.22 -
  disclosed, not fixed here). Both lane-owned files: **All checks passed**.
- `compileall` over `services/api/app` + `services/api/tests`: exit 0.
- Official `scripts/generate_contracts.ps1 -Check`: **CONTRACT_DRIFT_OK** (no contract
  surface change in this lane).
- Scope gate: `git diff --name-only 51ae45c..HEAD` = exactly `HEAD`, `HISTORY`,
  `services/api/app/strategic_lenses/validators.py`,
  `services/api/tests/test_strategic_lens_validators.py` (+ this handoff in the closure
  commit). Conflict-marker scan clean; secret scan of the full diff clean (no
  credentials recorded anywhere).

## 8. Known limits

- validators.py judges content + resolved references only; envelope discipline
  (server-owned field rejection, phase/skill-version pins) remains with the shared seam
  (`StrategicLensStageOutput.from_payload`) and the repository write path - unchanged.
- Reference *resolution* against the frozen Run (DB) is Task 10 Step 7 repository work
  (blocked on Task 9), not this lane; validators assume already-resolved sets.
- Meadows system-map coverage, gap/loop/sequence non-emptiness are enforced through the
  canonical shape mirror (stable `schema:<path>` codes) rather than bespoke behavior
  codes - consistent with the shipped meadows lane and still fail-closed here.
- The pre-existing ruff `F401` in the SIM-02A QA suite needs a QA-lane fast fix; it is
  not touched here to respect file ownership.
- No wiring into the quality gate / worker pipeline yet (hard Task 9 dependency, next
  lane); nothing imports validators.py in product code paths yet by design.

No credentials or secret values are recorded in this handoff.
