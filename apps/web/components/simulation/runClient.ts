// SIM-02A run API client owned by the Task 13 sandbox lane
// (frozen contract CCR-20260724-SIM-02A; consumed, never redefined):
//
//   POST /api/workspaces/{workspaceId}/simulations/{graphId}/runs
//   GET  /api/workspaces/{workspaceId}/simulations/{graphId}/runs/{simulationRunId}
//
// Frozen semantics honored here:
//   - Idempotency-Key travels as an HTTP header (never in the body);
//   - the POST body carries anchors only — mode / version ids / nodeOverrides
//     in raw BUSINESS values; riskTolerance / engineVersion / scoreDefinition
//     version are server-owned and never sent;
//   - cross-tenant / cross-graph scope failures surface as the uniform 404
//     CASE_NOT_FOUND and are presented without existence leakage;
//   - meta.idempotencyReplay is present ONLY on replays;
//   - GET replay returns the byte-equal frozen inputs + results.
//
// The X-CSRF-Token double-submit pattern follows the Task 3 auth surface
// (GET /api/auth/csrf). All calls are same-origin with credentials included.

import type { SimulationAnchors, SimulationRunData } from "./types";

export const IDEMPOTENCY_HEADER = "Idempotency-Key";

export class SimulationApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: unknown;

  constructor(code: string, message: string, status: number, details?: unknown) {
    super(message);
    this.name = "SimulationApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

/** Uniform 404: same-workspace cross-graph and cross-tenant collapse together. */
export function isUniformNotFound(error: unknown): boolean {
  return error instanceof SimulationApiError && error.status === 404;
}

export function isIdempotencyConflict(error: unknown): boolean {
  return error instanceof SimulationApiError && error.code === "IDEMPOTENCY_CONFLICT";
}

export function isGraphNotConfirmed(error: unknown): boolean {
  return error instanceof SimulationApiError && error.code === "GRAPH_NOT_CONFIRMED";
}

export function isNotConverged(error: unknown): boolean {
  return error instanceof SimulationApiError && error.code === "SIMULATION_NOT_CONVERGED";
}

export function isNetworkError(error: unknown): boolean {
  return error instanceof SimulationApiError && error.code === "NETWORK_ERROR";
}

type Envelope = { ok?: boolean; data?: unknown; meta?: { idempotencyReplay?: boolean } };

async function requestJson(
  fetchImpl: typeof fetch,
  path: string,
  init: RequestInit = {},
): Promise<Envelope> {
  let response: Response;
  try {
    response = await fetchImpl(path, { credentials: "include", ...init });
  } catch {
    throw new SimulationApiError("NETWORK_ERROR", "无法连接 /api 服务。", 0);
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
    throw new SimulationApiError(
      error?.code ?? "HTTP_ERROR",
      error?.message ?? `请求失败（HTTP ${response.status}）。`,
      response.status,
      error?.details,
    );
  }
  return (body ?? {}) as Envelope;
}

async function fetchCsrfToken(fetchImpl: typeof fetch): Promise<string> {
  const envelope = await requestJson(fetchImpl, "/api/auth/csrf");
  const token = (envelope.data as { csrfToken?: string } | undefined)?.csrfToken;
  if (!token) {
    throw new SimulationApiError("CSRF_TOKEN_MISSING", "CSRF token 响应缺少 csrfToken。", 200);
  }
  return token;
}

/** A fresh key per explicit run intention; retries of the SAME intention reuse it. */
export function newRunIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `sandbox-${crypto.randomUUID()}`;
  }
  return `sandbox-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export type SimulationRunOutcome = {
  run: SimulationRunData;
  /** true only when the server replayed a committed terminal outcome (§4.9). */
  idempotencyReplay: boolean;
};

export type PostSimulationRunInput = {
  anchors: SimulationAnchors;
  mode: "experimental" | "formal";
  /** Raw business values keyed by graph node id; the server owns any normalization. */
  nodeOverrides: Record<string, number>;
  idempotencyKey: string;
  fetchImpl?: typeof fetch;
};

export async function postSimulationRun({
  anchors,
  mode,
  nodeOverrides,
  idempotencyKey,
  fetchImpl = fetch,
}: PostSimulationRunInput): Promise<SimulationRunOutcome> {
  const csrfToken = await fetchCsrfToken(fetchImpl);
  const envelope = await requestJson(
    fetchImpl,
    `/api/workspaces/${encodeURIComponent(anchors.workspaceId)}/simulations/${encodeURIComponent(anchors.graphId)}/runs`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
        [IDEMPOTENCY_HEADER]: idempotencyKey,
      },
      body: JSON.stringify({
        mode,
        graphVersionId: anchors.graphVersionId,
        strategyVersionId: anchors.strategyVersionId,
        scenarioVersionId: anchors.scenarioVersionId,
        scoreDefinitionId: anchors.scoreDefinitionId,
        decisionMakerProfileId: anchors.decisionMakerProfileId,
        decisionMakerProfileVersion: anchors.decisionMakerProfileVersion,
        nodeOverrides,
      }),
    },
  );
  return {
    run: envelope.data as SimulationRunData,
    idempotencyReplay: envelope.meta?.idempotencyReplay === true,
  };
}

/** GET replay (§6): byte-equal frozen inputs + results for an existing run. */
export async function fetchSimulationRun(
  anchors: Pick<SimulationAnchors, "workspaceId" | "graphId">,
  simulationRunId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<SimulationRunData> {
  const envelope = await requestJson(
    fetchImpl,
    `/api/workspaces/${encodeURIComponent(anchors.workspaceId)}/simulations/${encodeURIComponent(anchors.graphId)}/runs/${encodeURIComponent(simulationRunId)}`,
  );
  return envelope.data as SimulationRunData;
}

/** Replay equivalence: same frozen run identity and inputs on GET. */
export function replayMatchesRun(replay: SimulationRunData, run: SimulationRunData): boolean {
  return (
    replay.simulationRunId === run.simulationRunId &&
    replay.inputHash === run.inputHash &&
    replay.engineVersion === run.engineVersion
  );
}
