# SIM_ENG_02_PROFILE_ENFORCEMENT_FAST_FIX_HANDOFF

- Mode: FAST PRODUCT FIX (minimal validation; full battery deferred to the integration gate)
- Role: Simulation/Graph Owner (Fable5)
- Date: 2026-07-25 (Asia/Shanghai)
- Branch: `codex/sim-eng-02-profile-enforcement-fast-fix`
- **Exact parent (live-resolved P2 head): `d43e36eb399900e24ec171c8cf02eff3048cf089`**
  (sole parent; P2's own sole parent re-verified = edaa8421; main `387041d4` and ENG-02
  contract `c8c9167b` re-verified live at lane start; fresh worktree; no amend/rebase/force)
- Fix SHA: recorded in the push section below.
- ready_for_fast_QA: **YES**
- ready_for_public_route: **NO**

## Changed paths (exact, 6 files + lifecycle/handoff)

| Path | Change |
|---|---|
| `app/simulations/engine.py` | `profile: ProfileFingerprint` now keyword-only **REQUIRED** on `compute_input_hash` AND `run_simulation`; explicit `None`/bare-dict → `SimulationInputError` fail-fast; the §2 profile block is now UNCONDITIONAL in the payload — no missing-profile / legacy / mixed 1.1.0 hash mode exists |
| `app/simulations/sensitivity.py` | fast-fix-permitted change ONLY: keyword-only required `profile` param + pass-through of the ONE fingerprint to every internal `run_simulation` call (base + all sweeps + flip grid); zero numeric/perturbation/ordering changes |
| `app/simulations/service.py` | passes the single verified fingerprint into `analyze_sensitivity` (base already received it) |
| `app/simulations/tests/test_simulation_engine.py` | fixed deterministic canonical `OWNER_FP` supplied to all 15 engine/sensitivity call sites; zero numeric-input changes |
| `app/simulations/tests/test_sim_eng_02_profile_hash.py` | +2 probe tests (below); numeric-drift test now compares two fingerprints; e2e counter-hash uses a different fingerprint instead of the removed no-profile mode |
| `app/simulations/tests/test_simulation_repository_service.py` | one direct `compute_input_hash` call now passes the world's verified fingerprint |

domain.py NOT needed (unchanged). ZERO diff: `services/api/tests/**`, `migrations/**`,
`models.py`, `types.py`, `schemas.py`, `packages/contracts/**`, routes/web/main.

## profile-required verdict

**ENFORCED.** Every `ENGINE_VERSION = "sim-engine-1.1.0"` hash/run path requires a verified
`ProfileFingerprint`; ENGINE_VERSION, the `profile{id,version,contentHash}` payload shape,
top-level `riskTolerance`, historical 1.0.0 rows, both Addendum A1 fail-closed codes, and
service tenant/case/profile authority are all unchanged.

## Four no-profile probe results (owner test `test_missing_or_none_profile_is_rejected_no_1_1_0_legacy_mode`)

| probe | result |
|---|---|
| `compute_input_hash` omitted profile | REJECTED (TypeError at call time) ✓ |
| `compute_input_hash(profile=None)` | REJECTED (SimulationInputError fail-fast) ✓ |
| `run_simulation` omitted profile | REJECTED (TypeError at call time) ✓ |
| `run_simulation(profile=None)` | REJECTED (SimulationInputError fail-fast) ✓ |

## Sensitivity call/fingerprint verdict (owner test `test_sensitivity_sweeps_all_use_the_same_fingerprint`)

Captured EVERY engine call inside `analyze_sensitivity` (spherical-robot fixture): base +
all sweep/perturbation/flip-grid calls; **None/missing count = 0**; all captured fingerprints
are the IDENTICAL object (`is` identity), independent of iteration order. Service-path
single-assembly reuse re-proven by the existing `test_base_and_sensitivity_share_single_fingerprint`.

## Verification (fast gates only, per task)

- Owner directed `pytest app/simulations/tests -q`: **84 passed / 0 failed** (82 prior + 2 probes)
- Numeric behavior unchanged: full Task 12 numeric suite (28) green with the fixed
  fingerprint — node results, option scores, convergence, recommendations, flip thresholds
  all byte-identical assertions untouched and passing; numeric-drift test proves two
  different fingerprints → identical numerics, different hashes.
- Static: ruff (app/simulations) PASS; compileall PASS; `git diff --check` clean; conflict
  markers zero; changed-path scope = exactly the 6 files above (+ HEAD/HISTORY/this handoff).
- NOT run (deferred to integration gate by task order): full pytest, lens_lanes,
  persistence/IO, migration lifecycle, generate_contracts, whole-tree ruff. Known consequence
  carried forward: QA-owned pure-engine acceptance tests calling `run_simulation` without a
  profile will now fail until the P2 QA lane updates them (services/api/tests untouched here).

## Remote verification

Post-push live ls-remote re-read recorded in the worklog: main `387041d4` unmoved; contract
`c8c9167b` unmoved; parent P2 branch unmoved at `d43e36eb`; fast-fix branch head = fix SHA.

- No credentials recorded.
