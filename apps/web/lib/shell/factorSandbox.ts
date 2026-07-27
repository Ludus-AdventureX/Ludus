/**
 * Factor sandbox client (three-layer what-if):
 *   Layer 1  GET  /cases/{id}/sandbox           baseline factor state
 *            POST /cases/{id}/sandbox/preview   deterministic re-propagation
 *                                               under user factor overrides
 *   Layer 3  launchAnalysisForCase (decisionLoop) - a full re-analysis run
 *
 * Layer 1 is a pure, reproducible calculator on the server; the client edits
 * factor strengths and re-previews instantly. Nothing here fabricates a live
 * verdict - the deep model re-run is an explicit, separate action.
 */

export class SandboxError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "SandboxError";
    this.status = status;
  }
}

export type FetchLike = typeof fetch;

function defaultFetch(): FetchLike {
  return (input, init) => fetch(input, init);
}

export type SandboxFactor = {
  id: string;
  label: string;
  weight: number;
  value: number;
  baseline: number;
  direction: string;
  source: string;
};

export type SandboxDriver = {
  nodeId: string;
  label: string;
  scoreDelta: number;
  direction: string;
  flipValue: number | null;
};

export type SandboxState = {
  available: boolean;
  outcomeScore: number;
  verdict: "proceed" | "hold";
  factors: SandboxFactor[];
  topDrivers: SandboxDriver[];
  flipThreshold: number;
  engine: string;
};

function normalize(data: Record<string, unknown> | null): SandboxState {
  if (!data || data.available === false) {
    return {
      available: false,
      outcomeScore: 0.5,
      verdict: "hold",
      factors: [],
      topDrivers: [],
      flipThreshold: 0.5,
      engine: "",
    };
  }
  return {
    available: true,
    outcomeScore: Number(data.outcomeScore ?? 0.5),
    verdict: (data.verdict as "proceed" | "hold") ?? "hold",
    factors: (data.factors as SandboxFactor[]) ?? [],
    topDrivers: (data.topDrivers as SandboxDriver[]) ?? [],
    flipThreshold: Number(data.flipThreshold ?? 0.5),
    engine: String(data.engine ?? ""),
  };
}

async function csrfToken(fetchImpl: FetchLike): Promise<string> {
  const r = await fetchImpl("/api/auth/csrf", { credentials: "include" });
  const body = (await r.json().catch(() => null)) as { data?: { csrfToken?: string } } | null;
  const token = body?.data?.csrfToken;
  if (!token) throw new SandboxError("CSRF token 缺失。", r.status);
  return token;
}

async function readData(response: Response): Promise<Record<string, unknown> | null> {
  const body = (await response.json().catch(() => null)) as { data?: Record<string, unknown> } | null;
  if (!response.ok) throw new SandboxError(`沙盘请求失败（HTTP ${response.status}）。`, response.status);
  return body?.data ?? null;
}

/** Layer 1 baseline: the case's factors at their analysed strength. */
export async function loadSandboxBaseline(
  workspaceId: string,
  decisionCaseId: string,
  fetchImpl: FetchLike = defaultFetch(),
): Promise<SandboxState> {
  const path = `/api/workspaces/${encodeURIComponent(workspaceId)}/cases/${encodeURIComponent(decisionCaseId)}/sandbox`;
  let response: Response;
  try {
    response = await fetchImpl(path, { credentials: "include" });
  } catch {
    throw new SandboxError("无法连接 /api 服务。", 0);
  }
  return normalize(await readData(response));
}

/** Layer 1 re-propagation under user overrides ({factorId: value in [0,1]}). */
export async function previewSandbox(
  workspaceId: string,
  decisionCaseId: string,
  nodeOverrides: Record<string, number>,
  fetchImpl: FetchLike = defaultFetch(),
): Promise<SandboxState> {
  const token = await csrfToken(fetchImpl);
  const path = `/api/workspaces/${encodeURIComponent(workspaceId)}/cases/${encodeURIComponent(decisionCaseId)}/sandbox/preview`;
  let response: Response;
  try {
    response = await fetchImpl(path, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
      body: JSON.stringify({ nodeOverrides }),
    });
  } catch {
    throw new SandboxError("无法连接 /api 服务。", 0);
  }
  return normalize(await readData(response));
}
