// Public DecisionHealthBar (Task 11 plan §DecisionHealthBar, filled by
// Session B + decision-health aggregation). Five segments — 证据 / 因果链 /
// 战略稳健性 / 质量门 / 版本 — each links (full-page) to the workspace view
// that owns its state. When a segment has no live state yet it renders as a
// disabled placeholder instead of pretending: loading shows 读取中…, an error
// shows 读取失败, and a legitimately empty surface shows its honest empty
// copy. No total confidence percentage and no fabricated verdicts.

import type { DecisionHealthSegmentState } from "@/lib/shell/decisionHealth";

export const decisionHealthSegments = [
  { id: "evidence", coordinate: "E", label: "证据" },
  { id: "causal-chain", coordinate: "C", label: "因果链" },
  { id: "strategic-robustness", coordinate: "S", label: "战略稳健性" },
  { id: "quality-gate", coordinate: "G", label: "质量门" },
  { id: "version", coordinate: "V", label: "版本" }
] as const;

export type DecisionHealthSegmentId = (typeof decisionHealthSegments)[number]["id"];

type DecisionHealthBarProps = {
  /** Live segment states from useDecisionHealth; default = loading placeholders. */
  segments?: DecisionHealthSegmentState[];
};

export function DecisionHealthBar({ segments }: DecisionHealthBarProps) {
  const rows = segments ?? [];
  return (
    <section className="custody-strip" data-phase-slot="decision-health-bar" aria-label="决策健康栏">
      <span className="custody-title">决策健康 / 分项状态</span>
      {rows.map(({ id, coordinate, label, href, status, summary }) =>
        href ? (
          <a
            key={id}
            className="health-segment"
            data-health-segment={id}
            data-health-status={status}
            href={href}
            title={`${label}：${summary}`}
          >
            <i>{coordinate}</i>
            <b>{label}</b>
            <small>{summary}</small>
          </a>
        ) : (
          <button
            key={id}
            type="button"
            className="health-segment"
            data-health-segment={id}
            data-health-status={status}
            disabled
            aria-disabled="true"
            title={`${label}：${summary}`}
          >
            <i>{coordinate}</i>
            <b>{label}</b>
            <small>{summary}</small>
          </button>
        ),
      )}
    </section>
  );
}
