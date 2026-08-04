// Route B: deterministic layered layout for the formal causal sandbox. Pure
// function over SandboxGraph (the READ-01 wire mapping) — the eight node
// kinds fall into three columns (inputs -> intermediates -> outputs) in
// stable wire order, and each edge carries its relation-quality tone. No
// xyflow import here: tests stay lightweight and the layout is provably
// reproducible, matching the deterministic engine contract.

import type { NodeKind, SandboxGraph } from "./types";

export const CAUSAL_COLUMN_X = { input: 40, middle: 350, output: 660 } as const;
export const CAUSAL_NODE_Y_GAP = 150;

export type CausalColumn = keyof typeof CAUSAL_COLUMN_X;

const KIND_COLUMNS: Record<NodeKind, CausalColumn> = {
  external: "input",
  lever: "input",
  constraint: "input",
  unknown: "input",
  intermediate: "middle",
  indicator: "middle",
  outcome: "output",
  decision: "output"
};

export function columnOfKind(kind: NodeKind): CausalColumn {
  return KIND_COLUMNS[kind];
}

export type CausalGraphNodeLayout = {
  id: string;
  column: CausalColumn;
  x: number;
  y: number;
};

/** Edge tone = relation quality semantics; drives stroke style in CSS. */
export type CausalGraphEdgeTone = "evidence" | "human" | "assumed";

export type CausalGraphEdgeLayout = {
  id: string;
  from: string;
  to: string;
  tone: CausalGraphEdgeTone;
  strokeWidth: number;
  dashed: boolean;
  label: string;
};

export type CausalGraphLayout = {
  nodes: CausalGraphNodeLayout[];
  edges: CausalGraphEdgeLayout[];
  width: number;
  height: number;
};

export function relationTone(relationQuality: string): CausalGraphEdgeTone {
  if (relationQuality === "evidence") return "evidence";
  if (relationQuality === "human_constraint") return "human";
  return "assumed";
}

/** Impact strength tier -> stroke width step (strong/moderate/weak). */
export function causalEdgeWidth(impactStrength: string): number {
  if (impactStrength === "strong") return 2.4;
  if (impactStrength === "moderate") return 1.8;
  return 1.2;
}

export function buildCausalGraphLayout(graph: SandboxGraph): CausalGraphLayout {
  const columnCounters: Record<CausalColumn, number> = { input: 0, middle: 0, output: 0 };

  const nodes: CausalGraphNodeLayout[] = graph.nodes.map((node) => {
    const column = columnOfKind(node.kind);
    const row = columnCounters[column];
    columnCounters[column] += 1;
    return {
      id: node.id,
      column,
      x: CAUSAL_COLUMN_X[column],
      y: row * CAUSAL_NODE_Y_GAP
    };
  });

  const nodeIds = new Set(nodes.map((node) => node.id));
  const edges: CausalGraphEdgeLayout[] = [];
  for (const edge of graph.edges) {
    // Admit only edges whose endpoints exist in this layout (no orphans).
    if (!nodeIds.has(edge.from) || !nodeIds.has(edge.to)) continue;
    const tone = relationTone(edge.relationQuality);
    edges.push({
      id: edge.id,
      from: edge.from,
      to: edge.to,
      tone,
      strokeWidth: causalEdgeWidth(edge.impactStrength),
      dashed: tone === "assumed",
      label: edge.verb
    });
  }

  const tallest = Math.max(columnCounters.input, columnCounters.middle, columnCounters.output);
  return {
    nodes,
    edges,
    width: CAUSAL_COLUMN_X.output + 230,
    height: Math.max((tallest - 1) * CAUSAL_NODE_Y_GAP + 130, 260)
  };
}
