# CCR_SIM_02A_RUN_API_CONTRACT_HANDOFF

- Date: 2026-07-25 (Asia/Shanghai)
- Role: Contract/Mainline Lead — Simulation Run API Contract Owner
- Mode: CONTRACT-FIRST / TEXT-ONLY ADJUDICATION (no product implementation, no main merge)

## Remote verification

- live main SHA (gate zero AND post-push re-read): `387041d40442faf16557b266ef3f844b7af8fb69` — unchanged, untouched
- migration head: `a3f8c2d47e19` (single head, verified via alembic heads in this worktree)
- contract branch: `codex/ccr-sim-02a-run-api-contract`
- contract branch head: recorded in HISTORY lifecycle entry and in the final push re-read (see repository)
- contract file: `docs/product-plan/docs/contract-changes/CCR-20260724-SIM-02A.md`

## Verdicts (normative source = the CCR file; this is the index)

| key | verdict |
|---|---|
| route_scope_verdict | **RUN_CREATE_AND_REPLAY_ONLY** (POST run + GET replay; SIM-02B graph read, SIM-03 from-report, SIM-04 working copies/review, SIM-05 branches/compare/rollback, SIM-06 adoption all deferred) |
| profile_authority_verdict | **PROFILE_PERSISTENCE_PREREQUISITE** (immutable versioned decision_maker_profiles + content hash + tenant-scoped run FK; service resolves riskTolerance from frozen Profile; client sends profile ID/version only) |
| public_post_run_blocked_by_profile | **true** |
| input_hash_verdict | **ENGINE_HASH_FIX_REQUIRED** (profile ID/version/content hash into compute_input_hash; ENGINE_VERSION bump from sim-engine-1.0.0) |
| engine_ccr_required | **true** (CCR-ENG-02, Simulation/Graph Owner; public POST blocked until it lands) |
| idempotency_verdict | **GENERIC_IDEMPOTENCY_RECORDS** (new idempotency_records table; UNIQUE(workspace_id, route_key, idempotency_key); normalized request hash incl. path graphId; atomic same-transaction insert with the run row; failed requests do not consume keys; loser-of-race replays committed outcome) |
| migration_required | **true** (forward revision on top of a3f8c2d47e19 — never rewritten; may combine profile tables + idempotency table in one new revision) |
| non-convergence verdict | **B** — formal non-converged run IS persisted, HTTP is 409 `SIMULATION_NOT_CONVERGED` with details.simulationRunId + convergenceStatus; experimental non-converged is 201 with truthful convergenceStatus; downstream formal consumers must re-gate |
| CSRF/rate-limit verdict | POST: require_csrf + per-(workspace,user) fail-closed limiter (10 runs/5min default) + budget guard (maxSteps ≤ 64, ≤ 500 nodes / 2000 edges) ⇒ `SIMULATION_BUDGET_EXCEEDED` 422; GET: no CSRF; rate limiting and idempotency strictly independent |

## Exact schemas / tables (frozen in CCR §5–§9)

- exact POST request schema: CCR §5 (10 fields; extra=forbid; camelCase;
  decisionCaseId derived; scoreDefinitionVersion/engineVersion/riskTolerance
  SERVER-OWNED and absent from the request; includeSensitivity not exposed,
  server-fixed true; formal runs require empty nodeOverrides)
- exact POST/GET response schema: CCR §6 `SimulationRunData` (same data schema on
  both routes; new wire DTO from SimulationRunView; ORM never at the boundary;
  workspace/case/graph anchors echoed; topDrivers always present, possibly empty)
- exact HTTP status semantics: CCR §7 (201 create; replay = original status +
  meta.idempotencyReplay=true; GET 200; formal non-converged 409-with-persisted-run)
- exact error mapping table: CCR §8 (type/code-based only, message string matching
  forbidden; SimulationAuthorizationError/formal_authorization_rejected →
  `GRAPH_NOT_CONFIRMED` 409 — closes prior P3; Addendum A1 codes
  `strategy_edge_gating_unsupported` / `score_constraint_operator_unsupported`
  appear VERBATIM lower-snake as envelope codes, 422; uniform `CASE_NOT_FOUND`
  404 for all existence/anchor denials incl. path-graphId mismatch and
  unverifiable Profile refs; `SIMULATION_INPUT_INVALID` 422 with safe domainCode;
  `SIMULATION_PERSISTENCE_FAILED` 500 retryable, never leaks SQLAlchemy/asyncpg;
  `IDEMPOTENCY_CONFLICT` 409; `GRAPH_VERSION_NOT_FOUND`/`SCENARIO_VERSION_MISMATCH`
  reserved for SIM-02B/SIM-04 surfaces)
- capability_matrix: CCR §9 (POST experimental/formal: membership + contribute;
  GET: membership only; simulations router never re-resolves membership)

## Router mounting plan (CCR §10)

- new module `services/api/app/simulations/routes.py`; relative prefix
  `/simulations/{graphId}`; mounted via `workspace_router.include_router(...)`;
  include line + app/main.py + OpenAPI catalog registration owned by Contract Lead.

## Generated contracts plan (CCR §10)

- intentional drift: new request/response/error schemas enter openapi.json +
  types.gen.ts via official generation; `-Check` = CONTRACT_DRIFT_OK becomes the
  NEW baseline; graph wire types NOT registered this slice; "zero contracts
  change" is retired as a gate for the simulation surface after the
  implementation wave.

## Implementation slices / owners (CCR §11)

- PREREQUISITE (P0, block public POST): P1 profile persistence, P2 engine hash
  CCR-ENG-02, P3 idempotency migration — Simulation/Graph Owner (Fable5).
- IMPLEMENTATION: I1 schemas/routes/error-mapping/idempotency/budget/repository
  get-run/service adapter (Simulation Owner); I2 mounting/CSRF-capability wiring/
  contracts regeneration/10-api P2 doc amendments (Contract Lead); I3 independent
  QA battery (QA Owner). Exclusive write paths per slice are frozen in CCR §11.

## P0/P1/P2 contract dependencies

- P0: profile persistence; engine hash fix (CCR-ENG-02); idempotency migration.
- P1: repository get_simulation_run read; wire DTO layer; type-based error mapping.
- P2: 10-api-and-events.md amendments (request example fields, new error codes,
  reserved codes note, meta.idempotencyReplay documentation).

## Next owner

- **Simulation/Graph Owner (Fable5)**: start PREREQUISITE P1/P2/P3 on a fresh
  branch from remote-verified main ≥ 387041d, consuming CCR-20260724-SIM-02A and
  Addendum A1 read-only; then I1; Contract Lead executes I2; QA executes I3;
  Mainline Lead integrates via the standard live-read ff-only publication chain.

## Discipline attestation

- No files outside `docs/product-plan/docs/contract-changes/CCR-20260724-SIM-02A.md`,
  `docs/handoffs/**`, `HEAD`, `HISTORY` were modified on this branch.
- No force-push, no amend, no rebase, no history rewrite; main not advanced.
- No credentials or secret values are recorded here.
