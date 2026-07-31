// Case workspace read/write client for the Q (问题) view mainline:
//
//   GET  /api/workspaces/{ws}/cases/{id}                         (CaseDetailData)
//   POST /api/workspaces/{ws}/cases/{id}/messages                (CaseMessageData)
//   GET  /api/workspaces/{ws}/cases/{id}/candidates              (CandidateListData)
//   POST /api/workspaces/{ws}/cases/{id}/candidates/{cid}/confirm
//   POST /api/workspaces/{ws}/cases/{id}/candidates/{cid}/reject
//
// Shapes are transcribed FIELD BY FIELD from services/api/app/dossiers/schemas.py
// and app/conversations/schemas.py (camelCase wire views) — never guessed.
// Unsafe writes carry the double-submit CSRF proof (GET /api/auth/csrf first);
// all calls are same-origin /api with credentials included. Missing / foreign /
// cross-tenant ids answer the uniform 404 envelope and stay collapsed here.

export class CaseApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "CaseApiError";
    this.code = code;
    this.status = status;
  }
}

type Envelope = { ok?: boolean; data?: unknown };

async function requestJson(
  fetchImpl: typeof fetch,
  path: string,
  init: RequestInit = {}
): Promise<unknown> {
  let response: Response;
  try {
    response = await fetchImpl(path, { credentials: "include", ...init });
  } catch {
    throw new CaseApiError("NETWORK_ERROR", "无法连接 /api 服务，请稍后重试。", 0);
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
    throw new CaseApiError(
      error?.code ?? "HTTP_ERROR",
      error?.message ?? `请求失败（HTTP ${response.status}）。`,
      response.status
    );
  }
  const envelope = (body ?? {}) as Envelope;
  if (typeof envelope !== "object" || envelope === null || !("data" in envelope)) {
    throw new CaseApiError("MALFORMED_ENVELOPE", "响应缺少 { ok, data } 信封。", response.status);
  }
  return envelope.data;
}

async function fetchCsrfToken(fetchImpl: typeof fetch): Promise<string> {
  const data = (await requestJson(fetchImpl, "/api/auth/csrf")) as { csrfToken?: string };
  if (!data?.csrfToken) {
    throw new CaseApiError("CSRF_TOKEN_MISSING", "CSRF token 响应缺少 csrfToken。", 200);
  }
  return data.csrfToken;
}

