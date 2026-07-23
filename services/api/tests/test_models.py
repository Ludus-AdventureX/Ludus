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
    AnalysisRun,
    Conversation,
    DecisionCase,
    DecisionSubject,
    DossierEntry,
    DossierVersion,
    Initiative,
    Message,
    QuickAnalysisResult,
    SignoffRequest as SignoffRequestModel,
    SimulationRun as SimulationRunModel,
    SourceRecord as SourceRecordModel,
    SourceSpan as SourceSpanModel,
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
        "analysis_runs",
        "source_records",
        "source_spans",
        "simulation_runs",
        "signoff_requests",
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

async def seed_subject_pair(
    connection: AsyncConnection,
    workspace_id: object,
) -> tuple[object, object]:
    subject_ids = (
        await connection.execute(
            insert(DecisionSubject)
            .values(
                [
                    {
                        "workspace_id": workspace_id,
                        "name": "Subject A",
                        "slug": f"subject-a-{uuid4()}",
                    },
                    {
                        "workspace_id": workspace_id,
                        "name": "Subject B",
                        "slug": f"subject-b-{uuid4()}",
                    },
                ]
            )
            .returning(DecisionSubject.id)
        )
    ).scalars().all()
    return subject_ids[0], subject_ids[1]


async def seed_case(
    connection: AsyncConnection,
    workspace_id: object,
    subject_id: object,
    *,
    initiative_id: object | None = None,
) -> object:
    return (
        await connection.execute(
            insert(DecisionCase)
            .values(
                workspace_id=workspace_id,
                decision_subject_id=subject_id,
                initiative_id=initiative_id,
                title=f"Case {uuid4()}",
                decision_question="Which option should be prioritized?",
            )
            .returning(DecisionCase.decision_case_id)
        )
    ).scalar_one()


async def seed_conversation(
    connection: AsyncConnection,
    workspace_id: object,
    subject_id: object,
    case_id: object,
) -> object:
    return (
        await connection.execute(
            insert(Conversation)
            .values(
                workspace_id=workspace_id,
                decision_subject_id=subject_id,
                decision_case_id=case_id,
            )
            .returning(Conversation.id)
        )
    ).scalar_one()


@pytest.mark.asyncio
async def test_same_workspace_cross_subject_case_initiative_is_rejected(
    connection: AsyncConnection,
) -> None:
    _, workspace_id, _ = await seed_user_and_workspaces(connection)
    subject_a, subject_b = await seed_subject_pair(connection, workspace_id)
    initiative_id = (
        await connection.execute(
            insert(Initiative)
            .values(
                workspace_id=workspace_id,
                decision_subject_id=subject_a,
                name="Subject A initiative",
            )
            .returning(Initiative.id)
        )
    ).scalar_one()

    savepoint = await connection.begin_nested()
    with pytest.raises(IntegrityError):
        await seed_case(
            connection,
            workspace_id,
            subject_b,
            initiative_id=initiative_id,
        )
    await savepoint.rollback()


@pytest.mark.asyncio
async def test_same_workspace_cross_subject_case_scoped_entry_is_rejected(
    connection: AsyncConnection,
) -> None:
    _, workspace_id, _ = await seed_user_and_workspaces(connection)
    subject_a, subject_b = await seed_subject_pair(connection, workspace_id)
    case_a = await seed_case(connection, workspace_id, subject_a)

    savepoint = await connection.begin_nested()
    with pytest.raises(IntegrityError):
        await connection.execute(
            insert(DossierEntry).values(
                workspace_id=workspace_id,
                decision_subject_id=subject_b,
                decision_case_id=case_a,
                scope="case",
                statement_type="assumption",
                content="Cross-subject case entry",
                status="candidate",
                source_type="user",
                version=1,
            )
        )
    await savepoint.rollback()


@pytest.mark.asyncio
async def test_same_workspace_cross_subject_conversation_is_rejected(
    connection: AsyncConnection,
) -> None:
    _, workspace_id, _ = await seed_user_and_workspaces(connection)
    subject_a, subject_b = await seed_subject_pair(connection, workspace_id)
    case_a = await seed_case(connection, workspace_id, subject_a)

    savepoint = await connection.begin_nested()
    with pytest.raises(IntegrityError):
        await connection.execute(
            insert(Conversation).values(
                workspace_id=workspace_id,
                decision_subject_id=subject_b,
                decision_case_id=case_a,
            )
        )
    await savepoint.rollback()


