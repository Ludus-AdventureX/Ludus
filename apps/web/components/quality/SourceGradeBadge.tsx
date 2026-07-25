// L1-L6 source CATEGORY badge (Task 11 B2). The six tiers are canonical
// wire literals (06-data-model.md L672) describing what KIND of source this
// is — they are orthogonal to the numeric quality dimensions and never imply
// a credibility score. Unknown grades render verbatim without inventing a
// category (schemas_api.py ships sourceGrade as a plain wire string).

import type { KnownSourceGrade } from "@/lib/api/evidence";
import { knownSourceGrades } from "@/lib/api/evidence";

const sourceGradeLabels: Record<KnownSourceGrade, { tier: string; label: string }> = {
  L1_primary: { tier: "L1", label: "一手来源" },
  L2_reputable: { tier: "L2", label: "权威来源" },
  L3_industry: { tier: "L3", label: "行业来源" },
  L4_general: { tier: "L4", label: "一般来源" },
  L5_opinion: { tier: "L5", label: "观点来源" },
  L6_unverified: { tier: "L6", label: "未核实来源" }
};

function isKnownSourceGrade(grade: string): grade is KnownSourceGrade {
  return (knownSourceGrades as readonly string[]).includes(grade);
}

export function SourceGradeBadge({ grade }: { grade: string }) {
  if (isKnownSourceGrade(grade)) {
    const { tier, label } = sourceGradeLabels[grade];
    return (
      <span className="source-grade-badge" data-source-grade={grade}>
        <b>{tier}</b>
        <span>{label}</span>
      </span>
    );
  }
  // Honest fallback: show the raw wire value, never guess a tier.
  return (
    <span className="source-grade-badge" data-source-grade={grade}>
      <span>{`未识别等级（${grade}）`}</span>
    </span>
  );
}
