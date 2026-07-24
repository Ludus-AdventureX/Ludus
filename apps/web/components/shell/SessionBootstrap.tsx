"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { sessionProbeQueryOptions } from "@/lib/api";

type SessionState = "checking" | "authenticated" | "unauthenticated" | "offline";

const COPY: Record<SessionState, { label: string; detail: string }> = {
  checking: {
    label: "正在检查会话",
    detail: "读取后端 canonical 会话状态…",
  },
  authenticated: {
    label: "会话已建立",
    detail: "用户、会话与工作区成员身份均来自后端 canonical 数据。",
  },
  unauthenticated: {
    label: "未登录",
    detail: "后端可达；当前没有活动会话。登录入口将在认证切片启用后提供。",
  },
  offline: {
    label: "后端未连接",
    detail: "无法连接 API。这是连通性提示，不代表任何决策或运行状态。",
  },
};

/**
 * Session bootstrap that wraps the Look V7 shell.
 *
 * It probes the canonical `GET /api/auth/session` route: 200 means an active
 * session, 401 means reachable-but-signed-out, and a transport failure means
 * offline. The strip reports exactly that and never fabricates auth, case or
 * run state; the shell below stays honest-empty until real business data
 * arrives from canonical routes.
 *
 * This wrapper keeps `DecisionShell` free of data hooks so the QA-owned shell
 * tests can keep rendering it without a QueryClientProvider.
 */
export function SessionBootstrap({ children }: { children: ReactNode }) {
  const probe = useQuery(sessionProbeQueryOptions());
  const [dismissed, setDismissed] = useState(false);
  const wasOffline = useRef(false);

  const state: SessionState = probe.isLoading
    ? "checking"
    : probe.isError
      ? "offline"
      : probe.data?.kind === "authenticated"
        ? "authenticated"
        : "unauthenticated";

  // Re-show the strip whenever connectivity drops so an operator is never left
  // looking at a stale status chip after the backend goes away.
  useEffect(() => {
    if (state === "offline") {
      wasOffline.current = true;
      setDismissed(false);
    } else if (state !== "checking" && wasOffline.current) {
      wasOffline.current = false;
    }
  }, [state]);

  const copy = COPY[state];
  const showStrip = !dismissed || state === "offline";

  return (
    <>
      {showStrip && (
        <div
          className={`session-status session-status-${state}`}
          role="status"
          aria-live="polite"
        >
          <span className="session-status-dot" aria-hidden="true" />
          <span className="session-status-text">
            <b>{copy.label}</b>
            <small>{copy.detail}</small>
          </span>
          <span className="session-status-actions">
            {state === "offline" && (
              <button
                type="button"
                className="session-status-retry"
                onClick={() => probe.refetch()}
                disabled={probe.isFetching}
              >
                重试连接
              </button>
            )}
            {(state === "authenticated" || state === "unauthenticated") && (
              <button
                type="button"
                className="session-status-dismiss"
                onClick={() => setDismissed(true)}
                aria-label="收起会话状态提示"
              >
                {"\u00d7"}
              </button>
            )}
          </span>
        </div>
      )}
      {children}
    </>
  );
}
