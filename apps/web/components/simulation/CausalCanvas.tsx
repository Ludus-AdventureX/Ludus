"use client";

// Task 13 Step 4 + Route B: full causal model canvas, mounted ONLY after the
// user clicks 展开完整模型 (progressive disclosure). Route B replaces the
// legacy node-button/edge-text lists with a real spatial graph on
// @xyflow/react: eight node kinds in three layers (inputs -> intermediates
// -> outputs), edge line style carrying relation quality (evidence/human
// constraint = solid, assumed = dashed). Highlights the currently tested
// variable, the located impact path and selection; node kinds stay
// distinguishable by shape class, border style, icon glyph AND text label
// together — never by color alone. Runtimes without ResizeObserver (jsdom)
// keep the legacy list render verbatim — the honest fallback.

import { useMemo, useState } from "react";

import {
  Background,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps
} from "@xyflow/react";
// xyflow base styles ship as the vendored app/xyflow.css (imported once by
// the root layout): the node_modules CSS path breaks vitest's PostCSS chain.

import {
  buildCausalGraphLayout,
  type CausalGraphEdgeLayout
} from "./causalGraphLayout";
import type { NodeKind, SandboxGraph, SandboxGraphNode } from "./types";

export const NODE_KIND_META: Record<NodeKind, { label: string; glyph: string; shapeClass: string }> = {
  lever: { label: "可控杠杆", glyph: "◎", shapeClass: "node-lever" },
  external: { label: "外部因素", glyph: "◇", shapeClass: "node-external" },
  constraint: { label: "硬约束", glyph: "▣", shapeClass: "node-constraint" },
  unknown: { label: "未知项", glyph: "？", shapeClass: "node-unknown" },
  intermediate: { label: "中间变量", glyph: "○", shapeClass: "node-center" },
  indicator: { label: "指标", glyph: "◔", shapeClass: "node-indicator" },
  outcome: { label: "结果", glyph: "★", shapeClass: "node-outcome" },
  decision: { label: "决策", glyph: "◆", shapeClass: "node-decision" },
};

type CausalCanvasProps = {
  graph: SandboxGraph;
  /** 当前被测试的变量节点。 */
  testedNodeId: string | null;
  /** 需要高亮的关键路径节点集合（含结果节点）。 */
  highlightedNodeIds: ReadonlySet<string>;
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  onSelectNode: (nodeId: string) => void;
  onSelectEdge: (edgeId: string) => void;
};

function ModelLegend() {
  return (
    <div className="model-legend" aria-label="模型节点图例">
      {Object.entries(NODE_KIND_META).map(([kind, meta]) => (
        <span key={kind}>
          <i aria-hidden="true">{meta.glyph}</i>
          {meta.label}
        </span>
      ))}
      <small>形状 / 边框 / 图标 / 文字共同区分节点类型，不依赖颜色</small>
    </div>
  );
}

function CanvasNote() {
  return (
    <div className="canvas-note">
      <span>关系说明</span>
      <p>待验证假设不会成为正式决定，除非你确认并主动运行。</p>
    </div>
  );
}

// --- Legacy list render: jsdom fallback + accessible non-spatial form -----

