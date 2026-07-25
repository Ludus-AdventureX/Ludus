// Task 13 Step 2: the (max) three most fragile conditions. Business unit,
// controllability, evidence status and one impact sentence each; selecting a
// condition focuses the stress-test control on it.

import type { Controllability, EvidenceStatus, FragileCondition } from "./types";

const CONTROLLABILITY_LABEL: Record<Controllability, string> = {
  controllable: "可控",
  partially_controllable: "部分可控",
  external: "外部因素",
};

const EVIDENCE_LABEL: Record<EvidenceStatus, string> = {
  confirmed: "证据确认",
  conditional: "条件性证据",
  assumed: "待验证假设",
  unknown: "未知项",
};

type FragileConditionListProps = {
  conditions: FragileCondition[];
  selectedNodeId: string | null;
  onSelect: (nodeId: string) => void;
};

export function FragileConditionList({ conditions, selectedNodeId, onSelect }: FragileConditionListProps) {
  const topThree = conditions.slice(0, 3);
  return (
    <nav className="fragile-index" aria-label="Fragile conditions">
      {topThree.map((condition, index) => {
        const active = condition.nodeId === selectedNodeId;
        return (
          <button
            key={condition.nodeId}
            type="button"
            className={active ? "is-active" : undefined}
            aria-pressed={active}
            onClick={() => onSelect(condition.nodeId)}
          >
            <span>{String(index + 1).padStart(2, "0")}</span>
            <b>{condition.title}</b>
            <small>
              {condition.businessDomain} · {CONTROLLABILITY_LABEL[condition.controllability]} ·{" "}
              {EVIDENCE_LABEL[condition.evidenceStatus]}
            </small>
            <small className="fragile-impact-note">{condition.impactNote}</small>
          </button>
        );
      })}
    </nav>
  );
}
