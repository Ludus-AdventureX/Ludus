"use client";

import { useCallback, useEffect, useState } from "react";

import {
  ProvenanceError,
  loadDecisionProvenance,
  type DecisionProvenance,
} from "@/lib/shell/provenance";

// "How was this decision reached?" - visualizes the tamper-evident hash chain
// behind a signed decision (DecisionRecord <- report <- run <- charter). Every
// value shown is a hash the backend already minted; nothing is fabricated, and
// a case with no signed decision renders nothing (the panel self-hides).

export type ProvenancePanelProps = {
  workspaceId?: string | null;
  decisionCaseId?: string;
  /** Bumped by the parent after a successful signoff to trigger a reload. */
  refreshKey?: number;
};

export function ProvenancePanel({ workspaceId = null, decisionCaseId, refreshKey = 0 }: ProvenancePanelProps) {
  const [chain, setChain] = useState<DecisionProvenance | null>(null);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    if (!workspaceId || !decisionCaseId) return;
    try {
      const result = await loadDecisionProvenance(workspaceId, decisionCaseId);
      setChain(result);
      setError("");
    } catch (err) {
      setError(err instanceof ProvenanceError ? err.message : "溯源读取失败。");
    } finally {
      setLoaded(true);
    }
  }, [decisionCaseId, workspaceId]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  // Self-hiding: no anchor, still loading, or no signed decision -> render
  // nothing (the provenance chain only exists after a decision is frozen).
  if (!workspaceId || !decisionCaseId) return null;
  if (!loaded && !chain) return null;
  if (loaded && !chain && !error) return null;

  return (
    <section className="provenance-panel" data-provenance-panel aria-label="决策溯源链">
      <header>
        <span className="eyebrow">决策溯源 · 可验证 · 可复现</span>
        <h3>这个决定是如何得来的</h3>
        <p className="provenance-note">
          每一环都是后端冻结的内容哈希，构成防篡改的证据链——从签署一路回溯到原始问题快照。
        </p>
      </header>
      {error && <p role="alert">{error}</p>}
      {chain && (
        <ol className="provenance-chain">
          {chain.links.map((link, index) => (
            <li
              key={`${link.kind}-${link.id}`}
              data-provenance-link={link.kind}
              data-available={link.available}
            >
              <div className="provenance-link-head">
                <b>{link.title}</b>
                <code>{link.id.length > 16 ? `${link.id.slice(0, 8)}…` : link.id}</code>
              </div>
              <dl>
                {link.rows.map(([label, value]) => (
                  <div key={label}>
                    <dt>{label}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
              </dl>
              {index < chain.links.length - 1 && <span className="provenance-arrow" aria-hidden>↓ 派生自</span>}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
