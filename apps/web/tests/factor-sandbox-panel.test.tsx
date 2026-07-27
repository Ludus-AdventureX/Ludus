/** @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createElement } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";

import { FactorSandboxPanel } from "../components/shell/views/FactorSandboxPanel";

// Factor sandbox battery: empty-state self-hide, baseline render, and a slide
// edit triggering a deterministic re-preview POST.

const WS = "11111111-1111-4111-8111-111111111111";
const CASE = "22222222-2222-4222-8222-222222222222";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function jsonResponse(status: number, payload: unknown): Response {
  return new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } });
}

const BASELINE = {
  available: true,
  outcomeScore: 0.72,
  verdict: "proceed",
  flipThreshold: 0.5,
  engine: "report-factor-sandbox/1.0 (deterministic)",
  factors: [
    { id: "f01", label: "channel demand", weight: 0.8, value: 0.8, baseline: 0.8, direction: "supporting", source: "buyer committed 40%" },
    { id: "f02", label: "clone risk", weight: -0.6, value: 0.6, baseline: 0.6, direction: "opposing", source: "competitor can clone" },
  ],
  topDrivers: [
    { nodeId: "f01", label: "channel demand", scoreDelta: 0.3, direction: "supporting", flipValue: 0.4 },
  ],
};

describe("FactorSandboxPanel", () => {
  test("shows the empty state when the case has no analysed factors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse(200, { ok: true, data: { available: false, factors: [], topDrivers: [] } })),
    );
    render(createElement(FactorSandboxPanel, { workspaceId: WS, decisionCaseId: CASE }));
    await waitFor(() =>
      expect(document.querySelector("[data-factor-sandbox='empty']")).toBeInTheDocument(),
    );
  });

  test("renders baseline factors + outcome, and a slide re-previews deterministically", async () => {
    const moved = { ...BASELINE, outcomeScore: 0.41, verdict: "hold" };
    let previewCalls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        if (/\/sandbox$/.test(path)) return jsonResponse(200, { ok: true, data: BASELINE });
        if (/\/auth\/csrf$/.test(path)) return jsonResponse(200, { ok: true, data: { csrfToken: "tok" } });
        if (/\/sandbox\/preview$/.test(path) && init?.method === "POST") {
          previewCalls += 1;
          return jsonResponse(200, { ok: true, data: moved });
        }
        throw new Error(`unexpected ${path}`);
      }),
    );

    render(createElement(FactorSandboxPanel, { workspaceId: WS, decisionCaseId: CASE }));
    await waitFor(() => expect(document.querySelector("[data-factor-sandbox='proceed']")).toBeInTheDocument());
    expect(screen.getAllByText("channel demand").length).toBeGreaterThan(0);

    const slider = screen.getAllByLabelText(/因子强度/)[0] as HTMLInputElement;
    fireEvent.change(slider, { target: { value: "0.1" } });

    await waitFor(() => expect(previewCalls).toBeGreaterThan(0));
    await waitFor(() => expect(document.querySelector("[data-factor-sandbox='hold']")).toBeInTheDocument());
  });
});
