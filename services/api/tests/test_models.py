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

# Task 8/9 models live in their own modules but register on the shared Base;
# import them so the exact-table-set assertion is deterministic regardless of
# test selection (same pattern as migrations/env.py).
import app.analyses.models  # noqa: F401  (registers analysis runtime tables)
import app.evidence.models  # noqa: F401  (registers evidence ledger tables)
import app.analyses.claims  # noqa: F401  (registers claims + claim_evidence)
import app.analyses.devils_advocate  # noqa: F401  (registers challenges)
import app.analyses.quality_gate  # noqa: F401  (registers quality_gate_results)
import app.reports.models  # noqa: F401  (registers report/export artifacts)

# Task 4/5 companion table registers the same way; importing it here keeps the
# exact-table-set equality deterministic under any test selection (QA finding
# F2, codex/qa-task-04-05-backend-r1: co-running any dossiers test used to
# flip this assertion).
import app.dossiers.models  # noqa: F401  (registers dossier_version_snapshots)
from app.models import (
    AnalysisRun,
    CausalGraph,
    Conversation,
    DecisionCase,
    DecisionMakerProfile,
    DecisionSubject,
    DossierEntry,
    DossierVersion,
    GraphVersion,
    Initiative,
    Message,
    QuickAnalysisResult,
    ScenarioVersion,
    ScoreDefinition,
    SignoffRequest as SignoffRequestModel,
    SimulationRun as SimulationRunModel,
    SourceRecord as SourceRecordModel,
    SourceSpan as SourceSpanModel,
    StrategicLensArtifact,
    StrategyVersion,
    User,
    UserSession,
    Workspace,
    WorkspaceMembership,
)
from app.types import (
    DecisionLifecycleStage,
    EntryStatus,
    EvidenceVerdict,
    LensProducerRole,
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
        "workspace_invites",
        "mentor_reviews",
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
        "decision_records",
        "decision_reviews",
        "decision_lifecycle_events",
        # CCR-20260724-Ways-01: persisted five-lens outputs.
        "strategic_lens_artifacts",
        # CCR-20260724-SIM-01: canonical simulation graph contract.
        "causal_graphs",
        "graph_versions",
        "graph_nodes",
        "graph_edges",
        "strategy_versions",
        "scenario_versions",
        "score_definitions",
        "graph_branches",
        # CCR-20260724-SIM-02A P1+P3: frozen profiles + idempotency persistence.
        "decision_maker_profiles",
        "idempotency_records",
        # Task 8: evidence ledger & information quality gateway.
        "retrieval_tasks",
        "raw_artifacts",
        "quality_assessments",
        "evidence_items",
        "evidence_relations",
        # Task 9: persistent deep analysis state machine & worker.
        "analysis_charters",
        "analysis_events",
        "research_packets",
        "run_intervention_classifications",
        "run_resolutions",
        # Task 10: propositions & adversarial arc (claims ledger).
        "claims",
        "claim_evidence",
        "challenges",
        # Task 10: formal quality gate & report objects.
        "quality_gate_results",
        "report_artifacts",
        "export_artifacts",
        # Task 4/5: immutable dossier snapshot companion (migration a7c3e9f1b5d8).
        "dossier_version_snapshots",
        # BYOK connectors (migration b2c3d4e5f6a7 / c3d4e5f6a7b8).
        "workspace_connectors",
        # Grey-goo wave-2 (migration 2b2d34dacee0 / CCR-20260802-P2W2).
        "retrieval_coverage",
        "evidence_funnel_audits",
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


async def seed_simulation_reference_stack(
    connection: AsyncConnection, workspace_id, case_id
) -> dict:
    """Create the full legal SIM-01 reference stack in one workspace/case.

    Satisfies all four composite simulation_runs FKs (graph_version,
    strategy_version, scenario_version, score_definition) plus the scenario's
    source lens artifact FK, so replay tests exercise the real referential
    contract instead of random bare UUIDs (QA fix for CCR-20260724-SIM-01).
    """

    run_id = await seed_analysis_run(connection, workspace_id, case_id)
    lens_artifact_id = (
        await connection.execute(
            insert(StrategicLensArtifact)
            .values(
                strategic_lens_artifact_id=uuid4(),
                workspace_id=workspace_id,
                decision_case_id=case_id,
                analysis_run_id=run_id,
                charter_id=uuid4(),
                lens_type=StrategicLensType.SCENARIO_PLANNING,
                producer_role=LensProducerRole.SYNTHESIS,
                method_id="hardtech-market-direction",
                method_version="1.1.0",
                method_content_hash="sha256:method",
                prompt_version="1.0.0",
                schema_version="1.1.0",
                origin_modes=["fixture"],
                content_hash=f"sha256:lens-{uuid4().hex[:12]}",
                payload={"summary": "sim stack"},
                claim_refs=[],
                evidence_refs=[],
                assumption_refs=[],
            )
            .returning(StrategicLensArtifact.strategic_lens_artifact_id)
        )
    ).scalar_one()

    graph_id = (
        await connection.execute(
            insert(CausalGraph)
            .values(
                id=uuid4(),
                workspace_id=workspace_id,
                decision_case_id=case_id,
                report_artifact_id=uuid4(),
                title="Replay graph",
                origin_modes=["fixture"],
            )
            .returning(CausalGraph.id)
        )
    ).scalar_one()
    graph_version_id = (
        await connection.execute(
            insert(GraphVersion)
            .values(
                id=uuid4(),
                workspace_id=workspace_id,
                graph_id=graph_id,
                decision_case_id=case_id,
                case_version=1,
                source_report_artifact_id=uuid4(),
                version=1,
                status="confirmed",
                provenance=[],
                origin_modes=["fixture"],
                title="Replay graph v1",
                content_hash="sha256:graph-v1",
                created_by=uuid4(),
                confirmed_at=datetime.now(timezone.utc),
            )
            .returning(GraphVersion.id)
        )
    ).scalar_one()
    strategy_version_id = (
        await connection.execute(
            insert(StrategyVersion)
            .values(
                id=uuid4(),
                workspace_id=workspace_id,
                graph_id=graph_id,
                decision_case_id=case_id,
                version=1,
                option_id=uuid4(),
                node_overrides={},
                enabled_edge_ids=[],
            )
            .returning(StrategyVersion.id)
        )
    ).scalar_one()
    scenario_version_id = (
        await connection.execute(
            insert(ScenarioVersion)
            .values(
                id=uuid4(),
                workspace_id=workspace_id,
                graph_id=graph_id,
                decision_case_id=case_id,
                source_lens_artifact_id=lens_artifact_id,
                source_strategic_scenario_id="scenario-frame-1",
                scenario_id=uuid4(),
                version=1,
                name="Replay scenario",
                description="Deterministic replay scenario",
                default_edge_multiplier=1.0,
                edge_multipliers={},
                node_shifts={},
                strategy_survives=True,
                early_warning_signals=[],
                damping=0.8,
            )
            .returning(ScenarioVersion.id)
        )
    ).scalar_one()
    score_definition_id = (
        await connection.execute(
            insert(ScoreDefinition)
            .values(
                id=uuid4(),
                workspace_id=workspace_id,
                graph_id=graph_id,
                decision_case_id=case_id,
                version="1.0.0",
                option_outcome_mappings=[],
                risk_weights=[],
                constraint_rules=[],
                content_hash="sha256:score-v1",
            )
            .returning(ScoreDefinition.id)
        )
    ).scalar_one()
    # CCR-20260724-SIM-02A P1: simulation_runs now carries a composite FK to a
    # real frozen decision-maker profile row; replay fixtures must satisfy it.
    profile_user_id = (
        await connection.execute(
            insert(User)
            .values(
                email=f"sim-profile-{uuid4()}@example.invalid",
                password_hash="not-a-real-hash",
            )
            .returning(User.id)
        )
    ).scalar_one()
    profile_id = uuid4()
    profile_version = 1
    await connection.execute(
        insert(DecisionMakerProfile).values(
            id=uuid4(),
            workspace_id=workspace_id,
            profile_id=profile_id,
            decision_case_id=None,
            user_id=profile_user_id,
            display_name="Replay profile v1",
            version=profile_version,
            preference_weights={},
            risk_tolerance=0.5,
            content_hash=f"sha256:profile-{uuid4().hex[:12]}",
        )
    )
    return {
        "analysis_run": run_id,
        "lens_artifact": lens_artifact_id,
        "graph": graph_id,
        "graph_version": graph_version_id,
        "strategy_version": strategy_version_id,
        "scenario_version": scenario_version_id,
        "score_definition": score_definition_id,
        "profile": profile_id,
        "profile_version": profile_version,
    }


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
    refs = await seed_simulation_reference_stack(connection, workspace_id, case_id)

    base_values = {
        "id": uuid4(),
        "workspace_id": workspace_id,
        "decision_case_id": case_id,
        "graph_id": refs["graph"],
        "graph_version_id": refs["graph_version"],
        "strategy_version_id": refs["strategy_version"],
        "scenario_version_id": refs["scenario_version"],
        "score_definition_id": refs["score_definition"],
        "score_definition_version": "1.0.0",
        # SIM-02A P1: base insert must reference the seeded frozen profile;
        # ghost profile refs are now their own FK negative, not fixture noise.
        "decision_maker_profile_id": refs["profile"],
        "decision_maker_profile_version": refs["profile_version"],
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
        {"epsilon": float("nan")},
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

    for relation_field in (
        "supersedes_analysis_run_id",
        "superseded_by_analysis_run_id",
    ):
        savepoint = await connection.begin_nested()
        try:
            with pytest.raises(IntegrityError):
                await connection.execute(
                    update(AnalysisRun)
                    .where(AnalysisRun.analysis_run_id == run_a)
                    .values(**{relation_field: run_b})
                )
        finally:
            await savepoint.rollback()
