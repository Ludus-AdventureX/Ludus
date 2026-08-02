"use client";

import Image from "next/image";
import { MouseEvent, useCallback, useEffect, useRef, useState } from "react";

import { CaseViewRouter } from "@/components/shell/CaseViewRouter";
import { AccountEntry } from "@/components/shell/AccountEntry";
import { DecisionSpine } from "@/components/shell/DecisionSpine";
import { InvitePanel } from "@/components/shell/InvitePanel";
import { ProjectDrawer } from "@/components/shell/ProjectDrawer";
import { defaultWorkspaceId, isCaseWorkspaceId, type CaseWorkspaceId } from "@/lib/shell/workspaces";
import { fetchCaseDetail } from "@/lib/shell/caseData";

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
  // Recover workspace from localStorage when the URL lost it (e.g. session
  // refresh, browser back). The server-supplied prop takes precedence.
  const effectiveWorkspaceId = tenantWorkspaceId ?? (
    typeof window !== "undefined"
      ? (new URLSearchParams(window.location.search).get("ws") || localStorage.getItem("ludus-ws"))
      : null
  );
  const [activeWorkspace, setActiveWorkspace] = useState<CaseWorkspaceId>(defaultWorkspaceId);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [ready, setReady] = useState(false);
  const [caseMeta, setCaseMeta] = useState<{ caseVersion: number; confirmedDossierVersion: number } | null>(null);
  const [caseMetaState, setCaseMetaState] = useState<"loading" | "ready" | "error">("loading");
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

  // Real dossier/case version for the masthead source-mode marker. The marker
  // used to be a static "档案未接入" string from the static-prototype era; the
  // dossier surface is live now, so the marker reports the actual confirmed
  // dossier version (honest loading/error states, never fabricated numbers).
  useEffect(() => {
    if (!decisionCaseId || !effectiveWorkspaceId) return;
    let cancelled = false;
    setCaseMetaState("loading");
    (async () => {
      try {
        const detail = await fetchCaseDetail(effectiveWorkspaceId, decisionCaseId);
        if (cancelled) return;
        setCaseMeta({
          caseVersion: detail.caseVersion,
          confirmedDossierVersion: detail.confirmedDossierVersion,
        });
        setCaseMetaState("ready");
      } catch {
        if (!cancelled) setCaseMetaState("error");
      }
    })();
    return () => { cancelled = true; };
  }, [decisionCaseId, effectiveWorkspaceId]);

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
          <InvitePanel workspaceId={effectiveWorkspaceId} />
          <span className="source-mode is-empty"><i /> <span>
            {caseMetaState === "ready" && caseMeta
              ? `CaseVersion v${caseMeta.caseVersion} · Dossier v${caseMeta.confirmedDossierVersion}`
              : caseMetaState === "error"
                ? "档案读取失败"
                : "档案读取中…"}
          </span></span>
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
          tenantWorkspaceId={effectiveWorkspaceId}
          activeWorkspace={activeWorkspace}
        />
      </main>

      <ProjectDrawer open={drawerOpen} decisionCaseId={decisionCaseId} onClose={closeDrawer} />
      <AccountEntry />
    </div>
  );
}
