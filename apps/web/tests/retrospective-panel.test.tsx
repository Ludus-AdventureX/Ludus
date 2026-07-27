/** @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { createElement } from "react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { RetrospectivePanel } from "../components/shell/views/RetrospectivePanel";

// Retrospective battery: self-hide with no decision, render indicators from a
// signed decision, and record a judgement that updates the calibration line.

const WS = "11111111-1111-4111-8111-111111111111";
const CASE = "22222222-2222-4222-8222-222222222222";

beforeEach(() => localStorage.clear());
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

function jsonResponse(status: number, payload: unknown): Response {
  return new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } });
}

const DECISION = {
  id: "dec-9999",
  payload: {
    decisionDraft: "Proceed under signed LOI.",
    reviewDate: "2020-01-01", // past -> due
    leadingIndicators: [
      { id: "li-1", metric: "signed pilots", expectedDirection: "up", threshold: ">= 2" },
    ],
    exitCriteria: ["procurement cycle exceeds the cash window"],
  },
};

describe("RetrospectivePanel", () => {
  test("renders nothing without a signed decision", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(200, { ok: true, data: { items: [] } })));
    const { container } = render(createElement(RetrospectivePanel, { workspaceId: WS, decisionCaseId: CASE }));
    await waitFor(() => expect(container.querySelector("[data-retro-panel]")).not.toBeInTheDocument());
  });

  test("renders indicators + due status and records a judgement into calibration", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(200, { ok: true, data: { items: [DECISION] } })));

    render(createElement(RetrospectivePanel, { workspaceId: WS, decisionCaseId: CASE }));
    await waitFor(() => expect(document.querySelector("[data-retro-panel]")).toBeInTheDocument());
    expect(document.querySelector("[data-retro-due='true']")).toBeInTheDocument();
    expect(screen.getByText(/signed pilots/)).toBeInTheDocument();
    expect(screen.getByText(/procurement cycle exceeds/)).toBeInTheDocument();

    // Judge the first indicator "on track" -> calibration appears at 100%.
    const onTrackButtons = screen.getAllByRole("button", { name: "如期" });
    await user.click(onTrackButtons[0]);

    await waitFor(() => expect(document.querySelector("[data-retro-calibration]")).toBeInTheDocument());
    expect(document.querySelector("[data-retro-calibration]")).toHaveTextContent("如期率");
    // Persisted to localStorage keyed by decisionId.
    expect(localStorage.getItem("ludus.retro.dec-9999")).toContain("on_track");
  });
});
