# Task 10 — Claims, Synthesis, Devil's Advocate & Formal Quality Gate (r1) Handoff

- Lane: `codex/task-10-quality-gate-r1`, worktree `decision-lab-task10-quality-gate-r1`
- Sole parent: main `4941e58bee3b91f14a4a92b7fab92750ef85b3b6` (remote-verified; carries
  Task 8/9 full chain + CCR-20260725-ANALYSIS-01 Addendum A1)
- Role: Ways/Agent-Pipeline Owner (Fable5). Two scope commits in this lane:
  `case_api_data` (the four `app/analyses` files, per CCR-20260724-Ways-01) and
  `ways_agent_pipeline` (reports + migration + tests + lifecycle).
- Plan: 18-detailed-development-plan.md Task 10 section (L1020-1105 @ 4941e58), consumed
  verbatim. Contract: CCR-20260725-ANALYSIS-01 (5ffccf8) + Addendum A1 (32dfbd1 + 9bb19eb),
  read from main @ 4941e58.
- ready_for_qa: **YES**. ready_for_public_route: **NO** (this batch mounts nothing; the
  read endpoints shipped earlier stay as-is; A3 owns all mounting).

## 1. Delivered

### case_api_data commit — `app/analyses/` four files

| File | Content |
|---|---|
| `claims.py` | `Claim`/`ClaimEvidence` ORM strictly on the 06 canonical fields (`statement_type`, `importance`, `support_score`, `supporting/opposing_evidence_ids`, `assumption_ids`, `scope`, `status`); `assess_claim_support` computes support and opposition **separately** (strongest-link + corroboration lift, never a per-source majority vote; `lead_only`/`rejected` links never support); `reconcile_facts` classifies same-metric divergence into the four canonical categories (`factual_conflict` / `definition_mismatch` / `freshness_gap` / `source_divergence`); unadjudicable conflicts ship in the report payload (`ReconciliationFinding.report_entry`) AND downgrade the named claims. |
| `devils_advocate.py` | `Challenge` ORM (06 shape + disposition trail columns); `evaluate_adversarial_arc` enforces the closed disposition set `accepted_change` / `rejected_with_reason` / `escalated` for every important finding; rejection without reason and missing dispositions are arc violations; an unresolved fatal defect (critical `fatal_flaw` not closed by `accepted_change`) sets `return_to_synthesis`; fewer than two important non-fatal findings changing the report is a warning-grade code. DB CHECKs mirror the arc rules (rejection requires reason; confirmed important findings require a disposition). |
| `quality_gate.py` | `QualityGateResult` ORM (unique per workspace+run; `(status='passed') = deliverable` CHECK); `ReportQualityGate.evaluate` runs exactly FOUR orthogonal checks (evidence sufficiency / adversarial pressure / logic consistency / synthesis deviation); the multiplicative value only decides deliverability; any severe failure → `blocked` and `pdf_allowed`/`simulation_allowed` are false; the six-dimension `RecommendationQuality` profile is a pure projection of the four checks (+ scenario flips) — never a second scoring system; `audit_full_run_lens_set` re-checks the persisted five-lens set (exact set vs frozen Charter, ready status, producer-role mapping, same case/charter, `lensArtifactIds` exact equality) and re-runs the merged behavior validators per lens (import-only from `app.strategic_lenses.validators`); schema-pass/behavior-fail keeps the run out of `ready`, and only repair inputs (no content) travel back. |
| `synthesis.py` | Level discipline (06 判别约束): focused → `brief` + `FocusedResearchResult`, zero lens/PDF/simulation surface (`ensure_lens_persistence_allowed` rejects focused lens persistence BEFORE the lens repository); full → `detailed` + `StructuredReport` whose `lensArtifactIds` must equal the five ready artifacts (body text never substitutes). Report persistence: worker-only writer, same-run same-hash idempotent replay of the original row, different-hash conflict PRESERVES the original; `publish_report_artifact` requires run `ready` + gate `passed`; `update/delete_report_artifact` reject ready rows (repository layer of the double-layer rule); `create_export_artifact` fails closed for focused level, blocked gate, non-ready run, unpublished report (`REPORT_PUBLICATION_BLOCKED`/`EXPORT_NOT_ALLOWED` semantics, no invented codes); `ensure_simulation_allowed` refuses formal simulation on a blocked gate. |

