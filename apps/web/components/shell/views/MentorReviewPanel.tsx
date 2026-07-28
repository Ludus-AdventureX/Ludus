"use client";

import { useCallback, useEffect, useState } from "react";

// R3 mentor review surface: REVIEW capability writes (the mentor invite
// preset), everyone in the workspace reads. Server enforces the boundary;
// the form self-degrades to read-only on 403.

type MentorReview = {
  mentorReviewId: string;
  qualityScore: number;
  blindSpots: string;
  nextStep: string;
  createdAt: string | null;
};

export type MentorReviewPanelProps = {
  workspaceId?: string | null;
  decisionCaseId?: string;
};

async function csrf(): Promise<string | null> {
  const r = await fetch("/api/auth/csrf", { credentials: "include" });
  const body = (await r.json().catch(() => null)) as { data?: { csrfToken?: string } } | null;
  return body?.data?.csrfToken ?? null;
}

export function MentorReviewPanel({ workspaceId = null, decisionCaseId }: MentorReviewPanelProps) {
  const [items, setItems] = useState<MentorReview[]>([]);
  const [score, setScore] = useState(3);
  const [blindSpots, setBlindSpots] = useState("");
  const [nextStep, setNextStep] = useState("");
  const [notice, setNotice] = useState("");
  const [canWrite, setCanWrite] = useState(true);

  const refresh = useCallback(async () => {
    if (!workspaceId || !decisionCaseId) return;
    const r = await fetch(
      `/api/workspaces/${encodeURIComponent(workspaceId)}/cases/${encodeURIComponent(decisionCaseId)}/mentor-reviews`,
      { credentials: "include" },
    ).catch(() => null);
    if (!r?.ok) return;
    const body = (await r.json().catch(() => null)) as { data?: { items?: MentorReview[] } } | null;
    setItems(body?.data?.items ?? []);
  }, [workspaceId, decisionCaseId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const submit = useCallback(async () => {
    if (!workspaceId || !decisionCaseId) return;
    if (!blindSpots.trim() || !nextStep.trim()) {
      setNotice("盲区提醒与建议下一步都不能为空。");
      return;
    }
    const token = await csrf();
    if (!token) return;
    const r = await fetch(
      `/api/workspaces/${encodeURIComponent(workspaceId)}/cases/${encodeURIComponent(decisionCaseId)}/mentor-reviews`,
      {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
        body: JSON.stringify({ qualityScore: score, blindSpots, nextStep }),
      },
    ).catch(() => null);
    if (r?.status === 403) {
      setCanWrite(false);
      setNotice("当前身份没有评审权（导师身份才能写点评）。");
      return;
    }
    if (r?.ok) {
      setBlindSpots("");
      setNextStep("");
      setNotice("点评已提交。");
      await refresh();
    } else {
      setNotice("提交失败，请稍后再试。");
    }
  }, [workspaceId, decisionCaseId, score, blindSpots, nextStep, refresh]);

  if (!workspaceId || !decisionCaseId) return null;

  return (
    <section className="mentor-review-panel" data-mentor-review-panel aria-label="导师评审">
      <h3>导师评审</h3>
      {items.length === 0 && <p className="phase-slot-note">还没有导师点评。</p>}
      {items.length > 0 && (
        <ul className="mentor-review-list">
          {items.map((item) => (
            <li key={item.mentorReviewId}>
              <b>思考质量 {item.qualityScore}/5</b>
              <p>盲区：{item.blindSpots}</p>
              <p>建议下一步:{item.nextStep}</p>
            </li>
          ))}
        </ul>
      )}
      {canWrite && (
        <div className="mentor-review-form">
          <label>
            思考质量（1-5）
            <input
              type="number"
              min={1}
              max={5}
              value={score}
              onChange={(e) => setScore(Math.max(1, Math.min(5, Number(e.target.value) || 3)))}
            />
          </label>
          <label>
            盲区提醒
            <textarea value={blindSpots} onChange={(e) => setBlindSpots(e.target.value)} rows={2} />
          </label>
          <label>
            建议下一步
            <textarea value={nextStep} onChange={(e) => setNextStep(e.target.value)} rows={2} />
          </label>
          <button type="button" className="secondary-action small" onClick={() => void submit()}>
            <span>提交点评</span>
          </button>
        </div>
      )}
      {notice && <p role="status">{notice}</p>}
    </section>
  );
}
