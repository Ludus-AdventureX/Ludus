"""Shared fixtures for the deliberation council suite (CCR-20260804-DELIB-01).

Follows the evidence owner-suite pattern: a transactional savepoint session
against the migrated test database and one fully seeded tenant scope per
test (case + analysis run + research packets + retrieving influences event).
This directory is deliberately not a package.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.analyses.models import AnalysisEvent, ResearchPacket
from app.db import get_database_url
from app.models import (
    AnalysisRun,
    DecisionCase,
    DecisionSubject,
    User,
    Workspace,
    WorkspaceMembership,
)
from app.types import FormalAnalysisLevel, OriginMode, WorkspaceRole


@dataclass
class DeliberationWorld:
    workspace_id: UUID
    user_id: UUID
    case_id: UUID
    analysis_run_id: UUID


PACKETS = [
    {"factor": "渠道需求", "conclusion": "买方承诺四成采购量，渠道需求真实存在", "direction": "supporting", "claim_support_score": 0.9},
    {"factor": "品类增长", "conclusion": "品类出货量两年近五倍增长，趋势成立", "direction": "supporting", "claim_support_score": 0.8},
    {"factor": "克隆风险", "conclusion": "竞品可在六十天内复制核心卖点", "direction": "opposing", "claim_support_score": 0.7},
]

INFLUENCES = [
    {"from": "品类增长", "to": "克隆风险", "polarity": "+", "note": "增长叙事吸引大厂入场"},
]


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


async def seed_deliberation_world(session: AsyncSession, slug: str) -> DeliberationWorld:
    ws_id, user_id, subject_id, case_id = uuid4(), uuid4(), uuid4(), uuid4()
    run_id = uuid4()

    session.add(User(id=user_id, email=f"delib-{slug}@example.test", password_hash="x"))
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
            idempotency_key=f"idem-delib-{slug}",
        )
    )
    await session.flush()
    for packet in PACKETS:
        session.add(
            ResearchPacket(
                id=uuid4(),
                workspace_id=ws_id,
                decision_case_id=case_id,
                analysis_run_id=run_id,
                role="research",
                factor=packet["factor"],
                conclusion=packet["conclusion"],
                direction=packet["direction"],
                claim_support_score=packet["claim_support_score"],
            )
        )
    session.add(
        AnalysisEvent(
            id=uuid4(),
            workspace_id=ws_id,
            decision_case_id=case_id,
            analysis_run_id=run_id,
            sequence=1,
            category="agent.status",
            type="analysis.stage.completed",
            origin_mode=OriginMode.FIXTURE,
            source_origin_modes=["fixture"],
            payload={"stage": "retrieving", "influences": INFLUENCES},
        )
    )
    await session.flush()
    return DeliberationWorld(
        workspace_id=ws_id,
        user_id=user_id,
        case_id=case_id,
        analysis_run_id=run_id,
    )


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> DeliberationWorld:
    return await seed_deliberation_world(session, f"w{uuid4().hex[:10]}")


@pytest_asyncio.fixture
async def foreign_world(session: AsyncSession) -> DeliberationWorld:
    return await seed_deliberation_world(session, f"f{uuid4().hex[:10]}")
