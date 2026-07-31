"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { logoutAccount, readAccountSession, type AccountSession } from "@/lib/shell/session";
import { ConnectorSettings } from "@/components/shell/ConnectorSettings";

// Account entry (bottom-right): session-aware replacement for the static
// "受邀进入 / 登录" link. Unauthenticated -> the invite/login link; logged in
// -> an account chip opening a small menu (email, workspace, logout, and a
// placeholder for connector/API settings). Look V7: square corners, hairline
// borders, no gradients. Behavior referenced from open-webui's account menu;
// no code copied (license boundary).

export function AccountEntry() {
  const [session, setSession] = useState<AccountSession | null>(null);
  const [open, setOpen] = useState(false);
  const [showConnectors, setShowConnectors] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    void readAccountSession()
      .then((s) => { if (!cancelled) setSession(s); })
      .catch(() => { if (!cancelled) setSession({ authenticated: false, email: null, workspaces: [] }); });
    return () => { cancelled = true; };
  }, []);

  // Close on outside click.
  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  // Loading: render nothing to avoid a flash of the wrong state.
  if (session === null) return null;

  if (!session.authenticated) {
    return (
      <nav aria-label="Alpha entry" className="account-entry">
        <Link href="/enter" className="account-entry-login">
          受邀进入 / 登录
        </Link>
      </nav>
    );
  }

  const emailPrefix = session.email?.split("@")[0] ?? "账号";
  const workspace = session.workspaces[0];

  return (
    <nav aria-label="账号" className="account-entry" ref={menuRef}>
      {open && (
        <div className="account-menu" role="menu" aria-label="账号菜单">
          <div className="account-menu-head">
            <b>{session.email}</b>
            {workspace && <small>{workspace.workspaceName} · {workspace.role}</small>}
          </div>
          <button type="button" role="menuitem" onClick={() => { setOpen(false); setShowConnectors(true); }}>
            连接器设置
          </button>
          <button
            type="button"
            role="menuitem"
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
        </div>
      )}
      <button
        type="button"
        className="account-entry-chip"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="account-glyph">{emailPrefix.slice(0, 1).toUpperCase()}</span>
        <span>{emailPrefix}</span>
      </button>
      {showConnectors && workspace && (
        <ConnectorSettings
          workspaceId={workspace.workspaceId}
          onClose={() => setShowConnectors(false)}
        />
      )}
    </nav>
  );
}
