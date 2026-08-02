// Decision health aggregation (five live segments for the DecisionHealthBar).
//
// Every segment resolves REAL state from the canonical read surfaces that
// already exist - evidence ledger, sandbox graph, ready reports, latest run
// gate verdict, case/dossier versions. No fabricated verdicts: each source
// degrades independently to an honest "读取失败" on error, and "empty" when
// the surface legitimately has nothing yet.
//
// Navigation targets are the five case workspaces (Q/E/J/G/D); the bar links
// full-page so the shell's drawer/replaceState effects cannot clobber the
// navigation (same live finding as ProjectDrawer).

import { useEffect, useState } from "react";

import { fetchCaseDetail } from "@/lib/shell/caseData";
import { listCaseAnalyses } from "@/lib/shell/runReads";
import { listCaseReports } from "@/lib/shell/caseActions";
import { loadSandboxCaseData } from "@/components/simulation/sandboxData";
import { fetchRunEvidence, resolveEvidenceAnchors } from "@/lib/api/evidence";
import type { CaseWorkspaceId } from "@/lib/shell/workspaces";

export type DecisionHealthSegmentState = {
  id: string;
  coordinate: string;
  label: string;
  /** null = link unavailable (loading/error/no data yet) -> disabled button. */
  href: string | null;
  status: "loading" | "ok" | "empty" | "blocked" | "error";
  summary: string;
};

type SegmentSpec = {
  id: string;
  coordinate: string;
  label: string;
  targetView: CaseWorkspaceId;
};

const SEGMENT_SPECS: SegmentSpec[] = [
  { id: "evidence", coordinate: "E", label: "证据", targetView: "analysis" },
  { id: "causal-chain", coordinate: "C", label: "因果链", targetView: "sandbox" },
  { id: "strategic-robustness", coordinate: "S", label: "战略稳健性", targetView: "report" },
  { id: "quality-gate", coordinate: "G", label: "质量门", targetView: "analysis" },
  { id: "version", coordinate: "V", label: "版本", targetView: "workspace" },
];

function loadingSegments(): DecisionHealthSegmentState[] {
  return SEGMENT_SPECS.map((spec) => ({
    ...spec,
    href: null,
    status: "loading",
    summary: "读取中…",
  }));
}

function hrefFor(workspaceId: string, decisionCaseId: string, view: CaseWorkspaceId): string {
  return `/cases/${encodeURIComponent(decisionCaseId)}?ws=${encodeURIComponent(workspaceId)}&view=${view}`;
}

export function useDecisionHealth(
  workspaceId: string | null,
  decisionCaseId: string | undefined,
): DecisionHealthSegmentState[] {
  const [segments, setSegments] = useState<DecisionHealthSegmentState[]>(loadingSegments);

  useEffect(() => {
    if (!workspaceId || !decisionCaseId) return;
    let cancelled = false;
    setSegments(loadingSegments());

    (async () => {
      const baseHref = (view: CaseWorkspaceId) => hrefFor(workspaceId, decisionCaseId, view);

      // Independent best-effort sources; every lane degrades on its own.
      const [detail, runs, reports, sandbox, anchors] = await Promise.allSettled([
        fetchCaseDetail(workspaceId, decisionCaseId),
        listCaseAnalyses(workspaceId, decisionCaseId),
        listCaseReports(workspaceId, decisionCaseId),
        loadSandboxCaseData(workspaceId, decisionCaseId),
        resolveEvidenceAnchors(workspaceId, decisionCaseId),
      ]);

      if (cancelled) return;

      // Evidence ledger needs a second hop (anchors -> run evidence items).
      let evidenceSummary = "读取失败";
      let evidenceStatus: DecisionHealthSegmentState["status"] = "error";
      let evidenceHref: string | null = null;
      if (anchors.status === "fulfilled" && anchors.value) {
        evidenceHref = baseHref("analysis");
        try {
          const ledger = await fetchRunEvidence(anchors.value);
          if (cancelled) return;
          const count = ledger.items.length;
          evidenceSummary = count > 0 ? `已收录 ${count} 条证据` : "尚无证据记录";
          evidenceStatus = count > 0 ? "ok" : "empty";
        } catch {
          evidenceSummary = "读取失败";
          evidenceStatus = "error";
        }
      } else if (anchors.status === "fulfilled") {
        evidenceSummary = "尚无证据记录";
        evidenceStatus = "empty";
      }

      const version: DecisionHealthSegmentState =
        detail.status === "fulfilled"
          ? {
              ...SEGMENT_SPECS[4]!,
              href: baseHref("workspace"),
              status: "ok",
              summary: `CaseVersion v${detail.value.caseVersion} · Dossier v${detail.value.confirmedDossierVersion}`,
            }
          : { ...SEGMENT_SPECS[4]!, href: null, status: "error", summary: "读取失败" };

      const causal: DecisionHealthSegmentState =
        sandbox.status === "fulfilled" && sandbox.value
          ? {
              ...SEGMENT_SPECS[1]!,
              href: baseHref("sandbox"),
              status: "ok",
              summary: `已构建 ${sandbox.value.graph.nodes.length} 节点`,
            }
          : sandbox.status === "rejected"
            ? { ...SEGMENT_SPECS[1]!, href: null, status: "error", summary: "读取失败" }
            : { ...SEGMENT_SPECS[1]!, href: baseHref("sandbox"), status: "empty", summary: "未构建推演图" };

      const robustness: DecisionHealthSegmentState =
        reports.status === "fulfilled"
          ? (() => {
              const ready = reports.value.filter((r) => r.status === "ready").length;
              return ready > 0
                ? { ...SEGMENT_SPECS[2]!, href: baseHref("report"), status: "ok", summary: `${ready} 份 ready 报告` }
                : { ...SEGMENT_SPECS[2]!, href: baseHref("report"), status: "empty", summary: "无 ready 报告" };
            })()
          : { ...SEGMENT_SPECS[2]!, href: null, status: "error", summary: "读取失败" };

      const gate: DecisionHealthSegmentState =
        runs.status === "fulfilled"
          ? (() => {
              const latest = runs.value[0];
              if (!latest) {
                return { ...SEGMENT_SPECS[3]!, href: baseHref("analysis"), status: "empty", summary: "未运行分析" };
              }
              if (latest.status === "ready") {
                return { ...SEGMENT_SPECS[3]!, href: baseHref("analysis"), status: "ok", summary: "最近一次：通过" };
              }
              if (latest.status === "blocked") {
                return { ...SEGMENT_SPECS[3]!, href: baseHref("analysis"), status: "blocked", summary: "最近一次：被质量门拦截" };
              }
              return { ...SEGMENT_SPECS[3]!, href: baseHref("analysis"), status: "empty", summary: `最近一次：${latest.status}` };
            })()
          : { ...SEGMENT_SPECS[3]!, href: null, status: "error", summary: "读取失败" };

      setSegments([
        { ...SEGMENT_SPECS[0]!, href: evidenceHref, status: evidenceStatus, summary: evidenceSummary },
        causal,
        robustness,
        gate,
        version,
      ]);
    })();

    return () => { cancelled = true; };
  }, [workspaceId, decisionCaseId]);

  return segments;
}
