// Task 13 Step 5: graph review ordered by decision impact. Items that would
// change the recommendation, trigger a hard constraint, or are high-impact
// with low relation quality come first; everything else is collapsed behind
// a safe batch confirm. While any item is unconfirmed the draft cannot be
// saved as a formal graph version and cannot run a FORMAL SimulationRun
// (UI feedback only — the API stays the enforcer); the draft may still run
// clearly-marked experimental simulations.

import { useState } from "react";

import type { SandboxGraph, SandboxGraphEdge } from "./types";

export type ReviewableItem = {
  id: string;
  kind: "node" | "edge";
  title: string;
  reason: string | null;
  priority: boolean;
};

function edgePriorityReason(edge: SandboxGraphEdge): string | null {
  if (edge.wouldChangeRecommendation) return "会改变推荐";
  if (edge.triggersHardConstraint) return "触发硬约束";
  if (edge.impactStrength === "strong" && edge.relationQuality === "assumed") {
    return "高影响但关系质量低";
  }
  return null;
}

export function buildReviewItems(
  graph: SandboxGraph,
  confirmations: Record<string, boolean>,
): ReviewableItem[] {
  const items: ReviewableItem[] = [];
  for (const node of graph.nodes) {
    if (confirmations[node.id]) continue;
    items.push({
      id: node.id,
      kind: "node",
      title: node.title,
      reason: node.kind === "constraint" ? "触发硬约束" : null,
      priority: node.kind === "constraint" || node.kind === "unknown",
    });
  }
  for (const edge of graph.edges) {
    if (confirmations[edge.id]) continue;
    const reason = edgePriorityReason(edge);
    items.push({
      id: edge.id,
      kind: "edge",
      title: `${edge.from} ${edge.verb} → ${edge.to}`,
      reason,
      priority: reason !== null,
    });
  }
  return [...items.filter((item) => item.priority), ...items.filter((item) => !item.priority)];
}

type GraphConfirmationPanelProps = {
  graph: SandboxGraph;
  confirmations: Record<string, boolean>;
  onConfirm: (id: string) => void;
  onBatchConfirm: (ids: string[]) => void;
};

export function GraphConfirmationPanel({
  graph,
  confirmations,
  onConfirm,
  onBatchConfirm,
}: GraphConfirmationPanelProps) {
  const [restExpanded, setRestExpanded] = useState(false);
  const items = buildReviewItems(graph, confirmations);
  const priorityItems = items.filter((item) => item.priority);
  const restItems = items.filter((item) => !item.priority);
  const allConfirmed = items.length === 0;

  return (
    <section className="graph-confirmation" aria-label="图审阅与确认">
      <header className="section-line-heading">
        <div>
          <span>按决策影响排序</span>
          <h3>图审阅</h3>
        </div>
        <small>{allConfirmed ? "全部项目已确认" : `${items.length} 项待确认`}</small>
      </header>

      {priorityItems.length > 0 ? (
        <ul className="confirmation-priority" aria-label="优先审阅项">
          {priorityItems.map((item) => (
            <li key={item.id}>
              <b>{item.title}</b>
              {item.reason ? <small>{item.reason}</small> : null}
              <button type="button" onClick={() => onConfirm(item.id)}>
                确认
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {restItems.length > 0 ? (
        <div className="confirmation-rest">
          <button
            type="button"
            className="text-action"
            aria-expanded={restExpanded}
            onClick={() => setRestExpanded((value) => !value)}
          >
            其余 {restItems.length} 项（低影响）
          </button>
          <button
            type="button"
            className="secondary-action"
            onClick={() => onBatchConfirm(restItems.map((item) => item.id))}
          >
            安全批量确认其余项
          </button>
          {restExpanded ? (
            <ul aria-label="其余待确认项">
              {restItems.map((item) => (
                <li key={item.id}>
                  <b>{item.title}</b>
                  <button type="button" onClick={() => onConfirm(item.id)}>
                    确认
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      {!allConfirmed ? (
        <p className="confirmation-gate-note" role="note">
          未完成确认的草稿不能保存为正式图版本，也不能运行正式（formal）模拟；仍可运行明确标记的实验（experimental）模拟。此处的禁用只是前端反馈，正式运行由 API 校验兜底。
        </p>
      ) : null}
    </section>
  );
}
