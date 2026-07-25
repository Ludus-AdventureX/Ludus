"""Task 4 owner tests: dossier commands, immutable snapshots, versioning.

Run (disposable clean PostgreSQL + already-installed venv; no new environment):

    $env:DATABASE_URL = "postgresql+asyncpg://<user>:<password>@localhost:<port>/<db>"
    <mainvenv>python -m pytest tests/test_dossier_versions.py -q

Persistence targets are the frozen canonical tables (Task 19A migration). The
lane's only new table (``dossier_version_snapshots``) is created from ORM
metadata by the module fixture because this lane's Alembic revision is
deferred until the Task 10 ``0004`` migration lands (see handoff).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.db import Base, get_database_url
from app.dossiers.service import (
    ConfirmEntry,
    DossierNotFoundError,
    DossierService,
    DossierVersionConflictError,
    ExpireEntry,
    ProposeEntry,
    ReclassifyEntry,
    RejectEntry,
)
from app.models import (
    CandidateRevision,
    CaseVersion,
    DecisionCase,
    DecisionSubject,
    DomainEvent,
    DossierEntry,
    DossierVersion,
    User,
    Workspace,
)
from app.types import (
    CandidateRevisionStatus,
    CandidateSourceType,
    DossierStatementType,
    EntryStatus,
)

_TABLES_READY = False


async def ensure_task0405_tables() -> None:
    """Create this lane's deferred table once per test session."""

    global _TABLES_READY
    if _TABLES_READY:
        return
    engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all, checkfirst=True)
    finally:
        await engine.dispose()
    _TABLES_READY = True


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    await ensure_task0405_tables()
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


class DossierWorld:
    """One seeded tenant: workspace, subject (dossier at version 1), case."""

    def __init__(
        self,
        workspace_id: UUID,
        subject_id: UUID,
        dossier_id: UUID,
        case_id: UUID,
    ) -> None:
        self.workspace_id = workspace_id
        self.subject_id = subject_id
        self.dossier_id = dossier_id
        self.case_id = case_id


async def seed_dossier_world(session: AsyncSession, *, suffix: str | None = None) -> DossierWorld:
    suffix = suffix or uuid4().hex[:8]
    user = User(
        email=f"task04-{suffix}@example.test",
        password_hash="$argon2id$fixture-not-a-real-hash",
    )
    session.add(user)
    await session.flush()
    workspace = Workspace(name=f"Task04 Tenant {suffix}", created_by_user_id=user.id)
    session.add(workspace)
    await session.flush()
    subject = DecisionSubject(
        workspace_id=workspace.id,
        name=f"Subject {suffix}",
        slug=f"subject-{suffix}",
    )
    session.add(subject)
    await session.flush()
    case = DecisionCase(
        workspace_id=workspace.id,
        decision_subject_id=subject.id,
        title=f"Case {suffix}",
        decision_question="救援市场还是家庭服务市场？",
    )
    session.add(case)
    await session.flush()
    return DossierWorld(workspace.id, subject.id, subject.dossier_id, case.decision_case_id)


@pytest_asyncio.fixture
async def world(session: AsyncSession) -> DossierWorld:
    return await seed_dossier_world(session)


@pytest_asyncio.fixture
async def dossier_service(session: AsyncSession, world: DossierWorld) -> DossierService:
    return DossierService(session, workspace_id=world.workspace_id)


# ---------------------------------------------------------------------------
# 18-plan Task 4 Step 1: candidates must not enter formal snapshots
# ---------------------------------------------------------------------------


async def test_only_confirmed_entries_are_in_snapshot(
    dossier_service: DossierService, world: DossierWorld
) -> None:
    confirmed = await dossier_service.add_entry(
        world.subject_id, "工程资源为2人6个月", "constraint", "confirmed", scope="subject"
    )
    await dossier_service.add_entry(
        world.subject_id,
        "家庭市场更有吸引力",
        "judgment",
        "candidate",
        scope="case",
        decision_case_id=world.case_id,
    )
    snapshot = await dossier_service.create_snapshot(world.case_id)
    assert [item.id for item in snapshot.entries] == [confirmed.id]


