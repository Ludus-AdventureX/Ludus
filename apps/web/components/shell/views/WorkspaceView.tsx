import { DecisionHealthBar } from "@/components/shell/DecisionHealthBar";
import { PhaseSlot } from "@/components/shell/PhaseSlot";

// Look V7 `#view-workspace` static layout frame (Phase 0 skeleton).
// Real ledger notes, folio counts and charter entry arrive in later phases;
// nothing here fabricates case, evidence or run state. Session B fills the
// decision-health-bar slot with the five-segment skeleton (no data yet).

type WorkspaceViewProps = {
  decisionCaseId: string;
};

export function WorkspaceView({ decisionCaseId }: WorkspaceViewProps) {
  return (
    <section className="view is-active" id="view-workspace" data-view-panel="workspace" aria-labelledby="workspace-view-title">
      <header className="view-intro workspace-intro">
        <div className="intro-coordinate"><span>Q-—</span><i /><small>档案未接入</small></div>
        <div className="intro-grid">
          <div>
            <p className="eyebrow">今天要看清的，不是答案，而是下注条件</p>
            <h1 id="workspace-view-title">决策项目 {decisionCaseId}</h1>
            <p className="intro-copy">问题工作区将在档案 API 接入后展示已确认的决策问题、边界与你的推演札记。进入正式档案的事实与最终决定始终由你确认。</p>
          </div>
          <div className="intro-actions">
            <PhaseSlot name="analysis-charter-form" label="分析委托入口" note="AnalysisCharterForm 将挂载于此；quick/focused/full 深度选择在 Charter Phase 接入。" />
          </div>
        </div>
      </header>

      <div className="workspace-grid">
        <article className="ledger-sheet" aria-labelledby="workspace-ledger-title">
          <header className="sheet-heading">
            <div>
              <span className="sheet-index">推演札记 / —</span>
              <h2 id="workspace-ledger-title">人的推演台</h2>
            </div>
            <p><i className="human-dot" /> 只有你确认的内容才会进入正式档案</p>
          </header>
          <div className="ledger-body">
            <DecisionHealthBar />
          </div>
        </article>

        <aside className="folio-peek" aria-label="当前案例摘要">
          <div className="folio-question">
            <span>Q-— · OWNER / USER</span>
            <p>档案折页将在 Case 只读 API 接入后展示问题与计数；空档案不显示伪造数字。</p>
          </div>
        </aside>
      </div>
    </section>
  );
}
