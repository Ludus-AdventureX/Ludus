// Formal slot/props contract for the five-workspace case shell
// (Task 11 Phase 0 Session B; prose version in
// docs/handoffs/TASK11_PHASE0_SHELL_B_HANDOFF.md §slot 合同).
//
// Rules for every later phase (Charter / Progress / QualityGate / Evidence /
// Task 14W Decision-Review):
//   1. Fill or replace ONLY the node carrying your `data-phase-slot` anchor
//      (or the documented replacement prop); never restructure the shell,
//      the spine, the view router or another slot.
//   2. The shell guarantees exactly the props listed here — nothing else.
//      Run/report/evidence state is owned by the filling phase and must come
//      from real APIs, never from shell-side mocks.
//   3. Slot names are frozen; adding a slot requires a new shell session,
//      not an in-phase edit.

import type { ReactNode } from "react";

import type { DecisionHealthSegmentId } from "@/components/shell/DecisionHealthBar";
import type { PhaseSlotName } from "@/components/shell/PhaseSlot";

// --- Props boundaries (what the shell provides to each slot filler) -------

/** AnalysisCharterForm (Task 11 Step 2) — WorkspaceView intro-actions. */
export type AnalysisCharterFormSlotProps = { decisionCaseId: string };

/** AnalysisProgress (Task 11 Step 3) — AnalysisView analysis-trace. */
export type AnalysisProgressSlotProps = { decisionCaseId: string };

/** QualityGatePanel (Task 11 Step 5) — AnalysisView quality-margin. */
export type QualityGatePanelSlotProps = { decisionCaseId: string };

/** EvidenceDrawer trigger (Task 11 Step 4) — AnalysisView custody-strip / ReportView dissent-page. */
export type EvidenceDrawerTriggerSlotProps = { decisionCaseId: string };

/** DecisionHealthBar segment click slot — WorkspaceView ledger-body (skeleton filled by Session B). */
export type DecisionHealthBarSlotProps = {
  onSelectSegment?: (segment: DecisionHealthSegmentId) => void;
};

/** Task 14W Decision signoff — DecisionView intro-actions. */
export type DecisionSignoffSlotProps = { decisionCaseId: string };

/** Task 14W ReviewDialog trigger — replaces DecisionSpine's disabled step via the `reviewSlot` prop. */
export type ReviewDialogTriggerSlotProps = {
  decisionCaseId: string | null;
  /** The rendered trigger node passed to `DecisionSpine reviewSlot`. */
  children?: ReactNode;
};

/** ProjectDrawer (filled by Session B) — CaseShell masthead trigger + drawer mount. */
export type ProjectDrawerSlotProps = {
  open: boolean;
  decisionCaseId: string | null;
  onClose: () => void;
};

/** SandboxWorkspace (Task 13, authorized shell increment) — SandboxView pressure-mode mount. */
export type SandboxWorkspaceSlotProps = { decisionCaseId: string };

// --- Contract registry -----------------------------------------------------

export type SlotContractEntry = {
  /** Where the anchor lives (component + Look V7 region). */
  host: string;
  /** Who is allowed to fill it. */
  owner: string;
  /** reserved = anchor placeholder still rendered; filled = production component mounted. */
  status: "reserved" | "filled";
  /** How the phase mounts: replace the PhaseSlot node or use the documented prop. */
  mount: "replace-phase-slot-node" | "prop";
};

export const shellSlotContract: Record<PhaseSlotName, SlotContractEntry> = {
  "analysis-charter-form": {
    host: "views/WorkspaceView intro-actions",
    owner: "AnalysisCharterForm（Task 11 Step 2）",
    status: "reserved",
    mount: "replace-phase-slot-node"
  },
  "analysis-progress": {
    host: "views/AnalysisView analysis-trace",
    owner: "AnalysisProgress（Task 11 Step 3）",
    status: "reserved",
    mount: "replace-phase-slot-node"
  },
  "quality-gate-panel": {
    host: "views/AnalysisView quality-margin",
    owner: "QualityGatePanel（Task 11 Step 5）",
    status: "reserved",
    mount: "replace-phase-slot-node"
  },
  "evidence-drawer-trigger": {
    host: "views/AnalysisView custody-strip；views/ReportView dissent-page",
    owner: "EvidenceDrawer（Task 11 Step 4）",
    status: "reserved",
    mount: "replace-phase-slot-node"
  },
  "decision-health-bar": {
    host: "views/WorkspaceView ledger-body",
    owner: "DecisionHealthBar 骨架（会话 B 已挂载）；分项数据由各负责 Phase 接入",
    status: "filled",
    mount: "replace-phase-slot-node"
  },
  "decision-signoff": {
    host: "views/DecisionView intro-actions",
    owner: "Task 14W Decision signoff",
    status: "reserved",
    mount: "replace-phase-slot-node"
  },
  "review-dialog-trigger": {
    host: "DecisionSpine 第六步（disabled 占位）",
    owner: "Task 14W ReviewDialog（经 DecisionSpine reviewSlot prop 替换）",
    status: "reserved",
    mount: "prop"
  },
  "project-drawer": {
    host: "CaseShell masthead case-title trigger + drawer mount",
    owner: "ProjectDrawer（会话 B 已挂载）",
    status: "filled",
    mount: "replace-phase-slot-node"
  },
  "sandbox-workspace": {
    host: "views/SandboxView pressure-mode（Look V7 #view-sandbox）",
    owner: "SandboxWorkspace（Task 13，经授权的最小 shell 增量；无真实档案输入时保持诚实空态）",
    status: "filled",
    mount: "replace-phase-slot-node"
  }
};
