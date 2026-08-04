"use client";

// Task 13 sandbox workspace orchestrator (fills the sandbox-workspace slot).
// Decision-user-first: the default surface is the conditional recommendation
// + top-3 fragile conditions + one-condition stress test. The full causal
// model, graph review, scenarios and branches unfold progressively and never
// crowd the default surface. All simulation results come from the real
// SIM-02A run API; nothing is fabricated client-side.

import { useMemo, useRef, useState } from "react";

import { BranchTimeline } from "./BranchTimeline";
import { CausalCanvas } from "./CausalCanvas";
import { CurrentRecommendationSummary } from "./CurrentRecommendationSummary";
import { EdgeInspector } from "./EdgeInspector";
import { FragileConditionList } from "./FragileConditionList";
import { GraphConfirmationPanel, buildReviewItems } from "./GraphConfirmationPanel";
import { ImpactPathOverlay } from "./ImpactPathOverlay";
import { ImpactPathSummary } from "./ImpactPathSummary";
import { NodeInspector } from "./NodeInspector";
import { ScenarioControl } from "./ScenarioControl";
import { StressTestControl } from "./StressTestControl";
import { StressTestResult } from "./StressTestResult";
import { ValidationActionCTA } from "./ValidationActionCTA";
import {
  buildImpactPaths,
  interpretRunOutcome,
  type ImpactPath,
  type RunInterpretation,
  type TestedPoint,
} from "./interpret";
import {
  isGraphNotConfirmed,
  isIdempotencyConflict,
  isNetworkError,
  isNotConverged,
  isUniformNotFound,
  newRunIdempotencyKey,
  postSimulationRun,
} from "./runClient";
import type {
  CandidateRevision,
  ExperimentBranch,
  SandboxCaseData,
  ScenarioFrame,
} from "./types";

export type SandboxWorkspaceProps = {
  decisionCaseId: string;
  /** null = 没有任何真实档案输入（诚实空态，见 sandboxData.ts）。 */
  data: SandboxCaseData | null;
};

type RunState =
  | { phase: "idle" }
  | { phase: "running" }
  | { phase: "error"; message: string; retryable: boolean };

type LastOutcome = {
  interpretation: RunInterpretation;
  idempotencyReplay: boolean;
  conditionNodeId: string;
  testedValue: number;
  runId: string;
};

