# CCR-20260805-GRAPH-ENTRY-01 — Causal graph build/confirm product path (pressure sandbox gate)

- Status: proposed (implementation pending on `codex/graph-entry-r1`)
- Date: 2026-08-05 (Asia/Shanghai)
- Owner: simulation lane (SIM-02A follow-up)
- Affected surface:
  - New write endpoints for graph draft build + confirmation (graph aggregate)
  - `SandboxWorkspace` empty-state unlock condition (anchors become non-empty)
  - Wire DTO additions only; no change to existing read contracts

## Problem

The G-page pressure workspace stays honest-empty for every ordinary workflow
(invite registration + deep analysis) because the causal graph product path is
not wired end to end. Audit evidence (2026-08-05):

1. **No write surface**: the API exposes no endpoint that creates a
   `CausalGraph` row or saves a `GraphVersion`. `grep` over `app/` finds zero
   `POST/PUT` graph routes; the only `CausalGraph(...)` constructors outside
   tests live in `app/prototype/guest_bootstrap.py` (guest-demo seed only).
2. **Orphaned pure functions**: `app/simulations/graph_builder.py` already
   implements `build_from_report` (draft-only immutable GraphVersion) and
   `confirm_graph_version` (draft → confirmed, with the invariant that no
   unconfirmed node/edge may be promoted) — but no product caller exists
   (callers are tests only).
3. **Front-end review without a backend**: `GraphConfirmationPanel` tracks
   confirmations in React state and never persists them; there is no "save as
   formal version" API behind it. The panel's gate note is honest UI feedback
   only, as its comment states.
4. **User-visible effect**: after a completed deep analysis the factor sandbox
   and deliberation council unlock (they key off analysis factors), but the
   pressure workspace shows "压力测试尚未开放" forever — anchors require a
   `CausalGraph` row with strategy/scenario/score versions
   (`GET /cases/{caseId}/simulations`).

## Change

### 1. Draft build (analysis → draft graph)

- New endpoint `POST /api/workspaces/{workspaceId}/graphs/from-report`
  (relative: `/graphs/from-report`), body: `{ analysisRunId }`.
- Server resolves the run's report artifact, derives nodes/edges per the
  existing report→graph extraction contract (09), calls
  `graph_builder.build_from_report` (pure, unchanged), and persists a
  `CausalGraph` row + immutable DRAFT `GraphVersion` (plus nodes/edges).
- Idempotent per `(workspace, case, analysisRunId)`: a repeat call returns the
  existing draft graph (same pattern as SIM-02A run idempotency).

### 2. Confirmation (draft → formal version)

- New endpoint `POST /api/workspaces/{workspaceId}/graphs/{graphId}/confirm`,
  body: `{ versionId, confirmedNodeIds, confirmedEdgeIds }`.
- Server re-validates the invariant set (every node/edge confirmed; nothing
  unconfirmed promoted), calls `confirm_graph_version` (pure, unchanged), and
  persists the new CONFIRMED version; updates
  `CausalGraph.current_graph_version_id` (service-maintained projection, no FK
  cycle, per `models.py` comment).
- `GET /cases/{caseId}/simulations` anchors then resolve non-empty and the
  pressure workspace unlocks — no change to that read contract.

### 3. Front-end wiring

- `GraphConfirmationPanel` gains a real "保存正式图版本" action calling the
  confirm endpoint; the existing React-state confirmations become the pending
  payload, and the panel shows the server response state (honest busy/error).
- `SandboxWorkspace` empty-state guide (already shipped in
  CCR-20260805-GRAPH-ENTRY-01 follow-up copy fix) stays as the explanatory
  note; no dead button is introduced until the endpoint lands.

## Compatibility

- Additive: new endpoints and a new wire DTO; no field/status changes to
  existing read surfaces, `AnalysisRun`, or the SIM-02A run contract.
- The pure builder functions are reused verbatim — no engine change.
- Migration: none required (tables `causal_graphs` / `graph_versions` /
  `graph_nodes` / `graph_edges` already exist); if a partial-unique index is
  needed for one-draft-per-run it is a new append-only revision.
- OpenAPI/TypeScript regeneration required for the two new endpoints.

## Contract regeneration

Run `scripts/generate_contracts.ps1` (generate then `-Check`); ops count only
grows; `-Check` must return CONTRACT_DRIFT_OK.

## Test plan

- Backend: idempotent draft build (repeat call returns same graph); confirm
  with unconfirmed items → structured invariant failure; confirm with full set
  → CONFIRMED version + anchors now resolve; cross-workspace 404 byte-parity on
  both endpoints (anti-enumeration).
- Frontend: `GraphConfirmationPanel` confirm action drives the endpoint and
  surfaces server error honestly; existing sandbox tests keep passing.
- Browser: invite-registration flow → deep analysis → draft graph appears →
  confirm → pressure workspace unlocks (the exact gap shown in the 2026-08-05
  walkthrough).
