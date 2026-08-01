"""Dossier-assumption registration lane tests (lens reference authority).

The counterparty lens gate resolves every coreAssumptionIds entry against the
frozen ledger, and ledger assumption_ids come from persisted Claim rows. This
suite pins the worker lane that registers CONFIRMED dossier assumption entries
as Claim rows: the exact filter (case scope + assumption type + confirmed
status), the source_span_ids audit anchor, idempotency across repeated stage
entries, and the fail-closed empty case (no rows, no ledger ids, gate blocks
honestly).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.analyses.claims import Claim
from app.models import (
    AnalysisRun,
    DecisionCase,
    DecisionSubject,
    DossierEntry,
    User,
    Workspace,
)
from app.types import (
    DossierScope,
    DossierSourceType,
    DossierStatementType,
    EntryStatus,
    OriginMode,
)
from app.workers.analysis_worker import AnalysisWorker, RoleExecutors


async def _seed_workspace(connection: AsyncConnection) -> object:
    user_id = (
        await connection.execute(
            insert(User)
            .values(
                email=f"dossier-assumption-{uuid4()}@example.invalid",
                password_hash="not-a-real-hash",
            )
            .returning(User.id)
        )
    ).scalar_one()
    return (
        await connection.execute(
            insert(Workspace)
            .values(name=f"WS {uuid4()}", created_by_user_id=user_id)
            .returning(Workspace.id)
        )
    ).scalar_one()


async def _seed_case(connection: AsyncConnection, workspace_id: object) -> object:
    subject_id = (
        await connection.execute(
            insert(DecisionSubject)
            .values(workspace_id=workspace_id, name="Robot", slug=f"robot-{uuid4()}")
            .returning(DecisionSubject.id)
        )
    ).scalar_one()
    return (
        await connection.execute(
            insert(DecisionCase)
            .values(
                workspace_id=workspace_id,
                decision_subject_id=subject_id,
                title=f"Case {uuid4()}",
                decision_question="Rescue market first or home service market first?",
            )
            .returning(DecisionCase.decision_case_id)
        )
    ).scalar_one()


async def _seed_run(connection: AsyncConnection, workspace_id: object, decision_case_id: object) -> object:
    return (
        await connection.execute(
            insert(AnalysisRun)
            .values(
                workspace_id=workspace_id,
                decision_case_id=decision_case_id,
                charter_id=uuid4(),
                charter_version=1,
                run_manifest_id=uuid4(),
                run_manifest_hash="sha256:run-manifest",
                cynefin_gate_result_id=uuid4(),
                analysis_level="full",
                status="analyzing",
                progress=0,
                origin_modes=["fixture"],
                case_version=1,
                case_snapshot_hash="sha256:case-snapshot",
                dossier_snapshot_version=1,
                dossier_snapshot_hash="sha256:dossier-snapshot",
                method_id="hardtech-market-direction",
                method_version="1.1.0",
                method_content_hash="sha256:method-pack",
                attempt=1,
                max_attempts=1,
                idempotency_key=f"dossier-assumption-{uuid4()}",
            )
            .returning(AnalysisRun.analysis_run_id)
        )
    ).scalar_one()


async def _seed_dossier_entry(
    connection: AsyncConnection,
    workspace_id: object,
    subject_id: object,
    decision_case_id: object | None,
    *,
    statement_type: DossierStatementType,
    status: EntryStatus,
    content: str = "the market will accept a 9-month procurement cycle",
) -> object:
    return (
        await connection.execute(
            insert(DossierEntry)
            .values(
                workspace_id=workspace_id,
                decision_subject_id=subject_id,
                decision_case_id=decision_case_id,
                scope=DossierScope.CASE if decision_case_id else DossierScope.SUBJECT,
                statement_type=statement_type,
                content=content,
                status=status,
                source_type=DossierSourceType.USER,
                version=1,
            )
            .returning(DossierEntry.id)
        )
    ).scalar_one()


def _stub_executors() -> RoleExecutors:
    async def stub(run, stage, inputs):
        raise AssertionError("registration lane tests never execute role stages")

    return RoleExecutors(research=stub, critic=stub, synthesis=stub, validation=stub)


async def _claim_rows(
    connection: AsyncConnection, workspace_id: object, run_id: object
) -> list:
    return (
        await connection.execute(
            select(Claim).where(
                Claim.workspace_id == workspace_id,
                Claim.analysis_run_id == run_id,
            )
        )
    ).all()


@pytest.mark.asyncio
async def test_registers_confirmed_case_assumptions_as_claims(
    db_connection: AsyncConnection,
) -> None:
    workspace_id = await _seed_workspace(db_connection)
    case_id = await _seed_case(db_connection, workspace_id)
    run_id = await _seed_run(db_connection, workspace_id, case_id)
    subject_id = (
        await db_connection.execute(
            select(DecisionSubject.id).where(DecisionSubject.workspace_id == workspace_id)
        )
    ).scalar_one()
    entry_a = await _seed_dossier_entry(
        db_connection, workspace_id, subject_id, case_id,
        statement_type=DossierStatementType.ASSUMPTION, status=EntryStatus.CONFIRMED,
        content="procurement cycles run ~9 months",
    )
    entry_b = await _seed_dossier_entry(
        db_connection, workspace_id, subject_id, case_id,
        statement_type=DossierStatementType.ASSUMPTION, status=EntryStatus.CONFIRMED,
        content="first mover wins certification lockout",
    )

    async with AsyncSession(bind=db_connection) as session:
        run_row = (
            await session.execute(select(AnalysisRun).where(AnalysisRun.analysis_run_id == run_id))
        ).scalar_one()
        worker = AnalysisWorker(session, executors=_stub_executors(), origin_mode=OriginMode.FIXTURE)
        await worker._register_dossier_assumptions(run_row)
        await session.commit()

    rows = await _claim_rows(db_connection, workspace_id, run_id)
    assert len(rows) == 2
    by_span = {row.source_span_ids[0]: row for row in rows}
    assert set(by_span) == {str(entry_a), str(entry_b)}
    for row in rows:
        assert row.statement_type.value == "assumption"
        assert row.importance == "core"
        assert row.source == "user"
        assert row.status.value == EntryStatus.CONFIRMED.value
        assert row.responsibility == {}
        assert row.support_score == 0.0

    # The frozen reference sets must see the registered rows: this is exactly
    # what the lens prompt shows and what the write path resolves.
    async with AsyncSession(bind=db_connection) as session:
        run_row = (
            await session.execute(select(AnalysisRun).where(AnalysisRun.analysis_run_id == run_id))
        ).scalar_one()
        worker = AnalysisWorker(session, executors=_stub_executors(), origin_mode=OriginMode.FIXTURE)
        refs = await worker._frozen_reference_sets(run_row)
    # Ledger ids are the Claim row ids (the persisted authority), not the
    # dossier entry ids recorded as source_span_ids.
    assert refs["assumption_ids"] == {str(row.id) for row in rows}


@pytest.mark.asyncio
async def test_filters_out_subject_scope_non_assumption_and_unconfirmed(
    db_connection: AsyncConnection,
) -> None:
    workspace_id = await _seed_workspace(db_connection)
    case_id = await _seed_case(db_connection, workspace_id)
    run_id = await _seed_run(db_connection, workspace_id, case_id)
    subject_id = (
        await db_connection.execute(
            select(DecisionSubject.id).where(DecisionSubject.workspace_id == workspace_id)
        )
    ).scalar_one()
    # Only this one qualifies: case-scoped, assumption-typed, CONFIRMED.
    qualifying = await _seed_dossier_entry(
        db_connection, workspace_id, subject_id, case_id,
        statement_type=DossierStatementType.ASSUMPTION, status=EntryStatus.CONFIRMED,
    )
    # Subject-scoped assumption: NOT case authority.
    await _seed_dossier_entry(
        db_connection, workspace_id, subject_id, None,
        statement_type=DossierStatementType.ASSUMPTION, status=EntryStatus.CONFIRMED,
    )
    # Case-scoped but not an assumption.
    await _seed_dossier_entry(
        db_connection, workspace_id, subject_id, case_id,
        statement_type=DossierStatementType.JUDGMENT, status=EntryStatus.CONFIRMED,
    )
    # Case-scoped assumption but not CONFIRMED by the decision-maker.
    await _seed_dossier_entry(
        db_connection, workspace_id, subject_id, case_id,
        statement_type=DossierStatementType.ASSUMPTION, status=EntryStatus.CANDIDATE,
    )

    async with AsyncSession(bind=db_connection) as session:
        run_row = (
            await session.execute(select(AnalysisRun).where(AnalysisRun.analysis_run_id == run_id))
        ).scalar_one()
        worker = AnalysisWorker(session, executors=_stub_executors(), origin_mode=OriginMode.FIXTURE)
        await worker._register_dossier_assumptions(run_row)
        await session.commit()

    rows = await _claim_rows(db_connection, workspace_id, run_id)
    assert len(rows) == 1
    assert rows[0].source_span_ids == [str(qualifying)]


@pytest.mark.asyncio
async def test_registration_is_idempotent_across_stage_entries(
    db_connection: AsyncConnection,
) -> None:
    workspace_id = await _seed_workspace(db_connection)
    case_id = await _seed_case(db_connection, workspace_id)
    run_id = await _seed_run(db_connection, workspace_id, case_id)
    subject_id = (
        await db_connection.execute(
            select(DecisionSubject.id).where(DecisionSubject.workspace_id == workspace_id)
        )
    ).scalar_one()
    await _seed_dossier_entry(
        db_connection, workspace_id, subject_id, case_id,
        statement_type=DossierStatementType.ASSUMPTION, status=EntryStatus.CONFIRMED,
    )

    # _run_lens_stages runs once per lens stage (analyzing/criticizing/
    # synthesizing), so registration must survive repeated entry.
    async with AsyncSession(bind=db_connection) as session:
        run_row = (
            await session.execute(select(AnalysisRun).where(AnalysisRun.analysis_run_id == run_id))
        ).scalar_one()
        worker = AnalysisWorker(session, executors=_stub_executors(), origin_mode=OriginMode.FIXTURE)
        await worker._register_dossier_assumptions(run_row)
        await worker._register_dossier_assumptions(run_row)
        await worker._register_dossier_assumptions(run_row)
        await session.commit()

    count = (
        await db_connection.execute(
            select(func.count())
            .select_from(Claim)
            .where(Claim.workspace_id == workspace_id, Claim.analysis_run_id == run_id)
        )
    ).scalar_one()
    assert count == 1


@pytest.mark.asyncio
async def test_no_assumption_entries_registers_nothing(
    db_connection: AsyncConnection,
) -> None:
    workspace_id = await _seed_workspace(db_connection)
    case_id = await _seed_case(db_connection, workspace_id)
    run_id = await _seed_run(db_connection, workspace_id, case_id)
    subject_id = (
        await db_connection.execute(
            select(DecisionSubject.id).where(DecisionSubject.workspace_id == workspace_id)
        )
    ).scalar_one()
    # Only facts: no assumptions exist, nothing may be invented.
    await _seed_dossier_entry(
        db_connection, workspace_id, subject_id, case_id,
        statement_type=DossierStatementType.FACT, status=EntryStatus.CONFIRMED,
    )

    async with AsyncSession(bind=db_connection) as session:
        run_row = (
            await session.execute(select(AnalysisRun).where(AnalysisRun.analysis_run_id == run_id))
        ).scalar_one()
        worker = AnalysisWorker(session, executors=_stub_executors(), origin_mode=OriginMode.FIXTURE)
        await worker._register_dossier_assumptions(run_row)
        refs = await worker._frozen_reference_sets(run_row)
        await session.commit()

    rows = await _claim_rows(db_connection, workspace_id, run_id)
    assert rows == []
    # Fail-closed: the counterparty gate keeps blocking because the model can
    # only cite registered ids and there are none.
    assert refs["assumption_ids"] == frozenset()
