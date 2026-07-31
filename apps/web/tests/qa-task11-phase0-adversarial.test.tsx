/** @vitest-environment jsdom */

// QA adversarial supplement for Task 11 Phase 0 Shell (Sessions A+B).
// Candidate: codex/task-11-phase0-shell-b @ 3d687302448968abd3b0bf9922266992dcab80b6.
// These tests intentionally probe failure paths the candidate suite does not:
// focus-trap escape attempts, URL-restored drawer focus return, illegal
// ?view=/&panel= values, hostile session payloads around the 401/500 paths,
// and a11y spot checks (landmarks, inert, dialog semantics, spine keyboard).

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { createElement, type AnchorHTMLAttributes, type ImgHTMLAttributes, type ReactNode } from "react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { CaseShell } from "../components/shell/CaseShell";

type MockImageProps = ImgHTMLAttributes<HTMLImageElement> & { priority?: boolean };

vi.mock("next/image", async () => {
  const ReactModule = await import("react");
  return {
    default: ({ priority, ...imageProps }: MockImageProps) => {
      void priority;
      return ReactModule.createElement("img", imageProps);
    }
  };
});

type MockLinkProps = AnchorHTMLAttributes<HTMLAnchorElement> & { children: ReactNode };

vi.mock("next/link", async () => {
  const ReactModule = await import("react");
  return {
    default: ({ children, ...anchorProps }: MockLinkProps) =>
      ReactModule.createElement("a", anchorProps, children)
  };
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.body.classList.remove("empty-case");
  window.history.replaceState(null, "", "/");
});

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body
  } as unknown as Response;
}

const sessionEnvelope = {
  ok: true,
  data: {
    user: { id: "user-1", email: "owner@example.com", status: "active", createdAt: "2026-07-25T00:00:00Z" },
    session: {
      id: "session-1",
      createdAt: "2026-07-25T00:00:00Z",
      lastSeenAt: "2026-07-25T00:00:00Z",
      expiresAt: "2026-07-26T00:00:00Z"
    },
    memberships: [
      { workspaceId: "ws-1", workspaceName: "Personal Workspace", role: "owner", capabilities: [], status: "active" }
    ]
  }
};

