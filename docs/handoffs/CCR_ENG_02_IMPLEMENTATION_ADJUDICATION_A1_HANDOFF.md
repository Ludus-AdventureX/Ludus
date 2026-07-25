# CCR_ENG_02_IMPLEMENTATION_ADJUDICATION_A1_HANDOFF

- Date: 2026-07-25 (Asia/Shanghai)
- Role: Contract/Mainline Lead — ENG-02 Implementation Conformance Adjudicator
- Mode: CONTRACT ADJUDICATION / NO PRODUCT MODIFICATION / NO MAIN MERGE

## Remote verification

| ref | SHA | status |
|---|---|---|
| main | `387041d40442faf16557b266ef3f844b7af8fb69` | live-verified, NOT advanced |
| SIM-02A contract | `0289b2e36a7765891e4f1908231ac2384c541318` | unchanged |
| ENG-02 contract | `codex/ccr-eng-02-profile-aware-input-hash-r1` @ `c8c9167b219fa8aa06bf9769776f49706f43b219` | unchanged (normative source) |
| P2 parent (P1/P3 QA) | `edaa8421c330de7cfe02a53c1e38574533e99c48` | unchanged |
| **exact full P2 product SHA** | `codex/sim-eng-02-profile-aware-input-hash-r1` @ **`d43e36eb399900e24ec171c8cf02eff3048cf089`** | resolved live via ls-remote (short d43e36e never used as authority) |
| adjudication branch | `codex/ccr-eng-02-implementation-adjudication-a1` (base c8c9167; head = this commit, re-read after push) | new |

Ancestry: `git rev-list --parents d43e36e…` = exactly one parent `edaa842…`;
P2 delta vs edaa842 = HEAD/HISTORY, owner handoff, assembly/domain/engine/
service.py, owner test `test_sim_eng_02_profile_hash.py` — inside the frozen P2
write scope; `services/api/tests/**`, migrations, contracts untouched.

## Exact engine/sensitivity call graph (at d43e36e)

```
compute_input_hash(graph, strategy, scenario, score_def, risk_tolerance,
                   mode, node_overrides, epsilon, max_steps,
                   *, profile: ProfileFingerprint | None = None)   [engine.py L313-324]
  └─ if profile is not None: payload["profile"] = {id, version, contentHash} [L358-362]
     (profile=None → 1.1.0 payload WITHOUT profile block; type guard only when not None [L335])

run_simulation(..., *, profile: ProfileFingerprint | None = None)  [engine.py L368-379]
  └─ compute_input_hash(..., profile=profile)                      [L401]
  └─ result.engine_version = ENGINE_VERSION ("sim-engine-1.1.0")   [L41, L490]

callers of run_simulation:
  1. service.run_and_record                [service.py L220-230]  profile=profile_fingerprint  ✔ conformant
  2. sensitivity.analyze_sensitivity run() [sensitivity.py L58-68] NO profile argument          ✘ base + EVERY sweep
  3. Task 12 owner engine tests            [tests/test_simulation_engine.py, 17 call sites]     ✘ zero profile references

callers of analyze_sensitivity:
  1. service.run_and_record (include_sensitivity=True) [service.py L236-245] — does NOT pass the fingerprint (function has no parameter)

fingerprint construction (single point, conformant):
  assembly.assemble_profile_fingerprint(row) [assembly.py L88-117] — verified row only,
  ^sha256:[0-9a-f]{64}$ gate → frozen_reference_incomplete; built EXACTLY ONCE [service.py L186-189]
```

## Answers to the 8 audit questions

1. `compute_input_hash` without ProfileFingerprint: SUCCEEDS; uses
   `ENGINE_VERSION = "sim-engine-1.1.0"`; hash preimage LACKS the profile block.
2. `run_simulation` without ProfileFingerprint: SUCCEEDS; returns
   sim-engine-1.1.0-tagged results; inputHash LACKS the profile block.
3. Explicit `profile=None`: SUCCEEDS (the `is not None` guard skips both the
   type check and the block).
4. Sensitivity base run: does NOT use a fingerprint (no parameter exists).
5. Sensitivity sweep runs: every perturbation/sweep run also runs WITHOUT a
   fingerprint — same closure, same omission.
