/**
 * In-case deep-analysis launch client (second half of the core decision loop;
 * guest bootstrap + case creation live in lib/shell/createCase.ts):
 *
 *   GET  /api/auth/csrf
 *   GET  /api/workspaces/{ws}/cases/{decisionCaseId}
 *   POST /api/workspaces/{ws}/cases/{decisionCaseId}/analysis-charters
 *   POST /api/workspaces/{ws}/analysis-charters/{charterId}/confirm
 *   POST /api/workspaces/{ws}/analysis-charters/{charterId}/runs
 *   GET  /api/workspaces/{ws}/analyses/{analysisRunId}
 *
 * Same-origin `/api` with credentials:"include", the {ok,data} envelope and
 * CSRF double-submit — the exact pattern proven by lib/demo/simulationDemo.ts
 * and lib/shell/createCase.ts. Every function accepts an injectable fetch
 * implementation for tests.
 */

export class DecisionLoopError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: unknown;

  constructor(code: string, message: string, status: number, details?: unknown) {
    super(message);
    this.name = "DecisionLoopError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

type Envelope = { ok?: boolean; data?: unknown; meta?: Record<string, unknown> };

export type FetchLike = typeof fetch;

function defaultFetch(): FetchLike {
  return (input, init) => fetch(input, init);
}

async function requestJson(
  fetchImpl: FetchLike,
  path: string,
  init: RequestInit = {},
): Promise<Envelope> {
  let response: Response;
  try {
    response = await fetchImpl(path, { credentials: "include", ...init });
  } catch {
    throw new DecisionLoopError("NETWORK_ERROR", "无法连接 /api 服务，请确认后端可用。", 0);
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
    throw new DecisionLoopError(
      error?.code ?? "HTTP_ERROR",
      error?.message ?? `请求失败（HTTP ${response.status}）。`,
      response.status,
      error?.details,
    );
  }
  return (body ?? {}) as Envelope;
}

export async function fetchCsrfToken(fetchImpl: FetchLike = defaultFetch()): Promise<string> {
  const envelope = await requestJson(fetchImpl, "/api/auth/csrf");
  const token = (envelope.data as { csrfToken?: string } | undefined)?.csrfToken;
  if (!token) throw new DecisionLoopError("CSRF_TOKEN_MISSING", "CSRF token 响应缺少 csrfToken。", 200);
  return token;
}

export type CaseAnalysisSeed = {
  decisionSubjectId: string;
  decisionQuestion: string;
};

export async function getCaseAnalysisSeed(
  workspaceId: string,
  decisionCaseId: string,
  fetchImpl: FetchLike = defaultFetch(),
): Promise<CaseAnalysisSeed> {
  const envelope = await requestJson(
    fetchImpl,
    `/api/workspaces/${encodeURIComponent(workspaceId)}/cases/${encodeURIComponent(decisionCaseId)}`,
  );
  const data = envelope.data as
    | { decisionSubjectId?: string; decisionQuestion?: string; title?: string }
    | undefined;
  if (!data?.decisionSubjectId) {
    throw new DecisionLoopError("CASE_DETAIL_INVALID", "案件详情缺少 decisionSubjectId。", 200);
  }
  return {
    decisionSubjectId: data.decisionSubjectId,
    decisionQuestion: data.decisionQuestion ?? data.title ?? "",
  };
}

function randomHex(bytes: number): string {
  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    const buffer = new Uint8Array(bytes);
    crypto.getRandomValues(buffer);
    return Array.from(buffer, (b) => b.toString(16).padStart(2, "0")).join("");
  }
  let out = "";
  while (out.length < bytes * 2) out += Math.floor(Math.random() * 16).toString(16);
  return out.slice(0, bytes * 2);
}

