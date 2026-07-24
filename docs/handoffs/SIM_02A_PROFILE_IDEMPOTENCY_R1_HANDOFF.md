# SIM_02A_PREREQUISITE_PROFILE_IDEMPOTENCY_R1 — QA Handoff

- Task: CCR-SIM-02A prerequisites P1 + P3 (profile persistence + idempotency schema)
- Role: Simulation/Graph Owner (Fable5 throughout)
- Date: 2026-07-25 (Asia/Shanghai)
- Branch: `codex/sim-02a-profile-idempotency-r1`
- Base main (live ls-remote verified at lane start): `387041d40442faf16557b266ef3f844b7af8fb69`
- Authoritative contract (consumed READ-ONLY via `git show`; not merged, not cherry-picked,
  no contract documents brought into this branch):
  `codex/ccr-sim-02a-run-api-contract @ 0289b2e36a7765891e4f1908231ac2384c541318`
- Migration: previous single head `a3f8c2d47e19` (untouched) → new single head `b2c7e9d4a1f6`
- ready_for_qa: YES (with the mandatory QA-suite revision list in §5)

## 1. Delivered (product)

| File | Change |
|---|---|
| `services/api/app/models.py` | additive: `DecisionMakerProfile` (immutable/append-only, business identity `UNIQUE(workspace_id, profile_id, version)`, row UUID PK storage-only), `IdempotencyRecord` (`UNIQUE(workspace_id, route_key, idempotency_key)`, enum-checked `response_kind` string, no PG enum by contract), plus the tenant-scoped composite FK `simulation_runs(workspace_id, decision_maker_profile_id, decision_maker_profile_version) → decision_maker_profiles(workspace_id, profile_id, version)` ON DELETE RESTRICT |
| `services/api/migrations/versions/b2c7e9d4a1f6_add_decision_maker_profiles_and_idempotency_records.py` | ONE forward revision (P1+P3 combined per contract §4): both tables + the runs FK via SIM-01 discipline — orphan preflight (explicit RuntimeError, never assumes empty table) → `ADD CONSTRAINT ... NOT VALID` → `VALIDATE CONSTRAINT` → `pg_constraint.convalidated = true` assertion; reversible downgrade |
| `services/api/app/simulations/profile_hash.py` | NEW pure helper `compute_profile_content_hash`: sha256 over canonical JSON (sorted keys, `,`/`:` separators, UTF-8) of every frozen field; JSONB key order never trusted |
| `services/api/app/simulations/repository.py` | `get_decision_maker_profile` (exact tenant-scoped `(workspace, profile_id, version)` SELECT) and `insert_decision_maker_profile` (append-only; `content_hash` computed server-side — the signature accepts no caller hash). NO update/delete surface exists |
| `services/api/app/simulations/service.py` | `SimulationRunRequest.risk_tolerance` REMOVED (callers select only profile id+version); the service resolves riskTolerance server-side from the frozen profile row; ghost id / wrong version / foreign workspace / wrong-case-scoped profile all collapse into the uniform `CASE_NOT_FOUND` 404 fail-closed BEFORE any engine work |
| `services/api/app/simulations/tests/*` | seeded workspace-global profile v1 in `seed_world`; `request_for` now anchors the seeded profile; NEW `test_sim_02a_profile_idempotency.py` (17 tests) + `conftest.py` (fixture re-export only) |

Explicitly NOT changed: `engine.py` (`compute_input_hash`, `ENGINE_VERSION`), `domain.py`,
`assembly.py`, `schemas.py`, `errors.py` (no new error class was needed — uniform 404 reuses
`simulation_scope_not_found`), routes (none created), `packages/contracts/**`, `apps/web/**`,
`scripts/**`, canonical docs 06/09/10, `services/api/tests/**` (QA domain, untouched),
`a3f8c2d47e19` migration. Both Addendum A1 fail-closed behaviors intact.

## 2. Contract semantics implemented

- Profile scope: `decision_case_id IS NULL` = workspace-global, usable by any case of the
  workspace (explicit owner test); non-NULL binds to exactly one case, service-enforced +
  composite-FK-enforced at DB level.
- Immutability: new version = new inserted row; repository/service expose no UPDATE/DELETE
  (proven by owner test via introspection); no DB trigger in this slice per task text.
