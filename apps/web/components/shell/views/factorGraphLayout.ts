// Route A: deterministic graph layout for the report factor sandbox. Pure
// function over the ALREADY-MOUNTED wire fields of SandboxState (factors +
// influence edges + outcome) — no new contract, nothing fabricated. Same
// input always yields the same coordinates/edges (unit-testable, mirrors
// the deterministic engine it visualizes). Rendering lives in
// FactorGraphCanvas; this module stays xyflow-free so tests import nothing
// heavy.

import type { SandboxFactor, SandboxInfluence, SandboxState } from "@/lib/shell/factorSandbox";

export const FACTOR_NODE_X = 40;
export const FACTOR_NODE_Y_GAP = 122;
export const OUTCOME_NODE_X = 620;

export type FactorGraphNodeKind = "factor" | "outcome";

export type FactorGraphNodeLayout = {
  id: string;
  kind: FactorGraphNodeKind;
  x: number;
  y: number;
};

/** Edge tone drives stroke semantics in CSS; never color alone (§11). */
export type FactorGraphEdgeTone = "supporting" | "opposing" | "neutral" | "boost" | "suppress";

export type FactorGraphEdgeLayout = {
  id: string;
  from: string;
  to: string;
  tone: FactorGraphEdgeTone;
  strokeWidth: number;
  dashed: boolean;
  label: string;
};

export type FactorGraphLayout = {
  nodes: FactorGraphNodeLayout[];
  edges: FactorGraphEdgeLayout[];
  /** Canvas size needed to contain every node (for fitView / min-height). */
  width: number;
  height: number;
};

export const OUTCOME_NODE_ID = "__outcome__";

function factorTone(direction: string): FactorGraphEdgeTone {
  if (direction === "supporting") return "supporting";
  if (direction === "opposing") return "opposing";
  return "neutral";
}

/** Line width carries the factor weight magnitude; capped at |w| = 1. */
export function factorEdgeWidth(weight: number): number {
  const magnitude = Math.min(1, Math.abs(Number.isFinite(weight) ? weight : 0));
  return Number((1 + 3 * magnitude).toFixed(2));
}

/**
 * Layout contract: factors stack in the left column (stable wire order),
 * the single outcome/"event" node sits right, vertically centred against
 * the factor stack. Influence edges run factor -> factor; every factor
 * also feeds the outcome node.
 */
export function buildFactorGraphLayout(state: SandboxState): FactorGraphLayout {
  const factors: SandboxFactor[] = Array.isArray(state.factors) ? state.factors : [];
  const influences: SandboxInfluence[] = Array.isArray(state.influences) ? state.influences : [];

  const nodes: FactorGraphNodeLayout[] = factors.map((factor, index) => ({
    id: factor.id,
    kind: "factor",
    x: FACTOR_NODE_X,
    y: index * FACTOR_NODE_Y_GAP
  }));

  const stackHeight = factors.length > 0 ? (factors.length - 1) * FACTOR_NODE_Y_GAP : 0;
  nodes.push({
    id: OUTCOME_NODE_ID,
    kind: "outcome",
    x: OUTCOME_NODE_X,
    y: stackHeight / 2
  });

  const factorIds = new Set(factors.map((factor) => factor.id));
  const edges: FactorGraphEdgeLayout[] = [];

  for (const factor of factors) {
    edges.push({
      id: `factor-outcome-${factor.id}`,
      from: factor.id,
      to: OUTCOME_NODE_ID,
      tone: factorTone(factor.direction),
      strokeWidth: factorEdgeWidth(factor.weight),
      dashed: factor.direction === "opposing",
      label: `权重 ${factor.weight.toFixed(2)}`
    });
  }

  for (const influence of influences) {
    // Only admit edges between nodes actually in the ledger (no orphans).
    if (!factorIds.has(influence.from) || !factorIds.has(influence.to)) continue;
    edges.push({
      id: `influence-${influence.from}-${influence.to}`,
      from: influence.from,
      to: influence.to,
      tone: influence.polarity === "-" ? "suppress" : "boost",
      strokeWidth: 1.6,
      dashed: influence.polarity === "-",
      label: influence.note || (influence.polarity === "-" ? "抑制" : "助推")
    });
  }

  return {
    nodes,
    edges,
    width: OUTCOME_NODE_X + 220,
    height: Math.max(stackHeight + 120, 220)
  };
}
