// Evidence provenance/conflict read client owned by the Task 11 B2 lane.
// Consumes the 7 evidence GET routes + the run event stream mounted by the
// A3 wave (CCR-20260726-MOUNT-01); shapes are transcribed FIELD BY FIELD from
// services/api/app/evidence/schemas_api.py (camelCase CanonicalModel wire
// views) + the "证据溯源与冲突读取 API" subsection of 10-api-and-events.md.
// Never redefined, never guessed:
//
//   GET /api/workspaces/{workspaceId}/evidence/{evidenceItemId}
//   GET /api/workspaces/{workspaceId}/evidence/{evidenceItemId}/quality
//   GET /api/workspaces/{workspaceId}/evidence/{evidenceItemId}/provenance
//   GET /api/workspaces/{workspaceId}/evidence/{evidenceItemId}/direction
//   GET /api/workspaces/{workspaceId}/evidence/{evidenceItemId}/same-source-group
//   GET /api/workspaces/{workspaceId}/analyses/{analysisRunId}/evidence
//   GET /api/workspaces/{workspaceId}/analyses/{analysisRunId}/evidence-conflicts
//   GET /api/workspaces/{workspaceId}/analyses/{analysisRunId}/events   (SSE)
//
// Frozen semantics honored here:
//   - read-only GETs under require_workspace_context; no CSRF, no
//     Idempotency-Key headers on this surface;
//   - missing / foreign / cross-tenant ids all answer the byte-identical
//     CASE_NOT_FOUND 404 — the client keeps them collapsed (anti-enumeration)
//     and the UI must never distinguish "does not exist" from "not yours";
//   - responses use the { ok, data } envelope; data is one of the *View DTOs;
//   - SSE `event:` equals the canonical category; this lane only consumes
//     `citation.added` as a passive refresh trigger (progress UI belongs to B1).

// --- Wire shapes (schemas_api.py transcription, camelCase) -----------------

/** app.types.EvidenceVerdict (four-tier). */
export type EvidenceVerdict = "accepted" | "conditional" | "lead_only" | "rejected";

/** app.types.OriginMode. */
export type OriginMode = "live" | "cached" | "fixture";

/**
 * Canonical six-tier source CATEGORY literals (06-data-model.md L672).
 * schemas_api.py types sourceGrade as a plain wire string (MOUNT-01 M10
 * posture), so consumers must tolerate unknown strings and never invent a
 * grade — see knownSourceGrades / the badge component.
 */
export type KnownSourceGrade =
  | "L1_primary"
  | "L2_reputable"
  | "L3_industry"
  | "L4_general"
  | "L5_opinion"
  | "L6_unverified";

export const knownSourceGrades: readonly KnownSourceGrade[] = [
  "L1_primary",
  "L2_reputable",
  "L3_industry",
  "L4_general",
  "L5_opinion",
  "L6_unverified"
];

/** schemas_api.QualityDimensionsView. */
export type QualityDimensionsView = {
  authenticity: number;
  sourceQuality: number;
  relevance: number;
  freshness: number;
  applicability: number;
  independence: number;
  extractionReliability: number;
  biasFlags: string[];
  completenessWarnings: string[];
  conflictGroupIds: string[];
  verdict: EvidenceVerdict;
  reasonCodes: string[];
  assessedAt: string;
};

/** schemas_api.EvidenceItemView. */
export type EvidenceItemView = {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  analysisRunId: string;
  title: string;
  url?: string | null;
  filePath?: string | null;
  sourceDomain?: string | null;
  sourceGrade: string;
  snippet: string;
  sourceRecordId: string;
  sourceSpanIds: string[];
  supportsClaimIds: string[];
  contradictsClaimIds: string[];
  publishedAt?: string | null;
  retrievedAt: string;
  freshnessStatus: string;
  relevance: number;
  bias?: string | null;
  conflictGroupId?: string | null;
  independentSourceGroupId?: string | null;
  verdict: EvidenceVerdict;
  verdictReasonCodes: string[];
  applicabilityLimits: string[];
  originMode: OriginMode;
  rawArtifactId: string;
  qualityAssessmentId: string;
};

