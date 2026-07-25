"use client";

import Image from "next/image";
import { useEffect, useState } from "react";

import { CaseViewRouter } from "@/components/shell/CaseViewRouter";
import { DecisionSpine } from "@/components/shell/DecisionSpine";
import { defaultWorkspaceId, isCaseWorkspaceId, type CaseWorkspaceId } from "@/lib/shell/workspaces";

// Five-workspace case shell (Task 11 Phase 0 Session A).
// Reads no analysis/case APIs yet: the masthead shows an honest
// "not connected" source mode, and the project drawer trigger is a
// reserved slot that Session B replaces with ProjectDrawer.

type CaseShellProps = {
  /** null = empty state (no decision case yet). */
  decisionCaseId: string | null;
};

export function CaseShell({ decisionCaseId }: CaseShellProps) {
  const [activeWorkspace, setActiveWorkspace] = useState<CaseWorkspaceId>(defaultWorkspaceId);
  const [ready, setReady] = useState(false);
  const isEmpty = !decisionCaseId;

  useEffect(() => {
    if (!isEmpty) return;
    document.body.classList.add("empty-case");
    return () => document.body.classList.remove("empty-case");
  }, [isEmpty]);

  // Restore the workspace from the URL so a refresh keeps the user's place.
  useEffect(() => {
    const requestedView = new URLSearchParams(window.location.search).get("view");
    if (isCaseWorkspaceId(requestedView)) setActiveWorkspace(requestedView);
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    const params = new URLSearchParams(window.location.search);
    params.set("view", activeWorkspace);
    window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
  }, [activeWorkspace, ready]);

  return (
    <div className="app-shell">
      <header className="masthead">
        <div className="brand-lockup" aria-label="Ludus">
          <Image className="brand-logo" src="/ludus-logo.svg" alt="Ludus" width={1478} height={406} priority />
        </div>
        <div className="case-title">
          <span>当前议题</span>
          <button
            type="button"
            data-phase-slot="project-drawer"
            aria-haspopup="dialog"
            aria-expanded={false}
            disabled
            aria-disabled="true"
            title="项目抽屉由会话 B 接入"
          >
            <span>{decisionCaseId ? `决策项目 ${decisionCaseId}` : "尚未创建决策项目"}</span> <i aria-hidden="true">{"\u2304"}</i>
          </button>
        </div>
        <div className="masthead-actions">
          <span className="source-mode is-empty"><i /> <span>档案未接入</span></span>
        </div>
      </header>

      <DecisionSpine activeWorkspace={activeWorkspace} onSelectWorkspace={setActiveWorkspace} />

      <main className="stage" id="mainStage">
        <CaseViewRouter decisionCaseId={decisionCaseId} activeWorkspace={activeWorkspace} />
      </main>
    </div>
  );
}
