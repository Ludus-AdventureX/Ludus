/** @vitest-environment jsdom */

import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import {
  DemoApiError,
  establishGuestSession,
  fetchCsrfToken,
  fetchGuestSession,
  runSimulation,
  type DemoFixtureIds,
  type SimulationRunData,
} from "../lib/demo/simulationDemo";

const guestFixture: DemoFixtureIds = {
  graphId: "11111111-1111-4111-8111-111111111111",
  graphVersionId: "22222222-2222-4222-8222-222222222222",
  strategyVersionId: "33333333-3333-4333-8333-333333333333",
  scenarioVersionId: "44444444-4444-4444-8444-444444444444",
  scoreDefinitionId: "55555555-5555-4555-8555-555555555555",
  decisionMakerProfileId: "66666666-6666-4666-8666-666666666666",
  decisionMakerProfileVersion: 1,
};

const runData: SimulationRunData = {
  simulationRunId: "77777777-7777-4777-8777-777777777777",
  workspaceId: "88888888-8888-4888-8888-888888888888",
  decisionCaseId: "99999999-9999-4999-8999-999999999999",
  graphId: guestFixture.graphId,
  graphVersionId: guestFixture.graphVersionId,
  strategyVersionId: guestFixture.strategyVersionId,
  scenarioVersionId: guestFixture.scenarioVersionId,
  scoreDefinitionId: guestFixture.scoreDefinitionId,
  scoreDefinitionVersion: "1",
  decisionMakerProfileId: guestFixture.decisionMakerProfileId,
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

describe("fetchCsrfToken / fetchGuestSession", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test("fetchCsrfToken reads the double-submit token from the envelope", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true, data: { csrfToken: "csrf-abc" } }));
    const token = await fetchCsrfToken();
    expect(token).toBe("csrf-abc");
    expect(fetchMock).toHaveBeenCalledWith("/api/auth/csrf", expect.objectContaining({ credentials: "include" }));
  });

  test("fetchGuestSession posts with X-CSRF-Token and parses the payload", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        ok: true,
        data: { workspaceId: runData.workspaceId, ...guestFixture },
      }),
    );
    const session = await fetchGuestSession("csrf-abc");
    expect(session.workspaceId).toBe(runData.workspaceId);
    expect(session.fixture).toEqual(guestFixture);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/auth/guest");
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>)["X-CSRF-Token"]).toBe("csrf-abc");
    expect(init.credentials).toBe("include");
  });

  test("fetchGuestSession throws GUEST_PAYLOAD_INVALID when workspaceId is missing", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true, data: { ...guestFixture } }));
    await expect(fetchGuestSession("csrf-abc")).rejects.toMatchObject({
      code: "GUEST_PAYLOAD_INVALID",
      status: 200,
    });
  });

  test("fetchGuestSession reports every missing fixture field", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ ok: true, data: { workspaceId: runData.workspaceId } }),
    );
    const error = await fetchGuestSession("csrf-abc").catch((e) => e);
    expect(error).toBeInstanceOf(DemoApiError);
    expect(error.message).toContain("graphId");
    expect(error.message).toContain("decisionMakerProfileVersion");
  });
});

describe("establishGuestSession", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test("walks csrf → guest and returns the workspace + fixture", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ ok: true, data: { csrfToken: "csrf-abc" } }))
      .mockResolvedValueOnce(
        jsonResponse({
          ok: true,
          data: { workspaceId: runData.workspaceId, ...guestFixture },
        }),
      );

    const steps: string[] = [];
    const session = await establishGuestSession((step) => steps.push(step));

    expect(steps).toEqual(["csrf", "guest"]);
    expect(session.workspaceId).toBe(runData.workspaceId);
    expect(session.fixture).toEqual(guestFixture);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/auth/csrf");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/auth/guest");
  });
});

describe("runSimulation", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test("walks csrf → run → replay with contract headers and same-origin /api", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ ok: true, data: { csrfToken: "csrf-abc" } }))
      .mockResolvedValueOnce(jsonResponse({ ok: true, data: runData }, 201))
      .mockResolvedValueOnce(jsonResponse({ ok: true, data: runData }));

    const steps: string[] = [];
    const result = await runSimulation(runData.workspaceId, guestFixture, (step) => steps.push(step));

    expect(steps).toEqual(["csrf", "run", "replay"]);
    expect(result.run.inputHash).toBe(runData.inputHash);
    expect(result.replay.simulationRunId).toBe(runData.simulationRunId);
    expect(result.idempotencyReplay).toBe(false);

    const [csrfCall, runCall, replayCall] = fetchMock.mock.calls;
    expect(csrfCall[0]).toBe("/api/auth/csrf");
    expect(runCall[0]).toBe(
      `/api/workspaces/${runData.workspaceId}/simulations/${guestFixture.graphId}/runs`,
    );
    expect(replayCall[0]).toBe(
      `/api/workspaces/${runData.workspaceId}/simulations/${guestFixture.graphId}/runs/${runData.simulationRunId}`,
    );

    for (const [, init] of fetchMock.mock.calls) {
      expect((init as RequestInit).credentials).toBe("include");
    }

    const runInit = runCall[1] as RequestInit;
    const runHeaders = runInit.headers as Record<string, string>;
    expect(runHeaders["X-CSRF-Token"]).toBe("csrf-abc");
    expect(runHeaders["Idempotency-Key"]).toMatch(/^demo-/);
    expect(JSON.parse(runInit.body as string)).toEqual({
      mode: "experimental",
      graphVersionId: guestFixture.graphVersionId,
      strategyVersionId: guestFixture.strategyVersionId,
      scenarioVersionId: guestFixture.scenarioVersionId,
      scoreDefinitionId: guestFixture.scoreDefinitionId,
      decisionMakerProfileId: guestFixture.decisionMakerProfileId,
      decisionMakerProfileVersion: guestFixture.decisionMakerProfileVersion,
    });
  });

  test("surfaces envelope errors with their stable code", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ ok: true, data: { csrfToken: "csrf-abc" } }))
      .mockResolvedValueOnce(
        jsonResponse(
          { ok: false, error: { code: "CASE_NOT_FOUND", message: "Fixture scope missing." } },
          404,
        ),
      );
    await expect(runSimulation(runData.workspaceId, guestFixture)).rejects.toMatchObject({
      code: "CASE_NOT_FOUND",
      status: 404,
    });
  });

  test("flags idempotent replays from the response meta", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ ok: true, data: { csrfToken: "csrf-abc" } }))
      .mockResolvedValueOnce(
        jsonResponse({ ok: true, data: runData, meta: { idempotencyReplay: true } }, 201),
      )
      .mockResolvedValueOnce(jsonResponse({ ok: true, data: runData }));

    const result = await runSimulation(runData.workspaceId, guestFixture);
    expect(result.idempotencyReplay).toBe(true);
  });
});
