"""Shared fixtures for the Task 9 analysis runtime owner suite.

Fixtures only; seeding helpers live in ``runtime_world.py`` (uniquely named)
so test modules never do an ambiguous ``import conftest`` across the three
owner suites. This directory is deliberately not a package.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.db import get_database_url

from runtime_world import RuntimeWorld, seed_runtime_world


@pytest.fixture(autouse=True, scope="session")
def _qa_auth_jwt_secret() -> Iterator[None]:
    """AUTH_JWT_SECRET for the suite (AuthSettings fails closed without it)."""
    previous = os.environ.get("AUTH_JWT_SECRET")
    os.environ["AUTH_JWT_SECRET"] = "qa-test-jwt-secret-not-for-production"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("AUTH_JWT_SECRET", None)
        else:
            os.environ["AUTH_JWT_SECRET"] = previous


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    async with engine.connect() as connection:
        outer = await connection.begin()
        async_session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield async_session
        finally:
            await async_session.close()
            await outer.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> RuntimeWorld:
    return await seed_runtime_world(session, f"w{uuid4().hex[:10]}")


@pytest_asyncio.fixture
async def foreign_world(session: AsyncSession) -> RuntimeWorld:
    return await seed_runtime_world(session, f"f{uuid4().hex[:10]}")