async def test_candidate_add_entry_never_touches_dossier_entries(
    dossier_service: DossierService, world: DossierWorld, session: AsyncSession
) -> None:
    candidate = await dossier_service.add_entry(
        world.subject_id, "候选判断", "judgment", "candidate", scope="subject"
    )
    assert isinstance(candidate, CandidateRevision)
    count = await session.scalar(
        select(func.count()).select_from(DossierEntry).where(
            DossierEntry.workspace_id == world.workspace_id
        )
    )
    assert count == 0


# ---------------------------------------------------------------------------
# Command semantics: Propose / Reject never version; Confirm is atomic
# ---------------------------------------------------------------------------


def _proposal(content: str, statement_type: str = "constraint", scope: str = "case") -> dict:
    return {
        "operation": "add",
        "entry": {
            "scope": scope,
            "statementType": statement_type,
            "content": content,
            "sourceType": "ai_candidate",
        },
    }


async def _version_count(session: AsyncSession, workspace_id: UUID) -> int:
    return await session.scalar(
        select(func.count()).select_from(DossierVersion).where(
            DossierVersion.workspace_id == workspace_id
        )
    )


async def _event_types(session: AsyncSession, workspace_id: UUID) -> set[str]:
    return set(
        await session.scalars(
            select(DomainEvent.event_type).where(DomainEvent.workspace_id == workspace_id)
        )
    )


async def test_propose_and_reject_write_only_candidates_and_events(
    dossier_service: DossierService, world: DossierWorld, session: AsyncSession
) -> None:
    before_versions = await _version_count(session, world.workspace_id)
    candidate = await dossier_service.propose(
        ProposeEntry(
            workspace_id=world.workspace_id,
            decision_subject_id=world.subject_id,
            decision_case_id=world.case_id,
            proposals=[_proposal("现金窗口只有9个月")],
            source_type=CandidateSourceType.CONVERSATION,
            source_id=uuid4(),
            base_dossier_version=1,
            base_case_version=1,
        )
    )
    assert candidate.status == CandidateRevisionStatus.PENDING
    rejected = await dossier_service.reject(
        RejectEntry(workspace_id=world.workspace_id, candidate_revision_id=candidate.id)
    )
    assert rejected.status == CandidateRevisionStatus.REJECTED

    assert await _version_count(session, world.workspace_id) == before_versions
    case_versions = await session.scalar(
        select(func.count()).select_from(CaseVersion).where(
            CaseVersion.workspace_id == world.workspace_id
        )
    )
    assert case_versions == 0
    events = await _event_types(session, world.workspace_id)
    assert {"dossier.candidate_proposed", "dossier.candidate_rejected"} <= events


async def test_confirm_bumps_versions_and_snapshot_excludes_unconfirmed(
    dossier_service: DossierService, world: DossierWorld, session: AsyncSession
) -> None:
    """Full chain: candidate -> confirm -> version+1 -> snapshot excludes pending."""

    confirmed_candidate = await dossier_service.propose(
        ProposeEntry(
            workspace_id=world.workspace_id,
            decision_subject_id=world.subject_id,
            decision_case_id=world.case_id,
            proposals=[_proposal("工程资源上限为2名工程师、6个月")],
            source_type=CandidateSourceType.CONVERSATION,
            source_id=uuid4(),
            base_dossier_version=1,
            base_case_version=1,
        )
    )
    # A second candidate stays pending and must never appear in snapshots.
    await dossier_service.propose(
        ProposeEntry(
            workspace_id=world.workspace_id,
            decision_subject_id=world.subject_id,
            decision_case_id=world.case_id,
            proposals=[_proposal("家庭市场更有吸引力", statement_type="judgment")],
            source_type=CandidateSourceType.CONVERSATION,
            source_id=uuid4(),
            base_dossier_version=1,
            base_case_version=1,
        )
    )
    outcome = await dossier_service.confirm(
        ConfirmEntry(
            workspace_id=world.workspace_id,
            candidate_revision_id=confirmed_candidate.id,
            base_dossier_version=1,
            base_case_version=1,
        )
    )
    assert outcome["dossier_version"].version == 2
    assert outcome["case_version"] is not None and outcome["case_version"].version == 2
    assert outcome["candidate"].status == CandidateRevisionStatus.ACCEPTED
    assert await dossier_service.current_dossier_version(
        world.workspace_id, world.subject_id
    ) == 2

    case = await session.get(DecisionCase, world.case_id)
    assert case.current_version == 2

    snapshot = await dossier_service.create_snapshot(world.case_id)
    confirmed_entry = outcome["entries"][0]
    assert [item.id for item in snapshot.entries] == [confirmed_entry.id]

    events = await _event_types(session, world.workspace_id)
    assert "dossier.candidate_confirmed" in events


