/** @vitest-environment jsdom */

// Client-sequence battery for the in-case deep-analysis launch loop
// (lib/shell/decisionLoop.ts): call order, paths, CSRF/idempotency headers,
// charter body invariants, terminal polling and error mapping.

import { describe, expect, test } from "vitest";

import {
  DecisionLoopError,
  buildCharterBody,
  launchAnalysisForCase,
  pollRunUntilTerminal,
  watchRunUntilTerminal,
  type RunEventSourceLike,
} from "../lib/shell/decisionLoop";

type Call = { path: string; method: string; headers: Record<string, string>; body: unknown };

function jsonResponse(status: number, payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function scriptedFetch(script: Array<{ match: RegExp; status: number; payload: unknown }>, calls: Call[]) {
  let index = 0;
  const impl: typeof fetch = async (input, init) => {
    const path = typeof input === "string" ? input : input instanceof URL ? input.pathname : input.url;
    const step = script[index];
    if (!step) throw new Error(`unexpected extra request: ${path}`);
    index += 1;
    if (!step.match.test(path)) throw new Error(`request ${index} was ${path}, expected ${step.match}`);
    calls.push({
      path,
      method: init?.method ?? "GET",
      headers: Object.fromEntries(Object.entries((init?.headers ?? {}) as Record<string, string>)),
      body: init?.body ? JSON.parse(String(init.body)) : null,
    });
    return jsonResponse(step.status, step.payload);
  };
  return impl;
}

const WS = "11111111-1111-4111-8111-111111111111";
const CASE = "22222222-2222-4222-8222-222222222222";

describe("launchAnalysisForCase", () => {
  test("drives csrf -> case seed -> charter -> confirm -> run with the frozen wire shape", async () => {
    const calls: Call[] = [];
    const fetchImpl = scriptedFetch(
      [
        { match: /\/api\/auth\/csrf$/, status: 200, payload: { ok: true, data: { csrfToken: "tok-1" } } },
        {
          match: new RegExp(`/api/workspaces/${WS}/cases/${CASE}$`),
          status: 200,
          payload: { ok: true, data: { decisionSubjectId: "sub-1", decisionQuestion: "进入救援市场吗？" } },
        },
        {
          match: new RegExp(`/api/workspaces/${WS}/cases/${CASE}/analysis-charters$`),
          status: 201,
          payload: { ok: true, data: { charterId: "ch-1" } },
        },
        {
          match: new RegExp(`/api/workspaces/${WS}/analysis-charters/ch-1/confirm$`),
          status: 200,
          payload: { ok: true, data: {} },
        },
        {
          match: new RegExp(`/api/workspaces/${WS}/analysis-charters/ch-1/runs$`),
          status: 201,
          payload: { ok: true, data: { analysisRunId: "run-1", status: "queued" } },
        },
      ],
      calls,
    );

    const steps: string[] = [];
    const launched = await launchAnalysisForCase(WS, CASE, {
      fetchImpl,
      onStep: (step) => steps.push(step),
    });

    expect(launched).toEqual({ charterId: "ch-1", analysisRunId: "run-1", status: "queued" });
    expect(steps).toEqual(["csrf", "seed", "charter", "confirm", "run"]);

    const charterCall = calls[2];
    expect(charterCall.method).toBe("POST");
    expect(charterCall.headers["X-CSRF-Token"]).toBe("tok-1");
    const body = charterCall.body as Record<string, unknown>;
    expect(body.decisionSubjectId).toBe("sub-1");
    expect(body.analysisLevel).toBe("focused");
    expect(body.formalAnalysisAllowed).toBe(true);
    expect(body.decisionQuestion).toBe("进入救援市场吗？");

    const runCall = calls[4];
    expect(runCall.headers["X-CSRF-Token"]).toBe("tok-1");
    expect(runCall.headers["Idempotency-Key"]).toMatch(/^loop-/);
    const runBody = runCall.body as Record<string, unknown>;
    expect(runBody.analysisLevel).toBe("focused");
    expect(String(runBody.runManifestHash)).toMatch(/^sha256:[0-9a-f]{64}$/);
    expect(String(runBody.cynefinGateResultId)).toMatch(/^[0-9a-f-]{36}$/);
  });

  test("maps a backend error envelope to DecisionLoopError with the server code", async () => {
    const fetchImpl: typeof fetch = async () =>
      jsonResponse(403, { ok: false, error: { code: "CSRF_REJECTED", message: "CSRF 校验失败" } });
    await expect(launchAnalysisForCase(WS, CASE, { fetchImpl })).rejects.toMatchObject({
      name: "DecisionLoopError",
      code: "CSRF_REJECTED",
      status: 403,
    });
  });

  test("maps a network failure to NETWORK_ERROR", async () => {
    const fetchImpl: typeof fetch = async () => {
      throw new TypeError("fetch failed");
    };
    await expect(launchAnalysisForCase(WS, CASE, { fetchImpl })).rejects.toMatchObject({
      code: "NETWORK_ERROR",
      status: 0,
    });
  });
});

describe("pollRunUntilTerminal", () => {
  test("polls until a terminal status and reports every tick", async () => {
    const snapshots = [
      { status: "planning", progress: 0.14, lastResumableStage: null },
      { status: "validating", progress: 0.86, lastResumableStage: null },
      { status: "blocked", progress: 0.86, lastResumableStage: null },
    ];
    let index = 0;
    const fetchImpl: typeof fetch = async () => jsonResponse(200, { ok: true, data: snapshots[index++] });

    const ticks: string[] = [];
    const final = await pollRunUntilTerminal(WS, "run-1", {
      fetchImpl,
      intervalMs: 1,
      onTick: (snapshot) => ticks.push(snapshot.status),
    });

    expect(final.status).toBe("blocked");
    expect(ticks).toEqual(["planning", "validating", "blocked"]);
  });

  test("times out fail-closed instead of spinning forever", async () => {
    const fetchImpl: typeof fetch = async () =>
      jsonResponse(200, { ok: true, data: { status: "queued", progress: 0, lastResumableStage: null } });
    await expect(
      pollRunUntilTerminal(WS, "run-1", { fetchImpl, intervalMs: 1, maxTicks: 3 }),
    ).rejects.toBeInstanceOf(DecisionLoopError);
  });
});

describe("watchRunUntilTerminal", () => {
  test("SSE events drive status re-reads to the terminal verdict", async () => {
    const snapshots = [
      { status: "planning", progress: 0.14, lastResumableStage: null },
      { status: "validating", progress: 0.86, lastResumableStage: null },
      { status: "ready", progress: 1.0, lastResumableStage: null },
    ];
    let index = 0;
    const fetchImpl: typeof fetch = async () => jsonResponse(200, { ok: true, data: snapshots[Math.min(index++, 2)] });

    const listeners: Array<() => void> = [];
    let closed = false;
    const source: RunEventSourceLike = {
      addEventListener: (_type, listener) => listeners.push(() => listener({})),
      close: () => {
        closed = true;
      },
    };
    const factory = (url: string) => {
      expect(url).toMatch(/\/analyses\/run-1\/events$/);
      // Emit one event per pending snapshot shortly after subscription.
      setTimeout(() => listeners.forEach((fire) => fire()), 1);
      setTimeout(() => listeners.forEach((fire) => fire()), 5);
      return source;
    };

    const ticks: string[] = [];
    const final = await watchRunUntilTerminal(WS, "run-1", {
      fetchImpl,
      factory,
      safetyPollMs: 60,
      onTick: (snapshot) => ticks.push(snapshot.status),
    });

    expect(final.status).toBe("ready");
    expect(ticks).toEqual(["planning", "validating", "ready"]);
    expect(closed).toBe(true);
  });

  test("falls back to plain polling when no EventSource factory exists", async () => {
    const snapshots = [
      { status: "queued", progress: 0, lastResumableStage: null },
      { status: "blocked", progress: 0.86, lastResumableStage: null },
    ];
    let index = 0;
    const fetchImpl: typeof fetch = async () => jsonResponse(200, { ok: true, data: snapshots[Math.min(index++, 1)] });

    const final = await watchRunUntilTerminal(WS, "run-1", { fetchImpl, factory: null });
    expect(final.status).toBe("blocked");
  });
});

describe("buildCharterBody", () => {
  test("pins the focused-level invariants the backend validated live", () => {
    const body = buildCharterBody("sub-9", "问题？");
    expect(body.analysisLevel).toBe("focused");
    expect(body.requiredStrategicLensTypes).toEqual([]);
    expect(body.formalAnalysisAllowed).toBe(true);
    expect(body.caseSnapshotHash).toMatch(/^sha256:[0-9a-f]{64}$/);
    expect(body.dossierSnapshotHash).toMatch(/^sha256:[0-9a-f]{64}$/);
  });
});
