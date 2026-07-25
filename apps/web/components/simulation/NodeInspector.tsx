// Task 13 Step 5: node inspector — business value, baseline, range, source,
// applicability limits and confirmation status, ordered for decision impact.

import { NODE_KIND_META } from "./CausalCanvas";
import type { SandboxGraphNode } from "./types";

type NodeInspectorProps = {
  node: SandboxGraphNode;
  confirmed: boolean;
  onConfirm: (nodeId: string) => void;
};

export function NodeInspector({ node, confirmed, onConfirm }: NodeInspectorProps) {
  const meta = NODE_KIND_META[node.kind];
  return (
    <aside className="node-inspector" aria-label={`节点检查器：${node.title}`}>
      <header>
        <span>
          <i aria-hidden="true">{meta.glyph}</i> {meta.label}
        </span>
        <h3>{node.title}</h3>
      </header>
      <dl>
        <div>
          <dt>业务值</dt>
          <dd>{node.businessValue}</dd>
        </div>
        <div>
          <dt>基线</dt>
          <dd>{node.baseline}</dd>
        </div>
        <div>
          <dt>区间</dt>
          <dd>{node.range}</dd>
        </div>
        <div>
          <dt>来源</dt>
          <dd>{node.source}</dd>
        </div>
        {node.applicability ? (
          <div>
            <dt>适用限制</dt>
            <dd>{node.applicability}</dd>
          </div>
        ) : null}
        <div>
          <dt>确认状态</dt>
          <dd>{confirmed ? "已确认" : "未确认"}</dd>
        </div>
      </dl>
      {!confirmed ? (
        <button type="button" className="secondary-action" onClick={() => onConfirm(node.id)}>
          确认此节点
        </button>
      ) : null}
    </aside>
  );
}
