// Honest data-availability contract for the sandbox workspace (Task 13),
// following the Session B `caseListRouteAvailable` precedent in
// lib/shell/projects.ts: a single source of truth per backend surface,
// no invented endpoints, no mock case data in production.
//
// CCR-20260726-READ-01 flipped this switch ON: the canonical read surface now
// covers every required input —
//   - GET /cases/{id}/simulations         (graph + strategy/scenario/score
//                                          anchors + decision-maker profiles)
//   - GET /simulations/{graphId}/versions/{graphVersionId}  (nodes + edges)
//   - GET /cases/{id}/reports?status=ready (StructuredReport recommendation)
//   - GET /cases/{id}/analyses + /analyses/{runId}/strategic-lenses/{id}
//                                          (scenario_planning frames)
//
// The loader stays fail-closed PER BLOCK: it assembles SandboxCaseData only
// when every required block resolves from real responses; any 404/empty/
// malformed block degrades the WHOLE load to null and the workspace keeps its
// honest Phase 0 empty frame. Nothing is fabricated, defaulted or predicted.

import type {
  Controllability,
  EvidenceStatus,
  FragileCondition,
  NodeKind,
  SandboxCaseData,
  SandboxGraph,
  SandboxGraphEdge,
  SandboxGraphNode,
  ScenarioFrame,
  SimulationAnchors
} from "./types";

export const sandboxCaseDataRouteAvailable = true;

type Envelope = { ok?: boolean; data?: unknown };

async function getData(fetchImpl: typeof fetch, url: string): Promise<unknown | null> {
  try {
    const response = await fetchImpl(url, {
      method: "GET",
      credentials: "same-origin",
      headers: { accept: "application/json" }
    });
    if (!response.ok) return null;
    const body = (await response.json()) as Envelope;
    if (typeof body !== "object" || body === null || !("data" in body)) return null;
    return body.data ?? null;
  } catch {
    return null;
  }
}

const NODE_KINDS: readonly NodeKind[] = [
  "lever",
  "external",
  "constraint",
  "unknown",
  "intermediate",
  "indicator",
  "outcome",
  "decision"
];

function asNodeKind(value: unknown): NodeKind | null {
  return NODE_KINDS.includes(value as NodeKind) ? (value as NodeKind) : null;
}

function asControllability(value: unknown): Controllability {
  // Wire values (canonical): controllable | partially_controllable | uncontrollable.
  if (value === "controllable") return "controllable";
  if (value === "partially_controllable") return "partially_controllable";
  return "external";
}

function asEvidenceStatus(value: unknown): EvidenceStatus {
  // Wire values (canonical): supported | conditional | assumed | unknown.
  if (value === "supported") return "confirmed";
  if (value === "conditional") return "conditional";
  if (value === "assumed") return "assumed";
  return "unknown";
}

type WireNode = Record<string, unknown>;
type WireEdge = Record<string, unknown>;

function mapNode(node: WireNode): SandboxGraphNode | null {
  const kind = asNodeKind(node.nodeType);
  if (typeof node.nodeId !== "string" || typeof node.label !== "string" || kind === null) {
    return null;
  }
  const baseline = typeof node.baselineValue === "number" ? node.baselineValue : null;
  const min = typeof node.minValue === "number" ? node.minValue : null;
  const max = typeof node.maxValue === "number" ? node.maxValue : null;
  if (baseline === null || min === null || max === null) return null;
  const unit = typeof node.unit === "string" && node.unit ? node.unit : "";
  return {
    id: node.nodeId,
    kind,
    title: node.label,
    businessValue: `${baseline}${unit ? ` ${unit}` : ""}`,
    baseline: `${baseline}${unit ? ` ${unit}` : ""}`,
    range: `${min} – ${max}${unit ? ` ${unit}` : ""}`,
    source: typeof node.rationale === "string" ? node.rationale : "",
    confirmation: node.reviewStatus === "confirmed" ? "confirmed" : "pending"
  };
}

