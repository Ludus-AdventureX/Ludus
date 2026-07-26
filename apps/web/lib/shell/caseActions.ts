/**
 * Case-workspace action client: deliberation messages, dossier candidate
 * confirm/reject, and report reads. Same-origin `/api`, credentials:"include",
 * {ok,data} envelope, CSRF double-submit — the proven decisionLoop pattern.
 */

export class CaseActionError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "CaseActionError";
    this.code = code;
    this.status = status;
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
    throw new CaseActionError("NETWORK_ERROR", "无法连接 /api 服务，请确认后端可用。", 0);
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
        ? (body as { error: { code?: string; message?: string } }).error
        : null;
    throw new CaseActionError(
      error?.code ?? "HTTP_ERROR",
      error?.message ?? `请求失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  return (body ?? {}) as Envelope;
}

async function csrfToken(fetchImpl: FetchLike): Promise<string> {
  const envelope = await requestJson(fetchImpl, "/api/auth/csrf");
  const token = (envelope.data as { csrfToken?: string } | undefined)?.csrfToken;
  if (!token) throw new CaseActionError("CSRF_TOKEN_MISSING", "CSRF token 响应缺少 csrfToken。", 200);
  return token;
}

export type CaseMessageResult = {
  assistantMessage: string;
  candidateRevisionId: string | null;
  proposedPatch: unknown;
};

/** POST /cases/{id}/messages — persist the note, get the assistant reply + candidate. */
export async function postCaseMessage(
  workspaceId: string,
  decisionCaseId: string,
  message: string,
  fetchImpl: FetchLike = defaultFetch(),
): Promise<CaseMessageResult> {
  const token = await csrfToken(fetchImpl);
  const envelope = await requestJson(
    fetchImpl,
    `/api/workspaces/${encodeURIComponent(workspaceId)}/cases/${encodeURIComponent(decisionCaseId)}/messages`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
      body: JSON.stringify({ message }),
    },
  );
  const data = envelope.data as
    | { assistantMessage?: string; candidateRevisionId?: string | null; proposedPatch?: unknown }
    | undefined;
  return {
    assistantMessage: data?.assistantMessage ?? "",
    candidateRevisionId: data?.candidateRevisionId ?? null,
    proposedPatch: data?.proposedPatch ?? null,
  };
}

/** POST /cases/{id}/candidates/{candidateId}/confirm | reject */
export async function decideCandidate(
  workspaceId: string,
  decisionCaseId: string,
  candidateId: string,
  decision: "confirm" | "reject",
  fetchImpl: FetchLike = defaultFetch(),
): Promise<void> {
  const token = await csrfToken(fetchImpl);
  await requestJson(
    fetchImpl,
    `/api/workspaces/${encodeURIComponent(workspaceId)}/cases/${encodeURIComponent(decisionCaseId)}/candidates/${encodeURIComponent(candidateId)}/${decision}`,
    { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": token } },
  );
}

export type ReportListItem = {
  reportId: string;
  status: string;
  title?: string;
  recommendation?: unknown;
  createdAt?: string;
  [key: string]: unknown;
};

/** GET /cases/{id}/reports — canonical list envelope {items,nextCursor}. */
export async function listCaseReports(
  workspaceId: string,
  decisionCaseId: string,
  fetchImpl: FetchLike = defaultFetch(),
): Promise<ReportListItem[]> {
  const envelope = await requestJson(
    fetchImpl,
    `/api/workspaces/${encodeURIComponent(workspaceId)}/cases/${encodeURIComponent(decisionCaseId)}/reports`,
  );
  const items = (envelope.data as { items?: unknown[] } | undefined)?.items;
  return Array.isArray(items) ? (items as ReportListItem[]) : [];
}

/** GET /cases/{id}/reports/{reportId} — full report detail (loose canonical). */
export async function getCaseReport(
  workspaceId: string,
  decisionCaseId: string,
  reportId: string,
  fetchImpl: FetchLike = defaultFetch(),
): Promise<Record<string, unknown>> {
  const envelope = await requestJson(
    fetchImpl,
    `/api/workspaces/${encodeURIComponent(workspaceId)}/cases/${encodeURIComponent(decisionCaseId)}/reports/${encodeURIComponent(reportId)}`,
  );
  return (envelope.data as Record<string, unknown>) ?? {};
}