6. Violating internal path EXISTS in production: every
   `include_sensitivity=True` service request produces 1.1.0 results whose
   inputHash lacks the profile block (base + sweeps inside analyze_sensitivity).
7. Optional-parameter motive: CONFIRMED — Task 12 owner engine tests have 17
   run_simulation/compute_input_hash call sites and ZERO profile references;
   the default exists so they pass without a Profile fixture.
8. sensitivity.py MUST be modified: `run()` calls `run_simulation` directly
   inside the module; no legal injection point exists in the currently allowed
   files (service cannot thread a fingerprint through a parameterless
   signature; monkeypatching is not a product mechanism).

## Verdicts

| key | verdict |
|---|---|
| no-mixed-mode verdict (A) | **PROFILE_REQUIRED_FOR_ALL_ENGINE_1_1_HASHES** — c8c9167 §1 "There is no mixed mode and no opt-in flag" + §2 unconditional profile block + §2 "Delta = exactly two things … Any other payload difference is a contract violation" (quotes verified byte-exact against the frozen blob) |
| sensitivity fingerprint verdict (B) | **EVERY_BASE_AND_SWEEP_RUN_MUST_RECEIVE_SAME_FINGERPRINT** — c8c9167 §4.1 "the sensitivity path may not omit, substitute, or re-resolve any of them" |
| optional parameter verdict | keyword-only `profile=None` default is NOT authorized by the contract; it exists solely for Task 12 test convenience (Q7) and creates the forbidden third payload shape; must be removed |
| Task 12 fixture verdict (D) | owner tests MUST add a canonical test ProfileFingerprint; "tests unchanged" is NOT a ground for an optional production path; numeric expectations unchanged (zero-drift stands); inputHash expectation changes are contract-expected |
| sensitivity.py scope verdict (C) | **SENSITIVITY_PY_SCOPE_EXPANSION_APPROVED** — fingerprint pass-through ONLY; no numeric/perturbation-order/convergence/scoring change; same-fingerprint proof via object identity or value equality required |
| contract addendum required | **YES** — `docs/product-plan/docs/contract-changes/CCR-20260724-ENG-02-ADDENDUM-A1.md` (this branch): grants the sensitivity.py scope expansion and freezes the fix requirements. The two normative questions themselves were NOT ambiguous; the addendum does not alter any c8c9167 ruling |
| product fix required | **YES — PRODUCT_FIX_REQUIRED** |

## Exact minimal product fix scope (frozen in the addendum §4)

1. remove the `None` default: `compute_input_hash`/`run_simulation` fail closed
   without a valid ProfileFingerprint (type guard unconditional, before any
   hash/numeric work);
2. no None/default mixed path anywhere in the engine surface;
3. `analyze_sensitivity` gains a REQUIRED fingerprint parameter; base + every
   sweep receive the SAME object; service passes the fingerprint it already
   builds once (service.py L186-189);
4. Task 12/owner tests (`app/simulations/tests/**`) add a canonical test
   fingerprint; numeric expectations untouched;
5. no numeric algorithm changes; no `services/api/tests/**` changes (QA-owned);
   no migration (head stays `b2c7e9d4a1f6`); no routes; no contracts delta
   (official `-Check` = CONTRACT_DRIFT_OK);
6. fix branch: ONLY direct parent = `d43e36eb399900e24ec171c8cf02eff3048cf089`.

## P0/P1/P2

- **P0**: engine optional-profile path + sensitivity omission (the two
  violations above) — block QA acceptance and everything downstream.
- **P1**: same-fingerprint proof test (identity/value equality across base +
  sweeps) as part of the fix slice.
- **P2**: none new; SIM-02A I-slices and doc amendments unchanged.

## Flags

- ready_for_final_QA: **NO — PRODUCT_FIX_REQUIRED first**; after the fix lands
  (direct child of d43e36e), independent QA re-runs preflight + flips the
  pinned P1/P3 assertions per CCR-ENG-02 §7.
- ready_for_public_route: **NO**

## Discipline attestation

- Read-only audit performed via `git show` at exact SHAs; no product file
  checked out or modified; write scope = addendum + this handoff + HEAD/HISTORY.
- No force-push/amend/rebase/history rewrite; main not merged or advanced.
- No credentials or secret values are recorded here.
