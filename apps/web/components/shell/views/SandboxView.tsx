// Look V7 `#view-sandbox` static layout frame (Phase 0 skeleton).
// Fragile conditions, sliders and pressure results only appear once a real
// confirmed graph and simulation runs exist; nothing is simulated here.

export function SandboxView() {
  return (
    <section className="view is-active" id="view-sandbox" data-view-panel="sandbox" aria-labelledby="sandbox-view-title">
      <div className="pressure-mode">
        <header className="view-intro sandbox-intro">
          <div className="intro-coordinate unknown-coordinate"><span>G-—</span><i /><small>尚无可推演的判断</small></div>
          <div className="intro-grid">
            <div>
              <p className="eyebrow">沙盘不预测未来，它暴露建议在何处失效</p>
              <h1 id="sandbox-view-title">推演尚未开放</h1>
            </div>
            <div className="intro-actions" />
          </div>
        </header>

        <nav className="fragile-index" aria-label="Fragile conditions">
          <button type="button" disabled aria-disabled="true">
            <span>—</span><b>脆弱条件待生成</b><small>需要真实报告与确认图</small>
          </button>
        </nav>

        <div className="pressure-layout">
          <article className="pressure-instrument">
            <header className="section-line-heading">
              <div><span>Fragile condition / —</span><h2>条件压力测试</h2></div>
              <small>等待真实因果图</small>
            </header>
            <p className="pressure-question">压力测试与完整因果模型只消费 confirmed graph 与真实 SimulationRun；预览与非收敛结果不会进入正式建议。</p>
          </article>
        </div>
      </div>
    </section>
  );
}
