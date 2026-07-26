/** @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { createElement } from "react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { AnalysisLaunchPanel } from "../components/shell/views/AnalysisLaunchPanel";

// Panel battery: honest gap state without the workspace anchor, real launch
// sequence to a terminal verdict, and honest error surface on failure.

const WS = "11111111-1111-4111-8111-111111111111";
const CASE = "22222222-2222-4222-8222-222222222222";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function jsonResponse(status: number, payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("AnalysisLaunchPanel", () => {
  test("renders the honest gap state without a workspace anchor and fires no request", () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    render(createElement(AnalysisLaunchPanel, { decisionCaseId: CASE }));

    expect(screen.getByText(/缺少工作区锚点/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  test("launches the real loop and lands on the backend terminal verdict", async () => {
    const user = userEvent.setup();
    const responses: Array<[RegExp, Response]> = [
      [/\/api\/auth\/csrf$/, jsonResponse(200, { ok: true, data: { csrfToken: "tok" } })],
      [
        new RegExp(`/cases/${CASE}$`),
        jsonResponse(200, { ok: true, data: { decisionSubjectId: "sub-1", decisionQuestion: "问题？" } }),
      ],
      [/analysis-charters$/, jsonResponse(201, { ok: true, data: { charterId: "ch-1" } })],
      [/\/confirm$/, jsonResponse(200, { ok: true, data: {} })],
      [/\/runs$/, jsonResponse(201, { ok: true, data: { analysisRunId: "run-12345678", status: "queued" } })],
      [
        /\/analyses\/run-12345678$/,
        jsonResponse(200, { ok: true, data: { status: "blocked", progress: 0.86, lastResumableStage: null } }),
      ],
    ];
    let index = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input);
        const step = responses[index];
        if (!step) throw new Error(`unexpected request: ${path}`);
        index += 1;
        if (!step[0].test(path)) throw new Error(`request ${index} was ${path}`);
        return step[1].clone();
      }),
    );

    render(createElement(AnalysisLaunchPanel, { workspaceId: WS, decisionCaseId: CASE }));

    await user.click(screen.getByRole("button", { name: /发起聚焦深度分析/ }));

    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("质量门未通过"),
    );
    expect(screen.getByRole("status").querySelector("[data-analysis-terminal='blocked']")).not.toBeNull();
    expect(screen.getByRole("button", { name: /再次发起分析/ })).toBeEnabled();
  });

  test("surfaces an honest error and offers retry when the launch fails", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(403, { ok: false, error: { code: "CSRF_REJECTED", message: "CSRF 校验失败" } })),
    );

    render(createElement(AnalysisLaunchPanel, { workspaceId: WS, decisionCaseId: CASE }));
    await user.click(screen.getByRole("button", { name: /发起聚焦深度分析/ }));

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("CSRF 校验失败"));
    expect(screen.getByRole("button", { name: /重试发起分析/ })).toBeEnabled();
  });
});
