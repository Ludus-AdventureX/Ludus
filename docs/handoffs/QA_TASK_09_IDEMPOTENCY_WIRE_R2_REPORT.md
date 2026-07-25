# QA Report — Task 8/9 lane, Phase B r2 candidate (e403c66)

- QA branch: `codex/qa-task-09-idempotency-wire-r2`, opened from candidate head
  `e403c665364d6260ad6199f283a5964db070f436` (chain verified exactly
  `bd9fde1 → c599030 → ed65f40 → e403c66`; every link ancestor-checked).
- QA additions: `services/api/tests/test_task09_idempotency_qa_r2.py`
  (6 adversarial probes, production-like session lifecycle) + this report.
- Disclosure: this QA session also authored the r2 fast-fix (session
  consolidation directed by the orchestrator). All gates were re-executed
  independently in a fresh worktree + fresh disposable PG16
  (`ludus-pg-qa-task09-r2` @55447, deleted after use); the two adversarial
  xfail findings below demonstrate the review was not self-confirming.

## Verdicts

| Phase | Candidate | Verdict |
|---|---|---|
| Phase A (Task 8 evidence ledger) | `c599030` | **PASS** (2 recorded ACCEPT adjudications) |
| Phase B r2 four fast-fix items | `e403c66` | **PASS** (all four verified + both disclosures ACCEPT) |
| Phase B overall (r1 carry-over) | `ed65f40`+`e403c66` | **FAIL-P1** — one pre-existing §2.3 durability violation (QA-P1 below), one race-window deviation (QA-P2). Both repairable by a small follow-up fast-fix; neither is introduced by e403c66. |

## Phase A gates (PASS)

- Own suite re-run green inside the full run (evidence 90/90).
- Migration `e7f3a2c9d5b1`: `down_revision = b2c7e9d4a1f6` confirmed;
  lifecycle verified (see below).
- Scope audit on the correct merge-base diff `bd9fde1..c599030`: all paths in
  the task-08 write scope; forbidden zones 0; QA-owned test files 0. (The
  `83df911..c599030` "test_guest_alpha.py deletion" is a bidirectional-diff
  artifact — do not repeat.)
- **ACCEPT (adjudication):** `migrations/env.py` +5 metadata-import lines —
  outside the literal write-scope list but disclosed in the handoff and
  following the established `rate_limit_metadata` inclusion pattern.
- **ACCEPT (adjudication):** the single known failure
  `tests/test_models.py::test_core_table_set_and_workspace_scope` is the
  frozen exact-table-set assertion (SIM-02A precedent); revision guidance is
  in the Phase A/B handoffs. QA Owner action: extend `expected` with the ten
  Task 8/9 tables when integrating.

## Phase B r2 gates (all green)

- Full suite from the QA worktree: **663 passed / 1 failed** — sole failure is
  the same disclosed table-set assertion; zero unexpected failures.
- Owner targeted suite `test_analysis_idempotency_wire.py`: 11/11 (`-W error`).
- Migration lifecycle on fresh PG16 @55447: single head `f9a4b7e2c8d3`,
  `upgrade head` → `check` clean → `downgrade -1` (= `e7f3a2c9d5b1`) →
  `downgrade -1` (= `b2c7e9d4a1f6`) → `upgrade head` → `check` clean.
- `generate_contracts.ps1 -Check` = **CONTRACT_DRIFT_OK** (independent run);
  `packages/contracts` zero diff; r2 migration delta = 0 lines.
- ruff / compileall / conflict-marker / secret-scan on the full lane diff:
  clean.
- r2 scope: 4 product/test files, all `app/analyses/**`; state machine,
  worker, SSE envelope, migrations untouched — matches the fast-fix order.
- SSE owner-test maintenance re-diffed: exactly 4 added header lines, zero
  assertion weakening. ACCEPT.

## The two directed adjudications

1. **Body-field layering — ACCEPT.** CCR §2.1/§2.2 original text mandates the
   `Idempotency-Key` header on the resolutions endpoint and never orders the
   removal of `AnalysisRun.idempotencyKey` / `DeepAnalysisRequest.idempotencyKey`
   (both canonical in 06-data-model L450/L2020; the CCR itself cites those
   interfaces as REAFFIRM sources). The canonical-internal vs HTTP-wire
   layering therefore stands; the wire-side intent is enforced by the
   "body-smuggled key ⇒ 422" guard (owner test green). No contract-lane
   arbitration needed.
