/** @vitest-environment jsdom */

import { describe, expect, test, vi } from "vitest";

import {
  CaseCreateFlowError,
  createDecisionCase,
  createdCaseUrl
} from "../lib/shell/createCase";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

const csrfEnvelope = { ok: true, data: { csrfToken: "token-1" } };
const guestEnvelope = { ok: true, data: { workspaceId: "ws-guest-1", graphId: "g-1" } };
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

describe("createDecisionCase (csrf -> guest -> POST /cases)", () => {
  test("walks the three frozen routes and returns the created identifiers", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(csrfEnvelope))
      .mockResolvedValueOnce(jsonResponse(guestEnvelope, 201))
      .mockResolvedValueOnce(jsonResponse(caseEnvelope, 201));

    const created = await createDecisionCase("先验证哪一个市场方向？", fetchMock);

    expect(created).toEqual({
      workspaceId: "ws-guest-1",
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
      "/api/auth/guest",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "X-CSRF-Token": "token-1" })
      })
    );
    const [createPath, createInit] = fetchMock.mock.calls[2];
    expect(createPath).toBe("/api/workspaces/ws-guest-1/cases");
    expect(createInit).toMatchObject({ method: "POST" });
    expect(JSON.parse(String(createInit?.body))).toEqual({
      decisionQuestion: "先验证哪一个市场方向？"
    });
  });

  test("maps the uniform guest 404 to an actionable GUEST_UNAVAILABLE error", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(csrfEnvelope))
      .mockResolvedValueOnce(
        jsonResponse(
          { ok: false, error: { code: "NOT_FOUND", message: "Not Found", retryable: false } },
          404
        )
      );

    const failure = await createDecisionCase("q", fetchMock).catch((error) => error);

    expect(failure).toBeInstanceOf(CaseCreateFlowError);
    expect(failure.code).toBe("GUEST_UNAVAILABLE");
    expect(failure.step).toBe("guest");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  test("surfaces the backend error envelope from the create step", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(csrfEnvelope))
      .mockResolvedValueOnce(jsonResponse(guestEnvelope, 201))
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
        workspaceId: "ws-guest-1",
        decisionCaseId: "case-123",
        version: 1,
        title: "t",
        clarifyingQuestions: []
      })
    ).toBe("/cases/case-123?ws=ws-guest-1");
  });
});
