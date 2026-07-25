import { PhaseSlot } from "@/components/shell/PhaseSlot";

// Look V7 `#view-decision` static layout frame (Phase 0 skeleton).
// The signoff flow and append-only DecisionRecord UI belong to Task 14W;
// this frame reserves the slots and never renders a fake decision.

export function DecisionView() {
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
            <PhaseSlot name="decision-signoff" label="签署入口" note="Task 14W Decision signoff（确认条件、异议和复盘日期）将挂载于此。" />
          </div>
        </div>
      </header>

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
