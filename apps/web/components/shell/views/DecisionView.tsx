"use client";

import { useState } from "react";

import { SignoffPanel } from "@/components/shell/views/SignoffPanel";
import { ProvenancePanel } from "@/components/shell/views/ProvenancePanel";

// Look V7 `#view-decision` layout frame. The decision-signoff slot is FILLED
// by SignoffPanel; once a decision is signed, ProvenancePanel renders the
// tamper-evident hash chain ("how this decision was reached"). The record
// sheet below stays honest until a real signed decision exists.

export type DecisionViewProps = {
  workspaceId?: string | null;
  decisionCaseId?: string;
};

export function DecisionView({ workspaceId = null, decisionCaseId }: DecisionViewProps = {}) {
  const [signedAt, setSignedAt] = useState(0);
  return (
    <section className="view is-active" id="view-decision" data-view-panel="decision" aria-labelledby="decision-view-title">
      <header className="view-intro decision-intro">
        <div className="intro-coordinate"><span>D-—</span><i /><small>尚无待签署决定</small></div>
        <div className="intro-grid">
          <div>
            <p className="eyebrow">决定不是一句结论，而是一份带退出条件的承诺</p>
            <h1 id="decision-view-title">还没有可以冻结的判断</h1>
          </div>
          <div className="intro-actions">
            <SignoffPanel
              {...(workspaceId ? { workspaceId } : {})}
              {...(decisionCaseId ? { decisionCaseId } : {})}
              onSigned={() => setSignedAt((n) => n + 1)}
            />
          </div>
        </div>
      </header>

      <ProvenancePanel
        {...(workspaceId ? { workspaceId } : {})}
        {...(decisionCaseId ? { decisionCaseId } : {})}
        refreshKey={signedAt}
      />

      <article className="decision-sheet">
        <header className="decision-sheet-header">
          <span>LUDUS DECISION RECORD</span>
          <small>CASE — · D-— · v—</small>
        </header>
        <div className="decision-core">
          <div className="decision-seal" aria-label="等待用户签署的决定印记"><span>D</span><small>—</small></div>
          <div>
            <span className="margin-label">条件性承诺</span>
            <h2>决定记录将由 Task 14W 接入</h2>
            <p>append-only DecisionRecord 只在授权人完成签署事务后出现；这里不展示示例承诺、条件或签名。</p>
          </div>
        </div>
        <div className="decision-conditions">
          <section><span>成立条件</span><p>等待真实决定。</p></section>
          <section><span>退出规则</span><p>等待真实决定。</p></section>
          <section><span>保留异议</span><p>等待真实决定。</p></section>
        </div>
        <footer className="decision-signature">
          <div><span>负责人</span><b>—</b></div>
          <div><span>领先指标</span><b>—</b></div>
          <div><span>复盘日期</span><b>—</b></div>
          <div className="signature-line"><span>等待签署</span></div>
        </footer>
      </article>
    </section>
  );
}
