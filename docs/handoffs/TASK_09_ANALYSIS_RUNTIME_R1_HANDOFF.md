# TASK 09 — Persistent Deep Analysis State Machine & Worker (r1) Handoff

- Role: Case/API/Data Owner (Fable5); lane = Task 9 (Phase B) of the deep
  research pipeline backend; Phase A (Task 8) shipped at
  `c599030a54db591528bf9e7b62850e5869c686e2`.
- Branch: `codex/task-09-analysis-runtime-r1`, fresh worktree
  `decision-lab-task09-runtime`; **parent = the Phase A exact SHA** (task-order
  mandated serial chain). No rebase/amend/force-push/cherry-pick; main untouched.
- Base disclosure: the lane base is the authorized main
  `bd9fde15278afd63d351b2adaeb95ec32441cd6f` (exact ls-remote match at Gate 0).
  Remote main advanced mid-lane to `51ae45c9` (guest demo wave). Deviation
  check recorded in HISTORY: `bd9fde1` IS an ancestor of `51ae45c9` and
  `git diff bd9fde1..51ae45c9 -- services/api/app/evidence services/api/app/analyses
  services/api/app/workers services/api/app/connectors` is EMPTY — the wave does
  not touch this lane's surfaces, the pinned base stays legitimate.
- Plan basis: 18-detailed-development-plan.md Task 9 (L951-1018); manifest
  task-09 write scope (`app/analyses/**` + `app/workers/analysis_worker.py`).
- Canonical contracts consumed read-only: 06-data-model.md (AnalysisCharter /
  AnalysisRun / AnalysisEvent / ResearchPacket / RunInterventionClassification /
  RunResolution / RunManifest), 10-api-and-events.md (SSE + resolutions/cancel +
  error codes), 08-deep-research-pipeline.md, 26-invariants; `app.types`
  enums imported only (`AnalysisRunStatus`, `FormalAnalysisLevel`,
  `OriginMode`); pre-existing `analysis_runs` / `strategic_lens_artifacts` ORM
  (contract_lead) consumed as-is, never modified.

## 1. Delivered files

Product (task-09 write scope):

- `app/analyses/models.py` — ORM: `analysis_charters` (frozen-contract charter
  with DB CHECK "focused lens set empty / full = exactly 5"),
  `analysis_events` (per-run strictly increasing `sequence`,
  UNIQUE(workspace, run, sequence)), `research_packets` (role PG enum),
  `run_intervention_classifications` (resolution XOR amendment CHECK),
  `run_resolutions` (three canonical payload kinds + resumable-stage CHECK);
  plus the canonical partial unique index
  `uq_analysis_runs_one_active_per_case` ATTACHED to the pre-existing
  `analysis_runs` table metadata (app/models.py untouched).
- `app/analyses/state_machine.py` — pure legality gates: Run machine
  (queued → six sequential stages → validating → ready|blocked; every
  executing stage → needs_attention|cancelled; needs_attention resumes ONLY
  to the persisted lastResumableStage; ready only from validating AND quality
  gate passed; blocked only from validating; terminals never transition;
  queued never a target), Charter machine (draft → awaiting_confirmation →
  confirmed → superseded), `normalize_lens_set` (focused=[] / full=exact
  five-set canonical order), `diff_frozen_fields` (canonical
  CharterFrozenField names).
- `app/analyses/repository.py` — durable operations: charter lifecycle
  (confirm freezes; replacement draft; replacement confirm atomically
  supersedes the old charter AND cancels its active run with
  `charter_replaced` + `supersededBy/supersedes` linkage); queued-run creation
  (confirmed && formalAnalysisAllowed only; same idempotency key = replay,
  different key while active = `ANALYSIS_RUN_ALREADY_ACTIVE` with
  existingAnalysisRunId, DB partial unique as the backstop); every transition
  locks the row, writes `analysis_events` + stage input/output hashes into
  `stage_results`; `claim_next_queued` (FOR UPDATE SKIP LOCKED, optional
  workspace filter); heartbeat; idempotent cooperative `cancel` (canonical
  terminal, ready/blocked guarded); `recover_stale_runs` (expired heartbeat →
  needs_attention with lastResumableStage); `classify_and_resolve`
  (classification-first; three canonical kinds; provider_recovery restricted
  to charter allowlist; ANY frozen-field change — lens set included — persists
  an amendment classification and raises RUN_AMENDMENT_REQUIRED, never a
  RunResolution).
