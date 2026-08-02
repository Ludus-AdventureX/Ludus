"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type MouseEvent } from "react";

import { caseListRouteAvailable, fetchProjectDirectory, type ProjectDirectory } from "@/lib/shell/projects";
import { logoutAccount } from "@/lib/shell/session";

// Look V7 `#caseDrawer` as the production ProjectDrawer (Session B).
// Workspace entries come from the Task 3 read-only session API; case entries
// come from the canonical case-list route. Navigating away is a FULL page
// load (`window.location.assign`) instead of Next Link: the shell's drawer
// effect calls history.replaceState with the pre-navigation pathname, which
// would otherwise clobber the router push and leave the user on the current
// case (live finding: switching projects / "new project" silently did
// nothing).
//
// Focus trap and focus return follow the DecisionShell drawer pattern.

const drawerFocusableSelector = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])"
].join(",");

function getDrawerFocusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(drawerFocusableSelector)).filter(
    (element) => element.getAttribute("aria-hidden") !== "true"
  );
}

type ProjectDrawerProps = {
  open: boolean;
  /** null = the shell is on the empty state (no decision case). */
  decisionCaseId: string | null;
  onClose: () => void;
};

export function ProjectDrawer({ open, decisionCaseId, onClose }: ProjectDrawerProps) {
  const [directory, setDirectory] = useState<ProjectDirectory | null>(null);
  const [cases, setCases] = useState<Array<{ decisionCaseId: string; title: string; status: string }>>([]);
  const [loggingOut, setLoggingOut] = useState(false);
  const drawerDialog = useRef<HTMLElement>(null);

  const loadDirectory = useCallback(async () => {
    setDirectory(null);
    const dir = await fetchProjectDirectory();
    setDirectory(dir);
    // Load case list for the first workspace when available.
    if (caseListRouteAvailable && dir.status === "ready" && dir.workspaces.length > 0) {
      const ws = dir.workspaces[0]!;
      try {
        const res = await fetch(
          `/api/workspaces/${encodeURIComponent(ws.workspaceId)}/cases`,
          { credentials: "include" },
        );
        if (res.ok) {
          const body = (await res.json()) as { data?: { items?: Array<{ decisionCaseId: string; title: string; status: string }> } };
          setCases(body?.data?.items ?? []);
        }
      } catch { /* graceful */ }
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    void loadDirectory();
  }, [open, loadDirectory]);

  useEffect(() => {
    if (!open) return;
    const dialog = drawerDialog.current;
    if (!dialog) return;

    const focusTimer = window.setTimeout(() => {
      const [firstFocusable] = getDrawerFocusableElements(dialog);
      (firstFocusable ?? dialog).focus();
    }, 0);

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;

      const focusable = getDrawerFocusableElements(dialog);
      if (focusable.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      const focusIsOutside = active === null || !dialog.contains(active);

      if (event.shiftKey && (active === first || focusIsOutside)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || focusIsOutside)) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <aside className="drawer case-drawer is-open">
      <button className="drawer-scrim" type="button" aria-label="关闭项目抽屉" onClick={onClose} />
      <section
        ref={drawerDialog}
        id="project-drawer-dialog"
        className="drawer-sheet case-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="project-drawer-title"
        tabIndex={-1}
      >
        <header>
          <div>
            <span>DECISION PROJECTS</span>
            <h2 id="project-drawer-title">项目与工作区</h2>
            <p>列表来自已上线的只读会话接口；切换只改变当前展示，不会修改已保存的 Case 版本。</p>
          </div>
          <button className="drawer-close" type="button" onClick={onClose} aria-label="关闭项目抽屉">{"\u00d7"}</button>
        </header>

        <div className="case-list" aria-label="工作区与项目">
          {directory === null && <p className="draft-notice" role="status">正在读取工作区…</p>}

          {directory?.status === "unauthenticated" && (
            <p className="draft-notice" role="status">尚未登录：登录后这里会列出你的工作区与项目。</p>
          )}

          {directory?.status === "error" && (
            <>
              <p className="draft-notice" role="alert">工作区读取失败。</p>
              <button className="secondary-action" type="button" onClick={() => void loadDirectory()}>重试</button>
            </>
          )}

          {directory?.status === "ready" && directory.workspaces.length === 0 && (
            <p className="draft-notice" role="status">当前账号没有可用的工作区。</p>
          )}

          {directory?.status === "ready" &&
            directory.workspaces.map(({ workspaceId, workspaceName, role }) => (
              <div key={workspaceId} className="case-choice" data-workspace-entry={workspaceId}>
                <span className="case-glyph">W</span>
                <span>
                  <b>{workspaceName}</b>
                  <small>{`角色 ${role}`}</small>
                </span>
              </div>
            ))}

          {cases.length > 0 && (
            <>
              {cases.map((c) => {
                const href = `/cases/${encodeURIComponent(c.decisionCaseId)}?ws=${encodeURIComponent(directory?.status === "ready" ? directory.workspaces[0]?.workspaceId ?? "" : "")}`;
                return (
                  <Link
                    key={c.decisionCaseId}
                    className="case-choice"
                    href={href}
                    aria-current={decisionCaseId === c.decisionCaseId ? "page" : undefined}
                    onClick={(event: MouseEvent<HTMLAnchorElement>) => {
                      // Full-page navigation: the shell's drawer-close effect
                      // rewrites the URL from the stale pathname and would
                      // cancel a client-side router push (see module note).
                      event.preventDefault();
                      window.location.assign(href);
                    }}
                  >
                    <span className="case-glyph">Q</span>
                    <span>
                      <b>{c.title || c.decisionCaseId.slice(0, 8)}</b>
                      <small>{c.status}</small>
                    </span>
                  </Link>
                );
              })}
            </>
          )}

          <Link
            className="case-choice"
            href="/"
            aria-current={decisionCaseId ? undefined : "page"}
            onClick={(event: MouseEvent<HTMLAnchorElement>) => {
              // Full-page navigation for the same reason as the case links.
              event.preventDefault();
              window.location.assign("/");
            }}
          >
            <span className="case-glyph empty">{"\uff0b"}</span>
            <span>
              <b>新建项目</b>
              <small>打开新建决策入口</small>
            </span>
          </Link>
        </div>

        <footer>
          <button className="secondary-action" type="button" onClick={onClose}>留在当前项目</button>
          {directory?.status === "ready" && (
            <button
              className="text-action"
              type="button"
              disabled={loggingOut}
              onClick={async () => {
                setLoggingOut(true);
                try {
                  await logoutAccount();
                  window.location.assign("/enter");
                } catch {
                  setLoggingOut(false);
                }
              }}
            >
              {loggingOut ? "退出中…" : "退出登录"}
            </button>
          )}
        </footer>
      </section>
    </aside>
  );
}
