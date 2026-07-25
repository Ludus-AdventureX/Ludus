// Public DecisionHealthBar skeleton (Task 11 plan §DecisionHealthBar,
// filled by Session B). Five segments — 证据 / 因果链 / 战略稳健性 / 质量门 /
// 版本 — each will link to the detail surface that owns its state in a later
// phase. Deliberately NO total confidence percentage and no fabricated
// per-segment verdicts: every segment reports "未接入" until real state
// arrives through the owning phase.

export const decisionHealthSegments = [
  { id: "evidence", coordinate: "E", label: "证据", owner: "证据账本（Task 11 Step 4）" },
  { id: "causal-chain", coordinate: "C", label: "因果链", owner: "推演模型（Task 12/13 UI）" },
  { id: "strategic-robustness", coordinate: "S", label: "战略稳健性", owner: "五视角报告（Task 11 Step 6）" },
  { id: "quality-gate", coordinate: "G", label: "质量门", owner: "质量门面板（Task 11 Step 5）" },
  { id: "version", coordinate: "V", label: "版本", owner: "Case 版本档案（Task 4 UI）" }
] as const;

export type DecisionHealthSegmentId = (typeof decisionHealthSegments)[number]["id"];

type DecisionHealthBarProps = {
  /**
   * Per-segment click slot: a later phase wires navigation into the detail
   * surface responsible for that segment. While absent the segments render
   * as disabled placeholders instead of pretending to be clickable.
   */
  onSelectSegment?: (segment: DecisionHealthSegmentId) => void;
};

export function DecisionHealthBar({ onSelectSegment }: DecisionHealthBarProps) {
  return (
    <section className="custody-strip" data-phase-slot="decision-health-bar" aria-label="决策健康栏">
      <span className="custody-title">决策健康 / 分项状态</span>
      {decisionHealthSegments.map(({ id, coordinate, label }) => (
        <button
          key={id}
          type="button"
          data-health-segment={id}
          disabled={!onSelectSegment}
          aria-disabled={onSelectSegment ? undefined : "true"}
          title={onSelectSegment ? undefined : "分项详情由负责该状态的 Phase 接入"}
          onClick={onSelectSegment ? () => onSelectSegment(id) : undefined}
        >
          <i>{coordinate}</i>
          <b>{label}</b>
          <small>未接入</small>
        </button>
      ))}
    </section>
  );
}
