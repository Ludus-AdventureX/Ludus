# TASK 08 — Evidence Ledger & Information Quality Gateway (r1) Handoff

- Role: Case/API/Data Owner (Fable5); lane = Task 8 (Phase A) of the deep research
  pipeline backend (Task 9 follows in the same lane, separate branch/commit).
- Branch: `codex/task-08-evidence-ledger-r1`, fresh worktree
  `decision-lab-task08-evidence` (no archived worktree reused).
- Base: `bd9fde15278afd63d351b2adaeb95ec32441cd6f` = live `git ls-remote origin
  refs/heads/main` at Gate 0 — EXACT match with the authorized baseline; the
  deviation protocol was NOT needed. No rebase/amend/force-push/cherry-pick; main
  untouched.
- Plan basis: `docs/product-plan/18-detailed-development-plan.md` Task 8
  (L896-949); write scope per `agent-work-manifest.yaml` task-08.
- Canonical contracts consumed read-only: 06-data-model.md, 08-deep-research-
  pipeline.md, 10-api-and-events.md, 26-decision-os-invariants-and-agent-engine-
  contract.md, `app/types.py` (enums imported only — `EvidenceVerdict`,
  `ConnectorStatus`, `OriginMode`, `SourceKind`; zero parallel definitions).

## 1. Delivered files

Product (all inside task-08 write scope):

- `services/api/app/evidence/models.py` — ORM for `retrieval_tasks`,
  `raw_artifacts`, `quality_assessments`, `evidence_items`, `evidence_relations`.
- `services/api/app/evidence/normalizer.py` — canonical URI normalization,
  root-source fingerprint, independent-source grouping (same-source dedup).
- `services/api/app/evidence/quality.py` — deterministic blocking gate
  (L1-L6 category + orthogonal dimensions + four-tier verdict + reason codes +
  remediation actions).
- `services/api/app/evidence/artifact_store.py` — filesystem ArtifactStore
  (workspace-scoped relative pointers only; staged write-and-move).
- `services/api/app/evidence/ingest.py` — RawArtifact-first retrieval ingestion
  (references returned only after immutable rows are persisted).
- `services/api/app/evidence/repository.py` — tenant-scoped read repository.
- `services/api/app/evidence/schemas_api.py` — camelCase CanonicalModel views
  (SIM-02A `schemas_api` precedent; NOT exported to generated contracts).
