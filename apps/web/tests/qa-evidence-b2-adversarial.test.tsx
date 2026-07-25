/** @vitest-environment jsdom */

// QA adversarial supplement — Task 11 B2 evidence provenance line (r1).
// Independent probes beyond the owner's evidence-drawer.test.tsx:
//   P1 hostile envelope: data:null on the ledger reads → honest error state;
//   P2 hostile data shape: wrong-typed / extra-field ledger payload → honest
//      empty state, zero fabricated rows;
//   P3 hostile envelope on the five detail reads ({ok:true}, no data) →
//      detail-level error + retry, ledger untouched;
//   P4 uniform 404 at the DETAIL level: missing id vs foreign-workspace id vs
//      bodyless 404 → ONE byte-identical anti-enumeration copy (same constant
//      the ledger uses), no id echo;
//   P5 aggregate-credibility / percentage scan across ALL drawer states
//      (gap, loading, 401, 404, error, empty, ready + detail);
//   P6 L1 badge must NOT read as an acceptance verdict on its own: an
//      L1_primary item with verdict=rejected keeps the category label and the
//      four-tier verdict stays the only acceptance signal;
//   P7 citation.added storm (30 rapid events) + out-of-order quiet responses →
//      no crash, no downgrade, ledger converges to the latest request.

import "@testing-library/jest-dom/vitest";

import { Component, type ReactNode } from "react";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { EvidenceDrawer, UNIFORM_NOT_FOUND_COPY } from "../components/quality/EvidenceDrawer";
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
  biasFlags: [],
  completenessWarnings: [],
  conflictGroupIds: [],
  verdict: "rejected",
  reasonCodes: ["contradicted_by_primary"],
  assessedAt: "2026-07-25T10:00:00+08:00"
};

const l1RejectedItem: EvidenceItemView = {
  id: "ev_l1r",
  workspaceId: "ws_1",
  decisionCaseId: "case_1",
  analysisRunId: "run_1",
  title: "一手来源但被否决的材料",
  url: null,
  filePath: null,
  sourceDomain: null,
  sourceGrade: "L1_primary",
  snippet: "一手来源不等于自动可信。",
  sourceRecordId: "sr_l1r",
  sourceSpanIds: [],
  supportsClaimIds: [],
  contradictsClaimIds: ["claim_z"],
  publishedAt: null,
  retrievedAt: "2026-07-25T09:00:00+08:00",
  freshnessStatus: "fresh",
  relevance: 0.4,
  bias: null,
  conflictGroupId: null,
  independentSourceGroupId: null,
  verdict: "rejected",
  verdictReasonCodes: ["contradicted_by_primary"],
  applicabilityLimits: [],
  originMode: "live",
  rawArtifactId: "raw_l1r",
  qualityAssessmentId: "qa_l1r"
};

const runEvidence: RunEvidenceListView = { analysisRunId: "run_1", items: [l1RejectedItem] };
const conflicts: ConflictListView = { analysisRunId: "run_1", conflicts: [] };

const provenance: EvidenceProvenanceView = {
  evidenceItemId: "ev_l1r",
  rawArtifact: {
    id: "raw_l1r",
    kind: "web_page",
    mediaType: "text/html",
    byteSize: 1024,
    sha256: "a".repeat(64),
    sourceUrl: null,
    originMode: "live",
    createdAt: "2026-07-25T09:00:00+08:00"
  },
  sourceRecord: {
    id: "sr_l1r",
    kind: "web_page",
    sourceScope: "run_frozen",
    canonicalUri: "https://example.org/rejected",
    title: "一手来源材料",
    contentHash: "hash_sr",
    sourceVersion: "v1",
    originMode: "live",
    rawArtifactId: "raw_l1r",
    spans: []
  },
  quality
};

const direction: EvidenceDirectionView = {
  evidenceItemId: "ev_l1r",
  supportsClaimIds: [],
  contradictsClaimIds: ["claim_z"],
  verdict: "rejected"
};

const sameSourceGroup: SameSourceGroupView = {
  independentSourceGroupId: null,
  memberEvidenceItemIds: ["ev_l1r"],
  independentSourceCountContribution: 1
};

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body
  } as unknown as Response;
}

const notFoundEnvelope = { ok: false, error: { code: "CASE_NOT_FOUND", message: "Case material not found." } };

