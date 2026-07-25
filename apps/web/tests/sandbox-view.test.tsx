/** @vitest-environment jsdom */

// Task 13 sandbox interaction tests (plan 18 L1248-1322 Step 1 + gates).
// All simulation results in these tests flow through a mocked SIM-02A wire
// (csrf + POST/GET runs) — the components never fabricate results.

import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { createElement } from "react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { SandboxWorkspace } from "../components/simulation/SandboxWorkspace";
import type {
  SandboxCaseData,
  SimulationRunData,
} from "../components/simulation/types";
import { shellSlotContract } from "../lib/shell/slotContracts";

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

function fixtureData(): SandboxCaseData {
  return {
    recommendation: {
      headline: "在现金安全垫可守的前提下，先做救援市场受控试点",
      optionId: "option-rescue",
      optionLabel: "救援优先策略",
      conditions: ["采购周期不超过 12 个月", "预算主体在启动窗口内确认"],
      sourceReportVersion: "R-3",
      scopeNote: "沙盘不预测未来，它暴露建议在何处失效；本建议只在上述条件内成立。",
    },
    fragileConditions: [
      {
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
      },
      {
        nodeId: "node-modification",
        title: "改装预算",
        unit: "万元",
        baselineValue: 80,
        min: 40,
        max: 160,
        step: 5,
        controllability: "controllable",
        evidenceStatus: "assumed",
        impactNote: "超支会挤占试点资源",
        businessDomain: "产品成熟度",
      },
      {
        nodeId: "node-budget-owner",
        title: "预算主体确认",
        unit: "周",
        baselineValue: 4,
        min: 1,
        max: 16,
        step: 1,
        controllability: "partially_controllable",
        evidenceStatus: "unknown",
        impactNote: "启动窗口尚无对口证据",
        businessDomain: "启动窗口",
      },
      {
        nodeId: "node-fourth",
        title: "第四条件不应显示",
        unit: "件",
        baselineValue: 1,
        min: 0,
        max: 2,
        step: 1,
        controllability: "external",
        evidenceStatus: "confirmed",
        impactNote: "超出前三的条件",
        businessDomain: "越界",
      },
    ],
    graph: {
      draft: false,
      hardConstraints: [{ id: "c-cash", label: "现金安全垫不得低于 6 个月" }],
      nodes: [
        { id: "node-procurement", kind: "constraint", title: "采购周期", businessValue: "10 个月", baseline: "10 个月", range: "6-18 个月", source: "E-12 访谈", confirmation: "pending" },
        { id: "node-cash", kind: "indicator", title: "现金安全", businessValue: "可守 9 个月", baseline: "可守 9 个月", range: "3-15 个月", source: "M-04 财务模型", confirmation: "confirmed" },
        { id: "node-pilot", kind: "intermediate", title: "有限试点可行性", businessValue: "3 条证据链", baseline: "3 条证据链", range: "—", source: "M-02", confirmation: "confirmed" },
        { id: "node-decision", kind: "decision", title: "救援优先策略", businessValue: "未冻结", baseline: "未冻结", range: "—", source: "R-3 报告", confirmation: "confirmed" },
        { id: "node-budget-owner", kind: "unknown", title: "预算主体确认", businessValue: "未知", baseline: "4 周", range: "1-16 周", source: "尚无来源", confirmation: "pending", applicability: "仅适用于政府采购口径" },
        { id: "node-demand", kind: "external", title: "救援需求强度", businessValue: "证据充分", baseline: "证据充分", range: "—", source: "E-12", confirmation: "confirmed" },
      ],
      edges: [
        { id: "edge-proc-cash", from: "node-procurement", to: "node-cash", relationQuality: "evidence", impactStrength: "strong", verb: "压缩", source: "C-07", confirmation: "pending", wouldChangeRecommendation: true },
        { id: "edge-cash-pilot", from: "node-cash", to: "node-pilot", relationQuality: "assumed", impactStrength: "strong", verb: "收紧", source: "A-03", confirmation: "pending" },
        { id: "edge-pilot-decision", from: "node-pilot", to: "node-decision", relationQuality: "evidence", impactStrength: "moderate", verb: "影响", source: "M-02", confirmation: "confirmed" },
        { id: "edge-demand-pilot", from: "node-demand", to: "node-pilot", relationQuality: "evidence", impactStrength: "weak", verb: "支撑", source: "E-12", confirmation: "pending" },
      ],
    },
    scenarioFrames: [
      {
        id: "frame-delay",
        title: "采购延迟情景",
        externalDrivers: ["政府采购流程延长"],
        unknownDrivers: ["预算主体归属"],
        strategySurvives: false,
        earlyWarnings: ["招标公告推迟超过一个月"],
        confirmed: true,
        scenarioVersionId: "scen-v1",
        conditionAdjustments: { "node-procurement": 14 },
      },
      {
        id: "frame-fast",
        title: "快速确认情景",
        externalDrivers: ["专项预算提前下达"],
        unknownDrivers: [],
        strategySurvives: true,
        earlyWarnings: ["无"],
        confirmed: false,
        scenarioVersionId: null,
      },
    ],
    anchors,
  };
}

