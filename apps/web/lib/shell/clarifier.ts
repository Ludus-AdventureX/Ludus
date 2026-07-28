/**
 * Question clarifier client (R2): POST /cases/{id}/question-clarifier.
 *
 * Advisory only - the card never blocks launching; adoption feeds the
 * refined question into launchAnalysisForCase({ questionOverride }).
 */

export type ClarifierCard = {
  available: boolean;
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
  if (!response.ok) return { available: false };
  const body = (await response.json().catch(() => null)) as { data?: ClarifierCard } | null;
  return body?.data ?? { available: false };
}
