# CCR Guest-Analysis Contracts Handoff

- Lane: Contract/Mainline Lead — contracts function only (NO mainline merge performed here)
- Branch: `codex/ccr-guest-analysis-contracts` (pushed)
- Base: `bd9fde15278afd63d351b2adaeb95ec32441cd6f`
  - Gate-zero live `git ls-remote origin refs/heads/main` = `bd9fde15278afd63d351b2adaeb95ec32441cd6f`
    — EQUAL to the authorized baseline at lane start.
  - **Mid-lane disclosure (post-delivery re-read):** main advanced DURING this lane to
    `51ae45c900ae4efa01b72d5d6842adb74ad50c91` (SIM alpha / Guest Demo wave publication).
    old_remote_main_sha: `bd9fde15278afd63d351b2adaeb95ec32441cd6f`;
    new_remote_main_sha: `51ae45c900ae4efa01b72d5d6842adb74ad50c91`.
    `bd9fde15` IS an ancestor of the new main (the wave explicitly adopted it), and the
    new-main delta touches NO canonical contract doc (no `docs/product-plan/**` path) — the
    only path overlap with this lane is HEAD/HISTORY (append-only worklogs). This lane is
    docs-only, so per protocol it did not stop; the branch merges cleanly onto the new main.
  - Integration note: the new main already ships a DIFFERENT
    `apps/web/lib/demo/simulationDemo.ts` + `/demo` page from `codex/prototype-sim-web`
    (env-fixture based, NO guest endpoint usage); the guest endpoint exists only on the two
    in-flight branches. Relevant context for the Release Owner's upcoming shape decision.
- Date: 2026-07-25 (Asia/Shanghai)
- Scope proof target: `git diff --name-only <base>..HEAD` contains ONLY
  `docs/product-plan/docs/contract-changes/**`, the CCR-authorized subsections of
  `docs/product-plan/06-data-model.md` + `docs/product-plan/10-api-and-events.md`,
  `docs/handoffs/**`, `HEAD`, `HISTORY`. Zero product code, zero migrations, zero tests.

## Delivery A — CCR-20260725-GUEST-01 (WITHDRAWN — rescinded by principal directive)

- File: `docs/product-plan/docs/contract-changes/CCR-20260725-GUEST-01.md`, now
  `Status: withdrawn`.
- Directive (2026-07-25, after the original push at `21bbeff`): this lane must NOT
  independently adjudicate the guest endpoint shape. New binding process:
  1. WAIT for the Guest Demo integration report;
  2. the wave's **Release Owner decides** the authoritative shape there;
  3. this lane (or successor) transcribes that decision VERBATIM into
     `CCR-20260725-GUEST-02` — a transcription-only archival record, zero re-derivation.
- As of this handoff no Guest integration report exists on `origin/main` (checked
  `docs/handoffs/` tree at `51ae45c9`), so the transcription target does not exist yet and
  GUEST-02 is intentionally NOT created.
- What survives in GUEST-01: the verbatim source-shape extractions (Evidence E1–E3: seed
  flat envelope @ 3278dd80, web nested-`fixture` assumption @ d504b4f0, canonical envelope
  precedents) remain valid factual reference for the Release Owner. The "Adjudication" /
  "fix instructions" sections are marked RESCINDED and carry no authority.
- ready_for_consumption: **NO** — nobody implements against GUEST-01; wait for the Release
  Owner decision + GUEST-02 transcription.

## Delivery B — CCR-20260725-ANALYSIS-01 (Task 9/10 wire pre-freeze)

- File: `docs/product-plan/docs/contract-changes/CCR-20260725-ANALYSIS-01.md`
  (ready_for_consumption: YES for Task 9 Phase B / Task 10 kickoff).
