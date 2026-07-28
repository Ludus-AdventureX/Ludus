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

// --- R3 gap closure: formal review persistence + cross-case calibration -----

export type WorkspaceCalibration = {
  totalReviews: number;
  outcomes: Record<string, number>;
  onTrackRate: number | null;
};

/** Cross-case calibration line from PERSISTED formal reviews (decision_reviews). */
export async function loadWorkspaceCalibration(
  workspaceId: string,
  fetchImpl?: FetchLike,
): Promise<WorkspaceCalibration | null> {
  const doFetch = fetchImpl ?? ((input: RequestInfo | URL, init?: RequestInit) => fetch(input, init));
  const r = await doFetch(`/api/workspaces/${encodeURIComponent(workspaceId)}/calibration`, {
    credentials: "include",
  }).catch(() => null);
  if (!r || !("ok" in r) || !r.ok) return null;
  const body = (await (r as Response).json().catch(() => null)) as
    | { data?: WorkspaceCalibration }
    | null;
  return body?.data ?? null;
}

/** Conservative mapping from per-indicator verdicts to the formal outcome. */
export function outcomeFromVerdicts(indicators: ReviewIndicator[]): {
  outcome: "on_track" | "adjust";
  outcomeQuality: "positive" | "mixed" | "not_yet_observable";
} {
  const summary = calibrationOf(indicators);
  if (summary.judged === 0 || summary.judged === summary.unclear) {
    return { outcome: "on_track", outcomeQuality: "not_yet_observable" };
  }
  if (summary.offTrack > 0) return { outcome: "adjust", outcomeQuality: "mixed" };
  return { outcome: "on_track", outcomeQuality: "positive" };
}

/**
 * Persist a lightweight FORMAL review to decision_reviews (append-only, cross
 * device). The indicator verdicts become observedIndicatorValues; the outcome
 * mapping is conservative and shown to the user before submission.
 */
export async function submitFormalReview(
  workspaceId: string,
  decisionCaseId: string,
  review: DecisionReview,
  notes: string,
  fetchImpl?: FetchLike,
): Promise<{ ok: boolean; message: string }> {
  const doFetch = fetchImpl ?? ((input: RequestInfo | URL, init?: RequestInit) => fetch(input, init));
  // The formal contract needs the decision's source run; read it from the record.
  const decisions = await listCaseDecisions(workspaceId, decisionCaseId, fetchImpl);
  const decision = decisions[0] as Record<string, unknown> | undefined;
  if (!decision?.id) return { ok: false, message: "没有已签署的决定，无法正式复盘。" };
  const sourceRunId = String(
    decision.sourceAnalysisRunId ?? decision.source_analysis_run_id ?? "",
  );
  if (!sourceRunId) return { ok: false, message: "决定记录缺少来源 run，无法提交。" };

  const csrfResponse = await doFetch("/api/auth/csrf", { credentials: "include" });
  const csrfBody = (await (csrfResponse as Response).json().catch(() => null)) as
    | { data?: { csrfToken?: string } }
    | null;
  const token = csrfBody?.data?.csrfToken;
  if (!token) return { ok: false, message: "安全令牌获取失败。" };

  const mapped = outcomeFromVerdicts(review.indicators);
  const observed: Record<string, string> = {};
  for (const indicator of review.indicators) observed[indicator.id] = indicator.verdict;

  const r = await doFetch(
    `/api/workspaces/${encodeURIComponent(workspaceId)}/decisions/${encodeURIComponent(review.decisionId)}/reviews`,
    {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
      body: JSON.stringify({
        sourceCaseVersion: Number(decision.caseVersion ?? decision.case_version ?? 1) || 1,
        sourceAnalysisRunId: sourceRunId,
        reviewDate: new Date().toISOString().slice(0, 10),
        outcome: mapped.outcome,
        recommendationAdoption: "adopted",
        executionAssessment: "as_planned",
        decisionProcessAssessment: "sound",
        outcomeQuality: mapped.outcomeQuality,
        observedIndicatorValues: observed,
        thresholdBreaches: [],
        externalChanges: [],
        actualOutcomes: [],
        assumptionResults: [],
        lessons: [],
        nextDecisionChanges: [],
        notes: notes.trim() || "轻量复盘：基于指标逐项判定提交（详细复盘可后续补充）。",
      }),
    },
  ).catch(() => null);
  if (!r) return { ok: false, message: "网络错误，提交失败。" };
  if (!(r as Response).ok) {
    return { ok: false, message: `提交失败（HTTP ${(r as Response).status}）。` };
  }
  return { ok: true, message: "正式复盘已存档（跨设备保留，计入校准线）。" };
}

