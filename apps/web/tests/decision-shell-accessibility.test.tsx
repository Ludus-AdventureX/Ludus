/** @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { createElement, type ImgHTMLAttributes } from "react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import path from "node:path";
import { afterEach, describe, expect, test, vi } from "vitest";

import { DecisionShell } from "../components/shell/DecisionShell";

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

// The homepage shell drives the real guest-backed create flow; unit tests
// keep the network and navigation seams mocked (the golden path covers wire).
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
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
  window.history.replaceState(null, "", "/");
});

async function renderShell() {
  window.history.replaceState(null, "", "/");
  window.localStorage.clear();
  const result = render(createElement(DecisionShell));
  await waitFor(() => expect(document.documentElement.dataset.theme).toBe("ink"));
  return result;
}

describe("DecisionShell Look V7 release gates", () => {
  test("keeps empty submit human-owned and returns focus to the question", async () => {
    const user = userEvent.setup();
    await renderShell();

    await user.click(screen.getByRole("button", { name: /建立决策项目/ }));

    expect(screen.getByRole("status")).toHaveTextContent("先写下一个需要承担后果的问题。");
    expect(screen.getByLabelText("现在最需要看清的取舍是什么？")).toHaveFocus();
    expect(createDecisionCaseMock).not.toHaveBeenCalled();
  });

  test("fills an example prompt, then creates the real decision case", async () => {
    const user = userEvent.setup();
    createDecisionCaseMock.mockResolvedValue({
      workspaceId: "ws-guest-1",
      decisionCaseId: "case-123",
      version: 1,
      title: "扩大当前市场还是转向细分机会？",
      clarifyingQuestions: []
    });
    const { container } = await renderShell();
    const question = screen.getByLabelText("现在最需要看清的取舍是什么？");

    await user.click(screen.getByRole("button", { name: /方向取舍/ }));
    expect(question).toHaveFocus();
    expect(question).toHaveValue("我们应该继续扩大当前市场，还是把资源转向一个更小但更确定的细分机会？");

    await user.click(screen.getByRole("button", { name: /建立决策项目/ }));

    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("决策项目已建立，正在打开工作台…")
    );
    expect(container.querySelector("#emptyCaseForm")).toHaveClass("is-drafted");
    expect(createDecisionCaseMock).toHaveBeenCalledWith(
      "我们应该继续扩大当前市场，还是把资源转向一个更小但更确定的细分机会？"
    );
    expect(navigateToCreatedCaseMock).toHaveBeenCalledWith(
      expect.objectContaining({ decisionCaseId: "case-123", workspaceId: "ws-guest-1" })
    );
  });

  test("names the theme drawer, moves focus inside, traps Tab, and returns focus on Escape", async () => {
    const user = userEvent.setup();
    await renderShell();
    const trigger = screen.getByRole("button", { name: /Switch theme: 水墨黑白/ });

    await user.click(trigger);

    const dialog = screen.getByRole("dialog", { name: "十种材料色" });
    const close = within(dialog).getByRole("button", { name: "Close drawer" });
    const apply = within(dialog).getByRole("button", { name: "应用并返回" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleName("十种材料色");
    await waitFor(() => expect(close).toHaveFocus());

    apply.focus();
    await user.tab();
    expect(close).toHaveFocus();

    close.focus();
    await user.tab({ shift: true });
    expect(apply).toHaveFocus();

    screen.getByLabelText("现在最需要看清的取舍是什么？").focus();
    await user.tab();
    expect(close).toHaveFocus();

    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  test("persists a selected theme and returns project drawer focus to its trigger", async () => {
    const user = userEvent.setup();
    await renderShell();

    const themeTrigger = screen.getByRole("button", { name: /Switch theme: 水墨黑白/ });
    await user.click(themeTrigger);
    const themeDialog = screen.getByRole("dialog", { name: "十种材料色" });
    await user.click(within(themeDialog).getByRole("radio", { name: /莫兰迪青/ }));
    await user.click(within(themeDialog).getByRole("button", { name: "应用并返回" }));

    await waitFor(() => expect(document.documentElement.dataset.theme).toBe("cyan"));
    expect(window.localStorage.getItem("ludus-theme-v7")).toBe("cyan");
    expect(window.location.search).toContain("theme=cyan");
    await waitFor(() => expect(themeTrigger).toHaveFocus());

    const projectTrigger = screen.getByRole("button", { name: /尚未创建决策项目/ });
    await user.click(projectTrigger);
    const projectDialog = screen.getByRole("dialog", { name: "项目与空工作台" });
    expect(projectDialog).toHaveAccessibleName("项目与空工作台");
    expect(projectDialog.contains(document.activeElement)).toBe(true);

    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(projectTrigger).toHaveFocus());
  });

  test("locks the mobile drawer controls to the 44 by 44 CSS pixel contract", () => {
    const styles = readFileSync(path.join(process.cwd(), "app", "look-styles.css"), "utf8");
    const themes = readFileSync(path.join(process.cwd(), "app", "look-themes.css"), "utf8");

    expect(styles).toMatch(/\.mobile-case-trigger\s*\{[^}]*width:\s*44px;[^}]*height:\s*44px;/);
    expect(styles).toMatch(/\.drawer-close\s*\{[^}]*width:\s*44px;[^}]*height:\s*44px;/);
    expect(styles).toMatch(/\.primary-action\.small\s*\{[^}]*min-height:\s*44px;/);
    expect(themes).toMatch(/@media \(max-width: 900px\)\s*\{[\s\S]*\.theme-trigger\s*\{[^}]*width:\s*44px;[^}]*min-width:\s*44px;[^}]*height:\s*44px;/);
  });
});