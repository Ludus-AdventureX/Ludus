"use client";

import { useCallback, useEffect, useState } from "react";

import {
  DemoApiError,
  DemoFlowResult,
  DemoFlowStep,
  establishGuestSession,
  runSimulation,
  type DemoFixtureIds,
  type SimulationRunData,
} from "@/lib/demo/simulationDemo";

const stepLabels: Record<DemoFlowStep, string> = {
  csrf: "1/4 获取 CSRF token",
  guest: "2/4 建立或恢复 Guest 会话",
  run: "3/4 提交 Simulation Run",
  replay: "4/4 读取 Replay",
};

type PanelState =
  | { phase: "ready"; workspaceId: string; fixture: DemoFixtureIds }
  | { phase: "running"; step: DemoFlowStep }
  | { phase: "done"; result: DemoFlowResult }
  | { phase: "error"; code: string; message: string; canRetry: boolean };

function formatScore(value: number): string {
  return Number.isFinite(value) ? value.toFixed(4) : String(value);
}

function ResultRow({ label, value, mono = true }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-neutral-200 py-2 last:border-b-0 sm:flex-row sm:items-baseline sm:gap-3">
      <dt className="w-40 shrink-0 text-xs uppercase tracking-wide text-neutral-500">{label}</dt>
      <dd className={`min-w-0 break-all text-sm text-neutral-900 ${mono ? "font-mono" : ""}`}>{value}</dd>
    </div>
  );
}

