/**
 * Technical Alpha demo client for the frozen SIM-02A run API contract
 * (docs/product-plan/docs/contract-changes/CCR-20260724-SIM-02A.md):
 *
 *   GET  /api/auth/csrf
 *   POST /api/auth/guest
 *   POST /api/workspaces/{workspaceId}/simulations/{graphId}/runs
 *   GET  /api/workspaces/{workspaceId}/simulations/{graphId}/runs/{simulationRunId}
 *
 * Every call is same-origin `/api` with `credentials: "include"`. No secret
 * is read from the environment — the guest endpoint returns the workspace
 * and fixture identifiers the page needs.
 */

export type DemoFixtureIds = {
  graphId: string;
  graphVersionId: string;
  strategyVersionId: string;
  scenarioVersionId: string;
  scoreDefinitionId: string;
  decisionMakerProfileId: string;
  decisionMakerProfileVersion: number;
};

export type GuestSession = {
  workspaceId: string;
  fixture: DemoFixtureIds;
};

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

/**
 * POST /api/auth/guest — create or restore a guest account. The server owns
 * the guest identity (cookie-bound session); the response returns a FLAT
 * ``data`` payload (workspaceId + frozen fixture identifiers) which the
 * client normalizes into ``GuestSession.fixture``.
 */
type GuestFlatPayload = {
  workspaceId?: string;
  decisionCaseId?: string;
  graphId?: string;
  graphVersionId?: string;
  strategyVersionId?: string;
  scenarioVersionId?: string;
  scoreDefinitionId?: string;
  decisionMakerProfileId?: string;
  decisionMakerProfileVersion?: number;
};

export async function fetchGuestSession(csrfToken: string): Promise<GuestSession> {
  const envelope = await requestJson("/api/auth/guest", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
  });
  const data = envelope.data as GuestFlatPayload | undefined;
  const missing = validateGuestPayload(data);
  if (missing.length > 0) {
    throw new DemoApiError(
      "GUEST_PAYLOAD_INVALID",
      `Guest 响应缺少必要字段：${missing.join(", ")}。`,
      200,
    );
  }
  return {
    workspaceId: data!.workspaceId!,
    fixture: {
      graphId: data!.graphId!,
      graphVersionId: data!.graphVersionId!,
      strategyVersionId: data!.strategyVersionId!,
      scenarioVersionId: data!.scenarioVersionId!,
      scoreDefinitionId: data!.scoreDefinitionId!,
      decisionMakerProfileId: data!.decisionMakerProfileId!,
      decisionMakerProfileVersion: data!.decisionMakerProfileVersion!,
    },
  };
}

function validateGuestPayload(data: GuestFlatPayload | undefined): string[] {
  if (!data) return ["data"];
  const missing: string[] = [];
  if (!data.workspaceId) missing.push("workspaceId");
  const required: (keyof DemoFixtureIds)[] = [
    "graphId",
    "graphVersionId",
    "strategyVersionId",
    "scenarioVersionId",
    "scoreDefinitionId",
    "decisionMakerProfileId",
    "decisionMakerProfileVersion",
  ];
  for (const key of required) {
    const value = data[key];
    if (value === undefined || value === null || value === "") missing.push(key);
  }
  if (
    data.decisionMakerProfileVersion !== undefined &&
    (!Number.isInteger(data.decisionMakerProfileVersion) ||
      data.decisionMakerProfileVersion < 1)
  ) {
    missing.push("decisionMakerProfileVersion");
  }
  return missing;
}

export type SimulationRunOutcome = {
  run: SimulationRunData;
  idempotencyReplay: boolean;
};

export async function createSimulationRun(
  workspaceId: string,
  csrfToken: string,
  fixture: DemoFixtureIds,
  idempotencyKey: string,
): Promise<SimulationRunOutcome> {
  const envelope = await requestJson(
    `/api/workspaces/${encodeURIComponent(workspaceId)}/simulations/${encodeURIComponent(fixture.graphId)}/runs`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
        "Idempotency-Key": idempotencyKey,
      },
      body: JSON.stringify({
        mode: "experimental",
        graphVersionId: fixture.graphVersionId,
        strategyVersionId: fixture.strategyVersionId,
        scenarioVersionId: fixture.scenarioVersionId,
        scoreDefinitionId: fixture.scoreDefinitionId,
        decisionMakerProfileId: fixture.decisionMakerProfileId,
        decisionMakerProfileVersion: fixture.decisionMakerProfileVersion,
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

export type DemoFlowStep = "csrf" | "guest" | "run" | "replay";

export type DemoFlowResult = {
  workspaceId: string;
  fixture: DemoFixtureIds;
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

/**
 * Establishes (or restores) the guest session: csrf → POST /api/auth/guest.
 * The guest step is idempotent at the server: a fresh browser gets a new guest,
 * an existing cookie-bound session is restored transparently.
 */
export async function establishGuestSession(
  onStep?: (step: DemoFlowStep) => void,
): Promise<GuestSession> {
  onStep?.("csrf");
  const csrfToken = await fetchCsrfToken();
  onStep?.("guest");
  return fetchGuestSession(csrfToken);
}

/**
 * Runs the simulation against an already-established guest session:
 * csrf → POST run → GET replay. The caller supplies the workspace + fixture
 * returned by establishGuestSession.
 */
export async function runSimulation(
  workspaceId: string,
  fixture: DemoFixtureIds,
  onStep?: (step: DemoFlowStep) => void,
): Promise<SimulationRunOutcome & { replay: SimulationRunData }> {
  onStep?.("csrf");
  const csrfToken = await fetchCsrfToken();
  onStep?.("run");
  const outcome = await createSimulationRun(
    workspaceId,
    csrfToken,
    fixture,
    newIdempotencyKey(),
  );
  onStep?.("replay");
  const replay = await fetchSimulationReplay(workspaceId, fixture.graphId, outcome.run.simulationRunId);
  return { ...outcome, replay };
}