- `services/api/app/evidence/routes.py` — provenance/conflict query router,
  **relative and NOT mounted** (`app/main.py` untouched; mounting is the
  integration layer's right, Run API lane precedent).
- `services/api/app/connectors/providers/{base,ssrf,exa,tavily,firecrawl,fixture,router}.py`
  — direct HTTP adapters + SSRF guard + Exa→Tavily failover router + spherical-
  robot fixture provider (CCR-20260724-Ways-01 moved this scope into task-08).
- `services/api/migrations/versions/e7f3a2c9d5b1_add_evidence_ledger.py` — the
  single forward migration of this lane.
- `services/api/migrations/env.py` — +1 disclosed import so autogenerate/check
  see the evidence metadata (comment marks it as Task 8; same pattern as the
  `rate_limit_metadata` inclusion).

Own tests (new directory, no QA-owned file touched):

- `services/api/app/evidence/tests/conftest.py` (+ fixtures/seeding)
- `test_evidence_quality.py` (15) — same-source dedup (3 articles citing one
  report = 1 independent source ⇒ conditional), L1 never auto-accepted,
  four-tier verdict matrix, conditional always carries limits, lead_only
  triggers next retrieval and never enters the Worker set, reason codes ⇒
  remediation actions, unknown grade fails closed.
- `test_evidence_models.py` (24) — persistence chain, tenant isolation /
  anti-enumeration at repository level, composite-FK cross-workspace negatives,
  CHECK negatives (sha256 hex, storage path relative, canonical literal sets,
  conditional-requires-limits, self-relation), enum catalog assertions,
  workspace CASCADE, immutability by shape (no update surface).
- `test_evidence_ingest.py` (4) — RawArtifact rows persisted BEFORE references
  are returned, fetch bodies hashed & pointer-scoped, degraded search records a
  failed RetrievalTask + structured status without fabricating artifacts,
  cross-workspace pointer read refused.
- `test_provider_adapters.py` (18) — missing_credentials before any request,
  HTTP status → ConnectorStatus matrix (401/403/429/402/5xx), transport errors
  as structured provider_error, Exa→Tavily switch, full fallback chain when all
  degrade, Firecrawl markdown fetch, SSRF-unsafe target refused before the
  platform is called, crawl disabled by default + allowlist gating, fixture
  provider stability/labeling, secrets never in outcomes or details.
- `test_ssrf_guard.py` (23) — scheme whitelist, loopback/private/link-local/
  metadata/unspecified negatives (IPv4+IPv6), DNS-rebinding negative, DNS
  fail-closed, userinfo, port whitelist, reason labels never echo URL content.
- `test_evidence_routes.py` (5) — router absent from canonical app; detail/
  quality/provenance/direction/same-source-group/run list/conflict list happy
  paths; cross-workspace real id vs ghost id = byte-identical CASE_NOT_FOUND
  404; unknown workspace = uniform WORKSPACE_NOT_FOUND 404.

Own tests total: **90** (`pytest app/evidence/tests -q -W error -rxX` → 90 passed).

## 2. Migration chain

- `alembic heads` before work: exactly `b2c7e9d4a1f6` (single head; the plan
  document's literal `0002` rev-id assumption is stale, as the task order
  anticipated).
- New revision: `e7f3a2c9d5b1` (down_revision `b2c7e9d4a1f6`); single head kept.
- Creates: the five tables above; PG enums `evidence_verdict` (values from
  canonical `app.types.EvidenceVerdict`) and `retrieval_task_status` (canonical
  06-data-model literal set; status-like columns must be enums per the
  decision-os invariants suite — no parallel Python StrEnum was declared).
  Shared `origin_mode` enum reused, never recreated.
- Verified on disposable PG16 `ludus-pg-task08` @55441 (fresh DB):
  `upgrade head` → `current = e7f3a2c9d5b1` → `alembic check` clean →
  `downgrade -1` (back to `b2c7e9d4a1f6`, tables + both enums dropped) →
  `upgrade head` → `check` clean.

## 3. Gate results (disposable PG16 @55441 + main worktree venv, zero installs)

| Gate | Result |
|---|---|
| Own suite `pytest app/evidence/tests -q -W error -rxX` | **90 passed / 0 failed** |
| Start-of-lane full baseline (recorded before any change) | **461 passed / 0 failed / 0 xfailed / 0 xpassed** |
| Full `pytest tests app/simulations/tests app/evidence/tests -q -W error -rxX` | **550 passed / 1 failed / 0 xfailed / 0 xpassed** |
| The single failure | `tests/test_models.py::test_core_table_set_and_workspace_scope` — QA-owned exact-table-set equality assertion; contract-driven, see §4 |
| Filtered regression (deselect exactly that node id) | **550 passed / 0 failed** — zero regression vs the 461 baseline |
| `ruff check services/api` | all checks passed |
| `compileall` (app + migrations) | exit 0 |
| Official `generate_contracts.ps1 -Check` | **CONTRACT_DRIFT_OK** (exit 0; preset read-only toolchain per SIM-02A closure precedent: junction `.venv` → main checkout venv, PATH-prepended `.tools\uv` + preinstalled `openapi-typescript` 7.13.0, `UV_NO_SYNC=1`/`UV_OFFLINE=1`; zero installs, zero network) |
| `packages/contracts/**` | zero git diff |
| `git diff --check` / conflict markers / secret scan | clean / 0 / 0 hits (only the literal test constant `task08-test-only-key-000000`) |
| Scope audit | changed set = `app/evidence/**` (new) + `app/connectors/providers/**` (new) + one migration + `migrations/env.py` (+5 lines, disclosed) + HEAD/HISTORY + this handoff. `app/simulations`, `app/strategic_lenses`, `app/auth`, `apps/web`, `packages/contracts`, `ways`, `app/main.py`, existing `services/api/tests/**`: ZERO diff |

## 4. Known contract-driven failure (QA adjudication requested, SIM-02A precedent)

`tests/test_models.py::test_core_table_set_and_workspace_scope` asserts
`set(Base.metadata.tables) == expected` with a frozen 31-table list. Task 8's
five canonical tables (`retrieval_tasks`, `raw_artifacts`,
`quality_assessments`, `evidence_items`, `evidence_relations`) necessarily
extend the metadata, so the equality fails by construction — exactly the
SIM-02A situation adjudicated as "implement per frozen contract, QA Owner
revises the assertion".

Revision guidance for QA: add the five table names (with a `Task 8 evidence
ledger` comment) to the `expected` set; the companion workspace-scope loop
already passes because every new table carries `workspace_id`.

The suite's other structural gates (`test_decision_os_invariants.py`
status-enum rule, workspace-column rule) pass unmodified against the new
tables.

