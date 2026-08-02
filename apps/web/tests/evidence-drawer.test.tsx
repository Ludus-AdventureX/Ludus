/** @vitest-environment jsdom */

// Task 11 B2 — evidence provenance line tests. Wire fixtures below are
// transcribed field-by-field from services/api/app/evidence/schemas_api.py
// (camelCase CanonicalModel views); routes are the 7 mounted evidence GETs
// + the run event stream (10-api-and-events.md「证据溯源与冲突读取 API」).

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { EvidenceDrawer, UNIFORM_NOT_FOUND_COPY } from "../components/quality/EvidenceDrawer";
import { EvidenceDrawerTrigger } from "../components/quality/EvidenceDrawerTrigger";
import type {
  ConflictListView,
  EvidenceDirectionView,
  EvidenceItemView,
  EvidenceProvenanceView,
  EvidenceEventSourceFactory,
  QualityDimensionsView,
  RunEvidenceListView,
  SameSourceGroupView
} from "../lib/api/evidence";
import { evidenceAnchorsRouteAvailable, resolveEvidenceAnchors } from "../lib/api/evidence";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// --- Fixtures (schemas_api.py wire shapes, camelCase) ------------------------

const anchors = { workspaceId: "ws_1", analysisRunId: "run_1" };

const quality: QualityDimensionsView = {
  authenticity: 0.91,
  sourceQuality: 0.84,
  relevance: 0.86,
  freshness: 0.62,
  applicability: 0.7,
  independence: 0.33,
  extractionReliability: 0.95,
  biasFlags: ["vendor_marketing"],
  completenessWarnings: ["missing_denominator"],
  conflictGroupIds: ["cg_1"],
  verdict: "conditional",
  reasonCodes: ["single_origin_cluster"],
  assessedAt: "2026-07-25T10:00:00+08:00"
};

function makeItem(overrides: Partial<EvidenceItemView>): EvidenceItemView {
  return {
    id: "ev_1",
    workspaceId: "ws_1",
    decisionCaseId: "case_1",
    analysisRunId: "run_1",
    title: "行业访谈纪要：远程侦察需求",
    url: "https://example.org/interviews",
    filePath: null,
    sourceDomain: "example.org",
    sourceGrade: "L1_primary",
    snippet: "受访的五支救援队中有三支提出进入前远程侦察的需求。",
    sourceRecordId: "sr_1",
    sourceSpanIds: ["span_1"],
    supportsClaimIds: ["claim_a"],
    contradictsClaimIds: [],
    publishedAt: null,
    retrievedAt: "2026-07-25T09:00:00+08:00",
    freshnessStatus: "fresh",
    relevance: 0.86,
    bias: "sample_bias",
    conflictGroupId: "cg_1",
    independentSourceGroupId: "isg_1",
    verdict: "conditional",
    verdictReasonCodes: ["single_origin_cluster"],
    applicabilityLimits: ["仅适用于城市搜救场景"],
    originMode: "live",
    rawArtifactId: "raw_1",
    qualityAssessmentId: "qa_1",
    ...overrides
  };
}

const itemOne = makeItem({});
const itemTwo = makeItem({
  id: "ev_2",
  title: "监管通报：设备准入限制",
  sourceGrade: "L2_reputable",
  supportsClaimIds: [],
  contradictsClaimIds: ["claim_a"],
  verdict: "accepted",
  verdictReasonCodes: [],
  applicabilityLimits: []
});

const runEvidence: RunEvidenceListView = { analysisRunId: "run_1", items: [itemOne, itemTwo] };

const conflicts: ConflictListView = {
  analysisRunId: "run_1",
  conflicts: [
    {
      id: "cr_1",
      fromEvidenceItemId: "ev_1",
      toEvidenceItemId: "ev_2",
      groupId: "cg_1",
      rationale: "口径不同：访谈针对需求，通报针对准入。"
    }
  ]
};

