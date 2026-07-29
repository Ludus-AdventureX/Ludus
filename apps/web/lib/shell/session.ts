// Account session client for the invite-gated alpha. The prototype guest
// endpoint (POST /api/auth/guest) is no longer the way in: registration is,
// and registration requires an invite code the operator hands out.
//
// Wire contract (all same-origin /api, credentials included):
//
//   GET  /api/auth/csrf     -> { data: { csrfToken } }
//   POST /api/auth/register  (email, password, inviteCode) -> AuthSessionEnvelope
//   POST /api/auth/login     (email, password)             -> AuthSessionEnvelope
//   POST /api/auth/logout                                  -> {}
//   GET  /api/auth/session                                 -> AuthSessionEnvelope | 401
//
// register/login answer the SAME envelope shape, whose memberships are the
// user's workspaces. The gate is deliberately narrow: an unknown code, a wrong
// code, and a deployment with no codes configured all answer one uniform 403,
// so the endpoint cannot be probed.

export type SessionStep = "csrf" | "register" | "login" | "logout" | "session";

export class SessionError extends Error {
  readonly code: string;
  readonly status: number;
  readonly step: SessionStep;

  constructor(code: string, message: string, status: number, step: SessionStep) {
    super(message);
    this.name = "SessionError";
    this.code = code;
    this.status = status;
    this.step = step;
  }
}

export type WorkspaceMembership = {
  workspaceId: string;
  workspaceName: string;
  role: string;
};

export type AccountSession = {
  authenticated: boolean;
  email: string | null;
  workspaces: WorkspaceMembership[];
};

type Envelope = { ok?: boolean; data?: unknown; error?: { code?: string; message?: string } };

async function readEnvelope(response: Response): Promise<Envelope> {
  try {
    return ((await response.json()) ?? {}) as Envelope;
  } catch {
    return {};
  }
}

function fail(step: SessionStep, response: Response, body: Envelope): SessionError {
  // Preserve the server's own code/message so the invite gate (403
  // SIGNUP_INVITE_REQUIRED) and invalid-credentials (401) surface honestly.
  return new SessionError(
    body.error?.code ?? "HTTP_ERROR",
    body.error?.message ?? `请求失败（HTTP ${response.status}）。`,
    response.status,
    step,
  );
}

async function request(
  fetchImpl: typeof fetch,
  step: SessionStep,
  path: string,
  init: RequestInit = {},
): Promise<Envelope> {
  let response: Response;
  try {
    response = await fetchImpl(path, { credentials: "include", ...init });
  } catch {
    throw new SessionError("NETWORK_ERROR", "无法连接 /api 服务，请稍后重试。", 0, step);
  }
  const body = await readEnvelope(response);
  if (!response.ok) throw fail(step, response, body);
  return body;
}

async function csrfToken(fetchImpl: typeof fetch): Promise<string> {
  const envelope = await request(fetchImpl, "csrf", "/api/auth/csrf");
  const token = (envelope.data as { csrfToken?: string } | undefined)?.csrfToken;
  if (!token) throw new SessionError("CSRF_TOKEN_MISSING", "CSRF token 响应缺少 csrfToken。", 200, "csrf");
  return token;
}

function toSession(envelope: Envelope): AccountSession {
  const data = envelope.data as
    | { user?: { email?: string }; memberships?: unknown }
    | undefined;
  const memberships = Array.isArray(data?.memberships) ? data?.memberships : [];
  const workspaces: WorkspaceMembership[] = [];
  for (const entry of memberships ?? []) {
    if (typeof entry !== "object" || entry === null) continue;
    const { workspaceId, workspaceName, role } = entry as Record<string, unknown>;
    if (typeof workspaceId === "string" && typeof workspaceName === "string" && typeof role === "string") {
      workspaces.push({ workspaceId, workspaceName, role });
    }
  }
  return { authenticated: true, email: data?.user?.email ?? null, workspaces };
}

/** Current session, or an unauthenticated marker. 401 is not an error here. */
export async function readAccountSession(
  fetchImpl: typeof fetch = fetch,
): Promise<AccountSession> {
  let response: Response;
  try {
    response = await fetchImpl("/api/auth/session", {
      method: "GET",
      credentials: "include",
      headers: { accept: "application/json" },
    });
  } catch {
    throw new SessionError("NETWORK_ERROR", "无法连接 /api 服务，请稍后重试。", 0, "session");
  }
  if (response.status === 401) return { authenticated: false, email: null, workspaces: [] };
  const body = await readEnvelope(response);
  if (!response.ok) throw fail("session", response, body);
  return toSession(body);
}

export type RegisterInput = { email: string; password: string; inviteCode: string };
export type LoginInput = { email: string; password: string };

export async function registerAccount(
  input: RegisterInput,
  fetchImpl: typeof fetch = fetch,
): Promise<AccountSession> {
  const token = await csrfToken(fetchImpl);
  const envelope = await request(fetchImpl, "register", "/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
    body: JSON.stringify({
      email: input.email,
      password: input.password,
      inviteCode: input.inviteCode,
    }),
  });
  return toSession(envelope);
}

export async function loginAccount(
  input: LoginInput,
  fetchImpl: typeof fetch = fetch,
): Promise<AccountSession> {
  const token = await csrfToken(fetchImpl);
  const envelope = await request(fetchImpl, "login", "/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
    body: JSON.stringify({ email: input.email, password: input.password }),
  });
  return toSession(envelope);
}

export async function logoutAccount(fetchImpl: typeof fetch = fetch): Promise<void> {
  const token = await csrfToken(fetchImpl);
  await request(fetchImpl, "logout", "/api/auth/logout", {
    method: "POST",
    headers: { "X-CSRF-Token": token },
  });
}
