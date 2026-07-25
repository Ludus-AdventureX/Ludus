// Task 13 Step 3: validation action CTA. Fragile UNKNOWN items generate
// candidate validation actions. The action ONLY creates a CandidateRevision
// (status "candidate") surfaced through onCreate — it never updates the
// formal archive and never invents a backend write route.

import type { CandidateRevision, FragileCondition } from "./types";

type ValidationActionCTAProps = {
  condition: FragileCondition;
  onCreate: (revision: CandidateRevision) => void;
  /** 已生成的候选验证行动（本工作副本内）。 */
  created: CandidateRevision[];
  /** 证据不足时 CTA 是主动作。 */
  primary: boolean;
};

export function ValidationActionCTA({ condition, onCreate, created, primary }: ValidationActionCTAProps) {
  const existing = created.filter((revision) => revision.sourceNodeId === condition.nodeId);

  const create = () => {
    onCreate({
      kind: "validation_action",
      status: "candidate",
      title: `验证「${condition.title}」`,
      detail: `${condition.impactNote}（${condition.businessDomain}，单位：${condition.unit}）。补齐该项证据后再回到沙盘复测。`,
      sourceNodeId: condition.nodeId,
    });
  };

  return (
    <section className="validation-action" aria-label="验证行动">
      <button
        type="button"
        className={primary ? "primary-action" : "secondary-action"}
        onClick={create}
      >
        <span>生成验证行动</span>
        <small>只创建候选修订，不直接更新正式档案</small>
      </button>
      {existing.length > 0 ? (
        <ul className="candidate-revision-list" aria-label="候选修订">
          {existing.map((revision, index) => (
            <li key={`${revision.sourceNodeId}-${index}`}>
              <b>{revision.title}</b>
              <small>候选修订 · {revision.detail}</small>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
