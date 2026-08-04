"use client";

// Route A: spatial graph render of the report factor sandbox — one outcome
// ("decision event") node fed by the factor nodes, plus the factor->factor
// influence edges. Layout is the pure buildFactorGraphLayout; this file only
// maps it onto @xyflow/react (locked tech stack, first real usage). Node
// kinds stay distinguishable by label + shape + line style together, never
// color alone (§11). Nodes are keyboard-focusable buttons.

import { useMemo } from "react";

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

import type { SandboxState } from "@/lib/shell/factorSandbox";

import {
  buildFactorGraphLayout,
  OUTCOME_NODE_ID,
  type FactorGraphEdgeLayout,
  type FactorGraphNodeLayout
} from "./factorGraphLayout";

type FactorNodeData = {
  label: string;
  direction: string;
  directionLabel: string;
  valueText: string;
  weightText: string;
  selected: boolean;
};

type OutcomeNodeData = {
  verdict: "proceed" | "hold";
  scoreText: string;
  thresholdText: string;
  busy: boolean;
};

type FactorFlowNode = Node<FactorNodeData, "factor">;
type OutcomeFlowNode = Node<OutcomeNodeData, "outcome">;

const DIRECTION_LABELS: Record<string, string> = {
  supporting: "支撑",
  opposing: "反向",
  neutral: "中性"
};

function FactorNodeCard({ data }: NodeProps<FactorFlowNode>) {
  return (
    <button
      type="button"
      className={`factor-graph-node${data.selected ? " is-selected" : ""}`}
      data-factor-direction={data.direction}
      data-factor-graph-node="factor"
      aria-pressed={data.selected}
    >
      <Handle type="target" position={Position.Left} id="in" isConnectable={false} />
      <span>{`因子 · ${data.directionLabel}`}</span>
      <b>{data.label}</b>
      <small>{`${data.valueText} · ${data.weightText}`}</small>
      <Handle type="source" position={Position.Right} id="out" isConnectable={false} />
    </button>
  );
}

function OutcomeNodeCard({ data }: NodeProps<OutcomeFlowNode>) {
  return (
    <div className="factor-graph-outcome" data-sandbox-verdict={data.verdict} data-factor-graph-node="outcome">
      <Handle type="target" position={Position.Left} id="in" isConnectable={false} />
      <span>决策事件</span>
      <b>{data.verdict === "proceed" ? "推进" : "按住/再等等"}</b>
      <small>
        {data.scoreText} · {data.thresholdText}
        {data.busy ? " · 重算中…" : ""}
      </small>
    </div>
  );
}

const NODE_TYPES = {
  factor: FactorNodeCard,
  outcome: OutcomeNodeCard
} as const;

function toFlowEdge(edge: FactorGraphEdgeLayout): Edge {
  return {
    id: edge.id,
    source: edge.from,
    target: edge.to,
    sourceHandle: "out",
    targetHandle: "in",
    type: "default",
    label: edge.label,
    className: `fg-edge-${edge.tone}${edge.dashed ? " fg-edge-dashed" : ""}`,
    style: { strokeWidth: edge.strokeWidth },
    markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 }
  };
}

export type FactorGraphCanvasProps = {
  state: SandboxState;
  selectedFactorId: string | null;
  onSelectFactor: (factorId: string) => void;
  busy?: boolean;
};

export function FactorGraphCanvas({ state, selectedFactorId, onSelectFactor, busy = false }: FactorGraphCanvasProps) {
  const layout = useMemo(() => buildFactorGraphLayout(state), [state]);
  const factorById = useMemo(() => new Map(state.factors.map((factor) => [factor.id, factor])), [state.factors]);

  const nodes = useMemo<Array<FactorFlowNode | OutcomeFlowNode>>(() => {
    return layout.nodes.map((node: FactorGraphNodeLayout) => {
      if (node.kind === "outcome") {
        const outcome: OutcomeFlowNode = {
          id: node.id,
          type: "outcome",
          position: { x: node.x, y: node.y },
          selectable: false,
          draggable: false,
          data: {
            verdict: state.verdict,
            scoreText: `倾向得分 ${Math.round(state.outcomeScore * 100)}%`,
            thresholdText: `翻转线 ${Math.round(state.flipThreshold * 100)}%`,
            busy
          }
        };
        return outcome;
      }
      const factor = factorById.get(node.id);
      const shown = factor?.effectiveValue ?? factor?.value ?? 0;
      const flowNode: FactorFlowNode = {
        id: node.id,
        type: "factor",
        position: { x: node.x, y: node.y },
        draggable: false,
        data: {
          label: factor?.label ?? node.id,
          direction: factor?.direction ?? "neutral",
          directionLabel: DIRECTION_LABELS[factor?.direction ?? "neutral"] ?? "中性",
          valueText: `强度 ${Math.round(shown * 100)}%`,
          weightText: `权重 ${(factor?.weight ?? 0).toFixed(2)}`,
          selected: node.id === selectedFactorId
        }
      };
      return flowNode;
    });
  }, [layout, factorById, state.verdict, state.outcomeScore, state.flipThreshold, busy, selectedFactorId]);

  const edges = useMemo(() => layout.edges.map(toFlowEdge), [layout.edges]);

  return (
    <div className="factor-graph-canvas" role="group" aria-label="因子因果图：因素决定决策事件">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        onNodeClick={(_event, node) => {
          if (node.id !== OUTCOME_NODE_ID) onSelectFactor(node.id);
        }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        fitView
        fitViewOptions={{ padding: 0.18, maxZoom: 1 }}
        minZoom={0.4}
        maxZoom={1.5}
        proOptions={{ hideAttribution: false }}
      >
        <Background gap={26} size={1} />
      </ReactFlow>
    </div>
  );
}
