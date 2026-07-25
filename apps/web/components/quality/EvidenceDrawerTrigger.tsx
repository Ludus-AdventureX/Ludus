"use client";

// evidence-drawer-trigger slot filler (Task 11 B2). Replaces exactly the
// PhaseSlot anchor node in AnalysisView custody-strip / ReportView
// dissent-page per apps/web/lib/shell/slotContracts.ts
// (mount: "replace-phase-slot-node"); the root keeps the
// `data-phase-slot="evidence-drawer-trigger"` anchor so the shell contract
// and its coverage tests stay intact.
//
// Contract divergence, disclosed in the handoff: EvidenceDrawerTriggerSlotProps
// promises { decisionCaseId }, but the Phase 0 host views receive no props to
// forward (threading it through CaseViewRouter is a shell increment that
// needs authorization, Task 13 precedent). decisionCaseId is therefore
// optional here — and today no route resolves it to run anchors anyway
// (lib/api/evidence.ts single switch), so the drawer opens on the honest gap
// state in production. Tests and future callers pass real anchors directly.

import { useCallback, useRef, useState } from "react";

import type { EvidenceEventSourceFactory, EvidenceRunAnchors } from "@/lib/api/evidence";
import { resolveEvidenceAnchors } from "@/lib/api/evidence";

import { EvidenceDrawer } from "./EvidenceDrawer";

export type EvidenceDrawerTriggerProps = {
  decisionCaseId?: string;
  /** Real run anchors, when the caller has them; overrides case resolution. */
  anchors?: EvidenceRunAnchors | null;
  fetchImpl?: typeof fetch;
  eventSourceFactory?: EvidenceEventSourceFactory | null;
  slowThresholdMs?: number;
};

export function EvidenceDrawerTrigger({
  decisionCaseId,
  anchors,
  fetchImpl,
  eventSourceFactory,
  slowThresholdMs
}: EvidenceDrawerTriggerProps) {
  const [open, setOpen] = useState(false);
  const triggerButton = useRef<HTMLButtonElement>(null);

  const resolvedAnchors =
    anchors !== undefined ? anchors : decisionCaseId ? resolveEvidenceAnchors(decisionCaseId) : null;

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