const provenance: EvidenceProvenanceView = {
  evidenceItemId: "ev_1",
  rawArtifact: {
    id: "raw_1",
    kind: "web_page",
    mediaType: "text/html",
    byteSize: 20480,
    sha256: "c3ab8ff13720e8ad9047dd39466b3c8974e592c2fa383d4a3960714caef0c4f2",
    sourceUrl: "https://example.org/interviews",
    originMode: "live",
    createdAt: "2026-07-25T09:00:00+08:00"
  },
  sourceRecord: {
    id: "sr_1",
    kind: "web_page",
    sourceScope: "run_frozen",
    canonicalUri: "https://example.org/interviews",
    title: "行业访谈纪要",
    contentHash: "hash_sr_1",
    sourceVersion: "v1",
    originMode: "live",
    rawArtifactId: "raw_1",
    spans: [
      {
        id: "span_1",
        locator: { paragraph: 3 },
        quote: "三支救援队提出进入前远程侦察需求。",
        quoteHash: "hash_span_1"
      }
    ]
  },
  quality
};

const direction: EvidenceDirectionView = {
  evidenceItemId: "ev_1",
  supportsClaimIds: ["claim_a"],
  contradictsClaimIds: [],
  verdict: "conditional"
};

// Three citations from one origin = ONE independent source.
const sameSourceGroup: SameSourceGroupView = {
  independentSourceGroupId: "isg_1",
  memberEvidenceItemIds: ["ev_1", "ev_3", "ev_4"],
  independentSourceCountContribution: 1
};

// --- Test plumbing -----------------------------------------------------------

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body
  } as unknown as Response;
}

const notFoundEnvelope = { ok: false, error: { code: "CASE_NOT_FOUND", message: "Case material not found." } };

function makeRouteFetch(routes: Record<string, () => Response>): ReturnType<typeof vi.fn> {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const handler = routes[url];
    if (!handler) return jsonResponse(404, notFoundEnvelope);
    return handler();
  });
}

const happyRoutes: Record<string, () => Response> = {
  "/api/workspaces/ws_1/analyses/run_1/evidence": () => jsonResponse(200, { ok: true, data: runEvidence }),
  "/api/workspaces/ws_1/analyses/run_1/evidence-conflicts": () => jsonResponse(200, { ok: true, data: conflicts }),
  "/api/workspaces/ws_1/evidence/ev_1": () => jsonResponse(200, { ok: true, data: itemOne }),
  "/api/workspaces/ws_1/evidence/ev_1/quality": () => jsonResponse(200, { ok: true, data: quality }),
  "/api/workspaces/ws_1/evidence/ev_1/provenance": () => jsonResponse(200, { ok: true, data: provenance }),
  "/api/workspaces/ws_1/evidence/ev_1/direction": () => jsonResponse(200, { ok: true, data: direction }),
  "/api/workspaces/ws_1/evidence/ev_1/same-source-group": () =>
    jsonResponse(200, { ok: true, data: sameSourceGroup }),
  // P1: strategic-lens read surface (routes.py _lens_summary / _lens_detail).
  "/api/workspaces/ws_1/analyses/run_1/strategic-lenses": () =>
    jsonResponse(200, {
      ok: true,
      data: [
        {
          id: "lens_porter",
          lensType: "porter_five_forces",
          producerRole: "research",
          status: "ready",
          methodId: "hardtech-market-direction",
          methodVersion: "1.1.0",
          methodContentHash: "hash_m",
          promptVersion: "1.0.0",
          schemaVersion: "1.0.0",
          contentHash: "hash_p",
          originModes: ["live"],
          referenceCounts: { claimCount: 1, evidenceCount: 1, assumptionCount: 0 },
          validationAcceptedAt: "2026-07-25T11:00:00+08:00",
          createdAt: "2026-07-25T10:30:00+08:00"
        },
        {
          id: "lens_scenario",
          lensType: "scenario_planning",
          producerRole: "synthesis",
          status: "ready",
          methodId: "hardtech-market-direction",
          methodVersion: "1.1.0",
          methodContentHash: "hash_m",
          promptVersion: "1.0.0",
          schemaVersion: "1.0.0",
          contentHash: "hash_s",
          originModes: ["live"],
          referenceCounts: { claimCount: 0, evidenceCount: 0, assumptionCount: 0 },
          validationAcceptedAt: "2026-07-25T11:00:00+08:00",
          createdAt: "2026-07-25T10:30:00+08:00"
        }
      ]
    }),
  "/api/workspaces/ws_1/analyses/run_1/strategic-lenses/lens_porter": () =>
    jsonResponse(200, {
      ok: true,
      data: {
        id: "lens_porter",
        lensType: "porter_five_forces",
        producerRole: "research",
        status: "ready",
        methodId: "hardtech-market-direction",
        methodVersion: "1.1.0",
        methodContentHash: "hash_m",
        promptVersion: "1.0.0",
        schemaVersion: "1.0.0",
        contentHash: "hash_p",
        originModes: ["live"],
        referenceCounts: { claimCount: 1, evidenceCount: 1, assumptionCount: 0 },
        validationAcceptedAt: "2026-07-25T11:00:00+08:00",
        createdAt: "2026-07-25T10:30:00+08:00",
        decisionCaseId: "case_1",
        analysisRunId: "run_1",
        charterId: "ch_1",
        claimRefs: ["claim_a"],
        evidenceRefs: ["ev_1"],
        assumptionRefs: [],
        content: {}
      }
    }),
  "/api/workspaces/ws_1/analyses/run_1/strategic-lenses/lens_scenario": () =>
    jsonResponse(200, {
      ok: true,
      data: {
        id: "lens_scenario",
        lensType: "scenario_planning",
        producerRole: "synthesis",
        status: "ready",
        methodId: "hardtech-market-direction",
        methodVersion: "1.1.0",
        methodContentHash: "hash_m",
        promptVersion: "1.0.0",
        schemaVersion: "1.0.0",
        contentHash: "hash_s",
        originModes: ["live"],
        referenceCounts: { claimCount: 0, evidenceCount: 0, assumptionCount: 0 },
        validationAcceptedAt: "2026-07-25T11:00:00+08:00",
        createdAt: "2026-07-25T10:30:00+08:00",
        decisionCaseId: "case_1",
        analysisRunId: "run_1",
        charterId: "ch_1",
        claimRefs: [],
        evidenceRefs: [],
        assumptionRefs: [],
        content: {}
      }
    })
};

