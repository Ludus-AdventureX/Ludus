"use client";

// Deliberation board (CCR-20260804-DELIB-01, Wave 3): the council control
// surface on the G page. Creation (subjective factor declarations), live
// transcript (SSE with Last-Event-ID reconnect), intervention console,
// nomination confirmation cards (never auto-activated), proposal ledger and
// the outcome panel. Honest states everywhere: loading / empty / error /
// awaiting_user / complete; fixture runs carry the fixture marker.

import { useCallback, useEffect, useRef, useState } from "react";

import { DeliberationGraph } from "./DeliberationGraph";

import {
  DeliberationClientError,
  createDeliberation,
  decideNomination,
  decideProposal,
  getDeliberation,
  getDeliberationOutcome,
  listDeliberationMessages,
  listDeliberations,
  postDeliberationIntervention,
  subscribeDeliberationEvents,
  type DeliberationMessageView,
  type DeliberationOutcomeView,
  type DeliberationRunDetailView,
  type SubjectiveFactorDeclaration
} from "@/lib/api/deliberation";

export type DeliberationBoardProps = {
  workspaceId?: string | null;
  decisionCaseId?: string;
  fetchImpl?: typeof fetch;
};

type BoardPhase = "loading" | "empty" | "basis-empty" | "error" | "run";

const SPEAKER_LABELS: Record<DeliberationMessageView["speaker"], string> = {
  witness: "持证人",
  moderator: "主持",
  user: "你"
};

const STATUS_LABELS: Record<DeliberationRunDetailView["status"], string> = {
  preparing: "准备中",
  running: "推演中",
  awaiting_user: "等待你的决策",
  complete: "已裁决",
  cancelled: "已取消"
};

function graphCapable(): boolean {
  // ReactFlow needs ResizeObserver; jsdom keeps the ledger list fallback.
  return typeof window !== "undefined" && typeof window.ResizeObserver === "function";
}