const happyRoutes: Record<string, () => Response> = {
  "/api/workspaces/ws_1/analyses/run_1/evidence": () => jsonResponse(200, { ok: true, data: runEvidence }),
  "/api/workspaces/ws_1/analyses/run_1/evidence-conflicts": () => jsonResponse(200, { ok: true, data: conflicts }),
  "/api/workspaces/ws_1/evidence/ev_l1r": () => jsonResponse(200, { ok: true, data: l1RejectedItem }),
  "/api/workspaces/ws_1/evidence/ev_l1r/quality": () => jsonResponse(200, { ok: true, data: quality }),
  "/api/workspaces/ws_1/evidence/ev_l1r/provenance": () => jsonResponse(200, { ok: true, data: provenance }),
  "/api/workspaces/ws_1/evidence/ev_l1r/direction": () => jsonResponse(200, { ok: true, data: direction }),
  "/api/workspaces/ws_1/evidence/ev_l1r/same-source-group": () =>
    jsonResponse(200, { ok: true, data: sameSourceGroup })
};

function makeRouteFetch(routes: Record<string, () => Response>): ReturnType<typeof vi.fn> {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const handler = routes[url];
    if (!handler) return jsonResponse(404, notFoundEnvelope);
    return handler();
  });
}

class ProbeBoundary extends Component<{ children: ReactNode }, { crashed: boolean }> {
  state = { crashed: false };
  static getDerivedStateFromError() {
    return { crashed: true };
  }
  render() {
    return this.state.crashed ? <p data-testid="qa-crash-detected">render crashed</p> : this.props.children;
  }
}

function renderDrawer(overrides: Partial<Parameters<typeof EvidenceDrawer>[0]> = {}) {
  const onClose = vi.fn();
  const view = render(
    <ProbeBoundary>
      <EvidenceDrawer
        open
        onClose={onClose}
        anchors={anchors}
        fetchImpl={makeRouteFetch(happyRoutes) as unknown as typeof fetch}
        eventSourceFactory={null}
        {...overrides}
      />
    </ProbeBoundary>
  );
  return { onClose, ...view };
}

// --- P1 / P2 / P3: hostile envelope & data shapes -----------------------------

describe("QA P1-P3: hostile envelopes and data shapes degrade honestly", () => {
  test("P1: data:null on the ledger reads degrades to the error state, no crash, no fabricated rows", async () => {
    renderDrawer({
      fetchImpl: makeRouteFetch({
        "/api/workspaces/ws_1/analyses/run_1/evidence": () => jsonResponse(200, { ok: true, data: null }),
        "/api/workspaces/ws_1/analyses/run_1/evidence-conflicts": () =>
          jsonResponse(200, { ok: true, data: null })
      }) as unknown as typeof fetch
    });

    expect(await screen.findByText("证据账本读取失败。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
    expect(screen.queryByTestId("qa-crash-detected")).not.toBeInTheDocument();
    expect(document.querySelectorAll("[data-evidence-item]")).toHaveLength(0);
  });

  test("P2: wrong-typed items + extra unknown fields render the honest empty state, nothing invented", async () => {
    renderDrawer({
      fetchImpl: makeRouteFetch({
        "/api/workspaces/ws_1/analyses/run_1/evidence": () =>
          jsonResponse(200, {
            ok: true,
            data: {
              analysisRunId: "run_1",
              items: "not-an-array",
              totalCredibility: 0.97,
              extraneous: { nested: true }
            }
          }),
        "/api/workspaces/ws_1/analyses/run_1/evidence-conflicts": () =>
          jsonResponse(200, { ok: true, data: { analysisRunId: "run_1", conflicts: 42 } })
      }) as unknown as typeof fetch
    });

    expect(await screen.findByText("该 Run 尚无证据条目；系统不填充示例证据。")).toBeInTheDocument();
    expect(screen.getByText("该 Run 没有已记录的证据冲突。")).toBeInTheDocument();
    expect(screen.queryByTestId("qa-crash-detected")).not.toBeInTheDocument();
    // The smuggled aggregate never leaks into the UI.
    expect(document.body.textContent).not.toContain("0.97");
    expect(document.body.textContent).not.toContain("%");
  });

  test("P3: envelope without `data` on the five detail reads → detail error + retry; ledger stays intact", async () => {
    const user = userEvent.setup();
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/evidence/ev_l1r")) return jsonResponse(200, { ok: true });
      const handler = happyRoutes[url];
      return handler ? handler() : jsonResponse(404, notFoundEnvelope);
    });
    renderDrawer({ fetchImpl: fetchImpl as unknown as typeof fetch });

    await user.click(await screen.findByRole("button", { name: /一手来源但被否决的材料/ }));
    expect(await screen.findByText("证据详情读取失败。")).toBeInTheDocument();
    // Ledger row must survive the detail failure.
    expect(screen.getByRole("button", { name: /一手来源但被否决的材料/ })).toBeInTheDocument();
    expect(screen.queryByTestId("qa-crash-detected")).not.toBeInTheDocument();
  });
});

