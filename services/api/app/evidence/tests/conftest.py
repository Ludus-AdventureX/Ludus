"""Shared fixtures for the Task 8 evidence ledger owner suite.

Follows the simulations owner-suite pattern: a transactional savepoint
session against the migrated test database, one fully seeded tenant scope
per test, and a tmp-dir artifact store so no test writes outside pytest's
sandbox. This directory is deliberately not a package.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.db import get_database_url
from app.evidence.artifact_store import FilesystemArtifactStore
from app.models import (
    AnalysisRun,
    DecisionCase,
    DecisionSubject,
    SourceRecord,
    SourceSpan,
    User,
    Workspace,
    WorkspaceMembership,
)
from app.types import (
    FormalAnalysisLevel,
    OriginMode,
    SourceKind,
    SourceScope,
    WorkspaceRole,
)

from evidence_world import EvidenceWorld

NOW = datetime(2026, 7, 25, 12, 0, 0, tzinfo=timezone.utc)


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


@pytest.fixture
def artifact_store(tmp_path) -> FilesystemArtifactStore:
    return FilesystemArtifactStore(root=tmp_path / "artifacts")


async def seed_evidence_world(session: AsyncSession, slug: str) -> EvidenceWorld:
    ws_id, user_id, subject_id, case_id = uuid4(), uuid4(), uuid4(), uuid4()
    run_id, record_id, span_id = uuid4(), uuid4(), uuid4()

    session.add(User(id=user_id, email=f"evidence-{slug}@example.test", password_hash="x"))
    await session.flush()
    session.add(Workspace(id=ws_id, name=f"ws-{slug}", created_by_user_id=user_id))
    await session.flush()
    session.add(
        WorkspaceMembership(
            id=uuid4(), workspace_id=ws_id, user_id=user_id, role=WorkspaceRole.OWNER
        )
    )
    session.add(
        DecisionSubject(id=subject_id, workspace_id=ws_id, name=f"subject-{slug}", slug=slug)
    )
    await session.flush()
    session.add(
        DecisionCase(
            decision_case_id=case_id,
            workspace_id=ws_id,
            decision_subject_id=subject_id,
            title=f"case-{slug}",
            decision_question="enter the rescue market?",
        )
    )
    await session.flush()
    session.add(
        AnalysisRun(
            analysis_run_id=run_id,
            workspace_id=ws_id,
            decision_case_id=case_id,
            charter_id=uuid4(),
            charter_version=1,
            run_manifest_id=uuid4(),
            run_manifest_hash="sha256:manifest",
            cynefin_gate_result_id=uuid4(),
            analysis_level=FormalAnalysisLevel.FULL,
            case_version=1,
            case_snapshot_hash="sha256:case",
            dossier_snapshot_version=1,
            dossier_snapshot_hash="sha256:dossier",
            method_id="hardtech-market-direction",
            method_version="1.1.0",
            method_content_hash="sha256:method",
            idempotency_key=f"idem-evidence-{slug}",
        )
    )
    await session.flush()
    session.add(
        SourceRecord(
            id=record_id,
            workspace_id=ws_id,
            decision_case_id=case_id,
            source_scope=SourceScope.PRE_RUN,
            kind=SourceKind.WEB_PAGE,
            canonical_uri=f"https://example.test/{slug}/report",
            title=f"source-{slug}",
            content_hash="sha256:source",
            source_version="v1",
            origin_mode=OriginMode.FIXTURE,
        )
    )
    await session.flush()
    session.add(
        SourceSpan(
            id=span_id,
            workspace_id=ws_id,
            decision_case_id=case_id,
            source_record_id=record_id,
            source_scope=SourceScope.PRE_RUN,
            locator={"paragraph_index": 2, "char_start": 10, "char_end": 90},
            quote="3 of 5 interviewed rescue teams identified remote reconnaissance.",
            quote_hash="sha256:quote",
        )
    )
    await session.flush()
    return EvidenceWorld(
        workspace_id=ws_id,
        user_id=user_id,
        subject_id=subject_id,
        case_id=case_id,
        analysis_run_id=run_id,
        source_record_id=record_id,
        source_span_id=span_id,
    )


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> EvidenceWorld:
    return await seed_evidence_world(session, f"w{uuid4().hex[:10]}")


@pytest_asyncio.fixture
async def foreign_world(session: AsyncSession) -> EvidenceWorld:
    return await seed_evidence_world(session, f"f{uuid4().hex[:10]}")