2. **`eventId` on fresh success — ACCEPT.** §2.1 freezes the success envelope
   verbatim as `{ ok, data: {...}, eventId }`; r1 omitted it. Fresh/replay
   equivalence verified: owner test asserts replayed `data` and `eventId`
   equal the original byte-for-byte, with `meta.idempotencyReplay: true` only
   on the replay.

## QA findings

- **QA-P1 (blocking, Phase B r1 pre-existing — NOT introduced by e403c66):**
  §2.3 freezes "server FIRST persists an append-only
  RunInterventionClassification" before the amendment 409, but the route
  raises before any commit; under the production `get_session` lifecycle the
  classification row AND the `analysis.amendment_required` event are rolled
  back and lost. Proven by
  `test_amendment_classification_is_durable_under_production_session`
  (xfail, production-like sessions; the owner suite's shared-savepoint
  fixture cannot see it). Fix: commit the classification (and its event)
  before raising `RunAmendmentRequired` — owner fast-fix requested.
- **QA-P2 (race window):** strict §2.2 says same key + same body ⇒ replay,
  ALWAYS. In a true dual-connection race the loser that passed the
  idempotency pre-check before the winner committed blocks on the run row
  lock, re-reads a resumed run and answers 409 `ANALYSIS_RUN_NOT_RESUMABLE`;
  the r2 IntegrityError fallback is unreachable on this path. Sequential
  retries DO replay correctly. Proven by
  `test_dual_connection_same_key_race_loser_replays_strict_ccr` (xfail);
  the non-negotiable invariants (exactly one resolution row, winner 200,
  loser answers a documented code) hold —
  `test_dual_connection_same_key_race_appends_exactly_one_resolution` passes.
  Fix suggestion: on `RunNotResumable`, re-check the idempotency record
  before answering; fold into the same fast-fix as QA-P1.
- Additional adversarial probes green: workspace-scoped idempotency (same key
  in another workspace = fresh success, never a cross-tenant replay or
  conflict); amendment 409 does not consume the key; amendment code never
  shadowed by the `ANALYSIS_TRANSITION_INVALID` backstop.

## Handoff consistency

Phase B handoff + r2 addendum spot-checked against the delivered tree: file
inventory, test counts (102 + 11), gate claims and both disclosures match.
CCR consumption declaration present with the exact contract SHA `d667569…`.

## Requested follow-ups

1. Owner fast-fix (single branch off `e403c66`): QA-P1 commit-before-raise +
   QA-P2 replay re-check. The two QA xfail probes flip to green assertions on
   that fix — promote them when integrating (xfail-promotion workflow).
2. Integration layer: standard `--no-ff` merge (candidate is a `bd9fde1`
   descendant, not `83df911`'s); migration chain single-head
   `b2c7e9d4a1f6 → e7f3a2c9d5b1 → f9a4b7e2c8d3`, no conflicts; QA Owner
   extends the table-set assertion per the handoff guidance.


---

## Closure addendum - r3 verified, findings resolved (2026-07-25)

- Owner r3 fast-fix `codex/task-09-amendment-durability-fast-fix` @
  `628f672` (sole parent e403c66) merged into this QA branch `--no-ff` for
  verification.
- xfail-promotion executed: both probes are now HARD assertions and pass -
  `test_amendment_classification_is_durable_under_production_session` (QA-P1)
  and `test_dual_connection_same_key_race_loser_replays_strict_ccr` (QA-P2).
- Combined verification on fresh disposable PG16 @55449 (deleted after use):
  QA probes 6/6 + owner analyses suites 117/117 = 123 passed, `-W error`.
- Owner r3 gates independently confirmed reasonable: full suite 667/1 (sole
  known table-set assertion), CONTRACT_DRIFT_OK, scope = routes.py + one owner
  test file.

### Updated verdicts

| Phase | Verdict |
|---|---|
| Phase A (c599030) | **PASS** (unchanged) |
| Phase B lane (ed65f40 + e403c66 + 628f672) | **PASS** - QA-P1/QA-P2 closed and regression-locked by promoted hard assertions |

Integration guidance unchanged: adopt `628f672` as the Task 9 lane head,
standard `--no-ff`, migration chain single-head, table-set assertion revision
per handoff guidance.
