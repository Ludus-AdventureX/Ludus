"use client";

import { FormEvent, useState } from "react";

import {
  DemoApiError,
  DemoFlowResult,
  DemoFlowStep,
  readDemoFixtureConfig,
  runDemoFlow,
} from "@/lib/demo/simulationDemo";

const stepLabels: Record<DemoFlowStep, string> = {
  csrf: "1/5 获取 CSRF token",
  login: "2/5 登录 Demo 账号",
  session: "3/5 读取 session / workspace",
  run: "4/5 提交 Simulation Run",
  replay: "5/5 读取 Replay",
};

type PanelState =
  | { phase: "idle" }
  | { phase: "loading"; step: DemoFlowStep }
  | { phase: "error"; code: string; message: string }
  | { phase: "done"; result: DemoFlowResult };

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
    <section aria-label="Simulation run result" className="mt-6 space-y-6">
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
  const fixture = readDemoFixtureConfig();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [state, setState] = useState<PanelState>({ phase: "idle" });

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!fixture.ok || state.phase === "loading") return;
    setState({ phase: "loading", step: "csrf" });
    try {
      const result = await runDemoFlow(fixture.config, { email, password }, (step) =>
        setState({ phase: "loading", step }),
      );
      setState({ phase: "done", result });
    } catch (error) {
      if (error instanceof DemoApiError) {
        setState({ phase: "error", code: error.code, message: error.message });
      } else {
        setState({ phase: "error", code: "UNEXPECTED_ERROR", message: "发生未知错误，请重试。" });
      }
    }
  };

  return (
    <main className="mx-auto min-h-screen w-full max-w-3xl px-4 py-8 sm:px-6">
      <header>
        <p className="inline-block rounded bg-amber-100 px-2 py-1 text-xs font-semibold uppercase tracking-wide text-amber-900">
          Technical Alpha · Demo Fixture
        </p>
        <h1 className="mt-3 text-2xl font-semibold text-neutral-900">Simulation Run Demo</h1>
        <p className="mt-2 text-sm text-neutral-600">
          使用预置 Demo fixture（Technical Alpha 专用，非正式数据）对同源 <span className="font-mono">/api</span>{" "}
          执行一次 Simulation Run，并读取 Replay 验证。
        </p>
      </header>

      {!fixture.ok ? (
        <div role="alert" className="mt-6 rounded border border-red-300 bg-red-50 p-4">
          <h2 className="text-sm font-semibold text-red-900">Demo fixture 未配置</h2>
          <p className="mt-1 text-sm text-red-800">缺少以下环境变量，无法启动演示：</p>
          <ul className="mt-2 list-inside list-disc font-mono text-xs text-red-800">
            {fixture.missing.map((name) => (
              <li key={name}>{name}</li>
            ))}
          </ul>
        </div>
      ) : (
        <>
          <form onSubmit={submit} className="mt-6 rounded border border-neutral-300 bg-white p-4">
            <h2 className="text-sm font-semibold text-neutral-900">Demo 账号登录</h2>
            <p className="mt-1 text-xs text-neutral-500">凭据仅提交到同源 /api/auth/login，不会写入页面代码或环境变量。</p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <label className="flex flex-col gap-1 text-sm text-neutral-700">
                Email
                <input
                  type="email"
                  required
                  autoComplete="username"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  className="rounded border border-neutral-300 px-2 py-1.5 font-mono text-sm"
                />
              </label>
              <label className="flex flex-col gap-1 text-sm text-neutral-700">
                Password
                <input
                  type="password"
                  required
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="rounded border border-neutral-300 px-2 py-1.5 font-mono text-sm"
                />
              </label>
            </div>
            <button
              type="submit"
              disabled={state.phase === "loading"}
              className="mt-4 w-full rounded bg-neutral-900 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-neutral-400 sm:w-auto"
            >
              {state.phase === "loading" ? "运行中…" : "运行 Demo Simulation"}
            </button>
          </form>

          <div aria-live="polite" className="mt-4">
            {state.phase === "loading" && (
              <p role="status" className="rounded border border-neutral-300 bg-neutral-50 p-3 text-sm text-neutral-700">
                {stepLabels[state.step]}…
              </p>
            )}
            {state.phase === "error" && (
              <div role="alert" className="rounded border border-red-300 bg-red-50 p-4">
                <h2 className="text-sm font-semibold text-red-900">请求失败</h2>
                <p className="mt-1 break-all text-sm text-red-800">
                  <span className="font-mono">{state.code}</span>：{state.message}
                </p>
              </div>
            )}
          </div>

          {state.phase === "done" && <RunResult result={state.result} />}
        </>
      )}

      <footer className="mt-8 border-t border-neutral-200 pt-4 text-xs text-neutral-500">
        Technical Alpha 演示：仅覆盖 Simulation Run 创建与 Replay 读取，不包含 Graph editor、Report 与 Decision。
      </footer>
    </main>
  );
}
