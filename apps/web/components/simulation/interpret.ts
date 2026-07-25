// Pure interpretation of a SIM-02A run outcome into decision-user language.
// Natural language first (business units), score details only where needed.
// Never surfaces normalized values, damping, edge multipliers, score formulas
// or success probabilities.

import type {
  FragileCondition,
  SandboxGraph,
  SandboxRecommendation,
  SimulationRunData,
} from "./types";

export type RecommendationShiftState = "kept" | "flipped" | "insufficient";

export type TestedPoint = {
  value: number;
  flipped: boolean;
  simulationRunId: string;
};

export type RunInterpretation = {
  state: RecommendationShiftState;
  /** 相对基线变化，业务单位（如「+4 个月」）。 */
  baselineDeltaText: string;
  /** 自然语言主解释。 */
  narrative: string;
  /** 保持：已测试范围文本；未测试出翻转时不伪造阈值。 */
  testedRangeText: string | null;
  /** 翻转：翻转阈值文本（仅来自真实已测试点）。 */
  flipThresholdText: string | null;
  /** 翻转：目标选项。 */
  flipTargetLabel: string | null;
  /** 证据不足：缺失的证据描述。 */
  missingEvidence: string | null;
  /** 必要的评分细节（次要展示）：engineVersion / steps / convergence。 */
  scoreDetail: { engineVersion: string; steps: number; convergenceStatus: string };
};

function formatDelta(condition: FragileCondition, value: number): string {
  const delta = value - condition.baselineValue;
  const sign = delta > 0 ? "+" : "";
  return `${sign}${Number(delta.toFixed(2))} ${condition.unit}`;
}

export function interpretRunOutcome(input: {
  run: SimulationRunData;
  condition: FragileCondition;
  testedValue: number;
  recommendation: SandboxRecommendation;
  testedPoints: TestedPoint[];
}): RunInterpretation {
  const { run, condition, testedValue, recommendation, testedPoints } = input;
  const scoreDetail = {
    engineVersion: run.engineVersion,
    steps: run.steps,
    convergenceStatus: run.convergenceStatus,
  };
  const baselineDeltaText = formatDelta(condition, testedValue);

  // 证据不足：条件本身证据未知，或模拟未收敛 —— 都不允许伪造阈值。
  if (condition.evidenceStatus === "unknown" || run.convergenceStatus !== "converged") {
    return {
      state: "insufficient",
      baselineDeltaText,
      narrative: `在「${condition.title}」调到 ${testedValue} ${condition.unit} 时，现有证据不足以判断建议是否仍然成立。`,
      testedRangeText: null,
      flipThresholdText: null,
      flipTargetLabel: null,
      missingEvidence:
        condition.evidenceStatus === "unknown"
          ? `「${condition.title}」当前是未知项：${condition.impactNote}`
          : "本次推演未收敛，结果不能作为判断依据。",
      scoreDetail,
    };
  }

  const flipped =
    run.recommendedOptionId !== null && run.recommendedOptionId !== recommendation.optionId;

  if (flipped) {
    // 阈值只来自真实已测试点：本点即最新观测到翻转的业务值。
    const flippedValues = testedPoints.filter((p) => p.flipped).map((p) => p.value);
    const threshold = flippedValues.length > 0 ? Math.min(...flippedValues, testedValue) : testedValue;
    return {
      state: "flipped",
      baselineDeltaText,
      narrative: `当「${condition.title}」达到 ${testedValue} ${condition.unit}，当前建议不再成立，推演转向另一个选项。`,
      testedRangeText: null,
      flipThresholdText: `已测试点中，${threshold} ${condition.unit} 处建议发生翻转。`,
      flipTargetLabel: run.recommendedOptionId,
      missingEvidence: null,
      scoreDetail,
    };
  }

  const values = [condition.baselineValue, testedValue, ...testedPoints.map((p) => p.value)];
  const low = Math.min(...values);
  const high = Math.max(...values);
  return {
    state: "kept",
    baselineDeltaText,
    narrative: `「${condition.title}」调到 ${testedValue} ${condition.unit} 后，当前建议仍然成立。`,
    testedRangeText: `已测试范围：${low} 到 ${high} ${condition.unit}，建议未翻转。`,
    flipThresholdText: null,
    flipTargetLabel: null,
    missingEvidence: null,
    scoreDetail,
  };
}

// --- Impact paths ------------------------------------------------------------

export type ImpactPathStep = { nodeId: string; title: string; verbToNext: string | null };
export type ImpactPath = { id: string; steps: ImpactPathStep[] };

/**
 * Build 1-3 readable impact paths from the tested condition node towards
 * decision/outcome nodes, preferring branches whose nodes appear among the
 * run's top drivers. Text only — no numeric weights.
 */
export function buildImpactPaths(
  graph: SandboxGraph,
  fromNodeId: string,
  run: SimulationRunData | null,
  maxPaths = 3,
): ImpactPath[] {
  const nodeById = new Map(graph.nodes.map((node) => [node.id, node]));
  const driverRank = new Map<string, number>();
  (run?.topDrivers ?? []).forEach((driver, index) => driverRank.set(driver.nodeId, index));

  const paths: ImpactPath[] = [];
  const walk = (nodeId: string, trail: ImpactPathStep[], visited: Set<string>) => {
    if (paths.length >= maxPaths) return;
    const node = nodeById.get(nodeId);
    if (!node) return;
    const outgoing = graph.edges
      .filter((edge) => edge.from === nodeId && !visited.has(edge.to))
      .sort((a, b) => (driverRank.get(a.to) ?? 99) - (driverRank.get(b.to) ?? 99));
    if (outgoing.length === 0 || node.kind === "decision" || node.kind === "outcome") {
      if (trail.length >= 2) {
        paths.push({ id: trail.map((step) => step.nodeId).join(">"), steps: [...trail] });
      }
      return;
    }
    for (const edge of outgoing) {
      if (paths.length >= maxPaths) return;
      const next = nodeById.get(edge.to);
      if (!next) continue;
      const step: ImpactPathStep[] = [...trail];
      step[step.length - 1] = { ...step[step.length - 1], verbToNext: edge.verb };
      step.push({ nodeId: next.id, title: next.title, verbToNext: null });
      walk(edge.to, step, new Set([...visited, edge.to]));
    }
  };

  const origin = nodeById.get(fromNodeId);
  if (!origin) return [];
  walk(fromNodeId, [{ nodeId: origin.id, title: origin.title, verbToNext: null }], new Set([fromNodeId]));
  return paths.slice(0, maxPaths);
}

export function impactPathText(path: ImpactPath): string {
  return path.steps
    .map((step) => (step.verbToNext ? `${step.title} ${step.verbToNext}` : step.title))
    .join(" → ");
}
