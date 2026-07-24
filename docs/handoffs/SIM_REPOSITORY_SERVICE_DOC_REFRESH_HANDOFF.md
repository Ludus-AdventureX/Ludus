# SIM_REPOSITORY_SERVICE_DOC_REFRESH_HANDOFF

- role: Simulation/Graph Owner — Repository/Service Documentation Refresh (Fable5 throughout)
- task_type: DOC-ONLY FOLLOW-UP (zero behavior / contract / test-semantics change)
- exact_parent_sha: 7844a1631c0747e2f39e2cbfb73088ed010c98ae (codex/task-simulation-repository-service-r1)
- new_branch: codex/task-simulation-repository-service-r1-doc-refresh
- new_head_sha: (recorded in HISTORY archive and in the lane handoff message after commit/push)
- accepted_contract_addendum (read-only dependency, not merged/cherry-picked/modified):
  codex/ccr-sim-01-addendum-a1 @ b28dda67f9794d705e79ac45c2a1cf2458d7cf7b
- remote_main_at_start: 3ed23b92e0b2a1326518a6f550984abb02f11179 (live ls-remote, exact)

## Changed paths

- services/api/app/simulations/domain.py — module docstring ONLY (the sole product change)
- docs/handoffs/SIM_REPOSITORY_SERVICE_DOC_REFRESH_HANDOFF.md — this document
- HEAD / HISTORY — append-only lifecycle

## Docstring semantics: before -> after

- BEFORE (stale, false): claimed the graph-side wire types (GraphVersion / CausalNode /
  CausalEdge / StrategyVersion / ScenarioVersion / ScoreDefinition / OptionOutcomeMapping /
  RiskWeight / ConstraintRule / GraphBranch) "do not yet exist in the frozen canonical
  contract" and that graph enums were "not-yet-canonical"; also listed OriginMode as a
  reused enum although the module never imports it.
- AFTER (accurate): the canonical graph wire schemas exist on main since CCR-20260724-SIM-01
  in app.simulations.schemas; domain dataclasses are engine-internal immutable value objects
  (not ORM, not wire DTOs, no I/O) assembled deterministically by app.simulations.assembly
  from already-validated canonical persistence/wire data; canonical enum authority is
  app.types (NodeType, SimulationMode, SimulationConvergenceStatus, EdgePolarity,
  GraphVersionStatus, FactorControllability as Controllability, FactorEvidenceStatus as
  EvidenceStatus — pure import aliases); ElementStatus/Normalization/Comparison remain
  engine-internal; Comparison is the executable subset (>, >=, <, <=) and canonical "="
  stays fail-closed (score_constraint_operator_unsupported); edge gating is NOT implemented
  and non-empty enabledEdgeIds stay fail-closed (strategy_edge_gating_unsupported).

## Addendum A1 five rulings — preserved unchanged

1. UUID identity (workspace_id, graph_version_id, id); no node_key/edge_key introduced;
   UUID id ordering untouched.
2. ConstraintComparison "=" kept canonical, not executed; fail-closed code unchanged.
3. enabledEdgeIds fail-closed code unchanged.
4. Enum authority via pure import aliases; no parallel enums.
5. Zero migration/schema/contract/router/API change.

## Zero-behavior proof

- Ancestry: the new commit's sole parent is 7844a16 (verified via git rev-parse HEAD^).
- Product diff 7844a16..new_head: only services/api/app/simulations/domain.py, docstring only.
- AST equivalence: both versions of domain.py parsed, module docstring Expr stripped,
  ast.dump(include_attributes=False) compared -> DOMAIN_EXECUTABLE_AST_EQUIVALENT.
- Byte gate (git blob OIDs vs 7844a16, CRLF-safe): repository.py, assembly.py, service.py,
  errors.py, engine.py, schemas.py, test_simulation_repository_service.py, types.py,
  models.py, migration a3f8c2d47e19, packages/contracts/openapi.json,
  packages/contracts/src/types.gen.ts — all identical (BYTE_GATE=PASS).
- Stale statement scan: "graph-side wire types do not yet exist" -> 0 hits in the tree.

## Regression (disposable Postgres ludus-pg-sim-repo-r1:55434; main venv 3.12.7)

- pytest app/simulations/tests -q: 52 passed (owner count unchanged).
- pytest tests app/simulations/tests -q -W error: 402 passed (full regression unchanged).
- pytest tests/lens_lanes -q: 121 passed (unchanged).
- ruff check services/api: PASS. compileall app: PASS. git diff --check: PASS.
- Contracts: packages/contracts/** zero git diff vs parent and vs index;
  openapi.json/types.gen.ts byte-identical to 7844a16. generate_contracts.ps1 -Check
  TypeScript substep NOT_RUN in this worktree (openapi-typescript unavailable without a new
  dependency install); zero schema/router/contracts change is proven by the blob byte gate;
  the full contract chain closes in independent QA.
- Scope audit: only domain.py + this handoff + HEAD/HISTORY changed. Secret scan: clean.

## Findings

- stale_documentation finding: CLOSED (the false "do not yet exist" claim is removed and
  replaced by the accurate contract state).
- P0: none. P1: none.
- P2: generate_contracts.ps1 TS substep still requires a node_modules-equipped environment
  (pre-existing environment gap, unchanged by this task; QA closes the loop).

## ready_for_independent_qa: YES