/** schemas_api.RawArtifactView — storage pointer style, no path, no body. */
export type RawArtifactView = {
  id: string;
  kind: string;
  mediaType: string;
  byteSize: number;
  sha256: string;
  sourceUrl?: string | null;
  originMode: OriginMode;
  createdAt: string;
};

/** schemas_api.SourceSpanView. */
export type SourceSpanView = {
  id: string;
  locator: Record<string, unknown>;
  quote: string;
  quoteHash: string;
};

/** schemas_api.SourceRecordView. */
export type SourceRecordView = {
  id: string;
  kind: string;
  sourceScope: string;
  canonicalUri: string;
  title: string;
  contentHash: string;
  sourceVersion: string;
  originMode: OriginMode;
  rawArtifactId?: string | null;
  spans: SourceSpanView[];
};

/** schemas_api.EvidenceProvenanceView — full traceability chain slice. */
export type EvidenceProvenanceView = {
  evidenceItemId: string;
  rawArtifact: RawArtifactView;
  sourceRecord: SourceRecordView;
  quality: QualityDimensionsView;
};

/** schemas_api.EvidenceDirectionView. */
export type EvidenceDirectionView = {
  evidenceItemId: string;
  supportsClaimIds: string[];
  contradictsClaimIds: string[];
  verdict: EvidenceVerdict;
};

/** schemas_api.SameSourceGroupView — 同源多篇引用计为一个独立来源. */
export type SameSourceGroupView = {
  independentSourceGroupId?: string | null;
  memberEvidenceItemIds: string[];
  independentSourceCountContribution: number;
};

/** schemas_api.ConflictRelationView. */
export type ConflictRelationView = {
  id: string;
  fromEvidenceItemId: string;
  toEvidenceItemId: string;
  groupId?: string | null;
  rationale?: string | null;
};

/** schemas_api.RunEvidenceListView (+ additive funnelAudit, CCR-20260802-P2W2). */
export type PacketEvidenceView = {
  packetId: string;
  factor?: string | null;
  direction?: string | null;
  conclusion: string;
  claimSupportScore: number;
  evidenceIds: string[];
  role: string;
};

export type RunEvidenceListView = {
  analysisRunId: string;
  items: EvidenceItemView[];
  /** Grey-goo 原则⑩: persisted TDD discard audit (absent when none exists). */
  funnelAudit?: {
    stage: string;
    admitted: number;
    discarded: Array<{ factor?: string; reason?: string; check?: string }>;
    warnings: string[];
    tierCounts: Record<string, number>;
    opposingCount: number;
    lowTierShare: number | null;
  } | null;
  /** Gap-fix wave A (CCR-20260803-GAPFIX): funnel-admitted packets projected
   * for the E page even before the ingest chain (evidence_items) exists. */
  packetEvidence?: PacketEvidenceView[];
};

/** schemas_api.ConflictListView. */
export type ConflictListView = {
  analysisRunId: string;
  conflicts: ConflictRelationView[];
};

// --- Strategic lens references (P1: evidence -> lens support chain) ---------
//
// Consumed from the ALREADY-MOUNTED strategic-lens read surface
// (GET /analyses/{analysisRunId}/strategic-lenses[/{artifactId}], analyses
// routes.py `_lens_summary` / `_lens_detail`). No new contract: the drawer
// only joins existing wire shapes to answer "which lens artifacts cite this
// evidence item".

/** routes.py `_lens_summary` (list item). */
export type LensArtifactSummaryView = {
  id: string;
  lensType: string;
  producerRole: string;
  status: string;
  methodId: string;
  methodVersion: string;
  methodContentHash: string;
  promptVersion: string;
  schemaVersion: string;
  contentHash: string;
  originModes: OriginMode[];
  referenceCounts: {
    claimCount: number;
    evidenceCount: number;
    assumptionCount: number;
  };
  validationAcceptedAt: string | null;
  createdAt: string;
};

/** routes.py `_lens_detail` (single artifact; adds refs + content). */
export type LensArtifactDetailView = LensArtifactSummaryView & {
  decisionCaseId: string;
  analysisRunId: string;
  charterId: string;
  claimRefs: string[];
  evidenceRefs: string[];
  assumptionRefs: string[];
  content: Record<string, unknown>;
};

// --- Error handling ---------------------------------------------------------

