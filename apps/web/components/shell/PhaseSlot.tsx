// Stable mount anchor for later Task 11 phases and Task 14W.
// Later phases fill these slots; they must not restructure the shell around
// them. Session B documents the slot/props contract in the handoff.

export type PhaseSlotName =
  | "analysis-charter-form"
  | "analysis-progress"
  | "quality-gate-panel"
  | "evidence-drawer-trigger"
  | "decision-health-bar"
  | "decision-signoff"
  | "review-dialog-trigger"
  | "project-drawer";

type PhaseSlotProps = {
  name: PhaseSlotName;
  /** Human-readable pending label; keeps the frame honest: no mock data. */
  label: string;
  note?: string;
};

export function PhaseSlot({ name, label, note }: PhaseSlotProps) {
  return (
    <div className="phase-slot" data-phase-slot={name}>
      <span className="margin-label">{label}</span>
      <p>{note ?? "等待后续 Phase 挂载；当前不展示任何伪造数据。"}</p>
    </div>
  );
}
