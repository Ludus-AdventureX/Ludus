/** @vitest-environment jsdom */

// Deliberation board QA battery (CCR-20260804-DELIB-01, Wave 3).
// jsdom has no ResizeObserver, so the board renders the accessible factor
// ledger fallback (same discipline as the factor sandbox graph).

import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createElement } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";

import { DeliberationBoard } from "../components/deliberation/DeliberationBoard";

const WS = "11111111-1111-4111-8111-111111111111";
const CASE = "22222222-2222-4222-8222-222222222222";
const RUN = "33333333-3333-4333-8333-333333333333";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function jsonResponse(status: number, payload: unknown): Response {
  return new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } });
}

const DETAIL_RUNNING = {
  id: RUN,
  workspaceId: WS,
  decisionCaseId: CASE,
  status: "running",
  currentRoundSeq: 1,
  maxRounds: 3,
  factorSnapshotHash: "sha256:abc",
  originModes: ["fixture"],
  factors: [
    { id: "f-obj", deliberationRunId: RUN, provenance: "objective", label: "渠道需求", strength: 0.9, sourceFactorId: "f01", evidenceStatus: null },
    { id: "f-sub", deliberationRunId: RUN, provenance: "subjective", label: "对手降价意愿", strength: 0.6, statement: "[opposing] 对手会降价", authorUserId: "u1", evidenceStatus: "assumed" }
  ],
  rounds: [{ id: "r1", deliberationRunId: RUN, seq: 1, kind: "opening", status: "complete", startedAt: "2026-08-04T00:00:00Z", endedAt: "2026-08-04T00:01:00Z" }],
  pendingProposalCount: 1,
  pendingNominationCount: 1,
  pendingProposals: [
    { id: "p1", deliberationRunId: RUN, proposerFactorId: "f-sub", kind: "factor_strength", before: { strength: 0.9 }, after: { strength: 0.85 }, status: "pending", enginePreview: { outcomeScore: 0.48, verdict: "hold", flipThreshold: 0.5 }, decidedAt: null }
  ],
  pendingNominations: [
    { id: "n1", deliberationRunId: RUN, rationale: "最敏感因子没有主观覆盖", targetDescription: "渠道需求", status: "pending", confirmedFactorId: null }
  ],
  createdAt: "2026-08-04T00:00:00Z",
  updatedAt: "2026-08-04T00:01:00Z"
};

const MESSAGES = [
  { id: "m1", deliberationRunId: RUN, roundId: "r1", speaker: "witness", speakerFactorId: "f-obj", kind: "statement", content: "我持有客观因子「渠道需求」。", structuredPayload: null, stampActor: "analysis", stampNote: null, originMode: "fixture", sourceOriginModes: ["fixture"], createdAt: "2026-08-04T00:00:30Z" },
  { id: "m2", deliberationRunId: RUN, roundId: "r1", speaker: "moderator", speakerFactorId: null, kind: "nomination", content: "提名：请就「渠道需求」补充主观判断。", structuredPayload: null, stampActor: "analysis", stampNote: null, originMode: "fixture", sourceOriginModes: ["fixture"], createdAt: "2026-08-04T00:01:00Z" }
];

function stubFetch(routes: Record<string, (url: string, init?: RequestInit) => Response>) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    for (const [pattern, handler] of Object.entries(routes)) {
      if (path.includes(pattern)) return handler(path, init);
    }
    throw new Error(`unexpected ${path}`);
  });
}