function runPayload(overrides: Partial<SimulationRunData> = {}): SimulationRunData {
  return {
    simulationRunId: "run-1",
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
    inputHash: "hash-1",
    nodeResults: { "node-cash": 0.4 },
    optionScores: [
      { optionId: "option-rescue", score: 0.62 },
      { optionId: "option-home", score: 0.55 },
    ],
    topDrivers: [{ nodeId: "node-cash", scoreDelta: -0.2 }],
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

function installFetch(
  postResponder: (call: FetchCall, postIndex: number) => unknown | Error,
) {
  const calls: FetchCall[] = [];
  let postIndex = 0;
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    if (url === "/api/auth/csrf") {
      return jsonResponse(200, { ok: true, data: { csrfToken: "csrf-1" } });
    }
    if (init?.method === "POST" && url.includes("/runs")) {
      const result = postResponder({ url, init }, postIndex++);
      if (result instanceof Error) throw result;
      return result;
    }
    if (!init?.method && url.includes("/runs/")) {
      return jsonResponse(200, { ok: true, data: runPayload() });
    }
    throw new Error(`unexpected fetch ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

function postCalls(calls: FetchCall[]): FetchCall[] {
  return calls.filter((call) => call.init?.method === "POST");
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      throw new Error("fetch not configured for this test");
    }),
  );
});

describe("Task 13 sandbox: default stress-test main flow (plan Step 1)", () => {
  test("first entry shows recommendation + max three fragile conditions and no full canvas", () => {
    const { container } = render(
      createElement(SandboxWorkspace, { decisionCaseId: "LX-2407", data: fixtureData() }),
    );

    expect(screen.getByText(/在现金安全垫可守的前提下/)).toBeVisible();
    expect(screen.getByText("来源报告版本 R-3")).toBeVisible();
    expect(screen.getByText(/本建议只在上述条件内成立/)).toBeVisible();

    const fragile = screen.getByRole("navigation", { name: "Fragile conditions" });
    expect(within(fragile).getAllByRole("button")).toHaveLength(3);
    expect(within(fragile).queryByText("第四条件不应显示")).not.toBeInTheDocument();
    expect(within(fragile).getByText(/现金窗口 · 外部因素 · 条件性证据/)).toBeInTheDocument();

    // 渐进展开：完整图画布未挂载。
    expect(container.querySelector(".causal-canvas")).not.toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });

  test("select 采购周期, adjust to 14 months, run: business-unit result with paths; no engine internals leak", async () => {
    const { calls } = installFetch(() =>
      jsonResponse(201, { ok: true, data: runPayload() }),
    );
    const user = userEvent.setup();
    const { container } = render(
      createElement(SandboxWorkspace, { decisionCaseId: "LX-2407", data: fixtureData() }),
    );

    const fragile = screen.getByRole("navigation", { name: "Fragile conditions" });
    await user.click(within(fragile).getByRole("button", { name: /采购周期/ }));

    const slider = screen.getByRole("slider", { name: "采购周期（个月）" });
    fireEvent.change(slider, { target: { value: "14" } });
    // 调整只写工作副本：不自动提交模拟。
    expect(postCalls(calls)).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: /运行压力测试/ }));

    // 结果：业务单位 + 相对基线变化 + 建议保持 + 已测试范围 + 影响路径。
    expect(await screen.findByText("建议保持", { selector: "h2" })).toBeVisible();
    expect(screen.getByText("+4 个月")).toBeVisible();
    expect(screen.getByText(/已测试范围：10 到 14 个月，建议未翻转/)).toBeVisible();
    const paths = screen.getByRole("list", { name: undefined, hidden: false });
    void paths;
    const pathSection = screen.getByLabelText("关键影响路径");
    expect(within(pathSection).getByText(/采购周期 压缩 → 现金安全 收紧 → 有限试点可行性 影响 → 救援优先策略/)).toBeVisible();
    expect(within(pathSection).getAllByRole("listitem").length).toBeLessThanOrEqual(3);

    // engineVersion 契约值可见于次要细节。
    expect(screen.getByText(/引擎 sim-engine-1\.1\.0/)).toBeVisible();

    // 请求纪律：Idempotency-Key 走 header；body 只有业务值 anchors。
    const [post] = postCalls(calls);
    const headers = post.init?.headers as Record<string, string>;
    expect(headers["Idempotency-Key"]).toMatch(/^sandbox-/);
    expect(headers["X-CSRF-Token"]).toBe("csrf-1");
    const body = JSON.parse(String(post.init?.body));
    expect(body.mode).toBe("experimental");
    expect(body.nodeOverrides).toEqual({ "node-procurement": 14 });
    const forbiddenKeys = /normalized|damping|multiplier|formula|probability|riskTolerance|engineVersion/i;
    expect(Object.keys(body).join(",")).not.toMatch(forbiddenKeys);
    // 控件与结果文案不得出现引擎内部概念。
    expect(container.textContent).not.toMatch(/normalized|damping|edge multiplier|评分公式|成功概率/i);
    expect(container.textContent).not.toMatch(/\d+\s*%/);
  });

  test("flip outcome shows target option, threshold from tested points and hard constraints", async () => {
    installFetch(() =>
      jsonResponse(201, { ok: true, data: runPayload({ recommendedOptionId: "option-home" }) }),
    );
    const user = userEvent.setup();
    render(createElement(SandboxWorkspace, { decisionCaseId: "LX-2407", data: fixtureData() }));

    fireEvent.change(screen.getByRole("slider", { name: "采购周期（个月）" }), {
      target: { value: "14" },
    });
    await user.click(screen.getByRole("button", { name: /运行压力测试/ }));

    expect(await screen.findByText("建议翻转", { selector: "h2" })).toBeVisible();
    expect(screen.getByText(/已测试点中，14 个月 处建议发生翻转/)).toBeVisible();
    expect(screen.getByText("option-home")).toBeVisible();
    expect(screen.getByText("现金安全垫不得低于 6 个月")).toBeVisible();
  });

  test("insufficient evidence: no fabricated threshold; primary CTA creates CandidateRevision only", async () => {
    const { calls } = installFetch(() =>
      jsonResponse(201, { ok: true, data: runPayload() }),
    );
    const user = userEvent.setup();
    render(createElement(SandboxWorkspace, { decisionCaseId: "LX-2407", data: fixtureData() }));

    const fragile = screen.getByRole("navigation", { name: "Fragile conditions" });
    await user.click(within(fragile).getByRole("button", { name: /预算主体确认/ }));
    fireEvent.change(screen.getByRole("slider", { name: "预算主体确认（周）" }), {
      target: { value: "8" },
    });
    await user.click(screen.getByRole("button", { name: /运行压力测试/ }));

    expect(await screen.findByText("证据不足", { selector: "h2" })).toBeVisible();
    // 不显示伪造阈值。
    expect(screen.queryByText(/翻转阈值/)).not.toBeInTheDocument();
    expect(screen.getByText(/「预算主体确认」当前是未知项/)).toBeVisible();

    // 主动作变为「生成验证行动」，且只创建候选修订。
    const cta = screen.getByRole("button", { name: /生成验证行动/ });
    expect(cta.className).toContain("primary-action");
    const callsBefore = calls.length;
    await user.click(cta);
    const revisionList = screen.getByRole("list", { name: "候选修订" });
    expect(within(revisionList).getByText("验证「预算主体确认」")).toBeVisible();
    expect(within(revisionList).getByText(/候选修订/)).toBeVisible();
    // 未直接更新正式档案：没有任何新的网络写入。
    expect(calls.length).toBe(callsBefore);
  });
});

describe("Task 13 sandbox: idempotency, uniform 404 and formal gate", () => {
  test("network retry reuses the same Idempotency-Key and surfaces the server replay flag", async () => {
    const { calls } = installFetch((call, postIndex) => {
      if (postIndex === 0) return new TypeError("network down");
      return jsonResponse(201, {
        ok: true,
        data: runPayload(),
        meta: { idempotencyReplay: true },
      });
    });
    const user = userEvent.setup();
    render(createElement(SandboxWorkspace, { decisionCaseId: "LX-2407", data: fixtureData() }));

    fireEvent.change(screen.getByRole("slider", { name: "采购周期（个月）" }), {
      target: { value: "13" },
    });
    await user.click(screen.getByRole("button", { name: /运行压力测试/ }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/重试将复用同一 Idempotency-Key，不会重复计算/);
    await user.click(within(alert).getByRole("button", { name: "重试本次运行" }));

    expect(await screen.findByText(/幂等重放（未重复计算）/)).toBeVisible();
    const posts = postCalls(calls);
    expect(posts).toHaveLength(2);
    const keyOf = (call: FetchCall) =>
      (call.init?.headers as Record<string, string>)["Idempotency-Key"];
    expect(keyOf(posts[0])).toBe(keyOf(posts[1]));
  });

  test("uniform 404 presentation stays tenant-safe", async () => {
    installFetch(() =>
      jsonResponse(404, {
        ok: false,
        error: { code: "CASE_NOT_FOUND", message: "Case not found." },
      }),
    );
    const user = userEvent.setup();
    render(createElement(SandboxWorkspace, { decisionCaseId: "LX-2407", data: fixtureData() }));

    await user.click(screen.getByRole("button", { name: /运行压力测试/ }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("该因果图在当前工作区不可见（未找到）。");
    // 不暗示资源在其他租户/工作区是否存在，也不提供重试假象。
    expect(alert.textContent).not.toMatch(/其他工作区|租户|存在/);
    expect(within(alert).queryByRole("button")).not.toBeInTheDocument();
  });

  test("formal entry is disabled until graph review passes, then posts mode=formal; API stays enforcer", async () => {
    const { calls } = installFetch(() =>
      jsonResponse(201, { ok: true, data: runPayload({ simulationMode: "formal" }) }),
    );
    const user = userEvent.setup();
    render(createElement(SandboxWorkspace, { decisionCaseId: "LX-2407", data: fixtureData() }));

    const formal = screen.getByRole("button", { name: /正式运行（formal）/ });
    expect(formal).toBeDisabled();
    expect(screen.getByText(/正式（formal）入口已禁用/)).toBeVisible();
    expect(screen.getByText(/前端禁用只是反馈，正式运行始终由 API 校验兜底/)).toBeVisible();

    // 展开完整模型完成图审阅：优先项逐条确认 + 其余项安全批量确认。
    await user.click(screen.getByRole("button", { name: /展开完整模型/ }));
    const panel = screen.getByRole("region", { name: "图审阅与确认" });
    await user.click(within(panel).getByRole("button", { name: "安全批量确认其余项" }));
    let confirmButtons = within(panel).queryAllByRole("button", { name: "确认" });
    while (confirmButtons.length > 0) {
      await user.click(confirmButtons[0]);
      confirmButtons = within(panel).queryAllByRole("button", { name: "确认" });
    }
    expect(within(panel).getByText("全部项目已确认")).toBeVisible();

    expect(formal).toBeEnabled();
    await user.click(formal);
    const posts = postCalls(calls);
    expect(posts).toHaveLength(1);
    expect(JSON.parse(String(posts[0].init?.body)).mode).toBe("formal");
  });

  test("API GRAPH_NOT_CONFIRMED rejection is surfaced honestly (server-side gate)", async () => {
    installFetch(() =>
      jsonResponse(409, {
        ok: false,
        error: { code: "GRAPH_NOT_CONFIRMED", message: "Formal requires confirmed graph." },
      }),
    );
    const user = userEvent.setup();
    render(createElement(SandboxWorkspace, { decisionCaseId: "LX-2407", data: fixtureData() }));

    await user.click(screen.getByRole("button", { name: /运行压力测试/ }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/正式模拟需要已确认的图版本（API 校验拒绝）/);
  });
});

describe("Task 13 sandbox: progressive model, review, scenarios and branches", () => {
  test("full model mounts only on demand; node kinds use shape+icon+label, not color alone", async () => {
    installFetch(() => jsonResponse(201, { ok: true, data: runPayload() }));
    const user = userEvent.setup();
    const { container } = render(
      createElement(SandboxWorkspace, { decisionCaseId: "LX-2407", data: fixtureData() }),
    );

    expect(container.querySelector(".causal-canvas")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /展开完整模型/ }));
    const canvas = container.querySelector(".causal-canvas");
    expect(canvas).toBeInTheDocument();

    // 当前被测试变量高亮；节点类型有形状 class + 图标 + 文字标签。
    const tested = container.querySelector('[data-node-id="node-procurement"]');
    expect(tested).toHaveAttribute("data-tested", "true");
    expect(within(tested as HTMLElement).getByText("当前被测试变量")).toBeInTheDocument();
    const unknownNode = container.querySelector('[data-node-id="node-budget-owner"]');
    expect(unknownNode).toHaveAttribute("data-node-kind", "unknown");
    expect(unknownNode?.className).toContain("node-unknown");
    expect(within(unknownNode as HTMLElement).getByText("未知项")).toBeInTheDocument();
    expect(screen.getByText(/不依赖颜色/)).toBeInTheDocument();

    // 检查器：业务值 / 基线 / 区间 / 来源 / 确认状态；关系质量 / 影响强度。
    await user.click(tested as HTMLElement);
    const nodeInspector = screen.getByLabelText("节点检查器：采购周期");
    // 业务值与基线同为「10 个月」：两个 dd 都应存在。
    expect(within(nodeInspector).getAllByText("10 个月")).toHaveLength(2);
    expect(within(nodeInspector).getByText("6-18 个月")).toBeInTheDocument();
    expect(within(nodeInspector).getByText("E-12 访谈")).toBeInTheDocument();
    expect(within(nodeInspector).getByText("未确认")).toBeInTheDocument();

    await user.click(container.querySelector('[data-edge-id="edge-cash-pilot"]') as HTMLElement);
    const edgeInspector = screen.getByLabelText("关系检查器");
    expect(within(edgeInspector).getByText("待验证假设")).toBeInTheDocument();
    expect(within(edgeInspector).getByText("影响强")).toBeInTheDocument();
  });

  test("graph review prioritizes recommendation-changing / hard-constraint / high-impact-low-quality items", async () => {
    installFetch(() => jsonResponse(201, { ok: true, data: runPayload() }));
    const user = userEvent.setup();
    render(createElement(SandboxWorkspace, { decisionCaseId: "LX-2407", data: fixtureData() }));

    await user.click(screen.getByRole("button", { name: /展开完整模型/ }));
    const priority = screen.getByRole("list", { name: "优先审阅项" });
    expect(within(priority).getByText("会改变推荐")).toBeInTheDocument();
    expect(within(priority).getByText("高影响但关系质量低")).toBeInTheDocument();
    expect(within(priority).getAllByText("触发硬约束").length).toBeGreaterThan(0);
    // 低影响项折叠在批量确认之后。
    expect(screen.getByRole("button", { name: /其余 1 项（低影响）/ })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.getByText(/未完成确认的草稿不能保存为正式图版本/)).toBeVisible();
  });

  test("scenario flow reads frames, creates ScenarioVersion candidates only after confirm, never asks risk preference", async () => {
    const { calls } = installFetch(() => jsonResponse(201, { ok: true, data: runPayload() }));
    const user = userEvent.setup();
    const { container } = render(
      createElement(SandboxWorkspace, { decisionCaseId: "LX-2407", data: fixtureData() }),
    );

    await user.click(screen.getByRole("button", { name: /情景与实验分支（次级流程）/ }));
    const scenario = screen.getByLabelText("情景");
    expect(within(scenario).getByText("政府采购流程延长")).toBeVisible();
    expect(within(scenario).getByText("strategySurvives：否")).toBeVisible();
    expect(within(scenario).getByText("招标公告推迟超过一个月")).toBeVisible();

    const before = calls.length;
    await user.click(within(scenario).getByRole("button", { name: "确认并创建 ScenarioVersion" }));
    const ledger = screen.getByRole("list", { name: "全部候选修订" });
    expect(within(ledger).getByText("快速确认情景")).toBeVisible();
    expect(within(ledger).getByText(/情景版本 · 候选修订/)).toBeVisible();
    expect(calls.length).toBe(before);
    // 不采集风险偏好。
    expect(container.textContent).not.toMatch(/风险偏好|风险容忍/);
  });

  test("confirmed scenario acts as preset; branches save and roll back non-destructively", async () => {
    installFetch(() => jsonResponse(201, { ok: true, data: runPayload() }));
    const user = userEvent.setup();
    render(createElement(SandboxWorkspace, { decisionCaseId: "LX-2407", data: fixtureData() }));

    // 已确认情景预设：把采购周期调整到 14 个月。
    const presets = screen.getByRole("group", { name: "已确认情景" });
    await user.click(within(presets).getByRole("button", { name: "采购延迟情景" }));
    const slider = screen.getByRole("slider", { name: "采购周期（个月）" });
    expect(slider).toHaveValue("14");

    await user.click(screen.getByRole("button", { name: /运行压力测试/ }));
    await screen.findByText("建议保持", { selector: "h2" });
    await user.click(screen.getByRole("button", { name: "保存实验分支" }));

    await user.click(screen.getByRole("button", { name: /情景与实验分支（次级流程）/ }));
    const timeline = screen.getByLabelText("实验分支");
    expect(within(timeline).getByText("采购周期 14 个月")).toBeVisible();

    // 改动工作副本后回滚：值恢复，分支不删除。
    fireEvent.change(slider, { target: { value: "9" } });
    await user.click(within(timeline).getByRole("button", { name: "回滚到此分支" }));
    expect(screen.getByRole("slider", { name: "采购周期（个月）" })).toHaveValue("14");
    expect(within(timeline).getByText("采购周期 14 个月")).toBeVisible();
  });
});

describe("Task 13 sandbox: honest empty state and slot contract", () => {
  test("without real case data the workspace keeps the honest Phase 0 empty frame and calls no API", () => {
    const { container } = render(
      createElement(SandboxWorkspace, { decisionCaseId: "LX-2407", data: null }),
    );

    expect(screen.getByRole("heading", { level: 1, name: "推演尚未开放" })).toBeVisible();
    expect(screen.getByText("脆弱条件待生成")).toBeInTheDocument();
    expect(container.querySelector('[data-sandbox-state="empty"]')).toBeInTheDocument();
    expect(container.querySelector(".causal-canvas")).not.toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });

  test("sandbox-workspace slot is registered as filled and the mount carries its anchor", () => {
    expect(shellSlotContract["sandbox-workspace"]).toMatchObject({
      status: "filled",
      mount: "replace-phase-slot-node",
    });
    const { container } = render(
      createElement(SandboxWorkspace, { decisionCaseId: "LX-2407", data: fixtureData() }),
    );
    expect(container.querySelector('[data-phase-slot="sandbox-workspace"]')).toBeInTheDocument();
  });

  test("keyboard path: fragile condition switch and explicit run are reachable without a pointer", async () => {
    const { calls } = installFetch(() => jsonResponse(201, { ok: true, data: runPayload() }));
    const user = userEvent.setup();
    render(createElement(SandboxWorkspace, { decisionCaseId: "LX-2407", data: fixtureData() }));

    const fragile = screen.getByRole("navigation", { name: "Fragile conditions" });
    const second = within(fragile).getByRole("button", { name: /改装预算/ });
    second.focus();
    await user.keyboard("{Enter}");
    expect(second).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("slider", { name: "改装预算（万元）" })).toBeInTheDocument();

    const run = screen.getByRole("button", { name: /运行压力测试/ });
    run.focus();
    await user.keyboard("{Enter}");
    expect(await screen.findByText("建议保持", { selector: "h2" })).toBeVisible();
    expect(postCalls(calls)).toHaveLength(1);
  });
});
