"use client";

// EvidenceDrawer (Task 11 B2, evidence provenance line). Read-only drawer
// over the 7 mounted evidence GET routes: run ledger (items + conflicts) on
// the left, per-item chain of custody (detail / quality / provenance /
// direction / same-source group) on demand. Focus trap, Escape handling and
// initial focus follow the ProjectDrawer precedent verbatim.
//
// Honest states, in contract order:
//   - anchors gap (no case→run resolution route yet; single switch in
//     lib/api/evidence.ts) → gap note, zero fetches, zero fabricated runs;
//   - loading / slow network (threshold, still loading, layout unchanged);
//   - 401 → session copy; uniform 404 → ONE anti-enumeration message that
//     never distinguishes "missing" from "not yours" (CASE_NOT_FOUND is
//     byte-identical on the wire and stays collapsed here);
//   - empty ledger → honest empty state; ready → real data only.
//
// SSE: subscribes ONLY to `citation.added` as a passive ledger refresh
// (reserved hook); progress rendering belongs to the B1 AnalysisProgress lane.

import { useCallback, useEffect, useRef, useState } from "react";

import type {
  ConflictRelationView,
  EvidenceDirectionView,
  EvidenceItemView,
  EvidenceProvenanceView,
  EvidenceRunAnchors,
  EvidenceEventSourceFactory,
  LensArtifactSummaryView,
  QualityDimensionsView,
  SameSourceGroupView
} from "@/lib/api/evidence";
import {
  defaultEvidenceEventSourceFactory,
  fetchEvidenceDirection,
  fetchEvidenceItem,
  fetchEvidenceProvenance,
  fetchEvidenceQuality,
  fetchLensArtifact,
  fetchRunConflicts,
  fetchRunEvidence,
  fetchRunLensArtifacts,
  fetchSameSourceGroup,
  isUnauthenticated,
  isUniformNotFound,
  subscribeCitationAdded
} from "@/lib/api/evidence";

import { ConflictList } from "./ConflictList";
import { DirectionPanel, ProvenanceChain, SameSourceGroupNote } from "./ProvenanceChain";
import { QualityDimensionsPanel } from "./QualityDimensionsPanel";
import { SourceGradeBadge } from "./SourceGradeBadge";
import { VerdictBlock } from "./VerdictBlock";

// One anti-enumeration message for every failed lookup class: the server
// answers missing, foreign and cross-tenant ids byte-identically, and this
// copy must not re-introduce an existence signal.
export const UNIFORM_NOT_FOUND_COPY = "证据材料不可访问。系统不区分“不存在”与“无权访问”，请检查当前工作区与链接。";

const drawerFocusableSelector = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])"
].join(",");

function getDrawerFocusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(drawerFocusableSelector)).filter(
    (element) => element.getAttribute("aria-hidden") !== "true"
  );
}

// --- P1: deterministic evidence-stance derivation (grey-goo TDD direction) --
// Pure derivation over ALREADY-PERSISTED wire fields (supports/contradicts
// claim ids, source grade). No new contract: the drawer only makes visible
// what the evidence ledger already stores — opposing evidence is never
// buried (v6-analysis-agent §1 Check 2 "Opposing MUST be included").

type EvidenceStance = "supporting" | "opposing" | "unlabeled";

function evidenceStance(item: EvidenceItemView): EvidenceStance {
  const supports = (item.supportsClaimIds ?? []).length > 0;
  const contradicts = (item.contradictsClaimIds ?? []).length > 0;
  if (contradicts && !supports) return "opposing";
  if (supports && !contradicts) return "supporting";
  return "unlabeled";
}

const STANCE_LABELS: Record<EvidenceStance, string> = {
  supporting: "支持",
  opposing: "反对",
  unlabeled: "未标注"
};

/** L5/L6 share across the ledger (discipline cap 30%, mirrors the funnel). */
function lowTrustShare(items: EvidenceItemView[]): number | null {
  const total = items.length;
  if (total === 0) return null;
  const low = items.filter(
    (item) => item.sourceGrade === "L5_opinion" || item.sourceGrade === "L6_unverified"
  ).length;
  return low / total;
}

type LedgerState =
  | { phase: "gap" }
  | { phase: "loading" }
  | { phase: "unauthenticated" }
  | { phase: "not-found" }
  | { phase: "error" }
  | { phase: "ready"; items: EvidenceItemView[]; conflicts: ConflictRelationView[] };