function CausalCanvasList({
  graph,
  testedNodeId,
  highlightedNodeIds,
  selectedNodeId,
  selectedEdgeId,
  onSelectNode,
  onSelectEdge
}: CausalCanvasProps) {
  const nodeById = new Map(graph.nodes.map((node) => [node.id, node]));
  return (
    <div className="causal-scroll" tabIndex={0} aria-label="可滚动的完整因果模型画布">
      <div className="causal-canvas" role="group" aria-label="完整因果模型">
        <ModelLegend />

        <ul className="causal-node-list">
          {graph.nodes.map((node) => {
            const meta = NODE_KIND_META[node.kind];
            const tested = node.id === testedNodeId;
            const highlighted = highlightedNodeIds.has(node.id);
            return (
              <li key={node.id}>
                <button
                  type="button"
                  className={[
                    "causal-node",
                    meta.shapeClass,
                    tested ? "is-tested" : "",
                    highlighted ? "is-on-path" : "",
                    node.id === selectedNodeId ? "is-selected" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  data-node-id={node.id}
                  data-node-kind={node.kind}
                  data-tested={tested || undefined}
                  data-highlighted={highlighted || undefined}
                  aria-pressed={node.id === selectedNodeId}
                  onClick={() => onSelectNode(node.id)}
                >
                  <span>
                    <i aria-hidden="true">{meta.glyph}</i> {meta.label}
                  </span>
                  <b>{node.title}</b>
                  <small>{node.businessValue}</small>
                  {tested ? <small className="node-flag">当前被测试变量</small> : null}
                </button>
              </li>
            );
          })}
        </ul>

        <ul className="causal-edge-list" aria-label="因果关系">
          {graph.edges.map((edge) => {
            const from = nodeById.get(edge.from);
            const to = nodeById.get(edge.to);
            if (!from || !to) return null;
            return (
              <li key={edge.id}>
                <button
                  type="button"
                  className={[
                    "causal-edge",
                    `edge-${edge.relationQuality}`,
                    edge.id === selectedEdgeId ? "is-selected" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  data-edge-id={edge.id}
                  aria-pressed={edge.id === selectedEdgeId}
                  onClick={() => onSelectEdge(edge.id)}
                >
                  <span>
                    {from.title} {edge.verb} → {to.title}
                  </span>
                  <small>
                    {edge.relationQuality === "evidence"
                      ? "证据支持"
                      : edge.relationQuality === "human_constraint"
                        ? "人的约束"
                        : "待验证假设"}
                    {edge.confirmation === "pending" ? " · 未确认" : ""}
                  </small>
                </button>
              </li>
            );
          })}
        </ul>

        <CanvasNote />
      </div>
    </div>
  );
}

// --- Spatial graph render (@xyflow/react) ---------------------------------

type CausalNodeData = {
  kind: NodeKind;
  glyph: string;
  kindLabel: string;
  shapeClass: string;
  title: string;
  businessValue: string;
  tested: boolean;
  onPath: boolean;
  selectedFlag: boolean;
};

type CausalFlowNode = Node<CausalNodeData, "causal">;

function CausalNodeCard({ data }: NodeProps<CausalFlowNode>) {
  return (
    <button
      type="button"
      className={[
        "causal-node",
        data.shapeClass,
        data.tested ? "is-tested" : "",
        data.onPath ? "is-on-path" : "",
        data.selectedFlag ? "is-selected" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      data-node-kind={data.kind}
      data-tested={data.tested || undefined}
      data-highlighted={data.onPath || undefined}
      aria-pressed={data.selectedFlag}
    >
      <Handle type="target" position={Position.Left} id="in" isConnectable={false} />
      <span>
        <i aria-hidden="true">{data.glyph}</i> {data.kindLabel}
      </span>
      <b>{data.title}</b>
      <small>{data.businessValue}</small>
      {data.tested ? <small className="node-flag">当前被测试变量</small> : null}
      <Handle type="source" position={Position.Right} id="out" isConnectable={false} />
    </button>
  );
}

const CAUSAL_NODE_TYPES = { causal: CausalNodeCard } as const;

function toFlowEdge(edge: CausalGraphEdgeLayout, selected: boolean): Edge {
  return {
    id: edge.id,
    source: edge.from,
    target: edge.to,
    sourceHandle: "out",
    targetHandle: "in",
    type: "default",
    label: edge.label,
    className: `cg-edge-${edge.tone}${edge.dashed ? " cg-edge-dashed" : ""}${selected ? " is-selected" : ""}`,
    style: { strokeWidth: edge.strokeWidth },
    markerEnd: { type: MarkerType.ArrowClosed, width: 15, height: 15 }
  };
}

function flowCapable(): boolean {
  return typeof window !== "undefined" && typeof window.ResizeObserver === "function";
}

export function CausalCanvas(props: CausalCanvasProps) {
  const { graph, testedNodeId, highlightedNodeIds, selectedNodeId, selectedEdgeId, onSelectNode, onSelectEdge } = props;
  const [canFlow] = useState<boolean>(() => flowCapable());
  // §11: small screens get a read-only overview — no pan/zoom interaction.
  const [compact] = useState<boolean>(
    () =>
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(max-width: 620px)").matches
  );

  const layout = useMemo(() => buildCausalGraphLayout(graph), [graph]);
  const nodeMetaById = useMemo(
    () => new Map<string, SandboxGraphNode>(graph.nodes.map((node) => [node.id, node])),
    [graph.nodes]
  );

  const nodes = useMemo<CausalFlowNode[]>(() => {
    if (!canFlow) return [];
    return layout.nodes.map((placed) => {
      const source = nodeMetaById.get(placed.id);
      if (!source) return null;
      const meta = NODE_KIND_META[source.kind];
      const node: CausalFlowNode = {
        id: placed.id,
        type: "causal",
        position: { x: placed.x, y: placed.y },
        draggable: false,
        data: {
          kind: source.kind,
          glyph: meta.glyph,
          kindLabel: meta.label,
          shapeClass: meta.shapeClass,
          title: source.title,
          businessValue: source.businessValue,
          tested: placed.id === testedNodeId,
          onPath: highlightedNodeIds.has(placed.id),
          selectedFlag: placed.id === selectedNodeId
        }
      };
      return node;
    }).filter((node): node is CausalFlowNode => node !== null);
  }, [canFlow, layout, nodeMetaById, testedNodeId, highlightedNodeIds, selectedNodeId]);

  const edges = useMemo<Edge[]>(() => {
    if (!canFlow) return [];
    return layout.edges.map((edge) => toFlowEdge(edge, edge.id === selectedEdgeId));
  }, [canFlow, layout.edges, selectedEdgeId]);

  if (!canFlow) {
    return <CausalCanvasList {...props} />;
  }

  return (
    <div className="causal-scroll" tabIndex={0} aria-label="可滚动的完整因果模型画布">
      <div className="causal-canvas causal-canvas--flow" role="group" aria-label="完整因果模型">
        <ModelLegend />
        <div className="causal-graph-viewport">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={CAUSAL_NODE_TYPES}
            onNodeClick={(_event, node) => onSelectNode(node.id)}
            onEdgeClick={(_event, edge) => onSelectEdge(edge.id)}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable={false}
            zoomOnScroll={!compact}
            panOnDrag={!compact}
            fitView
            fitViewOptions={{ padding: 0.12, maxZoom: 1 }}
            minZoom={0.3}
            maxZoom={1.5}
            proOptions={{ hideAttribution: false }}
          >
            <Background gap={28} size={1} />
          </ReactFlow>
        </div>
        <CanvasNote />
      </div>
    </div>
  );
}
