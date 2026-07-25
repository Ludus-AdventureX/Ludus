// Task 13 Step 5: edge inspector — relation quality, impact strength,
// source, applicability limits and confirmation status.

import type { SandboxGraphEdge, SandboxGraphNode } from "./types";

const QUALITY_LABEL: Record<SandboxGraphEdge["relationQuality"], string> = {
  evidence: "证据支持",
  human_constraint: "人的约束",
  assumed: "待验证假设",
};

const STRENGTH_LABEL: Record<SandboxGraphEdge["impactStrength"], string> = {
  strong: "影响强",
  moderate: "影响中",
  weak: "影响弱",
};

type EdgeInspectorProps = {
  edge: SandboxGraphEdge;
  fromNode: SandboxGraphNode | null;
  toNode: SandboxGraphNode | null;
  confirmed: boolean;
  onConfirm: (edgeId: string) => void;
};

export function EdgeInspector({ edge, fromNode, toNode, confirmed, onConfirm }: EdgeInspectorProps) {
  return (
    <aside className="edge-inspector" aria-label="关系检查器">
      <header>
        <span>因果关系</span>
        <h3>
          {fromNode?.title ?? edge.from} {edge.verb} → {toNode?.title ?? edge.to}
        </h3>
      </header>
      <dl>
        <div>
          <dt>关系质量</dt>
          <dd>{QUALITY_LABEL[edge.relationQuality]}</dd>
        </div>
        <div>
          <dt>影响强度</dt>
          <dd>{STRENGTH_LABEL[edge.impactStrength]}</dd>
        </div>
        <div>
          <dt>来源</dt>
          <dd>{edge.source}</dd>
        </div>
        {edge.applicability ? (
          <div>
            <dt>适用限制</dt>
            <dd>{edge.applicability}</dd>
          </div>
        ) : null}
        <div>
          <dt>确认状态</dt>
          <dd>{confirmed ? "已确认" : "未确认"}</dd>
        </div>
      </dl>
      {!confirmed ? (
        <button type="button" className="secondary-action" onClick={() => onConfirm(edge.id)}>
          确认此关系
        </button>
      ) : null}
    </aside>
  );
}
