/** @vitest-environment jsdom */

// QA adversarial supplement for Task 13 sandbox r1 (independent QA lane).
// Targets the seams named in the QA brief: idempotency key reuse without a
// fresh key, idempotencyReplay presentation, uniform-404 anti-enumeration
// copy, interpret threshold refusing extrapolation beyond tested points,
// sandboxCaseDataRouteAvailable flip safety — plus conflict-forces-new-key
// and hostile-payload resilience. QA-owned test additions only.

import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { createElement } from "react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { SandboxWorkspace } from "../components/simulation/SandboxWorkspace";
import { interpretRunOutcome } from "../components/simulation/interpret";
import {
  loadSandboxCaseData,
  sandboxCaseDataRouteAvailable,
} from "../components/simulation/sandboxData";
import type {
  FragileCondition,
  SandboxCaseData,
  SandboxRecommendation,
  SimulationRunData,
} from "../components/simulation/types";

const anchors = {
  workspaceId: "ws-1",
  graphId: "graph-1",
  graphVersionId: "gv-1",
  strategyVersionId: "strat-v1",
  scenarioVersionId: "scen-v1",
  scoreDefinitionId: "sd-1",
  decisionMakerProfileId: "dmp-1",
  decisionMakerProfileVersion: 3,
};

const procurement: FragileCondition = {
  nodeId: "node-procurement",
  title: "采购周期",
  unit: "个月",
  baselineValue: 10,
  min: 6,
  max: 18,
  step: 1,
  controllability: "external",
  evidenceStatus: "conditional",
  impactNote: "拉长会压缩现金窗口",
  businessDomain: "现金窗口",
};

const recommendation: SandboxRecommendation = {
  headline: "先做救援市场受控试点",
  optionId: "option-rescue",
  optionLabel: "救援优先策略",
  conditions: ["采购周期不超过 12 个月"],
  sourceReportVersion: "R-3",
  scopeNote: "沙盘不预测未来。",
};

function qaData(): SandboxCaseData {
  return {
    recommendation,
    fragileConditions: [procurement],
    graph: {
      draft: false,
      hardConstraints: [],
      nodes: [
        { id: "node-procurement", kind: "constraint", title: "采购周期", businessValue: "10 个月", baseline: "10 个月", range: "6-18 个月", source: "E-12", confirmation: "confirmed" },
        { id: "node-decision", kind: "decision", title: "救援优先策略", businessValue: "未冻结", baseline: "未冻结", range: "—", source: "R-3", confirmation: "confirmed" },
      ],
      edges: [
        { id: "edge-proc-decision", from: "node-procurement", to: "node-decision", relationQuality: "evidence", impactStrength: "strong", verb: "动摇", source: "C-07", confirmation: "confirmed" },
      ],
    },
    scenarioFrames: [],
    anchors,
  };
}

function runPayload(overrides: Partial<SimulationRunData> = {}): SimulationRunData {
  return {
    simulationRunId: "run-qa-1",
    workspaceId: anchors.workspaceId,
    decisionCaseId: "LX-2407",
    graphId: anchors.graphId,
    graphVersionId: anchors.graphVersionId,
    strategyVersionId: anchors.strategyVersionId,
    scenarioVersionId: anchors.scenarioVersionId,
    scoreDefinitionId: anchors.scoreDefinitionId,
    scoreDefinitionVersion: "1",
    decisionMakerProfileId: anchors.decisionMakerProfileId,
    decisionMakerProfileVersion: anchors.decisionMakerProfileVersion,
    riskTolerance: 0.4,
    engineVersion: "sim-engine-1.1.0",
    scenarioId: "scenario-1",
    simulationMode: "experimental",
    epsilon: 0.001,
    maxSteps: 12,
    steps: 6,
    inputHash: "hash-qa",
    nodeResults: {},
    optionScores: [{ optionId: "option-rescue", score: 0.6 }],
    topDrivers: [],
    recommendationShift: "No change",
    recommendedOptionId: "option-rescue",
    convergenceStatus: "converged",
    originModes: ["live"],
    createdAt: "2026-07-25T00:00:00Z",
    ...overrides,
  };
}

type FetchCall = { url: string; init?: RequestInit };

function jsonResponse(status: number, body: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

function installFetch(postResponder: (postIndex: number) => unknown | Error) {
  const calls: FetchCall[] = [];
  let postIndex = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      if (url === "/api/auth/csrf") {
        return jsonResponse(200, { ok: true, data: { csrfToken: "csrf-qa" } });
      }
      if (init?.method === "POST" && url.includes("/runs")) {
        const result = postResponder(postIndex++);
        if (result instanceof Error) throw result;
        return result;
      }
      throw new Error(`unexpected fetch ${url}`);
    }),
  );
  return calls;
}