type DetailData = {
  item: EvidenceItemView;
  quality: QualityDimensionsView;
  provenance: EvidenceProvenanceView;
  direction: EvidenceDirectionView;
  group: SameSourceGroupView;
};

type DetailState =
  | { phase: "loading"; evidenceItemId: string }
  | { phase: "unauthenticated"; evidenceItemId: string }
  | { phase: "not-found"; evidenceItemId: string }
  | { phase: "error"; evidenceItemId: string }
  | { phase: "ready"; evidenceItemId: string; data: DetailData };

/**
 * Evidence -> lens support chain (P1). Built once per drawer open from the
 * ALREADY-MOUNTED strategic-lens read surface: summary list + per-artifact
 * detail (evidenceRefs). Failed reads degrade to `unavailable`, never to
 * fabricated references.
 */
type LensRefsState =
  | { phase: "loading" }
  | { phase: "unavailable" }
  | { phase: "ready"; byEvidenceId: Map<string, string[]>; lensSummaries: LensArtifactSummaryView[] };

export type EvidenceDrawerProps = {
  open: boolean;
  onClose: () => void;
  /** null = the case→run resolution surface has not shipped (honest gap). */
  anchors: EvidenceRunAnchors | null;
  fetchImpl?: typeof fetch;
  /** null disables the SSE hook (e.g. runtimes without EventSource). */
  eventSourceFactory?: EvidenceEventSourceFactory | null;
  /** After this many ms of pending load the drawer admits the network is slow. */
  slowThresholdMs?: number;
};

/**
 * P1: ledger-level evidence discipline warnings (grey-goo TDD + funnel
 * warnings made visible). Deterministic derivations only: opposing-evidence
 * presence, L5/L6 trust share, rejected verdicts. Rendering a warning NEVER
 * fabricates data — it surfaces what the ledger already stores.
 */
function EvidenceSetWarnings({ items }: { items: EvidenceItemView[] }) {
  const opposingCount = items.filter((item) => evidenceStance(item) === "opposing").length;
  const lowShare = lowTrustShare(items);
  const rejectedCount = items.filter((item) => item.verdict === "rejected").length;

  const warnings: string[] = [];
  if (opposingCount === 0) {
    warnings.push(
      "账本中没有任何反对方向证据——若结论看起来一致，需警惕单一叙事（伪收敛）。"
    );
  }
  if (lowShare !== null && lowShare > 0.3) {
    // Deliberately NOT a percentage: QA P5 forbids "%" anywhere in the drawer
    // (aggregate-credibility discipline). The share is a category warning.
    warnings.push(
      "账本中多数证据来自低可信类别（L5/L6）——结论可能建立在薄弱证据上。"
    );
  }
  if (rejectedCount > 0) {
    warnings.push(`${rejectedCount} 条证据被质量门否决（rejected），引用它们会阻断正式发布。`);
  }
  if (warnings.length === 0) return null;
  return (
    <div className="evidence-set-warnings" data-evidence-set-warnings>
      {warnings.map((warning) => (
        <p key={warning} role="status">
          {warning}
        </p>
      ))}
    </div>
  );
}

/**
 * P1: evidence -> lens support chain ("which lens artifacts cite this item").
 * Honest phases mirror the ledger discipline: loading, unavailable (lens read
 * failed — never fabricated), none (ready but nothing cites this item), and
 * the consumer list.
 */
