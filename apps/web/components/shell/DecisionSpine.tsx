"use client";

import { KeyboardEvent, ReactNode, useRef } from "react";

import { caseWorkspaces, reviewTrigger, type CaseWorkspaceId } from "@/lib/shell/workspaces";

type DecisionSpineProps = {
  activeWorkspace: CaseWorkspaceId;
  onSelectWorkspace: (workspace: CaseWorkspaceId) => void;
  /** True while a modal drawer is open, so the spine leaves the tab order. */
  inert?: boolean;
  /**
   * Task 14W review dialog trigger slot. When absent, a disabled placeholder
   * step keeps the Look V7 spine geometry without pretending review exists.
   */
  reviewSlot?: ReactNode;
};

export function DecisionSpine({ activeWorkspace, onSelectWorkspace, inert, reviewSlot }: DecisionSpineProps) {
  const navRef = useRef<HTMLElement>(null);

  // Roving arrow-key navigation across the spine steps (Look app.js keyboard
  // behavior re-expressed for the production shell; app.js itself never loads).
  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    const keys = ["ArrowDown", "ArrowUp", "ArrowRight", "ArrowLeft", "Home", "End"];
    if (!keys.includes(event.key)) return;
    const nav = navRef.current;
    if (!nav) return;
    const steps = Array.from(nav.querySelectorAll<HTMLButtonElement>("button.spine-step:not([disabled])"));
    if (steps.length === 0) return;
    const current = document.activeElement instanceof HTMLButtonElement ? steps.indexOf(document.activeElement) : -1;
    let next: number;
    if (event.key === "Home") next = 0;
    else if (event.key === "End") next = steps.length - 1;
    else if (event.key === "ArrowDown" || event.key === "ArrowRight") next = current < 0 ? 0 : (current + 1) % steps.length;
    else next = current <= 0 ? steps.length - 1 : current - 1;
    event.preventDefault();
    steps[next].focus();
  };

  return (
    <nav ref={navRef} className="decision-spine" aria-label="决策生命周期" onKeyDown={onKeyDown} inert={inert}>
      <div className="spine-line" aria-hidden="true" />
      {caseWorkspaces.map(({ id, coordinate, label, description }) => {
        const active = activeWorkspace === id;
        return (
          <button
            key={id}
            type="button"
            className={active ? "spine-step is-active" : "spine-step"}
            data-view={id}
            aria-current={active ? "page" : undefined}
            onClick={() => onSelectWorkspace(id)}
          >
            <span className="step-coordinate">{coordinate}</span>
            <span className="step-copy"><b>{label}</b><small>{description}</small></span>
          </button>
        );
      })}
      {reviewSlot ?? (
        <button
          type="button"
          className="spine-step"
          data-phase-slot="review-dialog-trigger"
          disabled
          aria-disabled="true"
          title="复盘功能正在建设中"
        >
          <span className="step-coordinate">{reviewTrigger.coordinate}</span>
          <span className="step-copy"><b>{reviewTrigger.label}</b><small>{reviewTrigger.description}</small></span>
        </button>
      )}
    </nav>
  );
}