@pytest.mark.asyncio
async def test_message_scope_must_match_its_conversation_and_case(
    connection: AsyncConnection,
) -> None:
    _, workspace_id, _ = await seed_user_and_workspaces(connection)
    subject_a, subject_b = await seed_subject_pair(connection, workspace_id)
    case_a = await seed_case(connection, workspace_id, subject_a)
    case_b = await seed_case(connection, workspace_id, subject_b)
    conversation_a = await seed_conversation(connection, workspace_id, subject_a, case_a)

    savepoint = await connection.begin_nested()
    with pytest.raises(IntegrityError):
        await connection.execute(
            insert(Message).values(
                workspace_id=workspace_id,
                conversation_id=conversation_a,
                decision_subject_id=subject_b,
                decision_case_id=case_b,
                role="user",
                content="Cross-subject conversation message",
            )
        )
    await savepoint.rollback()


@pytest.mark.asyncio
async def test_quick_analysis_case_must_match_its_conversation(
    connection: AsyncConnection,
) -> None:
    _, workspace_id, _ = await seed_user_and_workspaces(connection)
    subject_a, subject_b = await seed_subject_pair(connection, workspace_id)
    case_a = await seed_case(connection, workspace_id, subject_a)
    case_b = await seed_case(connection, workspace_id, subject_b)
    conversation_a = await seed_conversation(connection, workspace_id, subject_a, case_a)

    savepoint = await connection.begin_nested()
    with pytest.raises(IntegrityError):
        await connection.execute(
            insert(QuickAnalysisResult).values(
                workspace_id=workspace_id,
                conversation_id=conversation_a,
                decision_case_id=case_b,
                judgment="Cross-subject quick analysis",
            )
        )
    await savepoint.rollback()

async def seed_analysis_run(
    connection: AsyncConnection,
    workspace_id: object,
    decision_case_id: object,
) -> object:
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
                analysis_level="focused",
                status="queued",
                progress=0,
                origin_modes=["fixture"],
                case_version=1,
                case_snapshot_hash="sha256:case-snapshot",
                dossier_snapshot_version=1,
                dossier_snapshot_hash="sha256:dossier-snapshot",
                method_id="method-1",
                method_version="1.1.0",
                method_content_hash="sha256:method-1",
                attempt=1,
                max_attempts=1,
                idempotency_key=f"analysis-{uuid4()}",
            )
            .returning(AnalysisRun.analysis_run_id)
        )
    ).scalar_one()


@pytest.mark.asyncio
async def test_task_19a_source_scope_and_cross_case_bindings_are_rejected(
    connection: AsyncConnection,
) -> None:
    _, workspace_id, _ = await seed_user_and_workspaces(connection)
    subject_a, subject_b = await seed_subject_pair(connection, workspace_id)
    case_a = await seed_case(connection, workspace_id, subject_a)
    case_b = await seed_case(connection, workspace_id, subject_b)
    run_a = await seed_analysis_run(connection, workspace_id, case_a)
    run_b = await seed_analysis_run(connection, workspace_id, case_b)

    source_a_id = uuid4()
    await connection.execute(
        insert(SourceRecordModel).values(
            id=source_a_id,
            workspace_id=workspace_id,
            decision_case_id=case_a,
            source_scope="pre_run",
            kind="human_input",
            canonical_uri="ludus://case/source-a",
            title="Case A source",
            content_hash="sha256:source-a",
            source_version="1",
            origin_mode="fixture",
        )
    )
    source_b_id = uuid4()
    await connection.execute(
        insert(SourceRecordModel).values(
            id=source_b_id,
            workspace_id=workspace_id,
            decision_case_id=case_b,
            source_scope="pre_run",
            kind="human_input",
            canonical_uri="ludus://case/source-b",
            title="Case B source",
            content_hash="sha256:source-b",
            source_version="1",
            origin_mode="fixture",
        )
    )
    await connection.execute(
        insert(SourceRecordModel).values(
            id=uuid4(),
            workspace_id=workspace_id,
            decision_case_id=case_b,
            source_scope="run_frozen",
            analysis_run_id=run_b,
            frozen_from_source_record_id=source_b_id,
            frozen_at=datetime.now(timezone.utc),
            kind="human_input",
            canonical_uri="ludus://case/source-b/frozen",
            title="Case B frozen source",
            content_hash="sha256:source-b-frozen",
            source_version="1",
            origin_mode="fixture",
        )
    )

    savepoint = await connection.begin_nested()
    with pytest.raises(IntegrityError):
        await connection.execute(
            insert(SourceRecordModel).values(
                id=uuid4(),
                workspace_id=workspace_id,
                decision_case_id=case_a,
                source_scope="pre_run",
                analysis_run_id=run_a,
                kind="human_input",
                canonical_uri="ludus://case/illegal-pre-run",
                title="Illegal pre-run source",
                content_hash="sha256:illegal-pre-run",
                source_version="1",
                origin_mode="fixture",
            )
        )
    await savepoint.rollback()

    savepoint = await connection.begin_nested()
    with pytest.raises(IntegrityError):
        await connection.execute(
            insert(SourceRecordModel).values(
                id=uuid4(),
                workspace_id=workspace_id,
                decision_case_id=case_a,
                source_scope="run_frozen",
                analysis_run_id=run_b,
                frozen_from_source_record_id=source_a_id,
                frozen_at=datetime.now(timezone.utc),
                kind="human_input",
                canonical_uri="ludus://case/cross-case-frozen",
                title="Cross-case frozen source",
                content_hash="sha256:cross-case-frozen",
                source_version="1",
                origin_mode="fixture",
            )
        )
    await savepoint.rollback()

    savepoint = await connection.begin_nested()
    with pytest.raises(IntegrityError):
        await connection.execute(
            insert(SourceSpanModel).values(
                id=uuid4(),
                workspace_id=workspace_id,
                decision_case_id=case_a,
                source_record_id=source_b_id,
                source_scope="pre_run",
                locator={"caseFieldPath": "decisionQuestion"},
                quote="Cross-case source span",
                quote_hash="sha256:cross-case-span",
            )
        )
    await savepoint.rollback()


