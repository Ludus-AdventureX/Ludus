"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { caseListRouteAvailable, fetchProjectDirectory, type ProjectDirectory } from "@/lib/shell/projects";

// Look V7 `#caseDrawer` as the production ProjectDrawer (Session B).
// Workspace entries come from the Task 3 read-only session API; the
// decision-case list route does not exist yet, so the case section renders
// an honest gap note instead of fabricated projects. Focus trap and focus
// return follow the DecisionShell drawer pattern.

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
  // null = request in flight (initial load or retry).
  const [directory, setDirectory] = useState<ProjectDirectory | null>(null);
  const drawerDialog = useRef<HTMLElement>(null);

  const loadDirectory = useCallback(async () => {
    setDirectory(null);
    setDirectory(await fetchProjectDirectory());
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
            <p className="draft-notice" role="status">尚未登录：登录后这里会列出你的真实工作区；不显示伪造列表。</p>
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
                  <em>{caseListRouteAvailable ? "" : "该工作区的 Case 列表等待只读路由上线。"}</em>
                </span>
              </div>
            ))}

          <Link
            className="case-choice"
            href="/cases/new"
            aria-current={decisionCaseId ? undefined : "page"}
            onClick={onClose}
          >
            <span className="case-glyph empty">{"\uff0b"}</span>
            <span>
              <b>空工作台</b>
              <small>尚未创建 Case</small>
              <em>打开新建决策入口；创建前不会生成任何档案。</em>
            </span>
          </Link>
        </div>

        <section className="case-drawer-note">
          <span>接口缺口</span>
          <p>Case 列表只读路由尚未上线（Task 3 目前只提供会话与工作区摘要）；这里不显示伪造项目，路由接入后自动列出真实 Case。</p>
        </section>

        <footer>
          <button className="secondary-action" type="button" onClick={onClose}>留在当前项目</button>
        </footer>
      </section>
    </aside>
  );
}
