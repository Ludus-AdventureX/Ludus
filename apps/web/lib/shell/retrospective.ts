/**
 * Retrospective / prediction-log client (grey-goo "chronic falsification").
 *
 * A signed decision already froze its own falsifiable predictions: the
 * leadingIndicators, exitCriteria and reviewDate on the DecisionRecord. This
 * module turns them into a review checklist and a calibration line - "when I
 * was N% confident, how often was I right".
 *
 * Judgements are the USER's own (never fabricated) and persist in
 * localStorage keyed by decisionId, so the loop closes without a DB migration.
 * The prediction record is honest about being self-reported.
 */

import { listCaseDecisions, type FetchLike } from "@/lib/shell/signoff";

export type IndicatorVerdict = "pending" | "on_track" | "off_track" | "unclear";

export type ReviewIndicator = {
  id: string;
  text: string;
  kind: "leadingIndicator" | "exitCriterion";
  verdict: IndicatorVerdict;
};

export type DecisionReview = {
  decisionId: string;
  decisionDraft: string;
  reviewDate: string | null;
  dueNow: boolean;
  indicators: ReviewIndicator[];
};

export type CalibrationSummary = {
  total: number;
  judged: number;
  onTrack: number;
  offTrack: number;
  unclear: number;
  /** on-track share of judged predictions (the calibration signal). */
  accuracy: number | null;
};

function storageKey(decisionId: string): string {
  return `ludus.retro.${decisionId}`;
}

function loadVerdicts(decisionId: string): Record<string, IndicatorVerdict> {
  if (typeof localStorage === "undefined") return {};
  try {
    const raw = localStorage.getItem(storageKey(decisionId));
    return raw ? (JSON.parse(raw) as Record<string, IndicatorVerdict>) : {};
  } catch {
    return {};
  }
}

export function saveVerdict(decisionId: string, indicatorId: string, verdict: IndicatorVerdict): void {
  if (typeof localStorage === "undefined") return;
  const current = loadVerdicts(decisionId);
  current[indicatorId] = verdict;
  try {
    localStorage.setItem(storageKey(decisionId), JSON.stringify(current));
  } catch {
    /* storage full / unavailable: judgements degrade to in-session only */
  }
}

function asText(value: unknown): string {
  if (typeof value === "string") return value;
  if (value && typeof value === "object" && "text" in value) return String((value as { text: unknown }).text ?? "");
  return String(value ?? "");
}

/** Build the review for the case's latest signed decision (null if none). */
export async function loadDecisionReview(
  workspaceId: string,
  decisionCaseId: string,
  fetchImpl?: FetchLike,
): Promise<DecisionReview | null> {
  const decisions = await listCaseDecisions(workspaceId, decisionCaseId, fetchImpl);
  const decision = decisions[0] as Record<string, unknown> | undefined;
  if (!decision?.id) return null;
  const payload = (decision.payload as Record<string, unknown>) ?? {};
  const decisionId = String(decision.id);
  const stored = loadVerdicts(decisionId);

  const indicators: ReviewIndicator[] = [];
  const leading = Array.isArray(payload.leadingIndicators) ? payload.leadingIndicators : [];
  leading.forEach((item, index) => {
    const li = item as Record<string, unknown>;
    const id = String(li.id ?? `li-${index}`);
    const text = [asText(li.metric), asText(li.expectedDirection), asText(li.threshold)]
      .filter(Boolean)
      .join(" ") || asText(item);
    indicators.push({ id, text, kind: "leadingIndicator", verdict: stored[id] ?? "pending" });
  });
  const exits = Array.isArray(payload.exitCriteria) ? payload.exitCriteria : [];
  exits.forEach((item, index) => {
    const id = `exit-${index}`;
    indicators.push({ id, text: asText(item), kind: "exitCriterion", verdict: stored[id] ?? "pending" });
  });

  const reviewDate = payload.reviewDate ? String(payload.reviewDate) : null;
  const dueNow = reviewDate != null && new Date(reviewDate).getTime() <= Date.now();

  return {
    decisionId,
    decisionDraft: asText(payload.decisionDraft) || "（未记录决定草案）",
    reviewDate,
    dueNow,
    indicators,
  };
}

export function calibrationOf(indicators: ReviewIndicator[]): CalibrationSummary {
  const onTrack = indicators.filter((i) => i.verdict === "on_track").length;
  const offTrack = indicators.filter((i) => i.verdict === "off_track").length;
  const unclear = indicators.filter((i) => i.verdict === "unclear").length;
  const judged = onTrack + offTrack + unclear;
  return {
    total: indicators.length,
    judged,
    onTrack,
    offTrack,
    unclear,
    accuracy: judged > 0 ? Math.round((onTrack / judged) * 100) / 100 : null,
  };
}
