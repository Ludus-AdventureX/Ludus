"use client";

import { useEffect, useState } from "react";

// R3 portfolio wall: every case x latest run status x signed decision x
// review-due badge, one screen. Pure projection of GET /portfolio - a case
// with no runs shows "未分析", never a fabricated status.

type PortfolioItem = {
  decisionCaseId: string;
  title: string;
  latestRunStatus: string | null;
  hasSignedDecision: boolean;
  reviewDate: string | null;
  reviewDue: boolean;
  reviewed: boolean;
};

export type PortfolioPanelProps = {
  workspaceId?: string | null;
};

function laneOf(item: PortfolioItem): { key: string; label: string } {
  if (item.reviewDue) return { key: "due", label: "该复盘了" };
  if (item.hasSignedDecision) return { key: "signed", label: "已签署" };
  if (item.latestRunStatus === "ready") return { key: "ready", label: "待签署" };
  if (item.latestRunStatus === "blocked") return { key: "blocked", label: "被质量门拦下" };
  if (item.latestRunStatus) return { key: "running", label: "分析中" };
  return { key: "idle", label: "未分析" };
}

export function PortfolioPanel({ workspaceId = null }: PortfolioPanelProps) {
  const [items, setItems] = useState<PortfolioItem[] | null>(null);

  useEffect(() => {
    if (!workspaceId) return;
    let cancelled = false;
    (async () => {
      const r = await fetch(
        `/api/workspaces/${encodeURIComponent(workspaceId)}/portfolio`,
        { credentials: "include" },
      ).catch(() => null);
      if (cancelled || !r?.ok) return;
      const body = (await r.json().catch(() => null)) as
        | { data?: { items?: PortfolioItem[] } }
        | null;
      if (!cancelled) setItems(body?.data?.items ?? []);
    })();
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  if (!workspaceId || items === null) return null;

  return (
    <section className="portfolio-wall" data-portfolio-wall aria-label="决策组合墙">
      <h3>决策组合墙</h3>
      {items.length === 0 && <p className="phase-slot-note">还没有决策案件。</p>}
      <ul>
        {items.map((item) => {
          const lane = laneOf(item);
          return (
            <li key={item.decisionCaseId} data-portfolio-lane={lane.key}>
              <span className="portfolio-lane-badge">{lane.label}</span>
              <span className="portfolio-title">{item.title || item.decisionCaseId.slice(0, 8)}</span>
              {item.reviewDate && (
                <em className="portfolio-review-date">
                  复盘日 {item.reviewDate}
                  {item.reviewed ? "（已复盘）" : ""}
                </em>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
