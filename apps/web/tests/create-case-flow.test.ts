/** @vitest-environment jsdom */

import { describe, expect, test, vi } from "vitest";

import {
  CaseCreateFlowError,
  createDecisionCase,
  createdCaseUrl,
  enterUrl,
  isAuthRequired
} from "../lib/shell/createCase";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

const csrfEnvelope = { ok: true, data: { csrfToken: "token-1" } };
const sessionEnvelope = {
  ok: true,
  data: {
    user: { id: "u-1", email: "invited@example.test" },
    memberships: [
      { workspaceId: "ws-own-1", workspaceName: "Personal Workspace", role: "owner" }
    ]
  }
};
const caseEnvelope = {
  ok: true,
  data: {
    decisionCaseId: "case-123",
    version: 1,
    title: "先验证哪一个市场方向？",
    inferredDecisionType: "market_direction",
    clarifyingQuestions: ["这个决定最重要的成功指标是什么？"]
  },
  eventId: "evt_case_created"
};

describe("createDecisionCase (csrf -> session -> POST /cases)", () => {
  test("uses the authenticated workspace and returns the created identifiers", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(csrfEnvelope))
      .mockResolvedValueOnce(jsonResponse(sessionEnvelope))
      .mockResolvedValueOnce(jsonResponse(caseEnvelope, 201));

    const created = await createDecisionCase("先验证哪一个市场方向？", fetchMock);

    expect(created).toEqual({
      workspaceId: "ws-own-1",
      decisionCaseId: "case-123",
      version: 1,
      title: "先验证哪一个市场方向？",
      clarifyingQuestions: ["这个决定最重要的成功指标是什么？"]
    });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/auth/csrf",
      expect.objectContaining({ credentials: "include" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/auth/session",
      expect.objectContaining({ method: "GET", credentials: "include" })
    );
    const [createPath, createInit] = fetchMock.mock.calls[2];
    expect(createPath).toBe("/api/workspaces/ws-own-1/cases");
    expect(createInit).toMatchObject({ method: "POST" });
    expect(JSON.parse(String(createInit?.body))).toEqual({
      decisionQuestion: "先验证哪一个市场方向？"
    });
  });

  test("an unauthenticated 401 becomes an AUTH_REQUIRED cue, not a dead end", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(csrfEnvelope))
      .mockResolvedValueOnce(
        jsonResponse(
          { ok: false, error: { code: "UNAUTHENTICATED", message: "no session" } },
          401
        )
      );

    const failure = await createDecisionCase("q", fetchMock).catch((error) => error);

    expect(failure).toBeInstanceOf(CaseCreateFlowError);
    expect(failure.code).toBe("AUTH_REQUIRED");
    expect(failure.step).toBe("session");
    expect(isAuthRequired(failure)).toBe(true);
    // The session probe is not a create attempt: it must not reach /cases.
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  test("surfaces the backend error envelope from the create step", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(csrfEnvelope))
      .mockResolvedValueOnce(jsonResponse(sessionEnvelope))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            ok: false,
            error: { code: "CSRF_VALIDATION_FAILED", message: "刷新后重试。", retryable: false }
          },
          403
        )
      );

    const failure = await createDecisionCase("q", fetchMock).catch((error) => error);

    expect(failure).toBeInstanceOf(CaseCreateFlowError);
    expect(failure.code).toBe("CSRF_VALIDATION_FAILED");
    expect(failure.status).toBe(403);
    expect(failure.step).toBe("create");
  });

  test("threads the workspace anchor into the created case url", () => {
    expect(
      createdCaseUrl({
        workspaceId: "ws-own-1",
        decisionCaseId: "case-123",
        version: 1,
        title: "t",
        clarifyingQuestions: []
      })
    ).toBe("/cases/case-123?ws=ws-own-1");
  });

  test("enterUrl carries the return path so the visitor comes back", () => {
    expect(enterUrl("/")).toBe("/enter?next=%2F");
  });
});
