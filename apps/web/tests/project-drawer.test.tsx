/** @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { createElement, type AnchorHTMLAttributes, type ImgHTMLAttributes, type ReactNode } from "react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { CaseShell } from "../components/shell/CaseShell";
import { DecisionHealthBar, decisionHealthSegments } from "../components/shell/DecisionHealthBar";
import { caseListRouteAvailable } from "../lib/shell/projects";
import { shellSlotContract } from "../lib/shell/slotContracts";

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
      { workspaceId: "ws-1", workspaceName: "Personal Workspace", role: "owner", capabilities: [], status: "active" },
      { workspaceId: "ws-2", workspaceName: "Hardtech Lab", role: "member", capabilities: [], status: "active" }
    ]
  }
};

async function openDrawer(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: /决策项目 LX-2407/ }));
  return await screen.findByRole("dialog", { name: "项目与工作区" });
}

describe("ProjectDrawer + Session B shell completion (Task 11 Phase 0)", () => {
  test("opens from the masthead trigger, lists real workspaces and discloses the case-list gap", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, sessionEnvelope));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    const { container } = render(createElement(CaseShell, { decisionCaseId: "LX-2407" }));

    const dialog = await openDrawer(user);

    // Only the shipped Task 3 read-only route is consumed.
    expect(fetchMock).toHaveBeenCalledWith("/api/auth/session", expect.objectContaining({ method: "GET" }));
    expect(await within(dialog).findByText("Personal Workspace")).toBeVisible();
    expect(within(dialog).getByText("Hardtech Lab")).toBeVisible();
    expect(within(dialog).getByText("角色 owner")).toBeVisible();

    // The canonical case list route (GET /cases) shipped; the drawer consumes
    // it. With an empty list it renders no fabricated case entries and the
    // honest new-project link stays.
    expect(caseListRouteAvailable).toBe(true);
    expect(within(dialog).queryByText(/Case 列表只读路由尚未上线/)).not.toBeInTheDocument();
    const emptyWorkbench = within(dialog).getByRole("link", { name: /新建项目/ });
    expect(emptyWorkbench).toHaveAttribute("href", "/");

    // Background is inert while the modal drawer is open; URL records the panel.
    expect(container.querySelector("header.masthead")).toHaveAttribute("inert");
    expect(container.querySelector("main.stage")).toHaveAttribute("inert");
    await waitFor(() => expect(window.location.search).toContain("panel=projects"));
  });

  test("renders an honest unauthenticated state on 401 without fabricated entries", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(401, { ok: false, error: { code: "AUTH_SESSION_REJECTED" } })));
    const user = userEvent.setup();
    const { container } = render(createElement(CaseShell, { decisionCaseId: "LX-2407" }));

    const dialog = await openDrawer(user);

    expect(await within(dialog).findByText(/尚未登录/)).toBeVisible();
    expect(container.querySelectorAll("[data-workspace-entry]")).toHaveLength(0);
  });

  test("renders a retryable error state that recovers on retry", async () => {
    // The drawer's own session read fails once, then recovers. URL-based
    // dispatch keeps the shell's other session consumers (AccountEntry) off
    // the reject, and the shipped case list route answers with an empty list.
    let sessionReads = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/auth/session") {
        sessionReads += 1;
        if (sessionReads === 2) throw new Error("network down");
        return jsonResponse(200, sessionEnvelope);
      }
      if (url.endsWith("/cases")) return jsonResponse(200, { ok: true, data: { items: [] } });
      return jsonResponse(200, sessionEnvelope);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(createElement(CaseShell, { decisionCaseId: "LX-2407" }));

    const dialog = await openDrawer(user);
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("工作区读取失败。");

    await user.click(within(dialog).getByRole("button", { name: "重试" }));
    expect(await within(dialog).findByText("Personal Workspace")).toBeVisible();
    expect(fetchMock).toHaveBeenCalledTimes(4); // AccountEntry 1 + session 2 + retry 3 + cases 4
  });

  test("traps focus, closes on Escape and returns focus to the trigger", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(200, sessionEnvelope)));
    const user = userEvent.setup();
    render(createElement(CaseShell, { decisionCaseId: "LX-2407" }));
    const trigger = screen.getByRole("button", { name: /决策项目 LX-2407/ });

    const dialog = await openDrawer(user);
    await within(dialog).findByText("Personal Workspace");
    await waitFor(() => expect(dialog.parentElement).toContainElement(document.activeElement as HTMLElement));

    // Tab from the last focusable wraps back into the drawer.
    const stayButton = within(dialog).getByRole("button", { name: "留在当前项目" });
    stayButton.focus();
    await user.tab();
    expect(dialog.parentElement).toContainElement(document.activeElement as HTMLElement);

    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(trigger).toHaveFocus());
    await waitFor(() => expect(window.location.search).not.toContain("panel=projects"));
  });

  test("restores drawer and workspace state after a refresh", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(200, sessionEnvelope)));
    window.history.replaceState(null, "", "/cases/LX-2407?view=sandbox&panel=projects");
    const user = userEvent.setup();
    const { container } = render(createElement(CaseShell, { decisionCaseId: "LX-2407" }));

    // Drawer reopens and the sandbox workspace stays active after refresh.
    const dialog = await screen.findByRole("dialog", { name: "项目与工作区" });
    expect(await within(dialog).findByText("Personal Workspace")).toBeVisible();
    expect(container.querySelector('section.view.is-active[data-view-panel="sandbox"]')).toBeInTheDocument();

    await user.keyboard("{Escape}");
    await waitFor(() => expect(window.location.search).not.toContain("panel=projects"));
    expect(window.location.search).toContain("view=sandbox");
  });

  test("mobile case trigger opens the same drawer for small viewports", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(200, sessionEnvelope)));
    const user = userEvent.setup();
    render(createElement(CaseShell, { decisionCaseId: "LX-2407" }));

    const mobileTrigger = screen.getByRole("button", { name: "打开项目抽屉" });
    expect(mobileTrigger).toHaveClass("mobile-case-trigger");
    await user.click(mobileTrigger);
    expect(await screen.findByRole("dialog", { name: "项目与工作区" })).toBeVisible();

    await user.keyboard("{Escape}");
    await waitFor(() => expect(mobileTrigger).toHaveFocus());
  });

  test("decision health bar renders five pending segments without a total percentage", async () => {
    const { container } = render(createElement(CaseShell, { decisionCaseId: "LX-2407" }));

    const healthBar = container.querySelector('[data-phase-slot="decision-health-bar"]');
    expect(healthBar).toBeInTheDocument();
    // Without mocked API data every segment stays an honest disabled
    // placeholder (loading or error) - never a fabricated verdict.
    const segments = within(healthBar as HTMLElement).getAllByRole("button");
    expect(segments).toHaveLength(5);
    for (const { label } of decisionHealthSegments) {
      const segment = within(healthBar as HTMLElement).getByRole("button", { name: new RegExp(label) });
      expect(segment).toBeDisabled();
      expect(segment.textContent).not.toMatch(/\d+\s*%/);
    }
    // No total confidence percentage anywhere in the skeleton.
    expect(healthBar?.textContent).not.toMatch(/\d+\s*%/);
  });

  test("health bar segments with live state render as links to their owning view", () => {
    render(
      createElement(DecisionHealthBar, {
        segments: [
          {
            id: "evidence", coordinate: "E", label: "证据",
            href: "/cases/LX-2407?ws=ws-1&view=analysis", status: "ok", summary: "已收录 3 条证据",
          },
          {
            id: "causal-chain", coordinate: "C", label: "因果链",
            href: null, status: "loading", summary: "读取中…",
          },
        ],
      }),
    );

    const link = screen.getByRole("link", { name: /证据/ });
    expect(link).toHaveAttribute("href", "/cases/LX-2407?ws=ws-1&view=analysis");
    expect(link).toHaveTextContent("已收录 3 条证据");

    const pending = screen.getByRole("button", { name: /因果链/ });
    expect(pending).toBeDisabled();
    expect(pending).toHaveTextContent("读取中…");
  });

  test("slot contract covers every frozen phase slot and marks Session B fills", () => {
    const frozenSlotNames = [
      "analysis-charter-form",
      "analysis-progress",
      "quality-gate-panel",
      "evidence-drawer-trigger",
      "decision-health-bar",
      "decision-signoff",
      "review-dialog-trigger",
      "project-drawer",
      // Task 13 authorized shell increment: sandbox workspace mount slot.
      "sandbox-workspace"
    ];
    expect(Object.keys(shellSlotContract).sort()).toEqual([...frozenSlotNames].sort());
    expect(shellSlotContract["project-drawer"].status).toBe("filled");
    expect(shellSlotContract["decision-health-bar"].status).toBe("filled");
    expect(shellSlotContract["sandbox-workspace"].status).toBe("filled");
    for (const name of ["analysis-charter-form", "analysis-progress", "quality-gate-panel", "evidence-drawer-trigger", "decision-signoff", "review-dialog-trigger"] as const) {
      expect(shellSlotContract[name].status).toBe("reserved");
    }
  });
});
