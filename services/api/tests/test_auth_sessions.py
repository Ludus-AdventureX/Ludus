"""Task 3 QA gate: session lifecycle (acceptance matrix rows A-02, A-04, A-05, A-06).

Skips until ``app.auth`` exists. JWT decoding is done without signature
verification on purpose: QA asserts the claim shape only and never needs the
signing secret.
"""

from __future__ import annotations

import base64
import json

import pytest

pytest.importorskip("app.auth", reason="Task 3 auth implementation not delivered yet")

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.main import app
from app.models import User, UserSession

REGISTER_PATH = "/api/auth/register"
LOGIN_PATH = "/api/auth/login"
LOGOUT_PATH = "/api/auth/logout"
CSRF_PATH = "/api/auth/csrf"
ME_PATH = "/api/auth/me"

QA_PASSWORD = "correct horse battery staple"


def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Origin": "http://testserver"},
    )


async def _csrf_headers(client: httpx.AsyncClient) -> dict[str, str]:
    response = await client.get(CSRF_PATH)
    assert response.status_code == 200
    token = response.json().get("data", {}).get("token") or response.json().get("token")
    assert token
    return {"X-CSRF-Token": token}


async def _register_and_login(client: httpx.AsyncClient, email: str) -> str:
    """Register + login; return the raw session cookie value (JWT)."""

    headers = await _csrf_headers(client)
    register = await client.post(
        REGISTER_PATH, json={"email": email, "password": QA_PASSWORD}, headers=headers
    )
    assert register.status_code in (200, 201)
    login = await client.post(
        LOGIN_PATH, json={"email": email, "password": QA_PASSWORD}, headers=headers
    )
    assert login.status_code == 200
    cookie = client.cookies.get("decision_lab_session")
    assert cookie, "login must set the decision_lab_session cookie"
    return cookie


def _jwt_claims(token: str) -> dict:
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


async def test_jwt_contains_only_minimal_claims() -> None:
    """A-02: JWT payload is exactly {sub, session_id, iat, exp}."""

    async with _client() as client:
        token = await _register_and_login(client, "qa-claims-a02@example.test")
    claims = _jwt_claims(token)
    assert set(claims) == {"sub", "session_id", "iat", "exp"}
    for forbidden in ("role", "workspace_id", "workspaceId", "capabilities", "email"):
        assert forbidden not in claims


async def test_logout_revokes_session_and_old_token_fails(
    db_connection: AsyncConnection,
) -> None:
    """A-04: logout sets revoked_at; the old JWT fails before its exp."""

    email = "qa-logout-a04@example.test"
    async with _client() as client:
        token = await _register_and_login(client, email)
        headers = await _csrf_headers(client)
        logout = await client.post(LOGOUT_PATH, headers=headers)
        assert logout.status_code in (200, 204)

        # replay the pre-logout cookie explicitly
        replay = await client.get(ME_PATH, cookies={"decision_lab_session": token})
        assert replay.status_code == 401

    user_id = (
        await db_connection.execute(select(User.id).where(User.email == email))
    ).scalar_one()
    revoked = (
        await db_connection.execute(
            select(UserSession.revoked_at).where(UserSession.user_id == user_id)
        )
    ).scalars().all()
    assert revoked, "a UserSession row must exist for the login"
    assert any(value is not None for value in revoked), "logout must set revoked_at"


async def test_token_version_bump_invalidates_live_session(
    db_connection: AsyncConnection,
) -> None:
    """A-05: bumping token_version server-side rejects an otherwise valid JWT."""

    email = "qa-version-a05@example.test"
    async with _client() as client:
        token = await _register_and_login(client, email)
        claims = _jwt_claims(token)

        user_id = (
            await db_connection.execute(select(User.id).where(User.email == email))
        ).scalar_one()
        await db_connection.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id)
            .values(token_version=UserSession.token_version + 1)
        )
        await db_connection.commit()

        replay = await client.get(ME_PATH, cookies={"decision_lab_session": token})
        assert replay.status_code == 401, (
            f"session {claims.get('session_id')} must be rejected after version bump"
        )


async def test_workspace_access_requires_live_membership(
    db_connection: AsyncConnection,
) -> None:
    """A-06: authorization re-reads membership per request; JWT alone is not enough."""

    from app.models import WorkspaceMembership
    from app.types import WorkspaceMembershipStatus

    email = "qa-membership-a06@example.test"
    async with _client() as client:
        headers = await _csrf_headers(client)
        register = await client.post(
            REGISTER_PATH, json={"email": email, "password": QA_PASSWORD}, headers=headers
        )
        assert register.status_code in (200, 201)
        login = await client.post(
            LOGIN_PATH, json={"email": email, "password": QA_PASSWORD}, headers=headers
        )
        assert login.status_code == 200

        workspaces = await client.get("/api/workspaces")
        assert workspaces.status_code == 200
        payload = workspaces.json()
        items = payload.get("data", payload)
        assert items, "registration flow must yield at least one workspace"
        workspace_id = items[0].get("id") or items[0].get("workspaceId")

        allowed = await client.get(f"/api/workspaces/{workspace_id}")
        assert allowed.status_code == 200

        user_id = (
            await db_connection.execute(select(User.id).where(User.email == email))
        ).scalar_one()
        await db_connection.execute(
            update(WorkspaceMembership)
            .where(WorkspaceMembership.user_id == user_id)
            .values(status=WorkspaceMembershipStatus.REVOKED)
        )
        await db_connection.commit()

        denied = await client.get(f"/api/workspaces/{workspace_id}")
        assert denied.status_code == 404, "revoked membership must yield uniform 404"
