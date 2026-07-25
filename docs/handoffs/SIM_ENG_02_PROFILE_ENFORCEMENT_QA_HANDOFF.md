# SIM_ENG_02_PROFILE_ENFORCEMENT_QA_HANDOFF (r1)

- Date: 2026-07-25 (Asia/Shanghai)
- Role: QA for CCR-ENG-02 P2 enforcement fix — EXECUTED BY THE CONTRACT/MAINLINE
  LEAD under an explicit principal directive (governance waiver, see below).
- Branch: `codex/qa-sim-eng-02-profile-enforcement-r1`, direct child of the fix
  head `codex/sim-eng-02-profile-enforcement-fast-fix` @
  `d2ae634f23e9e50a92020ca014d3ce380810f4b1` (single parent = `d43e36eb…`,
  independently re-proven this lane).

## Governance waiver (recorded per audit discipline)

- The project principal explicitly cancelled the independent-QA requirement for
  this slice and assigned QA authority to the Mainline Lead ("取消QA审查，交由
  你来审查，审查无误就合并"). This supersedes, FOR THIS SLICE ONLY, the
  CCR-ENG-02 §7.3 independent-QA-lane requirement. All other discipline
  (write-scope, append-only lifecycle, fresh acceptance, ff-only publication)
  remains in force. Future slices revert to independent QA unless re-waived.

## Addendum correspondence (as requested by the fix owner)

- This QA lane operates under `CCR-20260724-ENG-02-ADDENDUM-A1.md`
  (adjudication branch 19f552c). The fast-fix `d2ae634` predates the addendum
  push but is content-isomorphic to its §4 frozen requirements; the
  correspondence is hereby registered. Independent re-verification of §4.1-§4.8
  was performed by the adjudicator before this lane (engine/sensitivity/service
  signatures, write scope, single-parent, contracts drift).

## QA delta (exactly two QA-owned files)

1. `services/api/tests/test_sim_02a_profile_idempotency_qa.py` — the pinned
   P2-pending test flipped to a permanent green regression per ENG-02 §7.3:
   `ENGINE_VERSION == "sim-engine-1.1.0"`; `profile`/`content_hash` present in
   the hash source; same-rt/different-profile now asserts DIFFERENT inputHash;
   both runs assert engine_version 1.1.0. Fixtures/structure unchanged.
2. `services/api/tests/test_simulation_engine_acceptance.py` — canonical
   deterministic `QA_FP` ProfileFingerprint added and threaded through all 6
   direct engine/sensitivity call sites (the 1.1.0 engine now requires it).
   ALL numeric expectations byte-untouched.

No product file, no owner test, no migration, no contracts touched by QA.

## Fresh acceptance evidence (disposable PG16 @55432, no volume)

- alembic heads = exactly `b2c7e9d4a1f6`; upgrade head; current = b2c7e9d4a1f6;
  alembic check clean; no new migration.
- Full suite `pytest tests app/simulations/tests -q -W error -rxX`:
  **461 passed / 0 failed / 0 xfailed / 0 xpassed** (new frozen count; prior
  main baseline 417 + P1/P3 QA battery + ENG-02/P2 owner suites + this flip).
- Same-db immediately after (no table wipe): `pytest tests/lens_lanes -q` =
  **121 passed** (workspace-scope isolation holds).
- Official `powershell -File scripts/generate_contracts.ps1 -Check` =
  **CONTRACT_DRIFT_OK**; packages/contracts git-clean.
- ruff check services/api: all checks passed; compileall OK; git diff --check
  clean; changed-path set = exactly the two QA files above.
- Addendum §5 non-regression re-confirmed: both CCR-SIM-01 A1 fail-closed codes
  present and mapped; HISTORICAL_ROWS_IMMUTABLE untouched; payload shape §2.

## Verdict

- RELEASE_CONTENT_VERDICT: **PASS** (P0/P1/P2 = 0/0/0 on this combination)
- Merge object: this QA head (exact tested combination = product d2ae634 + this
  QA delta), NOT the bare product head.
- ready_for_public_route: **NO** (unchanged; SIM-02A I1/I2/I3 pending)
- No credentials or secret values are recorded here.
