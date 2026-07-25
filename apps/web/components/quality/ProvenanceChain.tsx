// Provenance chain (Task 11 B2): the full traceability slice for one
// evidence item — raw artifact (storage pointer metadata only, the API never
// exposes a disk path or body) → frozen source record with its quoted spans
// → orthogonal quality assessment. Also renders the same-source group
// (multiple citations from one origin count as ONE independent source) and
// the support/oppose direction projection.

import type {
  EvidenceDirectionView,
  EvidenceProvenanceView,
  SameSourceGroupView
} from "@/lib/api/evidence";

const originModeLabels: Record<string, string> = {
  live: "实时获取",
  cached: "缓存副本",
  fixture: "夹具数据"
};

function originModeLabel(mode: string): string {
  return originModeLabels[mode] ?? `未识别模式（${mode}）`;
}

export function ProvenanceChain({ provenance }: { provenance: EvidenceProvenanceView }) {
  const { rawArtifact, sourceRecord } = provenance;
  return (
    <section className="provenance-chain" aria-label="溯源链">
      <header>
        <h3>溯源链</h3>
        <p>原始材料 → 冻结来源 → 质量评估；每一环都可审计。</p>
      </header>

      <div className="provenance-step" data-provenance-step="raw-artifact">
        <span>原始材料</span>
        <dl>
          <div>
            <dt>类型</dt>
            <dd>{`${rawArtifact.kind}（${rawArtifact.mediaType}）`}</dd>
          </div>
          <div>
            <dt>字节数</dt>
            <dd>{String(rawArtifact.byteSize)}</dd>
          </div>
          <div>
            <dt>SHA-256</dt>
            <dd>
              <code>{rawArtifact.sha256}</code>
            </dd>
          </div>
          {rawArtifact.sourceUrl && (
            <div>
              <dt>来源 URL</dt>
              <dd>{rawArtifact.sourceUrl}</dd>
            </div>
          )}
          <div>
            <dt>获取方式</dt>
            <dd>{originModeLabel(rawArtifact.originMode)}</dd>
          </div>
          <div>
            <dt>获取时间</dt>
            <dd>{rawArtifact.createdAt}</dd>
          </div>
        </dl>
      </div>

      <div className="provenance-step" data-provenance-step="source-record">
        <span>冻结来源</span>
        <p>
          <b>{sourceRecord.title}</b>
          <small>{`${sourceRecord.kind} · ${sourceRecord.sourceScope} · 版本 ${sourceRecord.sourceVersion}`}</small>
        </p>
        <p className="provenance-uri">{sourceRecord.canonicalUri}</p>
        <p className="provenance-hash">
          <code>{sourceRecord.contentHash}</code>
        </p>
        {sourceRecord.spans.length > 0 ? (
          <ul className="provenance-spans" aria-label="引用片段">
            {sourceRecord.spans.map((span) => (
              <li key={span.id}>
                <blockquote>{span.quote}</blockquote>
                <code>{span.quoteHash}</code>
              </li>
            ))}
          </ul>
        ) : (
          <p className="provenance-spans-empty">该来源没有已冻结的引用片段。</p>
        )}
      </div>
    </section>
  );
}

/**
 * Same-source group: N citations from one origin contribute exactly
 * `independentSourceCountContribution` independent source(s) — the UI states
 * this explicitly so three articles from one origin never read as three
 * independent confirmations.
 */
export function SameSourceGroupNote({ group }: { group: SameSourceGroupView }) {
  const memberCount = group.memberEvidenceItemIds.length;
  return (
    <section className="same-source-group" aria-label="同源组">
      <h3>独立来源计数</h3>
      {group.independentSourceGroupId ? (
        <p data-same-source-count={group.independentSourceCountContribution}>
          {`该证据属于同源组：组内 ${memberCount} 条引用共计 ${group.independentSourceCountContribution} 个独立来源（同源多篇不叠加）。`}
        </p>
      ) : (
        <p data-same-source-count={group.independentSourceCountContribution}>
          {`该证据未归入同源组，独立来源贡献为 ${group.independentSourceCountContribution}。`}
        </p>
      )}
      {memberCount > 1 && (
        <ul aria-label="同源组成员">
          {group.memberEvidenceItemIds.map((memberId) => (
            <li key={memberId}>
              <code>{memberId}</code>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Support/oppose projection; the two directions stay separate, never netted. */
export function DirectionPanel({ direction }: { direction: EvidenceDirectionView }) {
  return (
    <section className="evidence-direction" aria-label="支持与反对方向">
      <h3>方向</h3>
      <div className="direction-column" data-direction="supports">
        <span>支持的命题</span>
        {direction.supportsClaimIds.length > 0 ? (
          <ul>
            {direction.supportsClaimIds.map((claimId) => (
              <li key={claimId}>
                <code>{claimId}</code>
              </li>
            ))}
          </ul>
        ) : (
          <p>无</p>
        )}
      </div>
      <div className="direction-column" data-direction="contradicts">
        <span>反对的命题</span>
        {direction.contradictsClaimIds.length > 0 ? (
          <ul>
            {direction.contradictsClaimIds.map((claimId) => (
              <li key={claimId}>
                <code>{claimId}</code>
              </li>
            ))}
          </ul>
        ) : (
          <p>无</p>
        )}
      </div>
    </section>
  );
}
