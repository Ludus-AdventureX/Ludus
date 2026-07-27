"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  DecisionLoopError,
  launchAnalysisForCase,
  watchRunUntilTerminal,
  type AnalysisLevel,
  type LaunchStep,
  type RunSnapshot,
} from "@/lib/shell/decisionLoop";

// Fills the reserved `analysis-progress` PhaseSlot with the REAL deep-analysis
// launch + polling line (second half of the core decision loop). Honest state
// only: no fabricated progress, quality verdicts come from the backend, and a
// missing tenant workspace anchor renders the gap state instead of guessing.

const launchStepLabels: Record<LaunchStep, string> = {
  csrf: "建立安全会话",
  seed: "读取案件边界",
  charter: "生成分析章程",
  confirm: "确认分析边界",
  run: "发起深度分析",
};

const runStatusLabels: Record<string, string> = {
  queued: "排队中，等待分析工作器领取",
  planning: "规划阶段",
  retrieving: "检索阶段",
  analyzing: "分析阶段",
  criticizing: "反方质疑",
  synthesizing: "综合阶段",
  validating: "验证阶段",
  ready: "分析完成，通过质量门",
  blocked: "分析完成：质量门未通过（系统拒绝伪造结论）",
  needs_attention: "分析暂停，需要人工关注",
  cancelled: "分析已取消",
};

function statusLabel(status?: string): string {
  return (status && runStatusLabels[status]) || status || "未知状态";
}

type PanelPhase = "idle" | "launching" | "analyzing" | "done" | "error";

type PanelState = {
  phase: PanelPhase;
  step?: LaunchStep;
  runId?: string;
  progress?: number;
  status?: string;
  error?: string;
};

export type AnalysisLaunchPanelProps = {
  workspaceId?: string | null;
  decisionCaseId?: string;
};

export function AnalysisLaunchPanel({ workspaceId = null, decisionCaseId }: AnalysisLaunchPanelProps) {
  const [state, setState] = useState<PanelState>({ phase: "idle" });
  const [level, setLevel] = useState<AnalysisLevel>("focused");
  const abortRef = useRef<AbortController | null>(null);
  // Synchronous re-entrancy guard: state.phase updates are async, so a fast
  // double click could otherwise start two polling loops (review finding P1).
  const busyRef = useRef(false);

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const launch = useCallback(async () => {
    if (!workspaceId || !decisionCaseId) return;
    if (busyRef.current) return;
    busyRef.current = true;
    const abort = new AbortController();
    abortRef.current = abort;
    setState({ phase: "launching" });
    try {
      const launched = await launchAnalysisForCase(workspaceId, decisionCaseId, {
        level,
        onStep: (step) => setState({ phase: "launching", step }),
      });
      setState({
        phase: "analyzing",
        runId: launched.analysisRunId,
        progress: 0,
        status: launched.status,
      });
      const final = await watchRunUntilTerminal(workspaceId, launched.analysisRunId, {
        signal: abort.signal,
        onTick: (snapshot: RunSnapshot) =>
          setState((prev) => ({
            ...prev,
            phase: "analyzing",
            progress: snapshot.progress,
            status: snapshot.status,
          })),
      });
      if (!abort.signal.aborted) {
        setState((prev) => ({
          ...prev,
          phase: "done",
          progress: final.progress,
          status: final.status,
        }));
      }
    } catch (error) {
      if (!abort.signal.aborted) {
        setState((prev) => ({
          ...prev,
          phase: "error",
          error: error instanceof DecisionLoopError ? error.message : "发起分析失败，请稍后重试。",
        }));
      }
    } finally {
      busyRef.current = false;
    }
  }, [decisionCaseId, level, workspaceId]);

  if (!workspaceId || !decisionCaseId) {
    // Same honest gap-state discipline as EvidenceDrawerTrigger: without the
    // tenant workspace anchor no launch is offered and nothing is fabricated.
    return (
      <p className="phase-slot-note" data-analysis-launch="gap">
        缺少工作区锚点（?ws=），无法发起分析；请从项目入口重新打开本案件。
      </p>
    );
  }

  const percent = Math.round((state.progress ?? 0) * 100);
  const busy = state.phase === "launching" || state.phase === "analyzing";

  return (
    <div className="analysis-launch" data-analysis-launch="ready">
      <fieldset className="analysis-level" disabled={busy}>
        <legend>分析深度</legend>
        <label>
          <input
            type="radio"
            name="analysisLevel"
            value="focused"
            checked={level === "focused"}
            onChange={() => setLevel("focused")}
          />
          聚焦研究（focused）
        </label>
        <label>
          <input
            type="radio"
            name="analysisLevel"
            value="full"
            checked={level === "full"}
            onChange={() => setLevel("full")}
          />
          完整战略分析（full，含五 Lens）
        </label>
      </fieldset>
      <button
        type="button"
        className="primary-action small"
        disabled={busy}
        onClick={() => void launch()}
      >
        <span>
          {state.phase === "idle" && "发起聚焦深度分析"}
          {state.phase === "launching" && `${launchStepLabels[state.step ?? "csrf"]}…`}
          {state.phase === "analyzing" && "分析进行中…"}
          {state.phase === "done" && "再次发起分析"}
          {state.phase === "error" && "重试发起分析"}
        </span>
      </button>

      <div role="status" aria-live="polite" className="analysis-launch-status">
        {state.phase === "idle" && <p>确认后将创建分析章程并交给后端工作器逐阶段推进；系统不伪造进度。</p>}
        {state.phase === "launching" && <p>正在{launchStepLabels[state.step ?? "csrf"]}…</p>}
        {state.phase === "analyzing" && (
          <p>
            Run {state.runId?.slice(0, 8)} — {statusLabel(state.status)}（{percent}%）
          </p>
        )}
        {state.phase === "done" && (
          <p data-analysis-terminal={state.status}>
            {statusLabel(state.status)}（Run {state.runId?.slice(0, 8)}，进度 {percent}%）
          </p>
        )}
        {state.phase === "error" && <p>{state.error}</p>}
      </div>
    </div>
  );
}
