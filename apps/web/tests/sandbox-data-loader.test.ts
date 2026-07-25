// READ-01 flip: positive end-to-end assembly test for loadSandboxCaseData.
// A complete wire fixture (anchors + graph version + ready report + ready
// full run + scenario_planning lens) must assemble a full SandboxCaseData;
// removing any single block must degrade the WHOLE load to null (fail-closed,
// no partial fabrication).

import { describe, expect, test, vi } from "vitest";

import { loadSandboxCaseData } from "../components/simulation/sandboxData";

function jsonResponse(status: number, body: unknown): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as unknown as Response;
}

const anchorsBody = {
  ok: true,
  data: {
    decisionCaseId: "case_1",
    items: [
      {
        graphId: "g1",
        title: "rescue graph",
        currentGraphVersionId: "gv1",
        reportArtifactId: "ra1",
        originModes: [],
        createdAt: "2026-07-25",
        updatedAt: "2026-07-25",
        strategyVersions: [{ strategyVersionId: "sv1", version: 2, optionId: "opt_rescue", createdAt: "2026-07-25" }],
        scenarioVersions: [
          {
            scenarioVersionId: "scv1",
            version: 1,
            name: "需求走弱",
            strategySurvives: true,
            sourceLensArtifactId: "lens_scenario",
            sourceStrategicScenarioId: "frame_a",
            createdAt: "2026-07-25"
          }
        ],
        scoreDefinitions: [{ scoreDefinitionId: "sd1", version: "1", createdAt: "2026-07-25" }]
      }
    ],
    decisionMakerProfiles: [
      { decisionMakerProfileId: "dmp1", version: 3, displayName: "默认档案", decisionCaseId: "case_1", createdAt: "2026-07-25" }
    ]
  }
};

const versionBody = {
  ok: true,
  data: {
    graphVersionId: "gv1",
    status: "confirmed",
    nodes: [
      {
        nodeId: "n_demand",
        label: "救援需求",
        nodeType: "external",
        baselineValue: 0.5,
        currentValue: 0.5,
        minValue: 0,
        maxValue: 1,
        unit: "指数",
        normalization: "linear",
        sensitivityStep: 0.1,
        controllability: "uncontrollable",
        authorship: "generated",
        evidenceStatus: "supported",
        evidenceQualityScore: 0.4,
        evidenceIds: [],
        assumptionIds: [],
        rationale: "访谈证据",
        reviewStatus: "confirmed",
        editable: true
      },
      {
        nodeId: "n_cash",
        label: "现金窗口",
        nodeType: "constraint",
        baselineValue: 9,
        currentValue: 9,
        minValue: 3,
        maxValue: 18,
        unit: "个月",
        normalization: "linear",
        sensitivityStep: 1,
        controllability: "partially_controllable",
        authorship: "generated",
        evidenceStatus: "conditional",
        evidenceQualityScore: 0.2,
        evidenceIds: [],
        assumptionIds: [],
        rationale: "财务模型",
        reviewStatus: "confirmed",
        editable: true
      }
    ],
    edges: [
      {
        edgeId: "e1",
        sourceNodeId: "n_demand",
        targetNodeId: "n_cash",
        polarity: "positive",
        strength: 0.7,
        delaySteps: 0,
        authorship: "generated",
        evidenceStatus: "supported",
        relationshipQualityScore: 0.7,
        rationale: "拉长",
        claimIds: [],
        evidenceIds: [],
        assumptionIds: [],
        reviewStatus: "confirmed"
      }
    ]
  }
};

const reportsBody = {
  ok: true,
  data: {
    items: [
      {
        id: "ra1",
        caseVersion: 4,
        status: "ready",
        structuredContent: {
          recommendation: {
            outcome: { kind: "option", optionId: "opt_rescue" },
            summary: "在现金窗口不低于 9 个月的条件下先做救援市场",
            conditions: ["现金窗口 ≥ 9 个月"]
          }
        }
      }
    ]
  }
};

const runsBody = {
  ok: true,
  data: {
    items: [
      { analysisRunId: "run_1", status: "ready", analysisLevel: "full", decisionCaseId: "case_1", charterId: "ch", caseVersion: 4, createdAt: "2026-07-25", completedAt: "2026-07-25" }
    ]
  }
};

const lensListBody = { ok: true, data: [{ id: "lens_scenario", lensType: "scenario_planning" }] };

const lensDetailBody = {
  ok: true,
  data: {
    id: "lens_scenario",
    lensType: "scenario_planning",
    content: {
      scenarios: [
        {
          id: "frame_a",
          title: "需求走弱",
          externalDrivers: ["政策收紧"],
          unknownDrivers: ["竞品进入节奏"],
          strategySurvives: true,
          earlyWarnings: ["询价量连续两月下滑"]
        },
        {
          id: "frame_b",
          title: "需求走强",
          externalDrivers: ["灾害频发"],
          unknownDrivers: [],
          strategySurvives: true,
          earlyWarnings: []
        }
      ]
    }
  }
};

