"use client";

import Image from "next/image";
import { MouseEvent, useCallback, useEffect, useRef, useState } from "react";

import { CaseViewRouter } from "@/components/shell/CaseViewRouter";
import { DecisionSpine } from "@/components/shell/DecisionSpine";
import { ProjectDrawer } from "@/components/shell/ProjectDrawer";
import { defaultWorkspaceId, isCaseWorkspaceId, type CaseWorkspaceId } from "@/lib/shell/workspaces";

// Five-workspace case shell (Task 11 Phase 0 Session A + B).
// Session B fills the reserved project-drawer slot with the real
// ProjectDrawer (Task 3 read-only session API); analysis/case data is
// still not fabricated anywhere in the shell.

type CaseShellProps = {
  /** null = empty state (no decision case yet). */
  decisionCaseId: string | null;
  /** Tenant workspace anchor (READ-01 flip threading; null = reads stay gap). */
  tenantWorkspaceId?: string | null;
};

export function CaseShell({ decisionCaseId, tenantWorkspaceId = null }: CaseShellProps) {
  const [activeWorkspace, setActiveWorkspace] = useState<CaseWorkspaceId>(defaultWorkspaceId);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [ready, setReady] = useState(false);
  const projectTrigger = useRef<HTMLButtonElement>(null);
  const drawerTrigger = useRef<HTMLButtonElement | null>(null);
  const isEmpty = !decisionCaseId;

  useEffect(() => {
    if (!isEmpty) return;
    document.body.classList.add("empty-case");
    return () => document.body.classList.remove("empty-case");
  }, [isEmpty]);

  // Restore workspace and drawer state from the URL so a refresh keeps
  // the user's place (view=<workspace>, panel=projects).
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const requestedView = params.get("view");
    if (isCaseWorkspaceId(requestedView)) setActiveWorkspace(requestedView);
    if (params.get("panel") === "projects") setDrawerOpen(true);
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    const params = new URLSearchParams(window.location.search);
    params.set("view", activeWorkspace);
    if (drawerOpen) params.set("panel", "projects");
    else params.delete("panel");
    window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
  }, [activeWorkspace, drawerOpen, ready]);

  const openDrawer = useCallback((event: MouseEvent<HTMLButtonElement>) => {
    drawerTrigger.current = event.currentTarget;
    setDrawerOpen(true);
  }, []);

  const closeDrawer = useCallback(() => {
    setDrawerOpen(false);
    // Focus returns to the trigger that opened the drawer (or the masthead
    // trigger after a URL-restored open) per the DecisionShell pattern.
    window.setTimeout(() => {
      const trigger = drawerTrigger.current;
      (trigger?.isConnected ? trigger : projectTrigger.current)?.focus();
      drawerTrigger.current = null;
    }, 0);
  }, []);

  return (
    <div className="app-shell">
      <header className="masthead" inert={drawerOpen}>
        <div className="brand-lockup" aria-label="Ludus">
          <Image className="brand-logo" src="/ludus-logo.svg" alt="Ludus" width={1478} height={406} priority />
        </div>
        <div className="case-title">
          <span>当前议题</span>
          <button
            ref={projectTrigger}
            type="button"
            data-phase-slot="project-drawer"
            aria-haspopup="dialog"
            aria-controls="project-drawer-dialog"
            aria-expanded={drawerOpen}
            onClick={openDrawer}
          >
            <span>{decisionCaseId ? `决策项目 ${decisionCaseId}` : "尚未创建决策项目"}</span> <i aria-hidden="true">{"\u2304"}</i>
          </button>
        </div>
        <div className="masthead-actions">
          <span className="source-mode is-empty"><i /> <span>档案未接入</span></span>
          <button
            className="mobile-case-trigger"
            type="button"
            aria-label="打开项目抽屉"
            aria-haspopup="dialog"
            aria-controls="project-drawer-dialog"
            aria-expanded={drawerOpen}
            onClick={openDrawer}
          >
            项
          </button>
        </div>
      </header>

      <DecisionSpine activeWorkspace={activeWorkspace} onSelectWorkspace={setActiveWorkspace} inert={drawerOpen} />

      <main className="stage" id="mainStage" inert={drawerOpen}>
        <CaseViewRouter
          decisionCaseId={decisionCaseId}
          tenantWorkspaceId={tenantWorkspaceId}
          activeWorkspace={activeWorkspace}
        />
      </main>

      <ProjectDrawer open={drawerOpen} decisionCaseId={decisionCaseId} onClose={closeDrawer} />
    </div>
  );
}