@pytest.mark.asyncio
async def test_task_19a_source_span_locator_and_quote_constraints_are_enforced(
    connection: AsyncConnection,
) -> None:
    _, workspace_id, _ = await seed_user_and_workspaces(connection)
    subject_id = (
        await connection.execute(
            insert(DecisionSubject)
            .values(
                workspace_id=workspace_id,
                name="Span subject",
                slug=f"span-subject-{uuid4()}",
            )
            .returning(DecisionSubject.id)
        )
    ).scalar_one()
    case_id = await seed_case(connection, workspace_id, subject_id)
    source_id = uuid4()
    await connection.execute(
        insert(SourceRecordModel).values(
            id=source_id,
            workspace_id=workspace_id,
            decision_case_id=case_id,
            source_scope="pre_run",
            kind="human_input",
            canonical_uri="ludus://case/span-source",
            title="Span source",
            content_hash="sha256:span-source",
            source_version="1",
            origin_mode="fixture",
        )
    )

    for invalid_values in (
        {"locator": {}, "quote": "valid quote"},
        {"locator": {"caseFieldPath": "question"}, "quote": ""},
    ):
        savepoint = await connection.begin_nested()
        with pytest.raises(IntegrityError):
            await connection.execute(
                insert(SourceSpanModel).values(
                    id=uuid4(),
                    workspace_id=workspace_id,
                    decision_case_id=case_id,
                    source_record_id=source_id,
                    source_scope="pre_run",
                    quote_hash="sha256:invalid-span",
                    **invalid_values,
                )
            )
        await savepoint.rollback()


@pytest.mark.asyncio
async def test_task_19a_simulation_replay_numeric_constraints_are_enforced(
    connection: AsyncConnection,
) -> None:
    _, workspace_id, _ = await seed_user_and_workspaces(connection)
    subject_id = (
        await connection.execute(
            insert(DecisionSubject)
            .values(
                workspace_id=workspace_id,
                name="Simulation subject",
                slug=f"simulation-subject-{uuid4()}",
            )
            .returning(DecisionSubject.id)
        )
    ).scalar_one()
    case_id = await seed_case(connection, workspace_id, subject_id)

    base_values = {
        "id": uuid4(),
        "workspace_id": workspace_id,
        "decision_case_id": case_id,
        "graph_id": uuid4(),
        "graph_version_id": uuid4(),
        "strategy_version_id": uuid4(),
        "scenario_version_id": uuid4(),
        "score_definition_id": uuid4(),
        "score_definition_version": "1.0.0",
        "decision_maker_profile_id": uuid4(),
        "decision_maker_profile_version": 1,
        "risk_tolerance": 0.5,
        "engine_version": "1.0.0",
        "scenario_id": uuid4(),
        "simulation_mode": "formal",
        "epsilon": 0.001,
        "max_steps": 20,
        "steps": 10,
        "input_hash": "sha256:simulation-input",
        "node_results": {"outcome-1": 0.5},
        "option_scores": [{"optionId": "option-1", "score": 0.5}],
        "top_drivers": [{"nodeId": "driver-1", "scoreDelta": 0.1}],
        "recommendation_shift": "No change",
        "convergence_status": "converged",
        "origin_modes": ["fixture"],
    }
    await connection.execute(insert(SimulationRunModel).values(base_values))

    for overrides in (
        {"steps": 21},
        {"risk_tolerance": -0.01},
        {"risk_tolerance": 1.01},
        {"epsilon": 0},
        {"epsilon": float("inf")},
        {"max_steps": 0},
        {"decision_maker_profile_version": 0},
    ):
        invalid_values = {**base_values, "id": uuid4(), **overrides}
        savepoint = await connection.begin_nested()
        with pytest.raises(IntegrityError):
            await connection.execute(insert(SimulationRunModel).values(invalid_values))
        await savepoint.rollback()


