// Task 13 Step 4: full causal model canvas, mounted ONLY after the user
// clicks 展开完整模型 (progressive disclosure). Highlights the currently
// tested variable, the key path and the outcome nodes; node size, ports
// and labels stay stable. Node kinds are distinguished by shape class,
// border style, icon glyph AND text label together — never by color alone.

import type { NodeKind, SandboxGraph } from "./types";

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

export function CausalCanvas({
  graph,
  testedNodeId,
  highlightedNodeIds,
  selectedNodeId,
  selectedEdgeId,
  onSelectNode,
  onSelectEdge,
}: CausalCanvasProps) {
  const nodeById = new Map(graph.nodes.map((node) => [node.id, node]));
  return (
    <div className="causal-scroll" tabIndex={0} aria-label="可滚动的完整因果模型画布">
      <div className="causal-canvas" role="group" aria-label="完整因果模型">
        <div className="model-legend" aria-label="模型节点图例">
          {Object.entries(NODE_KIND_META).map(([kind, meta]) => (
            <span key={kind}>
              <i aria-hidden="true">{meta.glyph}</i>
              {meta.label}
            </span>
          ))}
          <small>形状 / 边框 / 图标 / 文字共同区分节点类型，不依赖颜色</small>
        </div>

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

        <div className="canvas-note">
          <span>关系说明</span>
          <p>待验证假设不会成为正式决定，除非你确认并主动运行。</p>
        </div>
      </div>
    </div>
  );
}
