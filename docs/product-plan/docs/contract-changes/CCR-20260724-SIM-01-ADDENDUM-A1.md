# CCR-20260724-SIM-01 — Addendum A1: Simulation Identity & Engine-Capability Reconciliation

- Date: 2026-07-24 (Asia/Shanghai)
- Adjudicator: Contract/Mainline Lead (contract_lead)
- Status: ACCEPTED (formal correction/addendum to CCR-20260724-SIM-01)
- Baseline adjudicated against: remote main `3ed23b92e0b2a1326518a6f550984abb02f11179` (live-verified); migration head `a3f8c2d47e19`.
- Trigger: SIM_REPOSITORY_CONTRACT_DEPENDENCY_RECONCILIATION for candidate `codex/task-simulation-repository-service-r1` @ `7844a1631c0747e2f39e2cbfb73088ed010c98ae`.

## A1-1. Identity contract verdict: UUID_IDENTITY_CONFIRMED

The original adjudication Q2 wording ("UUID PK + (workspace_id, graph_version_id, node_key/edge_key) unique as business identity") is FORMALLY RETIRED. The canonical business identity of graph nodes and edges is:

    (workspace_id, graph_version_id, id)   — id is the server-generated UUID

Rationale (not an after-the-fact rationalization of the implementation — the entire *published and QA-frozen* contract surface is already uniformly UUID-based, and the key-column variant was never carried into any released artifact):

1. Rows in `graph_nodes`/`graph_edges` are immutable per frozen `graph_version`; the UUID is assigned once at version creation and never reused or remapped, so it satisfies every stability property a business key would provide *within a version*.
2. Every published reference point already uses the UUID `Identifier`: wire `CausalEdge.sourceNodeId/targetNodeId`, `ScenarioVersion.nodeShifts`/`edgeMultipliers` keys, `StrategyVersion.enabledEdgeIds`, `ScoreDefinition.optionOutcomes[].outcomeNodeId`/`riskWeights[].riskNodeId`/`constraintRules[].constraintNodeId`, the same-version composite FKs, `uq_graph_nodes_workspace_version_id`, `uq_graph_edges_workspace_version_id`, and the SIM-01 final QA exact assertions (378-green baseline).
3. Cross-version logical-node continuity (the one capability a human-readable key adds) is a graph-evolution concern owned by provenance/parent links (`parent_version_id`, `source_graph_version_id`, provenance refs), not by row identity. No shipped or in-flight consumer requires cross-version key equality today.
4. Adding `node_key`/`edge_key` now would demand a forward migration with backfill, wire-schema expansion, and re-freezing of all JSONB reference semantics, with zero consumer gain in this prototype window.

Binding rules going forward:

- All JSONB and wire references to nodes/edges use the UUID `id` — uniformly, no mixed keying.
- Deterministic ordering: repositories/assemblers MUST order by explicit `ORDER BY id ASC` (within the already-pinned workspace/version scope) and MUST NOT rely on database default row order. `(id)` is sufficient because ids are unique and immutable per version.
- Any future introduction of `node_key`/`edge_key` (e.g. for cross-version diffing UX) REQUIRES a new CCR and a new forward Alembic revision; it must arrive as an *additional* attribute, never as a replacement identity, and never as an in-place rewrite of `a3f8c2d47e19` (already on main).
- The CCR-20260724-SIM-01 record and `06-data-model.md` identity wording are read subject to this addendum.

## A1-2. Equality operator verdict: FAIL_CLOSED_ACCEPTED_FOR_THIS_SLICE

`ConstraintComparison` keeps its five canonical values (`>`, `>=`, `<`, `<=`, `=`). The Task 12 engine (`sim-engine-1.0.0`) executes only the four inequality comparisons. Registered capability gap:

- `=` is canonical-on-the-wire but NOT YET EXECUTABLE. The repository/service layer MUST reject a ScoreDefinition containing `=` with the stable domain error `score_constraint_operator_unsupported` (candidate 7844a16 does exactly this with an explicit membership check — audited: no fall-through path can coerce `=` to `<=`).
- CCR-SIM-02 (routes/API) MUST NOT advertise ScoreDefinitions containing `=` as executable; the stable error must surface through the API error envelope.
- Implementing equality requires a dedicated engine CCR defining numeric comparison semantics (exact vs tolerance/epsilon), inputHash impact, and engine version bump. Deleting `=` from the canonical enum to fit the engine is forbidden.

## A1-3. Edge gating verdict: FAIL_CLOSED_ACCEPTED_FOR_THIS_SLICE

`StrategyVersion.enabledEdgeIds` remains canonical on the persistence/wire surface. `sim-engine-1.0.0` has no edge-gating execution semantics. Registered capability gap:

- Non-empty `enabledEdgeIds` MUST fail closed with the stable domain error `strategy_edge_gating_unsupported` (candidate behavior audited and accepted). Silently ignoring the field is forbidden.
- CCR-SIM-02 MUST preserve this stable error and MUST NOT document edge gating as implemented.
- Implementing gating requires a dedicated engine CCR defining propagation rules for disabled edges (removal vs strength=0), formal-authorization interaction, inputHash and sensitivity impact, and engine version bump.

## A1-4. Enum authority verdict: PASS

`app.types` is the sole canonical authority for `FactorControllability`, `FactorEvidenceStatus`, `EdgePolarity`, `GraphVersionStatus` (plus `NodeType`, `SimulationMode`, `SimulationConvergenceStatus`). Candidate audit: `domain.py` imports all of these from `app.types`; `FactorControllability as Controllability` and `FactorEvidenceStatus as EvidenceStatus` are pure import aliases preserving the existing engine API — no parallel enum classes exist, so isinstance identity and serialized values cannot diverge. Legitimately retained engine-internal enums (no canonical Python counterpart was ever promoted): `ElementStatus` (node/edge review lifecycle — canonical form is a CHECK-locked string column plus wire Literal), `Normalization` (CHECK-locked string column by CCR-SIM-01 design), `Comparison` (engine-executable subset of `ConstraintComparison`, guarded by A1-2). These MUST NOT be re-declared as PG enums without a new CCR.

## A1-5. Stale documentation verdict: OWNER_FOLLOW_UP_REQUIRED

`domain.py` line 8 still claims graph-side wire types "do not yet exist in the frozen canonical contract" — false since CCR-SIM-01 landed on main. The Simulation Owner must push a comment/docstring-only follow-up commit on top of `7844a16` (no history rewrite) BEFORE QA freezes the exact head. Integration-time product-file edits are rejected to preserve the byte-identity gate discipline.

## A1-6. Candidate disposition: CANDIDATE_REFRESH_REQUIRED

No DB/contract fix is required (A1-1 confirms identity; A1-2/A1-3 accept fail-closed). The candidate needs only the small owner doc follow-up above; QA then runs on the new exact head with these accepted dependencies. Publication follows the standard live-read ff-only flow afterwards.

- P0/P1/P2 from this adjudication: 0 / 0 / 1 (the stale docstring, closed by the owner follow-up).
- No credentials or secret values are recorded here.