- content_hash: server-computed only; same payload → same hash; any frozen field change →
  different hash; key-order independent (all owner-tested).
- riskTolerance: resolved server-side; run row + wire self-check + view all carry the frozen
  profile value; a new profile version with different riskTolerance moves the engine
  `inputHash` (via the riskTolerance input — profile IDENTITY enters the hash only with P2 /
  CCR-ENG-02, out of scope here by contract §3).
- idempotency_records: persistence schema only. No header parsing, no replay/conflict flow,
  no route — owner test asserts the service module contains no idempotency logic.

## 3. Verification (disposable PG16 `ludus-pg-sim-02a` @ localhost:55436, main venv, no new env)

| Gate | Result |
|---|---|
| `alembic heads` | single head `b2c7e9d4a1f6` |
| `alembic upgrade head` / `check` | PASS / "No new upgrade operations detected" |
| `alembic downgrade -1` → `upgrade head` round trip | PASS; `current` = b2c7e9d4a1f6 |
| `pg_constraint.convalidated` for the new FK + both unique keys | all `t` (queried directly) |
| owner suite `app/simulations/tests` | **69 passed** (52 r1 baseline + 17 new P1/P3) |
| mainline `python -m pytest -q -W error` | **361 passed, 4 failed** — the 4 failures are exactly the adjudicated QA-baseline breakage, see §5 |
| ruff check app migrations | PASS |
| compileall app migrations | PASS |

## 4. Adjudications taken during the lane

1. Task text was truncated at its line 386 (P3 detail / validation / handoff sections
   missing). Adjudicated with the coordinating owner: proceed with CCR-SIM-02A §4 as the
   authoritative P3 spec and the r1 verification conventions. No guessing beyond the frozen
   contract.
2. QA-baseline collision (pre-declared, then adjudicated: "implement per contract, list the
   breakage"): contract §2's claim that "internal service-level callers (tests) are
   unaffected until the route lands" is FALSE once the FK lands — recorded here as a
   contract erratum for the Contract Lead.

## 5. KNOWN QA BREAKAGE — mandatory revision list for the QA Owner (I3 scope)

All 4 failures are structural consequences of the frozen P1 contract, not implementation
bugs. `services/api/tests/**` is this lane's forbidden zone; the QA Owner must revise:

| Test (services/api/tests) | Why it now fails | Suggested revision |
|---|---|---|
| `test_models.py::test_core_table_set_and_workspace_scope` | asserts the exact table inventory; two new tables exist | add `decision_maker_profiles`, `idempotency_records` to the expected set |
| `test_models.py::test_task_19a_simulation_replay_numeric_constraints_are_enforced` | base insert uses a ghost `decision_maker_profile_id: uuid4()` → new composite FK rejects it before the numeric probes run | seed a frozen profile row and reference it |
| `test_sim01_graph_contract_qa.py::test_simulation_run_frozen_refs_reject_cross_workspace_targets` | `_run_values` uses a ghost profile ref → baseline insert itself now violates the FK | seed per-workspace profiles; optionally extend the attack matrix with the profile ref (it now rejects cross-workspace targets too) |
| `test_simulation_repository_service_qa.py::test_run_level_parameters_each_change_input_hash` | encodes the OLD contract: caller-supplied `risk_tolerance=0.61` and ghost-profile runs | riskTolerance is no longer a request field; move the rt-changes-hash assertion to profile-version selection (owner test `test_new_profile_version_risk_tolerance_changes_input_hash` shows the pattern); ghost-profile now must expect uniform 404 |

Note for QA: the shared seeding helpers QA loads by file path (`seed_world`, `request_for`)
were updated in place — most QA service-path tests keep passing unchanged because they now
transparently consume the seeded workspace-global profile v1 (riskTolerance 0.5, identical
to the old hard-coded request value, so frozen hashes/counts elsewhere are unaffected).

## 6. Environment / next steps

- Disposable container `ludus-pg-sim-02a` (postgres:16-alpine, localhost:55436,
  user/db `decision_lab`) kept for QA; removable after acceptance.
- Next: independent QA (对话 3) on this branch + QA-suite revision above; then P2
  (CCR-ENG-02 engine hash + ENGINE_VERSION bump — this lane, separate branch) remains the
  last prerequisite blocking the public POST route; Mainline Lead assembles the wave.
- No credentials recorded anywhere in this handoff.
