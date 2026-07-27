/** @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { createElement, type ImgHTMLAttributes } from "react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import DecisionCasePage from "../app/(workspace)/cases/[decisionCaseId]/page";
import { CaseShell } from "../components/shell/CaseShell";
import { caseWorkspaces } from "../lib/shell/workspaces";

type MockImageProps = ImgHTMLAttributes<HTMLImageElement> & {
  priority?: boolean;
};

vi.mock("next/image", async () => {
  const ReactModule = await import("react");
  return {
    default: ({ priority, ...imageProps }: MockImageProps) => {
      void priority;
      return ReactModule.createElement("img", imageProps);
    }
  };
});

// The empty view drives the real guest-backed create flow; unit tests keep
// the network and navigation seams mocked (the golden path covers the wire).
const { createDecisionCaseMock, navigateToCreatedCaseMock } = vi.hoisted(() => ({
  createDecisionCaseMock: vi.fn(),
  navigateToCreatedCaseMock: vi.fn()
}));

vi.mock("@/lib/shell/createCase", () => ({
  CaseCreateFlowError: class CaseCreateFlowError extends Error {},
  createDecisionCase: createDecisionCaseMock,
  navigateToCreatedCase: navigateToCreatedCaseMock
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  document.body.classList.remove("empty-case");
  window.history.replaceState(null, "", "/");
});

async function renderCasePage(decisionCaseId: string) {
  const ui = await DecisionCasePage({ params: Promise.resolve({ decisionCaseId }) });
  return render(ui);
}

const workspaceHeadings: Record<string, RegExp> = {
  workspace: /决策项目 LX-2407/,
  analysis: /研究尚未开始/,
  report: /报告尚未生成/,
  sandbox: /推演尚未开放/,
  decision: /还没有可以冻结的判断/
};

describe("Case shell route skeleton (Task 11 Phase 0 Session A)", () => {
  test("renders the case route with landmarks and the five-workspace spine", async () => {
    const { container } = await renderCasePage("LX-2407");

    // jsdom's accessibility mapping also reports section-scoped view intros
    // as banner, so the masthead is asserted structurally instead.
    expect(container.querySelector(":scope > .app-shell > header.masthead")).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
    const spine = screen.getByRole("navigation", { name: "决策生命周期" });

    const steps = within(spine).getAllByRole("button");
    // Five workspaces + the disabled Task 14W review trigger slot.
    expect(steps).toHaveLength(6);
    for (const { label } of caseWorkspaces) {
      expect(within(spine).getByRole("button", { name: new RegExp(label) })).toBeInTheDocument();
    }

    const active = within(spine).getByRole("button", { name: /问题/ });
    expect(active).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("heading", { level: 1, name: workspaceHeadings.workspace })).toBeVisible();

    const review = within(spine).getByRole("button", { name: /复盘/ });
    expect(review).toBeDisabled();
    expect(review).toHaveAttribute("data-phase-slot", "review-dialog-trigger");
  });

  test("switches across all five workspaces with a single active structured view", async () => {
    const user = userEvent.setup();
    const { container } = await renderCasePage("LX-2407");
    const spine = screen.getByRole("navigation", { name: "决策生命周期" });

    for (const { id, label } of caseWorkspaces) {
      await user.click(within(spine).getByRole("button", { name: new RegExp(label) }));

      expect(screen.getByRole("heading", { level: 1, name: workspaceHeadings[id] })).toBeVisible();
      const activeViews = container.querySelectorAll("section.view.is-active");
      expect(activeViews).toHaveLength(1);
      expect(activeViews[0]).toHaveAttribute("data-view-panel", id);
      expect(within(spine).getByRole("button", { name: new RegExp(label) })).toHaveAttribute("aria-current", "page");
      await waitFor(() => expect(window.location.search).toContain(`view=${id}`));
    }
  });

  test("restores the requested workspace from the view query param", async () => {
    window.history.replaceState(null, "", "/cases/LX-2407?view=sandbox");
    render(createElement(CaseShell, { decisionCaseId: "LX-2407" }));

    await waitFor(() => expect(screen.getByRole("heading", { level: 1, name: workspaceHeadings.sandbox })).toBeVisible());
    const spine = screen.getByRole("navigation", { name: "决策生命周期" });
    expect(within(spine).getByRole("button", { name: /推演/ })).toHaveAttribute("aria-current", "page");
  });

  test("supports arrow key navigation along the spine", async () => {
    const user = userEvent.setup();
    await renderCasePage("LX-2407");
    const spine = screen.getByRole("navigation", { name: "决策生命周期" });

    const first = within(spine).getByRole("button", { name: /问题/ });
    first.focus();
    await user.keyboard("{ArrowDown}");
    expect(within(spine).getByRole("button", { name: /证据/ })).toHaveFocus();
    await user.keyboard("{End}");
    expect(within(spine).getByRole("button", { name: /决定/ })).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(first).toHaveFocus();
    await user.keyboard("{ArrowUp}");
    expect(within(spine).getByRole("button", { name: /决定/ })).toHaveFocus();
    await user.keyboard("{Home}");
    expect(first).toHaveFocus();
  });

  test("keeps stable phase slots exposed without fabricated analysis data", async () => {
    const user = userEvent.setup();
    const { container } = await renderCasePage("LX-2407");

    // Session B filled the project-drawer slot: the trigger is now live.
    const projectTrigger = container.querySelector('[data-phase-slot="project-drawer"]');
    expect(projectTrigger).toBeEnabled();
    expect(projectTrigger).toHaveAttribute("aria-haspopup", "dialog");
    expect(container.querySelector('[data-phase-slot="analysis-charter-form"]')).toBeInTheDocument();
    expect(container.querySelector('[data-phase-slot="decision-health-bar"]')).toBeInTheDocument();

    const spine = screen.getByRole("navigation", { name: "决策生命周期" });
    await user.click(within(spine).getByRole("button", { name: /证据/ }));
    expect(container.querySelector('[data-analysis-launch]')).toBeInTheDocument();
    expect(container.querySelector('[data-phase-slot="quality-gate-panel"]')).toBeInTheDocument();
    expect(container.querySelector('[data-phase-slot="evidence-drawer-trigger"]')).toBeInTheDocument();
    // No total confidence percentage and no fabricated counters anywhere.
    expect(container.textContent).not.toMatch(/\d+\s*%/);

    await user.click(within(spine).getByRole("button", { name: /决定/ }));
    expect(container.querySelector('[data-signoff-panel]')).toBeInTheDocument();
  });

  test("renders the question-first empty state without a template card wall", async () => {
    const user = userEvent.setup();
    createDecisionCaseMock.mockResolvedValue({
      workspaceId: "ws-guest-1",
      decisionCaseId: "case-123",
      version: 1,
      title: "先验证哪一个市场方向？",
      clarifyingQuestions: []
    });
    const { container } = await renderCasePage("new");

    expect(screen.getByRole("heading", { level: 1, name: /先写下一个真正需要承担后果的问题/ })).toBeVisible();
    expect(container.querySelector('section.view.is-active[data-view-panel="empty"]')).toBeInTheDocument();
    // No template card wall, no example gallery, no fabricated folio counters.
    expect(container.querySelector(".empty-examples")).not.toBeInTheDocument();
    expect(container.querySelector(".folio-counts")).not.toBeInTheDocument();
    expect(document.body).toHaveClass("empty-case");
    // Session B: the project trigger stays honest about the missing case but
    // is enabled so the drawer (real workspace list) remains reachable.
    expect(screen.getByRole("button", { name: /尚未创建决策项目/ })).toBeEnabled();

    // Human-owned draft flow: empty submit returns focus to the question and
    // never reaches the network.
    await user.click(screen.getByRole("button", { name: /建立决策项目/ }));
    expect(screen.getByRole("status")).toHaveTextContent("先写下一个需要承担后果的问题。");
    expect(screen.getByLabelText("现在最需要看清的取舍是什么？")).toHaveFocus();
    expect(createDecisionCaseMock).not.toHaveBeenCalled();

    // Real create flow: guest-backed POST /cases, then open the case route.
    await user.type(screen.getByLabelText("现在最需要看清的取舍是什么？"), "先验证哪一个市场方向？");
    await user.click(screen.getByRole("button", { name: /建立决策项目/ }));
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("决策项目已建立，正在打开工作台…")
    );
    expect(createDecisionCaseMock).toHaveBeenCalledWith("先验证哪一个市场方向？");
    expect(navigateToCreatedCaseMock).toHaveBeenCalledWith(
      expect.objectContaining({ decisionCaseId: "case-123", workspaceId: "ws-guest-1" })
    );
  });

  test("keeps an honest failure notice when the create flow fails", async () => {
    const user = userEvent.setup();
    createDecisionCaseMock.mockRejectedValue(new Error("boom"));
    await renderCasePage("new");

    await user.type(screen.getByLabelText("现在最需要看清的取舍是什么？"), "先验证哪一个市场方向？");
    await user.click(screen.getByRole("button", { name: /建立决策项目/ }));

    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("建立决策项目失败，请稍后重试。")
    );
    expect(navigateToCreatedCaseMock).not.toHaveBeenCalled();
    // The button recovers so the human can retry.
    expect(screen.getByRole("button", { name: /建立决策项目/ })).toBeEnabled();
  });
});
