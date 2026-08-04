"use client";

// Look V7 `#view-sandbox` view frame. Phase 0 shipped the static skeleton;
// Task 13 (authorized minimal shell increment) mounts the SandboxWorkspace
// through the sandbox-workspace slot. READ-01 flip: with the canonical case
// sandbox read surface mounted, this view loads the real inputs
// asynchronously; while loading, without a workspace anchor, or when any
// required block is missing, the workspace keeps its honest empty frame —
// nothing is simulated or fabricated here.

import { useEffect, useState } from "react";

import { DeliberationBoard } from "@/components/deliberation/DeliberationBoard";
import { SandboxWorkspace } from "@/components/simulation/SandboxWorkspace";
import { FactorSandboxPanel } from "@/components/shell/views/FactorSandboxPanel";
import { loadSandboxCaseData } from "@/components/simulation/sandboxData";
import type { SandboxCaseData } from "@/components/simulation/types";
import type { SandboxWorkspaceSlotProps } from "@/lib/shell/slotContracts";

export type SandboxViewProps = SandboxWorkspaceSlotProps & {
  workspaceId?: string | null;
  fetchImpl?: typeof fetch;
};

export function SandboxView({ workspaceId = null, decisionCaseId, fetchImpl }: SandboxViewProps) {
  const [data, setData] = useState<SandboxCaseData | null>(null);

  useEffect(() => {
    if (!workspaceId || !decisionCaseId) return;
    let cancelled = false;
    void loadSandboxCaseData(workspaceId, decisionCaseId, fetchImpl ?? fetch).then((result) => {
      if (!cancelled) setData(result);
    });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, decisionCaseId, fetchImpl]);

  return (
    <section className="view is-active" id="view-sandbox" data-view-panel="sandbox" aria-labelledby="sandbox-view-title">
      <FactorSandboxPanel
        {...(workspaceId ? { workspaceId } : {})}
        {...(decisionCaseId ? { decisionCaseId } : {})}
      />
      <DeliberationBoard
        {...(workspaceId ? { workspaceId } : {})}
        {...(decisionCaseId ? { decisionCaseId } : {})}
      />
      <SandboxWorkspace decisionCaseId={decisionCaseId} data={data} />
    </section>
  );
}