- `app/analyses/routes.py` — relative UNMOUNTED router: SSE
  `GET .../analyses/{analysisRunId}/events` (`event:` = canonical category,
  `data:` = full AnalysisEvent envelope, `id:` = event id, `Last-Event-ID`
  replays from the persisted sequence, stream ends at terminal states),
  `POST .../resolutions`, `POST .../cancel`; uniform CASE_NOT_FOUND
  anti-enumeration.
- `app/workers/analysis_worker.py` — DB-queue worker: claim → heartbeat →
  stage pipeline with persisted cancellation checks at every stage boundary
  AND around every external call; four role executors (fixture/stub providers
  in this lane); Critic always runs the mandatory Safety Anchor sub-stage
  first (focused AND full); Validation validates and blocks ONLY; full runs
  schedule the five lens stages (research→porter;
  critic→counterparty,pre_mortem; synthesis→scenario,meadows) through the
  SHIPPED lens write path (`app.strategic_lenses.repository.
  persist_lens_stage_output` / `apply_validation_verdict` — imported, never
  copied; identity asserted in tests) and record
  `strategicLensArtifactIds`; focused runs skip all lens stages and keep the
  array empty; `strategic_lens.completed` events are emitted only after the
  write path reports persistence.
- `migrations/versions/f9a4b7e2c8d3_add_analysis_runtime.py` — the single
  forward migration of this phase (down_revision `e7f3a2c9d5b1`).
- `migrations/env.py` — +4 disclosed lines registering `app.analyses.models`
  (same pattern as the Phase A/evidence registration).

Own tests (`app/analyses/tests/`, new directory):

- `test_analysis_state_machine.py` (67) — full legal-path matrix, exhaustive
  illegal transitions (incl. the plan's synthesizing→ready case, terminals ×
  targets grid, stage skipping/backwards, blocked-only-from-validating,
  resume-to-wrong-stage), charter lifecycle edges, focused/full lens-set
  normalization (partial/duplicate/foreign sets fail closed), frozen-field
  diffs.
- `test_analysis_runtime_repository.py` (20) — confirmed-charter immutability,
  DB lens-set CHECK negatives, confirmed+formalAnalysisAllowed run gate,
  idempotent replay vs ANALYSIS_RUN_ALREADY_ACTIVE, partial-unique catalog
  assertion, replacement-confirm supersede + charter_replaced cancel, event
  sequence monotonicity + DB uniqueness + stage hashes, invalid transition
  writes nothing, cancel idempotency + terminal guards, resolution resumes to
  lastResumableStage only, lens-set amendment forces replacement (classification
  persisted, zero resolutions, run stays parked), unknown kind / out-of-allowlist
  provider recovery fail closed, resolution outside needs_attention 409,
  heartbeat-expiry recovery (and fresh heartbeats untouched), committed
  two-session FOR UPDATE SKIP LOCKED double-claim proof.
- `test_analysis_worker.py` (6) — full run reaches ready with exactly five
  lens artifacts in fixed role order + recorded ids + Safety Anchor before the
  main critic call + stage IO hashes + `strategic_lens.completed` ×5 events;
  focused run schedules zero lenses and keeps `strategicLensArtifactIds=[]`;
  validation failure → blocked with prior artifacts kept and none repaired;
  cooperative cancellation stops at the next boundary (later stages never run,
  nothing published, prior events kept); empty queue → None; import-only reuse
  identity assertions on the shipped lens write path.