type FakeSource = {
  url: string;
  listeners: Map<string, (event: MessageEvent) => void>;
  closed: boolean;
};

function makeFakeEventSourceFactory(): { factory: EvidenceEventSourceFactory; sources: FakeSource[] } {
  const sources: FakeSource[] = [];
  const factory: EvidenceEventSourceFactory = (url) => {
    const source: FakeSource = { url, listeners: new Map(), closed: false };
    sources.push(source);
    return {
      addEventListener(type, listener) {
        source.listeners.set(type, listener);
      },
      close() {
        source.closed = true;
      }
    };
  };
  return { factory, sources };
}

function renderDrawer(overrides: Partial<Parameters<typeof EvidenceDrawer>[0]> = {}) {
  const onClose = vi.fn();
  const view = render(
    <EvidenceDrawer
      open
      onClose={onClose}
      anchors={anchors}
      fetchImpl={makeRouteFetch(happyRoutes) as unknown as typeof fetch}
      eventSourceFactory={null}
      {...overrides}
    />
  );
  return { onClose, ...view };
}

// --- Anchors resolution + availability switch --------------------------------

describe("evidence anchors availability (READ-01 flip)", () => {
  test("the case→run resolution route shipped; the switch is ON", () => {
    expect(evidenceAnchorsRouteAvailable).toBe(true);
  });

  test("resolveEvidenceAnchors picks the newest run and degrades to null honestly", async () => {
    const anchorsFetch = vi.fn(async () =>
      ({
        ok: true,
        status: 200,
        json: async () => ({
          ok: true,
          data: {
            decisionCaseId: "case_1",
            items: [
              { analysisRunId: "run_new", decisionCaseId: "case_1", charterId: "ch", analysisLevel: "full", status: "ready", caseVersion: 1, createdAt: "2026-07-25", completedAt: null }
            ]
          }
        })
      }) as unknown as Response
    );
    await expect(
      resolveEvidenceAnchors("ws_1", "case_1", anchorsFetch as unknown as typeof fetch)
    ).resolves.toEqual({ workspaceId: "ws_1", analysisRunId: "run_new" });
    expect(String((anchorsFetch.mock.calls as unknown[][])[0]?.[0])).toBe(
      "/api/workspaces/ws_1/cases/case_1/analyses"
    );

    const emptyFetch = vi.fn(async () =>
      ({ ok: true, status: 200, json: async () => ({ ok: true, data: { decisionCaseId: "case_1", items: [] } }) }) as unknown as Response
    );
    await expect(
      resolveEvidenceAnchors("ws_1", "case_1", emptyFetch as unknown as typeof fetch)
    ).resolves.toBeNull();

    const notFoundFetch = vi.fn(async () =>
      ({ ok: false, status: 404, json: async () => ({ ok: false, error: { code: "CASE_NOT_FOUND", message: "Case material not found." } }) }) as unknown as Response
    );
    await expect(
      resolveEvidenceAnchors("ws_1", "case_1", notFoundFetch as unknown as typeof fetch)
    ).resolves.toBeNull();
  });

  test("trigger without a workspace anchor keeps the honest gap state and performs ZERO fetches", async () => {
    const user = userEvent.setup();
    const fetchSpy = vi.fn();
    render(<EvidenceDrawerTrigger fetchImpl={fetchSpy as unknown as typeof fetch} eventSourceFactory={null} />);

    const trigger = screen.getByRole("button", { name: "查看证据溯源" });
    expect(trigger.closest('[data-phase-slot="evidence-drawer-trigger"]')).not.toBeNull();

    await user.click(trigger);
    expect(await screen.findByRole("dialog", { name: "证据溯源" })).toBeInTheDocument();
    expect(
      screen.getByText(/完成一次深度分析后，证据保管链会出现在这里；当前没有可展示的证据记录/)
    ).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

// --- Ready flow ---------------------------------------------------------------

describe("evidence drawer ready flow", () => {
  test("renders the run ledger with L1-L6 category badges and the conflict list", async () => {
    renderDrawer();

    expect(await screen.findByRole("button", { name: /行业访谈纪要：远程侦察需求/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /监管通报：设备准入限制/ })).toBeInTheDocument();
    // Source CATEGORY, not a credibility score.
    expect(screen.getByText("一手来源")).toBeInTheDocument();
    expect(screen.getByText("权威来源")).toBeInTheDocument();

    const conflictsRegion = screen.getByRole("region", { name: "冲突列表" });
    expect(within(conflictsRegion).getByText("口径不同：访谈针对需求，通报针对准入。")).toBeInTheDocument();
    expect(within(conflictsRegion).getByText(/冲突组 cg_1/)).toBeInTheDocument();
  });

  test("item selection loads the five per-item reads and shows verdict/rationale/limits + orthogonal dimensions", async () => {
    const user = userEvent.setup();
    const fetchImpl = makeRouteFetch(happyRoutes);
    renderDrawer({ fetchImpl: fetchImpl as unknown as typeof fetch });

    await user.click(await screen.findByRole("button", { name: /行业访谈纪要：远程侦察需求/ }));

    const detail = await screen.findByRole("article");
    // Four-tier verdict with machine reason codes and mandatory limits.
    expect(within(detail).getAllByText("结论 有条件采纳").length).toBeGreaterThan(0);
    expect(within(detail).getAllByText("single_origin_cluster").length).toBeGreaterThan(0);
    expect(within(detail).getByText("仅适用于城市搜救场景")).toBeInTheDocument();

    // Seven orthogonal dimensions rendered separately as decimals.
    const qualityPanel = within(detail).getByRole("region", { name: "正交质量维度" });
    for (const label of ["真实性", "来源质量", "相关性", "时效", "适用性", "独立性", "提取可靠性"]) {
      expect(within(qualityPanel).getByText(label)).toBeInTheDocument();
    }
    expect(within(qualityPanel).getByText("0.33")).toBeInTheDocument();
    expect(within(qualityPanel).getByText("vendor_marketing")).toBeInTheDocument();
    expect(within(qualityPanel).getByText("missing_denominator")).toBeInTheDocument();

    // Provenance chain: raw artifact pointer (hash, no disk path) + frozen span.
    const chain = within(detail).getByRole("region", { name: "溯源链" });
    expect(
      within(chain).getByText("c3ab8ff13720e8ad9047dd39466b3c8974e592c2fa383d4a3960714caef0c4f2")
    ).toBeInTheDocument();
    expect(within(chain).getByText("三支救援队提出进入前远程侦察需求。")).toBeInTheDocument();

    // Same-source group: three citations = ONE independent source.
    const group = within(detail).getByRole("region", { name: "同源组" });
    expect(within(group).getByText(/组内 3 条引用共计 1 个独立来源/)).toBeInTheDocument();

    // Direction: support and oppose stay separate.
    const directionRegion = within(detail).getByRole("region", { name: "支持与反对方向" });
    expect(within(directionRegion).getByText("claim_a")).toBeInTheDocument();

    const calledPaths = fetchImpl.mock.calls.map((call) => String(call[0]));
    for (const path of [
      "/api/workspaces/ws_1/evidence/ev_1",
      "/api/workspaces/ws_1/evidence/ev_1/quality",
      "/api/workspaces/ws_1/evidence/ev_1/provenance",
      "/api/workspaces/ws_1/evidence/ev_1/direction",
      "/api/workspaces/ws_1/evidence/ev_1/same-source-group"
    ]) {
      expect(calledPaths).toContain(path);
    }
  });

  test("no percentage and no aggregate credibility value anywhere in the ready UI", async () => {
    const user = userEvent.setup();
    const { container } = renderDrawer();

    await user.click(await screen.findByRole("button", { name: /行业访谈纪要：远程侦察需求/ }));
    await screen.findByRole("article");

    expect(container.textContent).not.toMatch(/\d+\s*%/);
    expect(container.textContent).not.toContain("%");
    expect(container.textContent).not.toMatch(/总可信度[:：]\s*\d/);
  });
});

// --- State handling -----------------------------------------------------------

describe("evidence drawer state handling", () => {
  test("401 renders the session copy without leaking material facts", async () => {
    renderDrawer({
      fetchImpl: makeRouteFetch({
        "/api/workspaces/ws_1/analyses/run_1/evidence": () =>
          jsonResponse(401, { ok: false, error: { code: "AUTH_REQUIRED", message: "Authentication required." } }),
        "/api/workspaces/ws_1/analyses/run_1/evidence-conflicts": () =>
          jsonResponse(401, { ok: false, error: { code: "AUTH_REQUIRED", message: "Authentication required." } })
      }) as unknown as typeof fetch
    });

    expect(await screen.findByText(/尚未登录：登录后这里会展示该 Run 的真实证据账本/)).toBeInTheDocument();
  });

  test("uniform 404 shows ONE anti-enumeration copy — identical for missing and cross-tenant ids, no id echo", async () => {
    // Missing run and foreign-workspace run answer byte-identically upstream;
    // the drawer must render the same sentence for both.
    const failing = makeRouteFetch({}); // every path → CASE_NOT_FOUND
    const first = render(
      <EvidenceDrawer
        open
        onClose={vi.fn()}
        anchors={{ workspaceId: "ws_1", analysisRunId: "run_missing" }}
        fetchImpl={failing as unknown as typeof fetch}
        eventSourceFactory={null}
      />
    );
    const firstCopy = (await first.findByRole("alert")).textContent;
    first.unmount();

    const second = render(
      <EvidenceDrawer
        open
        onClose={vi.fn()}
        anchors={{ workspaceId: "ws_foreign", analysisRunId: "run_1" }}
        fetchImpl={failing as unknown as typeof fetch}
        eventSourceFactory={null}
      />
    );
    const secondCopy = (await second.findByRole("alert")).textContent;

    expect(firstCopy).toBe(UNIFORM_NOT_FOUND_COPY);
    expect(secondCopy).toBe(firstCopy);
    expect(firstCopy).not.toContain("run_missing");
    expect(firstCopy).not.toContain("ws_foreign");
    expect(firstCopy).not.toMatch(/不存在，|确实不存在/);
  });

  test("slow network admits the delay and still resolves to real data", async () => {
    let releaseList: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      releaseList = resolve;
    });
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/evidence")) {
        await gate;
        return jsonResponse(200, { ok: true, data: runEvidence });
      }
      if (url.endsWith("/evidence-conflicts")) {
        await gate;
        return jsonResponse(200, { ok: true, data: conflicts });
      }
      return jsonResponse(404, notFoundEnvelope);
    });
    renderDrawer({ fetchImpl: fetchImpl as unknown as typeof fetch, slowThresholdMs: 30 });

    expect(await screen.findByText("网络较慢，仍在读取证据账本…")).toBeInTheDocument();
    releaseList?.();
    expect(await screen.findByRole("button", { name: /行业访谈纪要：远程侦察需求/ })).toBeInTheDocument();
  });

  test("empty ledger renders the honest empty state, not sample evidence", async () => {
    renderDrawer({
      fetchImpl: makeRouteFetch({
        "/api/workspaces/ws_1/analyses/run_1/evidence": () =>
          jsonResponse(200, { ok: true, data: { analysisRunId: "run_1", items: [] } }),
        "/api/workspaces/ws_1/analyses/run_1/evidence-conflicts": () =>
          jsonResponse(200, { ok: true, data: { analysisRunId: "run_1", conflicts: [] } })
      }) as unknown as typeof fetch
    });

    expect(await screen.findByText("该 Run 尚无证据条目；系统不填充示例证据。")).toBeInTheDocument();
    expect(screen.getByText("该 Run 没有已记录的证据冲突。")).toBeInTheDocument();
  });

  test("hostile envelope without data degrades to the error state with retry, then recovers", async () => {
    const user = userEvent.setup();
    let healthy = false;
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (!healthy) return jsonResponse(200, { ok: true });
      return happyRoutes[url] ? happyRoutes[url]() : jsonResponse(404, notFoundEnvelope);
    });
    renderDrawer({ fetchImpl: fetchImpl as unknown as typeof fetch });

    expect(await screen.findByText("证据账本读取失败。")).toBeInTheDocument();
    healthy = true;
    await user.click(screen.getByRole("button", { name: "重试" }));
    expect(await screen.findByRole("button", { name: /行业访谈纪要：远程侦察需求/ })).toBeInTheDocument();
  });
});

