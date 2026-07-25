// Four-tier evidence verdict block (Task 11 B2). Presents the canonical
// verdict WITH its machine reason codes and (when supplied) applicability
// limits; the four-tier semantics come from 17-product-design-v2.md /
// app.types.EvidenceVerdict. `conditional` must surface its limits — the
// contract forbids a bare conditional verdict in report use.

import type { EvidenceVerdict } from "@/lib/api/evidence";

const verdictLabels: Record<EvidenceVerdict, { label: string; meaning: string }> = {
  accepted: { label: "采纳", meaning: "可支撑主要判断" },
  conditional: { label: "有条件采纳", meaning: "只支撑带条件的判断，必须携带限制" },
  lead_only: { label: "仅作线索", meaning: "只能触发下一轮检索，不进入核心结论" },
  rejected: { label: "不采纳", meaning: "不进入 Worker 证据集合" }
};

type VerdictBlockProps = {
  verdict: EvidenceVerdict;
  reasonCodes: string[];
  applicabilityLimits?: string[];
};

export function VerdictBlock({ verdict, reasonCodes, applicabilityLimits }: VerdictBlockProps) {
  const { label, meaning } = verdictLabels[verdict];
  return (
    <div className="verdict-block" data-evidence-verdict={verdict}>
      <p>
        <b>{`结论 ${label}`}</b>
        <span>{meaning}</span>
      </p>
      {reasonCodes.length > 0 ? (
        <ul className="verdict-reasons" aria-label="判定理由码">
          {reasonCodes.map((code) => (
            <li key={code}>
              <code>{code}</code>
            </li>
          ))}
        </ul>
      ) : (
        <p className="verdict-reasons-empty">网关未附理由码。</p>
      )}
      {applicabilityLimits && applicabilityLimits.length > 0 && (
        <div className="verdict-limits" aria-label="适用限制">
          <span>适用限制</span>
          <ul>
            {applicabilityLimits.map((limit) => (
              <li key={limit}>{limit}</li>
            ))}
          </ul>
        </div>
      )}
      {verdict === "conditional" && (!applicabilityLimits || applicabilityLimits.length === 0) && (
        <p className="verdict-limits-missing" role="note">
          该证据为有条件采纳但未携带限制说明；使用前需人工补齐限制。
        </p>
      )}
    </div>
  );
}