describe("DeliberationBoard", () => {
  test("shows the creation panel when the case has no council yet", async () => {
    vi.stubGlobal(
      "fetch",
      stubFetch({
        "/deliberations": () => jsonResponse(200, { ok: true, data: { items: [] } })
      })
    );
    render(createElement(DeliberationBoard, { workspaceId: WS, decisionCaseId: CASE }));
    await waitFor(() => expect(document.querySelector("[data-deliberation-board='create']")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /创建议会并开始推演/ })).toBeInTheDocument();
  });

  test("reports the honest basis-empty state without fabricating a council", async () => {
    let createCalls = 0;
    vi.stubGlobal(
      "fetch",
      stubFetch({
        "/auth/csrf": () => jsonResponse(200, { ok: true, data: { csrfToken: "tok" } }),
        "cases": (url, init) => {
          if (init?.method === "POST") {
            createCalls += 1;
            return jsonResponse(409, { ok: false, error: { code: "DELIBERATION_BASIS_EMPTY", message: "该 Case 尚无分析因子基线" } });
          }
          return jsonResponse(200, { ok: true, data: { items: [] } });
        }
      })
    );
    render(createElement(DeliberationBoard, { workspaceId: WS, decisionCaseId: CASE }));
    await waitFor(() => expect(document.querySelector("[data-deliberation-board='create']")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /创建议会并开始推演/ }));
    await waitFor(() => expect(document.querySelector("[data-deliberation-board='basis-empty']")).toBeInTheDocument());
    expect(createCalls).toBe(1);
  });

  test("renders the running council: factors, transcript, proposal and nomination gates", async () => {
    let proposalDecision: string | null = null;
    vi.stubGlobal(
      "fetch",
      stubFetch({
        "/auth/csrf": () => jsonResponse(200, { ok: true, data: { csrfToken: "tok" } }),
        "/cases/": () => jsonResponse(200, { ok: true, data: { items: [{ id: RUN, decisionCaseId: CASE, status: "running", currentRoundSeq: 1, maxRounds: 3, createdAt: "2026-08-04T00:00:00Z", updatedAt: "2026-08-04T00:01:00Z" }] } }),
        "/messages": () => jsonResponse(200, { ok: true, data: { items: MESSAGES, nextCursor: null } }),
        "/proposals/": (url, init) => {
          if (init?.method === "POST") {
            proposalDecision = JSON.parse(String(init.body)).decision;
            return jsonResponse(200, { ok: true, data: { ...DETAIL_RUNNING.pendingProposals[0], status: proposalDecision } });
          }
          return jsonResponse(404, { ok: false, error: { code: "CASE_NOT_FOUND", message: "not found" } });
        },
        "/deliberations/": (url) => {
          if (url.includes(RUN)) return jsonResponse(200, { ok: true, data: DETAIL_RUNNING });
          return jsonResponse(200, { ok: true, data: { items: [] } });
        }
      })
    );
    render(createElement(DeliberationBoard, { workspaceId: WS, decisionCaseId: CASE }));

    // Running header with fixture marker and the factor ledger fallback.
    await waitFor(() => expect(document.querySelector("[data-deliberation-board='run']")).toBeInTheDocument());
    expect(document.querySelector(".deliberation-board .eyebrow")?.textContent).toContain("fixture");
    const subjective = document.querySelector("[data-provenance='subjective']");
    expect(subjective).not.toBeNull();
    expect(subjective?.textContent).toContain("对手降价意愿");
    expect(subjective?.textContent).toContain("assumed");

    // Transcript renders both messages.
    expect(screen.getByText(/我持有客观因子/)).toBeInTheDocument();
    expect(screen.getByText(/提名：请就/)).toBeInTheDocument();

    // Nomination gate: confirmation requires a statement (button disabled).
    const nominationCard = document.querySelector("[data-nomination-id='n1']");
    expect(nominationCard).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "我来声明" }));
    const confirmButton = screen.getByRole("button", { name: "确认并声明" });
    expect(confirmButton).toBeDisabled();

    // Proposal ledger: accept drives the decision endpoint.
    fireEvent.click(screen.getByRole("button", { name: "采纳" }));
    await waitFor(() => expect(proposalDecision).toBe("accepted"));
  });

  test("renders the outcome panel with the fixed disclaimer and no probability", async () => {
    const detail = { ...DETAIL_RUNNING, status: "complete", pendingProposals: [], pendingNominations: [], pendingProposalCount: 0, pendingNominationCount: 0 };
    const outcome = {
      id: "o1",
      deliberationRunId: RUN,
      conditionProjections: [
        { acceptedProposalIds: [], projection: { outcomeScore: 0.56, verdict: "proceed", flipThreshold: 0.5 }, condition: "基线：不采纳任何提议时，引擎的确定性投影。" }
      ],
      flipConditions: [{ factorId: "f01", label: "渠道需求", flipValue: 0.31, scoreDelta: 0.12 }],
      dissentLog: [{ factorId: "f-sub", witnessLabel: "对手降价意愿", originalStance: "提议被用户驳回", overturnedBasis: "用户裁决：提议未获采纳" }],
      assumptionLedger: [],
      disclaimer: "沙盘与议会不代表精确预测。",
      createdAt: "2026-08-04T00:05:00Z"
    };
    vi.stubGlobal(
      "fetch",
      stubFetch({
        "/cases/": () => jsonResponse(200, { ok: true, data: { items: [{ id: RUN, decisionCaseId: CASE, status: "complete", currentRoundSeq: 3, maxRounds: 3, createdAt: "2026-08-04T00:00:00Z", updatedAt: "2026-08-04T00:05:00Z" }] } }),
        "/messages": () => jsonResponse(200, { ok: true, data: { items: [], nextCursor: null } }),
        "/outcome": () => jsonResponse(200, { ok: true, data: outcome }),
        "/deliberations/": (url) => {
          if (url.includes(RUN)) return jsonResponse(200, { ok: true, data: detail });
          return jsonResponse(200, { ok: true, data: { items: [] } });
        }
      })
    );
    render(createElement(DeliberationBoard, { workspaceId: WS, decisionCaseId: CASE }));
    await waitFor(() => expect(document.querySelector("[data-deliberation-outcome='ready']")).toBeInTheDocument());
    expect(screen.getByText("沙盘与议会不代表精确预测。")).toBeInTheDocument();
    expect(screen.getByText(/推进 · 倾向 56%/)).toBeInTheDocument();
    expect(screen.getByText(/渠道需求：强度跨过 31% 时结论翻转/)).toBeInTheDocument();
    // The dissent witness label appears in the factor ledger AND the dissent log.
    expect(screen.getAllByText("对手降价意愿").length).toBeGreaterThanOrEqual(1);
    // No probability phrasing anywhere in the outcome area.
    const outcomeArea = document.querySelector("[data-deliberation-outcome='ready']");
    expect(outcomeArea?.textContent).not.toMatch(/成功概率|结论正确概率|概率\s*\d+%/);
  });
});
