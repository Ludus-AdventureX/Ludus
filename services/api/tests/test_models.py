from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.db import Base, get_database_url
from app.models import (
    DecisionSubject,
    DossierEntry,
    DossierVersion,
    Initiative,
    User,
    UserSession,
    Workspace,
    WorkspaceMembership,
)
from app.types import (
    DecisionLifecycleStage,
    EntryStatus,
    EvidenceVerdict,
    StatementType,
    StrategicLensType,
)


@pytest_asyncio.fixture
async def connection() -> AsyncIterator[AsyncConnection]:
    engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    async with engine.connect() as active_connection:
        transaction = await active_connection.begin()
        try:
            yield active_connection
        finally:
            await transaction.rollback()
    await engine.dispose()


def test_domain_enums_are_stable() -> None:
    assert StatementType.ASSUMPTION.value == "assumption"
    assert EntryStatus.CONFIRMED.value == "confirmed"
    assert EvidenceVerdict.LEAD_ONLY.value == "lead_only"
    assert [item.value for item in StrategicLensType] == [
        "porter_five_forces",
        "pre_mortem",
        "counterparty_response_matrix",
        "scenario_planning",
        "meadows_leverage_points",
    ]
    assert [item.value for item in DecisionLifecycleStage] == [
        "draft",
        "scoped",
        "ready",
        "running",
        "review",
        "pending_signoff",
        "decided",
        "monitoring",
    ]


def test_core_table_set_and_workspace_scope() -> None:
    expected = {
        "users",
        "workspaces",
        "workspace_memberships",
        "user_sessions",
        "decision_subjects",
        "initiatives",
        "decision_cases",
        "case_versions",
        "dossier_entries",
        "dossier_versions",
        "conversations",
        "messages",
        "candidate_revisions",
        "quick_analysis_results",
        "domain_events",
    }
    assert set(Base.metadata.tables) == expected

    global_tables = {"users", "workspaces", "user_sessions"}
    for table_name, table in Base.metadata.tables.items():
        if table_name not in global_tables:
            assert "workspace_id" in table.c

    assert "candidate_updates" not in Base.metadata.tables
    assert Base.metadata.tables["decision_cases"].c.status.type.name == "decision_lifecycle_stage"
    assert Base.metadata.tables["decision_cases"].c.operational_status.type.name == (
        "case_operational_status"
    )
    assert Base.metadata.tables["user_sessions"].c.revoked_at.nullable is True


async def seed_user_and_workspaces(connection: AsyncConnection) -> tuple[object, object, object]:
    user_id = (
        await connection.execute(
            insert(User)
            .values(email=f"task2-{uuid4()}@example.invalid", password_hash="not-a-real-hash")
            .returning(User.id)
        )
    ).scalar_one()
    workspace_ids = (
        await connection.execute(
            insert(Workspace)
            .values(
                [
                    {"name": "Workspace A", "created_by_user_id": user_id},
                    {"name": "Workspace B", "created_by_user_id": user_id},
                ]
            )
            .returning(Workspace.id)
        )
    ).scalars().all()
    return user_id, workspace_ids[0], workspace_ids[1]


@pytest.mark.asyncio
async def test_subject_slug_is_unique_only_inside_workspace(connection: AsyncConnection) -> None:
    _, workspace_a, workspace_b = await seed_user_and_workspaces(connection)
    slug = f"spherical-robot-{uuid4()}"

    await connection.execute(
        insert(DecisionSubject).values(
            workspace_id=workspace_a,
            name="Spherical Robot",
            slug=slug,
        )
    )

    savepoint = await connection.begin_nested()
    with pytest.raises(IntegrityError):
        await connection.execute(
            insert(DecisionSubject).values(
                workspace_id=workspace_a,
                name="Duplicate",
                slug=slug,
            )
        )
    await savepoint.rollback()

    await connection.execute(
        insert(DecisionSubject).values(
            workspace_id=workspace_b,
            name="Same slug in another tenant",
            slug=slug,
        )
    )


