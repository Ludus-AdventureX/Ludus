import type { Metadata } from "next";

import { CaseShell } from "@/components/shell/CaseShell";

// Stable case route skeleton for the five-workspace shell (Task 11 Phase 0).
// The reserved segment `new` renders the empty state until the Case create
// flow lands; any other segment is treated as an opaque DecisionCase id.
// The optional ?ws= query threads the tenant workspace anchor so the READ
// views can resolve real analysis/report data for the case.

export const metadata: Metadata = {
  title: "决策项目 · Ludus"
};

export const runtime = "edge";

const EMPTY_CASE_SEGMENT = "new";

type DecisionCasePageProps = {
  params: Promise<{ decisionCaseId: string }>;
  searchParams?: Promise<{ ws?: string | string[] }>;
};

export default async function DecisionCasePage({ params, searchParams }: DecisionCasePageProps) {
  const { decisionCaseId } = await params;
  const { ws } = (await searchParams) ?? {};
  const caseId = decodeURIComponent(decisionCaseId).trim();
  const isEmpty = caseId.length === 0 || caseId === EMPTY_CASE_SEGMENT;
  const tenantWorkspaceId = typeof ws === "string" && ws.trim().length > 0 ? ws.trim() : null;
  return <CaseShell decisionCaseId={isEmpty ? null : caseId} tenantWorkspaceId={tenantWorkspaceId} />;
}
