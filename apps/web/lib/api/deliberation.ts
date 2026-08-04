"use client";

/**
 * Deliberation council client (CCR-20260804-DELIB-01, Wave 3).
 *
 * Types are transcribed FIELD BY FIELD from
 * services/api/app/deliberation/schemas_api.py (camelCase CanonicalModel
 * views) — never guessed, never paralleled. The SSE subscription mirrors the
 * evidence lane's factory seam so jsdom tests can inject a fake EventSource.
 */

export type DeliberationRunStatus =
  | "preparing"
  | "running"
  | "awaiting_user"
  | "complete"
  | "cancelled";

export type DeliberationFactorProvenance = "objective" | "subjective";

export type DeliberationAnchorView = {
  id: string;
  decisionCaseId: string;
  status: DeliberationRunStatus;
  currentRoundSeq: number;
  maxRounds: number;
  createdAt: string;
  updatedAt: string;
};

export type DeliberationFactorView = {
  id: string;
  deliberationRunId: string;
  provenance: DeliberationFactorProvenance;
  label: string;
  strength: number;
  sourceFactorId?: string | null;
  statement?: string | null;
  authorUserId?: string | null;
  dossierAssumptionId?: string | null;
  evidenceStatus?: string | null;
};

export type DeliberationRoundView = {
  id: string;
  deliberationRunId: string;
  seq: number;
  kind: "opening" | "challenge" | "verdict";
  status: "active" | "complete";
  startedAt: string;
  endedAt?: string | null;
};

export type DeliberationMessageView = {
  id: string;
  deliberationRunId: string;
  roundId: string;
  speaker: "witness" | "moderator" | "user";
  speakerFactorId?: string | null;
  kind:
    | "statement"
    | "challenge"
    | "rebuttal"
    | "proposal"
    | "intervention"
    | "nomination"
    | "verdict_summary";
  content: string;
  structuredPayload?: Record<string, unknown> | null;
  stampActor: "human" | "analysis" | "unknown";
  stampNote?: string | null;
  originMode: string;
  sourceOriginModes: string[];
  createdAt: string;
};

export type DeliberationProposalView = {
  id: string;
  deliberationRunId: string;
  proposerFactorId: string;
  kind: "factor_strength" | "edge_validity" | "new_factor";
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  status: "pending" | "accepted" | "rejected";
  enginePreview?: {
    outcomeScore?: number | null;
    verdict?: string | null;
    flipThreshold?: number | null;
  } | null;
  decidedAt?: string | null;
};

export type DeliberationNominationView = {
  id: string;
  deliberationRunId: string;
  rationale: string;
  targetDescription: string;
  status: "pending" | "confirmed" | "rejected";
  confirmedFactorId?: string | null;
};

export type ConditionProjection = {
  acceptedProposalIds: string[];
  projection: {
    outcomeScore?: number | null;
    verdict?: string | null;
    flipThreshold?: number | null;
  };
  condition: string;
};

export type DeliberationOutcomeView = {
  id: string;
  deliberationRunId: string;
  conditionProjections: ConditionProjection[];
  flipConditions: Array<{
    factorId?: string | null;
    label?: string | null;
    flipValue?: number | null;
    scoreDelta?: number | null;
  }>;
  dissentLog: Array<{
    factorId?: string | null;
    witnessLabel?: string | null;
    originalStance?: string | null;
    overturnedBasis?: string | null;
  }>;
  assumptionLedger: Array<{
    factorId?: string | null;
    label?: string | null;
    provenance?: string | null;
    evidenceStatus?: string | null;
    finalStrength?: number | null;
  }>;
  disclaimer: string;
  createdAt: string;
};

export type DeliberationRunDetailView = {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  status: DeliberationRunStatus;
  currentRoundSeq: number;
  maxRounds: number;
  factorSnapshotHash: string;
  originModes: string[];
  factors: DeliberationFactorView[];
  rounds: DeliberationRoundView[];
  pendingProposalCount: number;
  pendingNominationCount: number;
  pendingProposals: DeliberationProposalView[];
  pendingNominations: DeliberationNominationView[];
  createdAt: string;
  updatedAt: string;
};