export class EvidenceApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "EvidenceApiError";
    this.code = code;
    this.status = status;
  }
}

/**
 * Uniform 404: the server answers missing, foreign and cross-tenant ids with
 * the byte-identical CASE_NOT_FOUND envelope; the client keeps them collapsed.
 */
export function isUniformNotFound(error: unknown): boolean {
  return error instanceof EvidenceApiError && error.status === 404;
}

export function isUnauthenticated(error: unknown): boolean {
  return error instanceof EvidenceApiError && error.status === 401;
}

export function isNetworkError(error: unknown): boolean {
  return error instanceof EvidenceApiError && error.code === "NETWORK_ERROR";
}

type Envelope = { ok?: boolean; data?: unknown };

async function getJson(fetchImpl: typeof fetch, path: string): Promise<unknown> {
  let response: Response;
  try {
    response = await fetchImpl(path, {
      method: "GET",
      credentials: "include",
      headers: { accept: "application/json" }
    });
  } catch {
    throw new EvidenceApiError("NETWORK_ERROR", "无法连接 /api 服务。", 0);
  }
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    const error =
      body && typeof body === "object" && "error" in body
        ? (body as { error?: { code?: string; message?: string } }).error
        : null;
    throw new EvidenceApiError(
      error?.code ?? "HTTP_ERROR",
      error?.message ?? `请求失败（HTTP ${response.status}）。`,
      response.status
    );
  }
  const envelope = (body ?? {}) as Envelope;
  if (typeof envelope !== "object" || envelope === null || !("data" in envelope)) {
    throw new EvidenceApiError("MALFORMED_ENVELOPE", "响应缺少 { ok, data } 信封。", response.status);
  }
  return envelope.data;
}

// --- The seven mounted GET readers ------------------------------------------

export type EvidenceItemAnchors = { workspaceId: string; evidenceItemId: string };
export type EvidenceRunAnchors = { workspaceId: string; analysisRunId: string };

function evidenceBase({ workspaceId, evidenceItemId }: EvidenceItemAnchors): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/evidence/${encodeURIComponent(evidenceItemId)}`;
}

function analysesBase({ workspaceId, analysisRunId }: EvidenceRunAnchors): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/analyses/${encodeURIComponent(analysisRunId)}`;
}

export async function fetchEvidenceItem(
  anchors: EvidenceItemAnchors,
  fetchImpl: typeof fetch = fetch
): Promise<EvidenceItemView> {
  return (await getJson(fetchImpl, evidenceBase(anchors))) as EvidenceItemView;
}

export async function fetchEvidenceQuality(
  anchors: EvidenceItemAnchors,
  fetchImpl: typeof fetch = fetch
): Promise<QualityDimensionsView> {
  return (await getJson(fetchImpl, `${evidenceBase(anchors)}/quality`)) as QualityDimensionsView;
}

export async function fetchEvidenceProvenance(
  anchors: EvidenceItemAnchors,
  fetchImpl: typeof fetch = fetch
): Promise<EvidenceProvenanceView> {
  return (await getJson(fetchImpl, `${evidenceBase(anchors)}/provenance`)) as EvidenceProvenanceView;
}

export async function fetchEvidenceDirection(
  anchors: EvidenceItemAnchors,
  fetchImpl: typeof fetch = fetch
): Promise<EvidenceDirectionView> {
  return (await getJson(fetchImpl, `${evidenceBase(anchors)}/direction`)) as EvidenceDirectionView;
}

export async function fetchSameSourceGroup(
  anchors: EvidenceItemAnchors,
  fetchImpl: typeof fetch = fetch
): Promise<SameSourceGroupView> {
  return (await getJson(fetchImpl, `${evidenceBase(anchors)}/same-source-group`)) as SameSourceGroupView;
}

export async function fetchRunEvidence(
  anchors: EvidenceRunAnchors,
  fetchImpl: typeof fetch = fetch
): Promise<RunEvidenceListView> {
  return (await getJson(fetchImpl, `${analysesBase(anchors)}/evidence`)) as RunEvidenceListView;
}

export async function fetchRunConflicts(
  anchors: EvidenceRunAnchors,
  fetchImpl: typeof fetch = fetch
): Promise<ConflictListView> {
  return (await getJson(fetchImpl, `${analysesBase(anchors)}/evidence-conflicts`)) as ConflictListView;
}

