"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { healthQueryOptions } from "@/lib/api";

type ConnectivityState = "checking" | "online" | "offline";

const COPY: Record<ConnectivityState, { label: string; detail: string }> = {
  checking: {
    label: "正在连接后端",
    detail: "检查会话与 API 连通性…",
  },
  online: {
    label: "后端已连接",
    detail: "API 连通性正常；业务状态仍以后端 canonical 数据为准。",
  },
  offline: {
    label: "后端未连接",
    detail: "无法连接 API。这是连通性提示，不代表任何决策或运行状态。",
  },
};

/**
 * Session / connectivity bootstrap that wraps the Look V7 shell.
 *
 * It performs the single real end-to-end call available today (`GET /health`)
 * and surfaces an honest connectivity strip. It deliberately does NOT fabricate
 * auth, session, case or run state: those depend on backend routes that are not
 * yet in the generated contract. The strip only reports transport reachability
 * so a demo operator can tell a wiring failure apart from an empty workspace.
 *
 * This wrapper keeps `DecisionShell` free of data hooks so the QA-owned shell
 * tests can keep rendering it without a QueryClientProvider.
 */
export function SessionBootstrap({ children }: { children: ReactNode }) {
  const health = useQuery(healthQueryOptions());
  const [dismissed, setDismissed] = useState(false);
  const wasOffline = useRef(false);

  const state: ConnectivityState = health.isLoading
    ? "checking"
    : health.isError
      ? "offline"
      : "online";

  // Re-show the strip whenever connectivity drops so an operator is never left
  // looking at a stale "online" chip after the backend goes away.
  useEffect(() => {
    if (state === "offline") {
      wasOffline.current = true;
      setDismissed(false);
    } else if (state === "online" && wasOffline.current) {
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
                onClick={() => health.refetch()}
                disabled={health.isFetching}
              >
                重试连接
              </button>
            )}
            {state === "online" && (
              <button
                type="button"
                className="session-status-dismiss"
                onClick={() => setDismissed(true)}
                aria-label="收起连通性提示"
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