async def test_confirm_with_stale_base_dossier_version_conflicts(
    dossier_service: DossierService, world: DossierWorld
) -> None:
    first = await dossier_service.propose(
        ProposeEntry(
            workspace_id=world.workspace_id,
            decision_subject_id=world.subject_id,
            decision_case_id=world.case_id,
            proposals=[_proposal("约束A")],
            source_type=CandidateSourceType.CONVERSATION,
            source_id=uuid4(),
            base_dossier_version=1,
            base_case_version=1,
        )
    )
    second = await dossier_service.propose(
        ProposeEntry(
            workspace_id=world.workspace_id,
            decision_subject_id=world.subject_id,
            decision_case_id=world.case_id,
            proposals=[_proposal("约束B")],
            source_type=CandidateSourceType.CONVERSATION,
            source_id=uuid4(),
            base_dossier_version=1,
            base_case_version=1,
        )
    )
    await dossier_service.confirm(
        ConfirmEntry(
            workspace_id=world.workspace_id,
            candidate_revision_id=first.id,
            base_dossier_version=1,
            base_case_version=1,
        )
    )
    # The dossier moved to version 2; the second confirm still claims base 1.
    with pytest.raises(DossierVersionConflictError):
        await dossier_service.confirm(
            ConfirmEntry(
                workspace_id=world.workspace_id,
                candidate_revision_id=second.id,
                base_dossier_version=1,
                base_case_version=1,
            )
        )


async def test_confirm_with_stale_base_case_version_conflicts(
    dossier_service: DossierService, world: DossierWorld
) -> None:
    candidate = await dossier_service.propose(
        ProposeEntry(
            workspace_id=world.workspace_id,
            decision_subject_id=world.subject_id,
            decision_case_id=world.case_id,
            proposals=[_proposal("约束C")],
            source_type=CandidateSourceType.CONVERSATION,
            source_id=uuid4(),
            base_dossier_version=1,
            base_case_version=1,
        )
    )
    with pytest.raises(DossierVersionConflictError):
        await dossier_service.confirm(
            ConfirmEntry(
                workspace_id=world.workspace_id,
                candidate_revision_id=candidate.id,
                base_dossier_version=1,
                base_case_version=99,
            )
        )


# ---------------------------------------------------------------------------
# Snapshot immutability
# ---------------------------------------------------------------------------


async def test_snapshots_are_immutable_after_entry_edits(
    dossier_service: DossierService, world: DossierWorld, session: AsyncSession
) -> None:
    entry = await dossier_service.add_entry(
        world.subject_id, "初始约束内容", "constraint", "confirmed", scope="subject"
    )
    snapshot = await dossier_service.create_snapshot(world.case_id)
    frozen_entries = [
        (item.id, item.version, item.content_hash) for item in snapshot.entries
    ]
    frozen_hash = snapshot.snapshot_hash

    # A later formal edit (reclassify) must not rewrite the existing snapshot.
    await dossier_service.reclassify(
        ReclassifyEntry(
            workspace_id=world.workspace_id,
            target_id=entry.id,
            new_statement_type=DossierStatementType.ASSUMPTION,
        )
    )
    stored = await session.scalar(
        select(DossierVersion).where(
            DossierVersion.workspace_id == world.workspace_id,
            DossierVersion.dossier_id == world.dossier_id,
            DossierVersion.version == snapshot.version,
        )
    )
    assert stored is not None
    assert stored.snapshot_hash == frozen_hash
    companion = await dossier_service.repository.get_version_snapshot(
        world.workspace_id, stored.id
    )
    assert companion is not None
    assert [
        (UUID(item["entryId"]), item["entryVersion"], item["contentHash"])
        for item in companion.entries
    ] == frozen_entries
    # The edit produced a NEW later version instead.
    assert await dossier_service.current_dossier_version(
        world.workspace_id, world.subject_id
    ) > snapshot.version


# ---------------------------------------------------------------------------
# Expire / Reclassify fork: formal edit vs candidate-only update
# ---------------------------------------------------------------------------


