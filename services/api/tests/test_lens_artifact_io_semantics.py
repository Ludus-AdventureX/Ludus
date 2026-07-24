"""Combined write→read semantics for the lens artifact IO integration (QA-owned).

Formalizes the integration candidate's five one-off probes: the persistence
write path (ways lane) and the read-only consumption path (case_api_data
lane) are exercised TOGETHER on the real migrated PostgreSQL. Skips cleanly
when either half is absent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

pytest.importorskip("app.strategic_lenses.repository", reason="write path absent")
pytest.importorskip("app.analyses.lens_artifact_reads", reason="read path absent")

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.analyses.lens_artifact_reads import StrategicLensArtifactReadService
from app.db import get_database_url
from app.models import AnalysisRun, DecisionCase, DecisionSubject, User, Workspace
from app.security.envelope import ApiFailure
from app.strategic_lenses.repository import (
    FrozenReferenceLedger,
    apply_validation_verdict,
    persist_lens_stage_output,
)
from app.tenancy.context import WorkspaceContext
from app.types import WorkspaceCapability, WorkspaceRole

REPO_ROOT = Path(__file__).resolve().parents[3]
PRE_MORTEM_EXPECTED = (
    REPO_ROOT
    / "fixtures"
    / "spherical-robot"
    / "expected"
    / "strategic-lenses"
    / "pre_mortem.json"
)


def _payload() -> dict[str, Any]:
    return json.loads(PRE_MORTEM_EXPECTED.read_text("utf-8"))


def _ledger_for(payload: dict[str, Any]) -> FrozenReferenceLedger:
    refs = payload["references"]
    return FrozenReferenceLedger(
        source_packet_ids=frozenset(refs.get("sourcePacketIds", ())),
        claim_ids=frozenset(refs.get("claimIds", ())),
        evidence_ids=frozenset(refs.get("evidenceIds", ())),
        assumption_ids=frozenset(refs.get("assumptionIds", ())),
        challenge_ids=frozenset(refs.get("challengeIds", ())),
    )


async def _seed_stack(connection: AsyncConnection) -> dict:
    user_id = (
        await connection.execute(
            insert(User)
            .values(email=f"qa-io-{uuid4()}@example.invalid", password_hash="not-a-real-hash")
            .returning(User.id)
        )
    ).scalar_one()
    workspace_id = (
        await connection.execute(
            insert(Workspace)
            .values(name="QA IO WS", created_by_user_id=user_id)
            .returning(Workspace.id)
        )
    ).scalar_one()
    subject_id = (
        await connection.execute(
            insert(DecisionSubject)
            .values(workspace_id=workspace_id, name="Robot", slug=f"robot-{uuid4()}")
            .returning(DecisionSubject.id)
        )
    ).scalar_one()
    case_id = (
        await connection.execute(
            insert(DecisionCase)
            .values(
                workspace_id=workspace_id,
                decision_subject_id=subject_id,
                title=f"QA IO Case {uuid4()}",
                decision_question="Rescue first or home first?",
            )
            .returning(DecisionCase.decision_case_id)
        )
    ).scalar_one()
    run_id = (
        await connection.execute(
            insert(AnalysisRun)
            .values(
                workspace_id=workspace_id,
                decision_case_id=case_id,
                charter_id=uuid4(),
                charter_version=1,
                run_manifest_id=uuid4(),
                run_manifest_hash="sha256:run-manifest",
                cynefin_gate_result_id=uuid4(),
                analysis_level="full",
                status="criticizing",
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
                idempotency_key=f"qa-io-{uuid4()}",
            )
            .returning(AnalysisRun.analysis_run_id)
        )
    ).scalar_one()
    return {"user": user_id, "ws": workspace_id, "case": case_id, "run": run_id}


def _context(stack: dict, *, capabilities=None) -> WorkspaceContext:
    return WorkspaceContext(
        user_id=stack["user"],
        workspace_id=stack["ws"],
        role=WorkspaceRole.OWNER,
        capabilities=(
            frozenset(WorkspaceCapability)
            if capabilities is None
            else frozenset(capabilities)
        ),
    )


@pytest.fixture
async def io_stack():
    """Committed stack + one session shared by writer and reader."""

    engine = create_async_engine(get_database_url(), poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = factory()
    try:
        stack = await _seed_stack(session)
        payload = _payload()
        artifact = await persist_lens_stage_output(
            session,
            workspace_id=stack["ws"],
            decision_case_id=stack["case"],
            analysis_run_id=stack["run"],
            payload=payload,
            ledger=_ledger_for(payload),
        )
        await session.commit()
        stack["artifact"] = artifact.strategic_lens_artifact_id
        stack["session"] = session
        stack["reader"] = StrategicLensArtifactReadService(session)
        yield stack
    finally:
        await session.close()
        await engine.dispose()


async def test_1_persisted_draft_is_invisible_to_ready_consumption(io_stack) -> None:
    reader = io_stack["reader"]
    context = _context(io_stack)
    views = await reader.list_ready_for_run(context, io_stack["case"], io_stack["run"])
    assert views == [], "a freshly persisted draft must not be consumable"
    with pytest.raises(ApiFailure) as excinfo:
        await reader.get_ready_artifact(
            context, io_stack["case"], io_stack["run"], io_stack["artifact"]
        )
    assert excinfo.value.code == "CASE_NOT_FOUND"


async def test_2_ready_verdict_makes_artifact_consumable(io_stack) -> None:
    session, reader = io_stack["session"], io_stack["reader"]
    await apply_validation_verdict(
        session,
        workspace_id=io_stack["ws"],
        strategic_lens_artifact_id=io_stack["artifact"],
        accepted=True,
    )
    await session.commit()
    context = _context(io_stack)
    views = await reader.list_ready_for_run(context, io_stack["case"], io_stack["run"])
    assert [v.strategic_lens_artifact_id for v in views] == [io_stack["artifact"]]
    view = await reader.get_ready_artifact(
        context, io_stack["case"], io_stack["run"], io_stack["artifact"]
    )
    assert view.strategic_lens_artifact_id == io_stack["artifact"]


async def test_3_rejected_verdict_is_audit_only(io_stack) -> None:
    session, reader = io_stack["session"], io_stack["reader"]
    await apply_validation_verdict(
        session,
        workspace_id=io_stack["ws"],
        strategic_lens_artifact_id=io_stack["artifact"],
        accepted=False,
    )
    await session.commit()
    context = _context(io_stack)
    assert await reader.list_ready_for_run(context, io_stack["case"], io_stack["run"]) == []
    with pytest.raises(ApiFailure):
        await reader.get_ready_artifact(
            context, io_stack["case"], io_stack["run"], io_stack["artifact"]
        )
    audit = await reader.list_for_audit(context, io_stack["case"])
    assert io_stack["artifact"] in {v.strategic_lens_artifact_id for v in audit}, (
        "review audit must retain the rejected artifact"
    )
    limited = _context(io_stack, capabilities=[WorkspaceCapability.CONTRIBUTE])
    with pytest.raises(ApiFailure) as denied:
        await reader.list_for_audit(limited, io_stack["case"])
    assert denied.value.code == "MEMBERSHIP_CAPABILITY_REQUIRED"


async def test_4_foreign_anchors_stay_uniform_404(io_stack) -> None:
    reader = io_stack["reader"]
    foreign_context = WorkspaceContext(
        user_id=uuid4(),
        workspace_id=uuid4(),  # attacker workspace that does not own the anchors
        role=WorkspaceRole.OWNER,
        capabilities=frozenset(WorkspaceCapability),
    )
    signatures = set()
    with pytest.raises(ApiFailure) as case_denied:
        await reader.list_ready_for_case(foreign_context, io_stack["case"])
    signatures.add((case_denied.value.code, case_denied.value.http_status))
    with pytest.raises(ApiFailure) as run_denied:
        await reader.list_ready_for_run(
            foreign_context, io_stack["case"], io_stack["run"]
        )
    signatures.add((run_denied.value.code, run_denied.value.http_status))
    with pytest.raises(ApiFailure) as get_denied:
        await reader.get_ready_artifact(
            foreign_context, io_stack["case"], io_stack["run"], io_stack["artifact"]
        )
    signatures.add((get_denied.value.code, get_denied.value.http_status))
    assert signatures == {("CASE_NOT_FOUND", 404)}, "no enumeration via foreign anchors"


async def test_5_persisted_id_reads_back_stably_under_full_anchor(io_stack) -> None:
    session, reader = io_stack["session"], io_stack["reader"]
    await apply_validation_verdict(
        session,
        workspace_id=io_stack["ws"],
        strategic_lens_artifact_id=io_stack["artifact"],
        accepted=True,
    )
    await session.commit()
    context = _context(io_stack)
    first = await reader.get_ready_artifact(
        context, io_stack["case"], io_stack["run"], io_stack["artifact"]
    )
    second = await reader.get_ready_artifact(
        context, io_stack["case"], io_stack["run"], io_stack["artifact"]
    )
    assert isinstance(first.strategic_lens_artifact_id, UUID)
    assert first.strategic_lens_artifact_id == second.strategic_lens_artifact_id
    assert first.content_hash == second.content_hash
    assert first.payload == second.payload
    assert first.claim_refs == second.claim_refs