- `test_analysis_sse_and_commands.py` (9) — router absent from canonical app;
  SSE canonical envelopes (event:=category, full envelope shape, increasing
  unique sequences); Last-Event-ID replay; SSE anti-enumeration byte-identical
  404s; resolutions endpoint success/amendment-409(with changedFrozenFields +
  replacement URL)/invalid-422/not-resumable-409; cancel endpoint idempotency +
  ANALYSIS_RUN_NOT_CANCELLABLE for blocked; cancel/resolution anti-enumeration.

Own-test maintenance inside my scope (disclosed): the Phase A evidence suite's
`EvidenceWorld` moved from `conftest.py` into the collision-free
`evidence_world.py` (a plain `import conftest` became ambiguous once three
owner suites collect together), and the Phase A alembic-head assertion became
chain-robust (single head == applied version AND `e7f3a2c9d5b1` in its
ancestry). No QA-owned file touched.

## 2. Migration chain

`0001 → 6b246c283d7a → f850d361ee42 → c4a1f0b2d9e7 → d7e2a91c5b48 →
a3f8c2d47e19 → b2c7e9d4a1f6 → e7f3a2c9d5b1 (Task 8) → f9a4b7e2c8d3 (Task 9)`
— single head kept. New PG enums: `analysis_charter_status`,
`research_packet_role`; `formal_analysis_level` / `analysis_run_status` /
`origin_mode` reused (never recreated). Verified on disposable PG16
`ludus-pg-task08` @55441, database `decision_lab_task09` (fresh):
`upgrade head` → `current` → `check` clean → `downgrade -1` (tables, partial
index, both enums dropped; Task 8 schema intact) → `upgrade head` → `check`
clean.

## 3. Gate results (disposable PG16 @55441 + main venv, zero installs)

| Gate | Result |
|---|---|
| Own suite `pytest app/analyses/tests -q -W error -rxX` | **102 passed / 0 failed** |
| Full `pytest tests app/simulations/tests app/evidence/tests app/analyses/tests -q -W error -rxX` | **652 passed / 1 failed / 0 xfailed / 0 xpassed** |
| The single failure | the SAME disclosed QA-owned `tests/test_models.py::test_core_table_set_and_workspace_scope` exact-table-set assertion (now 10 extra canonical tables: 5 Task 8 + 5 Task 9); revision guidance in §4 |
| Filtered regression (deselect exactly that node) | **652 passed / 0 failed** — zero regression vs the 461 lane baseline and the 550 Phase A count |
| `alembic` heads/upgrade/current/check/downgrade-roundtrip | clean; single head `f9a4b7e2c8d3` |
| `ruff check services/api` / `compileall` | all passed / exit 0 |
| Official `generate_contracts.ps1 -Check` | **CONTRACT_DRIFT_OK** (exit 0; preset read-only toolchain: junction venv + `.tools\uv` + preinstalled openapi-typescript 7.13.0, UV_NO_SYNC/UV_OFFLINE; zero installs, zero network) |
| `packages/contracts/**` | zero git diff |
| `git diff --check` / conflict markers / secret scan | clean / 0 / 0 |
| Scope audit | changed set = `app/analyses/**` (new) + `app/workers/analysis_worker.py` (new) + one migration + `migrations/env.py` (+4 disclosed) + evidence own-test maintenance (2 files + 1 new helper, own scope) + HEAD/HISTORY + this handoff. `app/simulations`, `app/strategic_lenses` (import-only), `app/agents` (read-only), `app/auth`, `apps/web`, `packages/contracts`, `ways`, `app/main.py`, QA-owned `services/api/tests/**`: ZERO diff |

Notably, the decision-os structural gates
(`test_tenant_unique_constraints_include_workspace`,
`test_database_status_columns_use_enums`) pass UNMODIFIED against all ten new
tables (workspace-scoped uniques; status/role columns as PG enums).

