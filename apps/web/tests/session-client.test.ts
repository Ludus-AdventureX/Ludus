/** @vitest-environment jsdom */

import { describe, expect, test, vi } from "vitest";

import {
  loginAccount,
  readAccountSession,
  registerAccount,
  SessionError
} from "../lib/shell/session";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

const csrfEnvelope = { ok: true, data: { csrfToken: "tok" } };
const authEnvelope = {
  ok: true,
  data: {
    user: { id: "u-1", email: "invited@example.test" },
    memberships: [
      { workspaceId: "ws-1", workspaceName: "Personal Workspace", role: "owner" }
    ]
  }
};

describe("session client (invite-gated auth)", () => {
  test("register sends email, password AND the invite code, then returns workspaces", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(csrfEnvelope))
      .mockResolvedValueOnce(jsonResponse(authEnvelope, 201));

    const session = await registerAccount(
      { email: "invited@example.test", password: "hunter2hunter2", inviteCode: "code-9" },
      fetchMock
    );

    expect(session.authenticated).toBe(true);
    expect(session.workspaces).toEqual([
      { workspaceId: "ws-1", workspaceName: "Personal Workspace", role: "owner" }
    ]);
    const [, init] = fetchMock.mock.calls[1];
    expect(JSON.parse(String(init?.body))).toEqual({
      email: "invited@example.test",
      password: "hunter2hunter2",
      inviteCode: "code-9"
    });
  });

  test("the invite gate's 403 surfaces with the server's own code", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(csrfEnvelope))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            ok: false,
            error: {
              code: "SIGNUP_INVITE_REQUIRED",
              message: "Registration requires a valid invite code."
            }
          },
          403
        )
      );

    const failure = await registerAccount(
      { email: "a@b.co", password: "hunter2hunter2", inviteCode: "wrong" },
      fetchMock
    ).catch((error) => error);

    expect(failure).toBeInstanceOf(SessionError);
    expect(failure.code).toBe("SIGNUP_INVITE_REQUIRED");
    expect(failure.status).toBe(403);
  });

  test("login surfaces invalid credentials as the server reported them", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(csrfEnvelope))
      .mockResolvedValueOnce(
        jsonResponse(
          { ok: false, error: { code: "INVALID_CREDENTIALS", message: "no" } },
          401
        )
      );

    const failure = await loginAccount(
      { email: "a@b.co", password: "whatever0" },
      fetchMock
    ).catch((error) => error);

    expect(failure).toBeInstanceOf(SessionError);
    expect(failure.code).toBe("INVALID_CREDENTIALS");
  });

  test("readAccountSession treats 401 as unauthenticated, not an error", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ ok: false }, 401));

    const session = await readAccountSession(fetchMock);
    expect(session).toEqual({ authenticated: false, email: null, workspaces: [] });
  });
});