### ways_agent_pipeline commit — reports, migration, tests, lifecycle

- `app/reports/models.py`: `ReportArtifact` / `ExportArtifact` ORM per 06 报告对象, with the
  level/type discriminant, `content_hash` idempotency anchor (unique per workspace+run),
  publish-requires-ready CHECK and html/pdf media pairing.
- `app/reports/schemas.py`: CanonicalModel wire views (`FocusedResearchResult`,
  `StructuredReport`, `Recommendation(Quality)`, `ReportValidation`, …); the
  `StructuredReport.lensArtifactIds` shape guard refuses anything but 5 distinct ids;
  internal only — nothing exported to `packages/contracts` (CONTRACT_DRIFT_OK).
- Migration `b6e8f3a1d7c2_add_analysis_outputs` (single forward revision after
  `f9a4b7e2c8d3`, single head preserved): creates `claims`, `claim_evidence`, `challenges`,
  `quality_gate_results`, `report_artifacts`, `export_artifacts`;
  `strategic_lens_artifacts` already exists (d7e2a91c5b48) and is NOT recreated — the
  revision only attaches the ready-row trigger to it. New PG enums: `statement_type`,
  `generated_content_status`, `quality_gate_status`, `report_artifact_status`,
  `export_artifact_status` (status columns per the decision-os invariant; Task 9
  packet-role precedent). `entry_status`/`evidence_verdict`/`formal_analysis_level`/
  `origin_mode` reused, never recreated.
- Ready-row immutability, database layer: one shared trigger function on
  `strategic_lens_artifacts` AND `report_artifacts` — UPDATE of a ready row is always
  forbidden; direct DELETE of a ready row is forbidden; FK cascade deletes
  (workspace/case/run purge) stay legal via `pg_trigger_depth()` (probe-verified: cascade
  depth 2 allowed, direct depth 1 blocked); explicit maintenance purge requires
  `SET LOCAL ludus.allow_ready_artifact_purge = 'on'`.
- `migrations/env.py`: registers the four new model modules on the shared metadata
  (Task 8/9 precedent; required for `alembic check`/autogenerate correctness).
- Own tests: `tests/test_analysis_quality_gate.py` (24) + `tests/test_reports_artifacts.py`
  (13) — red-light batch first (verbatim Step 1 test included), see §3.

## 2. Gates

| Gate | Result |
|---|---|
| Own suites `-W error` | **37 passed / 0 failed** |
| Full `pytest tests app/simulations/tests app/evidence/tests app/analyses/tests -q -W error -rxX` | **819 passed / 2 failed / 0 xfailed** — both failures are the disclosed QA-owned assertions in §4 |
| Filtered regression (deselect exactly those two nodes) | **819 passed / 0 failed** — zero regression vs the 784 baseline |
| alembic lifecycle (disposable PG16 `ludus-pg-task10-qg2` @55458) | heads = single `b6e8f3a1d7c2`; `upgrade head` → `check` ("No new upgrade operations detected") → `downgrade -1` (= `f9a4b7e2c8d3`) → `upgrade head` clean |
| `ruff check services/api` | all checks passed |
| `compileall` (app + migrations) | exit 0 |
| Official `generate_contracts.ps1 -Check` | **CONTRACT_DRIFT_OK** (exit 0; preset read-only toolchain: junction root `.venv` + `services/api/.venv` → main checkout venvs, junction `node_modules`, PATH-prepended `.tools\uv`, `UV_NO_SYNC=1`/`UV_OFFLINE=1`; zero installs, zero network) |
| `packages/contracts/**` | zero git diff |
| `git diff --check` / conflict-marker scan / secret scan | clean / 0 / 0 |

