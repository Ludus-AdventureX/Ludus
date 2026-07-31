"use client";

import { dimVerdict, humanizeFinding } from "@/lib/shell/runReads";

// The panel the E view's quality margin promised ("QualityGatePanel 将挂载于
// 此") and never received. Pure projection of the run's own verdict artifacts:
// the multiplicative deterministic gate (evidence × adversarial × consistency)
// and the terminal findings. Nothing here is scored client-side and no
// dimension is invented — a dimension the pipeline did not exercise renders
// as 未评估.

export type GateDims = {
  evidence?: number;
  adversarial?: number;
  consistency?: number;
};

export type QualityGateProjection = {
  /** Terminal run status: ready | blocked | needs_attention | executing states. */
  runStatus: string | null;
  /** The deterministic gate dict from the validating stage, when present. */
  gate: { passed?: boolean; score?: number; dims?: GateDims } | null;
  /** Stable reason codes from the blocked verdict (lens audit etc.). */
  blockedCodes: string[];
  /** True when the run's trace labels itself fixture (demo placeholder). */
  fixtureRun: boolean;
};

/** Repair action per stable reason code — concrete, not "try again". */
const REPAIR_ACTIONS: Record<string, string> = {
  strategic_lens_incomplete:
    "完整战略分析需要五个战略透镜全部产出并通过行为校验；当前部署的透镜执行尚未完全接通，请先使用聚焦研究，或等待透镜管线修复。",
  strategic_lens_reference_mismatch:
    "报告引用与实际产物不一致属于系统侧缺陷，无需补充档案；请重新发起一次分析。",
};

export function QualityGatePanel({ projection }: { projection: QualityGateProjection }) {
  const { runStatus, gate, blockedCodes, fixtureRun } = projection;
  const dims = gate?.dims ?? {};
  const terminal = runStatus === "ready" || runStatus === "blocked";

  const marginLabel = !runStatus
    ? "质量门未评估"
    : runStatus === "ready"
      ? "已通过最终质量门"
      : runStatus === "blocked"
        ? "尚未通过最终质量门"
        : "质量门评估中";

  const editorial = !runStatus
    ? "发起一次分析后，这里展示证据、反方与一致性的审查结果。"
    : runStatus === "ready"
      ? "证据、反方与链条一致性均已通过审查；建议以条件化形式成立。"
      : runStatus === "blocked"
        ? fixtureRun
          ? "本次运行处于演示占位模式，质量门按设计拦截正式产物。"
          : "证据链还支撑不起结论；下方是具体卡点与修复动作。"
        : "研究仍在推进，质量门在验证阶段给出裁决。";

  return (
    <div className="quality-margin" data-quality-gate-panel data-gate-status={runStatus ?? "none"}>
      <span className="margin-label">{marginLabel}</span>
      <h2>
        {runStatus === "blocked"
          ? "当前最脆弱的，是证据与结论之间的链条。"
          : runStatus === "ready"
            ? "本次结论带着它的条件一起交付。"
            : "质量门只在验证阶段给出裁决。"}
      </h2>
      <p>{editorial}</p>

      <dl>
        <div><dt>证据可用性</dt><dd>{dimVerdict(dims.evidence)}</dd></div>
        <div><dt>反方压力</dt><dd>{dimVerdict(dims.adversarial)}</dd></div>
        <div><dt>链条一致性</dt><dd>{dimVerdict(dims.consistency)}</dd></div>
        <div>
          <dt>综合裁决</dt>
          <dd>
            {terminal
              ? runStatus === "ready"
                ? "通过"
                : "拦截"
              : "未出"}
            {typeof gate?.score === "number" ? ` · ${gate.score.toFixed(2)}` : ""}
          </dd>
        </div>
      </dl>

      {blockedCodes.length > 0 && (
        <div className="gate-blockers" data-gate-blockers>
          <span className="margin-label">阻断项与修复动作</span>
          <ul>
            {blockedCodes.map((code) => (
              <li key={code}>
                <b>{humanizeFinding(code)}</b>
                {REPAIR_ACTIONS[code] && <p>{REPAIR_ACTIONS[code]}</p>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