// --- Strategic lens references (already-mounted read surface) ----------------

export async function fetchRunLensArtifacts(
  anchors: EvidenceRunAnchors,
  fetchImpl: typeof fetch = fetch
): Promise<LensArtifactSummaryView[]> {
  const data = (await getJson(
    fetchImpl,
    `${analysesBase(anchors)}/strategic-lenses`
  )) as unknown;
  return Array.isArray(data) ? (data as LensArtifactSummaryView[]) : [];
}

export async function fetchLensArtifact(
  anchors: EvidenceRunAnchors,
  artifactId: string,
  fetchImpl: typeof fetch = fetch
): Promise<LensArtifactDetailView> {
  return (await getJson(
    fetchImpl,
    `${analysesBase(anchors)}/strategic-lenses/${encodeURIComponent(artifactId)}`
  )) as LensArtifactDetailView;
}

// --- Honest data-availability contract (sandbox precedent) -------------------

// CCR-20260726-READ-01 shipped the canonical resolution surface
// (GET /api/workspaces/{workspaceId}/cases/{decisionCaseId}/analyses), so the
// single switch is now ON. The resolver stays honest: any 404/401/network
// failure or an empty run list resolves to null and the drawer keeps its gap
// state — no fabricated run id, no invented endpoint.
export const evidenceAnchorsRouteAvailable = true;

export type CaseRunAnchor = {
  analysisRunId: string;
  decisionCaseId: string;
  charterId: string;
  analysisLevel: string;
  status: string;
  caseVersion: number;
  createdAt: string;
  completedAt: string | null;
};

/**
 * Resolve the run anchors for a decision case via the READ-01 anchor route.
 * The newest run wins (server orders createdAt DESC). Every failure mode
 * degrades to null — the caller renders the honest gap state.
 */
export async function resolveEvidenceAnchors(
  workspaceId: string,
  decisionCaseId: string,
  fetchImpl: typeof fetch = fetch
): Promise<EvidenceRunAnchors | null> {
  if (!evidenceAnchorsRouteAvailable) return null;
  try {
    const data = (await getJson(
      fetchImpl,
      `/api/workspaces/${encodeURIComponent(workspaceId)}/cases/${encodeURIComponent(decisionCaseId)}/analyses`
    )) as { items?: unknown };
    const items = Array.isArray(data?.items) ? (data.items as CaseRunAnchor[]) : [];
    const first = items.find((item) => typeof item?.analysisRunId === "string");
    if (!first) return null;
    return { workspaceId, analysisRunId: first.analysisRunId };
  } catch {
    return null;
  }
}

// --- SSE passive-refresh hook (citation.added only; B1 owns progress) --------

/** SSE `event:` is the canonical category; this lane only consumes this one. */
export const CITATION_ADDED_CATEGORY = "citation.added";

type EventSourceLike = {
  addEventListener(type: string, listener: (event: MessageEvent) => void): void;
  close(): void;
};

export type EvidenceEventSourceFactory = (url: string) => EventSourceLike;

/** Default factory: the browser EventSource, when the runtime provides one. */
export function defaultEvidenceEventSourceFactory(): EvidenceEventSourceFactory | null {
  if (typeof EventSource === "undefined") return null;
  return (url: string) => new EventSource(url, { withCredentials: true });
}

/**
 * Passive refresh hook reserved for `citation.added` events on
 * GET .../analyses/{analysisRunId}/events. It never renders progress and
 * never parses stage payloads (the resumable progress line, Last-Event-ID
 * bookkeeping and status rows belong to the B1 AnalysisProgress lane); it
 * only tells the caller "the citation set changed, re-read the ledger".
 * Returns an unsubscribe function.
 */
export function subscribeCitationAdded(
  anchors: EvidenceRunAnchors,
  onCitationAdded: () => void,
  factory: EvidenceEventSourceFactory | null = defaultEvidenceEventSourceFactory()
): () => void {
  if (!factory) return () => {};
  const source = factory(`${analysesBase(anchors)}/events`);
  source.addEventListener(CITATION_ADDED_CATEGORY, () => {
    onCitationAdded();
  });
  return () => {
    source.close();
  };
}