## 3. Red-light batch (all green)

1. `test_core_claim_without_accepted_or_conditional_evidence_is_blocked` — verbatim plan
   Step 1 shape (`report_gate.evaluate` → `blocked` + `core_claim_unsupported`).
2. full missing any lens → `strategic_lens_incomplete` → blocked.
3. non-ready (draft) lens → blocked; wrong producer role → blocked; cross-run reference →
   `strategic_lens_reference_mismatch` → blocked; duplicate reference (5 entries, 4
   distinct) → blocked; shape guard additionally refuses ≠5/duplicate ids at parse time.
4. schema-pass/behavior-fail (Porter `scoreIsNotDecisionFormula=false` passes the pack JSON
   schema) → `lens_behavior_failed`, run blocked, repair inputs carry codes + frozen
   references and NO content ("Validation 不补写" asserted structurally).
5. focused lens persistence → `FocusedLensPersistenceRejected` before the lens repository.
6. blocked gate → PDF + formal simulation + publication all refused at the service layer.
7. ready-row UPDATE/DELETE double-layer rejection: repository errors first; raw SQL then
   hits the DB trigger — for report_artifacts AND strategic_lens_artifacts.
8. idempotency: same hash replays the original row; different hash → conflict, original
   row byte-preserved.

## 4. Disclosed QA-owned assertion conflicts (revision guidance)

1. `tests/test_models.py::test_core_table_set_and_workspace_scope` — the frozen
   exact-table-set assertion (SIM-02A/Task 8/9 precedent). Six new canonical tables extend
   the metadata by construction. QA Owner action when integrating: extend `expected` with
   `claims`, `claim_evidence`, `challenges` (Task 10 propositions & adversarial arc) and
   `quality_gate_results`, `report_artifacts`, `export_artifacts` (Task 10 gate & report
   objects). The workspace-scope loop passes unmodified (every new table carries
   `workspace_id`).
2. `tests/test_decision_os_invariants.py::test_database_status_columns_use_enums` — the
   invariant asserts every column named `scope` is an Enum, but canonical `Claim.scope`
   (06-data-model L18919 area: `scope: string`) is contractually FREE TEXT (适用范围).
   All genuinely enum-like Task 10 columns (all four `status` columns) ARE PG enums.
   QA Owner action: exempt `claims.scope` (e.g. allowlist) or scope the rule to
   enum-like columns; implementing `scope` as an enum would violate the frozen contract.

## 5. Combination-only change disclosed

- `tests/lens_lanes/test_lens_persistence_qa.py` (QA-owned): the committed-rows
  self-cleanup now opts into the maintenance purge
  (`SET LOCAL ludus.allow_ready_artifact_purge = 'on'`) before deleting its ready lens
  artifact — required by this batch's DB trigger. Assertions untouched; the test itself
  passes (guest-QA `07e5787` combination-only precedent).

## 6. Contract gaps / notes for A3

- No HTTP surface in this batch: the gate/report/export functions are service-layer and
  called by the worker/integration wave; the canonical wire codes
  (`REPORT_PUBLICATION_BLOCKED`, `EXPORT_NOT_ALLOWED`, `STRATEGIC_LENS_INCOMPLETE`) map
  1:1 onto the exception surface in `app/analyses/synthesis.py` / gate reason codes.
- `sourceJudgmentSetId`/`sourceDissentRecordId` are persisted as opaque UUIDs (their
  owning tables belong to a later slice; 06 keeps them required on `ReportArtifact`).
- The quality-gate → `analysis.blocked`/`analysis.ready` event append and the
  `strategic_lens.completed` timing stay with the Task 9 worker (already canonical);
  this batch exposes `QualityGateEvaluation` for it to consume.
