# CCR_ENG_02_PROFILE_AWARE_INPUT_HASH_HANDOFF

- Date: 2026-07-25 (Asia/Shanghai)
- Role: Contract/Mainline Lead — Simulation Engine Profile-Aware Hash Contract Owner
- Mode: CONTRACT-FIRST / NO PRODUCT CODE / NO MAIN MERGE

## Exact refs (all live ls-remote verified at gate zero AND re-read after push)

| ref | SHA |
|---|---|
| remote main | `387041d40442faf16557b266ef3f844b7af8fb69` (unchanged, untouched; migration head `a3f8c2d47e19`) |
| SIM-02A contract | `codex/ccr-sim-02a-run-api-contract` @ `0289b2e36a7765891e4f1908231ac2384c541318` |
| P1/P3 product | `codex/sim-02a-profile-idempotency-r1` @ `fb75b8f5dc282b9df3cf8172e3ed114fe23ae29a` |
| P1/P3 exact QA | `codex/qa-sim-02a-profile-idempotency-r1` @ `edaa8421c330de7cfe02a53c1e38574533e99c48` |
| ENG-02 contract branch | `codex/ccr-eng-02-profile-aware-input-hash-r1` (head = this commit; recorded in final push re-read) |

## Direct-parent / ancestry proof (executed this lane)

- `edaa842` has exactly ONE parent = `fb75b8f` (`git rev-list --parents`);
- QA delta fb75b8f→edaa842 = `services/api/tests/**` + QA handoff + HISTORY only
  ⇒ product bytes identical by construction;
- candidate migration head = exactly `b2c7e9d4a1f6`
  (`down_revision = a3f8c2d47e19`); main tree at 387041d does NOT contain it
  ⇒ main migration head still `a3f8c2d47e19`;
- `387041d` proven ancestor of `0289b2e` AND of `fb75b8f`
  (`merge-base --is-ancestor`);
- `0289b2e` delta vs main = CCR-SIM-02A file + its handoff + HEAD/HISTORY only
  ⇒ legal contract/lifecycle-only parent; this branch is its direct child.

## Verdicts (normative source = CCR-20260724-ENG-02.md)

| key | verdict |
|---|---|
| engine_version_verdict | **MINOR_BUMP_FROZEN** |
| exact new ENGINE_VERSION | **`sim-engine-1.1.0`** (from the first commit whose compute_input_hash carries the profile block; no mixed mode) |
| exact hash payload contract | CCR §2: nested top-level `profile` object with `id` (canonical lowercase UUID string), `version` (JSON int ≥ 1), `contentHash` (`^sha256:[0-9a-f]{64}$`, full persisted value); `riskTolerance` stays a separate top-level key with unchanged semantics; canonical JSON sorted/`,`/`:`/UTF-8 unchanged; delta vs 1.0.0 = engineVersion value + profile block ONLY; before/after examples frozen in the CCR |
| profile_hash_trust_verdict | **PERSISTED_HASH_TRUSTED_VIA_APPEND_ONLY_WRITE_PATH** with mandatory pre-engine format validation; malformed/missing content_hash ⇒ `frozen_reference_incomplete` before engine, zero rows; anchor failures stay uniform CASE_NOT_FOUND 404; no bare SQLAlchemy/ValueError at future HTTP boundary |
| sensitivity verdict | base run + sweeps share one verified fingerprint; iteration-order independent; includeSensitivity stays OUT of inputHash (Task 12 semantics); numeric algorithms untouched; same input ⇒ same hash + same numbers |
| historical compatibility verdict | **HISTORICAL_ROWS_IMMUTABLE** — 1.0.0 rows never backfilled/rewritten; GET replay reads persisted values, never recomputes |
| migration_required | **false** — no schema change; migration head stays exactly `b2c7e9d4a1f6` |
| Addendum A1 non-regression | `score_constraint_operator_unsupported` + `strategy_edge_gating_unsupported` preserved verbatim; no equality scoring, no edge gating smuggled under the version bump |
| CONTRACT_ERRATUM resolution | additive `CCR-20260724-SIM-02A-ADDENDUM-A1.md` supersedes the false "internal callers unaffected" sentence (original file NOT rewritten); no public API promise was at stake; internal adaptation already delivered + QA-locked at edaa842 |

## Exact P2 implementation write scope (CCR §7)

- Branch: DIRECT child of `edaa8421c330de7cfe02a53c1e38574533e99c48` (bare
  fb75b8f + hand-copied QA = audit error).
- ALLOWED: `app/simulations/{domain,engine,assembly,service}.py`,
  `app/simulations/profile_hash.py` (only if needed),
  `app/simulations/tests/**`, `docs/handoffs/**`, HEAD/HISTORY.
- FORBIDDEN: `services/api/tests/**` (QA-owned), migrations (default NO
  MIGRATION), `models.py`/`types.py`/`schemas.py`, routes/main.py/tenancy
  mounting, `packages/contracts/**`, `apps/web/**`, `scripts/**`, Artifact
  IO/Lens, product/QA branch rewrites, main.

## Exact P2 test/QA transition requirements (CCR §7–§8)

- QA-owned pinned assertions (at minimum
  `test_p2_engine_hash_gap_is_pinned_pending_dependency` in
  `services/api/tests/test_sim_02a_profile_idempotency_qa.py`) will
  INTENTIONALLY turn red after P2; the Owner must NOT touch them and MUST list
  the exact expected failures (file + test + reason) in the P2 handoff;
- an independent P2 QA lane (branching from the P2 head) flips the pinned
  assertions to permanent green and re-runs the full battery; only that
  QA-exact combination proceeds to integration;
- acceptance matrix (CCR §8): 1.1.0 exact; each of profile id/version/
  contentHash/riskTolerance independently flips the hash; preferenceWeights
  flow through contentHash; verified-row fingerprint only; pre-engine uniform
  404 with zero rows; Task 12 numeric zero-drift; both A1 fail-closed codes
  stable; contracts git-clean + official CONTRACT_DRIFT_OK; alembic single head
  `b2c7e9d4a1f6`.

## P0/P1/P2

- P0: none open in this contract lane (adjudication complete; no product risk introduced — text only).
- P1 (blocks P2 acceptance): implement §2 payload EXACTLY (any extra payload delta = violation); content_hash format guard before engine (§3).
- P2 (follow-ups): SIM-02A I2 doc amendments unchanged from SIM-02A; QA P3-a note (idempotency_records.http_status 100..599 DB CHECK sanity) remains assigned to the SIM-02A I1 lane, not to ENG-02.

## Remote verification

- gate zero: 4 refs live-verified exact (main / SIM-02A contract / P1P3 product / P1P3 QA);
- post-push: all 5 refs re-read live (main unchanged at `387041d`; ENG-02
  branch head matches local HEAD; other three unchanged) — recorded in HISTORY.

## Flags

- ready_for_P2_implementation: **YES** (Simulation/Graph Owner Fable5, direct child of edaa842)
- ready_for_public_route: **NO** (SIM-02A §2/§3 double-lock until P2 + P2 QA + I1/I2/I3 integrate)

## Discipline attestation

- Write scope respected: only CCR-20260724-ENG-02.md,
  CCR-20260724-SIM-02A-ADDENDUM-A1.md, this handoff, HEAD, HISTORY.
- Frozen CCR-SIM-02A original file byte-untouched (erratum is additive).
- No force-push/amend/rebase/history rewrite; main not merged or advanced.
- No credentials or secret values are recorded here.
