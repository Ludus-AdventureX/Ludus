"use client";

import { FormEvent, KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";

import { DecisionHealthBar } from "@/components/shell/DecisionHealthBar";
import { AnalysisLaunchPanel } from "@/components/shell/views/AnalysisLaunchPanel";
import { PortfolioPanel } from "@/components/shell/views/PortfolioPanel";
import {
  CaseApiError,
  confirmCandidate,
  fetchCandidates,
  fetchCaseDetail,
  postCaseMessage,
  rejectCandidate,
  statementTypeLabels,
  summarizeProposedPatch,
  type CandidateView,
  type CaseDetailView
} from "@/lib/shell/caseData";

// Look V7 `#view-workspace` — the live Q (问题) workspace. The ledger composer
// posts real case messages (assistant reply + candidate extraction), the
// candidate redline confirms/rejects into the canonical dossier, and the folio
// mirrors GET /cases/{id} (question, versions, argument nodes). Without the
// tenant workspace anchor (?ws=) every read stays an honest gap — nothing here
// fabricates case, evidence or run state.

type WorkspaceViewProps = {
  decisionCaseId: string;
  /** Tenant workspace anchor; null = reads stay gap (Phase 0 posture). */
  workspaceId?: string | null;
};

type LedgerNote =
  | { kind: "human"; text: string; time: string }
  | { kind: "system"; text: string; patchSummary: string; time: string };

function now(): string {
  return new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

const nodeTypeLabels: Record<string, string> = {
  claim: "问题",
  support: "支持",
  counter: "反对",
  assumption: "假设",
  risk: "风险"
};

export function WorkspaceView({ decisionCaseId, workspaceId = null }: WorkspaceViewProps) {
  const [caseDetail, setCaseDetail] = useState<CaseDetailView | null>(null);
  const [caseError, setCaseError] = useState("");
  const [notes, setNotes] = useState<LedgerNote[]>([]);
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [composerNotice, setComposerNotice] = useState("");
  const [candidates, setCandidates] = useState<CandidateView[]>([]);
  const [busyCandidateId, setBusyCandidateId] = useState<string | null>(null);
  const [candidateNotice, setCandidateNotice] = useState("");
  const noteInput = useRef<HTMLTextAreaElement>(null);
  const formRef = useRef<HTMLFormElement>(null);

  const refreshCase = useCallback(async () => {
    if (!workspaceId) return;
    try {
      setCaseDetail(await fetchCaseDetail(workspaceId, decisionCaseId));
      setCaseError("");
    } catch (error) {
      setCaseError(error instanceof CaseApiError ? error.message : "读取决策项目失败。");
    }
  }, [workspaceId, decisionCaseId]);

  const refreshCandidates = useCallback(async () => {
    if (!workspaceId) return;
    try {
      setCandidates(await fetchCandidates(workspaceId, decisionCaseId));
    } catch {
      // The redline panel simply stays empty; the ledger reply already told
      // the human whether extraction produced a candidate.
    }
  }, [workspaceId, decisionCaseId]);

  useEffect(() => {
    void refreshCase();
    void refreshCandidates();
  }, [refreshCase, refreshCandidates]);

  const submitNote = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const text = draft.trim();
    if (!workspaceId || isSending) return;
    if (!text) {
      setComposerNotice("先写下一条判断、担忧或问题。");
      noteInput.current?.focus();
      return;
    }
    setIsSending(true);
    setComposerNotice("");
    setNotes((prev) => [...prev, { kind: "human", text, time: now() }]);
    setDraft("");
    try {
      const result = await postCaseMessage(workspaceId, decisionCaseId, text);
      setNotes((prev) => [
        ...prev,
        {
          kind: "system",
          text: result.assistantMessage,
          patchSummary: summarizeProposedPatch(result.proposedPatch),
          time: now()
        }
      ]);
      if (result.candidateRevisionId) await refreshCandidates();
    } catch (error) {
      setComposerNotice(
        error instanceof CaseApiError ? `系统回应失败：${error.message}` : "系统回应失败，请稍后重试。"
      );
    } finally {
      setIsSending(false);
      noteInput.current?.focus();
    }
  };

  const onComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      formRef.current?.requestSubmit();
    }
  };

  const reviewCandidate = async (candidate: CandidateView, decision: "confirm" | "reject") => {
    if (!workspaceId || busyCandidateId) return;
    setBusyCandidateId(candidate.candidateRevisionId);
    setCandidateNotice("");
    try {
      if (decision === "confirm") {
        const outcome = await confirmCandidate(workspaceId, decisionCaseId, candidate);
        setCandidateNotice(
          outcome.caseVersion
            ? `已写入正式档案：DossierVersion v${outcome.dossierVersion} · CaseVersion v${outcome.caseVersion}`
            : `已写入正式档案：DossierVersion v${outcome.dossierVersion}`
        );
      } else {
        await rejectCandidate(workspaceId, decisionCaseId, candidate.candidateRevisionId);
        setCandidateNotice("候选已拒绝；正式档案未改动。");
      }
      await Promise.all([refreshCase(), refreshCandidates()]);
    } catch (error) {
      setCandidateNotice(
        error instanceof CaseApiError ? `候选处理失败：${error.message}` : "候选处理失败，请稍后重试。"
      );
    } finally {
      setBusyCandidateId(null);
    }
  };

  const pendingCandidates = candidates.filter((candidate) => candidate.status === "pending");
  const confirmedNodes = (caseDetail?.argumentNodes ?? []).filter(
    (node) => node.status === "confirmed" && node.type !== "claim"
  );
  const coordinate = caseDetail ? `Q-${String(caseDetail.caseVersion).padStart(2, "0")}` : "Q-—";
  const coordinateStatus = !workspaceId
    ? "档案未接入"
    : caseDetail
      ? `CaseVersion v${caseDetail.caseVersion} · Dossier v${caseDetail.confirmedDossierVersion}`
      : caseError
        ? "档案读取失败"
        : "正在读取档案…";

  return (
    <section className="view is-active" id="view-workspace" data-view-panel="workspace" aria-labelledby="workspace-view-title">
      <header className="view-intro workspace-intro">
        <div className="intro-coordinate"><span>{coordinate}</span><i /><small>{coordinateStatus}</small></div>
        <div className="intro-grid">
          <div>
            <p className="eyebrow">今天要看清的，不是答案，而是下注条件</p>
            <h1 id="workspace-view-title">{caseDetail ? caseDetail.decisionQuestion : `决策项目 ${decisionCaseId}`}</h1>
            <p className="intro-copy">
              {caseDetail
                ? "写下判断、担忧或追问；系统回应并提炼候选，进入正式档案的内容始终由你确认。"
                : workspaceId
                  ? caseError || "正在读取决策项目档案…"
                  : "缺少工作区锚点（URL 未携带 ?ws=），问题工作区保持骨架展示，不伪造档案数据。"}
            </p>
          </div>
          <div className="intro-actions">
            <PortfolioPanel {...(workspaceId ? { workspaceId } : {})} />
            <AnalysisLaunchPanel
              {...(workspaceId ? { workspaceId } : {})}
              decisionCaseId={decisionCaseId}
            />
          </div>
        </div>
      </header>

      <div className="workspace-grid">
        <article className="ledger-sheet" aria-labelledby="workspace-ledger-title">
          <header className="sheet-heading">
            <div>
              <span className="sheet-index">推演札记 / {notes.length > 0 ? String(notes.length).padStart(2, "0") : "—"}</span>
              <h2 id="workspace-ledger-title">人的推演台</h2>
            </div>
            <p><i className="human-dot" /> 只有你确认的内容才会进入正式档案</p>
          </header>

          {workspaceId && (
            <form ref={formRef} className="ledger-composer" id="noteForm" onSubmit={submitNote}>
              <div className="composer-topline">
                <span>新札记</span>
              </div>
              <label className="sr-only" htmlFor="noteInput">写下你的判断、担忧、直觉或问题</label>
              <textarea
                ref={noteInput}
                id="noteInput"
                rows={3}
                value={draft}
                onChange={(event) => { setDraft(event.target.value); setComposerNotice(""); }}
                onKeyDown={onComposerKeyDown}
                placeholder="写下你对方向和取舍的判断……"
                disabled={isSending}
              />
              <div className="composer-actions">
                <span className="composer-hint">Ctrl / ⌘ + Enter</span>
                <button type="submit" className="commit-note" disabled={isSending}>
                  {isSending ? "系统整理中…" : <>记入札记 <span>↗</span></>}
                </button>
              </div>
              {composerNotice && <p className="draft-notice" role="status">{composerNotice}</p>}
            </form>
          )}

          <div className="ledger-body" id="ledgerBody">
            {notes.length === 0 && (
              <DecisionHealthBar />
            )}
            {notes.map((note, index) =>
              note.kind === "human" ? (
                <article key={index} className="ledger-note human-note">
                  <div className="note-margin">
                    <span className="author-glyph">人</span>
                    <b>你的札记</b>
                    <time>{note.time}</time>
                  </div>
                  <div className="note-content">
                    <span className="note-kind">札记 · 已发送</span>
                    <p>{note.text}</p>
                  </div>
                </article>
              ) : (
                <article key={index} className="ledger-note system-note">
                  <div className="note-margin">
                    <span className="author-glyph">析</span>
                    <b>系统回应</b>
                    <time>{note.time}</time>
                  </div>
                  <div className="note-content">
                    <span className="note-kind">回应 · 非结论</span>
                    <p>{note.text}</p>
                    {note.patchSummary && (
                      <div className="note-actions">
                        <span>候选提炼：{note.patchSummary}（待你确认）</span>
                      </div>
                    )}
                  </div>
                </article>
              )
            )}
            {isSending && (
              <article className="ledger-note system-note" aria-live="polite">
                <div className="note-margin">
                  <span className="author-glyph">析</span>
                  <b>系统回应</b>
                </div>
                <div className="note-content">
                  <span className="note-kind">正在整理…</span>
                  <p>系统正在回应并尝试提炼候选条目。</p>
                </div>
              </article>
            )}

            {pendingCandidates.map((candidate) => (
              <article key={candidate.candidateRevisionId} className="candidate-redline">
                <div className="redline-original">
                  <span>系统提炼 · 候选</span>
                  <p>基线 Dossier v{candidate.baseDossierVersion}{candidate.baseCaseVersion ? ` · Case v${candidate.baseCaseVersion}` : ""}</p>
                </div>
                <div className="redline-arrow" aria-hidden="true">→</div>
                <div className="redline-extract">
                  <span>拟写入正式档案</span>
                  {candidate.proposals.map((proposal, index) => (
                    <p key={index}>
                      <b>{statementTypeLabels[String(proposal.entry?.statementType ?? "")] ?? String(proposal.entry?.statementType ?? "条目")}</b>
                      {" · "}
                      {String(proposal.entry?.content ?? "")}
                    </p>
                  ))}
                </div>
                <div className="redline-actions">
                  <button
                    type="button"
                    className="approve"
                    disabled={busyCandidateId === candidate.candidateRevisionId}
                    onClick={() => void reviewCandidate(candidate, "confirm")}
                  >
                    写入档案
                  </button>
                  <button
                    type="button"
                    disabled={busyCandidateId === candidate.candidateRevisionId}
                    onClick={() => void reviewCandidate(candidate, "reject")}
                  >
                    拒绝
                  </button>
                </div>
              </article>
            ))}
            {candidateNotice && <p className="draft-notice" role="status">{candidateNotice}</p>}
          </div>
        </article>

        <aside className="folio-peek" aria-label="当前案例摘要">
          <div className="folio-question">
            <span>{coordinate} · OWNER / USER</span>
            <p>
              {caseDetail
                ? caseDetail.decisionQuestion
                : "档案折页将在读取 Case 只读 API 后展示问题与计数；空档案不显示伪造数字。"}
            </p>
          </div>
          {caseDetail && (
            <div className="folio-question" aria-label="已确认条目">
              <span>已确认条目 / {confirmedNodes.length}</span>
              {confirmedNodes.length === 0 ? (
                <p>正式档案暂无已确认条目；候选写入后会出现在这里。</p>
              ) : (
                confirmedNodes.map((node) => (
                  <p key={node.id}>
                    <b>{nodeTypeLabels[node.type] ?? node.type}</b>
                    {" · "}
                    {node.text}
                  </p>
                ))
              )}
            </div>
          )}
        </aside>
      </div>
    </section>
  );
}