## 4. Known contract-driven failure (QA adjudication requested, SIM-02A precedent)

Same single assertion as Phase A: `test_core_table_set_and_workspace_scope`
freezes the exact table set. Revision guidance: add
`retrieval_tasks, raw_artifacts, quality_assessments, evidence_items,
evidence_relations` (Task 8) and `analysis_charters, analysis_events,
research_packets, run_intervention_classifications, run_resolutions` (Task 9)
to `expected`; the workspace-scope loop already passes.

## 5. Contract gaps / CCR requests

1. **Event/enum promotion**: AnalysisEventCategory/Type, ResearchPacket.role,
   InterventionResult, RunResolution kinds, CharterFrozenField and
   AnalysisCharter status have canonical literal sets in 06-data-model but no
   `app.types` enums; persisted per the SIM-02A precedent (CHECK strings; PG
   enums for status/role columns without parallel Python StrEnums). CCR
   requested to promote them.
2. **RunManifest storage**: 06-data-model defines the RunManifest interface but
   no storage decision; `analysis_runs.run_manifest_id/hash` (pre-existing
   columns) are populated and the manifest table/JSONB decision is left to a
   CCR — recorded, fail-closed (no invented table).
3. **Charter/Run creation HTTP endpoints** (analysis-charters CRUD + confirm +
   replacements + runs) are 10-api canonical but belong to the mounting/
   integration wave; this lane ships the domain/repository layer they will
   call. SSE/resolutions/cancel routers stay unmounted until that CCR.
4. **Heartbeat timeout value** is not specified canonically; default 120s
   (`DEFAULT_HEARTBEAT_TIMEOUT`), injectable per call. CCR/ops config decision
   requested.
5. **Lens payload end-to-end through the behavior gates**: worker consumes the
   shipped write path import-only; producing behavior-contract-passing lens
   payloads is Task 10 lens-content scope, so worker tests use recording lens
   writers plus identity assertions on the real path. Real-provider (DeepSeek)
   orchestration belongs to the integration lane by task order.
6. **`sourceOriginModes` persist as JSONB string lists** (not a PG enum array)
   on `analysis_events` — matches the wire contract; noted for the contracts
   regeneration wave.

## 6. Known limits

- Routers unmounted by design ⇒ no OpenAPI/TS change; `ready_for_public_route = NO`.
- Model calls are stub/fixture executors (task order); the WorkerRunner/agent
  runtime (Task 7) is consumed read-only at the seam level, full wiring lands
  with the integration lane.
- Retrieval stage integration with the Task 8 evidence gateway is exercised at
  the seam (stage executors receive the run context; the ingest service from
  Phase A is available) — full retrieval-through-gateway orchestration arrives
  with real lens/provider wiring.
- The disposable PG16 container `ludus-pg-task08` @55441 (databases
  `decision_lab_task08`, `decision_lab_task09`) can be removed after QA.

## 7. Verdict

- ready_for_qa: **YES**
- ready_for_public_route: **NO** (routers not mounted; mounting rights stay
  with the integration layer, per task order and Run API precedent)

No credentials or secret values are recorded in this handoff, the code, the
tests, or the lifecycle files.


---

## r2 fast-fix addendum - idempotency wire protocol alignment (2026-07-25)

- Branch: `codex/task-09-idempotency-wire-fast-fix`, sole parent = r1 exact SHA
  `ed65f40a0a905491c868a5ffb580ae808f52373f` (ENG-02 fast-fix precedent; no
  rebase/amend/force-push).
- CCR consumption declaration: CCR-20260725-ANALYSIS-01 was consumed READ-ONLY
  in full for this addendum via `git show` from
  `codex/ccr-guest-analysis-contracts` @ exact SHA
  `d6675693fd2b7709d9ed4756489e633c49c869ee`. The r1 implementation predated
  that consumption; four adjudicated deviations are closed here.

### The four items

