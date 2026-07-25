/**
 * Technical Alpha demo client for the frozen SIM-02A run API contract
 * (docs/product-plan/docs/contract-changes/CCR-20260724-SIM-02A.md):
 *
 *   GET  /api/auth/csrf
 *   POST /api/auth/login
 *   GET  /api/auth/session
 *   POST /api/workspaces/{workspaceId}/simulations/{graphId}/runs
 *   GET  /api/workspaces/{workspaceId}/simulations/{graphId}/runs/{simulationRunId}
 *
 * Every call is same-origin `/api` with `credentials: "include"`; no secret
 * is read from the environment — only public demo fixture identifiers.
 */

export type DemoFixtureConfig = {
  graphId: string;
  graphVersionId: string;
  strategyVersionId: string;
  scenarioVersionId: string;
  scoreDefinitionId: string;
  decisionMakerProfileId: string;
  decisionMakerProfileVersion: number;
};

export type DemoFixtureReadResult =
  | { ok: true; config: DemoFixtureConfig }
  | { ok: false; missing: string[] };

export type SimulationOptionScore = { optionId: string; score: number };
export type SimulationTopDriver = { nodeId: string; scoreDelta: number };

export type SimulationRunData = {
  simulationRunId: string;
  workspaceId: string;
  decisionCaseId: string;
  graphId: string;
  graphVersionId: string;
  strategyVersionId: string;
  scenarioVersionId: string;
  scoreDefinitionId: string;
  scoreDefinitionVersion: string;
  decisionMakerProfileId: string;
  decisionMakerProfileVersion: number;
  riskTolerance: number;
  engineVersion: string;
  scenarioId: string;
  simulationMode: string;
  epsilon: number;
  maxSteps: number;
  steps: number;
  inputHash: string;
  nodeResults: Record<string, number>;
  optionScores: SimulationOptionScore[];
  topDrivers: SimulationTopDriver[];
  recommendationShift: string;
  recommendedOptionId: string | null;
  convergenceStatus: string;
  originModes: string[];
  createdAt: string;
};

export class DemoApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: unknown;

  constructor(code: string, message: string, status: number, details?: unknown) {
    super(message);
    this.name = "DemoApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

/**
 * Reads the public demo fixture. Each variable is referenced statically so
 * Next.js can inline the NEXT_PUBLIC_* values into the client bundle.
 */
export function readDemoFixtureConfig(): DemoFixtureReadResult {
  const raw: Record<string, string | undefined> = {
    NEXT_PUBLIC_DEMO_GRAPH_ID: process.env.NEXT_PUBLIC_DEMO_GRAPH_ID,
    NEXT_PUBLIC_DEMO_GRAPH_VERSION_ID: process.env.NEXT_PUBLIC_DEMO_GRAPH_VERSION_ID,
    NEXT_PUBLIC_DEMO_STRATEGY_VERSION_ID: process.env.NEXT_PUBLIC_DEMO_STRATEGY_VERSION_ID,
    NEXT_PUBLIC_DEMO_SCENARIO_VERSION_ID: process.env.NEXT_PUBLIC_DEMO_SCENARIO_VERSION_ID,
    NEXT_PUBLIC_DEMO_SCORE_DEFINITION_ID: process.env.NEXT_PUBLIC_DEMO_SCORE_DEFINITION_ID,
    NEXT_PUBLIC_DEMO_PROFILE_ID: process.env.NEXT_PUBLIC_DEMO_PROFILE_ID,
    NEXT_PUBLIC_DEMO_PROFILE_VERSION: process.env.NEXT_PUBLIC_DEMO_PROFILE_VERSION,
  };
  const missing = Object.entries(raw)
    .filter(([, value]) => !value || !value.trim())
    .map(([name]) => name);
  const version = Number.parseInt(raw.NEXT_PUBLIC_DEMO_PROFILE_VERSION ?? "", 10);
  if (
    !missing.includes("NEXT_PUBLIC_DEMO_PROFILE_VERSION") &&
    (!Number.isInteger(version) || version < 1)
  ) {
    missing.push("NEXT_PUBLIC_DEMO_PROFILE_VERSION");
  }
  if (missing.length > 0) return { ok: false, missing };
  return {
    ok: true,
    config: {
      graphId: raw.NEXT_PUBLIC_DEMO_GRAPH_ID!.trim(),
      graphVersionId: raw.NEXT_PUBLIC_DEMO_GRAPH_VERSION_ID!.trim(),
      strategyVersionId: raw.NEXT_PUBLIC_DEMO_STRATEGY_VERSION_ID!.trim(),
      scenarioVersionId: raw.NEXT_PUBLIC_DEMO_SCENARIO_VERSION_ID!.trim(),
      scoreDefinitionId: raw.NEXT_PUBLIC_DEMO_SCORE_DEFINITION_ID!.trim(),
      decisionMakerProfileId: raw.NEXT_PUBLIC_DEMO_PROFILE_ID!.trim(),
      decisionMakerProfileVersion: version,
    },
  };
}

type Envelope = { ok?: boolean; data?: unknown; meta?: { idempotencyReplay?: boolean } };

async function requestJson(path: string, init: RequestInit = {}): Promise<Envelope> {
  let response: Response;
  try {
    response = await fetch(path, { credentials: "include", ...init });
  } catch {
    throw new DemoApiError("NETWORK_ERROR", "无法连接 /api 服务，请确认后端可用。", 0);
  }
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    const error =
      body && typeof body === "object" && "error" in body
        ? (body as { error: { code?: string; message?: string; details?: unknown } }).error
        : null;
    throw new DemoApiError(
      error?.code ?? "HTTP_ERROR",
      error?.message ?? `请求失败（HTTP ${response.status}）。`,
      response.status,
      error?.details,
    );
  }
  return (body ?? {}) as Envelope;
}