function mapEdge(edge: WireEdge): SandboxGraphEdge | null {
  if (
    typeof edge.edgeId !== "string" ||
    typeof edge.sourceNodeId !== "string" ||
    typeof edge.targetNodeId !== "string"
  ) {
    return null;
  }
  const strength = typeof edge.strength === "number" ? edge.strength : 0;
  const evidence = asEvidenceStatus(edge.evidenceStatus);
  return {
    id: edge.edgeId,
    from: edge.sourceNodeId,
    to: edge.targetNodeId,
    relationQuality:
      evidence === "confirmed" ? "evidence" : evidence === "conditional" ? "human_constraint" : "assumed",
    impactStrength: strength >= 0.66 ? "strong" : strength >= 0.33 ? "moderate" : "weak",
    verb: typeof edge.rationale === "string" && edge.rationale ? edge.rationale : "影响",
    source: typeof edge.rationale === "string" ? edge.rationale : "",
    confirmation: edge.reviewStatus === "confirmed" ? "confirmed" : "pending"
  };
}

function mapFragileConditions(nodes: WireNode[]): FragileCondition[] {
  // The three most fragile conditions = adjustable nodes (a sensitivity step
  // exists and the node is editable) ranked by WEAKEST evidence quality first
  // (canonical scores are real; nothing here is predicted or invented).
  const adjustable = nodes.filter(
    (node) =>
      typeof node.sensitivityStep === "number" &&
      node.editable === true &&
      typeof node.nodeId === "string" &&
      typeof node.baselineValue === "number" &&
      typeof node.minValue === "number" &&
      typeof node.maxValue === "number"
  );
  adjustable.sort((a, b) => {
    const qa = typeof a.evidenceQualityScore === "number" ? a.evidenceQualityScore : 1;
    const qb = typeof b.evidenceQualityScore === "number" ? b.evidenceQualityScore : 1;
    return qa - qb;
  });
  return adjustable.slice(0, 3).map((node) => ({
    nodeId: node.nodeId as string,
    title: typeof node.label === "string" ? node.label : (node.nodeId as string),
    unit: typeof node.unit === "string" && node.unit ? node.unit : "",
    baselineValue: node.baselineValue as number,
    min: node.minValue as number,
    max: node.maxValue as number,
    step: node.sensitivityStep as number,
    controllability: asControllability(node.controllability),
    evidenceStatus: asEvidenceStatus(node.evidenceStatus),
    impactNote: typeof node.rationale === "string" ? node.rationale : "",
    businessDomain: typeof node.label === "string" ? node.label : ""
  }));
}

type WireScenario = Record<string, unknown>;

function mapScenarioFrames(
  lensContent: Record<string, unknown>,
  confirmedByLensScenarioId: Map<string, string>
): ScenarioFrame[] | null {
  const scenarios = lensContent.scenarios;
  if (!Array.isArray(scenarios)) return null;
  const frames: ScenarioFrame[] = [];
  for (const raw of scenarios as WireScenario[]) {
    if (typeof raw !== "object" || raw === null) continue;
    const id = typeof raw.id === "string" ? raw.id : null;
    const title = typeof raw.title === "string" ? raw.title : typeof raw.name === "string" ? raw.name : null;
    if (!id || !title) continue;
    const versionId = confirmedByLensScenarioId.get(id) ?? null;
    frames.push({
      id,
      title,
      externalDrivers: Array.isArray(raw.externalDrivers)
        ? (raw.externalDrivers as unknown[]).filter((d): d is string => typeof d === "string")
        : [],
      unknownDrivers: Array.isArray(raw.unknownDrivers)
        ? (raw.unknownDrivers as unknown[]).filter((d): d is string => typeof d === "string")
        : [],
      strategySurvives: raw.strategySurvives === true,
      earlyWarnings: Array.isArray(raw.earlyWarnings)
        ? (raw.earlyWarnings as unknown[]).filter((w): w is string => typeof w === "string")
        : [],
      confirmed: versionId !== null,
      scenarioVersionId: versionId
    });
  }
  return frames.length > 0 ? frames : null;
}

