/**
 * Provenance client: reconstruct the tamper-evident chain behind a signed
 * decision. Every link is a content hash the backend already mints, so the
 * panel proves "how this decision was reached" without inventing anything:
 *
 *   DecisionRecord (payloadHash, one-time signature)
 *     ← ReportArtifact (contentHash, quality gate)
 *       ← AnalysisRun (runManifestHash + per-stage inputHash/outputHash)
 *         ← Charter (caseSnapshotHash, method + version)
 *
 * Read-only over the same {ok,data} `/api` envelope. Missing links degrade to
 * an honest "not available" node - the chain never fabricates a hash.
 */

export class ProvenanceError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ProvenanceError";
    this.status = status;
  }
}

export type FetchLike = typeof fetch;

function defaultFetch(): FetchLike {
  return (input, init) => fetch(input, init);
}

async function getData(fetchImpl: FetchLike, path: string): Promise<Record<string, unknown> | null> {
  let response: Response;
  try {
    response = await fetchImpl(path, { credentials: "include" });
  } catch {
    throw new ProvenanceError("无法连接 /api 服务。", 0);
  }
  if (response.status === 404) return null;
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    throw new ProvenanceError(`溯源读取失败（HTTP ${response.status}）。`, response.status);
  }
  return ((body as { data?: Record<string, unknown> })?.data ?? null) as Record<string, unknown> | null;
}

export type ProvenanceLink = {
  kind: "decision" | "report" | "run" | "charter";
  title: string;
  id: string;
  /** Ordered [label, hashOrValue] rows shown under the link. */
  rows: Array<[string, string]>;
  available: boolean;
};

export type DecisionProvenance = {
  decisionId: string;
  links: ProvenanceLink[];
};

function short(value: unknown): string {
  const text = String(value ?? "");
  if (text.startsWith("sha256:")) return `${text.slice(0, 15)}…${text.slice(-6)}`;
  return text.length > 22 ? `${text.slice(0, 14)}…${text.slice(-6)}` : text;
}

/**
 * Build the full provenance chain for the latest decision of a case (or a
 * specific decisionRecord). Returns null when the case has no signed decision.
 */
export async function loadDecisionProvenance(
  workspaceId: string,
  decisionCaseId: string,
  fetchImpl: FetchLike = defaultFetch(),
): Promise<DecisionProvenance | null> {
  const base = `/api/workspaces/${encodeURIComponent(workspaceId)}/cases/${encodeURIComponent(decisionCaseId)}`;
  const decisions = await getData(fetchImpl, `${base}/decisions`);
  const items = (decisions as { items?: Array<Record<string, unknown>> } | null)?.items ?? [];
  const decision = items[0];
  if (!decision?.id) return null;

  const links: ProvenanceLink[] = [];
  links.push({
    kind: "decision",
    title: "决定记录（append-only）",
    id: String(decision.id),
    available: true,
    rows: [
      ["载荷哈希", short(decision.payloadHash)],
      ["选定选项", String(decision.payload && (decision.payload as Record<string, unknown>).selectedOptionId || "—")],
      ["案件版本", String(decision.caseVersion ?? "—")],
    ],
  });

  const reportId = String(decision.sourceReportArtifactId ?? "");
  const runId = String(decision.sourceAnalysisRunId ?? "");

  const report = reportId ? await getData(fetchImpl, `${base}/reports/${encodeURIComponent(reportId)}`) : null;
  links.push({
    kind: "report",
    title: "质量门报告",
    id: reportId || "—",
    available: report != null,
    rows: report
      ? [
          ["内容哈希", short(report.contentHash ?? report.structuredContentHash)],
          ["类型 / 状态", `${String(report.type ?? "?")} / ${String(report.status ?? "?")}`],
          ["质量门", (report.validation as { passed?: boolean } | undefined)?.passed ? "通过" : "—"],
        ]
      : [["状态", "报告不可读（可能已被清理）"]],
  });

  const run = runId
    ? await getData(fetchImpl, `/api/workspaces/${encodeURIComponent(workspaceId)}/analyses/${encodeURIComponent(runId)}`)
    : null;
  const stageResults = (run?.stageResults as Record<string, { outputHash?: string }> | undefined) ?? {};
  const stageRows: Array<[string, string]> = Object.entries(stageResults).map(([stage, v]) => [
    stage,
    short(v?.outputHash),
  ]);
  links.push({
    kind: "run",
    title: "分析运行（六阶段）",
    id: runId || "—",
    available: run != null,
    rows: run
      ? [
          ["运行清单哈希", short(run.runManifestHash)],
          ["终态 / 进度", `${String(run.status ?? "?")} / ${Math.round(Number(run.progress ?? 0) * 100)}%`],
          ...stageRows,
        ]
      : [["状态", "运行不可读"]],
  });

  const charterId = String(run?.charterId ?? "");
  links.push({
    kind: "charter",
    title: "分析章程（问题快照）",
    id: charterId || "—",
    available: run != null && charterId !== "",
    rows: run
      ? [
          ["案件快照哈希", short(run.caseSnapshotHash)],
          ["方法 / 版本", `${String(run.methodId ?? "?")} @ ${String(run.methodVersion ?? "?")}`],
        ]
      : [["状态", "章程不可读"]],
  });

  return { decisionId: String(decision.id), links };
}