describe("QA adversarial: Task 11 Phase 0 shell (A+B)", () => {
  test("focus trap resists escape attempts: shift-tab wrap and outside-focus recapture", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(200, sessionEnvelope)));
    const user = userEvent.setup();
    render(createElement(CaseShell, { decisionCaseId: "LX-2407" }));

    await user.click(screen.getByRole("button", { name: /决策项目 LX-2407/ }));
    const dialog = await screen.findByRole("dialog", { name: "项目与工作区" });
    await within(dialog).findByText("Personal Workspace");

    // Shift+Tab from the first focusable must wrap to the last, never leave.
    // The footer's last focusable is now the account action (logged-in state).
    const closeButton = within(dialog).getByRole("button", { name: "关闭项目抽屉" });
    closeButton.focus();
    await user.tab({ shift: true });
    expect(dialog).toContainElement(document.activeElement as HTMLElement);
    expect(document.activeElement).toBe(within(dialog).getByRole("button", { name: "退出登录" }));

    // If focus somehow lands outside the dialog, the next Tab recaptures it.
    (document.activeElement as HTMLElement).blur();
    expect(dialog.contains(document.activeElement)).toBe(false);
    await user.tab();
    expect(dialog).toContainElement(document.activeElement as HTMLElement);
  });

  test("Escape after a URL-restored open still returns focus to the masthead trigger", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(200, sessionEnvelope)));
    window.history.replaceState(null, "", "/cases/LX-2407?view=analysis&panel=projects");
    const user = userEvent.setup();
    render(createElement(CaseShell, { decisionCaseId: "LX-2407" }));

    // Drawer opened via URL restore: no click ever registered a trigger.
    const dialog = await screen.findByRole("dialog", { name: "项目与工作区" });
    await within(dialog).findByText("Personal Workspace");

    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    // Fallback focus target is the masthead project trigger, not <body>.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /决策项目 LX-2407/ })).toHaveFocus()
    );
    await waitFor(() => expect(window.location.search).not.toContain("panel=projects"));
    expect(window.location.search).toContain("view=analysis");
  });

  test.each([
    "/cases/LX-2407?view=&panel=",
    "/cases/LX-2407?view=bogus&panel=nope",
    "/cases/LX-2407?view=__proto__&panel=PROJECTS",
    "/cases/LX-2407?view=review&panel=projects%20"
  ])("illegal query values do not crash and fall back to defaults (%s)", async (url) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(200, sessionEnvelope)));
    window.history.replaceState(null, "", url);
    const { container, unmount } = render(createElement(CaseShell, { decisionCaseId: "LX-2407" }));

    // Default workspace stays active; drawer stays closed; URL normalizes.
    expect(container.querySelector('section.view.is-active[data-view-panel="workspace"]')).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => expect(window.location.search).toContain("view=workspace"));
    expect(window.location.search).not.toContain("panel=projects");
    unmount();
  });

  test("hostile session payloads degrade to honest states without crashing", async () => {
    const user = userEvent.setup();

    // 401 with a garbage body is still the unauthenticated state.
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(401, "not-an-envelope")));
    const first = render(createElement(CaseShell, { decisionCaseId: "LX-2407" }));
    await user.click(screen.getByRole("button", { name: /决策项目 LX-2407/ }));
    let dialog = await screen.findByRole("dialog", { name: "项目与工作区" });
    expect(await within(dialog).findByText(/尚未登录/)).toBeVisible();
    expect(first.container.querySelectorAll("[data-workspace-entry]")).toHaveLength(0);
    first.unmount();

    // 500 → error state; malformed 200 envelope → error state; json() throw → error state.
    const hostileResponses = [
      jsonResponse(500, { ok: false }),
      jsonResponse(200, { ok: true, data: { memberships: "not-an-array" } }),
      jsonResponse(200, { ok: true, data: { memberships: [{ workspaceId: 42, workspaceName: null, role: {} }] } }),
      { ok: true, status: 200, json: async () => { throw new Error("bad json"); } } as unknown as Response
    ];
    for (const response of hostileResponses) {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
      const view = render(createElement(CaseShell, { decisionCaseId: "LX-2407" }));
      await user.click(screen.getByRole("button", { name: /决策项目 LX-2407/ }));
      dialog = await screen.findByRole("dialog", { name: "项目与工作区" });
      expect(await within(dialog).findByRole("alert")).toHaveTextContent("工作区读取失败。");
      expect(view.container.querySelectorAll("[data-workspace-entry]")).toHaveLength(0);
      view.unmount();
    }
  });

  test("a11y spot check: landmarks, dialog semantics and background inert while open", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(200, sessionEnvelope)));
    const user = userEvent.setup();
    const { container } = render(createElement(CaseShell, { decisionCaseId: "LX-2407" }));

    // Landmarks exist before the drawer opens.
    expect(container.querySelector("header.masthead")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "决策生命周期" })).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /决策项目 LX-2407/ }));
    const dialog = await screen.findByRole("dialog", { name: "项目与工作区" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAttribute("aria-labelledby", "project-drawer-title");

    // All three background landmarks are inert while the modal is open.
    expect(container.querySelector("header.masthead")).toHaveAttribute("inert");
    expect(container.querySelector("nav.decision-spine")).toHaveAttribute("inert");
    expect(container.querySelector("main.stage")).toHaveAttribute("inert");

    // Close restores the background to the tab order.
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(container.querySelector("header.masthead")).not.toHaveAttribute("inert");
    expect(container.querySelector("nav.decision-spine")).not.toHaveAttribute("inert");
    expect(container.querySelector("main.stage")).not.toHaveAttribute("inert");
  });

  test("a11y spot check: spine roving arrow keys stay on enabled steps and skip the reserved review slot", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(200, sessionEnvelope)));
    const user = userEvent.setup();
    render(createElement(CaseShell, { decisionCaseId: "LX-2407" }));

    const spine = screen.getByRole("navigation", { name: "决策生命周期" });
    const steps = within(spine).getAllByRole("button");
    // 5 workspaces + 1 disabled reserved review step.
    expect(steps).toHaveLength(6);
    const review = steps[5];
    expect(review).toBeDisabled();

    steps[0].focus();
    await user.keyboard("{ArrowRight}");
    expect(steps[1]).toHaveFocus();
    await user.keyboard("{End}");
    // End lands on the last ENABLED step, never the disabled review slot.
    expect(steps[4]).toHaveFocus();
    await user.keyboard("{ArrowRight}");
    expect(steps[0]).toHaveFocus();
    await user.keyboard("{ArrowLeft}");
    expect(steps[4]).toHaveFocus();
  });
});
