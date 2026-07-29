"use client";

import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { AccountGate } from "@/components/shell/AccountGate";
import { AccountSession } from "@/lib/shell/session";

// Invite-gated entry route. On success the user lands in their workspace: the
// `next` query param is honoured when it is a local path, otherwise the shell
// home anchored to the account's first workspace.

function isLocalPath(value: string | null): value is string {
  return typeof value === "string" && value.startsWith("/") && !value.startsWith("//");
}

function EnterInner() {
  const router = useRouter();
  const params = useSearchParams();
  const modeParam = params.get("mode");

  const goInside = (session: AccountSession) => {
    const next = params.get("next");
    if (isLocalPath(next)) {
      router.replace(next);
      return;
    }
    const workspaceId = session.workspaces[0]?.workspaceId;
    router.replace(workspaceId ? `/?ws=${encodeURIComponent(workspaceId)}` : "/");
  };

  return (
    <AccountGate
      onAuthenticated={goInside}
      initialMode={modeParam === "login" ? "login" : "register"}
    />
  );
}

export default function EnterPage() {
  return (
    <Suspense fallback={<main className="account-gate"><p>加载中…</p></main>}>
      <EnterInner />
    </Suspense>
  );
}
