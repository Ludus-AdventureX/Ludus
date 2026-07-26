import { EvidenceDrawerTrigger } from "@/components/quality/EvidenceDrawerTrigger";
import { PhaseSlot } from "@/components/shell/PhaseSlot";
import { AnalysisLaunchPanel } from "@/components/shell/views/AnalysisLaunchPanel";

// Look V7 `#view-analysis` static layout frame (Phase 0 skeleton).
// No run, trace step, evidence count or gate verdict is fabricated here;
// the analysis-progress slot is now FILLED by AnalysisLaunchPanel (real
// charter -> confirm -> run launch + status polling; replace-phase-slot-node
// per the Task 11 B2 precedent). QualityGatePanel still fills later. Task 11
// B2 fills the evidence-drawer-trigger anchor (replace-phase-slot-node only).
// READ-01 flip: the shell threads { workspaceId, decisionCaseId } so the
// trigger can resolve real run anchors (null workspaceId keeps the gap state).

export type AnalysisViewProps = {
  workspaceId?: string | null;
  decisionCaseId?: string;
};

export function AnalysisView({ workspaceId = null, decisionCaseId }: AnalysisViewProps = {}) {
  return (
    <section className="view is-active" id="view-analysis" data-view-panel="analysis" aria-labelledby="analysis-view-title">
      <header className="view-intro analysis-intro">
        <div className="intro-coordinate analysis-coordinate"><span>E-—</span><i /><small>尚无进行中的研究</small></div>
        <div className="intro-grid">
          <div>
            <p className="eyebrow">证据不是为了支持答案，而是为了暴露答案的边界</p>
            <h1 id="analysis-view-title">研究尚未开始</h1>
            <p className="intro-copy">确认分析委托后，这里展示研究轨迹与可审计产物。系统只展示可审计产物，不展示隐藏思维过程。</p>
          </div>
          <div className="intro-actions" />
        </div>
      </header>

      <div className="analysis-layout">
        <article className="analysis-trace">
          <header className="section-line-heading">
            <div><span>Analysis movement</span><h2>研究轨迹</h2></div>
            <small>等待真实 Run 事件</small>
          </header>
          <AnalysisLaunchPanel
            {...(workspaceId ? { workspaceId } : {})}
            {...(decisionCaseId ? { decisionCaseId } : {})}
          />
        </article>

        <div className="quality-margin">
          <span className="margin-label">质量门未评估</span>
          <PhaseSlot name="quality-gate-panel" label="质量门面板" note="QualityGatePanel（四维状态、阻断项与修复动作）将挂载于此。" />
        </div>
      </div>

      <section className="custody-strip" aria-label="证据保管链">
        <span className="custody-title">一条结论如何形成</span>
        <EvidenceDrawerTrigger
          {...(workspaceId ? { workspaceId } : {})}
          {...(decisionCaseId ? { decisionCaseId } : {})}
        />
      </section>
    </section>
  );
}