function EvidenceLensConsumers({
  evidenceItemId,
  lensRefs
}: {
  evidenceItemId: string;
  lensRefs: LensRefsState;
}) {
  if (lensRefs.phase === "loading") {
    return (
      <section className="evidence-lens-consumers" aria-label="透镜引用">
        <span>透镜引用</span>
        <p className="draft-notice" role="status">正在读取该证据被哪些透镜引用…</p>
      </section>
    );
  }
  if (lensRefs.phase === "unavailable") {
    return (
      <section className="evidence-lens-consumers" aria-label="透镜引用">
        <span>透镜引用</span>
        <p className="draft-notice" role="status">透镜引用关系暂不可用（读取失败，不提供猜测）。</p>
      </section>
    );
  }
  const consumers = lensRefs.byEvidenceId.get(evidenceItemId) ?? [];
  if (consumers.length === 0) {
    return (
      <section className="evidence-lens-consumers" aria-label="透镜引用">
        <span>透镜引用</span>
        <p className="draft-notice" role="status">尚无透镜引用该证据。</p>
      </section>
    );
  }
  return (
    <section className="evidence-lens-consumers" aria-label="透镜引用">
      <span>透镜引用</span>
      <ul>
        {consumers.map((lensType) => (
          <li key={lensType} data-lens-consumer={lensType}>
            {lensType}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function EvidenceDrawer({
  open,
  onClose,
  anchors,
  fetchImpl = fetch,
  eventSourceFactory = defaultEvidenceEventSourceFactory(),
  slowThresholdMs = 8000
}: EvidenceDrawerProps) {
  const [ledger, setLedger] = useState<LedgerState>(anchors ? { phase: "loading" } : { phase: "gap" });
  const [slowNetwork, setSlowNetwork] = useState(false);
  const [detail, setDetail] = useState<DetailState | null>(null);
  const [lensRefs, setLensRefs] = useState<LensRefsState>({ phase: "loading" });
  const drawerDialog = useRef<HTMLElement>(null);
  const ledgerRequestSeq = useRef(0);
  const detailRequestSeq = useRef(0);
  const lensRefsRequestSeq = useRef(0);

  const classifyFailure = (error: unknown): "unauthenticated" | "not-found" | "error" => {
    if (isUnauthenticated(error)) return "unauthenticated";
    if (isUniformNotFound(error)) return "not-found";
    return "error";
  };

  const loadLedger = useCallback(
    async (quiet: boolean) => {
      if (!anchors) {
        setLedger({ phase: "gap" });
        return;
      }
      const requestId = ++ledgerRequestSeq.current;
      if (!quiet) {
        setLedger({ phase: "loading" });
        setSlowNetwork(false);
      }
      const slowTimer = quiet
        ? null
        : window.setTimeout(() => {
            if (ledgerRequestSeq.current === requestId) setSlowNetwork(true);
          }, slowThresholdMs);
      try {
        const [runEvidence, runConflicts] = await Promise.all([
          fetchRunEvidence(anchors, fetchImpl),
          fetchRunConflicts(anchors, fetchImpl)
        ]);
        if (ledgerRequestSeq.current !== requestId) return;
        setLedger({
          phase: "ready",
          items: Array.isArray(runEvidence.items) ? runEvidence.items : [],
          conflicts: Array.isArray(runConflicts.conflicts) ? runConflicts.conflicts : []
        });
      } catch (error) {
        if (ledgerRequestSeq.current !== requestId) return;
        // A quiet (SSE-triggered) refresh never downgrades displayed data.
        if (!quiet) setLedger({ phase: classifyFailure(error) });
      } finally {
        if (slowTimer !== null) window.clearTimeout(slowTimer);
        if (ledgerRequestSeq.current === requestId) setSlowNetwork(false);
      }
    },
    [anchors, fetchImpl, slowThresholdMs]
  );

  const loadDetail = useCallback(
    async (evidenceItemId: string) => {
      if (!anchors) return;
      const requestId = ++detailRequestSeq.current;
      setDetail({ phase: "loading", evidenceItemId });
      const itemAnchors = { workspaceId: anchors.workspaceId, evidenceItemId };
      try {
        const [item, quality, provenance, direction, group] = await Promise.all([
          fetchEvidenceItem(itemAnchors, fetchImpl),
          fetchEvidenceQuality(itemAnchors, fetchImpl),
          fetchEvidenceProvenance(itemAnchors, fetchImpl),
          fetchEvidenceDirection(itemAnchors, fetchImpl),
          fetchSameSourceGroup(itemAnchors, fetchImpl)
        ]);
        if (detailRequestSeq.current !== requestId) return;
        setDetail({ phase: "ready", evidenceItemId, data: { item, quality, provenance, direction, group } });
      } catch (error) {
        if (detailRequestSeq.current !== requestId) return;
        setDetail({ phase: classifyFailure(error), evidenceItemId });
      }
    },
    [anchors, fetchImpl]
  );

  const loadLensRefs = useCallback(async () => {
    if (!anchors) {
      setLensRefs({ phase: "unavailable" });
      return;
    }
    const requestId = ++lensRefsRequestSeq.current;
    try {
      // Summary list first: an empty list is a valid honest state (no ready
      // lens artifacts yet) and stops before any per-artifact fetch.
      const summaries = await fetchRunLensArtifacts(anchors, fetchImpl);
      if (lensRefsRequestSeq.current !== requestId) return;
      if (summaries.length === 0) {
        setLensRefs({ phase: "ready", byEvidenceId: new Map(), lensSummaries: [] });
        return;
      }
      // Per-artifact details carry evidenceRefs: one fetch per artifact,
      // each failing on its own without poisoning the rest (the map only
      // gains what actually resolved).
      const details = await Promise.allSettled(
        summaries.map((summary) => fetchLensArtifact(anchors, summary.id, fetchImpl))
      );
      if (lensRefsRequestSeq.current !== requestId) return;
      const byEvidenceId = new Map<string, string[]>();
      let resolvedCount = 0;
      details.forEach((result, index) => {
        if (result.status !== "fulfilled") return;
        const detail = result.value;
        resolvedCount += 1;
        for (const evidenceId of detail.evidenceRefs ?? []) {
          const lenses = byEvidenceId.get(evidenceId) ?? [];
          lenses.push(detail.lensType);
          byEvidenceId.set(evidenceId, lenses);
        }
      });
      if (resolvedCount === 0) {
        setLensRefs({ phase: "unavailable" });
        return;
      }
      setLensRefs({ phase: "ready", byEvidenceId, lensSummaries: summaries });
    } catch {
      if (lensRefsRequestSeq.current !== requestId) return;
      setLensRefs({ phase: "unavailable" });
    }
  }, [anchors, fetchImpl]);

  // Initial + reopened load.
  useEffect(() => {
    if (!open) return;
    setDetail(null);
    void loadLedger(false);
    void loadLensRefs();
  }, [open, loadLedger, loadLensRefs]);

  // Reserved SSE hook: citation.added → passive, quiet ledger refresh.
  useEffect(() => {
    if (!open || !anchors || !eventSourceFactory) return;
    const unsubscribe = subscribeCitationAdded(anchors, () => void loadLedger(true), eventSourceFactory);
    return unsubscribe;
  }, [open, anchors, eventSourceFactory, loadLedger]);

  // Focus trap / Escape / initial focus — ProjectDrawer precedent.
  useEffect(() => {
    if (!open) return;
    const dialog = drawerDialog.current;
    if (!dialog) return;

    const focusTimer = window.setTimeout(() => {
      const [firstFocusable] = getDrawerFocusableElements(dialog);
      (firstFocusable ?? dialog).focus();
    }, 0);

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;

      const focusable = getDrawerFocusableElements(dialog);
      if (focusable.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      const focusIsOutside = active === null || !dialog.contains(active);

      if (event.shiftKey && (active === first || focusIsOutside)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || focusIsOutside)) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onClose]);

  if (!open) return null;

  const itemsById =
    ledger.phase === "ready"
      ? new Map(ledger.items.map((item) => [item.id, item]))
      : new Map<string, EvidenceItemView>();

  return (
    <aside className="drawer evidence-drawer is-open">
      <button className="drawer-scrim" type="button" aria-label="关闭证据抽屉" onClick={onClose} />
      <section
        ref={drawerDialog}
        id="evidence-drawer-dialog"
        className="drawer-sheet evidence-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="evidence-drawer-title"
        tabIndex={-1}
      >
        <header>
          <div>
            <span>CHAIN OF CUSTODY</span>
            <h2 id="evidence-drawer-title">证据溯源</h2>
            <p>来源类别（L1-L6）与质量维度相互独立；系统不给出总可信度数值。</p>
          </div>
          <button className="drawer-close" type="button" onClick={onClose} aria-label="关闭证据抽屉">{"\u00d7"}</button>
        </header>

        <div className="evidence-ledger" aria-label="证据账本">
          {ledger.phase === "gap" && (
            <section className="evidence-gap-note">
              <span>证据溯源</span>
              <p role="status">
                完成一次深度分析后，证据保管链会出现在这里；当前没有可展示的证据记录。
              </p>
            </section>
          )}

          {ledger.phase === "loading" && (
            <p className="draft-notice" role="status">
              {slowNetwork ? "网络较慢，仍在读取证据账本…" : "正在读取证据账本…"}
            </p>
          )}

          {ledger.phase === "unauthenticated" && (
            <p className="draft-notice" role="status">尚未登录：登录后这里会展示该 Run 的真实证据账本。</p>
          )}

          {ledger.phase === "not-found" && (
            <p className="draft-notice" role="alert">{UNIFORM_NOT_FOUND_COPY}</p>
          )}

          {ledger.phase === "error" && (
            <>
              <p className="draft-notice" role="alert">证据账本读取失败。</p>
              <button className="secondary-action" type="button" onClick={() => void loadLedger(false)}>重试</button>
            </>
          )}

          {ledger.phase === "ready" && ledger.items.length === 0 && (
            <p className="draft-notice" role="status">该 Run 尚无证据条目；系统不填充示例证据。</p>
          )}

          {ledger.phase === "ready" && ledger.items.length > 0 && (
            <>
              <EvidenceSetWarnings items={ledger.items} />
              <ul className="evidence-item-list">
                {ledger.items.map((item) => {
                  const stance = evidenceStance(item);
                  const lensTypes =
                    lensRefs.phase === "ready" ? (lensRefs.byEvidenceId.get(item.id) ?? []) : [];
                  return (
                    <li key={item.id} data-evidence-item={item.id}>
                      <button
                        type="button"
                        className="evidence-item-row"
                        onClick={() => void loadDetail(item.id)}
                        aria-expanded={detail !== null && detail.evidenceItemId === item.id}
                      >
                        <SourceGradeBadge grade={item.sourceGrade} />
                        <b>{item.title}</b>
                        <small>
                          {`${item.freshnessStatus} · ${item.originMode}`}
                          {stance !== "unlabeled" && (
                            <span
                              className={`evidence-stance evidence-stance--${stance}`}
                              data-evidence-stance={stance}
                            >
                              {STANCE_LABELS[stance]}
                            </span>
                          )}
                          {lensTypes.length > 0 && (
                            <span className="evidence-lens-refs" data-evidence-lens-refs={item.id}>
                              {`被 ${lensTypes.length} 个透镜引用`}
                            </span>
                          )}
                        </small>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </>
          )}

          {ledger.phase === "ready" && <ConflictList conflicts={ledger.conflicts} itemsById={itemsById} />}
        </div>

        {detail && (
          <div className="evidence-detail" aria-label="证据详情">
            {detail.phase === "loading" && (
              <p className="draft-notice" role="status">正在读取该证据的溯源链…</p>
            )}
            {detail.phase === "unauthenticated" && (
              <p className="draft-notice" role="status">尚未登录：登录后可读取该证据的溯源链。</p>
            )}
            {detail.phase === "not-found" && (
              <p className="draft-notice" role="alert">{UNIFORM_NOT_FOUND_COPY}</p>
            )}
            {detail.phase === "error" && (
              <>
                <p className="draft-notice" role="alert">证据详情读取失败。</p>
                <button
                  className="secondary-action"
                  type="button"
                  onClick={() => void loadDetail(detail.evidenceItemId)}
                >
                  重试
                </button>
              </>
            )}
            {detail.phase === "ready" && (
              <article className="evidence-detail-body">
                <header className="evidence-detail-head">
                  <SourceGradeBadge grade={detail.data.item.sourceGrade} />
                  <h3>{detail.data.item.title}</h3>
                  {detail.data.item.sourceDomain && <small>{detail.data.item.sourceDomain}</small>}
                  <blockquote>{detail.data.item.snippet}</blockquote>
                  {detail.data.item.bias && <p className="evidence-bias">{`偏见方向：${detail.data.item.bias}`}</p>}
                </header>
                <VerdictBlock
                  verdict={detail.data.item.verdict}
                  reasonCodes={detail.data.item.verdictReasonCodes}
                  applicabilityLimits={detail.data.item.applicabilityLimits}
                />
                <QualityDimensionsPanel quality={detail.data.quality} />
                <ProvenanceChain provenance={detail.data.provenance} />
                <SameSourceGroupNote group={detail.data.group} />
                <DirectionPanel direction={detail.data.direction} />
                <EvidenceLensConsumers
                  evidenceItemId={detail.data.item.id}
                  lensRefs={lensRefs}
                />
              </article>
            )}
          </div>
        )}

        <footer>
          <button className="secondary-action" type="button" onClick={onClose}>返回工作台</button>
        </footer>
      </section>
    </aside>
  );
}