@pytest.mark.asyncio
async def test_workspace_delete_cascades_dossier_rows(connection: AsyncConnection) -> None:
    _, workspace_id, _ = await seed_user_and_workspaces(connection)
    subject = (
        await connection.execute(
            insert(DecisionSubject)
            .values(
                workspace_id=workspace_id,
                name="Spherical Robot",
                slug=f"spherical-robot-{uuid4()}",
            )
            .returning(DecisionSubject.id, DecisionSubject.dossier_id)
        )
    ).one()

    await connection.execute(
        insert(DossierVersion).values(
            workspace_id=workspace_id,
            dossier_id=subject.dossier_id,
            decision_subject_id=subject.id,
            version=1,
            snapshot_hash="sha256:test-dossier",
            reason="initial",
            created_by="test-user",
        )
    )
    await connection.execute(
        insert(DossierEntry).values(
            workspace_id=workspace_id,
            decision_subject_id=subject.id,
            scope="subject",
            statement_type="fact",
            content="The project exists.",
            status="confirmed",
            source_type="user",
            version=1,
        )
    )

    await connection.execute(delete(Workspace).where(Workspace.id == workspace_id))

    for model in (DecisionSubject, DossierVersion, DossierEntry):
        remaining = await connection.scalar(
            select(func.count()).select_from(model).where(model.workspace_id == workspace_id)
        )
        assert remaining == 0


@pytest.mark.asyncio
async def test_cross_workspace_parent_reference_is_rejected(connection: AsyncConnection) -> None:
    _, workspace_a, workspace_b = await seed_user_and_workspaces(connection)
    subject_id = (
        await connection.execute(
            insert(DecisionSubject)
            .values(
                workspace_id=workspace_a,
                name="Tenant A subject",
                slug=f"tenant-a-{uuid4()}",
            )
            .returning(DecisionSubject.id)
        )
    ).scalar_one()

    savepoint = await connection.begin_nested()
    with pytest.raises(IntegrityError):
        await connection.execute(
            insert(Initiative).values(
                workspace_id=workspace_b,
                decision_subject_id=subject_id,
                name="Cross tenant initiative",
            )
        )
    await savepoint.rollback()


@pytest.mark.asyncio
async def test_case_scoped_entry_requires_decision_case(connection: AsyncConnection) -> None:
    _, workspace_id, _ = await seed_user_and_workspaces(connection)
    subject_id = (
        await connection.execute(
            insert(DecisionSubject)
            .values(
                workspace_id=workspace_id,
                name="Scope subject",
                slug=f"scope-{uuid4()}",
            )
            .returning(DecisionSubject.id)
        )
    ).scalar_one()

    savepoint = await connection.begin_nested()
    with pytest.raises(IntegrityError):
        await connection.execute(
            insert(DossierEntry).values(
                workspace_id=workspace_id,
                decision_subject_id=subject_id,
                scope="case",
                statement_type="assumption",
                content="Invalid case-scoped entry",
                status="candidate",
                source_type="user",
                version=1,
            )
        )
    await savepoint.rollback()


@pytest.mark.asyncio
async def test_membership_capability_and_session_revocation_fields_work(
    connection: AsyncConnection,
) -> None:
    user_id, workspace_id, _ = await seed_user_and_workspaces(connection)
    await connection.execute(
        insert(WorkspaceMembership).values(
            workspace_id=workspace_id,
            user_id=user_id,
            role="owner",
            capabilities=["contribute", "review", "sign", "manage_connectors"],
        )
    )
    session_id = (
        await connection.execute(
            insert(UserSession)
            .values(
                user_id=user_id,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
            .returning(UserSession.id)
        )
    ).scalar_one()
    revoked_at = datetime.now(timezone.utc)
    await connection.execute(
        update(UserSession).where(UserSession.id == session_id).values(revoked_at=revoked_at)
    )
    stored = await connection.scalar(
        select(UserSession.revoked_at).where(UserSession.id == session_id)
    )
    assert stored is not None
