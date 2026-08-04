// Route B layout battery: the formal causal graph layout is a pure,
// deterministic projection of SandboxGraph — the eight node kinds fall into
// three columns, relation quality maps to edge tone/dash, and orphan edges
// are dropped. Locks the semantics at unit level.

import { describe, expect, test } from "vitest";

import {
  buildCausalGraphLayout,
  CAUSAL_COLUMN_X,
  CAUSAL_NODE_Y_GAP,
  causalEdgeWidth,
  columnOfKind,
  relationTone
} from "../components/simulation/causalGraphLayout";
import type { NodeKind, SandboxGraph, SandboxGraphEdge, SandboxGraphNode } from "../components/simulation/types";

function node(id: string, kind: NodeKind): SandboxGraphNode {
  return {
    id,
    kind,
    title: `节点 ${id}`,
    businessValue: "0.5",
    baseline: "0.5",
    range: "0-1",
    source: "",
    confirmation: "pending"
  };
}

function edge(id: string, from: string, to: string, relationQuality: SandboxGraphEdge["relationQuality"], impactStrength: SandboxGraphEdge["impactStrength"] = "moderate"): SandboxGraphEdge {
  return {
    id,
    from,
    to,
    relationQuality,
    impactStrength,
    verb: "影响",
    source: "",
    confirmation: "pending"
  };
}

function makeGraph(): SandboxGraph {
  return {
    nodes: [
      node("e1", "external"),
      node("l1", "lever"),
      node("c1", "constraint"),
      node("u1", "unknown"),
      node("i1", "intermediate"),
      node("k1", "indicator"),
      node("o1", "outcome"),
      node("d1", "decision")
    ],
    edges: [
      edge("edge-1", "e1", "i1", "evidence", "strong"),
      edge("edge-2", "c1", "i1", "human_constraint"),
      edge("edge-3", "u1", "i1", "assumed", "weak"),
      edge("edge-4", "i1", "o1", "evidence"),
      edge("orphan", "ghost", "i1", "evidence")
    ],
    hardConstraints: [],
    draft: true
  };
}

describe("columnOfKind", () => {
  test("maps the eight canonical kinds onto three layers", () => {
    expect(columnOfKind("external")).toBe("input");
    expect(columnOfKind("lever")).toBe("input");
    expect(columnOfKind("constraint")).toBe("input");
    expect(columnOfKind("unknown")).toBe("input");
    expect(columnOfKind("intermediate")).toBe("middle");
    expect(columnOfKind("indicator")).toBe("middle");
    expect(columnOfKind("outcome")).toBe("output");
    expect(columnOfKind("decision")).toBe("output");
  });
});

describe("relationTone / causalEdgeWidth", () => {
  test("relation quality -> tone (assumed is the only dashed tone)", () => {
    expect(relationTone("evidence")).toBe("evidence");
    expect(relationTone("human_constraint")).toBe("human");
    expect(relationTone("assumed")).toBe("assumed");
  });

  test("impact strength -> stroke width tiers", () => {
    expect(causalEdgeWidth("strong")).toBe(2.4);
    expect(causalEdgeWidth("moderate")).toBe(1.8);
    expect(causalEdgeWidth("weak")).toBe(1.2);
  });
});

describe("buildCausalGraphLayout", () => {
  test("is deterministic: identical input produces identical layout", () => {
    const graph = makeGraph();
    expect(buildCausalGraphLayout(graph)).toEqual(buildCausalGraphLayout(graph));
  });

  test("places each column at its fixed x and stacks rows in wire order", () => {
    const { nodes } = buildCausalGraphLayout(makeGraph());
    const byId = new Map(nodes.map((placed) => [placed.id, placed]));
    expect(byId.get("e1")).toMatchObject({ column: "input", x: CAUSAL_COLUMN_X.input, y: 0 });
    expect(byId.get("l1")).toMatchObject({ y: CAUSAL_NODE_Y_GAP });
    expect(byId.get("c1")).toMatchObject({ y: 2 * CAUSAL_NODE_Y_GAP });
    expect(byId.get("u1")).toMatchObject({ y: 3 * CAUSAL_NODE_Y_GAP });
    expect(byId.get("i1")).toMatchObject({ column: "middle", x: CAUSAL_COLUMN_X.middle, y: 0 });
    expect(byId.get("k1")).toMatchObject({ y: CAUSAL_NODE_Y_GAP });
    expect(byId.get("o1")).toMatchObject({ column: "output", x: CAUSAL_COLUMN_X.output, y: 0 });
    expect(byId.get("d1")).toMatchObject({ y: CAUSAL_NODE_Y_GAP });
  });

  test("edge semantics: evidence/human solid, assumed dashed, orphan dropped, verb carried", () => {
    const { edges } = buildCausalGraphLayout(makeGraph());
    expect(edges).toHaveLength(4); // orphan edge dropped
    const byId = new Map(edges.map((flowEdge) => [flowEdge.id, flowEdge]));
    expect(byId.get("edge-1")).toMatchObject({ tone: "evidence", dashed: false, strokeWidth: 2.4, label: "影响" });
    expect(byId.get("edge-2")).toMatchObject({ tone: "human", dashed: false, strokeWidth: 1.8 });
    expect(byId.get("edge-3")).toMatchObject({ tone: "assumed", dashed: true, strokeWidth: 1.2 });
    expect(byId.has("orphan")).toBe(false);
  });
});
