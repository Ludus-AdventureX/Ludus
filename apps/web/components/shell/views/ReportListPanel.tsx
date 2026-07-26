"use client";

import { useCallback, useEffect, useState } from "react";

import {
  CaseActionError,
  getCaseReport,
  listCaseReports,
  type ReportListItem,
} from "@/lib/shell/caseActions";

// Real report reads for the report workspace: lists the case's canonical
// ReportArtifacts and loads one on demand. Honest empty state when no report
// has passed the quality gate yet; nothing is fabricated.

type PanelState =
  | { phase: "loading" }
  | { phase: "empty" }
  | { phase: "ready"; items: ReportListItem[] }
  | { phase: "error"; message: string };

export type ReportListPanelProps = {
  workspaceId?: string | null;
  decisionCaseId?: string;
};

export function ReportListPanel({ workspaceId = null, decisionCaseId }: ReportListPanelProps) {
  const [state, setState] = useState<PanelState>({ phase: "loading" });
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);

  useEffect(() => {
    if (!workspaceId || !decisionCaseId) return;
    let cancelled = false;
    (async () => {
      try {
        const items = await listCaseReports(workspaceId, decisionCaseId);
        if (cancelled) return;
        setState(items.length === 0 ? { phase: "empty" } : { phase: "ready", items });
      } catch (err) {
        if (cancelled) return;
        setState({
          phase: "error",
          message: err instanceof CaseActionError ? err.message : "报告读取失败。",
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [decisionCaseId, workspaceId]);

  const open = useCallback(
    async (reportId: string) => {
      if (!workspaceId || !decisionCaseId) return;
      setDetailId(reportId);
      setDetail(null);
      try {
        setDetail(await getCaseReport(workspaceId, decisionCaseId, reportId));
      } catch {
        setDetail({ error: "报告详情读取失败。" });
      }
    },
    [decisionCaseId, workspaceId],
  );

  if (!workspaceId || !decisionCaseId) {
    return (
      <p className="phase-slot-note" data-report-panel="gap">
        缺少工作区锚点（?ws=），报告读取暂不可用。
      </p>
    );
  }

  return (
    <div className="report-list-panel" data-report-panel="ready" role="status" aria-live="polite">
      {state.phase === "loading" && <p>正在读取本案件的报告…</p>}
      {state.phase === "empty" && (
        <p>本案件还没有通过质量门的报告；完成一次深度分析后，报告会出现在这里。</p>
      )}
      {state.phase === "error" && <p>{state.message}</p>}
      {state.phase === "ready" && (
        <ul className="report-items" aria-label="报告列表">
          {state.items.map((item) => (
            <li key={item.reportId}>
              <button type="button" className="secondary-action" onClick={() => void open(item.reportId)}>
                {String(item.title ?? item.reportId)}（{String(item.status)}）
              </button>
              {detailId === item.reportId && (
                <pre className="report-detail">
                  {detail ? JSON.stringify(detail, null, 2).slice(0, 4000) : "读取中…"}
                </pre>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