function caseBase(workspaceId: string, decisionCaseId: string): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/cases/${encodeURIComponent(decisionCaseId)}`;
}

// --- Wire shapes (dossiers/schemas.py + conversations/schemas.py) ----------

export type ArgumentNodeView = {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  optionId?: string | null;
  parentId?: string | null;
  type: "claim" | "support" | "counter" | "assumption" | "risk";
  text: string;
  evidenceIds: string[];
  assumptionIds: string[];
  supportScore: number;
  status: "draft" | "confirmed" | "rejected";
};

export type CaseDetailView = {
  decisionCaseId: string;
  decisionSubjectId: string;
  title: string;
  decisionQuestion: string;
  inferredDecisionType: string;
  status: string;
  operationalStatus: string;
  caseVersion: number;
  confirmedDossierVersion: number;
  confirmedDossierSnapshotHash?: string | null;
  argumentNodes: ArgumentNodeView[];
  createdAt: string;
  updatedAt: string;
};

export type ProposedPatchView = {
  goalsAdded: number;
  constraintsAdded: number;
  factsAdded: number;
  assumptionsAdded: number;
  unknownsAdded: number;
};

export type CaseMessageResult = {
  candidateRevisionId?: string | null;
  baseDossierVersion: number;
  baseCaseVersion?: number | null;
  assistantMessage: string;
  proposedPatch: ProposedPatchView;
};

export type CandidateProposalView = {
  operation: "add" | "update" | "reclassify" | "expire";
  entry: { statementType?: string; content?: string; [key: string]: unknown };
};

export type CandidateView = {
  candidateRevisionId: string;
  decisionCaseId?: string | null;
  sourceType: string;
  sourceId: string;
  baseDossierVersion: number;
  baseCaseVersion?: number | null;
  proposals: CandidateProposalView[];
  status: "pending" | "partially_accepted" | "accepted" | "rejected";
  reviewedAt?: string | null;
};

export type CandidateConfirmResult = {
  candidateRevisionId: string;
  status: string;
  dossierVersion: number;
  caseVersion?: number | null;
  confirmedEntryIds: string[];
};

// --- Readers -----------------------------------------------------------------

export async function fetchCaseDetail(
  workspaceId: string,
  decisionCaseId: string,
  fetchImpl: typeof fetch = fetch
): Promise<CaseDetailView> {
  return (await requestJson(fetchImpl, caseBase(workspaceId, decisionCaseId))) as CaseDetailView;
}

export async function fetchCandidates(
  workspaceId: string,
  decisionCaseId: string,
  fetchImpl: typeof fetch = fetch
): Promise<CandidateView[]> {
  const data = (await requestJson(
    fetchImpl,
    `${caseBase(workspaceId, decisionCaseId)}/candidates`
  )) as { items?: CandidateView[] };
  return Array.isArray(data?.items) ? data.items : [];
}

// --- Writers (CSRF double-submit) ---------------------------------------------

export type MessageView = { role: "user" | "assistant"; content: string; createdAt: string | null };

export async function fetchMessages(
  workspaceId: string,
  decisionCaseId: string,
  fetchImpl: typeof fetch = fetch
): Promise<MessageView[]> {
  const data = (await requestJson(
    fetchImpl,
    `${caseBase(workspaceId, decisionCaseId)}/messages`
  )) as { items?: MessageView[] };
  return Array.isArray(data?.items) ? data.items : [];
}

export async function postCaseMessage(
  workspaceId: string,
  decisionCaseId: string,
  message: string,
  fetchImpl: typeof fetch = fetch
): Promise<CaseMessageResult> {
  const csrfToken = await fetchCsrfToken(fetchImpl);
  return (await requestJson(fetchImpl, `${caseBase(workspaceId, decisionCaseId)}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify({ message, proposeStructuredUpdates: true })
  })) as CaseMessageResult;
}

export async function confirmCandidate(
  workspaceId: string,
  decisionCaseId: string,
  candidate: Pick<CandidateView, "candidateRevisionId" | "baseDossierVersion" | "baseCaseVersion">,
  fetchImpl: typeof fetch = fetch
): Promise<CandidateConfirmResult> {
  const csrfToken = await fetchCsrfToken(fetchImpl);
  return (await requestJson(
    fetchImpl,
    `${caseBase(workspaceId, decisionCaseId)}/candidates/${encodeURIComponent(candidate.candidateRevisionId)}/confirm`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
      body: JSON.stringify({
        baseDossierVersion: candidate.baseDossierVersion,
        baseCaseVersion: candidate.baseCaseVersion ?? null
      })
    }
  )) as CandidateConfirmResult;
}

export async function rejectCandidate(
  workspaceId: string,
  decisionCaseId: string,
  candidateRevisionId: string,
  fetchImpl: typeof fetch = fetch
): Promise<{ candidateRevisionId: string; status: string }> {
  const csrfToken = await fetchCsrfToken(fetchImpl);
  return (await requestJson(
    fetchImpl,
    `${caseBase(workspaceId, decisionCaseId)}/candidates/${encodeURIComponent(candidateRevisionId)}/reject`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
      body: JSON.stringify({})
    }
  )) as { candidateRevisionId: string; status: string };
}

// --- Presentation helpers ------------------------------------------------------

export const statementTypeLabels: Record<string, string> = {
  goal: "目标",
  constraint: "约束",
  fact: "事实",
  assumption: "假设",
  unknown: "未知项",
  judgment: "判断",
  preference: "偏好"
};

/** "＋2 事实 ＋1 假设" style summary; empty string when nothing was proposed. */
export function summarizeProposedPatch(patch: ProposedPatchView): string {
  const parts: string[] = [];
  const entries: [keyof ProposedPatchView, string][] = [
    ["goalsAdded", "目标"],
    ["constraintsAdded", "约束"],
    ["factsAdded", "事实"],
    ["assumptionsAdded", "假设"],
    ["unknownsAdded", "未知项"]
  ];
  for (const [key, label] of entries) {
    const count = patch?.[key] ?? 0;
    if (count > 0) parts.push(`＋${count} ${label}`);
  }
  return parts.join(" · ");
}
