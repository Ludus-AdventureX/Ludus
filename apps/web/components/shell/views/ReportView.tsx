import { PhaseSlot } from "@/components/shell/PhaseSlot";

// Look V7 `#view-report` static layout frame (Phase 0 skeleton).
// Recommendation, conditions and dissent render only from canonical
// Report contracts in later phases; no verdict is fabricated here.

export function ReportView() {
  return (
    <section className="view is-active" id="view-report" data-view-panel="report" aria-labelledby="report-view-title">
      <header className="view-intro report-intro">
        <div className="intro-coordinate"><span>J-—</span><i /><small>尚无条件化判断</small></div>
        <div className="intro-grid">
          <div>
            <p className="eyebrow">不是“选哪一个”，而是“在什么条件下先做什么”</p>
            <h1 id="report-view-title">报告尚未生成</h1>
          </div>
          <div className="intro-actions" />
        </div>
      </header>

      <article className="report-spread">
        <section className="recommendation-page" aria-label="当前建议">
          <div className="recommendation-rule"><span>当前建议</span><i /><b>等待分析完成</b></div>
          <p className="lead-paragraph">结构化报告只在真实 AnalysisRun 通过质量门后出现；这里不展示示例结论。</p>
          <div className="condition-list" />
          <footer className="report-signature">
            <span>系统综合</span>
            <i />
            <span>等待人类采纳</span>
          </footer>
        </section>

        <aside className="dissent-page">
          <span className="margin-label">最强反对意见</span>
          <p>反方审查与建议翻转条件将随真实报告一同呈现。</p>
          <hr />
          <PhaseSlot name="evidence-drawer-trigger" label="关键证据入口" note="EvidenceDrawer 触发点：主要判断可点击，抽屉展示支持/反对证据与来源等级。" />
        </aside>
      </article>
    </section>
  );
}
