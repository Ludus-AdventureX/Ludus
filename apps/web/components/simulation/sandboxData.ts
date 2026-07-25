// Honest data-availability contract for the sandbox workspace (Task 13),
// following the Session B `caseListRouteAvailable` precedent in
// lib/shell/projects.ts: a single source of truth per missing backend
// surface, no invented endpoints, no mock case data in production.
//
// What EXISTS today (consumed for real by this lane):
//   - POST/GET /api/workspaces/{workspaceId}/simulations/{graphId}/runs
//     (SIM-02A, mounted under the tenancy workspace_router).
// What DOES NOT exist yet (fail-closed, recorded in the Task 13 handoff):
//   - a read route for the confirmed causal graph / graph versions;
//   - a read route for the structured report (conditional recommendation);
//   - a read route for the scenario_planning artifact frames;
//   - any route returning the simulation anchors for a decision case.
//
// Until those routes ship, the production mount renders the honest Phase 0
// empty frame; the full interaction is driven by callers that CAN provide
// real data (and by tests with fixtures). Flip this flag only when the
// canonical case sandbox read surface lands — the UI needs no restructuring.

import type { SandboxCaseData } from "./types";

export const sandboxCaseDataRouteAvailable = false;

/**
 * Resolve the sandbox inputs for a decision case. Today there is no backend
 * read surface for any of the required inputs, so this returns null and the
 * workspace renders its honest empty state (no fabricated graph, report,
 * scenario or anchors).
 */
export function loadSandboxCaseData(decisionCaseId: string): SandboxCaseData | null {
  void decisionCaseId;
  if (!sandboxCaseDataRouteAvailable) return null;
  return null;
}
