"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { EvidenceDrawerTrigger } from "@/components/quality/EvidenceDrawerTrigger";
import { AnalysisLaunchPanel } from "@/components/shell/views/AnalysisLaunchPanel";
import {
  QualityGatePanel,
  type GateDims,
  type QualityGateProjection,
} from "@/components/quality/QualityGatePanel";
import {
  ANALYSIS_STAGES,
  stageStates,
  traceEntryFrom,
  type TraceEntry,
} from "@/components/shell/views/AnalysisProgress";
import {
  replayRunTrace,
  watchRunUntilTerminal,
  cancelRun,
  type RunTraceEvent,
} from "@/lib/shell/decisionLoop";
import {
  EXECUTING_RUN_STATUSES,
  listCaseAnalyses,
  runStatusLabel,
  type RunAnchor,
} from "@/lib/shell/runReads";

// Look V7 `#view-analysis` — now a LIVE projection of the case's latest
// AnalysisRun: the research trace replays the run's persisted event stream
// into the prototype's trace-list, the quality margin mounts the real
// QualityGatePanel, and the analysis launch controls live here (moved from Q).

export type AnalysisViewProps = {
  workspaceId?: string | null;
  decisionCaseId?: string;
};

type GateFinding = Record<string, unknown>;

function gateProjectionFrom(
  runStatus: string | null,
  findings: GateFinding[],
  trace: TraceEntry[],
): QualityGateProjection {
  let gate: QualityGateProjection["gate"] = null;
  const blockedCodes: string[] = [];
  for (const finding of findings) {
    const code = typeof finding.code === "string" ? finding.code : "";
    if (code === "deterministic_gate") {
      gate = {
        passed: finding.passed === true,
        ...(typeof finding.score === "number" ? { score: finding.score } : {}),
        ...(finding.dims && typeof finding.dims === "object"
          ? { dims: finding.dims as GateDims }
          : {}),
      };
    } else if (code && runStatus === "blocked") {
      blockedCodes.push(code);
    }
  }
  return {
    runStatus,
    gate,
    blockedCodes: [...new Set(blockedCodes)],
    fixtureRun: trace.some((entry) => entry.model?.startsWith("fixture")),
  };
}

