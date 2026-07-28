/**
 * Report export + evidence-link helpers (R1-3).
 *
 * Evidence ids are minted by the backend funnel as
 * `ev-retrieving-001 [L2] https://real.url/...` - the URL is REAL retrieval
 * output, so the UI renders it as a clickable link. The Markdown export is a
 * faithful projection of the canonical structured content with the
 * contentHash fingerprint in the footer, so a report shared outside the
 * system stays verifiable against the signed artifact.
 */

export type EvidenceParts = {
  id: string;
  tier: string | null;
  url: string | null;
  label: string;
};

/** Split a minted evidence id into display parts; never invents a URL. */
export function parseEvidenceId(raw: string): EvidenceParts {
  const text = String(raw ?? "").trim();
  const tierMatch = text.match(/\[(L[1-6]|L0)\]/);
  const urlMatch = text.match(/https?:\/\/\S+/);
  return {
    id: text.split(" ")[0] ?? text,
    tier: tierMatch ? tierMatch[1] : null,
    url: urlMatch ? urlMatch[0] : null,
    label: text,
  };
}

type Dict = Record<string, unknown>;

function asDict(value: unknown): Dict {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Dict) : {};
}

function asList(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function text(value: unknown): string {
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

/** Canonical report detail -> shareable Markdown (hash fingerprint footer). */
export function reportToMarkdown(detail: Dict): string {
  const content = asDict(detail.structuredContent ?? detail.content);
  const brief = asDict(content.executiveBrief);
  const recommendation = asDict(content.recommendation);
  const evidence = asDict(content.evidenceReview);
  const lines: string[] = [];

  lines.push(`# ${text(detail.title) || "决策分析报告"}`);
  lines.push("");
  if (text(brief.decision)) {
    lines.push("## 结论");
    lines.push(text(brief.decision));
    lines.push("");
  }
  const rationale = asList(brief.keyPoints ?? brief.rationale);
  if (rationale.length > 0) {
    lines.push("## 关键依据");
    for (const point of rationale) lines.push(`- ${text(asDict(point).text ?? point)}`);
    lines.push("");
  }
  const risks = asList(recommendation.risks);
  if (risks.length > 0) {
    lines.push("## 风险");
    for (const risk of risks) lines.push(`- ${text(asDict(risk).text ?? risk)}`);
    lines.push("");
  }
  const counters = asList(content.counterArguments);
  if (counters.length > 0) {
    lines.push("## 反方意见（保留原文）");
    for (const item of counters) lines.push(`- ${text(asDict(item).text ?? item)}`);
    lines.push("");
  }
  const uncertainty = asList(content.residualUncertainty);
  if (uncertainty.length > 0) {
    lines.push("## 未决问题");
    for (const item of uncertainty) lines.push(`- ${text(asDict(item).question ?? item)}`);
    lines.push("");
  }
  const actions = asList(content.nextActions);
  if (actions.length > 0) {
    lines.push("## 下一步行动");
    for (const item of actions) lines.push(`- ${text(asDict(item).text ?? item)}`);
    lines.push("");
  }
  const evidenceIds = asList(evidence.evidenceIds);
  if (evidenceIds.length > 0) {
    lines.push("## 证据清单");
    for (const raw of evidenceIds) {
      const parts = parseEvidenceId(text(raw));
      lines.push(parts.url ? `- ${parts.id} [${parts.tier ?? "?"}] <${parts.url}>` : `- ${parts.label}`);
    }
    lines.push("");
  }
  lines.push("---");
  lines.push(`> 本报告由 Ludus 生成 · 内容指纹 contentHash: ${text(detail.contentHash) || "(未提供)"}`);
  lines.push(`> 报告 ID: ${text(detail.id ?? detail.reportId) || "(未提供)"} · 状态: ${text(detail.status)}`);
  return lines.join("\n");
}

/** Trigger a browser download of the Markdown projection. */
export function downloadReportMarkdown(detail: Dict): void {
  const markdown = reportToMarkdown(detail);
  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `ludus-report-${text(detail.id ?? detail.reportId) || "export"}.md`;
  anchor.click();
  URL.revokeObjectURL(url);
}
