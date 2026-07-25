/** @vitest-environment jsdom */

import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import {
  DemoApiError,
  readDemoFixtureConfig,
  runDemoFlow,
  type DemoFixtureConfig,
  type SimulationRunData,
} from "../lib/demo/simulationDemo";

const fixtureEnv: Record<string, string> = {
  NEXT_PUBLIC_DEMO_GRAPH_ID: "11111111-1111-4111-8111-111111111111",
  NEXT_PUBLIC_DEMO_GRAPH_VERSION_ID: "22222222-2222-4222-8222-222222222222",
  NEXT_PUBLIC_DEMO_STRATEGY_VERSION_ID: "33333333-3333-4333-8333-333333333333",
  NEXT_PUBLIC_DEMO_SCENARIO_VERSION_ID: "44444444-4444-4444-8444-444444444444",
  NEXT_PUBLIC_DEMO_SCORE_DEFINITION_ID: "55555555-5555-4555-8555-555555555555",
  NEXT_PUBLIC_DEMO_PROFILE_ID: "66666666-6666-4666-8666-666666666666",
  NEXT_PUBLIC_DEMO_PROFILE_VERSION: "1",
};

const demoConfig: DemoFixtureConfig = {
  graphId: fixtureEnv.NEXT_PUBLIC_DEMO_GRAPH_ID,
  graphVersionId: fixtureEnv.NEXT_PUBLIC_DEMO_GRAPH_VERSION_ID,
  strategyVersionId: fixtureEnv.NEXT_PUBLIC_DEMO_STRATEGY_VERSION_ID,
  scenarioVersionId: fixtureEnv.NEXT_PUBLIC_DEMO_SCENARIO_VERSION_ID,
  scoreDefinitionId: fixtureEnv.NEXT_PUBLIC_DEMO_SCORE_DEFINITION_ID,
  decisionMakerProfileId: fixtureEnv.NEXT_PUBLIC_DEMO_PROFILE_ID,
  decisionMakerProfileVersion: 1,
};

const runData: SimulationRunData = {
  simulationRunId: "77777777-7777-4777-8777-777777777777",
  workspaceId: "88888888-8888-4888-8888-888888888888",
  decisionCaseId: "99999999-9999-4999-8999-999999999999",
  graphId: demoConfig.graphId,
  graphVersionId: demoConfig.graphVersionId,
  strategyVersionId: demoConfig.strategyVersionId,
  scenarioVersionId: demoConfig.scenarioVersionId,
  scoreDefinitionId: demoConfig.scoreDefinitionId,
  scoreDefinitionVersion: "1",
  decisionMakerProfileId: demoConfig.decisionMakerProfileId,
  decisionMakerProfileVersion: 1,
  riskTolerance: 0.5,
  engineVersion: "sim-engine-1.1.0",
  scenarioId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  simulationMode: "experimental",
  epsilon: 0.001,
  maxSteps: 12,
  steps: 6,
  inputHash: "b".repeat(64),
  nodeResults: { revenue: 0.42 },
  optionScores: [{ optionId: "option-a", score: 0.61 }],
  topDrivers: [{ nodeId: "price", scoreDelta: -0.2 }],
  recommendationShift: "stable",
  recommendedOptionId: "option-a",
  convergenceStatus: "converged",
  originModes: ["experimental"],
  createdAt: "2026-07-25T00:00:00Z",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("readDemoFixtureConfig", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  test("returns the parsed fixture when all variables are present", () => {
    for (const [name, value] of Object.entries(fixtureEnv)) vi.stubEnv(name, value);
    const result = readDemoFixtureConfig();
    expect(result).toEqual({ ok: true, config: demoConfig });
  });

  test("reports every missing variable by name", () => {
    for (const [name, value] of Object.entries(fixtureEnv)) vi.stubEnv(name, value);
    vi.stubEnv("NEXT_PUBLIC_DEMO_GRAPH_ID", "");
    vi.stubEnv("NEXT_PUBLIC_DEMO_PROFILE_VERSION", "not-a-number");
    const result = readDemoFixtureConfig();
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.missing).toContain("NEXT_PUBLIC_DEMO_GRAPH_ID");
      expect(result.missing).toContain("NEXT_PUBLIC_DEMO_PROFILE_VERSION");
    }
  });
});

