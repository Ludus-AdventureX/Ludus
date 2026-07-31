// Read-only consumption of the Task 3 auth/workspace surface for the
// project drawer (Session B). GET /api/auth/session is the only shipped
// read-only directory today: its membership summaries give the user's
// workspaces. There is NO decision-case list route yet — that gap is
// recorded in docs/handoffs/TASK11_PHASE0_SHELL_B_HANDOFF.md and the drawer
// renders an honest empty state instead of inventing a backend.

export type WorkspaceDirectoryEntry = {
  workspaceId: string;
  workspaceName: string;
  role: string;
};

export type ProjectDirectory =
  | { status: "unauthenticated" }
  | { status: "error" }
  | { status: "ready"; workspaces: WorkspaceDirectoryEntry[] };

// The canonical case list route (GET /cases) is now available.
export const caseListRouteAvailable = true;

function parseWorkspaces(payload: unknown): WorkspaceDirectoryEntry[] | null {
  if (typeof payload !== "object" || payload === null) return null;
  const data = (payload as { data?: unknown }).data;
  if (typeof data !== "object" || data === null) return null;
  const memberships = (data as { memberships?: unknown }).memberships;
  if (!Array.isArray(memberships)) return null;
  const workspaces: WorkspaceDirectoryEntry[] = [];
  for (const membership of memberships) {
    if (typeof membership !== "object" || membership === null) return null;
    const { workspaceId, workspaceName, role } = membership as Record<string, unknown>;
    if (typeof workspaceId !== "string" || typeof workspaceName !== "string" || typeof role !== "string") {
      return null;
    }
    workspaces.push({ workspaceId, workspaceName, role });
  }
  return workspaces;
}

export async function fetchProjectDirectory(fetchImpl: typeof fetch = fetch): Promise<ProjectDirectory> {
  let response: Response;
  try {
    response = await fetchImpl("/api/auth/session", {
      method: "GET",
      credentials: "same-origin",
      headers: { accept: "application/json" }
    });
  } catch {
    return { status: "error" };
  }
  if (response.status === 401) return { status: "unauthenticated" };
  if (!response.ok) return { status: "error" };
  try {
    const workspaces = parseWorkspaces(await response.json());
    if (workspaces === null) return { status: "error" };
    return { status: "ready", workspaces };
  } catch {
    return { status: "error" };
  }
}
