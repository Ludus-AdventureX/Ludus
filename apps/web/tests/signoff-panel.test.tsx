/** @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { createElement } from "react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { SignoffPanel } from "../components/shell/views/SignoffPanel";

// Signoff battery: ready-report gate, full create->sign flow to a
// DecisionRecord, and honest retryable failure on a rejected sign.

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

const readyReportDetail = {
  id: "report-1234",
  analysisRunId: "run-5678",
  sourceJudgmentSetId: "js-1",
  sourceDissentRecordId: "dr-1",
  caseVersion: 1,
  structuredContent: { recommendation: { outcome: { kind: "option", optionId: "opt_a" } } },
};

function stubFetchScript(script: Array<[RegExp, () => Response]>) {
  let unmatched: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      for (const [pattern, respond] of script) {
        if (pattern.test(path)) return respond();
      }
      unmatched.push(path);
      throw new Error(`unexpected request: ${path}`);
    }),
  );
  return () => unmatched;
}

describe("SignoffPanel", () => {
  test("renders the honest empty state when no ready report exists", async () => {
    stubFetchScript([
      [/\/reports\?status=ready/, () => jsonResponse(200, { ok: true, data: { items: [] } })],
      [/\/decisions$/, () => jsonResponse(200, { ok: true, data: { items: [] } })],
    ]);
    render(createElement(SignoffPanel, { workspaceId: WS, decisionCaseId: CASE }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("签署需要一份通过质量门的报告"));
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  test("drives create -> sign to an append-only DecisionRecord", async () => {
    const user = userEvent.setup();
    stubFetchScript([
      [/\/reports\?status=ready/, () => jsonResponse(200, { ok: true, data: { items: [{ id: "report-1234" }] } })],
      [/\/reports\/report-1234$/, () => jsonResponse(200, { ok: true, data: readyReportDetail })],
      [/\/decisions$/, () => jsonResponse(200, { ok: true, data: { items: [] } })],
      [/\/auth\/csrf$/, () => jsonResponse(200, { ok: true, data: { csrfToken: "tok" } })],
      [
        /\/signoff-requests$/,
        () =>
          jsonResponse(201, {
            ok: true,
            data: { signoffRequest: { id: "sr-1", payloadHash: "sha256:abc" }, nonce: "n-1" },
          }),
      ],
      [/\/signoff-requests\/sr-1\/sign$/, () => jsonResponse(200, { ok: true, data: { id: "dec-9999" } })],
    ]);

    render(createElement(SignoffPanel, { workspaceId: WS, decisionCaseId: CASE }));
    await waitFor(() => expect(screen.getByLabelText("选定选项 ID")).toHaveValue("opt_a"));

    await user.type(screen.getByLabelText(/决定草案/), "在既定条件下先做救援市场试点。");
    await user.type(screen.getByLabelText(/签名声明/), "我确认承担该决定。");
    await user.click(screen.getByRole("button", { name: /签署并冻结决定/ }));

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("决定已签署"));
    expect(screen.getByRole("status")).toHaveTextContent("dec-9999");
  });

  test("keeps the form retryable with an honest message when sign fails", async () => {
    const user = userEvent.setup();
    stubFetchScript([
      [/\/reports\?status=ready/, () => jsonResponse(200, { ok: true, data: { items: [{ id: "report-1234" }] } })],
      [/\/reports\/report-1234$/, () => jsonResponse(200, { ok: true, data: readyReportDetail })],
      [/\/decisions$/, () => jsonResponse(200, { ok: true, data: { items: [] } })],
      [/\/auth\/csrf$/, () => jsonResponse(200, { ok: true, data: { csrfToken: "tok" } })],
      [
        /\/signoff-requests$/,
        () =>
          jsonResponse(201, {
            ok: true,
            data: { signoffRequest: { id: "sr-1", payloadHash: "sha256:abc" }, nonce: "n-1" },
          }),
      ],
      [
        /\/signoff-requests\/sr-1\/sign$/,
        () => jsonResponse(409, { ok: false, error: { code: "SIGNOFF_NONCE_EXPIRED", message: "签署口令已过期" } }),
      ],
    ]);

    render(createElement(SignoffPanel, { workspaceId: WS, decisionCaseId: CASE }));
    await waitFor(() => expect(screen.getByLabelText("选定选项 ID")).toHaveValue("opt_a"));
    await user.type(screen.getByLabelText(/决定草案/), "草案");
    await user.type(screen.getByLabelText(/签名声明/), "签名");
    await user.click(screen.getByRole("button", { name: /签署并冻结决定/ }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("签署口令已过期"));
    expect(screen.getByRole("button", { name: /签署并冻结决定/ })).toBeEnabled();
  });
});
