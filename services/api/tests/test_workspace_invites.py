"""Multi-guest invite lane QA (hard-gate standard for an auth surface).

Matrix: OWNER-only management (create/list/revoke), CSRF enforcement, the
anti-enumeration contract (unknown/expired/revoked/exhausted tokens are
byte-identical 404s), idempotent re-redemption, capability projection for the
invitee (member CAN read/contribute, CANNOT sign, CANNOT manage invites), and
cross-workspace isolation staying intact.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from uuid import uuid4

import httpx
from sqlalchemy import text

from tests.conftest import QA_ORIGIN, build_qa_app, csrf_headers, execute_committed

GUEST_FLAG = "ENABLE_GUEST_ALPHA"


@lru_cache(maxsize=1)
def _invite_app():
    """QA assembly + guest router (same lazy-router workaround as guest QA)."""

    from app.auth.guest import router as guest_router

    app = build_qa_app()
    app.include_router(guest_router)
    return app


def qa_client(client_ip: str | None = None) -> httpx.AsyncClient:
    # Distinct client IPs per session keep the fail-closed redeem limiter from
    # coupling unrelated test actors.
    address = client_ip or f"10.79.{uuid4().bytes[0]}.{uuid4().bytes[1]}"
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_invite_app(), client=(address, 51234)),
        base_url=QA_ORIGIN,
        headers={"Origin": QA_ORIGIN},
    )


async def _guest(client: httpx.AsyncClient) -> dict:
    headers = await csrf_headers(client)
    response = await client.post("/api/auth/guest", headers=headers)
    assert response.status_code in (200, 201), response.text
    return response.json()["data"]


async def _create_invite(client: httpx.AsyncClient, workspace_id: str, body: dict | None = None):
    headers = await csrf_headers(client)
    return await client.post(
        f"/api/workspaces/{workspace_id}/invites", json=body or {}, headers=headers
    )


async def _redeem(client: httpx.AsyncClient, token: str):
    headers = await csrf_headers(client)
    return await client.post("/api/auth/invites/redeem", json={"token": token}, headers=headers)


async def test_owner_creates_invite_and_member_joins_with_projected_capabilities(monkeypatch) -> None:
    monkeypatch.setenv(GUEST_FLAG, "true")
    async with qa_client() as owner, qa_client() as invitee:
        ws = (await _guest(owner))["workspaceId"]

        created = await _create_invite(owner, ws)
        assert created.status_code == 201, created.text
        data = created.json()["data"]
        assert data["capabilities"] == ["contribute", "review"]  # SIGN excluded by default
        token = data["token"]
        assert token and token not in str(data["inviteId"])

        await _guest(invitee)  # invitee needs their own session first
        redeemed = await _redeem(invitee, token)
        assert redeemed.status_code == 200, redeemed.text
        payload = redeemed.json()["data"]
        assert payload["workspaceId"] == ws
        assert payload["membership"] == "created"

        # The invitee can now read the shared workspace's cases...
        cases = await invitee.get(f"/api/workspaces/{ws}/cases")
        assert cases.status_code == 200, cases.text
        # ...but CANNOT manage invites (MEMBER, not OWNER)...
        forbidden = await _create_invite(invitee, ws)
        assert forbidden.status_code == 403
        # ...and CANNOT reach the SIGN-gated surface (nonce rotation probe).
        headers = await csrf_headers(invitee)
        sign_probe = await invitee.post(
            f"/api/workspaces/{ws}/signoff-requests/00000000-0000-4000-8000-000000000000/nonce-rotations",
            headers=headers,
        )
        assert sign_probe.status_code == 403, sign_probe.text

        # Re-redemption is idempotent and consumes no extra use.
        again = await _redeem(invitee, token)
        assert again.status_code == 200
        assert again.json()["data"]["membership"] == "existing"
        listing = await owner.get(f"/api/workspaces/{ws}/invites")
        item = listing.json()["data"]["items"][0]
        assert item["usedCount"] == 1


async def test_invite_management_is_owner_only_and_csrf_guarded(monkeypatch) -> None:
    monkeypatch.setenv(GUEST_FLAG, "true")
    async with qa_client() as owner, qa_client() as stranger:
        ws = (await _guest(owner))["workspaceId"]
        await _guest(stranger)

        # No CSRF header -> rejected before anything else.
        naked = await owner.post(f"/api/workspaces/{ws}/invites", json={})
        assert naked.status_code == 403

        # A non-member cannot even see the invite surface (uniform 404).
        headers = await csrf_headers(stranger)
        foreign = await stranger.post(f"/api/workspaces/{ws}/invites", json={}, headers=headers)
        assert foreign.status_code == 404

        # manage_connectors can never travel through an invite.
        bad = await _create_invite(owner, ws, {"capabilities": ["manage_connectors"]})
        assert bad.status_code == 422


async def test_all_dead_token_shapes_are_byte_identical_404s(monkeypatch) -> None:
    monkeypatch.setenv(GUEST_FLAG, "true")
    async with qa_client() as owner, qa_client() as visitor:
        ws = (await _guest(owner))["workspaceId"]
        await _guest(visitor)

        # 1. fabricated token
        fake = await _redeem(visitor, "definitely-not-a-real-token")
        # 2. revoked token
        created = await _create_invite(owner, ws)
        revoked_token = created.json()["data"]["token"]
        invite_id = created.json()["data"]["inviteId"]
        headers = await csrf_headers(owner)
        await owner.post(f"/api/workspaces/{ws}/invites/{invite_id}/revoke", headers=headers)
        revoked = await _redeem(visitor, revoked_token)
        # 3. expired token (force expiry in the DB)
        created2 = await _create_invite(owner, ws)
        expired_token = created2.json()["data"]["token"]
        await execute_committed(
            text("UPDATE workspace_invites SET expires_at = :past WHERE id = CAST(:iid AS uuid)").bindparams(
                past=datetime.now(timezone.utc) - timedelta(hours=1),
                iid=created2.json()["data"]["inviteId"],
            )
        )
        expired = await _redeem(visitor, expired_token)
        # 4. exhausted token (max_uses reached)
        created3 = await _create_invite(owner, ws, {"maxUses": 1})
        exhausted_token = created3.json()["data"]["token"]
        async with qa_client() as consumer:
            await _guest(consumer)
            first = await _redeem(consumer, exhausted_token)
            assert first.status_code == 200
        exhausted = await _redeem(visitor, exhausted_token)

        bodies = {r.status_code for r in (fake, revoked, expired, exhausted)}
        assert bodies == {404}
        texts = {r.text for r in (fake, revoked, expired, exhausted)}
        assert len(texts) == 1, "dead-token responses must be byte-identical (anti-enumeration)"


async def test_active_invite_limit_is_enforced(monkeypatch) -> None:
    monkeypatch.setenv(GUEST_FLAG, "true")
    async with qa_client() as owner:
        ws = (await _guest(owner))["workspaceId"]
        for _ in range(10):
            created = await _create_invite(owner, ws)
            assert created.status_code == 201
        over = await _create_invite(owner, ws)
        assert over.status_code == 409
        assert over.json()["error"]["code"] == "INVITE_LIMIT"
