/** @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { createElement } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";

import { ProvenancePanel } from "../components/shell/views/ProvenancePanel";

// Provenance battery: self-hide without a signed decision, and render the full
// hash chain (decision <- report <- run <- charter) when one exists.

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

function stub(script: Array<[RegExp, () => Response]>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      for (const [pattern, respond] of script) if (pattern.test(path)) return respond();
      throw new Error(`unexpected request: ${path}`);
    }),
  );
}

describe("ProvenancePanel", () => {
  test("renders nothing when the case has no signed decision", async () => {
    stub([[/\/decisions$/, () => jsonResponse(200, { ok: true, data: { items: [] } })]]);
    const { container } = render(createElement(ProvenancePanel, { workspaceId: WS, decisionCaseId: CASE }));
    await waitFor(() =>
      expect(container.querySelector("[data-provenance-panel]")).not.toBeInTheDocument(),
    );
  });

  test("renders the full hash chain for a signed decision", async () => {
    stub([
      [
        /\/decisions$/,
        () =>
          jsonResponse(200, {
            ok: true,
            data: {
              items: [
                {
                  id: "dec-9999",
                  payloadHash: "sha256:" + "a".repeat(64),
                  caseVersion: 1,
                  payload: { selectedOptionId: "opt_a" },
                  sourceReportArtifactId: "report-1234",
                  sourceAnalysisRunId: "run-5678",
                },
              ],
            },
          }),
      ],
      [
        /\/reports\/report-1234$/,
        () =>
          jsonResponse(200, {
            ok: true,
            data: {
              contentHash: "sha256:" + "b".repeat(64),
              type: "brief",
              status: "ready",
              validation: { passed: true },
            },
          }),
      ],
      [
        /\/analyses\/run-5678$/,
        () =>
          jsonResponse(200, {
            ok: true,
            data: {
              charterId: "charter-1",
              runManifestHash: "sha256:" + "c".repeat(64),
              status: "ready",
              progress: 1,
              caseSnapshotHash: "sha256:" + "d".repeat(64),
              methodId: "hardtech-market-direction",
              methodVersion: "1.1.0",
              stageResults: { planning: { outputHash: "sha256:" + "e".repeat(64) } },
            },
          }),
      ],
    ]);

    render(createElement(ProvenancePanel, { workspaceId: WS, decisionCaseId: CASE }));
    await waitFor(() => expect(document.querySelector("[data-provenance-panel]")).toBeInTheDocument());

    expect(document.querySelector("[data-provenance-link='decision']")).toBeInTheDocument();
    expect(document.querySelector("[data-provenance-link='report']")).toBeInTheDocument();
    expect(document.querySelector("[data-provenance-link='run']")).toBeInTheDocument();
    expect(document.querySelector("[data-provenance-link='charter']")).toBeInTheDocument();
    expect(document.querySelector("[data-provenance-panel]")).toHaveTextContent("这个决定是如何得来的");
    expect(document.querySelector("[data-provenance-link='run']")).toHaveTextContent("planning");
  });
});
