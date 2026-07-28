"use client";

import { useCallback, useEffect, useState } from "react";

import {
  CaseActionError,
  getCaseReport,
  listCaseReports,
  type ReportListItem,
} from "@/lib/shell/caseActions";
import { downloadReportMarkdown, parseEvidenceId } from "@/lib/shell/reportExport";

// Real report reads for the report workspace: lists the case's canonical
// ReportArtifacts and loads one on demand. Honest empty state when no report
// has passed the quality gate yet; nothing is fabricated. Evidence ids carry
// REAL retrieval URLs, so they render as clickable links (R1-3).

type PanelState =
  | { phase: "loading" }
  | { phase: "empty" }
  | { phase: "ready"; items: ReportListItem[] }
  | { phase: "error"; message: string };

export type ReportListPanelProps = {
  workspaceId?: string | null;
  decisionCaseId?: string;
};

function itemId(item: ReportListItem): string {
  return String((item as { id?: string; reportId?: string }).id ?? item.reportId ?? "");
}

function evidenceIdsOf(detail: Record<string, unknown> | null): string[] {
  const content = (detail?.structuredContent ?? null) as Record<string, unknown> | null;
  const review = (content?.evidenceReview ?? null) as Record<string, unknown> | null;
  const ids = review?.evidenceIds;
  return Array.isArray(ids) ? ids.map((v) => String(v)) : [];
}

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
            <li key={itemId(item)}>
              <button type="button" className="secondary-action" onClick={() => void open(itemId(item))}>
                {String(item.title ?? itemId(item))}（{String(item.status)}）
              </button>
              {detailId === itemId(item) && (
                <div className="report-detail-block">
                  {detail && evidenceIdsOf(detail).length > 0 && (
                    <div className="report-evidence-links" data-report-evidence-links>
                      <h4>证据清单（真实来源，可点击核查）</h4>
                      <ul>
                        {evidenceIdsOf(detail).map((raw) => {
                          const parts = parseEvidenceId(raw);
                          return (
                            <li key={parts.label} data-evidence-tier={parts.tier ?? "unknown"}>
                              <span className="evidence-tier-badge">{parts.tier ?? "?"}</span>
                              {parts.url ? (
                                <a href={parts.url} target="_blank" rel="noopener noreferrer">
                                  {parts.url}
                                </a>
                              ) : (
                                <span>{parts.label}</span>
                              )}
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  )}
                  {detail && !("error" in (detail ?? {})) && (
                    <button
                      type="button"
                      className="secondary-action small"
                      onClick={() => downloadReportMarkdown(detail)}
                    >
                      <span>导出 Markdown（含内容指纹）</span>
                    </button>
                  )}
                  <pre className="report-detail">
                    {detail ? JSON.stringify(detail, null, 2).slice(0, 4000) : "读取中…"}
                  </pre>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
