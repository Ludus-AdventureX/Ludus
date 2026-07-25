"use client";

import { FormEvent, useRef, useState } from "react";

import {
  CaseCreateFlowError,
  createDecisionCase,
  navigateToCreatedCase
} from "@/lib/shell/createCase";

// Look V7 `#view-empty` frame for the case shell: question-first empty state.
// Deliberately no template card wall, no method gallery and no fabricated
// progress/evidence/run counters. Submit drives the real guest-backed create
// flow (csrf -> guest -> POST /cases) and opens the created case route.

const copy = {
  coordinate: "NEW-00",
  coordinateStatus: "尚未建立项目",
  eyebrow: "这里没有示例答案，也没有等待你清理的仪表盘",
  title: "先写下一个真正需要承担后果的问题。",
  intro: "Ludus 不要求你先选模板、方法或 Agent。一个决策项目从人的问题开始；证据、分析、推演和正式决定会在边界确认后逐步出现。",
  formLabel: "现在最需要看清的取舍是什么？",
  formSubline: "只有创建后才会生成 Case 版本",
  formPlaceholder: "例如：未来 12 个月，我们应该把有限资源投入现有产品增长，还是验证一个新的市场方向？",
  formPrivacy: "项目创建前不会生成证据、模型、报告或正式档案。",
  createText: "建立决策项目",
  createSubline: "进入问题边界确认，而不是立即开始分析",
  creatingTitle: "正在建立决策项目…",
  creatingSubline: "建立访客会话并写入决策问题",
  draftedTitle: "决策项目已建立",
  draftedSubline: "正在打开五工作台",
  submitNotice: "决策项目已建立，正在打开工作台…",
  noQuestionNotice: "先写下一个需要承担后果的问题。",
  createFailedFallback: "建立决策项目失败，请稍后重试。"
} as const;

export function EmptyCaseView() {
  const [question, setQuestion] = useState("");
  const [notice, setNotice] = useState("");
  const [isDrafted, setIsDrafted] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const questionInput = useRef<HTMLTextAreaElement>(null);

  const submitDraft = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (isCreating || isDrafted) return;
    if (!question.trim()) {
      setNotice(copy.noQuestionNotice);
      questionInput.current?.focus();
      return;
    }
    setIsCreating(true);
    setNotice("");
    try {
      const created = await createDecisionCase(question.trim());
      setIsDrafted(true);
      setNotice(copy.submitNotice);
      navigateToCreatedCase(created);
    } catch (error) {
      setNotice(error instanceof CaseCreateFlowError ? error.message : copy.createFailedFallback);
      questionInput.current?.focus();
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <section className="view empty-view is-active" id="view-empty" data-view-panel="empty" aria-labelledby="empty-case-title">
      <div className="empty-case-shell">
        <header className="empty-intro">
          <div className="intro-coordinate"><span>{copy.coordinate}</span><i /><small>{copy.coordinateStatus}</small></div>
          <p className="eyebrow">{copy.eyebrow}</p>
          <h1 id="empty-case-title">{copy.title}</h1>
          <p>{copy.intro}</p>
        </header>

        <div className="empty-workbench">
          <form className={isDrafted ? "empty-case-form is-drafted" : "empty-case-form"} onSubmit={submitDraft}>
            <div className="empty-form-heading"><span>DECISION QUESTION / DRAFT</span><small>{copy.formSubline}</small></div>
            <label htmlFor="caseShellQuestion">{copy.formLabel}</label>
            <textarea
              ref={questionInput}
              id="caseShellQuestion"
              rows={5}
              value={question}
              onChange={(event) => { setQuestion(event.target.value); setNotice(""); }}
              placeholder={copy.formPlaceholder}
            />
            <div className="empty-form-actions">
              <button type="submit" className="primary-action" disabled={isCreating}>
                <span>{isDrafted ? copy.draftedTitle : isCreating ? copy.creatingTitle : copy.createText}</span>
                <small>{isDrafted ? copy.draftedSubline : isCreating ? copy.creatingSubline : copy.createSubline}</small>
              </button>
            </div>
            <p className="empty-privacy">{copy.formPrivacy}</p>
            {notice && <p className="draft-notice" role="status">{notice}</p>}
          </form>

          <aside className="empty-method" aria-label="展示规则">
            <span className="margin-label">展示规则</span>
            <div className="empty-method-note"><i /><p>没有项目时，Decision Spine、档案计数和运行状态都不会伪造显示。</p></div>
          </aside>
        </div>
      </div>
    </section>
  );
}