const keyOf = (call: FetchCall) =>
  (call.init?.headers as Record<string, string>)["Idempotency-Key"];
const posts = (calls: FetchCall[]) => calls.filter((c) => c.init?.method === "POST");

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.doUnmock("@/components/simulation/sandboxData");
  vi.resetModules();
});

describe("QA-A1 idempotency: repeated network failures never mint a fresh key", () => {
  test("two failures + success = three POSTs, exactly one distinct Idempotency-Key", async () => {
    const calls = installFetch((postIndex) => {
      if (postIndex < 2) return new TypeError("network down");
      return jsonResponse(201, { ok: true, data: runPayload() });
    });
    const user = userEvent.setup();
    render(createElement(SandboxWorkspace, { decisionCaseId: "LX-2407", data: qaData() }));

    fireEvent.change(screen.getByRole("slider", { name: "采购周期（个月）" }), {
      target: { value: "14" },
    });
    await user.click(screen.getByRole("button", { name: /运行压力测试/ }));
    await user.click(within(await screen.findByRole("alert")).getByRole("button", { name: "重试本次运行" }));
    await user.click(within(await screen.findByRole("alert")).getByRole("button", { name: "重试本次运行" }));
    await screen.findByText("建议保持", { selector: "h2" });

    const postList = posts(calls);
    expect(postList).toHaveLength(3);
    const distinctKeys = new Set(postList.map(keyOf));
    expect(distinctKeys.size).toBe(1);
    expect([...distinctKeys][0]).toMatch(/^sandbox-/);
  });

  test("IDEMPOTENCY_CONFLICT clears the pending key: the next explicit run uses a different key", async () => {
    const calls = installFetch((postIndex) => {
      if (postIndex === 0) {
        return jsonResponse(409, {
          ok: false,
          error: { code: "IDEMPOTENCY_CONFLICT", message: "conflict" },
        });
      }
      return jsonResponse(201, { ok: true, data: runPayload() });
    });
    const user = userEvent.setup();
    render(createElement(SandboxWorkspace, { decisionCaseId: "LX-2407", data: qaData() }));

    await user.click(screen.getByRole("button", { name: /运行压力测试/ }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/幂等键已被不同的请求使用/);
    // 冲突不可用旧 key 重试：无重试按钮，必须重新发起。
    expect(within(alert).queryByRole("button")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /运行压力测试/ }));
    await screen.findByText("建议保持", { selector: "h2" });
    const postList = posts(calls);
    expect(postList).toHaveLength(2);
    expect(keyOf(postList[0])).not.toBe(keyOf(postList[1]));
  });
});

describe("QA-A2 idempotencyReplay presentation", () => {
  test("meta.idempotencyReplay=true renders the replay badge; absence renders none", async () => {
    let withMeta = true;
    const calls = installFetch(() =>
      jsonResponse(
        201,
        withMeta
          ? { ok: true, data: runPayload(), meta: { idempotencyReplay: true } }
          : { ok: true, data: runPayload() },
      ),
    );
    const user = userEvent.setup();
    render(createElement(SandboxWorkspace, { decisionCaseId: "LX-2407", data: qaData() }));

    await user.click(screen.getByRole("button", { name: /运行压力测试/ }));
    expect(await screen.findByText(/幂等重放（未重复计算）/, undefined, { timeout: 4000 })).toBeVisible();

    withMeta = false;
    await user.click(screen.getByRole("button", { name: /运行压力测试/ }));
    await screen.findByText("建议保持", { selector: "h2" });
    expect(posts(calls)).toHaveLength(2);
    expect(screen.queryByText(/幂等重放（未重复计算）/)).not.toBeInTheDocument();
  });
});