export function AnalysisView({ workspaceId = null, decisionCaseId }: AnalysisViewProps = {}) {
  const [run, setRun] = useState<RunAnchor | null>(null);
  const [phase, setPhase] = useState<"gap" | "loading" | "none" | "ready" | "error">(
    workspaceId && decisionCaseId ? "loading" : "gap",
  );
  const [status, setStatus] = useState<string | null>(null);
  const [trace, setTrace] = useState<TraceEntry[]>([]);
  const [findings, setFindings] = useState<GateFinding[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    if (!workspaceId || !decisionCaseId) return;
    let cancelled = false;
    const abort = new AbortController();
    abortRef.current = abort;

    const absorb = (event: RunTraceEvent) => {
      const entry = traceEntryFrom(event);
      if (entry) {
        setTrace((prev) =>
          prev.some((p) => p.stage === entry.stage) ? prev : [...prev, entry],
        );
      }
      if (event.findings) setFindings(event.findings);
    };

    (async () => {
      try {
        const anchors = await listCaseAnalyses(workspaceId, decisionCaseId);
        if (cancelled) return;
        if (anchors.length === 0) {
          setPhase("none");
          return;
        }
        const latest = anchors[0]!;
        setRun(latest);
        setStatus(latest.status);
        setPhase("ready");
        // Replay the persisted stream first — a settled run has its whole
        // trace on disk and SSE alone would show nothing after a reload.
        const replayed = await replayRunTrace(workspaceId, latest.analysisRunId);
        if (cancelled) return;
        for (const event of replayed) absorb(event);
        if (EXECUTING_RUN_STATUSES.has(latest.status)) {
          const final = await watchRunUntilTerminal(workspaceId, latest.analysisRunId, {
            signal: abort.signal,
            onTrace: absorb,
            onTick: (snapshot) => {
              if (!cancelled) setStatus(snapshot.status);
            },
          });
          if (!cancelled) setStatus(final.status);
        }
      } catch {
        if (!cancelled) setPhase("error");
      }
    })();
    return () => {
      cancelled = true;
      abort.abort();
    };
  }, [workspaceId, decisionCaseId]);

  const states = stageStates(status ?? "");
  const byStage = useMemo(() => new Map(trace.map((t) => [t.stage, t])), [trace]);
  const executing = status !== null && EXECUTING_RUN_STATUSES.has(status);
  const projection = gateProjectionFrom(
    phase === "ready" ? status : null,
    findings,
    trace,
  );

  const coordinate = run ? `E-${String(run.caseVersion).padStart(2, "0")}` : "E-—";
  const coordinateNote =
    phase === "ready"
      ? runStatusLabel(status ?? undefined)
      : phase === "loading"
        ? "正在读取研究记录…"
        : "尚无进行中的研究";

  const headline =
    phase === "ready" ? (
      <>先找到最可能<br />推翻当前倾向的证据</>
    ) : (
      "研究尚未开始"
    );

  const introCopy =
    phase === "ready"
      ? executing
        ? "研究正在推进；下方轨迹随每个阶段的提交实时更新。系统只展示可审计产物，不展示隐藏思维过程。"
        : "本次研究已结束；下方是完整的研究轨迹与质量门裁决。系统只展示可审计产物，不展示隐藏思维过程。"
      : phase === "gap"
        ? "缺少工作区锚点（?ws=），请从项目入口重新打开本案件。"
        : phase === "error"
          ? "研究记录读取失败，请稍后重试。"
          : "在上方发起分析后，这里展示研究轨迹与可审计产物。系统只展示可审计产物，不展示隐藏思维过程。";

  const doneCount = trace.filter((t) =>
    ANALYSIS_STAGES.some((s) => s.id === t.stage),
  ).length;

  return (
    <section className="view is-active" id="view-analysis" data-view-panel="analysis" aria-labelledby="analysis-view-title">
      <header className="view-intro analysis-intro">
        <div className="intro-coordinate analysis-coordinate"><span>{coordinate}</span><i /><small>{coordinateNote}</small></div>
        <div className="intro-grid">
          <div>
            <p className="eyebrow">证据不是为了支持答案，而是为了暴露答案的边界</p>
            <h1 id="analysis-view-title">{headline}</h1>
            <p className="intro-copy">{introCopy}</p>
          </div>
          <div className="intro-actions">
            {executing && (
              <span className="run-state"><i /> {runStatusLabel(status ?? undefined)}</span>
            )}
          </div>
        </div>
      </header>

      <div className="analysis-layout">
        <article className="analysis-trace">
          <header className="section-line-heading">
            <div><span>Analysis movement</span><h2>研究轨迹</h2></div>
            <small>
              {phase === "ready"
                ? `${doneCount} / ${ANALYSIS_STAGES.length} 个阶段有产物`
                : "等待第一次分析"}
            </small>
          </header>

          {phase !== "ready" || (status && ["blocked", "cancelled", "parked"].includes(status)) ? (
            <div>
              <AnalysisLaunchPanel
                {...(workspaceId ? { workspaceId } : {})}
                {...(decisionCaseId ? { decisionCaseId } : {})}
              />
              {phase === "none" && (
                <p className="phase-slot-note">在此发起第一次分析。</p>
              )}
              {phase === "loading" && (
                <p className="phase-slot-note">正在读取研究记录…</p>
              )}
              {phase === "ready" && status === "blocked" && trace.length > 0 && (
                <details className="trace-history" open>
                  <summary>上次分析轨迹（被质量门拦截）</summary>
                  <ol className="trace-list" aria-label="研究阶段轨迹">
                    {ANALYSIS_STAGES.map((stage, index) => {
                      const state = states[stage.id];
                      const entry = byStage.get(stage.id);
                      const className =
                        state === "done" ? "is-complete" : state === "active" ? "is-active" : "";
                      return (
                        <li key={stage.id} className={className} data-trace-stage={stage.id}>
                          <span className="trace-node">{String(index + 1).padStart(2, "0")}</span>
                          <div>
                            <b>{stage.label} · {stage.hint}</b>
                            <p>{entry?.headline ?? (state === "pending" ? "等待前序阶段完成。" : "本次运行未执行到该阶段。")}</p>
                          </div>
                        </li>
                      );
                    })}
                  </ol>
                </details>
              )}
            </div>
          ) : phase === "ready" && status === "needs_attention" ? (
            <>
              <RunParkedNotice workspaceId={workspaceId} run={run} />
              <ol className="trace-list" aria-label="研究阶段轨迹">
                {ANALYSIS_STAGES.map((stage, index) => {
                  const state = states[stage.id];
                  const entry = byStage.get(stage.id);
                  const className =
                    state === "done" ? "is-complete" : state === "active" ? "is-active" : "";
                  return (
                    <li key={stage.id} className={className} data-trace-stage={stage.id}>
                      <span className="trace-node">{String(index + 1).padStart(2, "0")}</span>
                      <div>
                        <b>{stage.label} · {stage.hint}</b>
                        <p>{entry?.headline ?? (state === "pending" ? "等待前序阶段完成。" : "本次运行未执行到该阶段。")}</p>
                      </div>
                    </li>
                  );
                })}
              </ol>
            </>
          ) : (
            <ol className="trace-list" aria-label="研究阶段轨迹">
              {ANALYSIS_STAGES.map((stage, index) => {
                const state = states[stage.id];
                const entry = byStage.get(stage.id);
                const className =
                  state === "done" ? "is-complete" : state === "active" ? "is-active" : "";
                return (
                  <li key={stage.id} className={className} data-trace-stage={stage.id}>
                    <span className="trace-node">{String(index + 1).padStart(2, "0")}</span>
                    <div>
                      <b>{stage.label} · {stage.hint}</b>
                      <p>{entry?.headline ?? (state === "pending" ? "等待前序阶段完成。" : state === "stopped" ? "本次运行未执行到该阶段。" : "进行中…")}</p>
                      {entry && entry.details.length > 0 && (
                        <div className="trace-output">
                          <span>阶段产物</span> {entry.details.join(" · ")}
                        </div>
                      )}
                    </div>
                    <small>
                      {state === "done" ? "完成" : state === "active" ? "进行中" : state === "stopped" ? "未执行" : "等待"}
                    </small>
                  </li>
                );
              })}
            </ol>
          )}
        </article>

        <QualityGatePanel projection={projection} />
      </div>

      <section className="custody-strip" aria-label="证据保管链">
        <span className="custody-title">一条结论如何形成</span>
        <EvidenceDrawerTrigger
          {...(workspaceId ? { workspaceId } : {})}
          {...(decisionCaseId ? { decisionCaseId } : {})}
        />
      </section>
    </section>
  );
}

type RunParkedNoticeProps = {
  workspaceId?: string | null;
  run: RunAnchor | null;
};

function RunParkedNotice({ workspaceId, run }: RunParkedNoticeProps) {
  const [cancelling, setCancelling] = useState(false);
  const [notice, setNotice] = useState("");
  if (!run || !workspaceId) return null;
  return (
    <div className="run-parked-note" data-run-parked>
      <p>
        本次分析已暂停（worker 执行失败，例如模型返回了无法解析的输出）。
        你可以取消本次分析后重新发起；数据不会丢失，已完成的阶段产物会保留在下方轨迹中。
      </p>
      {notice && <p className="remediation-notice" role="status">{notice}</p>}
      <button
        type="button"
        className="secondary-action"
        disabled={cancelling}
        onClick={async () => {
          setCancelling(true);
          setNotice("");
          try {
            await cancelRun(workspaceId, run.analysisRunId);
            window.location.reload();
          } catch {
            setCancelling(false);
            setNotice("取消失败，请稍后重试。");
          }
        }}
      >
        {cancelling ? "取消中…" : "取消本次分析"}
      </button>
    </div>
  );
}
