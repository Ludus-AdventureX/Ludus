"use client";

import { useCallback, useEffect, useState } from "react";

import {
  calibrationOf,
  loadDecisionReview,
  saveVerdict,
  type DecisionReview,
  type IndicatorVerdict,
} from "@/lib/shell/retrospective";

// Retrospective loop (g5): a signed decision froze its own falsifiable
// predictions (leading indicators + exit criteria + review date). This panel
// turns them into a review checklist and a calibration line. Judgements are
// the user's own (self-reported, persisted locally); nothing is fabricated,
// and the panel self-hides until a decision is signed.

export type RetrospectivePanelProps = {
  workspaceId?: string | null;
  decisionCaseId?: string;
  refreshKey?: number;
};

const VERDICT_LABELS: Record<IndicatorVerdict, string> = {
  pending: "待判定",
  on_track: "如期",
  off_track: "偏离",
  unclear: "不明",
};

export function RetrospectivePanel({ workspaceId = null, decisionCaseId, refreshKey = 0 }: RetrospectivePanelProps) {
  const [review, setReview] = useState<DecisionReview | null>(null);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    if (!workspaceId || !decisionCaseId) return;
    try {
      setReview(await loadDecisionReview(workspaceId, decisionCaseId));
    } catch {
      setReview(null);
    } finally {
      setLoaded(true);
    }
  }, [workspaceId, decisionCaseId]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const judge = useCallback(
    (indicatorId: string, verdict: IndicatorVerdict) => {
      setReview((prev) => {
        if (!prev) return prev;
        saveVerdict(prev.decisionId, indicatorId, verdict);
        return {
          ...prev,
          indicators: prev.indicators.map((i) => (i.id === indicatorId ? { ...i, verdict } : i)),
        };
      });
    },
    [],
  );

  if (!workspaceId || !decisionCaseId) return null;
  if (!loaded && !review) return null;
  if (loaded && !review) return null;
  if (!review) return null;

  const calibration = calibrationOf(review.indicators);

  return (
    <section className="retro-panel" data-retro-panel aria-label="决策复盘">
      <header>
        <span className="eyebrow">决策复盘 · 慢性证伪 · 校准</span>
        <h3>当初的判断，后来对了吗</h3>
        <p className="phase-slot-note">
          签署时冻结的领先指标与退出规则，就是这个决定的可证伪预测。到期逐条判定，日积月累算出你的校准曲线。
        </p>
      </header>

      <div className="retro-status" data-retro-due={review.dueNow}>
        <p>
          复盘日期：<b>{review.reviewDate ?? "未设定"}</b>
          {review.reviewDate && (review.dueNow ? " · 已到期，请复盘" : " · 未到期（可提前记录观察）")}
        </p>
        {calibration.accuracy != null && (
          <p data-retro-calibration>
            已判定 {calibration.judged}/{calibration.total} 项 · 如期率{" "}
            <b>{Math.round(calibration.accuracy * 100)}%</b>
            （如期 {calibration.onTrack} · 偏离 {calibration.offTrack} · 不明 {calibration.unclear}）
          </p>
        )}
      </div>

      <ol className="retro-indicators">
        {review.indicators.map((indicator) => (
          <li key={indicator.id} data-retro-verdict={indicator.verdict}>
            <div className="retro-indicator-text">
              <span className="retro-kind">{indicator.kind === "exitCriterion" ? "退出规则" : "领先指标"}</span>
              {indicator.text}
            </div>
            <div className="retro-verdict-buttons" role="group" aria-label={`判定：${indicator.text}`}>
              {(["on_track", "off_track", "unclear"] as IndicatorVerdict[]).map((v) => (
                <button
                  key={v}
                  type="button"
                  className={indicator.verdict === v ? "is-active" : ""}
                  aria-pressed={indicator.verdict === v}
                  onClick={() => judge(indicator.id, v)}
                >
                  {VERDICT_LABELS[v]}
                </button>
              ))}
            </div>
          </li>
        ))}
        {review.indicators.length === 0 && (
          <li className="phase-slot-note">这份决定没有登记领先指标或退出规则，无可证伪的复盘锚点。</li>
        )}
      </ol>
    </section>
  );
}
