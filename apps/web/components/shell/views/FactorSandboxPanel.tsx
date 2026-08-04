"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  SandboxError,
  loadSandboxBaseline,
  previewSandbox,
  type SandboxFactor,
  type SandboxState,
} from "@/lib/shell/factorSandbox";
import { launchAnalysisForCase } from "@/lib/shell/decisionLoop";
import { FactorGraphCanvas } from "@/components/shell/views/FactorGraphCanvas";

// Report factor sandbox (three-layer what-if). Layer 1: edit factor strengths
// -> instant deterministic re-propagation (server calculator, reproducible).
// Layer 3: one-click deep re-analysis (a real new focused run). No fabricated
// verdicts; the outcome bar is a transparent weighted propagation, and the
// panel self-hides until the case has analysed factors.
//
// Route A: the same wire data also renders as a spatial graph (outcome node
// fed by factor nodes + influence edges). Graph view is the default where the
// runtime supports it (ResizeObserver); the list view stays as the accessible
// fallback and the jsdom test path — both drive the identical preview chain.

export type FactorSandboxPanelProps = {
  workspaceId?: string | null;
  decisionCaseId?: string;
};

function directionTag(direction: string): string {
  return direction === "opposing" ? "反向" : direction === "neutral" ? "中性" : "支撑";
}

function graphCapable(): boolean {
  // ReactFlow measures through ResizeObserver; runtimes without it (jsdom)
  // keep the list view — the honest fallback, never a broken canvas.
  return typeof window !== "undefined" && typeof window.ResizeObserver === "function";
}

