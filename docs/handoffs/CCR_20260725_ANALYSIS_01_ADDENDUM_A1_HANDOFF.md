# CCR_20260725_ANALYSIS_01_ADDENDUM_A1_HANDOFF

- Date: 2026-07-25 (Asia/Shanghai)
- Role: Contract/Mainline Lead — docs-only addendum adjudication
- Mode: CONTRACT-FIRST / TEXT-ONLY (no product code, no migration, no main merge performed here)
- Branch: `codex/ccr-analysis-01-addendum-a1`, parent = main @ `4508b3059e1a71f62f90bdabcfb7a36cfc50cac4` (live ls-remote verified)

## Output

- `docs/product-plan/docs/contract-changes/CCR-20260725-ANALYSIS-01-ADDENDUM-A1.md` — full addendum with 10 ruling items, evidence citations, and canonical text syncs SA1-SA3
- `docs/product-plan/06-data-model.md` — SA1: idempotencyKey internal-vs-wire layering declaration after AnalysisRun interface
- `docs/product-plan/10-api-and-events.md` — SA2: amendment commit-before-raise timing clause; SA3: idempotency race-safety guarantee
- `docs/handoffs/CCR_20260725_ANALYSIS_01_ADDENDUM_A1_HANDOFF.md` — this file
- `HEAD` — updated with lane summary
- `HISTORY` — appended with lifecycle entry

## 10 ruling items summary

| Item | Tag | Summary |
|---|---|---|
| A1-1 | IMPLEMENTATION_FREE | Event/charter/frozen-field enums: DB CHECK/PG enum sufficient; Python promotion → A3 |
| A1-2 | REAFFIRM | RunManifest storage: reuse run_manifest_id/hash columns; no new table |
| A1-3 | IMPLEMENTATION_FREE | Heartbeat timeout: 120s default injectable; operational parameter |
| A1-4 | DEFERRED-to-A3 | Charter/Run HTTP endpoint mounting: paths canonical, mounting belongs to A3 |
| A1-5 | NEW | Idempotency-Key layering: internal fields (06 L450/L2020) vs HTTP wire; SA1 applied |
| A1-6 | NEW | eventId on fresh resolution success: ratified; already synced via S4 |
| A1-7 | NEW | Amendment commit-before-raise: classification+event durable before 409; SA2 applied |
| A1-8 | NEW | Idempotency race loser replay: RunNotResumable re-checks idempotency record; SA3 applied |
| A1-9 | DEFERRED-to-A3 | Evidence read API paths: absent from 10-api; A3 must CCR + mount |
| A1-10 | IMPLEMENTATION_FREE | SourceGrade/verdict/retrieval_task_status enums: DB-first; Python → A3 |

## Items requiring code follow-up (A3 lane)

| Item | Action | Lane |
|---|---|---|
| A1-1 | Promote AnalysisEventCategory/Type, ResearchPacket.role, CharterFrozenField, etc. to `app.types` | A3 integration |
| A1-4 | Mount Charter/Run HTTP endpoints (10-api L65-75) on Task 9 domain layer | A3 integration |
| A1-9 | CCR for evidence read paths (detail/quality/provenance/direction/same-source/run-list/conflict-list), then mount | A3 integration |
| A1-10 | Promote SourceGrade, FreshnessStatus, EvidenceVerdict, RetrievalTaskStatus to `app.types` | A3 integration |

## Verification

- `git diff --name-only` expected: `docs/product-plan/docs/contract-changes/CCR-20260725-ANALYSIS-01-ADDENDUM-A1.md`, `docs/product-plan/06-data-model.md`, `docs/product-plan/10-api-and-events.md`, `docs/handoffs/CCR_20260725_ANALYSIS_01_ADDENDUM_A1_HANDOFF.md`, `HEAD`, `HISTORY`
- `git diff --check` expected: clean
- Conflict markers / secret scan expected: 0 / 0
- `generate_contracts.ps1 -Check` expected: CONTRACT_DRIFT_OK (docs-only, no product change)

## ready_for_merge

**YES** — docs-only; no code, migration, test, or generated-contract change; all diff paths within the contract-changes + authorized text sync + handoff + HEAD/HISTORY boundary.