export function SandboxWorkspace({ decisionCaseId, data }: SandboxWorkspaceProps) {
  const [selectedConditionId, setSelectedConditionId] = useState<string | null>(
    data?.fragileConditions[0]?.nodeId ?? null,
  );
  const [workingValues, setWorkingValues] = useState<Record<string, number>>({});
  const [testedPoints, setTestedPoints] = useState<Record<string, TestedPoint[]>>({});
  const [runState, setRunState] = useState<RunState>({ phase: "idle" });
  const [lastOutcome, setLastOutcome] = useState<LastOutcome | null>(null);
  const [modelExpanded, setModelExpanded] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [locatedPath, setLocatedPath] = useState<ImpactPath | null>(null);
  const [confirmations, setConfirmations] = useState<Record<string, boolean>>(() => {
    const initial: Record<string, boolean> = {};
    for (const node of data?.graph.nodes ?? []) initial[node.id] = node.confirmation === "confirmed";
    for (const edge of data?.graph.edges ?? []) initial[edge.id] = edge.confirmation === "confirmed";
    return initial;
  });
  const [candidateRevisions, setCandidateRevisions] = useState<CandidateRevision[]>([]);
  const [branches, setBranches] = useState<ExperimentBranch[]>([]);
  const [secondaryOpen, setSecondaryOpen] = useState(false);
  // 网络失败重试复用同一 Idempotency-Key（同一运行意图幂等重放）。
  const pendingKey = useRef<string | null>(null);

  const condition = useMemo(
    () => data?.fragileConditions.find((entry) => entry.nodeId === selectedConditionId) ?? null,
    [data, selectedConditionId],
  );

  if (!data) {
    // 诚实空态：无真实报告/确认图/anchors 之前，沙盘不开放，也不伪造数据。
    return (
      <div className="pressure-mode" data-phase-slot="sandbox-workspace" data-sandbox-state="empty">
        <header className="view-intro sandbox-intro">
          <div className="intro-coordinate unknown-coordinate">
            <span>G-—</span>
            <i />
            <small>尚无可推演的判断</small>
          </div>
          <div className="intro-grid">
            <div>
              <p className="eyebrow">沙盘不预测未来，它暴露建议在何处失效</p>
              <h1 id="sandbox-view-title">压力测试尚未开放</h1>
            </div>
            <div className="intro-actions" />
          </div>
        </header>
        <nav className="fragile-index" aria-label="Fragile conditions">
          <button type="button" disabled aria-disabled="true">
            <span>—</span>
            <b>脆弱条件待生成</b>
            <small>需要真实报告与确认图</small>
          </button>
        </nav>
        <div className="pressure-layout">
          <article className="pressure-instrument">
            <header className="section-line-heading">
              <div>
                <span>Fragile condition / —</span>
                <h2>条件压力测试</h2>
              </div>
              <small>等待真实因果图</small>
            </header>
            <p className="pressure-question">
              压力测试尚未开放——需要一份已确认的正式因果图。完成深度分析后，在完整模型中审阅并确认全部节点与边，脆弱条件与压力测试即在此开放。
            </p>
            <p className="formal-gate-note" role="note">
              下一步：完成深度分析 → 展开完整模型 → 审阅确认全部节点与边 → 保存正式图版本。
              正式模拟始终由 API 校验图版本，前端不会伪造可用状态。
            </p>
          </article>
        </div>
      </div>
    );
  }

  const { recommendation, fragileConditions, graph, scenarioFrames, anchors } = data;
  const workingValue =
    condition == null
      ? null
      : (workingValues[condition.nodeId] ?? condition.baselineValue);
  const reviewOutstanding = buildReviewItems(graph, confirmations).length;
  const qualityGatePassed = reviewOutstanding === 0 && !graph.draft;
  const confirmedScenarios = scenarioFrames.filter((frame) => frame.confirmed);

  const setWorkingValue = (value: number) => {
    if (!condition) return;
    // 只写工作副本；绝不自动提交模拟。
    setWorkingValues((current) => ({ ...current, [condition.nodeId]: value }));
  };

  const applyScenario = (frame: ScenarioFrame) => {
    if (!condition) return;
    const adjusted = frame.conditionAdjustments?.[condition.nodeId];
    if (typeof adjusted === "number") setWorkingValue(adjusted);
  };

  const runStressTest = async (mode: "experimental" | "formal") => {
    if (!condition || workingValue == null) return;
    const idempotencyKey = pendingKey.current ?? newRunIdempotencyKey();
    pendingKey.current = idempotencyKey;
    setRunState({ phase: "running" });
    try {
      const outcome = await postSimulationRun({
        anchors,
        mode,
        nodeOverrides: { [condition.nodeId]: workingValue },
        idempotencyKey,
      });
      pendingKey.current = null;
      const history = testedPoints[condition.nodeId] ?? [];
      const interpretation = interpretRunOutcome({
        run: outcome.run,
        condition,
        testedValue: workingValue,
        recommendation,
        testedPoints: history,
      });
      setTestedPoints((current) => ({
        ...current,
        [condition.nodeId]: [
          ...history,
          {
            value: workingValue,
            flipped: interpretation.state === "flipped",
            simulationRunId: outcome.run.simulationRunId,
          },
        ],
      }));
      setLastOutcome({
        interpretation,
        idempotencyReplay: outcome.idempotencyReplay,
        conditionNodeId: condition.nodeId,
        testedValue: workingValue,
        runId: outcome.run.simulationRunId,
      });
      setRunState({ phase: "idle" });
    } catch (error) {
      if (isUniformNotFound(error)) {
        // 统一 404：不区分跨租户/跨图，不暗示资源是否存在。
        pendingKey.current = null;
        setRunState({
          phase: "error",
          message: "该因果图在当前工作区不可见（未找到）。",
          retryable: false,
        });
      } else if (isIdempotencyConflict(error)) {
        pendingKey.current = null;
        setRunState({
          phase: "error",
          message: "这次运行的幂等键已被不同的请求使用，请重新发起运行。",
          retryable: false,
        });
      } else if (isGraphNotConfirmed(error)) {
        pendingKey.current = null;
        setRunState({
          phase: "error",
          message: "正式模拟需要已确认的图版本（API 校验拒绝）。请先完成图审阅确认。",
          retryable: false,
        });
      } else if (isNotConverged(error)) {
        pendingKey.current = null;
        setRunState({
          phase: "error",
          message: "正式推演未收敛，结果已留档但不能作为判断依据。",
          retryable: false,
        });
      } else if (isNetworkError(error)) {
        // 保留幂等键：重试同一运行意图会得到服务端重放而非重复计算。
        setRunState({
          phase: "error",
          message: "网络中断。重试将复用同一 Idempotency-Key，不会重复计算。",
          retryable: true,
        });
      } else {
        pendingKey.current = null;
        setRunState({ phase: "error", message: "推演请求失败，请稍后再试。", retryable: true });
      }
    }
  };

  const saveBranch = () => {
    if (!lastOutcome) return;
    const conditionForBranch = fragileConditions.find(
      (entry) => entry.nodeId === lastOutcome.conditionNodeId,
    );
    if (!conditionForBranch) return;
    setBranches((current) => [
      ...current,
      {
        id: `branch-${current.length + 1}`,
        name: `${conditionForBranch.title} ${lastOutcome.testedValue} ${conditionForBranch.unit}`,
        conditionNodeId: lastOutcome.conditionNodeId,
        value: lastOutcome.testedValue,
        runId: lastOutcome.runId,
        summary: lastOutcome.interpretation.narrative,
      },
    ]);
  };

  const rollbackBranch = (branch: ExperimentBranch) => {
    // 非破坏性：只恢复工作副本与聚焦条件；分支列表不变。
    setSelectedConditionId(branch.conditionNodeId);
    setWorkingValues((current) => ({ ...current, [branch.conditionNodeId]: branch.value }));
  };

  const locatePath = (path: ImpactPath) => {
    setLocatedPath(path);
    setModelExpanded(true);
  };

  const highlightedNodeIds = new Set<string>(locatedPath?.steps.map((step) => step.nodeId) ?? []);
  const impactPaths =
    lastOutcome && condition
      ? buildImpactPaths(graph, lastOutcome.conditionNodeId, null, 3)
      : [];
  const selectedNode = graph.nodes.find((node) => node.id === selectedNodeId) ?? null;
  const selectedEdge = graph.edges.find((edge) => edge.id === selectedEdgeId) ?? null;
  const insufficient = lastOutcome?.interpretation.state === "insufficient";

  return (
    <div className="pressure-mode" data-phase-slot="sandbox-workspace" data-sandbox-state="ready">
      <header className="view-intro sandbox-intro">
        <div className="intro-coordinate">
          <span>G-01</span>
          <i />
          <small>条件压力测试</small>
        </div>
        <div className="intro-grid">
          <div>
            <p className="eyebrow">沙盘不预测未来，它暴露建议在何处失效</p>
            <h1 id="sandbox-view-title">
              {condition ? `「${condition.title}」变化时，当前建议还能成立吗？` : "条件压力测试"}
            </h1>
          </div>
          <div className="intro-actions">
            <button
              type="button"
              className="text-action"
              aria-expanded={modelExpanded}
              onClick={() => setModelExpanded((value) => !value)}
            >
              {modelExpanded ? "收起完整模型" : "展开完整模型"} <span aria-hidden="true">↗</span>
            </button>
            <button
              type="button"
              className="secondary-action"
              disabled={!qualityGatePassed}
              aria-disabled={!qualityGatePassed}
              title={
                qualityGatePassed
                  ? "以正式（formal）模式运行"
                  : "质量门未通过：完成图审阅确认并保存正式图版本后才能运行正式模拟"
              }
              onClick={() => runStressTest("formal")}
            >
              正式运行（formal）
            </button>
          </div>
        </div>
        {!qualityGatePassed ? (
          <p className="formal-gate-note" role="note">
            正式（formal）入口已禁用：{graph.draft ? "当前图仍是草稿；" : ""}
            {reviewOutstanding > 0 ? `${reviewOutstanding} 项图审阅未确认。` : ""}
            前端禁用只是反馈，正式运行始终由 API 校验兜底。
          </p>
        ) : null}
      </header>

      <CurrentRecommendationSummary recommendation={recommendation} />

      <FragileConditionList
        conditions={fragileConditions}
        selectedNodeId={selectedConditionId}
        onSelect={(nodeId) => {
          setSelectedConditionId(nodeId);
        }}
      />

      <div className="pressure-layout">
        {condition && workingValue != null ? (
          <StressTestControl
            condition={condition}
            value={workingValue}
            onChange={setWorkingValue}
            onReset={() => setWorkingValue(condition.baselineValue)}
            onRun={() => runStressTest("experimental")}
            running={runState.phase === "running"}
            confirmedScenarios={confirmedScenarios}
            onApplyScenario={applyScenario}
          />
        ) : null}

        {runState.phase === "error" ? (
          <div className="pressure-error" role="alert">
            <p>{runState.message}</p>
            {runState.retryable ? (
              <button type="button" onClick={() => runStressTest("experimental")}>
                重试本次运行
              </button>
            ) : null}
          </div>
        ) : null}

        {lastOutcome && lastOutcome.conditionNodeId === condition?.nodeId ? (
          <StressTestResult
            interpretation={lastOutcome.interpretation}
            idempotencyReplay={lastOutcome.idempotencyReplay}
            hardConstraints={graph.hardConstraints}
          />
        ) : null}
      </div>

      {condition && (insufficient || condition.evidenceStatus === "unknown") ? (
        <ValidationActionCTA
          condition={condition}
          created={candidateRevisions}
          onCreate={(revision) => setCandidateRevisions((current) => [...current, revision])}
          primary={insufficient}
        />
      ) : null}

      {lastOutcome && impactPaths.length > 0 ? (
        <ImpactPathSummary paths={impactPaths} onLocate={locatePath} />
      ) : null}

      {lastOutcome ? (
        <div className="intro-actions">
          <button type="button" className="secondary-action" onClick={saveBranch}>
            保存实验分支
          </button>
        </div>
      ) : null}

      {modelExpanded ? (
        <div className="model-mode" aria-labelledby="model-mode-title">
          <header className="model-header">
            <div>
              <span>G-01 · 因果关系</span>
              <h2 id="model-mode-title">完整因果模型</h2>
            </div>
            <button type="button" className="model-action" onClick={() => setModelExpanded(false)}>
              ← 返回压力测试
            </button>
          </header>
          <ImpactPathOverlay path={locatedPath} onClear={() => setLocatedPath(null)} />
          <CausalCanvas
            graph={graph}
            testedNodeId={selectedConditionId}
            highlightedNodeIds={highlightedNodeIds}
            selectedNodeId={selectedNodeId}
            selectedEdgeId={selectedEdgeId}
            onSelectNode={(nodeId) => {
              setSelectedNodeId(nodeId);
              setSelectedEdgeId(null);
            }}
            onSelectEdge={(edgeId) => {
              setSelectedEdgeId(edgeId);
              setSelectedNodeId(null);
            }}
          />
          {selectedNode ? (
            <NodeInspector
              node={selectedNode}
              confirmed={confirmations[selectedNode.id] === true}
              onConfirm={(id) => setConfirmations((current) => ({ ...current, [id]: true }))}
            />
          ) : null}
          {selectedEdge ? (
            <EdgeInspector
              edge={selectedEdge}
              fromNode={graph.nodes.find((node) => node.id === selectedEdge.from) ?? null}
              toNode={graph.nodes.find((node) => node.id === selectedEdge.to) ?? null}
              confirmed={confirmations[selectedEdge.id] === true}
              onConfirm={(id) => setConfirmations((current) => ({ ...current, [id]: true }))}
            />
          ) : null}
          <GraphConfirmationPanel
            graph={graph}
            confirmations={confirmations}
            onConfirm={(id) => setConfirmations((current) => ({ ...current, [id]: true }))}
            onBatchConfirm={(ids) =>
              setConfirmations((current) => {
                const next = { ...current };
                for (const id of ids) next[id] = true;
                return next;
              })
            }
          />
        </div>
      ) : null}

      <div className="sandbox-secondary">
        <button
          type="button"
          className="text-action"
          aria-expanded={secondaryOpen}
          onClick={() => setSecondaryOpen((value) => !value)}
        >
          情景与实验分支（次级流程）
        </button>
        {secondaryOpen ? (
          <>
            <ScenarioControl
              frames={scenarioFrames}
              onCreateScenarioVersion={(revision) =>
                setCandidateRevisions((current) => [...current, revision])
              }
            />
            <BranchTimeline branches={branches} onRollback={rollbackBranch} />
            {candidateRevisions.length > 0 ? (
              <ul className="candidate-revision-ledger" aria-label="全部候选修订">
                {candidateRevisions.map((revision, index) => (
                  <li key={index}>
                    <b>{revision.title}</b>
                    <small>{revision.kind === "validation_action" ? "验证行动" : "情景版本"} · 候选修订</small>
                  </li>
                ))}
              </ul>
            ) : null}
          </>
        ) : null}
      </div>
    </div>
  );
}
