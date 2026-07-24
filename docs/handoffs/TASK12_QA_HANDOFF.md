# TASK12_QA_HANDOFF — Deterministic Simulation Engine (r2)

- QA owner: qa_release (branch `codex/qa-mainline-258a94d`); independent review, one handoff per candidate.
- Candidate: `codex/task-12-simulation-engine-r2` @ **`b7060d5a631ac67f67ff8fb0b536c5295b8f5ae9`** (owner: simulation_graph).
- exact_tested_head: fresh detached worktree at `b7060d5` (byte-identical product tree) + QA-owned overlay `services/api/tests/test_simulation_engine_acceptance.py` (11 new tests; named `*_acceptance` to avoid a module-basename collision with the owner suite) + updated shared `conftest.py`. No product file modified by QA.

## Verdicts

- **IMPLEMENTATION_QA_VERDICT: PASS** — P0=0, P1=0, P2=0 new findings.
- **REMOTE_STATUS**: handoff claims live-verified `remote_branch_sha == b7060d5`; QA's own re-read hit the intermittent 443 block this round → recorded as **unverified-by-QA (blocked)**; content verdict unaffected.
- Integration note: engine-only slice; graph wire types / migration 0005 / routes / persistence correctly deferred behind the pending graph-side CCR to contract_lead. QA adopts `services/api/tests/test_simulation_engine_acceptance.py` as the canonical acceptance path (owner-proposed name `test_simulation_engine.py` collides with the owner suite module and was adjusted).

## Gate results (G-01..G-09)

- G-01 base: `b7060d5~1 == 258a94d`; fresh ✔
- G-02 scope: exactly `HEAD`/`HISTORY` + `services/api/app/simulations/**` (5 files) — inside simulation_graph write_scope; zero canonical/schema/migration/web change ✔ (owner claim "byte-identical to old fc36b33" is their migration method; QA verdict rests on this tree's own results)
- G-03 full suite `-W error` incl. owner suite: **157 passed, 1 xfailed, 0 failed** (baseline 118 + 11 QA acceptance + 28 owner tests) ✔
- G-04 migrations: none ✔ · G-05 contracts: unchanged ✔
- G-06 ruff + compileall (`app/simulations` + QA file): PASS ✔
- G-07 secret scan + `git diff --check` over `258a94d..b7060d5`: clean ✔
- G-08/09 observed ✔

## QA acceptance evidence (independent, beyond adopting the owner suite)

- **SG-01 determinism**: two fixture rebuilds + runs produce identical `input_hash`, identical `engine_version` (`sim-engine-1.0.0`) and a **byte-identical full-result serialization** (canonical JSON of the entire SimulationResult).
- **inputHash sensitivity**: hash changes when strategy, epsilon, or maxSteps change.
- **SG-04/06 authorization**: formal mode rejects a draft GraphVersion (message names `confirmed`); experimental mode accepts it; ScenarioVersion dataclass has no riskTolerance field.
- **Input validation**: epsilon<=0, maxSteps<=0, riskTolerance outside [0,1] all rejected (SimulationInputError).
- **SG-09 fixture contract**: ≥8 nodes, ≥10 edges, ≥3 scenarios, ≥2 strategies verified; baseline scenario converges within 12 steps, recommends `rescue_pilot`, all normalized values clamped to [0,1].
- **Hard-constraint flip**: the procurement scenario flips the recommendation away from rescue.
- **Sensitivity**: flip conditions exist, procurement cycle is the top flip driver, and repeated sensitivity analyses serialize identically (determinism).
- Owner suite (28 tests) additionally covers pos/neg edges, delay, damping/clipping, converged/max_steps/saturated/invalid statuses, non-finite abstain, scenario field constraints, eligible-edge differences — all PASS under `-W error`.

## Findings

- P0/P1/P2: none new. Known-risk note carried from the owner: fixture numeric design values couple the flip-threshold assertions to the pending scoring CCR — re-run this acceptance file if the CCR alters edge strengths/score weights.
