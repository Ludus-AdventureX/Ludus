# CCR-20260726-MOUNT-02-ADDENDUM-A1 — Dispatcher additions ⑥/⑦/⑧ (r2)

- Date: 2026-07-26 (Asia/Shanghai)
- Adjudicator: Contract/Mainline Lead (contract_lead) — same lane as CCR-20260726-MOUNT-02
- Status: ACCEPTED
- Baseline: remote main `cacf2a35f892fc22ab8ef21a029667a0053b8342` (live ls-remote at r2 Gate 0 — the MOUNT-02 r1 head; the serial clause was checked: the A1+A2 joint wave `codex/task-10-0405-mainline-integration` @ 40d2f34 had NOT landed on main, so this addendum branches from cacf2a3).
- Branch: `codex/ccr-mount-wave-02-r2` (no rebase/amend/force).
- Trigger: the dispatcher's MOUNT-02 launch order arrived carrying three additional deliverables (⑥⑦⑧) after the loaded wave body had already shipped as r1 (adoption object identical: `--no-ff` of QA tip 7978dd8 carrying 0f92b17). This addendum closes the delta.

## A1-⑧. M8 CSRF adjudication closure — ALREADY CLOSED (r1)

Closed by CCR-20260726-MOUNT-02 §M5 on main @ cacf2a3 (`require_csrf` on the seven analyses unsafe writes, SIM-02A parity, 10-api SM1 clarification, wave regression battery). No further action.

## A1-⑦. P3 combination-only fix: `supersedesAnalysisRunId` joins the run-create replay compare set — NEW (fixed here)

**Finding (real gap):** `create_analysis_run` §2.2 replay detection compared only `charter_id` + `runManifestHash` + `cynefinGateResultId`. A reused `Idempotency-Key` whose body changed ONLY the supersedes target silently replayed the original run instead of answering 409 — a body-mismatch escape.

**Ruling — fixed.** `run.supersedes_analysis_run_id != supersedes_id` joins the compare set (`app/analyses/routes.py`, combination-only, no repository change). Acceptance (`test_mount02_addendum_r2.py`): same-key supersedes-only change ⇒ 409 `IDEMPOTENCY_CONFLICT` (hard assertion — the dispatcher's "pinning test flipped to assert 409" lands here as a fresh hard test: no pinning test existed on main to flip, verified via `git grep` on main and on 40d2f34); exact replay including a non-null supersedes target still answers 201 + `meta.idempotencyReplay: true` (no false conflict).

## A1-⑥. `lensArtifactIds` verbatim passthrough for `audit_full_run_lens_set` — PINNED here; audit binding DEFERRED

**Finding:** `audit_full_run_lens_set` (with its `referenced_artifact_ids` exact-equality parameter) lives in `app/analyses/quality_gate.py` on the **A1+A2 joint wave** (@ 40d2f34), which is not on main. There is no route-layer call site to adjudicate yet.

**Ruling — two parts:**
1. **PINNED this commit:** the run-status projection forwards `strategicLensArtifactIds` VERBATIM — no route-layer UUID parsing, casing normalization, dedup, or reordering (A1 QA red-light semantics: normalization would mask persisted-set corruption the audit exists to catch). Negative acceptance added: hostile non-UUID / uppercase / duplicate entries survive the projection byte-for-byte and never 500 (`test_lens_artifact_ids_pass_through_verbatim`).
2. **DEFERRED-to-A1+A2-landing:** wiring `lensArtifactIds` into `audit_full_run_lens_set(referenced_artifact_ids=...)` binds when the joint wave lands on main. Binding contract fixed now: the route/worker layer passes the persisted list **as-is** (exact equality including order-insensitive set compare is the audit's job, never the caller's); the pinning test above is the tripwire.

## Canonical Impact

- Zero canonical-text change (no 10-api path/error/event change; `supersedesAnalysisRunId` was already a documented optional body field).
- Zero contract regeneration needed: both changes are handler-internal semantics on generic `{ok,data}` envelopes; `generate_contracts.ps1 -Check` stays `CONTRACT_DRIFT_OK` (verified).
- Write domain: `app/analyses/routes.py` (compare-set addition only) + new acceptance test file + this addendum + HEAD/HISTORY.

## Decision

- Accepted by: Contract/Mainline Lead, 2026-07-26 (Asia/Shanghai).
- ready_for_merge: pending r2 gates (analyses suites, full + canonical pytest on the disposable PG16, `-Check`, ruff/compileall/diff-check/marker/secret/scope) — recorded in HEAD/HISTORY on completion.
- Follow-up: A1+A2 integration wave consumes A1-⑥ part 2 (audit binding) on landing.
