/** @vitest-environment jsdom */

// Remediation reading tests: latest blocked run + validator reasons -> card
// data; lens-only blocks / no block / read failures -> null (card hidden).

import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { fetchBlockedRemediation } from "../lib/shell/remediation";

const workspaceId = "ws-1";
const caseId = "case-1";

function makeBlockedPayload() {
  return {
    type: "analysis.blocked",
    payload: {
      findings: [
        { code: "deterministic_gate", passed: true, score: 0.56 },
        {
          code: "validator_rejected",
          source: "model_validator",
          headline: "决策链存在关键断裂：一个月验证期缺乏可行性依据。",
          keyFindings: [
            "决策设定一个月验证震动唤醒与电池供应，但未提供在现有资源下能按时构建可测试原型的证据。",
            "80%唤醒率的用户测试需要足够样本和时间。",
          ],
          openQuestions: [
            "最小可行原型开发及用户测试的最短可行时间是多少？",
          ],
        },
      ],
    },
  };
}

function lensOnlyBlockedPayload() {
  return {
    type: "analysis.blocked",
    payload: {
      findings: [
        { code: "strategic_lens_incomplete", source: "lens_set_audit" },
      ],
    },
  };
}

function sseResponse(payload: unknown): Response {
  return new Response("data: " + JSON.stringify(payload) + "\n\n", {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

function runsResponse(items: Array<Record<string, unknown>>): Response {
  return new Response(
    JSON.stringify({ ok: true, data: { items } }),
    { status: 200 },
  );
}

describe("fetchBlockedRemediation", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test("resolves validator reasons from the latest blocked run", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.includes("/events")) return sseResponse(makeBlockedPayload());
      return runsResponse([
        { analysisRunId: "run-9", status: "blocked", analysisLevel: "full" },
        { analysisRunId: "run-8", status: "ready", analysisLevel: "full" },
      ]);
    }));

    const result = await fetchBlockedRemediation(workspaceId, caseId);
    expect(result).not.toBeNull();
    expect(result!.analysisRunId).toBe("run-9");
    expect(result!.headline).toContain("一个月验证期");
    expect(result!.gaps).toHaveLength(2);
    expect(result!.openQuestions).toHaveLength(1);
  });

  test("returns null when the latest run is not blocked", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.includes("/events")) return sseResponse({ type: "analysis.stage.started", payload: {} });
      return runsResponse([{ analysisRunId: "run-9", status: "ready" }]);
    }));
    expect(await fetchBlockedRemediation(workspaceId, caseId)).toBeNull();
  });

  test("returns null when the block has no validator rejection (lens-only)", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.includes("/events")) return sseResponse(lensOnlyBlockedPayload());
      return runsResponse([{ analysisRunId: "run-9", status: "blocked" }]);
    }));
    expect(await fetchBlockedRemediation(workspaceId, caseId)).toBeNull();
  });

  test("returns null on read failures (card stays hidden)", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new Error("network");
    }));
    expect(await fetchBlockedRemediation(workspaceId, caseId)).toBeNull();
  });
});
