/** @vitest-environment jsdom */

// QA adversarial supplement (flag flip): flipping the single source of truth
// `caseListRouteAvailable` to true must not crash the drawer — the workspace
// entries simply drop the gap note, per handoff §7.4 (no shell restructuring
// required when the case list route ships).

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, within } from "@testing-library/react";
import { createElement, type AnchorHTMLAttributes, type ImgHTMLAttributes, type ReactNode } from "react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { CaseShell } from "../components/shell/CaseShell";

vi.mock("@/lib/shell/projects", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/shell/projects")>();
  return { ...actual, caseListRouteAvailable: true };
});

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

describe("QA adversarial: caseListRouteAvailable flag flip", () => {
  test("flipping caseListRouteAvailable to true renders without crashing and drops the per-entry gap note", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => sessionEnvelope
      } as unknown as Response)
    );
    const user = userEvent.setup();
    render(createElement(CaseShell, { decisionCaseId: "LX-2407" }));

    await user.click(screen.getByRole("button", { name: /决策项目 LX-2407/ }));
    const dialog = await screen.findByRole("dialog", { name: "项目与工作区" });

    // Workspace entry still renders; the per-entry gap note is gone.
    const entry = (await within(dialog).findByText("Personal Workspace")).closest("[data-workspace-entry]");
    expect(entry).toBeInTheDocument();
    expect(within(entry as HTMLElement).queryByText(/Case 列表等待只读路由上线/)).not.toBeInTheDocument();

    // The drawer itself survives the flip: no crash, close still works.
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