function newUuid(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  const hex = randomHex(16);
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-4${hex.slice(13, 16)}-8${hex.slice(17, 20)}-${hex.slice(20, 32)}`;
}

/** Canonical five-lens set required by the FULL analysis level. */
export const FULL_LENS_TYPES = [
  "porter_five_forces",
  "pre_mortem",
  "counterparty_response_matrix",
  "scenario_planning",
  "meadows_leverage_points",
] as const;

export type AnalysisLevel = "focused" | "full";

/** Charter body proven live against the deployed stack. */
export function buildCharterBody(
  decisionSubjectId: string,
  decisionQuestion: string,
  level: AnalysisLevel = "focused",
  extraAssumptions: string[] = [],
) {
  return {
    decisionSubjectId,
    caseVersion: 1,
    caseSnapshotHash: `sha256:${randomHex(32)}`,
    analysisLevel: level,
    decisionQuestion,
    dossierSnapshotVersion: 1,
    dossierSnapshotHash: `sha256:${randomHex(32)}`,
    goals: [{ id: "g1", text: "看清这项取舍的关键前提" }],
    constraints: [
      { id: "c1", text: "以现有资源与时间窗口为边界" },
      // Layer-3 injection: sandbox what-if assumptions become REAL charter
      // constraints, so the new run genuinely reasons under them (the worker
      // feeds the confirmed charter to every stage).
      ...extraAssumptions.slice(0, 5).map((text, index) => ({
        id: `c-sandbox-${index + 1}`,
        text: text.slice(0, 300),
      })),
    ],
    optionIds: ["opt_a", "opt_b"],
    preferenceWeights: { risk: 0.5, speed: 0.5 },
    requiredStrategicLensTypes: level === "full" ? [...FULL_LENS_TYPES] : ([] as string[]),
    methodId: "hardtech-market-direction",
    methodVersion: "1.1.0",
    methodContentHash: `sha256:${randomHex(32)}`,
    formalAnalysisAllowed: true,
  };
}

export async function createCharter(
  workspaceId: string,
  decisionCaseId: string,
  seed: CaseAnalysisSeed,
  csrfToken: string,
  fetchImpl: FetchLike = defaultFetch(),
  level: AnalysisLevel = "focused",
  extraAssumptions: string[] = [],
): Promise<{ charterId: string }> {
  const envelope = await requestJson(
    fetchImpl,
    `/api/workspaces/${encodeURIComponent(workspaceId)}/cases/${encodeURIComponent(decisionCaseId)}/analysis-charters`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
      body: JSON.stringify(buildCharterBody(seed.decisionSubjectId, seed.decisionQuestion, level, extraAssumptions)),
    },
  );
  const charterId = (envelope.data as { charterId?: string } | undefined)?.charterId;
  if (!charterId) throw new DecisionLoopError("CHARTER_PAYLOAD_INVALID", "Charter 创建响应缺少 charterId。", 200);
  return { charterId };
}

export async function confirmCharter(
  workspaceId: string,
  charterId: string,
  csrfToken: string,
  fetchImpl: FetchLike = defaultFetch(),
): Promise<void> {
  await requestJson(
    fetchImpl,
    `/api/workspaces/${encodeURIComponent(workspaceId)}/analysis-charters/${encodeURIComponent(charterId)}/confirm`,
    { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken } },
  );
}

export async function createRun(
  workspaceId: string,
  charterId: string,
  csrfToken: string,
  fetchImpl: FetchLike = defaultFetch(),
  level: AnalysisLevel = "focused",
): Promise<{ analysisRunId: string; status: string }> {
  const envelope = await requestJson(
    fetchImpl,
    `/api/workspaces/${encodeURIComponent(workspaceId)}/analysis-charters/${encodeURIComponent(charterId)}/runs`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
        "Idempotency-Key": `loop-${newUuid()}`,
      },
      body: JSON.stringify({
        analysisLevel: level,
        cynefinGateResultId: newUuid(),
        runManifestHash: `sha256:${randomHex(32)}`,
      }),
    },
  );
  const data = envelope.data as { analysisRunId?: string; status?: string } | undefined;
  if (!data?.analysisRunId) throw new DecisionLoopError("RUN_PAYLOAD_INVALID", "Run 创建响应缺少 analysisRunId。", 200);
  return { analysisRunId: data.analysisRunId, status: data.status ?? "queued" };
}

export type RunSnapshot = {
  status: string;
  progress: number;
  lastResumableStage: string | null;
};

/**
 * POST /analyses/{runId}/cancel - idempotent cooperative cancellation.
 *
 * Offered when a run sits in `queued` for too long, which in practice means the
 * analysis worker is not running: without an exit the user's only option was to
 * stare at a frozen panel.
 */
export async function cancelRun(
  workspaceId: string,
  analysisRunId: string,
  fetchImpl: FetchLike = defaultFetch(),
): Promise<void> {
  const csrfToken = await fetchCsrfToken(fetchImpl);
  await requestJson(
    fetchImpl,
    `/api/workspaces/${encodeURIComponent(workspaceId)}/analyses/${encodeURIComponent(analysisRunId)}/cancel`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    },
  );
}

export async function getRunStatus(
  workspaceId: string,
  analysisRunId: string,
  fetchImpl: FetchLike = defaultFetch(),
): Promise<RunSnapshot> {
  const envelope = await requestJson(
    fetchImpl,
    `/api/workspaces/${encodeURIComponent(workspaceId)}/analyses/${encodeURIComponent(analysisRunId)}`,
  );
  const data = envelope.data as
    | { status?: string; progress?: number; lastResumableStage?: string | null }
    | undefined;
  if (!data?.status) throw new DecisionLoopError("RUN_STATUS_INVALID", "分析状态响应缺少 status。", 200);
  return {
    status: data.status,
    progress: typeof data.progress === "number" ? data.progress : 0,
    lastResumableStage: data.lastResumableStage ?? null,
  };
}

export type LaunchStep = "csrf" | "seed" | "charter" | "confirm" | "run";

export type LaunchedAnalysis = {
  charterId: string;
  analysisRunId: string;
  status: string;
};

/** csrf -> case seed -> charter -> confirm -> run, reporting each step. */
export async function launchAnalysisForCase(
  workspaceId: string,
  decisionCaseId: string,
  options: {
    fetchImpl?: FetchLike;
    onStep?: (step: LaunchStep) => void;
    level?: AnalysisLevel;
    /** Layer-3: sandbox what-if assumptions injected as charter constraints. */
    extraAssumptions?: string[];
    /** R2: clarifier-adopted rewrite replaces the seed decision question. */
    questionOverride?: string;
  } = {},
): Promise<LaunchedAnalysis> {
  const fetchImpl = options.fetchImpl ?? defaultFetch();
  const level = options.level ?? "focused";
  options.onStep?.("csrf");
  const csrfToken = await fetchCsrfToken(fetchImpl);
  options.onStep?.("seed");
  const seed = await getCaseAnalysisSeed(workspaceId, decisionCaseId, fetchImpl);
  const question = options.questionOverride?.trim();
  if (question) seed.decisionQuestion = question;
  options.onStep?.("charter");
  const { charterId } = await createCharter(
    workspaceId, decisionCaseId, seed, csrfToken, fetchImpl, level,
    options.extraAssumptions ?? [],
  );
  options.onStep?.("confirm");
  await confirmCharter(workspaceId, charterId, csrfToken, fetchImpl);
  options.onStep?.("run");
  const run = await createRun(workspaceId, charterId, csrfToken, fetchImpl, level);
  return { charterId, analysisRunId: run.analysisRunId, status: run.status };
}

export const TERMINAL_RUN_STATUSES = new Set([
  "ready",
  "blocked",
  "cancelled",
  "needs_attention",
]);

/** Poll GET /analyses/{runId} until a terminal status (or abort/timeout). */
export async function pollRunUntilTerminal(
  workspaceId: string,
  analysisRunId: string,
  options: {
    fetchImpl?: FetchLike;
    onTick?: (snapshot: RunSnapshot) => void;
    intervalMs?: number;
    maxTicks?: number;
    signal?: AbortSignal;
  } = {},
): Promise<RunSnapshot> {
  const fetchImpl = options.fetchImpl ?? defaultFetch();
  const intervalMs = options.intervalMs ?? 3000;
  const maxTicks = options.maxTicks ?? 200;
  let last: RunSnapshot = { status: "queued", progress: 0, lastResumableStage: null };
  for (let tick = 0; tick < maxTicks; tick += 1) {
    if (options.signal?.aborted) return last;
    last = await getRunStatus(workspaceId, analysisRunId, fetchImpl);
    options.onTick?.(last);
    if (TERMINAL_RUN_STATUSES.has(last.status)) return last;
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new DecisionLoopError("RUN_POLL_TIMEOUT", "分析轮询超时，run 仍未到达终态。", 0, last);
}

// --- SSE-driven watching (polling stays as the fallback) ---------------------

/** Minimal EventSource surface (mirrors the evidence.ts precedent). */
export type RunEventSourceLike = {
  addEventListener(type: string, listener: (event: { data?: unknown }) => void): void;
  close(): void;
};

export type RunEventSourceFactory = (url: string) => RunEventSourceLike;

/** One stage's visible thinking (the digest riding analysis.stage.completed). */
export type RunDigest = {
  headline?: string;
  keyFindings?: string[];
  risks?: string[];
  openQuestions?: string[];
  /** Which brain spoke (R1: heterogeneous adversary support). */
  model?: string;
  cognitiveSource?: "heterogeneous" | "primary";
};

/** A trace observation surfaced to the UI from the run's SSE event stream. */
export type RunTraceEvent = {
  type: string;
  stage?: string;
  digest?: RunDigest;
  findings?: Array<Record<string, unknown>>;
};

function parseTraceEvent(data: unknown): RunTraceEvent | null {
  if (typeof data !== "string" || !data) return null;
  try {
    const envelope = JSON.parse(data) as {
      type?: string;
      payload?: Record<string, unknown>;
    };
    const type = envelope.type ?? "";
    const payload = envelope.payload ?? {};
    const digest = payload.digest as RunDigest | undefined;
    const findings = payload.findings as Array<Record<string, unknown>> | undefined;
    if (type === "analysis.stage.completed" && digest) {
      return { type, stage: String(payload.stage ?? ""), digest };
    }
    // Independent enrichment roles ride research.packet.completed with an
    // enrichmentRole marker + their own digest; surface them in the trace as
    // pseudo-stages so the user sees the safety anchor's blind spots and the
    // chief of staff's actions live.
    const enrichmentRole = payload.enrichmentRole as string | undefined;
    if (enrichmentRole && digest) {
      return { type, stage: enrichmentRole, digest };
    }
    if (Array.isArray(findings) && findings.length > 0) {
      return { type, findings };
    }
    return null;
  } catch {
    return null;
  }
}

/** Default factory: the browser EventSource, when the runtime provides one. */
export function defaultRunEventSourceFactory(): RunEventSourceFactory | null {
  if (typeof EventSource === "undefined") return null;
  return (url: string) => new EventSource(url, { withCredentials: true });
}

/**
 * Event-driven run watching over GET /analyses/{runId}/events (SSE frames use
 * `event:` = canonical category). Every observed event triggers a status
 * re-read (GET stays the source of truth), with a slow safety poll so a
 * dropped stream cannot strand the UI. When no EventSource is available the
 * caller-visible behaviour degrades to the plain 3s poll.
 */
export async function watchRunUntilTerminal(
  workspaceId: string,
  analysisRunId: string,
  options: {
    fetchImpl?: FetchLike;
    onTick?: (snapshot: RunSnapshot) => void;
    onTrace?: (trace: RunTraceEvent) => void;
    factory?: RunEventSourceFactory | null;
    safetyPollMs?: number;
    signal?: AbortSignal;
    maxTicks?: number;
  } = {},
): Promise<RunSnapshot> {
  const factory = options.factory === undefined ? defaultRunEventSourceFactory() : options.factory;
  if (!factory) {
    return pollRunUntilTerminal(workspaceId, analysisRunId, {
      fetchImpl: options.fetchImpl,
      onTick: options.onTick,
      signal: options.signal,
      maxTicks: options.maxTicks,
    });
  }
  const fetchImpl = options.fetchImpl ?? defaultFetch();
  const safetyPollMs = options.safetyPollMs ?? 15000;
  const maxTicks = options.maxTicks ?? 400;

  let wake: (() => void) | null = null;
  const kick = () => {
    wake?.();
    wake = null;
  };
  const url =
    `/api/workspaces/${encodeURIComponent(workspaceId)}` +
    `/analyses/${encodeURIComponent(analysisRunId)}/events`;
  let source: RunEventSourceLike | null = null;
  const onMessage = (event: { data?: unknown }) => {
    if (options.onTrace) {
      const trace = parseTraceEvent(event.data);
      if (trace) options.onTrace(trace);
    }
    kick();
  };
  try {
    source = factory(url);
    for (const category of ["agent.status", "agent.task", "error"]) {
      source.addEventListener(category, onMessage);
    }
  } catch {
    source = null; // stream refused: the safety poll below still completes
  }

  let last: RunSnapshot = { status: "queued", progress: 0, lastResumableStage: null };
  try {
    for (let tick = 0; tick < maxTicks; tick += 1) {
      if (options.signal?.aborted) return last;
      last = await getRunStatus(workspaceId, analysisRunId, fetchImpl);
      options.onTick?.(last);
      if (TERMINAL_RUN_STATUSES.has(last.status)) return last;
      await new Promise<void>((resolve) => {
        wake = resolve;
        setTimeout(resolve, safetyPollMs);
      });
    }
  } finally {
    source?.close();
  }
  throw new DecisionLoopError("RUN_POLL_TIMEOUT", "分析监听超时，run 仍未到达终态。", 0, last);
}
