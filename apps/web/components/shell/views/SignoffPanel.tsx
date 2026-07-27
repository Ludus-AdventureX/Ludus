"use client";

import { useCallback, useEffect, useState } from "react";

import {
  SignoffError,
  buildSignoffPayload,
  createSignoffRequest,
  getLatestReadyReport,
  listCaseDecisions,
  signSignoffRequest,
  type DecisionRecordView,
  type ReadyReport,
} from "@/lib/shell/signoff";

// Human signoff line for the decision workspace: only a READY report unlocks
// the form ("no qualifying run, no report, no decision"), the payload's
// source projection mirrors that report verbatim, and the DecisionRecord is
// append-only - nothing here fabricates a decision.

type PanelPhase = "loading" | "no-report" | "form" | "signing" | "signed" | "error";

export type SignoffPanelProps = {
  workspaceId?: string | null;
  decisionCaseId?: string;
  /** Called after a DecisionRecord is successfully signed (provenance reload). */
  onSigned?: () => void;
};

function defaultReviewDate(): string {
  const d = new Date();
  d.setDate(d.getDate() + 90);
  return d.toISOString().slice(0, 10);
}

export function SignoffPanel({ workspaceId = null, decisionCaseId, onSigned }: SignoffPanelProps) {
  const [phase, setPhase] = useState<PanelPhase>("loading");
  const [report, setReport] = useState<ReadyReport | null>(null);
  const [decisions, setDecisions] = useState<DecisionRecordView[]>([]);
  const [error, setError] = useState("");

  const [selectedOptionId, setSelectedOptionId] = useState("");
  const [decisionDraft, setDecisionDraft] = useState("");
  const [conditionsText, setConditionsText] = useState("");
  const [exitText, setExitText] = useState("");
  const [reviewDate, setReviewDate] = useState(defaultReviewDate());
  const [statement, setStatement] = useState("");

  useEffect(() => {
    if (!workspaceId || !decisionCaseId) return;
    let cancelled = false;
    (async () => {
      try {
        const [ready, existing] = await Promise.all([
          getLatestReadyReport(workspaceId, decisionCaseId),
          listCaseDecisions(workspaceId, decisionCaseId),
        ]);
        if (cancelled) return;
        setDecisions(existing);
        if (existing.length > 0) {
          setPhase("signed");
          return;
        }
        if (!ready) {
          setPhase("no-report");
          return;
        }
        setReport(ready);
        const outcome = (ready.structuredContent.recommendation as { outcome?: { optionId?: string } } | undefined)
          ?.outcome;
        if (outcome?.optionId) setSelectedOptionId(outcome.optionId);
        setPhase("form");
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof SignoffError ? err.message : "签署面板初始化失败。");
        setPhase("error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [decisionCaseId, workspaceId]);

  const sign = useCallback(async () => {
    if (!workspaceId || !decisionCaseId || !report || phase === "signing") return;
    if (!selectedOptionId.trim() || !decisionDraft.trim() || !statement.trim()) {
      setError("选项、决定草案与签名声明都必须由你亲自填写。");
      return;
    }
    setPhase("signing");
    setError("");
    try {
      const payload = buildSignoffPayload(report, {
        selectedOptionId: selectedOptionId.trim(),
        decisionDraft: decisionDraft.trim(),
        conditions: conditionsText.split("\n").map((s) => s.trim()).filter(Boolean),
        exitCriteria: exitText.split("\n").map((s) => s.trim()).filter(Boolean),
        reviewDate,
      });
      const created = await createSignoffRequest(workspaceId, decisionCaseId, payload);
      const record = await signSignoffRequest(workspaceId, created, statement.trim());
      setDecisions([record]);
      setPhase("signed");
      onSigned?.();
    } catch (err) {
      setError(err instanceof SignoffError ? err.message : "签署失败，请重试。");
      setPhase("form");
    }
  }, [conditionsText, decisionCaseId, decisionDraft, exitText, phase, report, reviewDate, selectedOptionId, statement, workspaceId]);

  if (!workspaceId || !decisionCaseId) {
    return (
      <p className="phase-slot-note" data-signoff-panel="gap">
        缺少工作区锚点（?ws=），签署暂不可用。
      </p>
    );
  }

  return (
    <div className="signoff-panel" data-signoff-panel={phase}>
      <div role="status" aria-live="polite">
        {phase === "loading" && <p>正在检查可签署的报告…</p>}
        {phase === "no-report" && <p>签署需要一份通过质量门的报告；先完成一次深度分析。</p>}
        {phase === "error" && <p>{error}</p>}
        {phase === "signed" && (
          <p data-signoff-decision>
            决定已签署并进入 append-only 档案（DecisionRecord{" "}
            {String((decisions[0] as { id?: string } | undefined)?.id ?? "").slice(0, 8)}）。
          </p>
        )}
      </div>

      {(phase === "form" || phase === "signing") && report && (
        <form
          className="signoff-form"
          onSubmit={(event) => {
            event.preventDefault();
            void sign();
          }}
        >
          <p className="signoff-source">
            签署来源：报告 {report.id.slice(0, 8)} / Run {report.analysisRunId.slice(0, 8)}（来源投影随报告冻结）
          </p>
          <label htmlFor="signoffOption">选定选项 ID</label>
          <input
            id="signoffOption"
            value={selectedOptionId}
            onChange={(e) => setSelectedOptionId(e.target.value)}
          />
          <label htmlFor="signoffDraft">决定草案（一句带后果的承诺）</label>
          <textarea
            id="signoffDraft"
            rows={2}
            value={decisionDraft}
            onChange={(e) => setDecisionDraft(e.target.value)}
          />
          <label htmlFor="signoffConditions">成立条件（每行一条）</label>
          <textarea
            id="signoffConditions"
            rows={2}
            value={conditionsText}
            onChange={(e) => setConditionsText(e.target.value)}
          />
          <label htmlFor="signoffExit">退出规则（每行一条）</label>
          <textarea
            id="signoffExit"
            rows={2}
            value={exitText}
            onChange={(e) => setExitText(e.target.value)}
          />
          <label htmlFor="signoffReview">复盘日期</label>
          <input
            id="signoffReview"
            type="date"
            value={reviewDate}
            onChange={(e) => setReviewDate(e.target.value)}
          />
          <label htmlFor="signoffStatement">签名声明（亲笔输入，表示承担该决定）</label>
          <input
            id="signoffStatement"
            value={statement}
            onChange={(e) => setStatement(e.target.value)}
            placeholder="例如：我确认在上述条件下做出该决定。"
          />
          {error && <p role="alert">{error}</p>}
          <button type="submit" className="primary-action small" disabled={phase === "signing"}>
            <span>{phase === "signing" ? "签署中…" : "签署并冻结决定"}</span>
          </button>
        </form>
      )}
    </div>
  );
}
