/** @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { createElement } from "react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { AnalysisLaunchPanel } from "../components/shell/views/AnalysisLaunchPanel";
import type { RunEventSourceLike } from "../lib/shell/decisionLoop";

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
    // Mount-time probes fire BEFORE the user clicks: the Q-side profile fetch
    // (refined question) and the existing-run probe. The mock queue must
    // start there or every launch step shifts and the loop reads a CSRF
    // response as the seed.
    const responses: Array<[RegExp, Response]> = [
      [/\/profiles$/, jsonResponse(200, { ok: true, data: { question: { content: { refinedQuestion: "戒指闹钟：应优先进入救援市场还是家庭服务市场？" } } } })],
      [/\/analyses$/, jsonResponse(200, { ok: true, data: { items: [] } })],
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

    await user.click(screen.getByRole("button", { name: /发起分析/ }));

    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("质量门未通过"),
    );
    expect(screen.getByRole("status").querySelector("[data-analysis-terminal='blocked']")).not.toBeNull();
    expect(screen.getByRole("button", { name: /再次发起/ })).toBeEnabled();
  });

  test("surfaces an honest error and offers retry when the launch fails", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(403, { ok: false, error: { code: "CSRF_REJECTED", message: "CSRF 校验失败" } })),
    );

    render(createElement(AnalysisLaunchPanel, { workspaceId: WS, decisionCaseId: CASE }));
    await user.click(screen.getByRole("button", { name: /发起分析/ }));

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("CSRF 校验失败"));
    expect(screen.getByRole("button", { name: /重试/ })).toBeEnabled();
  });

  test("renders the SSE thinking trace and the blocked guidance from findings", async () => {
    const user = userEvent.setup();
    // A fake browser EventSource: the default factory picks it up in jsdom.
    const listeners: Array<[string, (event: { data?: unknown }) => void]> = [];
    class FakeEventSource implements RunEventSourceLike {
      constructor(_url: string, _init?: unknown) {}
      addEventListener(type: string, listener: (event: { data?: unknown }) => void) {
        listeners.push([type, listener]);
      }
      close() {}
    }
    vi.stubGlobal("EventSource", FakeEventSource);

    const responses: Array<[RegExp, Response]> = [
      [/\/profiles$/, jsonResponse(200, { ok: true, data: { question: { content: { refinedQuestion: "戒指闹钟：应优先进入救援市场还是家庭服务市场？" } } } })],
      [/\/analyses$/, jsonResponse(200, { ok: true, data: { items: [] } })],
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
        jsonResponse(200, { ok: true, data: { status: "analyzing", progress: 0.4, lastResumableStage: null } }),
      ],
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
        const step = responses[Math.min(index, responses.length - 1)];
        index += 1;
        if (!step[0].test(path)) throw new Error(`request ${index} was ${path}`);
        return step[1].clone();
      }),
    );

    render(createElement(AnalysisLaunchPanel, { workspaceId: WS, decisionCaseId: CASE }));
    await user.click(screen.getByRole("button", { name: /发起分析/ }));

    await waitFor(() => expect(listeners.length).toBeGreaterThan(0));
    const fire = (payload: unknown) =>
      listeners.forEach(([, listener]) => listener({ data: JSON.stringify(payload) }));
    fire({
      type: "analysis.stage.completed",
      payload: {
        stage: "criticizing",
        digest: { headline: "独家条款可能根本签不下来", keyFindings: ["对手 60 天内可复制报价"] },
      },
    });
    fire({
      type: "analysis.blocked",
      payload: { findings: [{ code: "claim_support_below_threshold" }] },
    });

    await waitFor(() =>
      expect(document.querySelector("[data-analysis-trace]")).toHaveTextContent("独家条款可能根本签不下来"),
    );
    expect(document.querySelector("[data-trace-stage='criticizing']")).toHaveTextContent(
      "对手 60 天内可复制报价",
    );

    await waitFor(() =>
      expect(document.querySelector("[data-analysis-blocked-guide]")).toBeInTheDocument(),
    );
    expect(document.querySelector("[data-analysis-blocked-guide]")).toHaveTextContent(
      "claim_support_below_threshold",
    );
  });

  test("blocked guidance shows validator reasons and hides a passed gate", async () => {
    const user = userEvent.setup();
    const listeners: Array<[string, (event: { data?: unknown }) => void]> = [];
    class FakeEventSource implements RunEventSourceLike {
      constructor(_url: string, _init?: unknown) {}
      addEventListener(type: string, listener: (event: { data?: unknown }) => void) {
        listeners.push([type, listener]);
      }
      close() {}
    }
    vi.stubGlobal("EventSource", FakeEventSource);

    const responses: Array<[RegExp, Response]> = [
      [/\/profiles$/, jsonResponse(200, { ok: true, data: { question: { content: { refinedQuestion: "戒指闹钟：应优先进入救援市场还是家庭服务市场？" } } } })],
      [/\/analyses$/, jsonResponse(200, { ok: true, data: { items: [] } })],
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
        const step = responses[Math.min(index, responses.length - 1)];
        index += 1;
        if (!step[0].test(path)) throw new Error(`request ${index} was ${path}`);
        return step[1].clone();
      }),
    );

    render(createElement(AnalysisLaunchPanel, { workspaceId: WS, decisionCaseId: CASE }));
    await user.click(screen.getByRole("button", { name: /发起分析/ }));

    await waitFor(() => expect(listeners.length).toBeGreaterThan(0));
    const fire = (payload: unknown) =>
      listeners.forEach(([, listener]) => listener({ data: JSON.stringify(payload) }));
    fire({
      type: "analysis.blocked",
      payload: {
        findings: [
          {
            code: "deterministic_gate",
            passed: true,
            score: 0.7,
            dims: { evidence: 0.7, adversarial: 1.0, consistency: 1.0 },
          },
          {
            code: "validator_rejected",
            source: "model_validator",
            headline: "追觅先上市仅为推测",
            keyFindings: ["决策所依据的上市时间仅为推测", "5%投诉门槛无法应对低投诉高危害事故"],
          },
        ],
      },
    });

    await waitFor(() =>
      expect(document.querySelector("[data-analysis-blocked-guide]")).toBeInTheDocument(),
    );
    const guide = document.querySelector("[data-analysis-blocked-guide]");
    expect(guide).toHaveTextContent("决策所依据的上市时间仅为推测");
    expect(guide).toHaveTextContent("5%投诉门槛无法应对低投诉高危害事故");
    // A passed gate is a verdict, not a blocker: it must not masquerade as
    // the reason the run was blocked.
    expect(guide).not.toHaveTextContent("deterministic_gate");
  });
});

test("lens-only block shows system-side guidance instead of the dossier hint", async () => {
  const user = userEvent.setup();
  const listeners: Array<[string, (event: { data?: unknown }) => void]> = [];
  class FakeEventSource implements RunEventSourceLike {
    constructor(_url: string, _init?: unknown) {}
    addEventListener(type: string, listener: (event: { data?: unknown }) => void) {
      listeners.push([type, listener]);
    }
    close() {}
  }
  vi.stubGlobal("EventSource", FakeEventSource);

  const responses: Array<[RegExp, Response]> = [
    [/\/profiles$/, jsonResponse(200, { ok: true, data: { question: { content: { refinedQuestion: "戒指闹钟：应优先进入救援市场还是家庭服务市场？" } } } })],
    [/\/analyses$/, jsonResponse(200, { ok: true, data: { items: [] } })],
    [/\/api\/auth\/csrf$/, jsonResponse(200, { ok: true, data: { csrfToken: "tok" } })],
    [
      new RegExp(`/cases/${CASE}$`),
      jsonResponse(200, { ok: true, data: { decisionSubjectId: "sub-1", decisionQuestion: "问题？" } }),
    ],
    [/analysis-charters$/, jsonResponse(201, { ok: true, data: { charterId: "ch-1" } })],
    [/\/confirm$/, jsonResponse(200, { ok: true, data: {} })],
    [/\/runs$/, jsonResponse(201, { ok: true, data: { analysisRunId: "run-87654321", status: "queued" } })],
    [
      /\/analyses\/run-87654321$/,
      jsonResponse(200, { ok: true, data: { status: "blocked", progress: 0.86, lastResumableStage: null } }),
    ],
  ];
  let index = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      const step = responses[Math.min(index, responses.length - 1)];
      index += 1;
      if (!step[0].test(path)) throw new Error(`request ${index} was ${path}`);
      return step[1].clone();
    }),
  );

  render(createElement(AnalysisLaunchPanel, { workspaceId: WS, decisionCaseId: CASE }));
  await user.click(screen.getByRole("button", { name: /发起分析/ }));

  await waitFor(() => expect(listeners.length).toBeGreaterThan(0));
  const fire = (payload: unknown) =>
    listeners.forEach(([, listener]) => listener({ data: JSON.stringify(payload) }));
  fire({
    type: "analysis.blocked",
    payload: {
      findings: [
        { code: "strategic_lens_incomplete", source: "lens_set_audit" },
        { code: "strategic_lens_reference_mismatch", source: "lens_set_audit" },
      ],
    },
  });

  await waitFor(() =>
    expect(document.querySelector("[data-analysis-blocked-guide]")).toBeInTheDocument(),
  );
  const guide = document.querySelector("[data-analysis-blocked-guide]");
  expect(guide).toHaveTextContent("透镜产物不完整属于模型/系统侧执行问题");
  expect(guide).not.toHaveTextContent("回到 Q 区");
});
