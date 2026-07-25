"""Task 8 owner tests: evidence ledger persistence, tenancy, and constraints."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.evidence.models import (
    EvidenceItem,
    EvidenceRelation,
    QualityAssessment,
    RawArtifact,
    RetrievalTask,
)
from app.evidence.repository import EvidenceReadRepository
from app.types import EvidenceVerdict, OriginMode

from evidence_world import EvidenceWorld

NOW = datetime(2026, 7, 25, 12, 0, 0, tzinfo=timezone.utc)
SHA = "a" * 64


def _retrieval_task(world: EvidenceWorld, **overrides) -> RetrievalTask:
    values = dict(
        id=uuid4(),
        workspace_id=world.workspace_id,
        decision_case_id=world.case_id,
        analysis_run_id=world.analysis_run_id,
        stable_tool_name="search_web",
        query_summary="rescue market",
        input_hash="sha256:" + "b" * 64,
        status="completed",
        created_at=NOW,
        completed_at=NOW,
    )
    values.update(overrides)
    return RetrievalTask(**values)


def _raw_artifact(world: EvidenceWorld, task_id: UUID | None = None, **overrides) -> RawArtifact:
    values = dict(
        id=uuid4(),
        workspace_id=world.workspace_id,
        decision_case_id=world.case_id,
        analysis_run_id=world.analysis_run_id,
        retrieval_task_id=task_id,
        kind="web_page",
        media_type="text/markdown",
        byte_size=120,
        sha256=SHA,
        storage_path=f"workspaces/{world.workspace_id}/uploads/raw/{uuid4().hex}.md",
        source_url="https://public.example.test/report",
        origin_mode=OriginMode.FIXTURE,
    )
    values.update(overrides)
    return RawArtifact(**values)


def _assessment(world: EvidenceWorld, artifact_id: UUID, **overrides) -> QualityAssessment:
    values = dict(
        id=uuid4(),
        workspace_id=world.workspace_id,
        decision_case_id=world.case_id,
        analysis_run_id=world.analysis_run_id,
        raw_artifact_id=artifact_id,
        authenticity=0.9,
        source_quality=0.85,
        relevance=0.8,
        freshness=1.0,
        applicability=0.8,
        independence=0.75,
        extraction_reliability=0.9,
        verdict=EvidenceVerdict.ACCEPTED,
    )
    values.update(overrides)
    return QualityAssessment(**values)


def _evidence_item(
    world: EvidenceWorld,
    artifact_id: UUID,
    assessment_id: UUID,
    **overrides,
) -> EvidenceItem:
    values = dict(
        id=uuid4(),
        workspace_id=world.workspace_id,
        decision_case_id=world.case_id,
        analysis_run_id=world.analysis_run_id,
        title="Rescue market evidence",
        url="https://public.example.test/report",
        source_domain="public.example.test",
        source_grade="L2_reputable",
        snippet="Procurement cycles run 14-22 months.",
        source_record_id=world.source_record_id,
        source_span_ids=[str(world.source_span_id)],
        retrieved_at=NOW,
        freshness_status="fresh",
        relevance=0.8,
        verdict=EvidenceVerdict.ACCEPTED,
        origin_mode=OriginMode.FIXTURE,
        raw_artifact_id=artifact_id,
        quality_assessment_id=assessment_id,
    )
    values.update(overrides)
    return EvidenceItem(**values)


async def seed_chain(
    session: AsyncSession, world: EvidenceWorld, **item_overrides
) -> EvidenceItem:
    task = _retrieval_task(world)
    session.add(task)
    await session.flush()
    artifact = _raw_artifact(world, task_id=task.id)
    session.add(artifact)
    await session.flush()
    assessment = _assessment(world, artifact.id)
    session.add(assessment)
    await session.flush()
    item = _evidence_item(world, artifact.id, assessment.id, **item_overrides)
    session.add(item)
    await session.flush()
    return item


# --- happy path + provenance chain -------------------------------------------


async def test_full_chain_persists_and_reads_back(session, world) -> None:
    item = await seed_chain(session, world)
    repo = EvidenceReadRepository(session)
    loaded = await repo.get_evidence_item(world.workspace_id, item.id)
    assert loaded is not None
    artifact = await repo.get_raw_artifact(world.workspace_id, loaded.raw_artifact_id)
    assessment = await repo.get_quality_assessment(
        world.workspace_id, loaded.quality_assessment_id
    )
    record = await repo.get_source_record(world.workspace_id, loaded.source_record_id)
    assert artifact is not None and assessment is not None and record is not None
    spans = await repo.list_source_spans(world.workspace_id, record.id)
    assert [str(span.id) for span in spans] == loaded.source_span_ids


async def test_raw_artifact_and_assessment_have_no_update_surface() -> None:
    # Immutability by construction: no updated_at column exists to churn.
    assert "updated_at" not in {c.key for c in inspect(RawArtifact).columns}
    assert "updated_at" not in {c.key for c in inspect(QualityAssessment).columns}
    assert "updated_at" not in {c.key for c in inspect(EvidenceItem).columns}


# --- tenant isolation / anti-enumeration at the repository layer -------------


async def test_repository_is_tenant_scoped(session, world, foreign_world) -> None:
    item = await seed_chain(session, world)
    repo = EvidenceReadRepository(session)
    # The same id is invisible from another workspace: identical None as a
    # truly nonexistent id (anti-enumeration).
    assert await repo.get_evidence_item(foreign_world.workspace_id, item.id) is None
    assert await repo.get_evidence_item(world.workspace_id, uuid4()) is None
    assert await repo.list_run_evidence(
        foreign_world.workspace_id, world.analysis_run_id
    ) == []
    assert not await repo.run_exists(foreign_world.workspace_id, world.analysis_run_id)


async def test_cross_workspace_run_reference_rejected_by_composite_fk(
    session, world, foreign_world
) -> None:
    task = _retrieval_task(world, analysis_run_id=foreign_world.analysis_run_id)
    session.add(task)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


# --- CHECK constraint negatives ----------------------------------------------


async def test_conditional_verdict_without_limits_rejected_by_db(session, world) -> None:
    async with session.begin_nested():
        task = _retrieval_task(world)
        session.add(task)
        await session.flush()
        artifact = _raw_artifact(world, task_id=task.id)
        session.add(artifact)
        await session.flush()
        assessment = _assessment(world, artifact.id, verdict=EvidenceVerdict.CONDITIONAL)
        session.add(assessment)
        await session.flush()
        item = _evidence_item(
            world,
            artifact.id,
            assessment.id,
            verdict=EvidenceVerdict.CONDITIONAL,
            applicability_limits=[],
        )
        session.add(item)
        with pytest.raises(IntegrityError) as excinfo:
            await session.flush()
    assert "conditional_requires_limits" in str(excinfo.value)


@pytest.mark.parametrize(
    ("field", "value", "constraint"),
    [
        ("sha256", "not-hex", "sha256_hex"),
        ("storage_provider", "s3", "storage_provider_locked"),
        ("storage_path", "/absolute/path.md", "storage_path_workspace_relative"),
        ("storage_path", "workspaces/../escape.md", "storage_path_workspace_relative"),
        ("kind", "screenshot", "kind_canonical"),
        ("byte_size", -1, "byte_size_non_negative"),
    ],
)
async def test_raw_artifact_check_negatives(session, world, field, value, constraint) -> None:
    async with session.begin_nested():
        artifact = _raw_artifact(world, **{field: value})
        session.add(artifact)
        with pytest.raises(IntegrityError) as excinfo:
            await session.flush()
    assert constraint in str(excinfo.value)


@pytest.mark.parametrize(
    ("field", "value", "constraint"),
    [
        ("stable_tool_name", "browse_web", "stable_tool_name_canonical"),
        ("input_hash", "", "input_hash_not_empty"),
    ],
)
async def test_retrieval_task_check_negatives(session, world, field, value, constraint) -> None:
    async with session.begin_nested():
        task = _retrieval_task(world, **{field: value})
        session.add(task)
        with pytest.raises(IntegrityError) as excinfo:
            await session.flush()
    assert constraint in str(excinfo.value)


async def test_retrieval_task_status_is_db_enum_rejecting_unknown_values(
    session, world
) -> None:
    from sqlalchemy.exc import DBAPIError

    async with session.begin_nested():
        session.add(_retrieval_task(world, status="paused"))
        with pytest.raises(DBAPIError) as excinfo:
            await session.flush()
    assert "retrieval_task_status" in str(excinfo.value)


@pytest.mark.parametrize(
    ("field", "value", "constraint"),
    [
        ("source_grade", "L0_root", "source_grade_canonical"),
        ("freshness_status", "ancient", "freshness_status_canonical"),
        ("relevance", 1.5, "relevance_range"),
    ],
)
async def test_evidence_item_check_negatives(session, world, field, value, constraint) -> None:
    async with session.begin_nested():
        task = _retrieval_task(world)
        session.add(task)
        await session.flush()
        artifact = _raw_artifact(world, task_id=task.id)
        session.add(artifact)
        await session.flush()
        assessment = _assessment(world, artifact.id)
        session.add(assessment)
        await session.flush()
        item = _evidence_item(world, artifact.id, assessment.id, **{field: value})
        session.add(item)
        with pytest.raises(IntegrityError) as excinfo:
            await session.flush()
    assert constraint in str(excinfo.value)


async def test_quality_dimension_range_enforced(session, world) -> None:
    async with session.begin_nested():
        artifact = _raw_artifact(world)
        session.add(artifact)
        await session.flush()
        session.add(_assessment(world, artifact.id, independence=1.2))
        with pytest.raises(IntegrityError) as excinfo:
            await session.flush()
    assert "independence_range" in str(excinfo.value)


# --- relations: same-source group and conflicts -------------------------------


async def test_evidence_relations_group_and_conflict_queries(session, world) -> None:
    group = uuid4()
    item_a = await seed_chain(session, world, independent_source_group_id=group)
    item_b = await seed_chain(session, world, independent_source_group_id=group)
    item_c = await seed_chain(session, world)
    session.add(
        EvidenceRelation(
            id=uuid4(),
            workspace_id=world.workspace_id,
            decision_case_id=world.case_id,
            from_evidence_item_id=item_a.id,
            to_evidence_item_id=item_b.id,
            kind="same_source_group",
            group_id=group,
        )
    )
    session.add(
        EvidenceRelation(
            id=uuid4(),
            workspace_id=world.workspace_id,
            decision_case_id=world.case_id,
            from_evidence_item_id=item_a.id,
            to_evidence_item_id=item_c.id,
            kind="conflicts_with",
        )
    )
    await session.flush()
    repo = EvidenceReadRepository(session)
    members = await repo.list_same_source_group(world.workspace_id, item_a)
    assert {member.id for member in members} == {item_a.id, item_b.id}
    conflicts = await repo.list_conflict_relations(
        world.workspace_id, world.analysis_run_id
    )
    assert len(conflicts) == 1
    assert conflicts[0].to_evidence_item_id == item_c.id


async def test_relation_self_reference_rejected(session, world) -> None:
    item = await seed_chain(session, world)
    async with session.begin_nested():
        session.add(
            EvidenceRelation(
                id=uuid4(),
                workspace_id=world.workspace_id,
                decision_case_id=world.case_id,
                from_evidence_item_id=item.id,
                to_evidence_item_id=item.id,
                kind="conflicts_with",
            )
        )
        with pytest.raises(IntegrityError) as excinfo:
            await session.flush()
    assert "no_self_relation" in str(excinfo.value)


# --- migration surface ---------------------------------------------------------


async def test_evidence_tables_and_enum_exist_with_single_alembic_head(session) -> None:
    tables = {
        row[0]
        for row in (
            await session.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE tablename IN "
                    "('retrieval_tasks', 'raw_artifacts', 'quality_assessments', "
                    "'evidence_items', 'evidence_relations')"
                )
            )
        ).all()
    }
    assert tables == {
        "retrieval_tasks",
        "raw_artifacts",
        "quality_assessments",
        "evidence_items",
        "evidence_relations",
    }
    enum_values = [
        row[0]
        for row in (
            await session.execute(
                text(
                    "SELECT e.enumlabel FROM pg_enum e "
                    "JOIN pg_type t ON t.oid = e.enumtypid "
                    "WHERE t.typname = 'evidence_verdict' ORDER BY e.enumsortorder"
                )
            )
        ).all()
    ]
    assert enum_values == ["accepted", "conditional", "lead_only", "rejected"]
    status_values = [
        row[0]
        for row in (
            await session.execute(
                text(
                    "SELECT e.enumlabel FROM pg_enum e "
                    "JOIN pg_type t ON t.oid = e.enumtypid "
                    "WHERE t.typname = 'retrieval_task_status' ORDER BY e.enumsortorder"
                )
            )
        ).all()
    ]
    assert status_values == ["queued", "running", "completed", "failed", "cancelled"]
    version = (
        await session.execute(text("SELECT version_num FROM alembic_version"))
    ).scalar_one()
    # Chain-robust: the applied head must contain the evidence revision in its
    # ancestry (later lane migrations legitimately advance the single head).
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    alembic_ini = Path(__file__).resolve().parents[3] / "alembic.ini"
    script = ScriptDirectory.from_config(Config(str(alembic_ini)))
    heads = script.get_heads()
    assert heads == [version], "single alembic head must equal the applied version"
    ancestry = {rev.revision for rev in script.walk_revisions("base", version)}
    assert "e7f3a2c9d5b1" in ancestry


async def test_all_evidence_tables_are_workspace_scoped(session) -> None:
    for table in (
        "retrieval_tasks",
        "raw_artifacts",
        "quality_assessments",
        "evidence_items",
        "evidence_relations",
    ):
        columns = {
            row[0]
            for row in (
                await session.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        f"WHERE table_name = '{table}'"
                    )
                )
            ).all()
        }
        assert "workspace_id" in columns


async def test_workspace_delete_cascades_evidence_rows(session, world) -> None:
    item = await seed_chain(session, world)
    await session.execute(
        text("DELETE FROM workspaces WHERE id = :ws"), {"ws": str(world.workspace_id)}
    )
    remaining = (
        await session.execute(
            select(EvidenceItem.id).where(EvidenceItem.id == item.id)
        )
    ).first()
    assert remaining is None
