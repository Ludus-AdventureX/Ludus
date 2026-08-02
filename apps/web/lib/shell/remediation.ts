// Blocked-run remediation reading for the Q workspace (remediation card).
//
// When the latest analysis run was blocked by the model validator, the card
// turns the validator's own reasons (keyFindings + openQuestions) into an
// actionable checklist: the human adopts each item (or writes their own via
// the "其它" input) and the text lands in the ledger composer, then flows
// through the EXISTING candidate pipeline - propose -> confirm -> dossier.
//
// Backend-free: everything is derived from the canonical read surfaces
// (run anchors + append-only run events), so a stale or lens-side block
// simply yields null and the card stays hidden.

import { listCaseAnalyses } from "@/lib/shell/runReads";
import { replayRunTrace } from "@/lib/shell/decisionLoop";

export type BlockedRemediation = {
  analysisRunId: string;
  headline: string;
  /** Validator reasons the human can adopt as dossier candidates. */
  gaps: string[];
  /** Open questions the validator wants answered before the chain holds. */
  openQuestions: string[];
};

const VALIDATOR_CODE = "validator_rejected";
const BLOCKED_EVENT = "analysis.blocked";

/**
 * Resolve the latest blocked run's validator remediation for a case.
 * Returns null when there is no block, no validator rejection, or any read
 * fails (the card renders nothing - never fabricated guidance).
 */
export async function fetchBlockedRemediation(
  workspaceId: string,
  decisionCaseId: string,
): Promise<BlockedRemediation | null> {
  let runs;
  try {
    runs = await listCaseAnalyses(workspaceId, decisionCaseId);
  } catch {
    return null;
  }
  const latest = runs[0];
  if (!latest || latest.status !== "blocked") return null;

  let trace;
  try {
    trace = await replayRunTrace(workspaceId, latest.analysisRunId);
  } catch {
    return null;
  }
  const blocked = trace.find((entry) => entry.type === BLOCKED_EVENT);
  const findings = blocked?.findings ?? [];
  const validator = findings.find(
    (finding) => finding?.code === VALIDATOR_CODE,
  );
  if (!validator) return null;

  const headline =
    typeof validator.headline === "string" && validator.headline.trim()
      ? validator.headline.trim()
      : "验证审查拒绝了本次分析（理由见下）。";
  const gaps = Array.isArray(validator.keyFindings)
    ? validator.keyFindings.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    : [];
  const openQuestions = Array.isArray(validator.openQuestions)
    ? validator.openQuestions.filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    : [];
  if (gaps.length === 0 && openQuestions.length === 0) return null;
  return { analysisRunId: latest.analysisRunId, headline, gaps, openQuestions };
}
