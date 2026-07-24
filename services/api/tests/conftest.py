"""Shared QA fixtures for the Task 3 auth/workspace gate tests.

Two layers:

- DB-layer fixtures (``db_connection``, ``two_tenants``) rely only on the
  frozen canonical models from Task 19A and run on the baseline.
- The QA app assembly (``build_qa_app``) mounts the Task 3 routers exactly as
  the accompanying CONTRACT_CHANGE_REQUEST instructs the Contract Lead to do
  in ``app.main``. It is imported lazily so this conftest still loads on
  baselines where ``app.auth`` does not exist yet.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from uuid import UUID, uuid4

import httpx
import pytest_asyncio
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.db import get_database_url
from app.models import (
    User,
    UserSession,
    Workspace,
    WorkspaceMembership,
)
from app.types import (
    UserStatus,
    WorkspaceCapability,
    WorkspaceMembershipStatus,
    WorkspaceRole,
    WorkspaceStatus,
)

QA_PASSWORD = "correct horse battery staple"
QA_ORIGIN = "http://testserver"


@pytest_asyncio.fixture
async def db_connection() -> AsyncIterator[AsyncConnection]:
    """Rollback-only connection against the migrated test database."""

    engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            yield connection
        finally:
            await transaction.rollback()
    await engine.dispose()


async def execute_committed(statement) -> None:
    """Run one statement in its own committed transaction.

    HTTP-level tests need mutations that the API's separate connection can
    observe, so the rollback-only fixture cannot be used for them.
    """

    engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    try:
        async with engine.begin() as connection:
            await connection.execute(statement)
    finally:
        await engine.dispose()


async def fetch_committed(statement):
    """Read committed state on a throwaway connection."""

    engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(statement)
            return result.all()
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# QA app assembly (Task 3 handoff review)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def build_qa_app():
    """Return the app under test, preferring the canonical ``app.main``.

    Release-gate mode: when CCR-20260724-005 has mounted the auth/tenancy
    routers into ``app.main``, tests run against the real canonical app so
    endpoint reachability, error handlers, and envelopes are verified on the
    shipped assembly. Before mounting, tests fall back to a QA assembly that
    mirrors the CCR instructions. In both modes a QA-only probe route is
    attached under ``workspace_router`` (its docstring invites exactly this)
    and the DB session dependency is overridden with a per-request NullPool
    engine, because pytest-asyncio gives every test its own event loop and
    the product's module-level engine pools connections across loops.
    """

    from app.auth.routes import router as auth_router
    from app.db import get_session
    from app.security.envelope import register_error_handlers
    from app.tenancy.routes import workspace_router

    from fastapi import APIRouter, Depends, FastAPI

    from app.tenancy.context import require_workspace_context

    # Dedicated probe router: include_router copies routes, so mutating
    # workspace_router after canonical mounting would not propagate. The
    # probe reuses the exact same guard dependency as workspace_router.
    probe_router = APIRouter(
        prefix="/api/workspaces/{workspaceId}",
        dependencies=[Depends(require_workspace_context)],
    )

    @probe_router.get("/qa-tenancy-probe")
    async def qa_tenancy_probe() -> dict[str, bool]:
        return {"reached": True}

    from app.main import app as canonical_app

    canonical_paths = {getattr(route, "path", "") for route in canonical_app.routes}
    if "/api/auth/csrf" in canonical_paths:
        app = canonical_app
    else:
        app = FastAPI(title="Ludus QA Task 3 assembly")
        app.include_router(auth_router)
        app.include_router(workspace_router)
        register_error_handlers(app)
    if "/api/workspaces/{workspaceId}/qa-tenancy-probe" not in {
        getattr(route, "path", "") for route in app.routes
    }:
        app.include_router(probe_router)

    # pytest-asyncio gives every test its own event loop. The product's
    # module-level engine pools asyncpg connections across loops, which
    # poisons later tests; the QA harness swaps in a NullPool session per
    # request so each connection lives and dies inside one loop.
    async def qa_get_session():
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        from sqlalchemy.pool import NullPool

        engine = create_async_engine(get_database_url(), poolclass=NullPool)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        try:
            async with factory() as session:
                yield session
        finally:
            await engine.dispose()

    app.dependency_overrides[get_session] = qa_get_session
    return app


def qa_client(client_ip: str | None = None) -> httpx.AsyncClient:
    """Async client over the assembled app with a same-origin header.

    Each client gets its own simulated source address by default so the
    Postgres-backed per-IP login throttle (auth hardening lane) never couples
    unrelated tests through a shared 127.0.0.1 budget.
    """

    address = client_ip or f"10.77.{uuid4().bytes[0]}.{uuid4().bytes[1]}"
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=build_qa_app(), client=(address, 51234)),
        base_url=QA_ORIGIN,
        headers={"Origin": QA_ORIGIN},
    )


async def csrf_headers(client: httpx.AsyncClient) -> dict[str, str]:
    response = await client.get("/api/auth/csrf")
    assert response.status_code == 200, "CSRF issuance endpoint must exist (C-01)"
    token = response.json()["data"]["csrfToken"]
    assert token
    return {"X-CSRF-Token": token}


async def register_user(
    client: httpx.AsyncClient,
    *,
    email: str | None = None,
    password: str = QA_PASSWORD,
) -> tuple[str, dict]:
    """Register a fresh user; return (email, session envelope data)."""

    email = email or f"qa-{uuid4().hex[:12]}@example.test"
    headers = await csrf_headers(client)
    response = await client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return email, response.json()["data"]


# ---------------------------------------------------------------------------
# DB-level tenancy fixture (runs on the frozen baseline)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TenancyFixture:
    """Two isolated workspaces with distinct users, memberships, and sessions."""

    user_a: UUID
    user_b: UUID
    workspace_a: UUID
    workspace_b: UUID
    membership_a: UUID
    membership_b: UUID
    session_a: UUID
    session_b: UUID


async def seed_two_tenants(connection: AsyncConnection) -> TenancyFixture:
    """Insert two users, two workspaces, one membership + session each.

    Capability sets intentionally differ so projection tests can tell the
    tenants apart: A's membership stores the full grant list, B's lacks
    ``sign``.
    """

    now = datetime.now(timezone.utc)
    user_a, user_b = uuid4(), uuid4()
    ws_a, ws_b = uuid4(), uuid4()
    member_a, member_b = uuid4(), uuid4()
    session_a, session_b = uuid4(), uuid4()

    await connection.execute(
        insert(User),
        [
            {
                "id": user_a,
                "email": f"qa-a-{user_a.hex[:12]}@example.test",
                "password_hash": "$argon2id$qa-fixture-not-a-real-hash",
                "status": UserStatus.ACTIVE,
            },
            {
                "id": user_b,
                "email": f"qa-b-{user_b.hex[:12]}@example.test",
                "password_hash": "$argon2id$qa-fixture-not-a-real-hash",
                "status": UserStatus.ACTIVE,
            },
        ],
    )
    await connection.execute(
        insert(Workspace),
        [
            {
                "id": ws_a,
                "name": "QA Tenant A",
                "status": WorkspaceStatus.ACTIVE,
                "created_by_user_id": user_a,
            },
            {
                "id": ws_b,
                "name": "QA Tenant B",
                "status": WorkspaceStatus.ACTIVE,
                "created_by_user_id": user_b,
            },
        ],
    )
    await connection.execute(
        insert(WorkspaceMembership),
        [
            {
                "id": member_a,
                "workspace_id": ws_a,
                "user_id": user_a,
                "role": WorkspaceRole.OWNER,
                "capabilities": [
                    WorkspaceCapability.CONTRIBUTE,
                    WorkspaceCapability.REVIEW,
                    WorkspaceCapability.SIGN,
                    WorkspaceCapability.MANAGE_CONNECTORS,
                ],
                "status": WorkspaceMembershipStatus.ACTIVE,
            },
            {
                "id": member_b,
                "workspace_id": ws_b,
                "user_id": user_b,
                "role": WorkspaceRole.MEMBER,
                "capabilities": [
                    WorkspaceCapability.CONTRIBUTE,
                    WorkspaceCapability.REVIEW,
                ],
                "status": WorkspaceMembershipStatus.ACTIVE,
            },
        ],
    )
    await connection.execute(
        insert(UserSession),
        [
            {
                "id": session_a,
                "user_id": user_a,
                "token_version": 1,
                "expires_at": now + timedelta(hours=1),
            },
            {
                "id": session_b,
                "user_id": user_b,
                "token_version": 1,
                "expires_at": now + timedelta(hours=1),
            },
        ],
    )
    return TenancyFixture(
        user_a=user_a,
        user_b=user_b,
        workspace_a=ws_a,
        workspace_b=ws_b,
        membership_a=member_a,
        membership_b=member_b,
        session_a=session_a,
        session_b=session_b,
    )


@pytest_asyncio.fixture
async def two_tenants(db_connection: AsyncConnection) -> TenancyFixture:
    return await seed_two_tenants(db_connection)
