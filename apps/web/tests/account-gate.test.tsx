/** @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";

import { afterEach, describe, expect, test, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Mock the session client so the gate is tested without the network.
const { registerMock, loginMock } = vi.hoisted(() => ({
  registerMock: vi.fn(),
  loginMock: vi.fn()
}));

vi.mock("@/lib/shell/session", () => ({
  SessionError: class SessionError extends Error {
    code: string;
    status: number;
    step: string;
    constructor(code: string, message: string, status: number, step: string) {
      super(message);
      this.code = code;
      this.status = status;
      this.step = step;
    }
  },
  registerAccount: registerMock,
  loginAccount: loginMock
}));

import { AccountGate } from "../components/shell/AccountGate";
import { SessionError } from "@/lib/shell/session";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AccountGate", () => {
  test("register mode submits email + password + invite code and reports the session", async () => {
    const onAuthenticated = vi.fn();
    registerMock.mockResolvedValue({ authenticated: true, email: "a@b.co", workspaces: [] });
    const user = userEvent.setup();
    render(<AccountGate onAuthenticated={onAuthenticated} />);

    await user.type(screen.getByLabelText("邮箱"), "invited@example.test");
    await user.type(screen.getByLabelText("密码"), "hunter2hunter2");
    await user.type(screen.getByLabelText("邀请码"), "code-9");
    await user.click(screen.getByRole("button", { name: "创建账号并进入" }));

    await waitFor(() => expect(onAuthenticated).toHaveBeenCalledTimes(1));
    expect(registerMock).toHaveBeenCalledWith({
      email: "invited@example.test",
      password: "hunter2hunter2",
      inviteCode: "code-9"
    });
  });

  test("shows the server's uniform invite refusal verbatim and does not advance", async () => {
    const onAuthenticated = vi.fn();
    registerMock.mockRejectedValue(
      new SessionError(
        "SIGNUP_INVITE_REQUIRED",
        "Registration requires a valid invite code.",
        403,
        "register"
      )
    );
    const user = userEvent.setup();
    render(<AccountGate onAuthenticated={onAuthenticated} />);

    await user.type(screen.getByLabelText("邮箱"), "invited@example.test");
    await user.type(screen.getByLabelText("密码"), "hunter2hunter2");
    await user.type(screen.getByLabelText("邀请码"), "wrong");
    await user.click(screen.getByRole("button", { name: "创建账号并进入" }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Registration requires a valid invite code."
      )
    );
    expect(onAuthenticated).not.toHaveBeenCalled();
  });

  test("login mode has no invite field and calls loginAccount", async () => {
    const onAuthenticated = vi.fn();
    loginMock.mockResolvedValue({ authenticated: true, email: "a@b.co", workspaces: [] });
    const user = userEvent.setup();
    render(<AccountGate onAuthenticated={onAuthenticated} initialMode="login" />);

    expect(screen.queryByLabelText("邀请码")).toBeNull();
    await user.type(screen.getByLabelText("邮箱"), "invited@example.test");
    await user.type(screen.getByLabelText("密码"), "hunter2hunter2");
    await user.click(screen.getByRole("button", { name: "登录并进入" }));

    await waitFor(() => expect(loginMock).toHaveBeenCalledTimes(1));
    expect(loginMock).toHaveBeenCalledWith({
      email: "invited@example.test",
      password: "hunter2hunter2"
    });
  });

  test("client-side guard: a missing invite code is refused before any request", async () => {
    const onAuthenticated = vi.fn();
    const user = userEvent.setup();
    render(<AccountGate onAuthenticated={onAuthenticated} />);

    await user.type(screen.getByLabelText("邮箱"), "invited@example.test");
    await user.type(screen.getByLabelText("密码"), "hunter2hunter2");
    await user.click(screen.getByRole("button", { name: "创建账号并进入" }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("请输入邀请码。"));
    expect(registerMock).not.toHaveBeenCalled();
  });
});