export function DeliberationBoard({
  workspaceId = null,
  decisionCaseId,
  fetchImpl
}: DeliberationBoardProps) {
  const [phase, setPhase] = useState<BoardPhase>("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const [run, setRun] = useState<DeliberationRunDetailView | null>(null);
  const [messages, setMessages] = useState<DeliberationMessageView[]>([]);
  const [outcome, setOutcome] = useState<DeliberationOutcomeView | null>(null);
  const [busy, setBusy] = useState(false);
  // Creation form
  const [maxRounds, setMaxRounds] = useState(3);
  const [declarations, setDeclarations] = useState<SubjectiveFactorDeclaration[]>([]);
  const [draftLabel, setDraftLabel] = useState("");
  const [draftStatement, setDraftStatement] = useState("");
  const [draftStrength, setDraftStrength] = useState(0.6);
  const [draftDirection, setDraftDirection] = useState<"supporting" | "opposing" | "neutral">("supporting");
  // Intervention console
  const [interventionText, setInterventionText] = useState("");
  const [challengeTargetId, setChallengeTargetId] = useState("");
  // Nomination confirmation form
  const [nominationFor, setNominationFor] = useState<string | null>(null);
  const [nominationLabel, setNominationLabel] = useState("");
  const [nominationStatement, setNominationStatement] = useState("");
  const [nominationStrength, setNominationStrength] = useState(0.6);
  const canGraph = graphCapable();
  const refreshSeq = useRef(0);

  const fetcher = fetchImpl ?? fetch;

  const refreshRun = useCallback(
    async (runId: string) => {
      if (!workspaceId) return;
      const seq = ++refreshSeq.current;
      try {
        const detail = await getDeliberation(workspaceId, runId, fetcher);
        if (seq !== refreshSeq.current) return;
        setRun(detail);
        const transcript = await listDeliberationMessages(workspaceId, runId, fetcher);
        if (seq !== refreshSeq.current) return;
        setMessages(transcript.items);
        if (detail.status === "complete") {
          const result = await getDeliberationOutcome(workspaceId, runId, fetcher).catch(() => null);
          if (seq !== refreshSeq.current) return;
          setOutcome(result);
        } else {
          setOutcome(null);
        }
      } catch (error) {
        if (seq !== refreshSeq.current) return;
        setErrorMessage(error instanceof DeliberationClientError ? error.message : "议会读取失败。");
      }
    },
    [workspaceId, fetcher]
  );

  // Initial load: latest council for the case (honest empty when none).
  useEffect(() => {
    if (!workspaceId || !decisionCaseId) return;
    let cancelled = false;
    void (async () => {
      try {
        const anchors = await listDeliberations(workspaceId, decisionCaseId, fetcher);
        if (cancelled) return;
        if (anchors.length === 0) {
          setPhase("empty");
          return;
        }
        setPhase("run");
        await refreshRun(anchors[0].id);
      } catch (error) {
        if (cancelled) return;
        setPhase("error");
        setErrorMessage(error instanceof DeliberationClientError ? error.message : "议会读取失败。");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [workspaceId, decisionCaseId, fetcher, refreshRun]);

  // SSE: only while the council can still move, and only where the runtime
  // actually has EventSource (jsdom degrades to manual refresh — honest, no
  // fabricated streams).
  useEffect(() => {
    if (!workspaceId || !run) return;
    if (run.status === "complete" || run.status === "cancelled") return;
    if (typeof window === "undefined" || typeof window.EventSource !== "function") return;
    const unsubscribe = subscribeDeliberationEvents(workspaceId, run.id, () => {
      void refreshRun(run.id);
    });
    return unsubscribe;
  }, [workspaceId, run?.id, run?.status, refreshRun]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!workspaceId || !decisionCaseId) return null;

  const createCouncil = async () => {
    setBusy(true);
    setErrorMessage("");
    try {
      const anchor = await createDeliberation(
        workspaceId,
        decisionCaseId,
        { subjectiveFactors: declarations, maxRounds },
        fetcher
      );
      setPhase("run");
      await refreshRun(anchor.id);
    } catch (error) {
      if (error instanceof DeliberationClientError && error.code === "DELIBERATION_BASIS_EMPTY") {
        setPhase("basis-empty");
      } else {
        setErrorMessage(error instanceof DeliberationClientError ? error.message : "创建议会失败。");
      }
    } finally {
      setBusy(false);
    }
  };

  const addDraftDeclaration = () => {
    if (!draftLabel.trim() || !draftStatement.trim()) return;
    setDeclarations((current) => [
      ...current,
      {
        label: draftLabel.trim(),
        statement: draftStatement.trim(),
        strength: draftStrength,
        direction: draftDirection
      }
    ]);
    setDraftLabel("");
    setDraftStatement("");
    setDraftStrength(0.6);
    setDraftDirection("supporting");
  };

  const sendIntervention = async (kind: "interject" | "challenge_witness" | "reopen_round") => {
    if (!run) return;
    setBusy(true);
    setErrorMessage("");
    try {
      if (kind === "interject") {
        if (!interventionText.trim()) return;
        await postDeliberationIntervention(workspaceId, run.id, { kind, text: interventionText.trim() }, fetcher);
        setInterventionText("");
      } else if (kind === "challenge_witness") {
        if (!interventionText.trim() || !challengeTargetId) return;
        await postDeliberationIntervention(
          workspaceId,
          run.id,
          { kind, text: interventionText.trim(), targetFactorId: challengeTargetId },
          fetcher
        );
        setInterventionText("");
      } else {
        await postDeliberationIntervention(workspaceId, run.id, { kind }, fetcher);
      }
      await refreshRun(run.id);
    } catch (error) {
      setErrorMessage(error instanceof DeliberationClientError ? error.message : "介入失败。");
    } finally {
      setBusy(false);
    }
  };

  const confirmNomination = async (nominationId: string, decision: "confirmed" | "rejected") => {
    if (!run) return;
    setBusy(true);
    setErrorMessage("");
    try {
      if (decision === "confirmed") {
        if (!nominationStatement.trim()) return;
        await decideNomination(
          workspaceId,
          run.id,
          nominationId,
          "confirmed",
          {
            label: nominationLabel.trim() || "未命名主观因子",
            statement: nominationStatement.trim(),
            strength: nominationStrength
          },
          fetcher
        );
      } else {
        await decideNomination(workspaceId, run.id, nominationId, "rejected", undefined, fetcher);
      }
      setNominationFor(null);
      setNominationLabel("");
      setNominationStatement("");
      setNominationStrength(0.6);
      await refreshRun(run.id);
    } catch (error) {
      setErrorMessage(error instanceof DeliberationClientError ? error.message : "提名决策失败。");
    } finally {
      setBusy(false);
    }
  };

  const onProposalDecision = async (proposalId: string, decision: "accepted" | "rejected") => {
    if (!run) return;
    setBusy(true);
    setErrorMessage("");
    try {
      await decideProposal(workspaceId, run.id, proposalId, decision, fetcher);
      await refreshRun(run.id);
    } catch (error) {
      setErrorMessage(error instanceof DeliberationClientError ? error.message : "提议决策失败。");
    } finally {
      setBusy(false);
    }
  };

  if (phase === "loading") {
    return (
      <section className="deliberation-board" data-deliberation-board="loading" aria-label="推演棋盘">
        <p className="phase-slot-note" role="status">正在读取推演议会…</p>
      </section>
    );
  }

  if (phase === "basis-empty") {
    return (
      <section className="deliberation-board" data-deliberation-board="basis-empty" aria-label="推演棋盘">
        <p className="phase-slot-note" role="status">
          推演议会尚未开放——该 Case 尚无分析因子基线；完成一次深度分析后即可开议会。
        </p>
      </section>
    );
  }

  if (phase === "error") {
    return (
      <section className="deliberation-board" data-deliberation-board="error" aria-label="推演棋盘">
        <p className="phase-slot-note" role="alert">{errorMessage || "议会读取失败。"}</p>
      </section>
    );
  }

  if (phase === "empty") {
    return (
      <section className="deliberation-board" data-deliberation-board="create" aria-label="推演棋盘">
        <header>
          <span className="eyebrow">推演议会 · 因子持证人 · 引擎裁决</span>
          <h3>开一场议会：每个因子一个持证人，主观判断可署名入场</h3>
          <p className="phase-slot-note">
            客观因子自动取自分析基线；你的主观判断（直觉/内部数据/对手反应）以 assumed 身份 + Human
            署名进图，永不冒充证据。数值一律由确定性引擎计算——议会不输出任何概率。
          </p>
        </header>

        <div className="deliberation-declare">
          <h4>可选：声明主观因子</h4>
          <div className="deliberation-declare-row">
            <input
              value={draftLabel}
              onChange={(event) => setDraftLabel(event.target.value)}
              placeholder="因子名称（如：对手降价意愿）"
              aria-label="主观因子名称"
            />
            <select
              value={draftDirection}
              onChange={(event) => setDraftDirection(event.target.value as "supporting" | "opposing" | "neutral")}
              aria-label="主观因子方向"
            >
              <option value="supporting">支撑推进</option>
              <option value="opposing">反向拉扯</option>
              <option value="neutral">中性</option>
            </select>
          </div>
          <textarea
            value={draftStatement}
            onChange={(event) => setDraftStatement(event.target.value)}
            placeholder="判断陈述（为什么这样认为）"
            aria-label="主观因子陈述"
          />
          <label className="deliberation-strength">
            声明强度 {Math.round(draftStrength * 100)}%
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={draftStrength}
              onChange={(event) => setDraftStrength(Number(event.target.value))}
              aria-label="主观因子强度"
            />
          </label>
          <button type="button" className="secondary-action small" onClick={addDraftDeclaration} disabled={busy}>
            <span>加入声明</span>
          </button>
          {declarations.length > 0 && (
            <ul className="deliberation-declared">
              {declarations.map((declaration, index) => (
                <li key={`${declaration.label}-${index}`} data-declared-factor={declaration.label}>
                  <b>{declaration.label}</b>
                  <small>{`${declaration.direction ?? "supporting"} · 强度 ${Math.round(declaration.strength * 100)}% · assumed（你的署名）`}</small>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="deliberation-create-row">
          <label>
            轮次预算
            <select value={maxRounds} onChange={(event) => setMaxRounds(Number(event.target.value))} aria-label="轮次预算">
              <option value={2}>2 轮</option>
              <option value={3}>3 轮</option>
              <option value={4}>4 轮</option>
              <option value={5}>5 轮（上限）</option>
            </select>
          </label>
          <button type="button" className="primary-action small" onClick={() => void createCouncil()} disabled={busy}>
            <span>{busy ? "正在创建议会…" : "创建议会并开始推演"}</span>
          </button>
        </div>
        {errorMessage && <p role="alert" className="phase-slot-note">{errorMessage}</p>}
      </section>
    );
  }

  if (!run) return null;

  const fixtureMark = run.originModes.includes("fixture");
  const closed = run.status === "complete" || run.status === "cancelled";

  return (
    <section className="deliberation-board" data-deliberation-board="run" data-deliberation-status={run.status} aria-label="推演棋盘">
      <header>
        <span className="eyebrow">推演议会 · 因子持证人 · 引擎裁决{fixtureMark ? " · fixture" : ""}</span>
        <h3>
          {STATUS_LABELS[run.status]} · 第 {run.currentRoundSeq} / {run.maxRounds} 轮
          {busy && <em> · 处理中…</em>}
        </h3>
        <p className="phase-slot-note">
          主持智能体组织轮次，持证人为各自因子辩护；一切数值由确定性引擎裁决。议会不代表精确预测。
        </p>
      </header>

      {errorMessage && <p role="alert" className="phase-slot-note">{errorMessage}</p>}

      {canGraph ? (
        <DeliberationGraph
          factors={run.factors}
          outcome={outcome}
          statusText={`${STATUS_LABELS[run.status]} · 第 ${run.currentRoundSeq} 轮`}
        />
      ) : (
        <ul className="deliberation-factor-ledger" aria-label="议会因子账本">
          {run.factors.map((factor) => (
            <li key={factor.id} data-provenance={factor.provenance} data-board-node="factor">
              <b>{factor.label}</b>
              <small>
                {factor.provenance === "subjective"
                  ? `主观 · ${factor.evidenceStatus ?? "assumed"} · Human 署名`
                  : "客观 · 证据基线"}
                {` · 强度 ${Math.round(factor.strength * 100)}%`}
              </small>
            </li>
          ))}
        </ul>
      )}

      {run.pendingNominations.length > 0 && (
        <div className="deliberation-nominations">
          <h4>主持提名：请补位主观判断（确认后才生效）</h4>
          {run.pendingNominations.map((nomination) => (
            <div key={nomination.id} className="deliberation-nomination" data-nomination-id={nomination.id}>
              <p>{nomination.rationale}</p>
              {nominationFor === nomination.id ? (
                <>
                  <input
                    value={nominationLabel}
                    onChange={(event) => setNominationLabel(event.target.value)}
                    placeholder="因子名称"
                    aria-label="提名副因子名称"
                  />
                  <textarea
                    value={nominationStatement}
                    onChange={(event) => setNominationStatement(event.target.value)}
                    placeholder="你的判断陈述（必填）"
                    aria-label="提名判断陈述"
                  />
                  <label className="deliberation-strength">
                    声明强度 {Math.round(nominationStrength * 100)}%
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.05}
                      value={nominationStrength}
                      onChange={(event) => setNominationStrength(Number(event.target.value))}
                      aria-label="提名声明强度"
                    />
                  </label>
                  <div className="deliberation-nomination-actions">
                    <button
                      type="button"
                      className="primary-action small"
                      onClick={() => void confirmNomination(nomination.id, "confirmed")}
                      disabled={busy || !nominationStatement.trim()}
                    >
                      <span>确认并声明</span>
                    </button>
                    <button
                      type="button"
                      className="secondary-action small"
                      onClick={() => setNominationFor(null)}
                      disabled={busy}
                    >
                      <span>暂不</span>
                    </button>
                  </div>
                </>
              ) : (
                <div className="deliberation-nomination-actions">
                  <button
                    type="button"
                    className="primary-action small"
                    onClick={() => {
                      setNominationFor(nomination.id);
                      setNominationLabel(nomination.targetDescription);
                    }}
                    disabled={busy}
                  >
                    <span>我来声明</span>
                  </button>
                  <button
                    type="button"
                    className="secondary-action small"
                    onClick={() => void confirmNomination(nomination.id, "rejected")}
                    disabled={busy}
                  >
                    <span>拒绝提名</span>
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {run.pendingProposals.length > 0 && (
        <div className="deliberation-proposals">
          <h4>持证人提议（采纳后引擎立即重算）</h4>
          <ul>
            {run.pendingProposals.map((proposal) => (
              <li key={proposal.id} data-proposal-id={proposal.id}>
                <small>
                  {proposal.kind === "factor_strength" ? "因子强度调整" : proposal.kind}
                  {typeof proposal.after?.strength === "number" &&
                    ` → ${Math.round(Number(proposal.after.strength) * 100)}%`}
                  {proposal.enginePreview?.outcomeScore != null &&
                    ` · 引擎预览倾向 ${Math.round(Number(proposal.enginePreview.outcomeScore) * 100)}%（${proposal.enginePreview.verdict === "proceed" ? "推进" : "按住"}）`}
                </small>
                <div className="deliberation-proposal-actions">
                  <button
                    type="button"
                    className="primary-action small"
                    onClick={() => void onProposalDecision(proposal.id, "accepted")}
                    disabled={busy}
                  >
                    <span>采纳</span>
                  </button>
                  <button
                    type="button"
                    className="secondary-action small"
                    onClick={() => void onProposalDecision(proposal.id, "rejected")}
                    disabled={busy}
                  >
                    <span>驳回</span>
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="deliberation-transcript" aria-label="议会实况转录">
        <h4>实况转录（{messages.length} 条）</h4>
        <ol>
          {messages.map((message) => (
            <li key={message.id} data-message-kind={message.kind} data-speaker={message.speaker}>
              <span className="deliberation-speaker">
                {SPEAKER_LABELS[message.speaker]}
                {message.stampActor === "human" ? " · Human" : ""}
                {message.originMode === "fixture" ? " · fixture" : ""}
              </span>
              <p>{message.content}</p>
            </li>
          ))}
        </ol>
      </div>

      {!closed && (
        <div className="deliberation-intervene">
          <h4>介入控制台</h4>
          <textarea
            value={interventionText}
            onChange={(event) => setInterventionText(event.target.value)}
            placeholder="插话，或选中某个因子发起质询…"
            aria-label="介入文本"
          />
          <div className="deliberation-intervene-actions">
            <button
              type="button"
              className="secondary-action small"
              onClick={() => void sendIntervention("interject")}
              disabled={busy || !interventionText.trim()}
            >
              <span>插话</span>
            </button>
            <select
              value={challengeTargetId}
              onChange={(event) => setChallengeTargetId(event.target.value)}
              aria-label="质询目标因子"
            >
              <option value="">选择质询对象…</option>
              {run.factors.map((factor) => (
                <option key={factor.id} value={factor.id}>{factor.label}</option>
              ))}
            </select>
            <button
              type="button"
              className="secondary-action small"
              onClick={() => void sendIntervention("challenge_witness")}
              disabled={busy || !interventionText.trim() || !challengeTargetId}
            >
              <span>质询该持证人</span>
            </button>
            <button
              type="button"
              className="secondary-action small"
              onClick={() => void sendIntervention("reopen_round")}
              disabled={busy}
            >
              <span>要求重开一轮</span>
            </button>
          </div>
        </div>
      )}

      {outcome && (
        <div className="deliberation-outcome" data-deliberation-outcome="ready">
          <h4>条件化预估（引擎投影 · 非概率）</h4>
          <p className="phase-slot-note">{outcome.disclaimer}</p>
          <ul className="deliberation-projections">
            {outcome.conditionProjections.map((projection, index) => (
              <li key={`${projection.acceptedProposalIds.length}-${index}`}>
                <b>
                  {projection.projection.verdict === "proceed" ? "推进" : "按住/再等等"}
                  {projection.projection.outcomeScore != null &&
                    ` · 倾向 ${Math.round(Number(projection.projection.outcomeScore) * 100)}%`}
                </b>
                <small>{projection.condition}</small>
              </li>
            ))}
          </ul>
          {outcome.flipConditions.length > 0 && (
            <div className="deliberation-flips">
              <h5>翻转条件</h5>
              <ul>
                {outcome.flipConditions.map((flip, index) => (
                  <li key={`${flip.factorId ?? index}`}>
                    {`${flip.label ?? flip.factorId ?? "因子"}：强度跨过 ${flip.flipValue != null ? Math.round(flip.flipValue * 100) : "?"}% 时结论翻转`}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {outcome.dissentLog.length > 0 && (
            <div className="deliberation-dissent">
              <h5>异议留档</h5>
              <ul>
                {outcome.dissentLog.map((dissent, index) => (
                  <li key={`${dissent.factorId ?? index}`}>
                    <b>{dissent.witnessLabel}</b>
                    <small>{dissent.originalStance}</small>
                    <small>{dissent.overturnedBasis}</small>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
