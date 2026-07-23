"""Shared QA fixtures for the Task 3 auth/workspace gate tests.

Fixtures here are implementation-independent: they rely only on the frozen
canonical models from Task 19A and a migrated PostgreSQL database. Gate tests
that need the not-yet-delivered auth implementation must importorskip it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

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

    User A owns workspace A only; user B owns workspace B only. Capability
    sets intentionally differ so capability-projection tests can tell them
    apart: A has the full human set, B lacks ``sign``.
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
                "role": WorkspaceRole.OWNER,
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
