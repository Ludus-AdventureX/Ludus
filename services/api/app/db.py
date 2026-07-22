from __future__ import annotations

import os
from collections.abc import AsyncIterator

from sqlalchemy import MetaData
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def get_database_url() -> str:
    """Return the async PostgreSQL URL without logging credentials."""

    configured = os.getenv("DATABASE_URL")
    if configured:
        if configured.startswith("postgresql://"):
            return configured.replace("postgresql://", "postgresql+asyncpg://", 1)
        if configured.startswith("postgres://"):
            return configured.replace("postgres://", "postgresql+asyncpg://", 1)
        return configured

    return URL.create(
        drivername="postgresql+asyncpg",
        username=os.getenv("POSTGRES_USER", "decision_lab"),
        password=os.getenv("POSTGRES_PASSWORD", "decision_lab_dev"),
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "decision_lab"),
    ).render_as_string(hide_password=False)


def create_database_engine(database_url: str | None = None) -> AsyncEngine:
    return create_async_engine(
        database_url or get_database_url(),
        pool_pre_ping=True,
    )


engine = create_database_engine()
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session