1. **Mandatory `Idempotency-Key` header (2.1).** `POST
   .../analyses/{analysisRunId}/resolutions` now requires the header
   (`validate_idempotency_key`; 1..200 chars mirroring the
   `idempotency_records` CHECK; format details IMPLEMENTATION_FREE per 2.2 /
   SIM-02A precedent). Missing/blank/over-long header = 422
   `VALIDATION_FAILED` with `details.header = "Idempotency-Key"`. A
   body-smuggled `idempotencyKey`/`idempotency_key` member is rejected the
   same way: the key travels ONLY via the header.
   **Adjudication disclosed:** the r1 body fields
   `AnalysisRun.idempotencyKey` (06-data-model L450 canonical) and
   `DeepAnalysisRequest.idempotencyKey` (06 L2020 canonical) are the internal
   run-creation/worker contracts, not this HTTP wire; they are deliberately
   unchanged.
2. **Same key + different body = 409 `IDEMPOTENCY_CONFLICT` (2.2).**
   Conflict detection binds the key to `normalized_request_hash`
   (canonical-JSON sha256, key-order/whitespace insensitive). Storage reuses
   the generic `idempotency_records` table (SIM-02A schema already migrated -
   ZERO new migration in this fast-fix), `route_key = "analyses.resolutions"`,
   48h retention, `response_kind = "success"`. A concurrent same-key race
   loser is answered per 2.2 through the unique-constraint IntegrityError
   fallback (replay on same hash, conflict on different hash).
3. **Replay carries `meta.idempotencyReplay: true` (2.2).** Same key + same
   normalized body replays the ORIGINAL success: stored HTTP status,
   byte-identical `data` and `eventId`, plus the meta flag; no second
   `RunResolution` row is ever appended, and an idempotent hit is never
   expressed as an error. The replay body is rebuilt from the append-only
   RunResolution / classification / `analysis.resumed` event rows. The fresh
   success response now also carries the 2.1 frozen envelope member `eventId`
   (adjacent alignment required for coherent byte-identical replay -
   disclosed).
4. **`ANALYSIS_TRANSITION_INVALID` 409 registered (5).** Backstop mapping of
   the pure state machine's `InvalidTransition` on the resolutions and cancel
   endpoints, placed strictly AFTER every specific code
   (`ANALYSIS_RUN_NOT_RESUMABLE`, `ANALYSIS_RUN_NOT_CANCELLABLE`,
   `RUN_AMENDMENT_REQUIRED`, `RUN_RESOLUTION_INVALID`) so it can never shadow
   them; it answers only the documented race window between state check and
   act.

### Scope and gates

- Changed files: `app/analyses/routes.py`, `app/analyses/repository.py`
  (+ helpers/exception, no state-machine/worker/SSE-envelope/migration
  change), own tests `test_analysis_idempotency_wire.py` (NEW, 11 tests) and
  `test_analysis_sse_and_commands.py` (three resolutions POSTs now send the
  mandatory header - lane-owned file).
- Gates: targeted suite 11/0 (`-W error`); analyses + evidence 203/0 (zero
  regression vs r1's 102 + Phase A's 90); full suite 663 passed / 1 failed -
  the sole failure remains the disclosed QA-owned exact-table-set assertion
  (revision guidance in section 4 above; +1 name unchanged since r1);
  ruff/compileall/diff-check/conflict-marker/secret-scan/scope-audit clean;
  `generate_contracts.ps1 -Check` = **CONTRACT_DRIFT_OK**; `packages/contracts`
  zero diff; alembic single head `f9a4b7e2c8d3` re-verified on disposable PG16
  `ludus-pg-task09-fastfix` @55446 (deleted after use).
- ready_for_fast_QA: **YES**. ready_for_public_route: **NO** (routers stay
  unmounted).


---

## r3 fast-fix addendum - QA-P1 + QA-P2 closure (2026-07-25)