// --- P4: uniform 404 at the detail level ---------------------------------------

describe("QA P4: detail-level 404 stays collapsed (anti-enumeration)", () => {
  async function detailNotFoundCopy(detail404: () => Response): Promise<string> {
    const user = userEvent.setup();
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/evidence/ev_l1r")) return detail404();
      const handler = happyRoutes[url];
      return handler ? handler() : jsonResponse(404, notFoundEnvelope);
    });
    const view = render(
      <EvidenceDrawer
        open
        onClose={vi.fn()}
        anchors={anchors}
        fetchImpl={fetchImpl as unknown as typeof fetch}
        eventSourceFactory={null}
      />
    );
    await user.click(await view.findByRole("button", { name: /一手来源但被否决的材料/ }));
    const copy = (await view.findByRole("alert")).textContent ?? "";
    view.unmount();
    return copy;
  }

  test("missing id, foreign-workspace envelope and bodyless 404 all collapse to the ONE ledger copy", async () => {
    const missing = await detailNotFoundCopy(() => jsonResponse(404, notFoundEnvelope));
    const foreign = await detailNotFoundCopy(() =>
      jsonResponse(404, { ok: false, error: { code: "CASE_NOT_FOUND", message: "Case material not found." } })
    );
    const bodyless = await detailNotFoundCopy(
      () =>
        ({
          ok: false,
          status: 404,
          json: async () => {
            throw new Error("no body");
          }
        }) as unknown as Response
    );

    expect(missing).toBe(UNIFORM_NOT_FOUND_COPY);
    expect(foreign).toBe(missing);
    expect(bodyless).toBe(missing);
    expect(missing).not.toContain("ev_l1r");
    expect(missing).not.toMatch(/不存在，|确实不存在|无权访问：/);
  });
});

// --- P5: aggregate credibility / percentage scan across ALL states -------------

describe("QA P5: no percentage / aggregate credibility figure in ANY drawer state", () => {
  function expectNoAggregate(container: HTMLElement) {
    expect(container.textContent).not.toMatch(/\d+(\.\d+)?\s*%/);
    expect(container.textContent).not.toContain("%");
    expect(container.textContent).not.toMatch(/总可信度[:：]?\s*\d/);
    expect(container.textContent).not.toMatch(/可信度\s*\d/);
  }

  test("gap / loading / 401 / 404 / error / empty / ready+detail are all scanned clean", async () => {
    const user = userEvent.setup();

    // gap
    const gap = renderDrawer({ anchors: null });
    expectNoAggregate(gap.container);
    gap.unmount();

    // loading (never resolves)
    const pending = renderDrawer({
      fetchImpl: vi.fn(() => new Promise<never>(() => {})) as unknown as typeof fetch
    });
    await screen.findByText("正在读取证据账本…");
    expectNoAggregate(pending.container);
    pending.unmount();

    // 401
    const unauth = renderDrawer({
      fetchImpl: makeRouteFetch({
        "/api/workspaces/ws_1/analyses/run_1/evidence": () =>
          jsonResponse(401, { ok: false, error: { code: "AUTH_REQUIRED", message: "Authentication required." } }),
        "/api/workspaces/ws_1/analyses/run_1/evidence-conflicts": () =>
          jsonResponse(401, { ok: false, error: { code: "AUTH_REQUIRED", message: "Authentication required." } })
      }) as unknown as typeof fetch
    });
    await screen.findByText(/尚未登录/);
    expectNoAggregate(unauth.container);
    unauth.unmount();

    // 404
    const notFound = renderDrawer({ fetchImpl: makeRouteFetch({}) as unknown as typeof fetch });
    await screen.findByRole("alert");
    expectNoAggregate(notFound.container);
    notFound.unmount();

    // error
    const error = renderDrawer({
      fetchImpl: makeRouteFetch({
        "/api/workspaces/ws_1/analyses/run_1/evidence": () => jsonResponse(200, { ok: true, data: null }),
        "/api/workspaces/ws_1/analyses/run_1/evidence-conflicts": () => jsonResponse(200, { ok: true, data: null })
      }) as unknown as typeof fetch
    });
    await screen.findByText("证据账本读取失败。");
    expectNoAggregate(error.container);
    error.unmount();

    // empty
    const empty = renderDrawer({
      fetchImpl: makeRouteFetch({
        "/api/workspaces/ws_1/analyses/run_1/evidence": () =>
          jsonResponse(200, { ok: true, data: { analysisRunId: "run_1", items: [] } }),
        "/api/workspaces/ws_1/analyses/run_1/evidence-conflicts": () =>
          jsonResponse(200, { ok: true, data: { analysisRunId: "run_1", conflicts: [] } })
      }) as unknown as typeof fetch
    });
    await screen.findByText(/该 Run 尚无证据条目/);
    expectNoAggregate(empty.container);
    empty.unmount();

    // ready + detail
    const ready = renderDrawer();
    await user.click(await screen.findByRole("button", { name: /一手来源但被否决的材料/ }));
    await screen.findByRole("article");
    expectNoAggregate(ready.container);
    ready.unmount();
  });
});