@pytest.mark.asyncio
async def test_task_19a_signoff_expiry_and_signed_timestamp_constraints_are_enforced(
    connection: AsyncConnection,
) -> None:
    user_id, workspace_id, _ = await seed_user_and_workspaces(connection)
    subject_id = (
        await connection.execute(
            insert(DecisionSubject)
            .values(
                workspace_id=workspace_id,
                name="Signoff subject",
                slug=f"signoff-subject-{uuid4()}",
            )
            .returning(DecisionSubject.id)
        )
    ).scalar_one()
    case_id = await seed_case(connection, workspace_id, subject_id)
    issued_at = datetime(2026, 7, 23, 12, 0, tzinfo=timezone.utc)
    base_values = {
        "id": uuid4(),
        "workspace_id": workspace_id,
        "decision_case_id": case_id,
        "requested_by_user_id": user_id,
        "payload": {"caseVersion": 1},
        "payload_hash": "sha256:signoff",
        "status": "pending",
        "nonce_hash": "sha256:nonce",
        "nonce_issued_at": issued_at,
        "expires_at": issued_at + timedelta(hours=1),
    }
    await connection.execute(insert(SignoffRequestModel).values(base_values))

    for overrides in (
        {"expires_at": issued_at},
        {"status": "signed", "signed_at": None},
    ):
        invalid_values = {**base_values, "id": uuid4(), **overrides}
        savepoint = await connection.begin_nested()
        with pytest.raises(IntegrityError):
            await connection.execute(insert(SignoffRequestModel).values(invalid_values))
        await savepoint.rollback()

@pytest.mark.asyncio
async def test_task_19a_human_and_case_sources_cannot_persist_raw_artifacts(
    connection: AsyncConnection,
) -> None:
    _, workspace_id, _ = await seed_user_and_workspaces(connection)
    subject_id = (
        await connection.execute(
            insert(DecisionSubject)
            .values(
                workspace_id=workspace_id,
                name="Raw artifact subject",
                slug=f"raw-artifact-subject-{uuid4()}",
            )
            .returning(DecisionSubject.id)
        )
    ).scalar_one()
    decision_case_id = await seed_case(connection, workspace_id, subject_id)

    for source_kind in ("human_input", "case_snapshot"):
        savepoint = await connection.begin_nested()
        try:
            with pytest.raises(IntegrityError):
                await connection.execute(
                    insert(SourceRecordModel).values(
                        id=uuid4(),
                        workspace_id=workspace_id,
                        decision_case_id=decision_case_id,
                        source_scope="pre_run",
                        kind=source_kind,
                        raw_artifact_id=uuid4(),
                        canonical_uri=f"ludus://case/fabricated-{source_kind}",
                        title="Fabricated raw artifact reference",
                        content_hash="sha256:fabricated",
                        source_version="1",
                        origin_mode="fixture",
                    )
                )
        finally:
            await savepoint.rollback()


@pytest.mark.asyncio
async def test_task_19a_run_supersession_cannot_cross_decision_cases(
    connection: AsyncConnection,
) -> None:
    _, workspace_id, _ = await seed_user_and_workspaces(connection)
    subject_a, subject_b = await seed_subject_pair(connection, workspace_id)
    case_a = await seed_case(connection, workspace_id, subject_a)
    case_b = await seed_case(connection, workspace_id, subject_b)
    run_a = await seed_analysis_run(connection, workspace_id, case_a)
    run_b = await seed_analysis_run(connection, workspace_id, case_b)

    savepoint = await connection.begin_nested()
    try:
        with pytest.raises(IntegrityError):
            await connection.execute(
                update(AnalysisRun)
                .where(AnalysisRun.analysis_run_id == run_a)
                .values(superseded_by_analysis_run_id=run_b)
            )
    finally:
        await savepoint.rollback()
