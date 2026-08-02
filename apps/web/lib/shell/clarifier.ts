/**
 * Question clarifier client (R2): POST /cases/{id}/question-clarifier.
 *
 * Advisory only - the card never blocks launching; adoption feeds the
 * refined question into launchAnalysisForCase({ questionOverride }).
 */

export type ClarifierCard = {
  available: boolean;
  /** Human-readable reason when the card is unavailable (e.g. 422 too-short). */
  reason?: string;
  pseudoDecision?: { verdict: boolean; reason: string };
  falseDilemma?: { verdict: boolean; thirdOption: string };
  reversibility?: { type: "type1" | "type2"; advice: string };
  refinedQuestion?: string;
  originalQuestion?: string;
};

export type FetchLike = typeof fetch;

function defaultFetch(): FetchLike {
  return (input, init) => fetch(input, init);
}

export async function clarifyCaseQuestion(
  workspaceId: string,
  decisionCaseId: string,
  question: string,
  options: { goals?: string[]; constraints?: string[]; fetchImpl?: FetchLike } = {},
): Promise<ClarifierCard> {
  const fetchImpl = options.fetchImpl ?? defaultFetch();
  const csrfResponse = await fetchImpl("/api/auth/csrf", { credentials: "include" });
  const csrfBody = (await csrfResponse.json().catch(() => null)) as
    | { data?: { csrfToken?: string } }
    | null;
  const token = csrfBody?.data?.csrfToken;
  if (!token) return { available: false };
  let response: Response;
  try {
    response = await fetchImpl(
      `/api/workspaces/${encodeURIComponent(workspaceId)}/cases/${encodeURIComponent(decisionCaseId)}/question-clarifier`,
      {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
        body: JSON.stringify({
          question,
          goals: options.goals ?? [],
          constraints: options.constraints ?? [],
        }),
      },
    );
  } catch {
    return { available: false };
  }
  if (!response.ok) {
    // 422 CLARIFIER_QUESTION_TOO_SHORT: tell the human to refine the
    // question in Q instead of a generic "unavailable" dead end.
    if (response.status === 422) {
      return {
        available: false,
        reason: "决策问题过短，请先在 Q 区完善决策问题后再质检。",
      };
    }
    return { available: false };
  }
  const body = (await response.json().catch(() => null)) as { data?: ClarifierCard } | null;
  return body?.data ?? { available: false };
}