describe("runDemoFlow", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test("walks csrf → login → session → run → replay with contract headers", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ ok: true, data: { csrfToken: "csrf-token-1" } }))
      .mockResolvedValueOnce(jsonResponse({ ok: true, data: { user: {}, session: {}, memberships: [] } }))
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          data: { memberships: [{ workspaceId: runData.workspaceId, workspaceName: "Demo" }] },
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ ok: true, data: runData }, 201))
      .mockResolvedValueOnce(jsonResponse({ ok: true, data: runData }));

    const steps: string[] = [];
    const result = await runDemoFlow(
      demoConfig,
      { email: "demo@example.test", password: "demo-password" },
      (step) => steps.push(step),
    );

    expect(steps).toEqual(["csrf", "login", "session", "run", "replay"]);
    expect(result.workspaceId).toBe(runData.workspaceId);
    expect(result.run.inputHash).toBe(runData.inputHash);
    expect(result.replay.simulationRunId).toBe(runData.simulationRunId);
    expect(result.idempotencyReplay).toBe(false);

    const [csrfCall, loginCall, sessionCall, runCall, replayCall] = fetchMock.mock.calls;
    expect(csrfCall[0]).toBe("/api/auth/csrf");
    expect(loginCall[0]).toBe("/api/auth/login");
    expect(sessionCall[0]).toBe("/api/auth/session");
    expect(runCall[0]).toBe(
      `/api/workspaces/${runData.workspaceId}/simulations/${demoConfig.graphId}/runs`,
    );
    expect(replayCall[0]).toBe(
      `/api/workspaces/${runData.workspaceId}/simulations/${demoConfig.graphId}/runs/${runData.simulationRunId}`,
    );

    // Every request stays same-origin /api with cookies included.
    for (const [, init] of fetchMock.mock.calls) {
      expect((init as RequestInit).credentials).toBe("include");
    }

    const loginInit = loginCall[1] as RequestInit;
    expect((loginInit.headers as Record<string, string>)["X-CSRF-Token"]).toBe("csrf-token-1");

    const runInit = runCall[1] as RequestInit;
    const runHeaders = runInit.headers as Record<string, string>;
    expect(runHeaders["X-CSRF-Token"]).toBe("csrf-token-1");
    expect(runHeaders["Idempotency-Key"]).toMatch(/^demo-/);
    expect(JSON.parse(runInit.body as string)).toEqual({
      mode: "experimental",
      graphVersionId: demoConfig.graphVersionId,
      strategyVersionId: demoConfig.strategyVersionId,
      scenarioVersionId: demoConfig.scenarioVersionId,
      scoreDefinitionId: demoConfig.scoreDefinitionId,
      decisionMakerProfileId: demoConfig.decisionMakerProfileId,
      decisionMakerProfileVersion: demoConfig.decisionMakerProfileVersion,
    });
  });

  test("surfaces the envelope error code and message on failure", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ ok: true, data: { csrfToken: "csrf-token-1" } }))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            ok: false,
            error: { code: "AUTH_INVALID_CREDENTIALS", message: "Email or password is incorrect." },
          },
          401,
        ),
      );

    const attempt = runDemoFlow(demoConfig, { email: "demo@example.test", password: "wrong" });
    await expect(attempt).rejects.toMatchObject({
      code: "AUTH_INVALID_CREDENTIALS",
      status: 401,
    });
    await expect(
      runDemoFlow(demoConfig, { email: "demo@example.test", password: "wrong" }).catch((error) => {
        expect(error).toBeInstanceOf(DemoApiError);
        throw error;
      }),
    ).rejects.toBeDefined();
  });

  test("stops on network failure with a NETWORK_ERROR code", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    await expect(
      runDemoFlow(demoConfig, { email: "demo@example.test", password: "demo-password" }),
    ).rejects.toMatchObject({ code: "NETWORK_ERROR" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  test("flags idempotent replays from the response meta", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ ok: true, data: { csrfToken: "csrf-token-1" } }))
      .mockResolvedValueOnce(jsonResponse({ ok: true, data: {} }))
      .mockResolvedValueOnce(
        jsonResponse({ ok: true, data: { memberships: [{ workspaceId: runData.workspaceId }] } }),
      )
      .mockResolvedValueOnce(
        jsonResponse({ ok: true, data: runData, meta: { idempotencyReplay: true } }, 201),
      )
      .mockResolvedValueOnce(jsonResponse({ ok: true, data: runData }));

    const result = await runDemoFlow(demoConfig, {
      email: "demo@example.test",
      password: "demo-password",
    });
    expect(result.idempotencyReplay).toBe(true);
  });
});