export type DeliberationEventView = {
  id: string;
  sequence: number;
  workspaceId: string;
  decisionCaseId: string;
  deliberationRunId: string;
  category:
    | "deliberation.round"
    | "deliberation.message"
    | "deliberation.proposal"
    | "deliberation.nomination"
    | "deliberation.outcome";
  type: string;
  originMode: string;
  sourceOriginModes: string[];
  createdAt: string;
  payload: Record<string, unknown>;
};

export type SubjectiveFactorDeclaration = {
  label: string;
  statement: string;
  strength: number;
  direction?: "supporting" | "opposing" | "neutral";
  dossierAssumptionId?: string | null;
};

export type FetchLike = typeof fetch;

function defaultFetch(): FetchLike {
  return (input, init) => fetch(input, init);
}

export class DeliberationClientError extends Error {
  readonly status: number;
  readonly code: string;
  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "DeliberationClientError";
    this.code = code;
    this.status = status;
  }
}

async function readData(response: Response): Promise<Record<string, unknown> | null> {
  const body = (await response.json().catch(() => null)) as
    | { ok?: boolean; data?: Record<string, unknown>; error?: { code?: string; message?: string } }
    | null;
  if (!response.ok) {
    throw new DeliberationClientError(
      body?.error?.code ?? "DELIBERATION_REQUEST_FAILED",
      body?.error?.message ?? `议会请求失败（HTTP ${response.status}）。`,
      response.status
    );
  }
  return body?.data ?? null;
}

async function csrfToken(fetchImpl: FetchLike): Promise<string> {
  const response = await fetchImpl("/api/auth/csrf", { credentials: "include" });
  const body = (await response.json().catch(() => null)) as { data?: { csrfToken?: string } } | null;
  const token = body?.data?.csrfToken;
  if (!token) throw new DeliberationClientError("CSRF_MISSING", "CSRF token 缺失。", response.status);
  return token;
}

export function isUniformNotFound(error: unknown): boolean {
  return error instanceof DeliberationClientError && error.code === "CASE_NOT_FOUND";
}

// --- reads ------------------------------------------------------------------

export async function listDeliberations(
  workspaceId: string,
  decisionCaseId: string,
  fetchImpl: FetchLike = defaultFetch()
): Promise<DeliberationAnchorView[]> {
  const path = `/api/workspaces/${encodeURIComponent(workspaceId)}/cases/${encodeURIComponent(decisionCaseId)}/deliberations`;
  const data = await readData(await fetchImpl(path, { credentials: "include" }));
  const items = (data?.items as DeliberationAnchorView[] | undefined) ?? [];
  return items;
}

export async function getDeliberation(
  workspaceId: string,
  deliberationRunId: string,
  fetchImpl: FetchLike = defaultFetch()
): Promise<DeliberationRunDetailView> {
  const path = `/api/workspaces/${encodeURIComponent(workspaceId)}/deliberations/${encodeURIComponent(deliberationRunId)}`;
  const data = await readData(await fetchImpl(path, { credentials: "include" }));
  return data as unknown as DeliberationRunDetailView;
}

export async function listDeliberationMessages(
  workspaceId: string,
  deliberationRunId: string,
  fetchImpl: FetchLike = defaultFetch()
): Promise<{ items: DeliberationMessageView[]; nextCursor: string | null }> {
  const path = `/api/workspaces/${encodeURIComponent(workspaceId)}/deliberations/${encodeURIComponent(deliberationRunId)}/messages?limit=200`;
  const data = await readData(await fetchImpl(path, { credentials: "include" }));
  return {
    items: ((data?.items as DeliberationMessageView[] | undefined) ?? []),
    nextCursor: (data?.nextCursor as string | null) ?? null
  };
}

export async function getDeliberationOutcome(
  workspaceId: string,
  deliberationRunId: string,
  fetchImpl: FetchLike = defaultFetch()
): Promise<DeliberationOutcomeView> {
  const path = `/api/workspaces/${encodeURIComponent(workspaceId)}/deliberations/${encodeURIComponent(deliberationRunId)}/outcome`;
  const data = await readData(await fetchImpl(path, { credentials: "include" }));
  return data as unknown as DeliberationOutcomeView;
}

// --- writes -------------------------------------------------------------------

