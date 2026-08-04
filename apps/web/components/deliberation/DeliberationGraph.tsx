"use client";

// Deliberation board graph (CCR-20260804-DELIB-01, Wave 3): the council's
// factor chessboard. Objective factors carry solid borders (engine-derived
// evidence), subjective factors are dashed + human-accent with a Human
// signature corner badge — assumed/unknown identity is visible, never
// impersonating evidence. The outcome node shows the latest engine verdict
// once the council completes. Layout mirrors the factor sandbox: factors in
// the left column, the decision event on the right, deterministic positions.

import { useMemo } from "react";

import {
  Handle,
  Position,
  ReactFlow,
  type Node,
  type NodeProps
} from "@xyflow/react";

import type { DeliberationFactorView, DeliberationOutcomeView } from "@/lib/api/deliberation";

export const DELIBERATION_NODE_X = 40;
export const DELIBERATION_NODE_Y_GAP = 122;
export const DELIBERATION_OUTCOME_X = 620;
export const DELIBERATION_OUTCOME_NODE_ID = "__deliberation_outcome__";

type BoardFactorNodeData = {
  label: string;
  provenance: "objective" | "subjective";
  strengthText: string;
  identityText: string;
};

type BoardOutcomeNodeData = {
  title: string;
  detailText: string;
  settled: boolean;
};

type BoardFactorFlowNode = Node<BoardFactorNodeData, "boardFactor">;
type BoardOutcomeFlowNode = Node<BoardOutcomeNodeData, "boardOutcome">;

function BoardFactorNodeCard({ data }: NodeProps<BoardFactorFlowNode>) {
  return (
    <div
      className="deliberation-board-node"
      data-provenance={data.provenance}
      data-board-node="factor"
    >
      <Handle type="source" position={Position.Right} id="out" isConnectable={false} />
      <span>{data.provenance === "subjective" ? "主观因子 · Human 署名" : "客观因子 · 证据基线"}</span>
      <b>{data.label}</b>
      <small>{`${data.strengthText} · ${data.identityText}`}</small>
    </div>
  );
}

function BoardOutcomeNodeCard({ data }: NodeProps<BoardOutcomeFlowNode>) {
  return (
    <div
      className="deliberation-board-outcome"
      data-board-settled={data.settled ? "true" : "false"}
      data-board-node="outcome"
    >
      <Handle type="target" position={Position.Left} id="in" isConnectable={false} />
      <span>决策事件</span>
      <b>{data.title}</b>
      <small>{data.detailText}</small>
    </div>
  );
}

const BOARD_NODE_TYPES = {
  boardFactor: BoardFactorNodeCard,
  boardOutcome: BoardOutcomeNodeCard
} as const;

export function deliberationBoardLayout(factorCount: number): {
  factorY: (index: number) => number;
  outcomeY: number;
} {
  const stackHeight = factorCount > 0 ? (factorCount - 1) * DELIBERATION_NODE_Y_GAP : 0;
  return {
    factorY: (index: number) => index * DELIBERATION_NODE_Y_GAP,
    outcomeY: stackHeight / 2
  };
}

export type DeliberationGraphProps = {
  factors: DeliberationFactorView[];
  outcome: DeliberationOutcomeView | null;
  statusText: string;
};

export function DeliberationGraph({ factors, outcome, statusText }: DeliberationGraphProps) {
  const nodes = useMemo<Array<BoardFactorFlowNode | BoardOutcomeFlowNode>>(() => {
    const layout = deliberationBoardLayout(factors.length);
    const projection = outcome?.conditionProjections?.[outcome.conditionProjections.length - 1];
    const verdictText = projection?.projection?.verdict;
    const factorNodes: BoardFactorFlowNode[] = factors.map((factor, index) => ({
      id: factor.id,
      type: "boardFactor",
      position: { x: DELIBERATION_NODE_X, y: layout.factorY(index) },
      draggable: false,
      selectable: false,
      data: {
        label: factor.label,
        provenance: factor.provenance,
        strengthText: `强度 ${(factor.strength * 100).toFixed(0)}%`,
        identityText:
          factor.provenance === "subjective"
            ? factor.evidenceStatus ?? "assumed"
            : "evidence-backed"
      }
    }));
    const outcomeNode: BoardOutcomeFlowNode = {
      id: DELIBERATION_OUTCOME_NODE_ID,
      type: "boardOutcome",
      position: { x: DELIBERATION_OUTCOME_X, y: layout.outcomeY },
      draggable: false,
      selectable: false,
      data: {
        title: outcome
          ? verdictText === "proceed"
            ? "推进"
            : verdictText === "hold"
              ? "按住/再等等"
              : "已裁决"
          : "推演中",
        detailText: outcome
          ? `${outcome.conditionProjections.length} 组条件投影 · ${outcome.disclaimer}`
          : statusText,
        settled: outcome !== null
      }
    };
    return [...factorNodes, outcomeNode];
  }, [factors, outcome, statusText]);

  return (
    <div className="deliberation-board-canvas" role="group" aria-label="推演棋盘：因子与决策事件">
      <ReactFlow
        nodes={nodes}
        edges={[]}
        nodeTypes={BOARD_NODE_TYPES}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        fitView
        fitViewOptions={{ padding: 0.18, maxZoom: 1 }}
        minZoom={0.35}
        maxZoom={1.4}
        proOptions={{ hideAttribution: false }}
      />
    </div>
  );
}
