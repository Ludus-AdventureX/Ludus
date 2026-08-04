// Route A layout battery: the factor graph layout is a pure, deterministic
// projection of the sandbox wire state — same input, same graph, and the
// edge semantics (weight -> line width, direction/polarity -> tone+dash)
// are locked here so visual regressions surface at unit level.

import { describe, expect, test } from "vitest";

import {
  buildFactorGraphLayout,
  FACTOR_NODE_X,
  FACTOR_NODE_Y_GAP,
  factorEdgeWidth,
  OUTCOME_NODE_ID,
  OUTCOME_NODE_X
} from "../components/shell/views/factorGraphLayout";
import type { SandboxState } from "../lib/shell/factorSandbox";

function makeState(overrides: Partial<SandboxState> = {}): SandboxState {
  return {
    available: true,
    outcomeScore: 0.62,
    verdict: "proceed",
    flipThreshold: 0.5,
    engine: "report-factor-sandbox/2.0",
    factors: [
      { id: "f01", label: "渠道需求", weight: 0.8, value: 0.8, baseline: 0.8, direction: "supporting", source: "买方承诺 40%" },
      { id: "f02", label: "克隆风险", weight: -0.6, value: 0.6, baseline: 0.6, direction: "opposing", source: "竞品可复制" },
      { id: "f03", label: "政策窗口", weight: 0.3, value: 0.3, baseline: 0.3, direction: "neutral", source: "试点政策" }
    ],
    influences: [
      { from: "f01", fromLabel: "渠道需求", to: "f02", toLabel: "克隆风险", polarity: "-", note: "承诺量压缩克隆窗口" },
      { from: "f03", fromLabel: "政策窗口", to: "f01", toLabel: "渠道需求", polarity: "+", note: "" }
    ],
    topDrivers: [],
    ...overrides
  };
}

describe("buildFactorGraphLayout", () => {
  test("is deterministic: identical input produces identical nodes and edges", () => {
    const state = makeState();
    expect(buildFactorGraphLayout(state)).toEqual(buildFactorGraphLayout(state));
  });

  test("stacks factors in the left column and centres one outcome node on the right", () => {
    const { nodes } = buildFactorGraphLayout(makeState());
    const factors = nodes.filter((node) => node.kind === "factor");
    const outcome = nodes.find((node) => node.kind === "outcome");
    expect(factors).toHaveLength(3);
    factors.forEach((node, index) => {
      expect(node.x).toBe(FACTOR_NODE_X);
      expect(node.y).toBe(index * FACTOR_NODE_Y_GAP);
    });
    expect(outcome?.id).toBe(OUTCOME_NODE_ID);
    expect(outcome?.x).toBe(OUTCOME_NODE_X);
    // Centred against the factor stack: ((n-1) * gap) / 2.
    expect(outcome?.y).toBe(FACTOR_NODE_Y_GAP);
  });

  test("emits exactly one factor->outcome edge per factor with width = 1 + 3*|weight|", () => {
    const { edges } = buildFactorGraphLayout(makeState());
    const outcomeEdges = edges.filter((edge) => edge.to === OUTCOME_NODE_ID);
    expect(outcomeEdges).toHaveLength(3);
    const byFrom = new Map(outcomeEdges.map((edge) => [edge.from, edge]));
    expect(byFrom.get("f01")?.strokeWidth).toBe(factorEdgeWidth(0.8));
    expect(byFrom.get("f02")?.strokeWidth).toBe(factorEdgeWidth(-0.6));
    expect(factorEdgeWidth(0.8)).toBe(3.4);
    expect(factorEdgeWidth(-1.7)).toBe(4); // capped at |w| = 1
  });

  test("opposing factors feed the outcome dashed, supporting/neutral stay solid", () => {
    const { edges } = buildFactorGraphLayout(makeState());
    const byFrom = new Map(edges.filter((edge) => edge.to === OUTCOME_NODE_ID).map((edge) => [edge.from, edge]));
    expect(byFrom.get("f01")).toMatchObject({ tone: "supporting", dashed: false });
    expect(byFrom.get("f02")).toMatchObject({ tone: "opposing", dashed: true });
    expect(byFrom.get("f03")).toMatchObject({ tone: "neutral", dashed: false });
  });

  test("influence edges keep polarity semantics and drop orphan endpoints", () => {
    const state = makeState({
      influences: [
        { from: "f01", fromLabel: "a", to: "f02", toLabel: "b", polarity: "-", note: "抑制链" },
        { from: "f03", fromLabel: "c", to: "f01", toLabel: "a", polarity: "+", note: "" },
        { from: "ghost", fromLabel: "g", to: "f01", toLabel: "a", polarity: "+", note: "orphan" }
      ]
    });
    const { edges } = buildFactorGraphLayout(state);
    const influences = edges.filter((edge) => edge.id.startsWith("influence-"));
    expect(influences).toHaveLength(2);
    expect(influences[0]).toMatchObject({ tone: "suppress", dashed: true, label: "抑制链" });
    expect(influences[1]).toMatchObject({ tone: "boost", dashed: false, label: "助推" });
  });

  test("no factors -> a lone outcome node and zero edges (nothing fabricated)", () => {
    const { nodes, edges } = buildFactorGraphLayout(makeState({ factors: [], influences: [] }));
    expect(nodes).toHaveLength(1);
    expect(nodes[0].kind).toBe("outcome");
    expect(edges).toHaveLength(0);
  });
});