- Frozen items:
  1. Charter (`draft/awaiting_confirmation/confirmed/superseded`) + Run (11 canonical
     values, `types.py` sole authority) transition matrices; 06 vs 18 Task 9 wording check =
     no substantive divergence; two NEW cells adjudicated: strict linear six-stage order (no
     skipping, focused included) and `ready`/`blocked` enterable ONLY from `validating`.
  2. RunResolution: closed 3-kind union (`source_conflict` / `hard_constraint_confirmation` /
     `provider_recovery`) with exact payload schemas; Idempotency-Key replay semantics;
     amendment boundary — classification first, `changedFrozenFields != []` ⇒ NO resolution
     row + `409 RUN_AMENDMENT_REQUIRED` with frozen details keys
     `{ changedFrozenFields, replacementUrl }` (NEW key name `replacementUrl`).
  3. AnalysisEvent: 5 categories + closed 20-value `type` union (lifecycle ledger events are
     NOT AnalysisEvent types); envelope fields; NEW explicit ruling — `sequence` strictly
     increasing per `analysisRunId`, gaps allowed; SSE `id:`=event id, `event:`=category,
     `data:`=full envelope, `Last-Event-ID` resolves to persisted sequence;
     `strategic_lens.completed` payload frozen as
     `{ lensArtifactId, lensType, producerRole, referenceCounts, contentHash }` (NEW:
     `referenceCounts` key + emit-only-after-artifact-commit timing).
  4. Five-lens linkage: focused = empty set, full = exact `FULL_REQUIRED_STRATEGIC_LENSES`
     canonical order; `strategicLensArtifactIds` population; producer mapping; Task 10
     quality-gate ownership split (wire exact-set gate = 10-api
     `STRATEGIC_LENS_INCOMPLETE`; behavior validators = method-pack/ways schema contract;
     DB invariants = CCR-20260724-Ways-01, already live).
  5. Error codes: full reaffirmed table + ONE new reserved code
     `ANALYSIS_TRANSITION_INVALID` (409, backstop only); post-cancel publication uses
     existing `REPORT_PUBLICATION_BLOCKED`/`EXPORT_NOT_ALLOWED`, no new code.
- IMPLEMENTATION_FREE items (deliberately not frozen): Charter
  `draft → awaiting_confirmation` trigger mechanics; worker claim primitive / heartbeat
  interval / progress granularity; Idempotency-Key format details; sequence storage
  mechanism and gap-freeness; SSE keep-alive/retry/buffering; additive payload keys on
  non-lens event types; extra sanitized `details` members; all prompt/stage/provider
  internals.
- Canonical text syncs performed in this commit, verbatim per CCR §7: S1 (06 state
  paragraph), S2 (10-api lens event sentence), S3 (10-api error table row), S4 (10-api
  amendment details), S5 (10-api SSE sequence sentence). Nothing else touched in those docs.

## Read-only inputs consumed (never merged/cherry-picked)

- `codex/prototype-web-demo` @ `d504b4f0c204940edf6cd1f3b8d44f114f32e1bb` (git show only)
- `codex/prototype-guest-seed-smoke` @ `3278dd809c1c30103e6949d9aef9f85a49a61b73` (git show only)
- `codex/prototype-run-api` @ `56e01abd49adaa119dd296d70e6d59c67537a199` (git show only)
- Canonical docs 06/08/10/18/26 + `services/api/app/types.py` at base `bd9fde15`
- CCR precedents: Ways-01, SIM-01 + Addendum A1, SIM-02A + Addendum A1, ENG-02 (+A1)

## Gates

- docs-only diff proof (only the 7 authorized paths), `git diff --check` clean,
  conflict-marker scan clean, HISTORY strictly append-only (numstat 25/0), secret scan: the
  single pattern hit is an INHERITED historical HISTORY line (a backup file path reference
  from the 2026-07-22 Gate 1 record; contains no credential value and predates this lane);
  no file written by this lane contains any key/credential/env value.
- This lane did NOT advance main, did NOT rebase/amend/force-push, and carried NO code from
  the in-flight branches.

## Consumers

- Guest Demo integration wave / Release Owner: decide the guest endpoint shape in the
  integration report; GUEST-01's Evidence section is your verbatim source-of-record for both
  sides' actual shapes. This lane transcribes your decision into CCR-20260725-GUEST-02.
- Fable5 (Task 9 Phase B) and ways_agent_pipeline (Task 10): implement against
  CCR-20260725-ANALYSIS-01; deviations require an addendum BEFORE code diverges.

No credentials or secret values are recorded here.
