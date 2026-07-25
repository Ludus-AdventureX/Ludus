import type { Metadata } from "next";

import { CaseShell } from "@/components/shell/CaseShell";

// Stable case route skeleton for the five-workspace shell (Task 11 Phase 0).
// The reserved segment `new` renders the empty state until the Case create
// flow lands; any other segment is treated as an opaque DecisionCase id.
// No case/analysis API is read in Phase 0.

export const metadata: Metadata = {
  title: "决策项目 · Ludus"
};

export const runtime = "edge";

const EMPTY_CASE_SEGMENT = "new";

type DecisionCasePageProps = {
  params: Promise<{ decisionCaseId: string }>;
};

export default async function DecisionCasePage({ params }: DecisionCasePageProps) {
  const { decisionCaseId } = await params;
  const caseId = decodeURIComponent(decisionCaseId).trim();
  const isEmpty = caseId.length === 0 || caseId === EMPTY_CASE_SEGMENT;
  return <CaseShell decisionCaseId={isEmpty ? null : caseId} />;
}
