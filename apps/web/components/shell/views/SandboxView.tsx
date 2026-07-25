// Look V7 `#view-sandbox` view frame. Phase 0 shipped the static skeleton;
// Task 13 (authorized minimal shell increment) mounts the SandboxWorkspace
// through the sandbox-workspace slot. With no real case sandbox data
// available (see components/simulation/sandboxData.ts) the workspace renders
// the same honest empty frame; nothing is simulated or fabricated here.

import { SandboxWorkspace } from "@/components/simulation/SandboxWorkspace";
import { loadSandboxCaseData } from "@/components/simulation/sandboxData";
import type { SandboxWorkspaceSlotProps } from "@/lib/shell/slotContracts";

export function SandboxView({ decisionCaseId }: SandboxWorkspaceSlotProps) {
  return (
    <section className="view is-active" id="view-sandbox" data-view-panel="sandbox" aria-labelledby="sandbox-view-title">
      <SandboxWorkspace decisionCaseId={decisionCaseId} data={loadSandboxCaseData(decisionCaseId)} />
    </section>
  );
}