export function FactorSandboxPanel({ workspaceId = null, decisionCaseId }: FactorSandboxPanelProps) {
  const [state, setState] = useState<SandboxState | null>(null);
  const [overrides, setOverrides] = useState<Record<string, number>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [deepStatus, setDeepStatus] = useState("");
  const [canGraph] = useState<boolean>(() => graphCapable());
  const [viewMode, setViewMode] = useState<"graph" | "list">("graph");
  const [selectedFactorId, setSelectedFactorId] = useState<string | null>(null);
  const loadedRef = useRef(false);

  useEffect(() => {
    if (!workspaceId || !decisionCaseId) return;
    let cancelled = false;
    void loadSandboxBaseline(workspaceId, decisionCaseId)
      .then((result) => {
        if (!cancelled) {
          setState(result);
          loadedRef.current = true;
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof SandboxError ? err.message : "沙盘加载失败。");
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, decisionCaseId]);

  const rerun = useCallback(
    async (next: Record<string, number>) => {
      if (!workspaceId || !decisionCaseId) return;
      setBusy(true);
      setError("");
      try {
        setState(await previewSandbox(workspaceId, decisionCaseId, next));
      } catch (err) {
        setError(err instanceof SandboxError ? err.message : "重新推演失败。");
      } finally {
        setBusy(false);
      }
    },
    [workspaceId, decisionCaseId],
  );

  const onSlide = useCallback(
    (factorId: string, value: number) => {
      setOverrides((prev) => {
        const next = { ...prev, [factorId]: value };
        void rerun(next);
        return next;
      });
    },
    [rerun],
  );

  const onRemove = useCallback(
    (factorId: string) => {
      // "Removing" a factor = driving its strength to zero (it stops pushing).
      onSlide(factorId, 0);
    },
    [onSlide],
  );

  const reset = useCallback(() => {
    setOverrides({});
    void rerun({});
  }, [rerun]);

  const deepReanalyze = useCallback(async () => {
    if (!workspaceId || !decisionCaseId) return;
    setDeepStatus("正在发起深度重分析…");
    try {
      // Layer 3: the user's what-if assumptions travel into the new charter
      // as REAL constraints, so the fresh run genuinely reasons under them.
      const assumptions = (state?.factors ?? [])
        .filter((f) => overrides[f.id] != null && overrides[f.id] !== f.baseline)
        .map((f) =>
          overrides[f.id] === 0
            ? `沙盘假设：忽略因子「${f.label}」（用户判定其不成立）`
            : `沙盘假设：因子「${f.label}」的强度按 ${Math.round((overrides[f.id] ?? 0) * 100)}% 考虑（原 ${Math.round(f.baseline * 100)}%）`,
        );
      const launched = await launchAnalysisForCase(workspaceId, decisionCaseId, {
        level: "focused",
        extraAssumptions: assumptions,
      });
      setDeepStatus(
        assumptions.length > 0
          ? `已带着 ${assumptions.length} 条沙盘假设发起新 run（${launched.analysisRunId.slice(0, 8)}）——到 E 证据区看实时进度。`
          : `已发起新的分析 run（${launched.analysisRunId.slice(0, 8)}）——到 E 证据区查看实时进度。`,
      );
    } catch {
      setDeepStatus("发起深度重分析失败，请到 E 证据区手动发起。");
    }
  }, [workspaceId, decisionCaseId, state, overrides]);

  if (!workspaceId || !decisionCaseId) return null;
  if (loadedRef.current && state && !state.available) {
    return (
      <section className="factor-sandbox" data-factor-sandbox="empty">
        <p className="phase-slot-note">
          因子沙盘尚未开放——完成一次深度分析后，影响因子会出现在这里。
        </p>
      </section>
    );
  }
  if (!state) return null;

  const percent = Math.round(state.outcomeScore * 100);
  const dirty = Object.keys(overrides).length > 0;
  const showGraph = canGraph && viewMode === "graph";
  const selectedFactor: SandboxFactor | null =
    state.factors.find((factor) => factor.id === selectedFactorId) ?? state.factors[0] ?? null;

  const factorRows = state.factors.map((factor) => (
    <li key={factor.id} data-factor-direction={factor.direction}>
      <div className="sandbox-factor-head">
        <b>{factor.label}</b>
        <span className="sandbox-factor-tag">
          {directionTag(factor.direction)} · 权重 {factor.weight.toFixed(2)}
        </span>
        <button type="button" className="sandbox-remove" onClick={() => onRemove(factor.id)} aria-label={`移除因子 ${factor.label}`}>
          移除
        </button>
      </div>
      <input
        type="range"
        min={0}
        max={1}
        step={0.05}
        value={factor.value}
        onChange={(e) => onSlide(factor.id, Number(e.target.value))}
        aria-label={`因子强度 ${factor.label}`}
      />
      <p className="sandbox-factor-source">{factor.source}</p>
    </li>
  ));

  return (
    <section className="factor-sandbox" data-factor-sandbox={state.verdict} aria-label="报告因子沙盘">
      <header className="section-line-heading">
        <div>
          <span>Factor sandbox / G-04 · 确定性推演 · 可复现</span>
          <h2>调节影响因子，实时看结论如何移动</h2>
        </div>
        <small>权重来自分析支撑度 · 拖动即时重算</small>
      </header>
      <p className="phase-slot-note">
        每个因子的权重来自分析的支撑度；拖动强度即时重算（Layer 1 确定性传播，非伪模拟）。要真正重跑推理，用下方的深度重分析。
      </p>

      <div className="sandbox-outcome" data-sandbox-verdict={state.verdict}>
        <div className="sandbox-meter" role="meter" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
          <span style={{ width: `${percent}%` }} />
          <i style={{ left: `${state.flipThreshold * 100}%` }} aria-hidden />
        </div>
        <p>
          倾向得分 <b>{percent}%</b> · 结论：<b>{state.verdict === "proceed" ? "推进" : "按住/再等等"}</b>
          {busy && <em> · 重算中…</em>}
        </p>
      </div>

      {error && <p role="alert" className="sandbox-error-note">{error}</p>}

      {canGraph && (
        <div className="sandbox-view-switch" role="group" aria-label="沙盘视图切换">
          <button
            type="button"
            className="text-action"
            aria-pressed={showGraph}
            onClick={() => setViewMode("graph")}
          >
            图视图<span aria-hidden="true">◇</span>
          </button>
          <button
            type="button"
            className="text-action"
            aria-pressed={!showGraph}
            onClick={() => setViewMode("list")}
          >
            列表视图<span aria-hidden="true">≡</span>
          </button>
        </div>
      )}

      {showGraph ? (
        <>
          <FactorGraphCanvas
            state={state}
            selectedFactorId={selectedFactor?.id ?? null}
            onSelectFactor={setSelectedFactorId}
            busy={busy}
          />
          {selectedFactor ? (
            <div className="factor-graph-inspector" data-factor-inspector={selectedFactor.id}>
              <div className="sandbox-factor-head">
                <b>{selectedFactor.label}</b>
                <span className="sandbox-factor-tag">
                  {directionTag(selectedFactor.direction)} · 权重 {selectedFactor.weight.toFixed(2)}
                </span>
                <button
                  type="button"
                  className="sandbox-remove"
                  onClick={() => onRemove(selectedFactor.id)}
                  aria-label={`移除因子 ${selectedFactor.label}`}
                >
                  移除
                </button>
              </div>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={selectedFactor.value}
                onChange={(e) => onSlide(selectedFactor.id, Number(e.target.value))}
                aria-label={`因子强度 ${selectedFactor.label}`}
              />
              <p className="sandbox-factor-source">{selectedFactor.source}</p>
            </div>
          ) : (
            <p className="phase-slot-note">点击图中任一因子节点以调节其强度。</p>
          )}
        </>
      ) : (
        <>
          <ol className="sandbox-factors">{factorRows}</ol>

          {state.influences.length > 0 && (
            <div className="sandbox-influences">
              <h4>因子间因果链（来自分析检索，确定性收编——非编造）</h4>
              <ul>
                {state.influences.map((edge) => (
                  <li key={`${edge.from}-${edge.to}`} data-influence-polarity={edge.polarity}>
                    <b>{edge.fromLabel}</b>
                    <span className="sandbox-edge-arrow">{edge.polarity === "-" ? "→（抑制）" : "→（助推）"}</span>
                    <b>{edge.toLabel}</b>
                    {edge.note && <em>：{edge.note}</em>}
                  </li>
                ))}
              </ul>
              <p className="phase-slot-note">
                拖动上游因子时，偏离会沿因果链传导到下游因子（多级传播，有界迭代）。
              </p>
            </div>
          )}
        </>
      )}

      {state.topDrivers.length > 0 && (
        <div className="sandbox-drivers">
          <h4>最敏感的驱动因子（改动它们最能翻转结论）</h4>
          <ol>
            {state.topDrivers.map((driver) => (
              <li key={driver.nodeId}>
                <b>{driver.label}</b>：影响 {(driver.scoreDelta * 100).toFixed(1)} 分
                {driver.flipValue != null && (
                  <em>（当其强度跨过 {Math.round(driver.flipValue * 100)}% 时结论翻转）</em>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}

      <div className="sandbox-actions">
        <button type="button" className="secondary-action small" onClick={reset} disabled={!dirty || busy}>
          <span>恢复基线</span>
        </button>
        <button type="button" className="primary-action small" onClick={() => void deepReanalyze()}>
          <span>用当前假设发起深度重分析</span>
        </button>
      </div>
      {deepStatus && <p className="sandbox-deep-status" role="status">{deepStatus}</p>}
    </section>
  );
}
