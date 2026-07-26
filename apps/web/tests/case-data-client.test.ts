/** @vitest-environment jsdom */

import { describe, expect, test, vi } from "vitest";

import {
  CaseApiError,
  confirmCandidate,
  fetchCandidates,
  fetchCaseDetail,
  postCaseMessage,
  summarizeProposedPatch
} from "../lib/shell/caseData";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

const csrfEnvelope = { ok: true, data: { csrfToken: "token-1" } };

describe("caseData client (frozen dossier/conversation wire shapes)", () => {
  test("fetchCaseDetail unwraps the { ok, data } envelope", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ ok: true, data: { decisionCaseId: "case-1", caseVersion: 1 } }));

    const detail = await fetchCaseDetail("ws-1", "case-1", fetchMock);

    expect(detail.decisionCaseId).toBe("case-1");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workspaces/ws-1/cases/case-1",
      expect.objectContaining({ credentials: "include" })
    );
  });

  test("postCaseMessage sends the CSRF proof and the frozen body", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(csrfEnvelope))
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          data: {
            candidateRevisionId: "cand-1",
            baseDossierVersion: 1,
            baseCaseVersion: 1,
            assistantMessage: "回应",
            proposedPatch: { goalsAdded: 0, constraintsAdded: 1, factsAdded: 0, assumptionsAdded: 0, unknownsAdded: 0 }
          }
        })
      );

    const result = await postCaseMessage("ws-1", "case-1", "现金窗口 12 个月", fetchMock);

    expect(result.assistantMessage).toBe("回应");
    const [path, init] = fetchMock.mock.calls[1];
    expect(path).toBe("/api/workspaces/ws-1/cases/case-1/messages");
    expect(init).toMatchObject({ method: "POST" });
    expect((init?.headers as Record<string, string>)["X-CSRF-Token"]).toBe("token-1");
    expect(JSON.parse(String(init?.body))).toEqual({
      message: "现金窗口 12 个月",
      proposeStructuredUpdates: true
    });
  });

  test("confirmCandidate carries the candidate's base versions", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(csrfEnvelope))
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          data: {
            candidateRevisionId: "cand-1",
            status: "accepted",
            dossierVersion: 2,
            caseVersion: 2,
            confirmedEntryIds: ["entry-1"]
          }
        })
      );

    const outcome = await confirmCandidate(
      "ws-1",
      "case-1",
      { candidateRevisionId: "cand-1", baseDossierVersion: 1, baseCaseVersion: 1 },
      fetchMock
    );

    expect(outcome.dossierVersion).toBe(2);
    const [path, init] = fetchMock.mock.calls[1];
    expect(path).toBe("/api/workspaces/ws-1/cases/case-1/candidates/cand-1/confirm");
    expect(JSON.parse(String(init?.body))).toEqual({ baseDossierVersion: 1, baseCaseVersion: 1 });
  });

  test("the uniform 404 surfaces as a CaseApiError with the envelope code", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        jsonResponse(
          { ok: false, error: { code: "CASE_NOT_FOUND", message: "Not Found", retryable: false } },
          404
        )
      );

    const failure = await fetchCandidates("ws-1", "case-x", fetchMock).catch((error) => error);

    expect(failure).toBeInstanceOf(CaseApiError);
    expect(failure.code).toBe("CASE_NOT_FOUND");
    expect(failure.status).toBe(404);
  });

  test("summarizeProposedPatch renders only the non-zero buckets", () => {
    expect(
      summarizeProposedPatch({ goalsAdded: 0, constraintsAdded: 2, factsAdded: 1, assumptionsAdded: 0, unknownsAdded: 0 })
    ).toBe("＋2 约束 · ＋1 事实");
    expect(
      summarizeProposedPatch({ goalsAdded: 0, constraintsAdded: 0, factsAdded: 0, assumptionsAdded: 0, unknownsAdded: 0 })
    ).toBe("");
  });
});
