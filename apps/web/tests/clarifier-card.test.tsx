/** @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createElement } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";

import { AnalysisLaunchPanel } from "@/components/shell/views/AnalysisLaunchPanel";

// R2 clarifier battery: the advisory card renders the three verdicts and the
// adoption toggle; it never blocks launching and degrades honestly.

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

describe("AnalysisLaunchPanel question clarifier", () => {
  test("runs the check and renders verdicts + adoption toggle", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input);
        if (/\/auth\/csrf$/.test(path)) {
          return jsonResponse(200, { ok: true, data: { csrfToken: "tok" } });
        }
        if (/\/cases\/[^/]+$/.test(path)) {
          return jsonResponse(200, {
            ok: true,
            data: {
              decisionSubjectId: "s1",
              decisionQuestion: "签独家还是不签？",
            },
          });
        }
        if (/\/question-clarifier$/.test(path)) {
          return jsonResponse(200, {
            ok: true,
            data: {
              available: true,
              pseudoDecision: { verdict: false, reason: "" },
              falseDilemma: { verdict: true, thirdOption: "限期排他+销量对赌" },
              reversibility: { type: "type1", advice: "独家条款难回退" },
              refinedQuestion: "以什么条件签订有限期独家？",
              originalQuestion: "签独家还是不签？",
            },
          });
        }
        throw new Error(`unexpected ${path}`);
      }),
    );

    render(createElement(AnalysisLaunchPanel, { workspaceId: WS, decisionCaseId: CASE }));
    fireEvent.click(screen.getByRole("button", { name: /先做问题质检/ }));

    await waitFor(() =>
      expect(document.querySelector("[data-clarifier-card]")).toBeInTheDocument(),
    );
    expect(screen.getByText(/疑似假两难/)).toBeInTheDocument();
    expect(screen.getByText(/限期排他\+销量对赌/)).toBeInTheDocument();
    expect(screen.getByText(/难逆决定/)).toBeInTheDocument();

    const adopt = screen.getByRole("checkbox");
    fireEvent.click(adopt);
    expect((adopt as HTMLInputElement).checked).toBe(true);
  });

  test("degrades honestly when the clarifier is unavailable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input);
        if (/\/auth\/csrf$/.test(path)) {
          return jsonResponse(200, { ok: true, data: { csrfToken: "tok" } });
        }
        if (/\/cases\/[^/]+$/.test(path)) {
          return jsonResponse(200, {
            ok: true,
            data: { decisionSubjectId: "s1", decisionQuestion: "q?" },
          });
        }
        if (/\/question-clarifier$/.test(path)) {
          return jsonResponse(200, { ok: true, data: { available: false } });
        }
        throw new Error(`unexpected ${path}`);
      }),
    );

    render(createElement(AnalysisLaunchPanel, { workspaceId: WS, decisionCaseId: CASE }));
    fireEvent.click(screen.getByRole("button", { name: /先做问题质检/ }));
    await waitFor(() =>
      expect(screen.getByText(/问题质检暂不可用/)).toBeInTheDocument(),
    );
  });
});
