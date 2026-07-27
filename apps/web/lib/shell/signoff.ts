/**
 * Signoff client: turn a ready report into a signed, append-only
 * DecisionRecord through the canonical three-step flow:
 *
 *   GET  /cases/{id}/reports?status=ready         (latest qualifying report)
 *   GET  /cases/{id}/reports/{reportId}           (source projection + content)
 *   POST /cases/{id}/signoff-requests             (returns payloadHash + one-time nonce)
 *   POST /signoff-requests/{requestId}/sign       (signatureStatement + payloadHash + nonce)
 *   GET  /cases/{id}/decisions                    (append-only records)
 *
 * Same-origin `/api`, credentials:"include", {ok,data} envelope, CSRF
 * double-submit - the proven decisionLoop pattern. The payload's source
 * projection MUST mirror the ready report exactly (server rejects any drift
 * with SIGNOFF_PAYLOAD_SOURCE_MISMATCH).
 */

export class SignoffError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "SignoffError";
    this.code = code;
    this.status = status;
  }
}

type Envelope = { ok?: boolean; data?: unknown };

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
    throw new SignoffError("NETWORK_ERROR", "无法连接 /api 服务，请确认后端可用。", 0);
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
    throw new SignoffError(
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
  if (!token) throw new SignoffError("CSRF_TOKEN_MISSING", "CSRF token 响应缺少 csrfToken。", 200);
  return token;
}

export type ReadyReport = {
  id: string;
  analysisRunId: string;
  sourceJudgmentSetId: string;
  sourceDissentRecordId: string;
  caseVersion: number;
  structuredContent: Record<string, unknown>;
};

/** Latest ready report for the case; null = honest "nothing to sign yet". */
export async function getLatestReadyReport(
  workspaceId: string,
  decisionCaseId: string,
  fetchImpl: FetchLike = defaultFetch(),
): Promise<ReadyReport | null> {
  const base = `/api/workspaces/${encodeURIComponent(workspaceId)}/cases/${encodeURIComponent(decisionCaseId)}`;
  const listEnvelope = await requestJson(fetchImpl, `${base}/reports?status=ready&limit=1`);
  const items = (listEnvelope.data as { items?: Array<{ id?: string }> } | undefined)?.items ?? [];
  const first = items[0]?.id;
  if (!first) return null;
  const detailEnvelope = await requestJson(fetchImpl, `${base}/reports/${encodeURIComponent(first)}`);
  const d = detailEnvelope.data as Record<string, unknown> | undefined;
  if (!d?.id) throw new SignoffError("REPORT_DETAIL_INVALID", "报告详情缺少 id。", 200);
  return {
    id: String(d.id),
    analysisRunId: String(d.analysisRunId),
    sourceJudgmentSetId: String(d.sourceJudgmentSetId),
    sourceDissentRecordId: String(d.sourceDissentRecordId),
    caseVersion: Number(d.caseVersion),
    structuredContent: (d.structuredContent as Record<string, unknown>) ?? {},
  };
}

export type SignoffDraft = {
  selectedOptionId: string;
  decisionDraft: string;
  conditions: string[];
  exitCriteria: string[];
  reviewDate: string;
};

/** Assemble the canonical payload: sources mirror the report verbatim. */
export function buildSignoffPayload(report: ReadyReport, draft: SignoffDraft) {
  const recommendation =
    (report.structuredContent.recommendation as Record<string, unknown> | undefined) ?? {};
  const outcome = (recommendation.outcome as Record<string, unknown> | undefined) ?? {
    kind: "abstain",
  };
  return {
    caseVersion: report.caseVersion,
    sourceAnalysisRunId: report.analysisRunId,
    sourceReportArtifactId: report.id,
    sourceJudgmentSetId: report.sourceJudgmentSetId,
    sourceDissentRecordId: report.sourceDissentRecordId,
    systemRecommendation: outcome,
    selectedOptionId: draft.selectedOptionId,
    decisionDraft: draft.decisionDraft,
    conditions: draft.conditions,
    thresholds: [],
    exitCriteria: draft.exitCriteria,
    actionItems: [
      {
        id: "act-signoff-review",
        text: "在复盘日期前确认成立条件仍然成立",
        owner: "decision owner",
        dueAt: draft.reviewDate,
        status: "open",
      },
    ],
    leadingIndicators: [],
    acceptedUnknownIds: [],
    reviewDate: draft.reviewDate,
  };
}

export type CreatedSignoff = {
  signoffRequestId: string;
  payloadHash: string;
  nonce: string;
};

export async function createSignoffRequest(
  workspaceId: string,
  decisionCaseId: string,
  payload: ReturnType<typeof buildSignoffPayload>,
  fetchImpl: FetchLike = defaultFetch(),
): Promise<CreatedSignoff> {
  const token = await csrfToken(fetchImpl);
  const envelope = await requestJson(
    fetchImpl,
    `/api/workspaces/${encodeURIComponent(workspaceId)}/cases/${encodeURIComponent(decisionCaseId)}/signoff-requests`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
      body: JSON.stringify({ payload }),
    },
  );
  const d = envelope.data as
    | { signoffRequest?: { id?: string; payloadHash?: string }; nonce?: string }
    | undefined;
  if (!d?.signoffRequest?.id || !d.signoffRequest.payloadHash || !d.nonce) {
    throw new SignoffError("SIGNOFF_CREATE_INVALID", "签署请求响应缺少 id/payloadHash/nonce。", 200);
  }
  return {
    signoffRequestId: d.signoffRequest.id,
    payloadHash: d.signoffRequest.payloadHash,
    nonce: d.nonce,
  };
}

export type DecisionRecordView = Record<string, unknown>;

export async function signSignoffRequest(
  workspaceId: string,
  created: CreatedSignoff,
  signatureStatement: string,
  fetchImpl: FetchLike = defaultFetch(),
): Promise<DecisionRecordView> {
  const token = await csrfToken(fetchImpl);
  const envelope = await requestJson(
    fetchImpl,
    `/api/workspaces/${encodeURIComponent(workspaceId)}/signoff-requests/${encodeURIComponent(created.signoffRequestId)}/sign`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
      body: JSON.stringify({
        signatureStatement,
        payloadHash: created.payloadHash,
        nonce: created.nonce,
      }),
    },
  );
  return (envelope.data as DecisionRecordView) ?? {};
}

export async function listCaseDecisions(
  workspaceId: string,
  decisionCaseId: string,
  fetchImpl: FetchLike = defaultFetch(),
): Promise<DecisionRecordView[]> {
  const envelope = await requestJson(
    fetchImpl,
    `/api/workspaces/${encodeURIComponent(workspaceId)}/cases/${encodeURIComponent(decisionCaseId)}/decisions`,
  );
  const items = (envelope.data as { items?: unknown[] } | undefined)?.items;
  return Array.isArray(items) ? (items as DecisionRecordView[]) : [];
}