// --- P6: L1 category never reads as acceptance ---------------------------------

describe("QA P6: L1 badge is a source CATEGORY, never an acceptance verdict", () => {
  test("L1_primary + verdict=rejected: badge keeps the category label; only the four-tier verdict speaks acceptance", async () => {
    const user = userEvent.setup();
    renderDrawer();

    const row = await screen.findByRole("button", { name: /一手来源但被否决的材料/ });
    const rowBadge = row.querySelector(".source-grade-badge");
    expect(rowBadge).not.toBeNull();
    expect(rowBadge?.textContent).toContain("一手来源");
    // The badge itself must not carry acceptance vocabulary.
    expect(rowBadge?.textContent).not.toMatch(/采纳|已接受|接受|可信|通过/);
    // The ledger row shows NO verdict wording at all — category alone is not a verdict.
    expect(row.textContent).not.toMatch(/采纳|已接受|不采纳/);

    await user.click(row);
    const detail = await screen.findByRole("article");
    // Acceptance semantics live exclusively in the four-tier verdict block.
    expect(within(detail).getAllByText("结论 不采纳").length).toBeGreaterThan(0);
    const detailBadge = detail.querySelector(".source-grade-badge");
    expect(detailBadge?.textContent).toContain("一手来源");
    expect(detailBadge?.textContent).not.toMatch(/采纳|已接受|接受|可信|通过/);
    // Verdict attribute reflects rejected while the badge stays L1.
    expect(detail.querySelector('[data-evidence-verdict="rejected"]')).not.toBeNull();
    expect(detail.querySelector('[data-source-grade="L1_primary"]')).not.toBeNull();
  });
});

// --- P7: citation.added storm + out-of-order quiet responses --------------------

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

describe("QA P7: citation.added refresh survives an event storm without downgrade or crash", () => {
  test("30 rapid events + a stale slow response never clobber the latest ledger", async () => {
    const { factory, sources } = makeFakeEventSourceFactory();

    let evidenceCalls = 0;
    const staleGate: { release?: () => void } = {};
    const fetchImpl = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/evidence")) {
        evidenceCalls += 1;
        // The 2nd ledger read (first storm refresh) hangs and resolves LAST
        // with stale content; the seq guard must drop it.
        if (evidenceCalls === 2) {
          await new Promise<void>((resolve) => {
            staleGate.release = resolve;
          });
          return jsonResponse(200, {
            ok: true,
            data: {
              analysisRunId: "run_1",
              items: [{ ...l1RejectedItem, id: "ev_stale", title: "过期的旧账本条目" }]
            }
          });
        }
        return jsonResponse(200, { ok: true, data: runEvidence });
      }
      if (url.endsWith("/evidence-conflicts")) return jsonResponse(200, { ok: true, data: conflicts });
      const handler = happyRoutes[url];
      return handler ? handler() : jsonResponse(404, notFoundEnvelope);
    });

    renderDrawer({ fetchImpl: fetchImpl as unknown as typeof fetch, eventSourceFactory: factory });
    await screen.findByRole("button", { name: /一手来源但被否决的材料/ });
    expect(sources).toHaveLength(1);

    const emit = sources[0].listeners.get("citation.added");
    expect(emit).toBeDefined();
    for (let i = 0; i < 30; i += 1) {
      emit?.(new MessageEvent("citation.added", { data: "{}" }));
    }

    // All storm refreshes fan out; wait for the fresh ones to settle.
    await waitFor(() => {
      expect(evidenceCalls).toBe(31); // 1 initial + 30 quiet refreshes
    });
    await screen.findByRole("button", { name: /一手来源但被否决的材料/ });

    // Now release the stale response — it must be DROPPED, not rendered.
    staleGate.release?.();
    await waitFor(() => {
      expect(screen.queryByText(/过期的旧账本条目/)).not.toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /一手来源但被否决的材料/ })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByTestId("qa-crash-detected")).not.toBeInTheDocument();
  });
});