describe("QA-A3 uniform 404 anti-enumeration", () => {
  test.each([
    ["CASE_NOT_FOUND", "Case not found."],
    ["NOT_FOUND", "Nothing here."],
  ])("404 with code %s collapses to the same tenant-safe copy", async (code, message) => {
    installFetch(() => jsonResponse(404, { ok: false, error: { code, message } }));
    const user = userEvent.setup();
    render(createElement(SandboxWorkspace, { decisionCaseId: "LX-2407", data: qaData() }));

    await user.click(screen.getByRole("button", { name: /运行压力测试/ }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("该因果图在当前工作区不可见（未找到）。");
    // 不回显服务端 message，不泄露 id/租户/存在性，不提供重试。
    expect(alert.textContent).not.toContain(message);
    expect(alert.textContent).not.toMatch(/graph-1|ws-1|租户|其他工作区|存在/);
    expect(within(alert).queryByRole("button")).not.toBeInTheDocument();
  });
});

describe("QA-A4 interpret: thresholds only from really tested points", () => {
  const base = { condition: procurement, recommendation };

  test("kept outcome never fabricates a flip threshold", () => {
    const result = interpretRunOutcome({
      ...base,
      run: runPayload(),
      testedValue: 14,
      testedPoints: [],
    });
    expect(result.state).toBe("kept");
    expect(result.flipThresholdText).toBeNull();
    expect(result.testedRangeText).toBe("已测试范围：10 到 14 个月，建议未翻转。");
  });

  test("flip with no prior flipped points anchors the threshold at the current tested value only", () => {
    const result = interpretRunOutcome({
      ...base,
      run: runPayload({ recommendedOptionId: "option-home" }),
      testedValue: 16,
      testedPoints: [{ value: 12, flipped: false, simulationRunId: "r-12" }],
    });
    expect(result.state).toBe("flipped");
    // 12 未翻转，不得被外推为阈值；阈值=16（真实测得）。
    expect(result.flipThresholdText).toContain("16 个月");
    expect(result.flipThresholdText).not.toContain("12");
    expect(result.flipThresholdText).not.toMatch(/13|14|15/);
  });

  test("flip threshold takes the minimum over REALLY flipped points, ignoring non-flipped ones", () => {
    const result = interpretRunOutcome({
      ...base,
      run: runPayload({ recommendedOptionId: "option-home" }),
      testedValue: 16,
      testedPoints: [
        { value: 12, flipped: false, simulationRunId: "r-12" },
        { value: 15, flipped: true, simulationRunId: "r-15" },
      ],
    });
    expect(result.flipThresholdText).toContain("15 个月");
    expect(result.flipThresholdText).not.toContain("12");
  });

  test("unknown evidence or non-convergence yields insufficient with zero threshold text", () => {
    const unknownCondition: FragileCondition = { ...procurement, evidenceStatus: "unknown" };
    const insufficientByEvidence = interpretRunOutcome({
      condition: unknownCondition,
      recommendation,
      run: runPayload({ recommendedOptionId: "option-home" }),
      testedValue: 14,
      testedPoints: [],
    });
    expect(insufficientByEvidence.state).toBe("insufficient");
    expect(insufficientByEvidence.flipThresholdText).toBeNull();

    const insufficientByConvergence = interpretRunOutcome({
      ...base,
      run: runPayload({ convergenceStatus: "max_steps" }),
      testedValue: 14,
      testedPoints: [{ value: 13, flipped: true, simulationRunId: "r-13" }],
    });
    expect(insufficientByConvergence.state).toBe("insufficient");
    expect(insufficientByConvergence.flipThresholdText).toBeNull();
    expect(insufficientByConvergence.missingEvidence).toContain("未收敛");
  });
});

describe("QA-A5 sandboxCaseDataRouteAvailable flip safety", () => {
  test("today's single source of truth is false and resolves to null", () => {
    expect(sandboxCaseDataRouteAvailable).toBe(false);
    expect(loadSandboxCaseData("LX-2407")).toBeNull();
  });

  test("flipping the flag (mocked module) still renders the honest empty frame without crashing", async () => {
    vi.doMock("@/components/simulation/sandboxData", () => ({
      sandboxCaseDataRouteAvailable: true,
      loadSandboxCaseData: () => null,
    }));
    const { SandboxView } = await import("../components/shell/views/SandboxView");
    const { container } = render(createElement(SandboxView, { decisionCaseId: "LX-2407" }));

    expect(screen.getByRole("heading", { level: 1, name: "推演尚未开放" })).toBeVisible();
    expect(container.querySelector('[data-sandbox-state="empty"]')).toBeInTheDocument();
    expect(container.querySelector(".causal-canvas")).not.toBeInTheDocument();
  });
});

describe("QA-A6 hostile wire payload resilience", () => {
  test("ok envelope without data degrades to the generic honest error, no crash, no fake result", async () => {
    installFetch(() => jsonResponse(201, { ok: true }));
    const user = userEvent.setup();
    render(createElement(SandboxWorkspace, { decisionCaseId: "LX-2407", data: qaData() }));

    await user.click(screen.getByRole("button", { name: /运行压力测试/ }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("推演请求失败，请稍后再试。");
    expect(screen.queryByText("建议保持", { selector: "h2" })).not.toBeInTheDocument();
    expect(screen.queryByText(/翻转阈值/)).not.toBeInTheDocument();
  });
});
