# CCR-20260724-ENG-02 — ADDENDUM A1 (Implementation Adjudication: mandatory profile + sensitivity.py scope)

- Status: ADJUDICATED — ADDITIVE, ORIGINAL CCR-ENG-02 TEXT NOT REWRITTEN
- Date: 2026-07-25 (Asia/Shanghai)
- Owner: Contract/Mainline Lead — ENG-02 Implementation Conformance Adjudicator
- Applies to: `docs/product-plan/docs/contract-changes/CCR-20260724-ENG-02.md`
  (frozen at `codex/ccr-eng-02-profile-aware-input-hash-r1` @
  `c8c9167b219fa8aa06bf9769776f49706f43b219`)
- Adjudicated product: `codex/sim-eng-02-profile-aware-input-hash-r1` @
  `d43e36eb399900e24ec171c8cf02eff3048cf089` (full SHA resolved live; single
  direct parent = `edaa8421c330de7cfe02a53c1e38574533e99c48`, proven)
- Trigger: SIM_ENG_02_PROFILE_AWARE_INPUT_HASH_QA_PREFLIGHT r2 raised two
  adjudication items (keyword-only optional ProfileFingerprint; sensitivity
  sweeps possibly running with None fingerprint).

## 1. Adjudication of the two items (against the frozen c8c9167 text)

### A. No-mixed-mode — verdict: PROFILE_REQUIRED_FOR_ALL_ENGINE_1_1_HASHES

The frozen contract is NOT ambiguous:

- §1: "From that commit on, EVERY newly persisted SimulationRun carries
  `engine_version = "sim-engine-1.1.0"` and a §2-shaped inputHash. There is no
  mixed mode and no opt-in flag."
- §2: "compute_input_hash gains one nested top-level object under the
  canonical key `profile`" — unconditional presence, and the frozen AFTER
  payload example contains the profile block;
- §2 closing law: "Delta = exactly two things: the engineVersion value and the
  new profile object. Any other payload difference is a contract violation."

A `sim-engine-1.1.0` hash whose payload omits the profile block is therefore a
THIRD payload shape the contract does not authorize. "The service always passes
it" is explicitly insufficient — the prohibition binds every production AND
internal call path.

### B. Sensitivity fingerprint — verdict: EVERY_BASE_AND_SWEEP_RUN_MUST_RECEIVE_SAME_FINGERPRINT

§4.1 of the frozen contract: "The base run and every sensitivity sweep
iteration use the SAME frozen profile fingerprint (id/version/contentHash) and
the same riskTolerance; the sensitivity path may not omit, substitute, or
re-resolve any of them." No omission authorization exists.

## 2. Product audit result — PRODUCT_FIX_REQUIRED

At `d43e36e` (source evidence, exact lines in the handoff):

- `engine.compute_input_hash(..., profile: ProfileFingerprint | None = None)`
  succeeds without a fingerprint and emits a 1.1.0 payload WITHOUT the profile
  block (violates §1/§2);
- `engine.run_simulation(..., profile=None)` succeeds and produces
  1.1.0-tagged results whose inputHash lacks the profile block (violates §1/§2);
- `sensitivity.analyze_sensitivity` has NO profile parameter; its internal
  `run()` closure calls `run_simulation` without a fingerprint for the base run
  AND every sweep (violates §4.1);
- `service.run_and_record` passes the fingerprint to the persisted run but
  calls `analyze_sensitivity` without it — so every include_sensitivity=True
  request exercises the violating internal path;
- Task 12 engine tests (17 call sites, zero profile references) are the only
  beneficiaries of the optional parameter.

## 3. Scope expansion — SENSITIVITY_PY_SCOPE_EXPANSION_APPROVED

The original CCR-ENG-02 §7 ALLOWED list omitted
`services/api/app/simulations/sensitivity.py`. Conformant repair is impossible
without it (the `run()` closure calls `run_simulation` directly; no legal
injection point exists outside the module). This addendum ADDS, for the ENG-02
fix slice only:

- ALLOWED: `services/api/app/simulations/sensitivity.py` — restricted to
  ProfileFingerprint pass-through ONLY:
  - add a required profile/fingerprint parameter and thread the SAME object
    into the base run and every perturbation/sweep run;
  - FORBIDDEN in the same file: any change to sensitivity numeric algorithms,
    perturbation step computation or ordering, convergence, scoring, flip
    detection, or driver ranking;
  - the fix must be provably pass-through: tests must show (object identity or
    value equality) that base and all sweeps received the same fingerprint.

All other §7 allowed/forbidden entries remain exactly as frozen.

## 4. Frozen minimal fix requirements (binding on the fix slice)

1. `compute_input_hash` and `run_simulation` MUST NOT succeed without a valid
   `ProfileFingerprint` under `sim-engine-1.1.0`: remove the `None` default;
   an absent/None/mistyped fingerprint fails closed (the existing
   "assembly-verified ProfileFingerprint" type guard pattern, now
   unconditional) BEFORE any hash or numeric work.
2. No None/default mixed path remains anywhere in the engine surface.
3. All Task 12/owner callers (`app/simulations/tests/**`) provide a canonical
   test ProfileFingerprint fixture. Numeric expectations MUST NOT change;
   inputHash expectation changes are contract-expected (§1/§2). "Tests would
   need fixtures" is NOT a ground for keeping an optional production path.
4. `analyze_sensitivity` gains a required fingerprint parameter; service passes
   the SAME verified fingerprint it already builds once per run.
5. No numeric algorithm changes anywhere (Task 12 zero-drift stands).
6. `services/api/tests/**` untouched (QA-owned).
7. No migration (head stays `b2c7e9d4a1f6`), no routes, no
   `packages/contracts/**` delta; official `-Check` stays `CONTRACT_DRIFT_OK`.
8. The fix branch MUST have `d43e36eb399900e24ec171c8cf02eff3048cf089` as its
   ONLY direct parent (no rebase, no history rewrite, no bare re-derivation).

## 5. Non-regression guard

- Both Addendum A1 (CCR-SIM-01) fail-closed codes remain untouched:
  `score_constraint_operator_unsupported`, `strategy_edge_gating_unsupported`.
- HISTORICAL_ROWS_IMMUTABLE, hash payload shape (§2), trust boundary (§3), and
  every other ENG-02 ruling remain exactly as frozen at c8c9167.
- ready_for_public_route remains **NO**.
- No credentials or secret values are recorded here.