- Branch: `codex/task-09-amendment-durability-fast-fix`, sole parent = r2 exact
  SHA `e403c665364d6260ad6199f283a5964db070f436`; ordered by QA report
  `QA_TASK_09_IDEMPOTENCY_WIRE_R2_REPORT.md` (QA tip `e4ac7dc`).
- Scope: `app/analyses/routes.py` only (+ new owner test file
  `test_analysis_amendment_durability.py`); repository/state machine/worker/
  SSE envelope/migrations ZERO diff.

### QA-P1 (2.3 amendment durability) - FIXED

The amendment path now commits the append-only
`RunInterventionClassification` and its `analysis.amendment_required` event
BEFORE raising 409 `RUN_AMENDMENT_REQUIRED`. Under the production
`get_session` lifecycle a brand-new session sees both rows after the 409;
repeated amendment attempts append exactly one classification row each
(append-only ledger).

### QA-P2 (2.2 race-loser replay) - FIXED

`RunNotResumable` is no longer answered blindly: the handler first re-checks
the idempotency record. The dual-connection same-key same-body race now ends
with BOTH sides receiving the success (exactly one carries
`meta.idempotencyReplay: true`); same key + different body still answers
`IDEMPOTENCY_CONFLICT`; a FRESH key on an already-resumed run still answers
the specific `ANALYSIS_RUN_NOT_RESUMABLE` (no shadowing - dedicated negative
test).

### Gates

