"use client";

import { useEffect, useState } from "react";

// Profile panel: shows the AI-extracted decision-maker and question profiles
// in the Q page right rail. Refetches after each conversation turn via the
// ludus:profile-refresh custom event. Look V7 style: no rounded corners, no
// gradients, hairline borders, semantic tokens only.

type DecisionMakerProfile = {
  riskTolerance?: string;
  timeConstraints?: string[];
  resourceConstraints?: string[];
  expressedPreferences?: string[];
  bottomLines?: string[];
};

type QuestionProfile = {
  coreTradeoff?: string;
  confirmedFacts?: string[];
  keyAssumptions?: string[];
  unknowns?: string[];
  options?: string[];
  refinedQuestion?: string;
};

type ProfileData = {
  decision_maker?: { content: DecisionMakerProfile; version: number };
  question?: { content: QuestionProfile; version: number };
};

export type ProfilePanelProps = {
  workspaceId?: string | null;
  decisionCaseId?: string;
};

const RISK_LABELS: Record<string, string> = {
  conservative: "保守型",
  moderate: "平衡型",
  aggressive: "激进型",
};

export function ProfilePanel({ workspaceId = null, decisionCaseId }: ProfilePanelProps) {
  const [data, setData] = useState<ProfileData | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const bump = () => setTick((t) => t + 1);
    window.addEventListener("ludus:profile-refresh", bump);
    return () => window.removeEventListener("ludus:profile-refresh", bump);
  }, []);

  useEffect(() => {
    if (!workspaceId || !decisionCaseId) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(
          `/api/workspaces/${encodeURIComponent(workspaceId)}/cases/${encodeURIComponent(decisionCaseId)}/profiles`,
          { credentials: "include" },
        );
        if (!res.ok || cancelled) return;
        const body = (await res.json()) as { ok?: boolean; data?: ProfileData };
        if (!cancelled && body?.ok) setData(body.data ?? null);
      } catch { /* graceful */ }
    })();
    return () => { cancelled = true; };
  }, [workspaceId, decisionCaseId, tick]);

  if (!workspaceId || !decisionCaseId) return null;

  // Readiness indicator: guides the user toward E page when profiles are rich enough.
  const readiness = computeReadiness(data);

  if (!data || (!data.decision_maker && !data.question)) {
    return (
      <div className="profile-panel" data-profile-panel="empty">
        <span className="profile-panel-title">系统当前理解</span>
        <p className="profile-empty">与系统对话后，画像会自动形成。</p>
        <div className="profile-readiness" data-readiness="empty">
          <span>准备度</span>
          <p>继续对话，系统会自动整理问题结构。</p>
        </div>
      </div>
    );
  }

  const dm = data.decision_maker?.content;
  const q = data.question?.content;

  return (
    <div className="profile-panel" data-profile-panel="ready">
      <span className="profile-panel-title">系统当前理解</span>

      {dm && (
        <section className="profile-section" data-profile-section="decision-maker">
          <h4>决策者</h4>
          {dm.riskTolerance && (
            <span className="profile-tag">{RISK_LABELS[dm.riskTolerance] ?? dm.riskTolerance}</span>
          )}
          {dm.timeConstraints && dm.timeConstraints.length > 0 && (
            <div className="profile-list">
              <b>时间约束</b>
              {dm.timeConstraints.map((item, i) => <p key={i} className="profile-item">{item}</p>)}
            </div>
          )}
          {dm.resourceConstraints && dm.resourceConstraints.length > 0 && (
            <div className="profile-list">
              <b>资源约束</b>
              {dm.resourceConstraints.map((item, i) => <p key={i} className="profile-item">{item}</p>)}
            </div>
          )}
          {dm.expressedPreferences && dm.expressedPreferences.length > 0 && (
            <div className="profile-list">
              <b>偏好</b>
              {dm.expressedPreferences.map((item, i) => <p key={i} className="profile-item">{item}</p>)}
            </div>
          )}
          {dm.bottomLines && dm.bottomLines.length > 0 && (
            <div className="profile-list">
              <b>底线</b>
              {dm.bottomLines.map((item, i) => <p key={i} className="profile-item">{item}</p>)}
            </div>
          )}
        </section>
      )}

      {q && (
        <section className="profile-section" data-profile-section="question">
          <h4>问题结构</h4>
          {q.coreTradeoff && <p className="profile-tradeoff">{q.coreTradeoff}</p>}
          {q.refinedQuestion && (
            <div className="profile-refined">
              <b>精炼问题</b>
              <p className="profile-item">{q.refinedQuestion}</p>
            </div>
          )}
          {q.options && q.options.length > 0 && (
            <div className="profile-list">
              <b>选项</b>
              {q.options.map((item, i) => <p key={i} className="profile-item">{item}</p>)}
            </div>
          )}
          {q.confirmedFacts && q.confirmedFacts.length > 0 && (
            <div className="profile-list">
              <b>已确认事实</b>
              {q.confirmedFacts.map((item, i) => <p key={i} className="profile-item">{item}</p>)}
            </div>
          )}
          {q.keyAssumptions && q.keyAssumptions.length > 0 && (
            <div className="profile-list">
              <b>关键假设</b>
              {q.keyAssumptions.map((item, i) => <p key={i} className="profile-item">{item}</p>)}
            </div>
          )}
          {q.unknowns && q.unknowns.length > 0 && (
            <div className="profile-list">
              <b>待验证</b>
              {q.unknowns.map((item, i) => <p key={i} className="profile-item">{item}</p>)}
            </div>
          )}
        </section>
      )}

      <div className="profile-readiness" data-readiness={readiness.level}>
        <span>准备度</span>
        <p>{readiness.message}</p>
      </div>
    </div>
  );
}

// --- Readiness computation ---------------------------------------------------

type Readiness = { level: "empty" | "partial" | "ready"; message: string };

function computeReadiness(data: ProfileData | null): Readiness {
  if (!data || (!data.decision_maker && !data.question)) {
    return { level: "empty", message: "继续对话，系统会自动整理问题结构。" };
  }
  const q = data.question?.content;
  const dm = data.decision_maker?.content;
  const missing: string[] = [];
  if (!q?.coreTradeoff) missing.push("核心取舍");
  if (!q?.options || q.options.length === 0) missing.push("选项");
  if (!dm?.riskTolerance) missing.push("风险倾向");
  if ((!q?.confirmedFacts || q.confirmedFacts.length === 0) && (!q?.keyAssumptions || q.keyAssumptions.length === 0))
    missing.push("事实或假设");
  if (missing.length === 0) {
    return { level: "ready", message: "问题结构已就绪，可以到 E 页发起深度分析。" };
  }
  return {
    level: "partial",
    message: `还缺 ${missing.join("、")}，补充后分析会更有效。`,
  };
}
