"use client";

import { useEffect, useState } from "react";

import type { RunTraceEvent } from "@/lib/shell/decisionLoop";

/**
 * The visible answer to "where is my analysis right now?".
 *
 * This was previously a single line of text (`status（xx%）`), which is why the
 * run felt frozen. It is now a six-stage indicator plus a progress bar fed by
 * the run's OWN persisted progress - and the backend only started publishing
 * that mid-run once stage boundaries became commit boundaries, so nothing here
 * is estimated or animated to look busy.
 *
 * Honesty rules kept:
 * - progress comes from the run, never from a timer;
 * - `queued` shows 0% and says so, instead of creeping forward;
 * - colour is never the only signal: every stage carries a text state and a
 *   data attribute, and the bar carries aria values.
 */

export const ANALYSIS_STAGES = [
  { id: "planning", label: "规划", hint: "拆解决定" },
  { id: "retrieving", label: "检索", hint: "建立事实" },
  { id: "analyzing", label: "分析", hint: "权衡选项" },
  { id: "criticizing", label: "反方", hint: "攻击结论" },
  { id: "synthesizing", label: "综合", hint: "给出承诺" },
  { id: "validating", label: "验证", hint: "审查链条" },
] as const;

export type StageState = "done" | "active" | "pending" | "stopped";

const STATE_LABELS: Record<StageState, string> = {
  done: "已完成",
  active: "进行中",
  pending: "未开始",
  stopped: "未执行",
};

/** Independent extra passes; they are not pipeline stages and never gate a run. */
const ENRICHMENT_LABELS: Record<string, string> = {
  safety_anchor: "安全锚（独立盲区复核）",
  chief_of_staff: "参谋长（行动建议）",
};

const TERMINAL_OK = new Set(["ready"]);
const TERMINAL_STOPPED = new Set(["blocked", "cancelled", "needs_attention"]);

/** Seconds a run may sit in `queued` before the UI stops looking patient. */
const QUEUED_WARN_SECONDS = 30;
const QUEUED_ALARM_SECONDS = 180;

export type TraceEntry = {
  stage: string;
  headline: string;
  details: string[];
  model?: string;
};

export function stageStates(status: string): Record<string, StageState> {
  const index = ANALYSIS_STAGES.findIndex((stage) => stage.id === status);
  const states: Record<string, StageState> = {};
  ANALYSIS_STAGES.forEach((stage, position) => {
    if (TERMINAL_OK.has(status)) {
      states[stage.id] = "done";
    } else if (TERMINAL_STOPPED.has(status)) {
      // A stopped run did reach SOME stage; without knowing which, the honest
      // rendering is "not executed" rather than a fake tick.
      states[stage.id] = "stopped";
    } else if (index < 0) {
      states[stage.id] = "pending"; // queued: nothing has started
    } else if (position < index) {
      states[stage.id] = "done";
    } else if (position === index) {
      states[stage.id] = "active";
    } else {
      states[stage.id] = "pending";
    }
  });
  return states;
}

export function traceEntryFrom(trace: RunTraceEvent): TraceEntry | null {
  if (!trace.digest) return null;
  const details = [
    ...(trace.digest.keyFindings ?? []),
    ...(trace.digest.risks ?? []).map((risk) => `风险：${risk}`),
  ].slice(0, 4);
  const headline = trace.digest.headline ?? details[0] ?? "";
  if (!headline) return null;
  // R1: show WHICH brain spoke - a heterogeneous adversary is a genuinely
  // independent second opinion; same-model opposition is labeled honestly.
  const model = trace.digest.model
    ? trace.digest.cognitiveSource === "heterogeneous"
      ? `${trace.digest.model} · 异构第二脑`
      : trace.digest.model
    : "";
  return { stage: trace.stage ?? "", headline, details, model };
}

export type AnalysisProgressProps = {
  status: string;
  /** The run's own persisted progress, 0..1. */
  progress: number;
  runId?: string;
  statusLabel: string;
  trace: TraceEntry[];
  /** Cancel the run; offered once a queued run has waited too long. */
  onCancel?: () => void;
  cancelling?: boolean;
};

