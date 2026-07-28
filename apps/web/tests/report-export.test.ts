import { describe, expect, test } from "vitest";

import { parseEvidenceId, reportToMarkdown } from "@/lib/shell/reportExport";

// R1-3 battery: evidence ids with REAL urls become clickable parts, and the
// Markdown projection keeps the contentHash fingerprint so shared reports
// stay verifiable.

describe("parseEvidenceId", () => {
  test("extracts tier and url from a minted evidence id", () => {
    const parts = parseEvidenceId(
      "ev-retrieving-002 [L2] https://competition-policy.ec.europa.eu/doc.pdf",
    );
    expect(parts.id).toBe("ev-retrieving-002");
    expect(parts.tier).toBe("L2");
    expect(parts.url).toBe("https://competition-policy.ec.europa.eu/doc.pdf");
  });

  test("never invents a url for model-internal evidence", () => {
    const parts = parseEvidenceId("ev-retrieving-001 [L6] model-internal reasoning (no external source)");
    expect(parts.tier).toBe("L6");
    expect(parts.url).toBeNull();
  });
});

describe("reportToMarkdown", () => {
  test("projects the canonical sections and pins the contentHash footer", () => {
    const markdown = reportToMarkdown({
      id: "rep-1",
      title: "独家分销决策报告",
      status: "ready",
      contentHash: "sha256:abc123",
      structuredContent: {
        executiveBrief: { decision: "仅在签署排他 LOI 后推进。" },
        recommendation: { risks: [{ text: "单一买家依赖" }] },
        counterArguments: [{ text: "对手 60 天可复制该报价。" }],
        residualUncertainty: [{ question: "买家是否愿签排他？" }],
        nextActions: [{ text: "两周内拿到 LOI 草案。" }],
        evidenceReview: {
          evidenceIds: ["ev-retrieving-002 [L2] https://ec.europa.eu/doc.pdf"],
        },
      },
    });
    expect(markdown).toContain("# 独家分销决策报告");
    expect(markdown).toContain("仅在签署排他 LOI 后推进。");
    expect(markdown).toContain("对手 60 天可复制该报价。");
    expect(markdown).toContain("<https://ec.europa.eu/doc.pdf>");
    expect(markdown).toContain("contentHash: sha256:abc123");
  });

  test("degrades honestly when fields are missing", () => {
    const markdown = reportToMarkdown({});
    expect(markdown).toContain("# 决策分析报告");
    expect(markdown).toContain("contentHash: (未提供)");
  });
});