export async function createDeliberation(
  workspaceId: string,
  decisionCaseId: string,
  body: { subjectiveFactors: SubjectiveFactorDeclaration[]; maxRounds: number },
  fetchImpl: FetchLike = defaultFetch()
): Promise<DeliberationAnchorView> {
  const token = await csrfToken(fetchImpl);
  const path = `/api/workspaces/${encodeURIComponent(workspaceId)}/cases/${encodeURIComponent(decisionCaseId)}/deliberations`;
  const data = await readData(
    await fetchImpl(path, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
      body: JSON.stringify(body)
    })
  );
  return data as unknown as DeliberationAnchorView;
}

export async function postDeliberationIntervention(
  workspaceId: string,
  deliberationRunId: string,
  body:
    | { kind: "interject"; text: string }
    | { kind: "challenge_witness"; text: string; targetFactorId: string }
    | { kind: "declare_subjective_factor"; subjectiveFactor: SubjectiveFactorDeclaration }
    | { kind: "reopen_round" },
  fetchImpl: FetchLike = defaultFetch()
): Promise<Record<string, unknown>> {
  const token = await csrfToken(fetchImpl);
  const path = `/api/workspaces/${encodeURIComponent(workspaceId)}/deliberations/${encodeURIComponent(deliberationRunId)}/interventions`;
  const data = await readData(
    await fetchImpl(path, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
      body: JSON.stringify(body)
    })
  );
  return data ?? {};
}

export async function decideProposal(
  workspaceId: string,
  deliberationRunId: string,
  proposalId: string,
  decision: "accepted" | "rejected",
  fetchImpl: FetchLike = defaultFetch()
): Promise<DeliberationProposalView> {
  const token = await csrfToken(fetchImpl);
  const path = `/api/workspaces/${encodeURIComponent(workspaceId)}/deliberations/${encodeURIComponent(deliberationRunId)}/proposals/${encodeURIComponent(proposalId)}/decision`;
  const data = await readData(
    await fetchImpl(path, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
      body: JSON.stringify({ decision })
    })
  );
  return data as unknown as DeliberationProposalView;
}

export async function decideNomination(
  workspaceId: string,
  deliberationRunId: string,
  nominationId: string,
  decision: "confirmed" | "rejected",
  subjectiveFactor?: SubjectiveFactorDeclaration,
  fetchImpl: FetchLike = defaultFetch()
): Promise<DeliberationNominationView> {
  const token = await csrfToken(fetchImpl);
  const path = `/api/workspaces/${encodeURIComponent(workspaceId)}/deliberations/${encodeURIComponent(deliberationRunId)}/nominations/${encodeURIComponent(nominationId)}/decision`;
  const data = await readData(
    await fetchImpl(path, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
      body: JSON.stringify(
        subjectiveFactor ? { decision, subjectiveFactor } : { decision }
      )
    })
  );
  return data as unknown as DeliberationNominationView;
}

// --- SSE ---------------------------------------------------------------------

export type DeliberationEventSourceFactory = (url: string) => EventSource;

function defaultEventSourceFactory(url: string): EventSource {
  return new EventSource(url);
}

const DELIBERATION_CATEGORIES = [
  "deliberation.round",
  "deliberation.message",
  "deliberation.proposal",
  "deliberation.nomination",
  "deliberation.outcome"
] as const;

/**
 * Subscribe to the council stream. The browser auto-sends Last-Event-ID on
 * reconnect; the server replays from the persisted per-run sequence.
 */
export function subscribeDeliberationEvents(
  workspaceId: string,
  deliberationRunId: string,
  onEvent: (event: DeliberationEventView) => void,
  factory: DeliberationEventSourceFactory = defaultEventSourceFactory
): () => void {
  const url = `/api/workspaces/${encodeURIComponent(workspaceId)}/deliberations/${encodeURIComponent(deliberationRunId)}/events`;
  const source = factory(url);
  const handlers: Array<{ category: string; handler: (message: MessageEvent) => void }> = [];
  for (const category of DELIBERATION_CATEGORIES) {
    const handler = (message: MessageEvent) => {
      try {
        onEvent(JSON.parse(String(message.data)) as DeliberationEventView);
      } catch {
        // Malformed frames are dropped; the persisted transcript stays the
        // source of truth and a refresh re-reads it.
      }
    };
    source.addEventListener(category, handler as EventListener);
    handlers.push({ category, handler });
  }
  return () => {
    for (const { category, handler } of handlers) {
      source.removeEventListener(category, handler as EventListener);
    }
    source.close();
  };
}
