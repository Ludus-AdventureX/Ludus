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

// NOTE: no `export const runtime = "edge"` here. It was declared and it broke the
// page in production: `next build && next start` (and the standalone output the
// compose deploy runs) answered 500 with `Could not find the module ... in the
// React Server Consumer Manifest` for every case URL, because this route's
// client components are bundled for the Node server while the edge declaration
// asks for the edge manifest. Dev mode hid it. The deployment target is a Node
// container, so the honest runtime is the default one.

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
