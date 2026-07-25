import { EmptyCaseView } from "@/components/shell/EmptyCaseView";
import { AnalysisView } from "@/components/shell/views/AnalysisView";
import { DecisionView } from "@/components/shell/views/DecisionView";
import { ReportView } from "@/components/shell/views/ReportView";
import { SandboxView } from "@/components/shell/views/SandboxView";
import { WorkspaceView } from "@/components/shell/views/WorkspaceView";
import type { CaseWorkspaceId } from "@/lib/shell/workspaces";

// View router for the five-workspace case shell. Phase 0 mounts one
// structured Look V7 placeholder view per workspace; later phases replace
// the placeholder internals through the reserved PhaseSlot anchors only.

type CaseViewRouterProps = {
  /** null = no decision case selected/created yet -> empty view. */
  decisionCaseId: string | null;
  activeWorkspace: CaseWorkspaceId;
};

export function CaseViewRouter({ decisionCaseId, activeWorkspace }: CaseViewRouterProps) {
  if (!decisionCaseId) {
    return <EmptyCaseView />;
  }
  switch (activeWorkspace) {
    case "analysis":
      return <AnalysisView />;
    case "report":
      return <ReportView />;
    case "sandbox":
      return <SandboxView />;
    case "decision":
      return <DecisionView />;
    case "workspace":
    default:
      return <WorkspaceView decisionCaseId={decisionCaseId} />;
  }
}
