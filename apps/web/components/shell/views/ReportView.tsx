"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { EvidenceDrawerTrigger } from "@/components/quality/EvidenceDrawerTrigger";
import {
  CaseActionError,
  getCaseReport,
  listCaseReports,
  type ReportListItem,
} from "@/lib/shell/caseActions";
import { downloadReportMarkdown, parseEvidenceId } from "@/lib/shell/reportExport";

// Look V7 `#view-report` — now a LIVE projection of the case's canonical
// ReportArtifacts (B1). The layout consumes the prototype's report-spread
// contract verbatim (recommendation-page + dissent-page, condition-list,
// margin labels); no JSON dumps, no raw UUIDs, no fabricated verdicts.
// Honest states: loading, empty (no gated report yet), error, and a draft
// badge when the quality gate did not pass.

export type ReportViewProps = {
  workspaceId?: string | null;
  decisionCaseId?: string;
};

type ReportDoc = {
  executiveBrief?: {
    decision?: string;
    whyNow?: string;
    conditions?: string[];
    exitCriteria?: string[];
    reviewDate?: string;
  };
  recommendation?: {
    summary?: string;
    conditions?: string[];
    thresholds?: Array<{ metric?: string; operator?: string; value?: string; actionIfMissed?: string }>;
    risks?: string[];
    nextActions?: Array<{ text?: string; owner?: string; dueAt?: string }>;
    reviewDate?: string;
  };
  evidenceReview?: { evidenceIds?: string[]; reconciliationFindings?: string[] };
  counterArguments?: Array<{ text?: string; severity?: string; mitigation?: string }>;
  residualUncertainty?: Array<{ question?: string; priority?: string }>;
  qualityGate?: { passed?: boolean; warnings?: string[]; errors?: string[] };
  originModes?: string[];
};

type ViewState =
  | { phase: "gap" }
  | { phase: "loading" }
  | { phase: "empty" }
  | { phase: "error"; message: string }
  | { phase: "ready"; items: ReportListItem[]; active: number; doc: ReportDoc };

function reportId(item: ReportListItem): string {
  return String((item as { id?: string }).id ?? item.reportId ?? "");
}

/** First clause of the decision as the editorial H1 (look keeps H1 short). */
function headlineOf(decision: string): string {
  const clause = decision.split(/[。；;]/)[0]?.trim() ?? "";
  return clause.length > 46 ? `${clause.slice(0, 45)}…` : clause || "条件化建议已生成";
}

/** Split "标题：说明" / "标题，说明" conditions into the list's b/p pair. */
function splitCondition(text: string): { title: string; body: string } {
  const match = text.match(/^(.{2,18}?)[：:，,](.+)$/);
  if (match?.[1] && match[2]) return { title: match[1], body: match[2] };
  return { title: text, body: "" };
}

