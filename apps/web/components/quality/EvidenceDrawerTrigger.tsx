"use client";

// evidence-drawer-trigger slot filler (Task 11 B2). Replaces exactly the
// PhaseSlot anchor node in AnalysisView custody-strip / ReportView
// dissent-page per apps/web/lib/shell/slotContracts.ts
// (mount: "replace-phase-slot-node"); the root keeps the
// `data-phase-slot="evidence-drawer-trigger"` anchor so the shell contract
// and its coverage tests stay intact.
//
// READ-01 flip: the canonical case→run resolution route shipped, so when the
// host provides { workspaceId, decisionCaseId } the trigger resolves the
// newest run's anchors asynchronously (honest null on 404/empty/error).
// Callers with real anchors still override the resolution.

import { useCallback, useEffect, useRef, useState } from "react";

import type { EvidenceEventSourceFactory, EvidenceRunAnchors } from "@/lib/api/evidence";
import { resolveEvidenceAnchors } from "@/lib/api/evidence";

import { EvidenceDrawer } from "./EvidenceDrawer";

export type EvidenceDrawerTriggerProps = {
  workspaceId?: string;
  decisionCaseId?: string;
  /** Real run anchors, when the caller has them; overrides case resolution. */
  anchors?: EvidenceRunAnchors | null;
  fetchImpl?: typeof fetch;
  eventSourceFactory?: EvidenceEventSourceFactory | null;
  slowThresholdMs?: number;
};

export function EvidenceDrawerTrigger({
  workspaceId,
  decisionCaseId,
  anchors,
  fetchImpl,
  eventSourceFactory,
  slowThresholdMs
}: EvidenceDrawerTriggerProps) {
  const [open, setOpen] = useState(false);
  const [resolved, setResolved] = useState<EvidenceRunAnchors | null>(null);
  const triggerButton = useRef<HTMLButtonElement>(null);

  const shouldResolve = anchors === undefined && Boolean(workspaceId && decisionCaseId);

  useEffect(() => {
    if (!shouldResolve || !workspaceId || !decisionCaseId) return;
    let cancelled = false;
    void resolveEvidenceAnchors(workspaceId, decisionCaseId, fetchImpl ?? fetch).then(
      (result) => {
        if (!cancelled) setResolved(result);
      }
    );
    return () => {
      cancelled = true;
    };
  }, [shouldResolve, workspaceId, decisionCaseId, fetchImpl]);

  const resolvedAnchors = anchors !== undefined ? anchors : shouldResolve ? resolved : null;

  // Focus returns to the trigger on close (drawer trap follows ProjectDrawer).
  const closeDrawer = useCallback(() => {
    setOpen(false);
    triggerButton.current?.focus();
  }, []);

  return (
    <div className="evidence-drawer-trigger" data-phase-slot="evidence-drawer-trigger">
      <p>原始来源 → 命题 → 判断 → 决定：每条结论的证据链可查。</p>
      <button
        ref={triggerButton}
        type="button"
        className="secondary-action"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(true)}
      >
        查看证据溯源
      </button>
      <EvidenceDrawer
        open={open}
        onClose={closeDrawer}
        anchors={resolvedAnchors}
        {...(fetchImpl ? { fetchImpl } : {})}
        {...(eventSourceFactory !== undefined ? { eventSourceFactory } : {})}
        {...(slowThresholdMs !== undefined ? { slowThresholdMs } : {})}
      />
    </div>
  );
}
