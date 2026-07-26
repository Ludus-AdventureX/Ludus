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
  /** Tenant workspace id (READ-01 flip threading; null = anchors stay gap). */
  tenantWorkspaceId?: string | null;
  activeWorkspace: CaseWorkspaceId;
};

export function CaseViewRouter({
  decisionCaseId,
  tenantWorkspaceId = null,
  activeWorkspace
}: CaseViewRouterProps) {
  if (!decisionCaseId) {
    return <EmptyCaseView />;
  }
  switch (activeWorkspace) {
    case "analysis":
      return <AnalysisView workspaceId={tenantWorkspaceId} decisionCaseId={decisionCaseId} />;
    case "report":
      return <ReportView workspaceId={tenantWorkspaceId} decisionCaseId={decisionCaseId} />;
    case "sandbox":
      return <SandboxView workspaceId={tenantWorkspaceId} decisionCaseId={decisionCaseId} />;
    case "decision":
      return <DecisionView />;
    case "workspace":
    default:
      return <WorkspaceView decisionCaseId={decisionCaseId} workspaceId={tenantWorkspaceId} />;
  }
}