async def test_expire_confirmed_entry_is_formal_edit_with_new_version(
    dossier_service: DossierService, world: DossierWorld
) -> None:
    entry = await dossier_service.add_entry(
        world.subject_id, "将过期的约束", "constraint", "confirmed", scope="subject"
    )
    version_before = await dossier_service.current_dossier_version(
        world.workspace_id, world.subject_id
    )
    outcome = await dossier_service.expire(
        ExpireEntry(workspace_id=world.workspace_id, target_id=entry.id)
    )
    assert outcome["formal"] is True
    assert outcome["dossier_version"].version == version_before + 1
    assert entry.status == EntryStatus.EXPIRED
    assert entry.version == 2


async def test_expire_candidate_only_updates_candidate_without_version(
    dossier_service: DossierService, world: DossierWorld, session: AsyncSession
) -> None:
    candidate = await dossier_service.add_entry(
        world.subject_id, "候选内容", "judgment", "candidate", scope="subject"
    )
    before_versions = await _version_count(session, world.workspace_id)
    outcome = await dossier_service.expire(
        ExpireEntry(workspace_id=world.workspace_id, target_id=candidate.id)
    )
    assert outcome["formal"] is False
    assert outcome["dossier_version"] is None
    assert await _version_count(session, world.workspace_id) == before_versions
    assert candidate.status == CandidateRevisionStatus.REJECTED


async def test_reclassify_confirmed_vs_candidate_fork(
    dossier_service: DossierService, world: DossierWorld, session: AsyncSession
) -> None:
    entry = await dossier_service.add_entry(
        world.subject_id, "被误分类的事实", "judgment", "confirmed", scope="subject"
    )
    formal = await dossier_service.reclassify(
        ReclassifyEntry(
            workspace_id=world.workspace_id,
            target_id=entry.id,
            new_statement_type=DossierStatementType.FACT,
        )
    )
    assert formal["formal"] is True
    assert entry.statement_type == DossierStatementType.FACT
    assert entry.version == 2

    candidate = await dossier_service.add_entry(
        world.subject_id, "候选判断待改类", "judgment", "candidate", scope="subject"
    )
    before_versions = await _version_count(session, world.workspace_id)
    soft = await dossier_service.reclassify(
        ReclassifyEntry(
            workspace_id=world.workspace_id,
            target_id=candidate.id,
            new_statement_type=DossierStatementType.ASSUMPTION,
        )
    )
    assert soft["formal"] is False
    assert await _version_count(session, world.workspace_id) == before_versions
    refreshed = await dossier_service.repository.get_candidate(
        world.workspace_id, candidate.id
    )
    assert refreshed.proposals[0]["entry"]["statementType"] == "assumption"
    assert refreshed.status == CandidateRevisionStatus.PENDING


# ---------------------------------------------------------------------------
# Cross-tenant isolation at the service seam
# ---------------------------------------------------------------------------


async def test_cross_tenant_candidate_and_case_invisible(
    session: AsyncSession,
) -> None:
    world_a = await seed_dossier_world(session, suffix=f"a{uuid4().hex[:6]}")
    world_b = await seed_dossier_world(session, suffix=f"b{uuid4().hex[:6]}")
    service_a = DossierService(session, workspace_id=world_a.workspace_id)
    service_b = DossierService(session, workspace_id=world_b.workspace_id)

    candidate = await service_a.propose(
        ProposeEntry(
            workspace_id=world_a.workspace_id,
            decision_subject_id=world_a.subject_id,
            decision_case_id=world_a.case_id,
            proposals=[_proposal("租户A的约束")],
            source_type=CandidateSourceType.CONVERSATION,
            source_id=uuid4(),
            base_dossier_version=1,
            base_case_version=1,
        )
    )
    # Tenant B cannot see tenant A's candidate, case, or subject.
    assert (
        await service_b.repository.get_candidate(world_b.workspace_id, candidate.id)
    ) is None
    assert (await service_b.repository.get_case(world_b.workspace_id, world_a.case_id)) is None
    with pytest.raises(DossierNotFoundError):
        await service_b.confirm(
            ConfirmEntry(
                workspace_id=world_b.workspace_id,
                candidate_revision_id=candidate.id,
                base_dossier_version=1,
            )
        )
    with pytest.raises(DossierNotFoundError):
        await service_b.add_entry(
            world_a.subject_id, "越界写入", "fact", "confirmed", scope="subject"
        )