## 5. Contract gaps / CCR requests (fail-closed dispositions)

1. **Evidence read API paths are absent from 10-api-and-events.md.** The
   conflict/provenance query layer is therefore delivered as a relative,
   UNMOUNTED router with internal DTOs only; nothing reaches the generated
   contracts. CCR needed before mounting: canonical paths + wire shapes for
   evidence detail / quality / provenance / direction / same-source group /
   run evidence list / conflict list (proposed shapes in
   `app/evidence/schemas_api.py`).
2. **`SourceGrade` (L1-L6), `FreshnessStatus`, `RetrievalTask.status`,
   `stableToolName` have canonical wire literal sets in 06-data-model but no
   `app.types` enum.** Persisted per the SIM-02A `response_kind` precedent
   (CHECK-constrained strings; `retrieval_task_status` as a PG enum from the
   canonical tuple). CCR requested to promote these sets into `app.types`.
3. **Independent-source grouping has no canonical field.** 06-data-model gives
   `conflictGroupId` but no same-source/independent-source group field, while
   Task 8 requires "three articles citing one report = 1 independent source".
   Implemented as `evidence_items.independent_source_group_id` (nullable UUID,
   deterministic uuid5 of the root-source fingerprint) + `evidence_relations`
   rows (`same_source_group|conflicts_with|corroborates`). Neither appears on
   any generated contract; CCR requested to canonize the wire representation.
4. **`evidence_relations` is named in the plan but not defined in 06-data-model.**
   Field design documented in `app/evidence/models.py` docstring; ClaimEvidence
   (claim↔evidence direction) intentionally NOT duplicated — it stays a Task 10
   surface.
5. **Nine review dimensions vs seven canonical numeric fields.** Mapping used:
   authenticity/relevance/freshness/applicability/independence/
   extraction_reliability = numeric scores; bias → `bias_flags[]`;
   completeness → `completeness_warnings[]`; conflict → `conflict_group_ids[]`;
   `source_quality` carries the L1-L6 category projection. No new wire fields
   invented.
6. **SSRF guard placement.** 10-api mandates one SSRF-safe client; the unified
   client is task-16 scope (`app/security/**`). This lane ships the guard at
   `app/connectors/providers/ssrf.py` for provider outbound URLs; when task-16
   lands the shared client, providers should switch to it (import-only change).
7. **`app/connectors/` package root.** Only `providers/**` is task-08 scope;
   no `__init__.py` files were added anywhere (namespace packages, matching
   `app/evidence`'s existing style), so the `connectors` root remains untouched
   for task-16.

## 6. Known limits

- Router unmounted by design ⇒ no OpenAPI/TS change (drift check stays OK).
- Provider adapters are exercised offline via `httpx.MockTransport` and the
  fixture provider; real-key liveness belongs to the integration lane.
- `ClaimEvidence` supporting/opposing persistence is Task 10 scope; the
  direction view projects `supports/contradicts_claim_ids` JSON lists.
- Crawl remains single-page semantics even when explicitly enabled (allowlist +
  caps enforced); true multi-page crawl is a later, separately-gated slice.
- The disposable PG16 container `ludus-pg-task08` @55441 can be removed after
  QA (`docker rm -f ludus-pg-task08`).

## 7. Verdict

- ready_for_qa: **YES**
- ready_for_public_route: **NO** (router not mounted; evidence API paths await
  their CCR; this is the contract-mandated state)
- Next: Phase B — Task 9 (`codex/task-09-analysis-runtime-r1`), parent = this
  branch's exact SHA (reported in the lane summary after push).

No credentials or secret values are recorded in this handoff, the code, the
tests, or the lifecycle files.
