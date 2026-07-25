// Orthogonal quality dimensions panel (Task 11 B2). Renders the seven
// numeric dimensions of QualityDimensionsView SEPARATELY, exactly as the
// gateway assessed them. Deliberate omissions (product contract,
// 04-decision-methodology.md「不确定性表达」): no aggregate credibility
// number, no percent formatting anywhere, no majority-vote rollup — the
// dimensions stay orthogonal to the L1-L6 source category.

import type { QualityDimensionsView } from "@/lib/api/evidence";

import { VerdictBlock } from "./VerdictBlock";

const dimensionLabels: ReadonlyArray<{
  key: keyof Pick<
    QualityDimensionsView,
    | "authenticity"
    | "sourceQuality"
    | "relevance"
    | "freshness"
    | "applicability"
    | "independence"
    | "extractionReliability"
  >;
  label: string;
}> = [
  { key: "authenticity", label: "真实性" },
  { key: "sourceQuality", label: "来源质量" },
  { key: "relevance", label: "相关性" },
  { key: "freshness", label: "时效" },
  { key: "applicability", label: "适用性" },
  { key: "independence", label: "独立性" },
  { key: "extractionReliability", label: "提取可靠性" }
];

/** Raw 0-1 assessment value; shown as a decimal, never as a percentage. */
function formatDimensionValue(value: number): string {
  return Number.isFinite(value) ? value.toFixed(2) : "无数值";
}

export function QualityDimensionsPanel({ quality }: { quality: QualityDimensionsView }) {
  return (
    <section className="evidence-quality-panel" aria-label="正交质量维度">
      <header>
        <h3>质量维度（正交，不合成总分）</h3>
        <p>各维度独立评估；系统不给出单一可信度总值。</p>
      </header>
      <dl className="quality-dimension-list">
        {dimensionLabels.map(({ key, label }) => (
          <div key={key} className="quality-dimension" data-quality-dimension={key}>
            <dt>{label}</dt>
            <dd>{formatDimensionValue(quality[key])}</dd>
          </div>
        ))}
      </dl>

      {quality.biasFlags.length > 0 && (
        <div className="quality-flags" data-quality-flags="bias">
          <span>偏见标记</span>
          <ul>
            {quality.biasFlags.map((flag) => (
              <li key={flag}>{flag}</li>
            ))}
          </ul>
        </div>
      )}

      {quality.completenessWarnings.length > 0 && (
        <div className="quality-flags" data-quality-flags="completeness">
          <span>完整性警告</span>
          <ul>
            {quality.completenessWarnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}

      <VerdictBlock verdict={quality.verdict} reasonCodes={quality.reasonCodes} />
      <p className="quality-assessed-at">{`评估时间 ${quality.assessedAt}`}</p>
    </section>
  );
}