export function AnalysisProgress({
  status,
  progress,
  runId,
  statusLabel,
  trace,
  onCancel,
  cancelling = false,
}: AnalysisProgressProps) {
  const [queuedSeconds, setQueuedSeconds] = useState(0);

  useEffect(() => {
    if (status !== "queued") {
      setQueuedSeconds(0);
      return;
    }
    const started = Date.now();
    const timer = setInterval(
      () => setQueuedSeconds(Math.floor((Date.now() - started) / 1000)),
      1000,
    );
    return () => clearInterval(timer);
  }, [status]);

  const percent = Math.round(Math.min(1, Math.max(0, progress)) * 100);
  const states = stageStates(status);
  const byStage = new Map(trace.map((entry) => [entry.stage, entry]));
  const enrichment = trace.filter((entry) => entry.stage in ENRICHMENT_LABELS);

  const queuedLevel =
    status !== "queued"
      ? null
      : queuedSeconds >= QUEUED_ALARM_SECONDS
        ? "alarm"
        : queuedSeconds >= QUEUED_WARN_SECONDS
          ? "warn"
          : "waiting";

  return (
    <div className="analysis-progress" data-analysis-progress={status}>
      <div className="analysis-progress-head">
        <span>
          {runId ? `Run ${runId.slice(0, 8)} · ` : ""}
          {statusLabel}
        </span>
        <b data-analysis-percent={percent}>{percent}%</b>
      </div>

      <div
        className="analysis-progress-bar"
        role="progressbar"
        aria-label="分析进度"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        aria-valuetext={`${statusLabel}，${percent}%`}
      >
        <i style={{ width: `${percent}%` }} />
      </div>

      {queuedLevel && queuedLevel !== "waiting" && (
        <p className="analysis-queued-warning" data-analysis-queued={queuedLevel} role="alert">
          {queuedLevel === "alarm"
            ? `已排队 ${queuedSeconds} 秒仍未开始执行。分析工作器很可能没有运行（本地开发需单独启动 worker 进程），或队列前面还有任务。`
            : `已排队 ${queuedSeconds} 秒。正常情况下工作器会在数秒内领取；若持续等待，请确认分析工作器是否在运行。`}
          {onCancel && (
            <>
              {" "}
              <button type="button" className="secondary-action small" disabled={cancelling} onClick={onCancel}>
                <span>{cancelling ? "正在取消…" : "取消本次分析"}</span>
              </button>
            </>
          )}
        </p>
      )}

      {/* data-analysis-trace stays on the stage list: the trace IS the stages. */}
      <ol className="analysis-stepper" data-analysis-stepper data-analysis-trace aria-label="分析阶段与思考轨迹">
        {ANALYSIS_STAGES.map((stage) => {
          const state = states[stage.id];
          const entry = byStage.get(stage.id);
          return (
            <li key={stage.id} data-stage={stage.id} data-stage-state={state} data-trace-stage={stage.id}>
              <div className="stepper-line">
                <i aria-hidden="true" className={`stepper-dot is-${state}`} />
                <b>{stage.label}</b>
                <small>{state === "pending" || state === "stopped" ? stage.hint : STATE_LABELS[state]}</small>
                {entry?.model && (
                  <span className="trace-model-badge" data-trace-model={entry.model}>
                    {entry.model}
                  </span>
                )}
              </div>
              {entry && (
                <div className="stepper-digest">
                  <p>{entry.headline}</p>
                  {entry.details.length > 0 && (
                    <ul>
                      {entry.details.map((detail) => (
                        <li key={detail}>{detail}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ol>

      {enrichment.length > 0 && (
        <ul className="analysis-enrichment" data-analysis-enrichment aria-label="独立复核与行动建议">
          {enrichment.map((entry) => (
            <li key={entry.stage} data-trace-stage={entry.stage}>
              <b>{ENRICHMENT_LABELS[entry.stage]}</b>：{entry.headline}
              {entry.details.length > 0 && (
                <ul>
                  {entry.details.map((detail) => (
                    <li key={detail}>{detail}</li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
