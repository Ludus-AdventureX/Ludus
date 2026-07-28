"use client";

import { useCallback, useEffect, useState } from "react";

import {
  InviteError,
  createInvite,
  listInvites,
  revokeInvite,
  type InviteView,
} from "@/lib/shell/invites";

// OWNER-only invite management: create a join link (the token is shown ONCE),
// list active invites, revoke. Non-owners get a 403/404 from the backend and
// the panel self-hides - membership boundaries are enforced server-side, the
// UI merely reflects them.

export type InvitePanelProps = {
  workspaceId?: string | null;
};

export function InvitePanel({ workspaceId = null }: InvitePanelProps) {
  const [open, setOpen] = useState(false);
  const [invites, setInvites] = useState<InviteView[] | null>(null);
  const [fresh, setFresh] = useState<InviteView | null>(null);
  const [grantSign, setGrantSign] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [allowed, setAllowed] = useState(true);

  const refresh = useCallback(async () => {
    if (!workspaceId) return;
    try {
      setInvites(await listInvites(workspaceId));
      setAllowed(true);
    } catch (err) {
      if (err instanceof InviteError && (err.status === 403 || err.status === 404)) {
        setAllowed(false); // not the owner (or not a member) - hide the surface
      } else {
        setError(err instanceof InviteError ? err.message : "邀请列表读取失败。");
      }
    }
  }, [workspaceId]);

  useEffect(() => {
    if (open) void refresh();
  }, [open, refresh]);

  const create = useCallback(async () => {
    if (!workspaceId || busy) return;
    setBusy(true);
    setError("");
    setCopied(false);
    try {
      const invite = await createInvite(workspaceId, { grantSign });
      setFresh(invite);
      await refresh();
    } catch (err) {
      setError(err instanceof InviteError ? err.message : "创建邀请失败。");
    } finally {
      setBusy(false);
    }
  }, [workspaceId, busy, grantSign, refresh]);

  const copy = useCallback(async () => {
    if (!fresh?.joinUrl) return;
    const absolute = `${window.location.origin}${fresh.joinUrl}`;
    try {
      await navigator.clipboard.writeText(absolute);
      setCopied(true);
    } catch {
      setError("复制失败——请手动选择链接复制。");
    }
  }, [fresh]);

  if (!workspaceId || !allowed) return null;

  return (
    <div className="invite-panel" data-invite-panel>
      <button
        type="button"
        className="secondary-action small"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span>邀请协作者</span>
      </button>

      {open && (
        <div className="invite-pop" role="dialog" aria-label="邀请协作者">
          <p className="phase-slot-note">
            受邀者以协作者身份进入本工作区：可写札记、确认档案、发起分析、读报告、玩沙盘。
          </p>
          <label className="invite-sign-toggle">
            <input
              type="checkbox"
              checked={grantSign}
              onChange={(e) => setGrantSign(e.target.checked)}
            />
            <span className="invite-sign-warn">
              同时授予签署权（该协作者将能代表工作区签署决定——请慎重）
            </span>
          </label>
          <button type="button" className="primary-action small" disabled={busy} onClick={() => void create()}>
            <span>{busy ? "创建中…" : "生成邀请链接"}</span>
          </button>

          {fresh?.joinUrl && (
            <div className="invite-fresh" data-invite-token-shown>
              <p>链接只显示这一次，请立即复制发给协作者：</p>
              <code>{fresh.joinUrl}</code>
              <button type="button" className="secondary-action small" onClick={() => void copy()}>
                <span>{copied ? "已复制 ✓" : "复制完整链接"}</span>
              </button>
              <p className="phase-slot-note">
                有效期 72 小时 · 最多 {fresh.maxUses} 人使用 · 权限：{fresh.capabilities.join(" / ")}
              </p>
            </div>
          )}

          {error && <p role="alert">{error}</p>}

          {invites && invites.length > 0 && (
            <ul className="invite-list">
              {invites.map((invite) => (
                <li key={invite.inviteId} data-invite-revoked={invite.revokedAt != null}>
                  <span>
                    {invite.usedCount}/{invite.maxUses} 已用 ·{" "}
                    {invite.revokedAt ? "已撤销" : `到期 ${invite.expiresAt.slice(0, 10)}`}
                  </span>
                  {!invite.revokedAt && (
                    <button
                      type="button"
                      onClick={() =>
                        void revokeInvite(workspaceId, invite.inviteId).then(refresh)
                      }
                    >
                      撤销
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