// --- SSE passive refresh hook ---------------------------------------------------

describe("citation.added passive refresh hook", () => {
  test("subscribes to the run event stream and quietly re-reads the ledger on citation.added only", async () => {
    const { factory, sources } = makeFakeEventSourceFactory();
    const fetchImpl = makeRouteFetch(happyRoutes);
    const { unmount } = renderDrawer({
      fetchImpl: fetchImpl as unknown as typeof fetch,
      eventSourceFactory: factory
    });

    await screen.findByRole("button", { name: /行业访谈纪要：远程侦察需求/ });
    expect(sources).toHaveLength(1);
    expect(sources[0].url).toBe("/api/workspaces/ws_1/analyses/run_1/events");
    // Reserved hook listens ONLY to citation.added (progress belongs to B1).
    expect(Array.from(sources[0].listeners.keys())).toEqual(["citation.added"]);

    const callsBefore = fetchImpl.mock.calls.length;
    sources[0].listeners.get("citation.added")?.(new MessageEvent("citation.added", { data: "{}" }));
    await waitFor(() => {
      expect(fetchImpl.mock.calls.length).toBe(callsBefore + 2); // evidence + conflicts, quiet
    });
    expect(screen.getByRole("button", { name: /行业访谈纪要：远程侦察需求/ })).toBeInTheDocument();

    unmount();
    expect(sources[0].closed).toBe(true);
  });

  test("a failed quiet refresh never downgrades the displayed ledger", async () => {
    const { factory, sources } = makeFakeEventSourceFactory();
    let poisoned = false;
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (poisoned) return jsonResponse(404, notFoundEnvelope);
      return happyRoutes[url] ? happyRoutes[url]() : jsonResponse(404, notFoundEnvelope);
    });
    renderDrawer({ fetchImpl: fetchImpl as unknown as typeof fetch, eventSourceFactory: factory });

    await screen.findByRole("button", { name: /行业访谈纪要：远程侦察需求/ });
    poisoned = true;
    const callsBefore = fetchImpl.mock.calls.length;
    sources[0].listeners.get("citation.added")?.(new MessageEvent("citation.added", { data: "{}" }));
    await waitFor(() => {
      expect(fetchImpl.mock.calls.length).toBe(callsBefore + 2);
    });
    // Data stays; no alert appears from the quiet path.
    expect(screen.getByRole("button", { name: /行业访谈纪要：远程侦察需求/ })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

// --- Accessibility (ProjectDrawer precedent) -------------------------------------

describe("evidence drawer accessibility", () => {
  test("dialog semantics, initial focus inside, Tab trap cycles, Escape closes", async () => {
    const user = userEvent.setup();
    const { onClose } = renderDrawer();

    const dialog = await screen.findByRole("dialog", { name: "证据溯源" });
    expect(dialog).toHaveAttribute("aria-modal", "true");

    await waitFor(() => {
      expect(dialog.contains(document.activeElement)).toBe(true);
    });

    // Tab keeps focus inside the sheet.
    for (let i = 0; i < 12; i += 1) {
      await user.tab();
      expect(dialog.contains(document.activeElement) || document.activeElement === dialog).toBe(true);
    }
    await user.tab({ shift: true });
    expect(dialog.contains(document.activeElement) || document.activeElement === dialog).toBe(true);

    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });

  test("closing from the trigger returns focus to the trigger button", async () => {
    const user = userEvent.setup();
    render(<EvidenceDrawerTrigger fetchImpl={vi.fn() as unknown as typeof fetch} eventSourceFactory={null} />);

    const trigger = screen.getByRole("button", { name: "查看证据溯源" });
    expect(trigger).toHaveAttribute("aria-haspopup", "dialog");
    await user.click(trigger);
    const dialog = await screen.findByRole("dialog", { name: "证据溯源" });
    expect(trigger).toHaveAttribute("aria-expanded", "true");

    await user.click(within(dialog).getByRole("button", { name: "关闭证据抽屉" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(document.activeElement).toBe(trigger);
    });
  });
});

// --- P1: evidence-stance + low-trust warnings + lens support chain --------------

describe("P1: evidence discipline visibility (grey-goo TDD direction)", () => {
  test("opposing and supporting stances are derived and labeled, never guessed", async () => {
    renderDrawer();

    const opposing = await screen.findByText("反对");
    const supporting = screen.getByText("支持");
    expect(opposing).toHaveAttribute("data-evidence-stance", "opposing");
    expect(supporting).toHaveAttribute("data-evidence-stance", "supporting");
  });

  test("zero opposing evidence raises the single-narrative warning; none when both sides exist", async () => {
    // itemOne supports, itemTwo contradicts → balanced set, no warning.
    renderDrawer();
    await screen.findByRole("button", { name: /行业访谈纪要：远程侦察需求/ });
    expect(screen.queryByText(/没有任何反对方向证据/)).not.toBeInTheDocument();

    cleanup();
    // All-supporting set → the pseudo-convergence warning appears.
    const oneSided = makeRouteFetch({
      ...happyRoutes,
      "/api/workspaces/ws_1/analyses/run_1/evidence": () =>
        jsonResponse(200, {
          ok: true,
          data: {
            analysisRunId: "run_1",
            items: [itemOne]
          }
        })
    });
    render(
      <EvidenceDrawer
        open
        onClose={vi.fn()}
        anchors={anchors}
        fetchImpl={oneSided as unknown as typeof fetch}
        eventSourceFactory={null}
      />
    );
    expect(await screen.findByText(/没有任何反对方向证据——若结论看起来一致/)).toBeInTheDocument();
  });

  test("L5/L6-heavy ledger raises the low-trust category warning without percentages", async () => {
    const lowTrustItems = [
      makeItem({ id: "ev_l5", sourceGrade: "L5_opinion" }),
      makeItem({ id: "ev_l6", sourceGrade: "L6_unverified" })
    ];
    const fetchImpl = makeRouteFetch({
      ...happyRoutes,
      "/api/workspaces/ws_1/analyses/run_1/evidence": () =>
        jsonResponse(200, { ok: true, data: { analysisRunId: "run_1", items: lowTrustItems } })
    });
    render(
      <EvidenceDrawer
        open
        onClose={vi.fn()}
        anchors={anchors}
        fetchImpl={fetchImpl as unknown as typeof fetch}
        eventSourceFactory={null}
      />
    );
    expect(await screen.findByText(/多数证据来自低可信类别（L5\/L6）/)).toBeInTheDocument();
    // QA P5 aggregate-credibility discipline: no "%" anywhere in the drawer.
    expect(document.body.textContent).not.toContain("%");
  });

  test("lens consumers are listed on the item and inside the detail (support chain)", async () => {
    const user = userEvent.setup();
    renderDrawer();

    // Ledger row: ev_1 is cited by porter_five_forces (from evidenceRefs).
    await waitFor(() => {
      expect(screen.getByText("被 1 个透镜引用")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /行业访谈纪要：远程侦察需求/ }));
    // Detail shows ONLY the lenses that actually cite this item (ev_1 is
    // referenced by porter, never by scenario_planning).
    expect(await screen.findByText("porter_five_forces")).toBeInTheDocument();
    expect(screen.queryByText("scenario_planning")).not.toBeInTheDocument();
  });

  test("lens reads failing degrade to unavailable — no fabricated references", async () => {
    const user = userEvent.setup();
    // Detail reads succeed (from happyRoutes); ONLY the lens surface fails.
    const fetchImpl = makeRouteFetch({
      ...happyRoutes,
      "/api/workspaces/ws_1/analyses/run_1/strategic-lenses": () =>
        jsonResponse(500, { ok: false, error: { code: "INTERNAL", message: "boom" } })
    });
    render(
      <EvidenceDrawer
        open
        onClose={vi.fn()}
        anchors={anchors}
        fetchImpl={fetchImpl as unknown as typeof fetch}
        eventSourceFactory={null}
      />
    );
    const row = await screen.findByRole("button", { name: /行业访谈纪要：远程侦察需求/ });
    // The ledger row itself carries NO fabricated lens-count badge.
    expect(screen.queryByText(/被 \d+ 个透镜引用/)).not.toBeInTheDocument();

    // Open the detail: the lens-consumer section honestly reports unavailability.
    await user.click(row);
    expect(await screen.findByText(/透镜引用关系暂不可用/)).toBeInTheDocument();
  });
});

// --- P2 wave 2: persisted TDD funnel audit (原则⑩ / CCR-20260802-P2W2) --------

describe("P2: funnel discard audit (what was filtered out and why)", () => {
  test("renders one row per discarded fact with its check and reason", async () => {
    const withAudit: RunEvidenceListView = {
      ...runEvidence,
      funnelAudit: {
        stage: "retrieving",
        admitted: 2,
        discarded: [
          { factor: "market size", reason: "conclusion too thin to be a checkable fact", check: "relevance" },
          { factor: "timing", reason: "filler phrase ('more research needed')", check: "relevance" }
        ],
        warnings: ["low-trust sources make up 100% of the evidence set"],
        tierCounts: { L6: 3 },
        opposingCount: 0,
        lowTierShare: 1.0
      }
    };
    const fetchImpl = makeRouteFetch({
      ...happyRoutes,
      "/api/workspaces/ws_1/analyses/run_1/evidence": () =>
        jsonResponse(200, { ok: true, data: withAudit })
    });
    render(
      <EvidenceDrawer
        open
        onClose={vi.fn()}
        anchors={anchors}
        fetchImpl={fetchImpl as unknown as typeof fetch}
        eventSourceFactory={null}
      />
    );

    expect(await screen.findByText("被过滤的事实（2 条）")).toBeInTheDocument();
    expect(screen.getByText("market size")).toBeInTheDocument();
    expect(screen.getByText(/relevance：conclusion too thin/)).toBeInTheDocument();
  });

  test("zero discards renders the honest empty state", async () => {
    const withEmptyAudit: RunEvidenceListView = {
      ...runEvidence,
      funnelAudit: {
        stage: "retrieving",
        admitted: 2,
        discarded: [],
        warnings: [],
        tierCounts: { L2: 2 },
        opposingCount: 1,
        lowTierShare: 0
      }
    };
    const fetchImpl = makeRouteFetch({
      ...happyRoutes,
      "/api/workspaces/ws_1/analyses/run_1/evidence": () =>
        jsonResponse(200, { ok: true, data: withEmptyAudit })
    });
    render(
      <EvidenceDrawer
        open
        onClose={vi.fn()}
        anchors={anchors}
        fetchImpl={fetchImpl as unknown as typeof fetch}
        eventSourceFactory={null}
      />
    );

    expect(await screen.findByText("本轮检索没有事实被过滤。")).toBeInTheDocument();
  });

  test("absent audit renders nothing (no fabricated filter section)", async () => {
    renderDrawer();
    await screen.findByRole("button", { name: /行业访谈纪要：远程侦察需求/ });
    expect(screen.queryByText(/被过滤的事实/)).not.toBeInTheDocument();
  });
});