Owner targeted suite 4/0 (`-W error`); full suite 667 passed / 1 failed (the
disclosed QA-owned table-set assertion; zero regression vs r2's 663);
ruff/compileall/diff-check clean; `generate_contracts.ps1 -Check` =
**CONTRACT_DRIFT_OK**; no migration touched (single head `f9a4b7e2c8d3`
re-verified on disposable PG16 @55448, deleted after use).

xfail-promotion: the two QA probes
(`test_amendment_classification_is_durable_under_production_session`,
`test_dual_connection_same_key_race_loser_replays_strict_ccr`) flip green
against this head and should be promoted to hard assertions on the QA branch.

ready_for_fast_QA: **YES**. ready_for_public_route: **NO**.


---

## r4 addendum — Analyses HTTP handlers (MOUNT-01 M3/M4/M5 + M9), 2026-07-26 (Asia/Shanghai)

- Role: Case/API/Data Owner (Task 9 owner follow-up). Branch `codex/task-09-analyses-http-handlers-r1`, parent = main @ `4941e58bee3b91f14a4a92b7fab92750ef85b3b6` (live Gate 0 echo). No rebase/amend/force; relative implementation — mounting stays with MOUNT-02; zero migration (domain layer already complete).
- Scope: `app/analyses/routes.py` (product) + own tests + this addendum + HEAD/HISTORY. ZERO change to repository / state machine / models / schemas / lens_artifact_reads / migrations / main.py / packages/contracts.

### Delivered HTTP handlers (relative, UNMOUNTED — added to the existing analyses router)

Each consumes the shipped repository + lens read service as-is, answers the `{ok,data}` envelope + the existing error-code table, and collapses cross-tenant / missing ids into the uniform `CASE_NOT_FOUND` 404 (anti-enumeration):

1. `POST /cases/{decisionCaseId}/analysis-charters` — create draft (`create_charter_draft`); missing-field + lens-set violations fail closed 422 (VALIDATION_FAILED).
2. `PATCH /analysis-charters/{charterId}` — edit draft (`update_draft_charter`); confirmed/superseded → 409 CHARTER_IMMUTABLE.
3. `POST /analysis-charters/{charterId}/replacements` — replacement draft (`create_replacement_draft`); non-confirmed origin → 409 CHARTER_NOT_CONFIRMED.
4. `POST /analysis-charters/{charterId}/confirm` — freeze; auto-bridges draft → awaiting_confirmation → confirmed (`submit_charter` + `confirm_charter`, since 10-api exposes no separate submit endpoint); re-confirm/superseded → 409 CHARTER_IMMUTABLE.
5. `POST /analysis-charters/{charterId}/runs` — create queued Run (`create_queued_run`); mandatory `Idempotency-Key` header (resolutions precedent; body-smuggled key → 422); key-based replay returns the original 201 + `meta.idempotencyReplay: true`; a reused key whose persisted charter/manifest/cynefin fields differ → 409 IDEMPOTENCY_CONFLICT (handler-level body-conflict check, no repository change); unconfirmed charter → 409 CHARTER_NOT_CONFIRMED; second active run → 409 ANALYSIS_RUN_ALREADY_ACTIVE (+ details.existingAnalysisRunId).
6. `GET /analyses/{analysisRunId}` — run status projection (10-api §AnalysisRun 状态).
7. `GET /analyses/{analysisRunId}/strategic-lenses` — ready lens summaries in canonical order (`StrategicLensArtifactReadService.list_ready_for_run`; decision_case_id derived from the run).
8. `GET /analyses/{analysisRunId}/strategic-lenses/{artifactId}` — one ready lens detail (`get_ready_artifact`); draft/rejected/missing/cross-tenant → uniform CASE_NOT_FOUND.

### MOUNT-01 stop-report items adopted

- **M9 (adopted):** `POST .../cancel` now enforces the mandatory `Idempotency-Key` header (10-api L953; body-smuggled key → 422). Cancel is naturally idempotent (canonical terminal state converges on replay), so requiring the header — not an `idempotency_records` row — honors the guarantee; no repository change. Disclosed own-test maintenance (Task 9 r1 "disclosed maintenance" precedent): the pre-existing cancel calls in `test_analysis_sse_and_commands.py` (5) and `test_analysis_idempotency_wire.py` (2) now send the header; no assertion semantics changed.
- **M8 (fix-plan only — NOT self-fixed; referred to the auth/security lane):** under cookie-based session auth the analyses unsafe-write endpoints (`resolutions`, `cancel`, and the new charter/run POSTs) are CSRF-exposed. 10-api scopes CSRF to "Cookie mutation" (L5/L946), but SIM-02A applies `require_csrf` to its authenticated `POST /runs`. **Recommended fix (auth lane):** add `Depends(require_csrf)` to the analyses unsafe-write handlers (SIM-02A parity) and clarify the canonical text so authenticated unsafe writes under cookie auth carry CSRF. Not applied here — `app/security/csrf.py` / middleware is outside this lane and CSRF is a cross-cutting security decision.

### Gates (fresh disposable PG16 `ludus-pg-task09-http` @55451; main venv via junction; uv/pnpm offline, zero installs)

- Own suite `pytest app/analyses/tests/test_analysis_http_handlers.py -q -W error -rxX` = **32 passed** (per-endpoint positive/negative + run-create idempotency replay/conflict + cancel header + cross-tenant/missing 404 matrix).
- Owner diagnostic zero-regression: `pytest app/analyses/tests app/evidence/tests` = **239 passed / 0 failed**; full `pytest tests app/simulations/tests app/evidence/tests app/analyses/tests` = **816 passed / 0 failed** (= mainline 784 + 32 new).
- `ruff check services/api` all-pass; `compileall app` exit 0; `git diff --check` clean; secret scan 0.
- Official `generate_contracts.ps1 -Check` = **CONTRACT_DRIFT_OK** — the router stays unmounted, so `app.main.app.openapi()` is unchanged (8 published ops); verified the analyses router carries 11 routes but reaches no generated contract (analyses paths absent from OpenAPI).
- alembic single head `f9a4b7e2c8d3` re-verified on the disposable PG16.

### Verdict

- ready_for_qa: **YES**. ready_for_public_route: **NO** (mounting is MOUNT-02's job).
- Next: MOUNT-02 mounts the now-complete analyses router (11 routes: 3 prior + 8 new) and regenerates contracts; the M8 CSRF hardening is the auth lane's to land.
- No credentials or secret values are recorded in this addendum, the code, or the tests.
