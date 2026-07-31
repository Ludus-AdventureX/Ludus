// Decision case create flow for the empty-state shells, on the invite-gated
// alpha. The prototype guest bootstrap is gone: the user must already hold an
// authenticated session (see /enter and lib/shell/session.ts), so the flow is
//
//   GET  /api/auth/csrf                      -> { data: { csrfToken } }
//   GET  /api/auth/session                   -> memberships (workspaces)
//        (401 -> AUTH_REQUIRED: the shell sends the visitor to /enter)
//   POST /api/workspaces/{workspaceId}/cases -> { data: CaseCreateData }
//        (require_csrf; body CaseCreateRequest { decisionQuestion })
//
// The workspace is the one the account already owns; no workspace is created
// here. A visitor without a session is not an error to swallow — it is a cue to
// authenticate, surfaced as the AUTH_REQUIRED code below.

import { readAccountSession, SessionError } from "@/lib/shell/session";

export type CaseCreateStep = "csrf" | "session" | "create";

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

  // The account already owns a workspace; find it. An unauthenticated visitor
  // is redirected to /enter by the shell, so this is a typed signal, not a
  // swallowed failure.
  let session;
  try {
    session = await readAccountSession(fetchImpl);
  } catch (error) {
    if (error instanceof SessionError) {
      throw new CaseCreateFlowError(error.code, error.message, error.status, "session");
    }
    throw error;
  }
  if (!session.authenticated) {
    throw new CaseCreateFlowError(
      "AUTH_REQUIRED",
      "请先登录或使用邀请码注册，再建立决策项目。",
      401,
      "session",
    );
  }
  const workspaceId = session.workspaces[0]?.workspaceId;
  if (!workspaceId) {
    throw new CaseCreateFlowError(
      "NO_WORKSPACE",
      "当前账号还没有可用工作区。",
      200,
      "session",
    );
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
  // Persist the workspace so returning to the app after session refresh keeps
  // the user in the same workspace (fixes "unknown workspace UUID" bug).
  try { localStorage.setItem("ludus-ws", created.workspaceId); } catch { /* SSR / private */ }
  window.location.assign(createdCaseUrl(created));
}

/**
 * A create failure means "authenticate first" when the session step reported
 * AUTH_REQUIRED. The shell uses this to send the visitor to /enter rather than
 * showing a dead-end notice for a state the user can actually resolve.
 */
export function isAuthRequired(error: unknown): boolean {
  return error instanceof CaseCreateFlowError && error.code === "AUTH_REQUIRED";
}

/** /enter with a return path, so the visitor comes back to where they were. */
export function enterUrl(nextPath = "/"): string {
  return `/enter?next=${encodeURIComponent(nextPath)}`;
}

/** Navigation seam for the auth redirect (mockable in jsdom tests). */
export function navigateToEnter(nextPath = "/"): void {
  window.location.assign(enterUrl(nextPath));
}
