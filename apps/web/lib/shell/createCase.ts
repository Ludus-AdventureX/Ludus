// Guest-backed decision case create flow for the empty-state shells.
// Wire contract (all same-origin /api, credentials included):
//
//   GET  /api/auth/csrf                      -> { data: { csrfToken } }
//   POST /api/auth/guest                     -> { data: { workspaceId, ... } }
//        (ENABLE_GUEST_ALPHA gate: disabled answers a uniform 404)
//   POST /api/workspaces/{workspaceId}/cases -> { data: CaseCreateData }
//        (require_csrf; body CaseCreateRequest { decisionQuestion })
//
// The guest step is idempotent at the server: a fresh browser gets a new
// guest workspace, an existing cookie-bound session is restored transparently
// (same behaviour the /demo simulation flow relies on).

export type CaseCreateStep = "csrf" | "guest" | "create";

export class CaseCreateFlowError extends Error {
  readonly code: string;
  readonly status: number;
  readonly step: CaseCreateStep;

  constructor(code: string, message: string, status: number, step: CaseCreateStep) {
    super(message);
    this.name = "CaseCreateFlowError";
    this.code = code;
    this.status = status;
    this.step = step;
  }
}

type Envelope = { ok?: boolean; data?: unknown };

async function requestJson(
  fetchImpl: typeof fetch,
  step: CaseCreateStep,
  path: string,
  init: RequestInit = {}
): Promise<Envelope> {
  let response: Response;
  try {
    response = await fetchImpl(path, { credentials: "include", ...init });
  } catch {
    throw new CaseCreateFlowError("NETWORK_ERROR", "无法连接 /api 服务，请稍后重试。", 0, step);
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
        ? (body as { error?: { code?: string; message?: string } }).error
        : null;
    throw new CaseCreateFlowError(
      error?.code ?? "HTTP_ERROR",
      error?.message ?? `请求失败（HTTP ${response.status}）。`,
      response.status,
      step
    );
  }
  return (body ?? {}) as Envelope;
}

export type CreatedDecisionCase = {
  workspaceId: string;
  decisionCaseId: string;
  version: number;
  title: string;
  clarifyingQuestions: string[];
};

/**
 * csrf -> guest session -> POST /cases. Returns the canonical identifiers the
 * shell needs to open the real case route. Every failure surfaces as a
 * CaseCreateFlowError so the form can keep an honest, human-readable notice.
 */
export async function createDecisionCase(
  decisionQuestion: string,
  fetchImpl: typeof fetch = fetch
): Promise<CreatedDecisionCase> {
  const csrfEnvelope = await requestJson(fetchImpl, "csrf", "/api/auth/csrf");
  const csrfToken = (csrfEnvelope.data as { csrfToken?: string } | undefined)?.csrfToken;
  if (!csrfToken) {
    throw new CaseCreateFlowError("CSRF_TOKEN_MISSING", "CSRF token 响应缺少 csrfToken。", 200, "csrf");
  }

  let guestEnvelope: Envelope;
  try {
    guestEnvelope = await requestJson(fetchImpl, "guest", "/api/auth/guest", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken }
    });
  } catch (error) {
    // The gate answers a uniform 404 while ENABLE_GUEST_ALPHA is off; keep the
    // message actionable instead of pretending the button did nothing.
    if (error instanceof CaseCreateFlowError && error.status === 404) {
      throw new CaseCreateFlowError(
        "GUEST_UNAVAILABLE",
        "访客通道当前未开启，暂时无法建立决策项目。",
        404,
        "guest"
      );
    }
    throw error;
  }
  const workspaceId = (guestEnvelope.data as { workspaceId?: string } | undefined)?.workspaceId;
  if (!workspaceId) {
    throw new CaseCreateFlowError("GUEST_PAYLOAD_INVALID", "Guest 响应缺少 workspaceId。", 200, "guest");
  }

  const createEnvelope = await requestJson(
    fetchImpl,
    "create",
    `/api/workspaces/${encodeURIComponent(workspaceId)}/cases`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
      body: JSON.stringify({ decisionQuestion })
    }
  );
  const data = createEnvelope.data as
    | { decisionCaseId?: string; version?: number; title?: string; clarifyingQuestions?: string[] }
    | undefined;
  if (!data?.decisionCaseId) {
    throw new CaseCreateFlowError("CASE_PAYLOAD_INVALID", "创建响应缺少 decisionCaseId。", 200, "create");
  }
  return {
    workspaceId,
    decisionCaseId: data.decisionCaseId,
    version: data.version ?? 1,
    title: data.title ?? decisionQuestion,
    clarifyingQuestions: data.clarifyingQuestions ?? []
  };
}

/** Case route with the tenant workspace anchor threaded as ?ws= (READ flip). */
export function createdCaseUrl(created: CreatedDecisionCase): string {
  return `/cases/${encodeURIComponent(created.decisionCaseId)}?ws=${encodeURIComponent(created.workspaceId)}`;
}

/** Navigation seam: components call this so jsdom tests can mock the module. */
export function navigateToCreatedCase(created: CreatedDecisionCase): void {
  window.location.assign(createdCaseUrl(created));
}