function RunResult({ result }: { result: DemoFlowResult }) {
  const { run, replay, idempotencyReplay } = result;
  const replayMatches = replay.inputHash === run.inputHash;
  return (
    <section aria-label="Simulation run result" className="space-y-6">
      <div className="rounded border border-neutral-300 bg-white p-4">
        <h2 className="text-sm font-semibold text-neutral-900">Run 结果</h2>
        <dl className="mt-2">
          <ResultRow label="Run ID" value={run.simulationRunId} />
          <ResultRow label="Input Hash" value={run.inputHash} />
          <ResultRow label="Engine Version" value={run.engineVersion} />
          <ResultRow
            label="Convergence"
            value={`${run.convergenceStatus}（steps ${run.steps}/${run.maxSteps}）`}
            mono={false}
          />
          <ResultRow
            label="Recommendation"
            value={
              run.recommendedOptionId
                ? `${run.recommendedOptionId}（shift: ${run.recommendationShift}）`
                : `无推荐选项（shift: ${run.recommendationShift}）`
            }
            mono={false}
          />
          {idempotencyReplay && (
            <ResultRow label="Idempotency" value="本次响应为幂等重放（idempotencyReplay）" mono={false} />
          )}
        </dl>
      </div>

      <div className="rounded border border-neutral-300 bg-white p-4">
        <h2 className="text-sm font-semibold text-neutral-900">Option Scores</h2>
        {run.optionScores.length === 0 ? (
          <p className="mt-2 text-sm text-neutral-600">引擎未返回选项得分。</p>
        ) : (
          <ul className="mt-2 divide-y divide-neutral-200">
            {run.optionScores.map((option) => (
              <li key={option.optionId} className="flex items-baseline justify-between gap-4 py-2">
                <span className="min-w-0 break-all font-mono text-sm">{option.optionId}</span>
                <span className="font-mono text-sm tabular-nums">{formatScore(option.score)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="rounded border border-neutral-300 bg-white p-4">
        <h2 className="text-sm font-semibold text-neutral-900">Sensitivity / 翻转条件（Top Drivers）</h2>
        {run.topDrivers.length === 0 ? (
          <p className="mt-2 text-sm text-neutral-600">本次运行没有产生敏感性驱动因子。</p>
        ) : (
          <ul className="mt-2 divide-y divide-neutral-200">
            {run.topDrivers.map((driver) => (
              <li key={driver.nodeId} className="flex items-baseline justify-between gap-4 py-2">
                <span className="min-w-0 break-all font-mono text-sm">{driver.nodeId}</span>
                <span className="font-mono text-sm tabular-nums">Δscore {formatScore(driver.scoreDelta)}</span>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-xs text-neutral-500">
          recommendationShift: <span className="font-mono">{run.recommendationShift}</span>
        </p>
      </div>

      <div className="rounded border border-neutral-300 bg-white p-4">
        <h2 className="text-sm font-semibold text-neutral-900">Replay（GET）</h2>
        <dl className="mt-2">
          <ResultRow label="Replay Run ID" value={replay.simulationRunId} />
          <ResultRow label="Replay Input Hash" value={replay.inputHash} />
          <ResultRow
            label="Hash 校验"
            value={replayMatches ? "一致：GET 重放与 POST 结果 inputHash 相同" : "不一致：请检查后端 replay 契约"}
            mono={false}
          />
        </dl>
      </div>
    </section>
  );
}

export function SimulationDemoPanel() {
  const [state, setState] = useState<PanelState>({ phase: "running", step: "csrf" });

  const boot = useCallback(async () => {
    setState({ phase: "running", step: "csrf" });
    try {
      const { workspaceId, fixture } = await establishGuestSession((step) => {
        setState({ phase: "running", step });
      });
      // Guest 会话已建立（或恢复）；停留在 ready 等待用户点击 Run。
      setState({ phase: "ready", workspaceId, fixture });
    } catch (error) {
      if (error instanceof DemoApiError) {
        setState({ phase: "error", code: error.code, message: error.message, canRetry: true });
      } else {
        setState({ phase: "error", code: "UNEXPECTED_ERROR", message: "发生未知错误，请重试。", canRetry: true });
      }
    }
  }, []);

  useEffect(() => {
    void boot();
  }, [boot]);

  const run = async () => {
    if (state.phase !== "ready") return;
    const { workspaceId, fixture } = state;
    setState({ phase: "running", step: "csrf" });
    try {
      const { run, idempotencyReplay, replay } = await runSimulation(
        workspaceId,
        fixture,
        (step) => setState({ phase: "running", step }),
      );
      setState({
        phase: "done",
        result: { workspaceId, fixture, run, idempotencyReplay, replay },
      });
    } catch (error) {
      if (error instanceof DemoApiError) {
        setState({ phase: "error", code: error.code, message: error.message, canRetry: false });
      } else {
        setState({ phase: "error", code: "UNEXPECTED_ERROR", message: "发生未知错误，请重试。", canRetry: false });
      }
    }
  };

  return (
    <main className="mx-auto min-h-screen w-full max-w-3xl px-4 py-8 sm:px-6">
      <header>
        <p className="inline-block rounded bg-amber-100 px-2 py-1 text-xs font-semibold uppercase tracking-wide text-amber-900">
          Guest · Technical Alpha
        </p>
        <h1 className="mt-3 text-2xl font-semibold text-neutral-900">Simulation Demo</h1>
        <p className="mt-2 text-sm text-neutral-600">
          无需注册：页面加载即建立 Guest 会话（刷新后自动恢复）。所有请求走同源{" "}
          <span className="font-mono">/api</span>，凭据以 cookie 形式随请求携带。
        </p>
      </header>

      <div aria-live="polite" className="mt-6">
        {state.phase === "running" && (
          <p role="status" className="rounded border border-neutral-300 bg-neutral-50 p-3 text-sm text-neutral-700">
            {stepLabels[state.step]}…
          </p>
        )}

        {state.phase === "ready" && (
          <div className="rounded border border-neutral-300 bg-white p-4">
            <h2 className="text-sm font-semibold text-neutral-900">Guest 会话已就绪</h2>
            <dl className="mt-2">
              <ResultRow label="Workspace ID" value={state.workspaceId} />
              <ResultRow label="Graph ID" value={state.fixture.graphId} />
              <ResultRow label="Profile" value={`${state.fixture.decisionMakerProfileId} v${state.fixture.decisionMakerProfileVersion}`} />
            </dl>
            <button
              type="button"
              onClick={run}
              className="mt-4 w-full rounded bg-neutral-900 px-4 py-2 text-sm font-semibold text-white sm:w-auto"
            >
              Run Simulation
            </button>
          </div>
        )}

        {state.phase === "error" && (
          <div role="alert" className="rounded border border-red-300 bg-red-50 p-4">
            <h2 className="text-sm font-semibold text-red-900">请求失败</h2>
            <p className="mt-1 break-all text-sm text-red-800">
              <span className="font-mono">{state.code}</span>：{state.message}
            </p>
            {state.canRetry && (
              <button
                type="button"
                onClick={boot}
                className="mt-3 rounded border border-red-300 bg-white px-3 py-1.5 text-sm font-semibold text-red-800"
              >
                重试
              </button>
            )}
          </div>
        )}

        {state.phase === "done" && <RunResult result={state.result} />}
      </div>

      <footer className="mt-8 border-t border-neutral-200 pt-4 text-xs text-neutral-500">
        Technical Alpha 演示：仅覆盖 Simulation Run 创建与 Replay 读取，不包含 Graph editor、Report 与 Decision。
      </footer>
    </main>
  );
}

export type { SimulationRunData };