function routedFetch(overrides: Record<string, unknown | null> = {}) {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const routes: Record<string, unknown> = {
      "/api/workspaces/ws_1/cases/case_1/simulations": anchorsBody,
      "/api/workspaces/ws_1/simulations/g1/versions/gv1": versionBody,
      "/api/workspaces/ws_1/cases/case_1/reports?status=ready": reportsBody,
      "/api/workspaces/ws_1/cases/case_1/analyses": runsBody,
      "/api/workspaces/ws_1/analyses/run_1/strategic-lenses": lensListBody,
      "/api/workspaces/ws_1/analyses/run_1/strategic-lenses/lens_scenario": lensDetailBody
    };
    if (url in overrides) {
      const body = overrides[url];
      return body === null
        ? jsonResponse(404, { ok: false, error: { code: "CASE_NOT_FOUND", message: "Case material not found." } })
        : jsonResponse(200, body);
    }
    const body = routes[url];
    return body
      ? jsonResponse(200, body)
      : jsonResponse(404, { ok: false, error: { code: "CASE_NOT_FOUND", message: "Case material not found." } });
  });
}

describe("loadSandboxCaseData end-to-end assembly (READ-01 flip)", () => {
  test("a complete wire fixture assembles the full SandboxCaseData", async () => {
    const fetchImpl = routedFetch();
    const data = await loadSandboxCaseData("ws_1", "case_1", fetchImpl as unknown as typeof fetch);
    expect(data).not.toBeNull();
    // Anchors: every SIM-02A id resolved from real reads, nothing invented.
    expect(data?.anchors).toEqual({
      workspaceId: "ws_1",
      graphId: "g1",
      graphVersionId: "gv1",
      strategyVersionId: "sv1",
      scenarioVersionId: "scv1",
      scoreDefinitionId: "sd1",
      decisionMakerProfileId: "dmp1",
      decisionMakerProfileVersion: 3
    });
    // Graph mapped from wire nodes/edges (confirmed version => not draft).
    expect(data?.graph.draft).toBe(false);
    expect(data?.graph.nodes.map((n) => n.id)).toEqual(["n_demand", "n_cash"]);
    expect(data?.graph.edges[0]).toMatchObject({ from: "n_demand", to: "n_cash", impactStrength: "strong" });
    // Fragile conditions ranked weakest evidence first (n_cash 0.2 < n_demand 0.4).
    expect(data?.fragileConditions.map((c) => c.nodeId)).toEqual(["n_cash", "n_demand"]);
    expect(data?.fragileConditions[0]).toMatchObject({ unit: "个月", baselineValue: 9, min: 3, max: 18, step: 1 });
    // Recommendation straight from the ready StructuredReport.
    expect(data?.recommendation.optionId).toBe("opt_rescue");
    expect(data?.recommendation.headline).toContain("现金窗口");
    expect(data?.recommendation.sourceReportVersion).toBe("4");
    // Scenario frames from the lens artifact; confirmed frame carries its version anchor.
    expect(data?.scenarioFrames.map((f) => f.id)).toEqual(["frame_a", "frame_b"]);
    expect(data?.scenarioFrames[0]).toMatchObject({ confirmed: true, scenarioVersionId: "scv1" });
    expect(data?.scenarioFrames[1]).toMatchObject({ confirmed: false, scenarioVersionId: null });
  });

  test.each([
    ["/api/workspaces/ws_1/simulations/g1/versions/gv1"],
    ["/api/workspaces/ws_1/cases/case_1/reports?status=ready"],
    ["/api/workspaces/ws_1/cases/case_1/analyses"],
    ["/api/workspaces/ws_1/analyses/run_1/strategic-lenses"]
  ])("missing block %s degrades the WHOLE load to null", async (url) => {
    const fetchImpl = routedFetch({ [url]: null });
    await expect(
      loadSandboxCaseData("ws_1", "case_1", fetchImpl as unknown as typeof fetch)
    ).resolves.toBeNull();
  });

  test("an abstain recommendation keeps the sandbox closed (no option to stress-test)", async () => {
    const fetchImpl = routedFetch({
      "/api/workspaces/ws_1/cases/case_1/reports?status=ready": {
        ok: true,
        data: {
          items: [
            {
              id: "ra1",
              caseVersion: 4,
              status: "ready",
              structuredContent: {
                recommendation: {
                  outcome: { kind: "abstain", reasonCodes: ["insufficient_evidence"], rationale: "证据不足" },
                  summary: "暂不建议行动"
                }
              }
            }
          ]
        }
      }
    });
    await expect(
      loadSandboxCaseData("ws_1", "case_1", fetchImpl as unknown as typeof fetch)
    ).resolves.toBeNull();
  });
});
