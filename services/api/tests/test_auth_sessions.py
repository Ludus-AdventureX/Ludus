"""Task 3 QA gate: session lifecycle (acceptance matrix rows A-02, A-04, A-05, A-06).

Skips until ``app.auth`` exists. JWT decoding is done without signature
verification on purpose: QA asserts the claim shape only and never needs the
signing secret.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

pytest.importorskip("app.auth", reason="Task 3 auth implementation not delivered yet")

from sqlalchemy import select, update

from app.models import User, UserSession, WorkspaceMembership
from app.types import WorkspaceMembershipStatus

from tests.conftest import (
    csrf_headers,
    execute_committed,
    fetch_committed,
    qa_client,
    register_user,
)

SESSION_COOKIE = "decision_lab_session"


def _jwt_claims(token: str) -> dict:
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


async def test_jwt_contains_only_minimal_claims() -> None:
    """A-02: JWT payload is exactly {sub, session_id, iat, exp}."""

    async with qa_client() as client:
        await register_user(client)
        token = client.cookies.get(SESSION_COOKIE)
    assert token, "register must set the session cookie"
    claims = _jwt_claims(token)
    assert set(claims) == {"sub", "session_id", "iat", "exp"}
    for forbidden in ("role", "workspace_id", "workspaceId", "capabilities", "email"):
        assert forbidden not in claims


async def test_logout_revokes_session_and_old_token_fails() -> None:
    """A-04: logout sets revoked_at first; the old JWT fails before its exp."""

    async with qa_client() as client:
        email, _ = await register_user(client)
        token = client.cookies.get(SESSION_COOKIE)
        assert token

        headers = await csrf_headers(client)
        logout = await client.post("/api/auth/logout", headers=headers)
        assert logout.status_code == 200

        client.cookies.set(SESSION_COOKIE, token)
        replay = await client.get("/api/auth/session")
        assert replay.status_code == 401
        assert replay.json()["error"]["code"] == "SESSION_REVOKED_OR_EXPIRED"

    session_id = UUID(str(_jwt_claims(token)["session_id"]))
    rows = await fetch_committed(
        select(UserSession.revoked_at).where(UserSession.id == session_id)
    )
    assert rows and rows[0][0] is not None, "logout must persist revoked_at"


async def test_expired_session_is_rejected_before_revocation() -> None:
    """A-05: an expired-but-unrevoked session fails with the uniform 401."""

    async with qa_client() as client:
        await register_user(client)
        token = client.cookies.get(SESSION_COOKIE)
        session_id = UUID(str(_jwt_claims(token)["session_id"]))

        await execute_committed(
            update(UserSession)
            .where(UserSession.id == session_id)
            .values(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
        )

        replay = await client.get("/api/auth/session")
        assert replay.status_code == 401
        assert replay.json()["error"]["code"] == "SESSION_REVOKED_OR_EXPIRED"


async def test_token_version_bump_invalidates_live_session() -> None:
    """A-05: bumping token_version must reject outstanding tokens.

    Formerly the QA-TASK03-002 xfail; promoted to a formal green regression
    when the auth security hardening lane shipped per-request tokenVersion
    validation (commit 60ef51c, combined candidate 609a780).
    """

    async with qa_client() as client:
        await register_user(client)
        token = client.cookies.get(SESSION_COOKIE)
        session_id = UUID(str(_jwt_claims(token)["session_id"]))

        await execute_committed(
            update(UserSession)
            .where(UserSession.id == session_id)
            .values(token_version=UserSession.token_version + 1)
        )

        replay = await client.get("/api/auth/session")
        assert replay.status_code == 401


async def test_workspace_access_requires_live_membership() -> None:
    """A-06: authorization re-reads membership per request; JWT alone fails."""

    async with qa_client() as client:
        email, data = await register_user(client)
        memberships = data["memberships"]
        assert memberships, "registration must create the first workspace membership"
        workspace_id = memberships[0]["workspaceId"]

        allowed = await client.get(f"/api/workspaces/{workspace_id}/qa-tenancy-probe")
        assert allowed.status_code == 200

        user_rows = await fetch_committed(select(User.id).where(User.email == email))
        user_id = user_rows[0][0]
        await execute_committed(
            update(WorkspaceMembership)
            .where(WorkspaceMembership.user_id == user_id)
            .values(status=WorkspaceMembershipStatus.REVOKED)
        )

        denied = await client.get(f"/api/workspaces/{workspace_id}/qa-tenancy-probe")
        assert denied.status_code == 404, "revoked membership must yield uniform 404"
        assert denied.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"


async def test_disabled_user_cannot_use_live_session() -> None:
    """A-06 support: disabling the user invalidates an otherwise valid session."""

    from app.types import UserStatus

    async with qa_client() as client:
        email, _ = await register_user(client)
        token = client.cookies.get(SESSION_COOKIE)
        assert token

        await execute_committed(
            update(User).where(User.email == email).values(status=UserStatus.DISABLED)
        )

        replay = await client.get("/api/auth/session")
        assert replay.status_code == 401
        assert replay.json()["error"]["code"] == "SESSION_REVOKED_OR_EXPIRED"
