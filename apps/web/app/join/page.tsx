"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { InviteError, joinWithInvite } from "@/lib/shell/invites";

// Invite landing: ?code=... -> ensure a guest session -> redeem -> enter the
// shared workspace (?ws= anchors every panel). Dead invites get ONE honest
// message by design - the backend refuses to distinguish them.

function JoinInner() {
  const params = useSearchParams();
  const router = useRouter();
  const [phase, setPhase] = useState<"working" | "error" | "missing">("working");
  const [message, setMessage] = useState("正在验证邀请并进入工作区…");

  useEffect(() => {
    const code = params.get("code");
    if (!code) {
      setPhase("missing");
      return;
    }
    let cancelled = false;
    void joinWithInvite(code)
      .then(({ workspaceId }) => {
        if (!cancelled) router.replace(`/?ws=${encodeURIComponent(workspaceId)}`);
      })
      .catch((err) => {
        if (cancelled) return;
        setPhase("error");
        setMessage(
          err instanceof InviteError && err.code === "GUEST_UNAVAILABLE"
            ? err.message
            : "邀请无效或已过期，请向邀请人索取新的链接。",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [params, router]);

  return (
    <main className="join-page" data-join-phase={phase}>
      <section>
        <span className="eyebrow">LUDUS · 协作邀请</span>
        {phase === "working" && <h1>正在进入共享工作区…</h1>}
        {phase === "missing" && <h1>链接不完整——缺少邀请码</h1>}
        {phase === "error" && <h1>无法加入</h1>}
        <p role="status">{phase === "missing" ? "请使用邀请人发给你的完整链接。" : message}</p>
      </section>
    </main>
  );
}

export default function JoinPage() {
  return (
    <Suspense fallback={<main className="join-page"><p>加载中…</p></main>}>
      <JoinInner />
    </Suspense>
  );
}
