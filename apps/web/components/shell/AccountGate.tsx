"use client";

import { FormEvent, useState } from "react";

import {
  AccountSession,
  loginAccount,
  registerAccount,
  SessionError,
} from "@/lib/shell/session";

// Invite-gated entry for the alpha. Two modes over the same shipped auth
// surface: register (needs an invite code) and login. On success the caller
// decides where to go (the /enter route sends the user into the workspace).
//
// The invite gate answers ONE uniform 403 for "no code", "wrong code" and
// "registration is closed here", so this form must not pretend to know which
// it was; it shows the server's own message verbatim.

const copy = {
  eyebrow: "LUDUS · 受邀进入",
  registerTitle: "使用邀请码创建账号",
  loginTitle: "登录你的账号",
  registerLead:
    "内测阶段仅对受邀用户开放。请使用邀请人给你的邀请码创建账号；账号会绑定一个属于你的工作区。",
  loginLead: "已有账号？直接登录，回到你自己的工作区。",
  email: "邮箱",
  password: "密码",
  inviteCode: "邀请码",
  passwordHint: "至少 8 位",
  register: "创建账号并进入",
  login: "登录并进入",
  working: "正在处理…",
  toLogin: "已有账号，去登录",
  toRegister: "有邀请码，去注册",
  genericError: "操作未成功，请稍后重试。",
  emailInvalid: "请输入有效的邮箱地址。",
  passwordShort: "密码至少 8 位。",
  inviteMissing: "请输入邀请码。",
} as const;

type Mode = "register" | "login";

export function AccountGate({
  onAuthenticated,
  initialMode = "register",
}: {
  onAuthenticated: (session: AccountSession) => void;
  initialMode?: Mode;
}) {
  const [mode, setMode] = useState<Mode>(initialMode);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const switchMode = (next: Mode) => {
    setMode(next);
    setNotice("");
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy) return;
    const trimmedEmail = email.trim();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(trimmedEmail)) {
      setNotice(copy.emailInvalid);
      return;
    }
    if (password.length < 8) {
      setNotice(copy.passwordShort);
      return;
    }
    if (mode === "register" && !inviteCode.trim()) {
      setNotice(copy.inviteMissing);
      return;
    }
    setBusy(true);
    setNotice("");
    try {
      const session =
        mode === "register"
          ? await registerAccount({
              email: trimmedEmail,
              password,
              inviteCode: inviteCode.trim(),
            })
          : await loginAccount({ email: trimmedEmail, password });
      onAuthenticated(session);
    } catch (error) {
      // Surface the server's own message (invite gate 403, invalid credentials
      // 401) rather than inventing one.
      setNotice(error instanceof SessionError ? error.message : copy.genericError);
    } finally {
      setBusy(false);
    }
  };

  const isRegister = mode === "register";

  return (
    <main className="account-gate" data-account-mode={mode}>
      <section className="account-gate-card">
        <span className="eyebrow">{copy.eyebrow}</span>
        <h1>{isRegister ? copy.registerTitle : copy.loginTitle}</h1>
        <p className="account-gate-lead">{isRegister ? copy.registerLead : copy.loginLead}</p>

        <form className="account-gate-form" onSubmit={submit} noValidate>
          <label htmlFor="accountEmail">{copy.email}</label>
          <input
            id="accountEmail"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => { setEmail(event.target.value); setNotice(""); }}
            disabled={busy}
            required
          />

          <label htmlFor="accountPassword">{copy.password}</label>
          <input
            id="accountPassword"
            type="password"
            autoComplete={isRegister ? "new-password" : "current-password"}
            value={password}
            onChange={(event) => { setPassword(event.target.value); setNotice(""); }}
            disabled={busy}
            required
          />
          {isRegister && <small className="account-gate-hint">{copy.passwordHint}</small>}

          {isRegister && (
            <>
              <label htmlFor="accountInvite">{copy.inviteCode}</label>
              <input
                id="accountInvite"
                type="text"
                inputMode="text"
                autoComplete="one-time-code"
                value={inviteCode}
                onChange={(event) => { setInviteCode(event.target.value); setNotice(""); }}
                disabled={busy}
                required
              />
            </>
          )}

          <button type="submit" className="primary-action" disabled={busy}>
            {busy ? copy.working : isRegister ? copy.register : copy.login}
          </button>
          {notice && <p className="account-gate-notice" role="alert">{notice}</p>}
        </form>

        <button
          type="button"
          className="account-gate-switch"
          onClick={() => switchMode(isRegister ? "login" : "register")}
          disabled={busy}
        >
          {isRegister ? copy.toLogin : copy.toRegister}
        </button>
      </section>
    </main>
  );
}
