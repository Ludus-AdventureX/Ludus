"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  DecisionLoopError,
  cancelRun,
  getCaseAnalysisSeed,
  launchAnalysisForCase,
  watchRunUntilTerminal,
  type AnalysisLevel,
  type LaunchStep,
  type RunSnapshot,
  type RunTraceEvent,
} from "@/lib/shell/decisionLoop";
import {
  AnalysisProgress,
  traceEntryFrom,
  type TraceEntry,
} from "@/components/shell/views/AnalysisProgress";
import { clarifyCaseQuestion, type ClarifierCard } from "@/lib/shell/clarifier";

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

/** Actionable text per failure class; the technical code rides the title only. */
function errorMessage(error: unknown): string {
  if (!(error instanceof DecisionLoopError)) {
    return "发起分析失败，请稍后重试。";
  }
  if (error.code === "NETWORK_ERROR" || error.status === 0) {
    return "无法连接后端服务。本地开发需要 API 进程在运行（默认 127.0.0.1:8000）。";
  }
  if (error.code === "RUN_POLL_TIMEOUT") {
    return "分析长时间没有推进。请确认分析工作器进程是否在运行，然后重试或取消本次分析。";
  }
  if (error.status === 401 || error.status === 403) {
    return `会话或权限校验未通过：${error.message}`;
  }
  if (error.status === 404) {
    return "找不到对应的案件或工作区（也可能是无权访问）。请从项目入口重新打开本案件。";
  }
  if (error.status >= 500) {
    return "后端处理本次请求时出错。请稍后重试；若持续失败请查看 API 日志。";
  }
  return error.message;
}

