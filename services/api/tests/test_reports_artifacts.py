"""Task 10 owner tests: report/export artifacts and their guard surface (r1).

Covers the 06 报告对象 discriminant (focused->brief FocusedResearchResult,
full->detailed StructuredReport), report idempotency (same hash replays the
original row, a different hash conflicts and PRESERVES the original), the
double-layer ready-row immutability (repository rejection + database trigger,
for report_artifacts AND the pre-existing strategic_lens_artifacts), and the
blocked-run refusal surface (publication, PDF/HTML export, formal simulation).
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.analyses.repository import AnalysisRuntimeRepository
from app.analyses.synthesis import (
    ExportNotAllowed,
    ReportArtifactConflict,
    ReportArtifactImmutable,
    ReportPublicationBlocked,
    build_report_validation,
    canonical_report_hash,
    create_export_artifact,
    delete_report_artifact,
    persist_report_artifact,
    publish_report_artifact,
    update_report_artifact,
)
from app.db import get_database_url
from app.models import (
    DecisionCase,
    DecisionSubject,
    StrategicLensArtifact,
    User,
    Workspace,
    WorkspaceMembership,
)
from app.reports.models import ReportArtifact
from app.types import (
    AnalysisRunStatus,
    FormalAnalysisLevel,
    LensProducerRole,
    StrategicLensArtifactStatus,
    StrategicLensType,
    WorkspaceRole,
)

S = AnalysisRunStatus
FULL_SET = [lens.value for lens in StrategicLensType]


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def seed_run_world(
    factory,
    *,
    level: FormalAnalysisLevel = FormalAnalysisLevel.FOCUSED,
    to_status: S = S.VALIDATING,
):
    slug = f"t10r-{uuid4().hex[:10]}"
    async with factory() as session:
        ws_id, user_id, subject_id, case_id = uuid4(), uuid4(), uuid4(), uuid4()
        session.add(User(id=user_id, email=f"{slug}@example.test", password_hash="x"))
        await session.flush()
        session.add(Workspace(id=ws_id, name=f"ws-{slug}", created_by_user_id=user_id))
        await session.flush()
        session.add(
            WorkspaceMembership(
                id=uuid4(), workspace_id=ws_id, user_id=user_id, role=WorkspaceRole.OWNER
            )
        )
        session.add(
            DecisionSubject(id=subject_id, workspace_id=ws_id, name=f"s-{slug}", slug=slug)
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
        repo = AnalysisRuntimeRepository(session)
        charter = await repo.create_charter_draft(
            workspace_id=ws_id,
            decision_subject_id=subject_id,
            decision_case_id=case_id,
            case_version=1,
            case_snapshot_hash="sha256:case",
            analysis_level=level,
            decision_question="enter the rescue market?",
            dossier_snapshot_version=1,
            dossier_snapshot_hash="sha256:dossier",
            method_id="hardtech-market-direction",
            method_version="1.1.0",
            method_content_hash="sha256:method",
            formal_analysis_allowed=True,
            required_strategic_lens_types=(
                list(FULL_SET) if level is FormalAnalysisLevel.FULL else []
            ),
            allowed_connector_ids=["exa"],
            budget={"max_model_calls": 20},
        )
        await repo.submit_charter(ws_id, charter.id)
        await repo.confirm_charter(ws_id, charter.id)
        run, created = await repo.create_queued_run(
            workspace_id=ws_id,
            charter_id=charter.id,
            idempotency_key=f"run-{uuid4().hex[:12]}",
            run_manifest_hash="sha256:manifest",
            cynefin_gate_result_id=uuid4(),
        )
        assert created
        run_id = run.analysis_run_id
        for stage in [S.PLANNING, S.RETRIEVING, S.ANALYZING, S.CRITICIZING,
                      S.SYNTHESIZING, S.VALIDATING, S.READY]:
            if stage is S.READY and to_status is not S.READY:
                break
            await repo.transition(
                ws_id, run_id, stage, quality_gate_passed=(stage is S.READY)
            )
            if stage is to_status:
                break
        await session.commit()
    return ws_id, case_id, charter.id, run_id


def quality_block() -> dict:
    return {
        "evidenceAvailability": "sufficient",
        "claimSupport": "supported",
        "assumptionStability": "stable",
        "causalReliability": "confirmed",
        "strategicRobustness": "robust",
        "processQuality": "passed",
        "weakestDimension": "assumption_stability",
        "rationale": ["all four checks passed"],
    }


def recommendation_block() -> dict:
    return {
        "outcome": {"kind": "option", "optionId": "option-rescue-market"},
        "alternativeOptionIds": ["option-home-service-market"],
        "summary": "Advance the rescue pilot under the stated conditions.",
        "conditions": ["six rescue-agency interviews within four weeks"],
        "thresholds": [
            {
                "metric": "procurement cycle",
                "operator": "<=",
                "value": "12 months",
                "actionIfMissed": "stop the pilot and return to research",
            }
        ],
        "exitCriteria": ["procurement cycle exceeds the cash window"],
        "risks": ["tender delays"],
        "fragileAssumptionIds": ["asm-sr-001"],
        "leadingIndicators": [
            {
                "id": "li-001",
                "metric": "pilot intents",
                "expectedDirection": "up",
                "threshold": ">= 2 signed",
                "checkCadence": "weekly",
            }
        ],
        "nextActions": [
            {
                "id": "act-001",
                "text": "book rescue-agency interviews",
                "owner": "founder",
                "dueAt": "2026-08-15",
                "status": "open",
            }
        ],
        "reviewDate": "2026-10-15",
        "quality": quality_block(),
    }


def brief_block() -> dict:
    return {
        "decision": "Pursue the rescue market pilot first.",
        "whyNow": "Procurement standards are tightening within the cash window.",
        "conditions": ["six rescue-agency interviews within four weeks"],
        "thresholds": [],
        "exitCriteria": ["procurement cycle exceeds the cash window"],
        "reviewDate": "2026-10-15",
    }


_QUALITY_GATE_BLOCK = build_report_validation(passed=True)


def focused_document() -> dict:
    return {
        "schemaVersion": "report-1.0.0",
        "methodId": "hardtech-market-direction",
        "methodVersion": "1.1.0",
        "methodContentHash": "sha256:method",
        "executiveBrief": brief_block(),
        "recommendation": recommendation_block(),
        "evidenceReview": {
            "evidenceIds": ["ev-sr-001"],
            "conflictGroupIds": [],
            "freshnessWarnings": [],
            "reconciliationFindings": [],
        },
        "counterArguments": [
            {
                "id": "ch-001",
                "category": "counterargument",
                "text": "Home-service demand may outgrow rescue budgets.",
                "severity": "high",
                "affectedOptionIds": ["option-rescue-market"],
                "evidenceIds": ["ev-sr-002"],
                "mitigation": "revisit at the review date",
                "status": "confirmed",
            }
        ],
        "residualUncertainty": [
            {
                "id": "unk-001",
                "question": "Will certification land within 12 months?",
                "priority": "high",
                "status": "open",
            }
        ],
        "qualityGate": dict(_QUALITY_GATE_BLOCK),
        "originModes": ["fixture"],
    }


def structured_document(lens_ids: list[str]) -> dict:
    section = {
        "title": "Situation",
        "summary": "Two candidate markets with different force profiles.",
        "claimIds": ["claim-sr-001"],
        "evidenceIds": ["ev-sr-001"],
    }
    return {
        **focused_document(),
        "situation": section,
        "sections": [section],
        "options": [
            {
                "optionId": "option-rescue-market",
                "summary": "Focused rescue niche entry.",
                "benefits": ["high entry barriers protect the niche"],
                "risks": ["tender delays"],
            }
        ],
        "lensArtifactIds": lens_ids,
        "simulationSeeds": {"candidateNodes": [], "candidateEdges": []},
        "appendix": [],
    }


async def persist(factory, world, document):
    ws_id, case_id, _, run_id = world
    async with factory() as session:
        report = await persist_report_artifact(
            session,
            workspace_id=ws_id,
            decision_case_id=case_id,
            analysis_run_id=run_id,
            source_judgment_set_id=uuid4(),
            source_dissent_record_id=uuid4(),
            case_version=1,
            content=document,
            validation=build_report_validation(passed=True),
        )
        await session.commit()
        return report.id, report.content_hash, report.type


# --- level discriminant ---------------------------------------------------------


async def test_focused_run_persists_brief_focused_result(factory):
    world = await seed_run_world(factory)
    report_id, content_hash, report_type = await persist(factory, world, focused_document())
    assert report_type == "brief"
    assert content_hash.startswith("sha256:")
    assert report_id is not None


async def test_full_run_persists_detailed_structured_report(factory):
    world = await seed_run_world(factory, level=FormalAnalysisLevel.FULL)
    lens_ids = [str(uuid4()) for _ in range(5)]
    _, _, report_type = await persist(factory, world, structured_document(lens_ids))
    assert report_type == "detailed"


async def test_focused_content_with_lens_ids_is_rejected(factory):
    world = await seed_run_world(factory)
    smuggled = focused_document()
    smuggled["lensArtifactIds"] = [str(uuid4()) for _ in range(5)]
    with pytest.raises(Exception):  # extra="forbid" refuses the smuggled key
        await persist(factory, world, smuggled)


async def test_structured_report_requires_exactly_five_distinct_lens_ids(factory):
    world = await seed_run_world(factory, level=FormalAnalysisLevel.FULL)
    four = structured_document([str(uuid4()) for _ in range(4)])
    with pytest.raises(Exception):
        await persist(factory, world, four)
    dup = str(uuid4())
    duplicated = structured_document([dup, dup] + [str(uuid4()) for _ in range(3)])
    with pytest.raises(Exception):
        await persist(factory, world, duplicated)


async def test_db_check_rejects_focused_detailed_pairing(factory):
    world = await seed_run_world(factory)
    ws_id, case_id, _, run_id = world
    async with factory() as session:
        session.add(
            ReportArtifact(
                id=uuid4(),
                workspace_id=ws_id,
                analysis_run_id=run_id,
                source_judgment_set_id=uuid4(),
                source_dissent_record_id=uuid4(),
                decision_case_id=case_id,
                case_version=1,
                analysis_level=FormalAnalysisLevel.FOCUSED,
                type="detailed",  # illegal pairing, DB CHECK must refuse
                structured_content={},
                content_hash="sha256:x",
                origin_modes=[],
                validation={},
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


# --- idempotency ---------------------------------------------------------------


async def test_same_content_hash_replays_the_original_row(factory):
    world = await seed_run_world(factory)
    document = focused_document()
    first_id, first_hash, _ = await persist(factory, world, document)
    second_id, second_hash, _ = await persist(factory, world, document)
    assert first_id == second_id and first_hash == second_hash


async def test_different_content_hash_conflicts_and_preserves_original(factory):
    world = await seed_run_world(factory)
    document = focused_document()
    first_id, first_hash, _ = await persist(factory, world, document)
    changed = focused_document()
    changed["executiveBrief"] = {**brief_block(), "decision": "A different decision."}
    with pytest.raises(ReportArtifactConflict):
        await persist(factory, world, changed)
    ws_id = world[0]
    async with factory() as session:
        row = (
            await session.execute(
                select(ReportArtifact).where(
                    ReportArtifact.workspace_id == ws_id,
                    ReportArtifact.id == first_id,
                )
            )
        ).scalar_one()
        assert row.content_hash == first_hash  # original untouched


async def test_canonical_report_hash_is_deterministic():
    document = {"b": 1, "a": [1, 2]}
    assert canonical_report_hash(document) == canonical_report_hash({"a": [1, 2], "b": 1})


# --- ready-row immutability (double layer) --------------------------------------


async def publish_ready_report(factory, world):
    ws_id = world[0]
    report_id, _, _ = await persist(factory, world, focused_document())
    async with factory() as session:
        await publish_report_artifact(
            session, workspace_id=ws_id, report_artifact_id=report_id,
            gate_status="passed",
        )
        await session.commit()
    return report_id


async def test_ready_report_update_and_delete_rejected_at_both_layers(factory):
    world = await seed_run_world(factory, to_status=S.READY)
    ws_id = world[0]
    report_id = await publish_ready_report(factory, world)

    # layer 1: repository refuses before touching the database
    async with factory() as session:
        with pytest.raises(ReportArtifactImmutable):
            await update_report_artifact(
                session, workspace_id=ws_id, report_artifact_id=report_id,
                values={"case_version": 2},
            )
        with pytest.raises(ReportArtifactImmutable):
            await delete_report_artifact(
                session, workspace_id=ws_id, report_artifact_id=report_id
            )

    # layer 2: a raw statement that bypasses the repository hits the trigger
    async with factory() as session:
        with pytest.raises(DBAPIError):
            await session.execute(
                update(ReportArtifact)
                .where(ReportArtifact.id == report_id)
                .values(case_version=2)
            )
    async with factory() as session:
        with pytest.raises(DBAPIError):
            await session.execute(
                delete(ReportArtifact).where(ReportArtifact.id == report_id)
            )


async def test_ready_lens_artifact_rows_hit_the_same_trigger(factory):
    world = await seed_run_world(factory, level=FormalAnalysisLevel.FULL)
    ws_id, case_id, charter_id, run_id = world
    artifact_id = uuid4()
    async with factory() as session:
        session.add(
            StrategicLensArtifact(
                strategic_lens_artifact_id=artifact_id,
                workspace_id=ws_id,
                decision_case_id=case_id,
                analysis_run_id=run_id,
                charter_id=charter_id,
                lens_type=StrategicLensType.PORTER_FIVE_FORCES,
                producer_role=LensProducerRole.RESEARCH,
                status=StrategicLensArtifactStatus.READY,
                method_id="hardtech-market-direction",
                method_version="1.1.0",
                method_content_hash="sha256:method",
                prompt_version="1.1.0",
                schema_version="1.1.0",
                origin_modes=[],
                content_hash="sha256:lens",
                payload={"content": {}},
                claim_refs=[],
                evidence_refs=[],
                assumption_refs=[],
                validation_accepted_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()
    async with factory() as session:
        with pytest.raises(DBAPIError):
            await session.execute(
                update(StrategicLensArtifact)
                .where(StrategicLensArtifact.strategic_lens_artifact_id == artifact_id)
                .values(content_hash="sha256:tampered")
            )
    async with factory() as session:
        with pytest.raises(DBAPIError):
            await session.execute(
                delete(StrategicLensArtifact).where(
                    StrategicLensArtifact.strategic_lens_artifact_id == artifact_id
                )
            )


# --- blocked-run refusal surface -------------------------------------------------


async def test_publication_blocked_when_gate_blocked_or_run_not_ready(factory):
    world = await seed_run_world(factory, to_status=S.VALIDATING)
    ws_id = world[0]
    report_id, _, _ = await persist(factory, world, focused_document())
    async with factory() as session:
        with pytest.raises(ReportPublicationBlocked):
            await publish_report_artifact(
                session, workspace_id=ws_id, report_artifact_id=report_id,
                gate_status="blocked",
            )
        with pytest.raises(ReportPublicationBlocked):
            await publish_report_artifact(
                session, workspace_id=ws_id, report_artifact_id=report_id,
                gate_status="passed",  # gate fine, but the run is not ready
            )


async def test_export_rejected_for_focused_level_and_blocked_gate(factory):
    focused_world = await seed_run_world(factory, to_status=S.READY)
    ws_id = focused_world[0]
    report_id = await publish_ready_report(factory, focused_world)
    async with factory() as session:
        # focused never exports, even when published and gate-passed
        with pytest.raises(ExportNotAllowed):
            await create_export_artifact(
                session, workspace_id=ws_id, report_artifact_id=report_id,
                export_type="pdf", renderer_version="r1", gate_status="passed",
            )

    full_world = await seed_run_world(
        factory, level=FormalAnalysisLevel.FULL, to_status=S.READY
    )
    full_ws = full_world[0]
    lens_ids = [str(uuid4()) for _ in range(5)]
    full_report_id, _, _ = await persist(factory, full_world, structured_document(lens_ids))
    async with factory() as session:
        # a blocked gate always disables PDF, even on a full detailed report
        with pytest.raises(ExportNotAllowed):
            await create_export_artifact(
                session, workspace_id=full_ws, report_artifact_id=full_report_id,
                export_type="pdf", renderer_version="r1", gate_status="blocked",
            )
        # unpublished draft cannot export either
        with pytest.raises(ReportPublicationBlocked):
            await create_export_artifact(
                session, workspace_id=full_ws, report_artifact_id=full_report_id,
                export_type="html", renderer_version="r1", gate_status="passed",
            )


async def test_full_ready_published_report_can_create_export(factory):
    world = await seed_run_world(factory, level=FormalAnalysisLevel.FULL, to_status=S.READY)
    ws_id = world[0]
    lens_ids = [str(uuid4()) for _ in range(5)]
    report_id, _, _ = await persist(factory, world, structured_document(lens_ids))
    async with factory() as session:
        await publish_report_artifact(
            session, workspace_id=ws_id, report_artifact_id=report_id,
            gate_status="passed",
        )
        export_id = await create_export_artifact(
            session, workspace_id=ws_id, report_artifact_id=report_id,
            export_type="pdf", renderer_version="r1", gate_status="passed",
        )
        await session.commit()
    assert export_id is not None