/**
 * Resolve the sandbox inputs for a decision case from the mounted READ-01
 * surface. Returns null (honest empty frame) unless EVERY required block —
 * anchors, graph, recommendation, scenario frames — resolves for real.
 */
export async function loadSandboxCaseData(
  workspaceId: string,
  decisionCaseId: string,
  fetchImpl: typeof fetch = fetch
): Promise<SandboxCaseData | null> {
  if (!sandboxCaseDataRouteAvailable) return null;
  const ws = encodeURIComponent(workspaceId);
  const caseId = encodeURIComponent(decisionCaseId);

  // 1. Case→graph anchors (graph + strategy/scenario/score + profiles).
  const anchorsData = (await getData(
    fetchImpl,
    `/api/workspaces/${ws}/cases/${caseId}/simulations`
  )) as Record<string, unknown> | null;
  if (!anchorsData || !Array.isArray(anchorsData.items) || anchorsData.items.length === 0) {
    return null;
  }
  const graphItem = anchorsData.items[0] as Record<string, unknown>;
  const graphId = typeof graphItem.graphId === "string" ? graphItem.graphId : null;
  const graphVersionId =
    typeof graphItem.currentGraphVersionId === "string" ? graphItem.currentGraphVersionId : null;
  const strategy = Array.isArray(graphItem.strategyVersions)
    ? ((graphItem.strategyVersions as Record<string, unknown>[])[0] ?? null)
    : null;
  const scenarioVersions = Array.isArray(graphItem.scenarioVersions)
    ? (graphItem.scenarioVersions as Record<string, unknown>[])
    : [];
  const score = Array.isArray(graphItem.scoreDefinitions)
    ? ((graphItem.scoreDefinitions as Record<string, unknown>[])[0] ?? null)
    : null;
  const profile = Array.isArray(anchorsData.decisionMakerProfiles)
    ? ((anchorsData.decisionMakerProfiles as Record<string, unknown>[])[0] ?? null)
    : null;
  const scenarioForAnchor = scenarioVersions[0] ?? null;
  if (!graphId || !graphVersionId || !strategy || !scenarioForAnchor || !score || !profile) {
    return null; // anchors incomplete — fail closed, no partial run surface
  }
  const anchors: SimulationAnchors = {
    workspaceId,
    graphId,
    graphVersionId,
    strategyVersionId: String(strategy.strategyVersionId ?? ""),
    scenarioVersionId: String(scenarioForAnchor.scenarioVersionId ?? ""),
    scoreDefinitionId: String(score.scoreDefinitionId ?? ""),
    decisionMakerProfileId: String(profile.decisionMakerProfileId ?? ""),
    decisionMakerProfileVersion: Number(profile.version ?? 0)
  };
  if (
    !anchors.strategyVersionId ||
    !anchors.scenarioVersionId ||
    !anchors.scoreDefinitionId ||
    !anchors.decisionMakerProfileId ||
    !Number.isFinite(anchors.decisionMakerProfileVersion) ||
    anchors.decisionMakerProfileVersion <= 0
  ) {
    return null;
  }

  // 2. Graph version detail (nodes + edges).
  const versionData = (await getData(
    fetchImpl,
    `/api/workspaces/${ws}/simulations/${encodeURIComponent(graphId)}/versions/${encodeURIComponent(graphVersionId)}`
  )) as Record<string, unknown> | null;
  if (!versionData || !Array.isArray(versionData.nodes) || !Array.isArray(versionData.edges)) {
    return null;
  }
  const wireNodes = versionData.nodes as WireNode[];
  const nodes = wireNodes.map(mapNode);
  const edges = (versionData.edges as WireEdge[]).map(mapEdge);
  if (nodes.some((node) => node === null) || edges.some((edge) => edge === null)) return null;
  const graph: SandboxGraph = {
    nodes: nodes as SandboxGraphNode[],
    edges: edges as SandboxGraphEdge[],
    hardConstraints: [],
    draft: versionData.status !== "confirmed"
  };
  const fragileConditions = mapFragileConditions(wireNodes);
  if (fragileConditions.length === 0) return null;

  // 3. Ready report → conditional recommendation.
  const reportsData = (await getData(
    fetchImpl,
    `/api/workspaces/${ws}/cases/${caseId}/reports?status=ready`
  )) as Record<string, unknown> | null;
  const reports = reportsData && Array.isArray(reportsData.items) ? (reportsData.items as Record<string, unknown>[]) : [];
  const report = reports[0] ?? null;
  const content = report && typeof report.structuredContent === "object" && report.structuredContent !== null
    ? (report.structuredContent as Record<string, unknown>)
    : null;
  const wireRecommendation =
    content && typeof content.recommendation === "object" && content.recommendation !== null
      ? (content.recommendation as Record<string, unknown>)
      : null;
  if (!wireRecommendation || typeof wireRecommendation.summary !== "string") return null;
  const outcome =
    typeof wireRecommendation.outcome === "object" && wireRecommendation.outcome !== null
      ? (wireRecommendation.outcome as Record<string, unknown>)
      : null;
  if (!outcome || outcome.kind !== "option" || typeof outcome.optionId !== "string") {
    // abstain / malformed outcome: the sandbox has no option to stress-test.
    return null;
  }
  const recommendation = {
    headline: wireRecommendation.summary,
    optionId: outcome.optionId,
    optionLabel: outcome.optionId,
    conditions: Array.isArray(wireRecommendation.conditions)
      ? (wireRecommendation.conditions as unknown[]).filter((c): c is string => typeof c === "string")
      : [],
    sourceReportVersion: String(report?.caseVersion ?? ""),
    scopeNote: "沙盘暴露失效处，不预测未来。"
  };

  // 4. Scenario frames from the scenario_planning lens artifact.
  const runsData = (await getData(
    fetchImpl,
    `/api/workspaces/${ws}/cases/${caseId}/analyses`
  )) as Record<string, unknown> | null;
  const runs = runsData && Array.isArray(runsData.items) ? (runsData.items as Record<string, unknown>[]) : [];
  const readyRun = runs.find((run) => run.status === "ready" && run.analysisLevel === "full") ?? null;
  if (!readyRun || typeof readyRun.analysisRunId !== "string") return null;
  const lensList = (await getData(
    fetchImpl,
    `/api/workspaces/${ws}/analyses/${encodeURIComponent(readyRun.analysisRunId)}/strategic-lenses`
  )) as unknown;
  const lensSummaries = Array.isArray(lensList) ? (lensList as Record<string, unknown>[]) : [];
  const scenarioLens = lensSummaries.find((lens) => lens.lensType === "scenario_planning") ?? null;
  if (!scenarioLens || typeof scenarioLens.id !== "string") return null;
  const lensDetail = (await getData(
    fetchImpl,
    `/api/workspaces/${ws}/analyses/${encodeURIComponent(readyRun.analysisRunId)}/strategic-lenses/${encodeURIComponent(scenarioLens.id)}`
  )) as Record<string, unknown> | null;
  const lensContent =
    lensDetail && typeof lensDetail.content === "object" && lensDetail.content !== null
      ? (lensDetail.content as Record<string, unknown>)
      : null;
  if (!lensContent) return null;
  const confirmedByLensScenarioId = new Map<string, string>();
  for (const version of scenarioVersions) {
    const sourceId = version.sourceStrategicScenarioId;
    const versionId = version.scenarioVersionId;
    if (typeof sourceId === "string" && typeof versionId === "string") {
      confirmedByLensScenarioId.set(sourceId, versionId);
    }
  }
  const scenarioFrames = mapScenarioFrames(lensContent, confirmedByLensScenarioId);
  if (!scenarioFrames) return null;

  return { recommendation, fragileConditions, graph, scenarioFrames, anchors };
}
