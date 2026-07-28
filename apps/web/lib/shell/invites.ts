/**
 * Workspace invite client (multi-guest collaboration).
 *
 *   POST /workspaces/{id}/invites            OWNER creates (token shown once)
 *   GET  /workspaces/{id}/invites            OWNER lists
 *   POST /workspaces/{id}/invites/{i}/revoke OWNER revokes
 *   POST /auth/invites/redeem                invitee joins (guest session first)
 *
 * Same-origin `/api`, {ok,data} envelope, CSRF double-submit. Dead invites are
 * indistinguishable by design - the client surfaces ONE honest failure text.
 */

export class InviteError extends Error {
  readonly code: string;
  readonly status: number;
  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "InviteError";
    this.code = code;
    this.status = status;
  }
}

export type FetchLike = typeof fetch;

function defaultFetch(): FetchLike {
  return (input, init) => fetch(input, init);
}

type Envelope = { ok?: boolean; data?: unknown; error?: { code?: string; message?: string } };

async function requestJson(fetchImpl: FetchLike, path: string, init: RequestInit = {}): Promise<Envelope> {
  let response: Response;
  try {
    response = await fetchImpl(path, { credentials: "include", ...init });
  } catch {
    throw new InviteError("NETWORK_ERROR", "无法连接 /api 服务。", 0);
  }
  const body = (await response.json().catch(() => null)) as Envelope | null;
  if (!response.ok) {
    throw new InviteError(
      body?.error?.code ?? "HTTP_ERROR",
      body?.error?.message ?? `请求失败（HTTP ${response.status}）。`,
      response.status,
    );
  }
  return body ?? {};
}

async function csrfToken(fetchImpl: FetchLike): Promise<string> {
  const envelope = await requestJson(fetchImpl, "/api/auth/csrf");
  const token = (envelope.data as { csrfToken?: string } | undefined)?.csrfToken;
  if (!token) throw new InviteError("CSRF_TOKEN_MISSING", "CSRF token 缺失。", 200);
  return token;
}

export type InviteView = {
  inviteId: string;
  capabilities: string[];
  maxUses: number;
  usedCount: number;
  expiresAt: string;
  revokedAt: string | null;
  /** Present ONLY on the create response. */
  token?: string;
  joinUrl?: string;
};

export async function createInvite(
  workspaceId: string,
  options: { grantSign?: boolean; mentorPreset?: boolean } = {},
  fetchImpl: FetchLike = defaultFetch(),
): Promise<InviteView> {
  const token = await csrfToken(fetchImpl);
  // Mentor preset: review-only (sees the full thinking chain, writes mentor
  // reviews, cannot contribute dossier facts). Otherwise collaborator preset.
  const capabilities = options.mentorPreset
    ? ["review"]
    : options.grantSign
      ? ["contribute", "review", "sign"]
      : ["contribute", "review"];
  const envelope = await requestJson(
    fetchImpl,
    `/api/workspaces/${encodeURIComponent(workspaceId)}/invites`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
      body: JSON.stringify({ capabilities }),
    },
  );
  return envelope.data as InviteView;
}

export async function listInvites(
  workspaceId: string,
  fetchImpl: FetchLike = defaultFetch(),
): Promise<InviteView[]> {
  const envelope = await requestJson(
    fetchImpl,
    `/api/workspaces/${encodeURIComponent(workspaceId)}/invites`,
  );
  return ((envelope.data as { items?: InviteView[] } | undefined)?.items ?? []) as InviteView[];
}

export async function revokeInvite(
  workspaceId: string,
  inviteId: string,
  fetchImpl: FetchLike = defaultFetch(),
): Promise<void> {
  const token = await csrfToken(fetchImpl);
  await requestJson(
    fetchImpl,
    `/api/workspaces/${encodeURIComponent(workspaceId)}/invites/${encodeURIComponent(inviteId)}/revoke`,
    { method: "POST", headers: { "X-CSRF-Token": token } },
  );
}

/** Redeem flow for /join: ensure a session (guest), then redeem the code. */
export async function joinWithInvite(
  code: string,
  fetchImpl: FetchLike = defaultFetch(),
): Promise<{ workspaceId: string; membership: string }> {
  // 1. Ensure a session exists (idempotent for an existing guest session).
  const guestToken = await csrfToken(fetchImpl);
  const guest = await fetchImpl("/api/auth/guest", {
    method: "POST",
    credentials: "include",
    headers: { "X-CSRF-Token": guestToken },
  });
  if (!guest.ok && guest.status !== 200 && guest.status !== 201) {
    throw new InviteError("GUEST_UNAVAILABLE", "访客通道未开放，请联系工作区管理员。", guest.status);
  }
  // 2. Redeem.
  const redeemToken = await csrfToken(fetchImpl);
  const envelope = await requestJson(fetchImpl, "/api/auth/invites/redeem", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": redeemToken },
    body: JSON.stringify({ token: code }),
  });
  const data = envelope.data as { workspaceId?: string; membership?: string } | undefined;
  if (!data?.workspaceId) throw new InviteError("REDEEM_INVALID", "兑换响应缺少 workspaceId。", 200);
  return { workspaceId: data.workspaceId, membership: data.membership ?? "created" };
}