export async function fetchCsrfToken(): Promise<string> {
  const envelope = await requestJson("/api/auth/csrf");
  const token = (envelope.data as { csrfToken?: string } | undefined)?.csrfToken;
  if (!token) throw new DemoApiError("CSRF_TOKEN_MISSING", "CSRF token 响应缺少 csrfToken。", 200);
  return token;
}

export async function loginDemoAccount(
  csrfToken: string,
  email: string,
  password: string,
): Promise<void> {
  await requestJson("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify({ email, password }),
  });
}

export async function fetchWorkspaceId(): Promise<string> {
  const envelope = await requestJson("/api/auth/session");
  const memberships = (envelope.data as { memberships?: { workspaceId?: string }[] } | undefined)
    ?.memberships;
  const workspaceId = memberships?.[0]?.workspaceId;
  if (!workspaceId) {
    throw new DemoApiError("WORKSPACE_MISSING", "Demo 账号没有可用的 workspace membership。", 200);
  }
  return workspaceId;
}

export type SimulationRunOutcome = {
  run: SimulationRunData;
  idempotencyReplay: boolean;
};

export async function createSimulationRun(
  workspaceId: string,
  csrfToken: string,
  config: DemoFixtureConfig,
  idempotencyKey: string,
): Promise<SimulationRunOutcome> {
  const envelope = await requestJson(
    `/api/workspaces/${encodeURIComponent(workspaceId)}/simulations/${encodeURIComponent(config.graphId)}/runs`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
        "Idempotency-Key": idempotencyKey,
      },
      body: JSON.stringify({
        mode: "experimental",
        graphVersionId: config.graphVersionId,
        strategyVersionId: config.strategyVersionId,
        scenarioVersionId: config.scenarioVersionId,
        scoreDefinitionId: config.scoreDefinitionId,
        decisionMakerProfileId: config.decisionMakerProfileId,
        decisionMakerProfileVersion: config.decisionMakerProfileVersion,
      }),
    },
  );
  return {
    run: envelope.data as SimulationRunData,
    idempotencyReplay: envelope.meta?.idempotencyReplay === true,
  };
}

export async function fetchSimulationReplay(
  workspaceId: string,
  graphId: string,
  simulationRunId: string,
): Promise<SimulationRunData> {
  const envelope = await requestJson(
    `/api/workspaces/${encodeURIComponent(workspaceId)}/simulations/${encodeURIComponent(graphId)}/runs/${encodeURIComponent(simulationRunId)}`,
  );
  return envelope.data as SimulationRunData;
}

export type DemoFlowStep = "csrf" | "login" | "session" | "run" | "replay";

export type DemoFlowResult = {
  workspaceId: string;
  run: SimulationRunData;
  idempotencyReplay: boolean;
  replay: SimulationRunData;
};

export function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `demo-${crypto.randomUUID()}`;
  }
  return `demo-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/** Runs the full demo flow: csrf → login → session → POST run → GET replay. */
export async function runDemoFlow(
  config: DemoFixtureConfig,
  credentials: { email: string; password: string },
  onStep?: (step: DemoFlowStep) => void,
): Promise<DemoFlowResult> {
  onStep?.("csrf");
  const csrfToken = await fetchCsrfToken();
  onStep?.("login");
  await loginDemoAccount(csrfToken, credentials.email, credentials.password);
  onStep?.("session");
  const workspaceId = await fetchWorkspaceId();
  onStep?.("run");
  const { run, idempotencyReplay } = await createSimulationRun(
    workspaceId,
    csrfToken,
    config,
    newIdempotencyKey(),
  );
  onStep?.("replay");
  const replay = await fetchSimulationReplay(workspaceId, config.graphId, run.simulationRunId);
  return { workspaceId, run, idempotencyReplay, replay };
}