function findingText(finding: Record<string, unknown>): string {
  for (const key of ["message", "detail", "reason", "code"]) {
    const value = finding[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return JSON.stringify(finding);
}

export type AnalysisLaunchPanelProps = {
  workspaceId?: string | null;
  decisionCaseId?: string;
};

export function AnalysisLaunchPanel({ workspaceId = null, decisionCaseId }: AnalysisLaunchPanelProps) {
  const [state, setState] = useState<PanelState>({ phase: "idle" });
  const [level, setLevel] = useState<AnalysisLevel>("focused");
  const [trace, setTrace] = useState<TraceEntry[]>([]);
  const [findings, setFindings] = useState<string[]>([]);
  // R2 question clarifier: advisory card + adoption toggle.
  const [clarifier, setClarifier] = useState<ClarifierCard | null>(null);
  const [adopted, setAdopted] = useState(false);
  const [clarifying, setClarifying] = useState(false);
  const [cancelling, setCancelling] = useState(false);
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
    setTrace([]);
    setFindings([]);
    try {
      const launched = await launchAnalysisForCase(workspaceId, decisionCaseId, {
        level,
        // R2: an adopted clarifier rewrite becomes the charter's question,
        // and the clarifier verdicts are archived as charter constraints so
        // the run (and the provenance chain) remembers WHY it was reframed.
        questionOverride: adopted && clarifier?.refinedQuestion ? clarifier.refinedQuestion : undefined,
        extraAssumptions:
          adopted && clarifier?.available
            ? [
                `问题质检存档：${clarifier.pseudoDecision?.verdict ? "疑似伪决策" : "真决策"}；` +
                  `${clarifier.falseDilemma?.verdict ? `假两难（第三选项：${clarifier.falseDilemma.thirdOption}）` : "选项框架成立"}；` +
                  `可逆性 ${clarifier.reversibility?.type ?? "type1"}。原问题：${clarifier.originalQuestion ?? ""}`,
              ]
            : undefined,
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
        onTrace: (event: RunTraceEvent) => {
          const entry = traceEntryFrom(event);
          if (entry) {
            setTrace((prev) =>
              prev.some((p) => p.stage === entry.stage) ? prev : [...prev, entry],
            );
          }
          if (event.findings) {
            setFindings(event.findings.map(findingText).filter(Boolean).slice(0, 5));
          }
        },
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
          error: errorMessage(error),
        }));
      }
    } finally {
      busyRef.current = false;
      setCancelling(false);
    }
  }, [adopted, clarifier, decisionCaseId, level, workspaceId]);

  /** Escape hatch for a run the worker never picked up. */
  const cancel = useCallback(async () => {
    if (!workspaceId || !state.runId || cancelling) return;
    setCancelling(true);
    try {
      await cancelRun(workspaceId, state.runId);
      // The watcher's own status re-read observes `cancelled` and finishes; no
      // local status is invented here.
    } catch (error) {
      setState((prev) => ({ ...prev, error: errorMessage(error) }));
      setCancelling(false);
    }
  }, [workspaceId, state.runId, cancelling]);

  const runClarifier = useCallback(async () => {
    if (!workspaceId || !decisionCaseId || clarifying) return;
    setClarifying(true);
    setAdopted(false);
    try {
      const seed = await getCaseAnalysisSeed(workspaceId, decisionCaseId);
      const card = await clarifyCaseQuestion(workspaceId, decisionCaseId, seed.decisionQuestion);
      setClarifier(card);
    } catch {
      setClarifier({ available: false });
    } finally {
      setClarifying(false);
    }
  }, [workspaceId, decisionCaseId, clarifying]);

  if (!workspaceId || !decisionCaseId) {
    // Same honest gap-state discipline as EvidenceDrawerTrigger: without the
    // tenant workspace anchor no launch is offered and nothing is fabricated.
    return (
      <p className="phase-slot-note" data-analysis-launch="gap">
        缺少工作区锚点（?ws=），无法发起分析；请从项目入口重新打开本案件。
      </p>
    );
  }

  const busy = state.phase === "launching" || state.phase === "analyzing";

  return (
    <div className="analysis-launch" data-analysis-launch="ready">
      {/* R2: question quality check BEFORE spending an analysis run. */}
      <div className="clarifier-block" data-clarifier-block>
        <button
          type="button"
          className="secondary-action small"
          disabled={busy || clarifying}
          onClick={() => void runClarifier()}
        >
          <span>{clarifying ? "质检中…" : "先做问题质检（问对问题再分析）"}</span>
        </button>
        {clarifier && !clarifier.available && (
          <p className="phase-slot-note">问题质检暂不可用——可直接发起分析。</p>
        )}
        {clarifier?.available && (
          <div className="clarifier-card" data-clarifier-card role="note">
            <p data-clarifier-pseudo={clarifier.pseudoDecision?.verdict ?? false}>
              <b>{clarifier.pseudoDecision?.verdict ? "⚠ 疑似伪决策" : "✓ 是真决策"}</b>
              {clarifier.pseudoDecision?.reason && `：${clarifier.pseudoDecision.reason}`}
            </p>
            <p data-clarifier-dilemma={clarifier.falseDilemma?.verdict ?? false}>
              <b>{clarifier.falseDilemma?.verdict ? "⚠ 疑似假两难" : "✓ 选项框架成立"}</b>
              {clarifier.falseDilemma?.thirdOption && `：第三条路——${clarifier.falseDilemma.thirdOption}`}
            </p>
            <p>
              <b>{clarifier.reversibility?.type === "type2" ? "可逆决定（Type 2）" : "难逆决定（Type 1）"}</b>
              {clarifier.reversibility?.advice && `：${clarifier.reversibility.advice}`}
            </p>
            {clarifier.refinedQuestion &&
              clarifier.refinedQuestion !== clarifier.originalQuestion && (
                <label className="clarifier-adopt">
                  <input
                    type="checkbox"
                    checked={adopted}
                    onChange={(e) => setAdopted(e.target.checked)}
                  />
                  <span>
                    采纳改写后的问题发起分析：「{clarifier.refinedQuestion}」
                  </span>
                </label>
              )}
          </div>
        )}
      </div>
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

      {state.phase === "idle" ? (
        <p className="analysis-launch-status">确认后将创建分析章程并交给后端工作器逐阶段推进；系统不伪造进度。</p>
      ) : (
        <div role="status" aria-live="polite" className="analysis-launch-status">
          {state.phase === "launching" && <p>正在{launchStepLabels[state.step ?? "csrf"]}…</p>}
          {(state.phase === "analyzing" || state.phase === "done") && (
            <div data-analysis-terminal={state.phase === "done" ? state.status : undefined}>
              <AnalysisProgress
                status={state.status ?? "queued"}
                progress={state.progress ?? 0}
                statusLabel={statusLabel(state.status)}
                trace={trace}
                {...(state.runId ? { runId: state.runId } : {})}
                {...(state.phase === "analyzing" ? { onCancel: () => void cancel(), cancelling } : {})}
              />
            </div>
          )}
          {state.phase === "error" && <p>{state.error}</p>}
        </div>
      )}

      {state.phase === "done" && state.status === "blocked" && (
        <div className="analysis-blocked-guide" data-analysis-blocked-guide>
          <p>质量门拦截了本次分析——不是失败，而是证据链还支撑不起结论。卡点：</p>
          {findings.length > 0 ? (
            <ul>
              {findings.map((text) => (
                <li key={text}>{text}</li>
              ))}
            </ul>
          ) : (
            <p>验证阶段判定证据支撑不足（未给出具体条目）。</p>
          )}
          <p>建议：回到 Q 区把上面缺口对应的事实补进档案（确认候选），再发起一次分析。</p>
        </div>
      )}
    </div>
  );
}