function shortDate(iso: string | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export function ReportView({ workspaceId = null, decisionCaseId }: ReportViewProps = {}) {
  const [state, setState] = useState<ViewState>(
    workspaceId && decisionCaseId ? { phase: "loading" } : { phase: "gap" },
  );
  const [showEvidence, setShowEvidence] = useState(false);
  const [rawDetail, setRawDetail] = useState<Record<string, unknown> | null>(null);

  const openReport = useCallback(
    async (items: ReportListItem[], index: number) => {
      if (!workspaceId || !decisionCaseId) return;
      const id = reportId(items[index]!);
      try {
        const detail = await getCaseReport(workspaceId, decisionCaseId, id);
        const doc = ((detail.structuredContent ?? detail.content ?? {}) as ReportDoc) || {};
        setRawDetail(detail);
        setState({ phase: "ready", items, active: index, doc });
        setShowEvidence(false);
      } catch (err) {
        setState({
          phase: "error",
          message: err instanceof CaseActionError ? err.message : "报告详情读取失败。",
        });
      }
    },
    [workspaceId, decisionCaseId],
  );

  useEffect(() => {
    if (!workspaceId || !decisionCaseId) return;
    let cancelled = false;
    (async () => {
      try {
        const items = await listCaseReports(workspaceId, decisionCaseId);
        if (cancelled) return;
        if (items.length === 0) {
          setState({ phase: "empty" });
          return;
        }
        await openReport(items, 0);
      } catch (err) {
        if (!cancelled)
          setState({
            phase: "error",
            message: err instanceof CaseActionError ? err.message : "报告读取失败。",
          });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [workspaceId, decisionCaseId, openReport]);

  const ready = state.phase === "ready" ? state : null;
  const doc = ready?.doc ?? {};
  const brief = doc.executiveBrief ?? {};
  const rec = doc.recommendation ?? {};
  const decision = brief.decision || rec.summary || "";
  const conditions = (brief.conditions?.length ? brief.conditions : rec.conditions) ?? [];
  const actions = rec.nextActions ?? [];
  const thresholds = rec.thresholds ?? [];
  const counters = doc.counterArguments ?? [];
  const unknowns = doc.residualUncertainty ?? [];
  const evidenceIds = doc.evidenceReview?.evidenceIds ?? [];
  const gatePassed = doc.qualityGate?.passed === true;
  const reviewDate = brief.reviewDate || rec.reviewDate || "";
  const originModes = doc.originModes ?? [];

  const coordinate = ready ? `J-${String(ready.items.length - ready.active).padStart(2, "0")}` : "J-—";
  const coordinateNote = ready
    ? gatePassed
      ? "条件化判断"
      : "草稿 · 质量门未通过"
    : state.phase === "loading"
      ? "正在读取报告…"
      : "尚无条件化判断";

  const headline = useMemo(
    () => (ready && decision ? headlineOf(decision) : "报告尚未生成"),
    [ready, decision],
  );

  return (
    <section className="view is-active" id="view-report" data-view-panel="report" aria-labelledby="report-view-title">
      <header className="view-intro report-intro">
        <div className="intro-coordinate"><span>{coordinate}</span><i /><small>{coordinateNote}</small></div>
        <div className="intro-grid">
          <div>
            <p className="eyebrow">不是“选哪一个”，而是“在什么条件下先做什么”</p>
            <h1 id="report-view-title">{headline}</h1>
            {ready && brief.whyNow && <p className="intro-copy">{brief.whyNow}</p>}
          </div>
          <div className="intro-actions">
            {ready && rawDetail && (
              <button
                type="button"
                className="text-action"
                onClick={() => downloadReportMarkdown(rawDetail)}
              >
                导出一页简报 <span>↓</span>
              </button>
            )}
          </div>
        </div>
      </header>

      {ready && ready.items.length > 1 && (
        <nav className="report-switcher" aria-label="历史报告">
          {ready.items.map((item, index) => (
            <button
              key={reportId(item)}
              type="button"
              className="text-action"
              aria-pressed={index === ready.active}
              disabled={index === ready.active}
              onClick={() => void openReport(ready.items, index)}
            >
              分析 {ready.items.length - index}
              {item.createdAt ? ` · ${shortDate(String(item.createdAt))}` : ""}
            </button>
          ))}
        </nav>
      )}

      <article className="report-spread">
        <section className="recommendation-page" aria-label="当前建议">
          <div className="recommendation-rule">
            <span>当前建议</span>
            <i />
            <b>
              {state.phase === "loading" && "正在读取…"}
              {state.phase === "gap" && "缺少工作区锚点"}
              {state.phase === "empty" && "等待分析完成"}
              {state.phase === "error" && "读取失败"}
              {ready && (gatePassed ? "有条件成立" : "草稿 · 未通过质量门")}
            </b>
          </div>

          {state.phase === "empty" && (
            <p className="lead-paragraph">
              本案件还没有通过质量门的报告；在 Q 问题页发起一次聚焦研究或完整战略分析后，
              条件化建议会出现在这里。系统不展示示例结论。
            </p>
          )}
          {state.phase === "error" && <p className="lead-paragraph">{state.message}</p>}
          {state.phase === "gap" && (
            <p className="lead-paragraph">缺少工作区锚点（?ws=），请从项目入口重新打开本案件。</p>
          )}
          {ready && <p className="lead-paragraph">{decision}</p>}

          {ready && conditions.length > 0 && (
            <div className="condition-list">
              {conditions.slice(0, 4).map((text, index) => {
                const { title, body } = splitCondition(text);
                return (
                  <article key={index}>
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <div>
                      <b>{title}</b>
                      {body && <p>{body}</p>}
                    </div>
                  </article>
                );
              })}
            </div>
          )}

          {ready && actions.length > 0 && (
            <>
              <div className="recommendation-rule">
                <span>下一步行动</span>
                <i />
                <b>{reviewDate ? `复盘日 ${reviewDate} 前` : "按建议节奏"}</b>
              </div>
              <div className="condition-list">
                {actions.slice(0, 4).map((action, index) => (
                  <article key={index}>
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <div>
                      <b>{action.owner || "负责人"}</b>
                      <p>{action.text}{action.dueAt ? `（${action.dueAt} 前）` : ""}</p>
                    </div>
                  </article>
                ))}
              </div>
            </>
          )}

          <footer className="report-signature">
            <span>
              系统综合
              {originModes.length > 0 && ` · 来源 ${originModes.join(" / ")}`}
            </span>
            <i />
            <span>{ready && gatePassed ? "等待人类采纳" : "等待分析完成"}</span>
          </footer>
        </section>

        <aside className="dissent-page">
          <span className="margin-label">最强反对意见</span>
          {ready && counters.length > 0 ? (
            <>
              <blockquote>{counters[0]?.text}</blockquote>
              <div className="dissent-meta">
                <span>Critic{counters[0]?.severity ? ` · ${counters[0].severity}` : ""}</span>
                <b>
                  {counters[0]?.mitigation
                    ? `缓解：${counters[0].mitigation}`
                    : counters[1]?.text ?? "反方未给出缓解路径。"}
                </b>
              </div>
            </>
          ) : (
            <p>反方审查与建议翻转条件将随真实报告一同呈现。</p>
          )}

          {ready && (thresholds.length > 0 || unknowns.length > 0) && (
            <>
              <hr />
              <span className="margin-label">
                {thresholds.length > 0 ? "建议翻转条件" : "剩余未知"}
              </span>
              <ul>
                {thresholds.slice(0, 3).map((item, index) => (
                  <li key={`t-${index}`}>
                    <b>{String(item.value ?? "—")}</b>
                    <span>{item.metric ?? ""}</span>
                  </li>
                ))}
                {thresholds.length === 0 &&
                  unknowns.slice(0, 3).map((item, index) => (
                    <li key={`u-${index}`}>
                      <b>{item.priority === "high" ? "高" : "中"}</b>
                      <span>{item.question}</span>
                    </li>
                  ))}
              </ul>
            </>
          )}

          {ready && evidenceIds.length > 0 && (
            <>
              <button
                type="button"
                className="text-action"
                aria-expanded={showEvidence}
                onClick={() => setShowEvidence((v) => !v)}
              >
                查看 {evidenceIds.length} 条关键证据 <span>{showEvidence ? "↑" : "↗"}</span>
              </button>
              {showEvidence && (
                <div className="report-evidence-links" data-report-evidence-links>
                  <ul>
                    {evidenceIds.map((raw) => {
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
            </>
          )}

          <hr />
          <EvidenceDrawerTrigger
            {...(workspaceId ? { workspaceId } : {})}
            {...(decisionCaseId ? { decisionCaseId } : {})}
          />
        </aside>
      </article>
    </section>
  );
}
