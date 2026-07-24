"""StrategicLensArtifact write-path tests (Ways Persistence lane, DB-backed).

Covers server identity injection from the frozen run, model self-report
rejection, behavior-gate fail-closed (nothing persisted), frozen-ledger
reference resolution, uniform cross-tenant not-found, idempotent re-submission,
ready-conflict protection, and the Validation verdict wiring
draft -> ready/rejected with immutability afterwards.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.agents.errors import ServerOwnedFieldError
from app.agents.lenses import LENS_OUTPUT_SCHEMA_ID
from app.models import AnalysisRun, DecisionCase, DecisionSubject, StrategicLensArtifact, User, Workspace
from app.strategic_lenses.repository import (
    FrozenReferenceLedger,
    LensArtifactConflict,
    LensArtifactImmutable,
    LensBehaviorRejected,
    LensReferenceResolutionError,
    LensRunNotFound,
    LensRunNotWritable,
    apply_validation_verdict,
    persist_lens_stage_output,
)
from app.types import LensProducerRole, StrategicLensArtifactStatus, StrategicLensType

REPO_ROOT = Path(__file__).resolve().parents[4]
PRE_MORTEM_EXPECTED = (
    REPO_ROOT / "fixtures" / "spherical-robot" / "expected" / "strategic-lenses" / "pre_mortem.json"
)
PRE_MORTEM_NEGATIVE = (
    REPO_ROOT
    / "fixtures"
    / "spherical-robot"
    / "negative"
    / "strategic-lenses"
    / "pre_mortem_missing_top_risk_control.json"
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


async def _seed_workspace(connection: AsyncConnection) -> tuple[object, object]:
    user_id = (
        await connection.execute(
            insert(User)
            .values(email=f"lens-persist-{uuid4()}@example.invalid", password_hash="not-a-real-hash")
            .returning(User.id)
        )
    ).scalar_one()
    workspace_ids = (
        await connection.execute(
            insert(Workspace)
            .values(
                [
                    {"name": "Lens WS A", "created_by_user_id": user_id},
                    {"name": "Lens WS B", "created_by_user_id": user_id},
                ]
            )
            .returning(Workspace.id)
        )
    ).scalars().all()
    return workspace_ids[0], workspace_ids[1]


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


async def _seed_run(
    connection: AsyncConnection,
    workspace_id: object,
    decision_case_id: object,
    *,
    status: str = "criticizing",
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
                analysis_level="full",
                status=status,
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
                idempotency_key=f"lens-persist-{uuid4()}",
            )
            .returning(AnalysisRun.analysis_run_id)
        )
    ).scalar_one()


async def _artifact_count(connection: AsyncConnection, workspace_id) -> int:
    # Scoped to the test's own workspace: absolute global counts break the
    # moment any committed-data test (e.g. a real concurrency race) has run
    # against the same database. Every caller seeds a unique workspace, so a
    # workspace-scoped count expresses exactly the intended invariant while
    # staying immune to leftovers from earlier suites (QA isolation fix).
    return (
        await connection.execute(
            select(func.count())
            .select_from(StrategicLensArtifact)
            .where(StrategicLensArtifact.workspace_id == workspace_id)
        )
    ).scalar_one()


@pytest.mark.asyncio
async def test_persist_injects_server_identity_from_frozen_run(
    db_connection: AsyncConnection,
) -> None:
    workspace_id, _ = await _seed_workspace(db_connection)
    case_id = await _seed_case(db_connection, workspace_id)
    run_id = await _seed_run(db_connection, workspace_id, case_id)
    payload = _payload()

    result = await persist_lens_stage_output(
        db_connection,
        workspace_id=workspace_id,
        decision_case_id=case_id,
        analysis_run_id=run_id,
        payload=payload,
        ledger=_ledger_for(payload),
    )
    assert result.created is True
    assert result.status is StrategicLensArtifactStatus.DRAFT

    row = (
        await db_connection.execute(
            select(StrategicLensArtifact).where(
                StrategicLensArtifact.strategic_lens_artifact_id
                == result.strategic_lens_artifact_id
            )
        )
    ).one()
    assert row.workspace_id == workspace_id
    assert row.decision_case_id == case_id
    assert row.analysis_run_id == run_id
    assert row.lens_type == StrategicLensType.PRE_MORTEM
    assert row.producer_role == LensProducerRole.CRITIC
    assert row.method_id == "hardtech-market-direction"
    assert row.method_version == "1.1.0"
    assert row.method_content_hash == "sha256:method-pack"
    assert row.schema_version == LENS_OUTPUT_SCHEMA_ID.rsplit(":", 1)[-1]
    assert row.content_hash.startswith("sha256:")
    assert row.validation_accepted_at is None
    assert set(row.evidence_refs) == set(payload["references"]["evidenceIds"])


@pytest.mark.asyncio
async def test_persist_is_idempotent_for_identical_content(
    db_connection: AsyncConnection,
) -> None:
    workspace_id, _ = await _seed_workspace(db_connection)
    case_id = await _seed_case(db_connection, workspace_id)
    run_id = await _seed_run(db_connection, workspace_id, case_id)
    payload = _payload()
    ledger = _ledger_for(payload)

    first = await persist_lens_stage_output(
        db_connection,
        workspace_id=workspace_id,
        decision_case_id=case_id,
        analysis_run_id=run_id,
        payload=payload,
        ledger=ledger,
    )
    second = await persist_lens_stage_output(
        db_connection,
        workspace_id=workspace_id,
        decision_case_id=case_id,
        analysis_run_id=run_id,
        payload=_payload(),
        ledger=ledger,
    )
    assert second.created is False
    assert second.strategic_lens_artifact_id == first.strategic_lens_artifact_id
    assert await _artifact_count(db_connection, workspace_id) == 1


@pytest.mark.asyncio
async def test_self_reported_identity_fields_are_rejected_before_write(
    db_connection: AsyncConnection,
) -> None:
    workspace_id, _ = await _seed_workspace(db_connection)
    case_id = await _seed_case(db_connection, workspace_id)
    run_id = await _seed_run(db_connection, workspace_id, case_id)
    payload = _payload()
    payload["workspaceId"] = str(workspace_id)

    with pytest.raises(ServerOwnedFieldError):
        await persist_lens_stage_output(
            db_connection,
            workspace_id=workspace_id,
            decision_case_id=case_id,
            analysis_run_id=run_id,
            payload=payload,
            ledger=_ledger_for(_payload()),
        )
    assert await _artifact_count(db_connection, workspace_id) == 0


@pytest.mark.asyncio
async def test_behavior_gate_failure_persists_nothing(
    db_connection: AsyncConnection,
) -> None:
    workspace_id, _ = await _seed_workspace(db_connection)
    case_id = await _seed_case(db_connection, workspace_id)
    run_id = await _seed_run(db_connection, workspace_id, case_id)
    negative = json.loads(PRE_MORTEM_NEGATIVE.read_text("utf-8"))

    with pytest.raises(LensBehaviorRejected) as excinfo:
        await persist_lens_stage_output(
            db_connection,
            workspace_id=workspace_id,
            decision_case_id=case_id,
            analysis_run_id=run_id,
            payload=negative,
            ledger=_ledger_for(negative),
        )
    assert "PM_TOP_RISK_CONTROL_MISSING" in excinfo.value.reason_codes
    assert await _artifact_count(db_connection, workspace_id) == 0


@pytest.mark.asyncio
async def test_unresolved_frozen_reference_fails_closed(
    db_connection: AsyncConnection,
) -> None:
    workspace_id, _ = await _seed_workspace(db_connection)
    case_id = await _seed_case(db_connection, workspace_id)
    run_id = await _seed_run(db_connection, workspace_id, case_id)
    payload = _payload()
    ledger = _ledger_for(payload)
    incomplete = FrozenReferenceLedger(
        source_packet_ids=ledger.source_packet_ids,
        claim_ids=ledger.claim_ids,
        evidence_ids=frozenset(list(ledger.evidence_ids)[:-1]) if ledger.evidence_ids else frozenset(),
        assumption_ids=ledger.assumption_ids,
        challenge_ids=ledger.challenge_ids,
    )

    with pytest.raises(LensReferenceResolutionError):
        await persist_lens_stage_output(
            db_connection,
            workspace_id=workspace_id,
            decision_case_id=case_id,
            analysis_run_id=run_id,
            payload=payload,
            ledger=incomplete,
        )
    assert await _artifact_count(db_connection, workspace_id) == 0


@pytest.mark.asyncio
async def test_cross_workspace_run_is_uniform_not_found(
    db_connection: AsyncConnection,
) -> None:
    workspace_a, workspace_b = await _seed_workspace(db_connection)
    case_id = await _seed_case(db_connection, workspace_a)
    run_id = await _seed_run(db_connection, workspace_a, case_id)
    payload = _payload()

    with pytest.raises(LensRunNotFound):
        await persist_lens_stage_output(
            db_connection,
            workspace_id=workspace_b,
            decision_case_id=case_id,
            analysis_run_id=run_id,
            payload=payload,
            ledger=_ledger_for(payload),
        )
    # neither the attacker's workspace nor the anchor workspace gained a row
    assert await _artifact_count(db_connection, workspace_a) == 0
    assert await _artifact_count(db_connection, workspace_b) == 0


@pytest.mark.asyncio
async def test_terminal_run_status_rejects_writes(
    db_connection: AsyncConnection,
) -> None:
    workspace_id, _ = await _seed_workspace(db_connection)
    case_id = await _seed_case(db_connection, workspace_id)
    run_id = await _seed_run(db_connection, workspace_id, case_id, status="ready")
    payload = _payload()

    with pytest.raises(LensRunNotWritable):
        await persist_lens_stage_output(
            db_connection,
            workspace_id=workspace_id,
            decision_case_id=case_id,
            analysis_run_id=run_id,
            payload=payload,
            ledger=_ledger_for(payload),
        )


@pytest.mark.asyncio
async def test_validation_verdict_wiring_and_immutability(
    db_connection: AsyncConnection,
) -> None:
    workspace_id, workspace_b = await _seed_workspace(db_connection)
    case_id = await _seed_case(db_connection, workspace_id)
    run_id = await _seed_run(db_connection, workspace_id, case_id)
    payload = _payload()

    result = await persist_lens_stage_output(
        db_connection,
        workspace_id=workspace_id,
        decision_case_id=case_id,
        analysis_run_id=run_id,
        payload=payload,
        ledger=_ledger_for(payload),
    )

    # Foreign workspace cannot even see the artifact.
    with pytest.raises(LensRunNotFound):
        await apply_validation_verdict(
            db_connection,
            workspace_id=workspace_b,
            strategic_lens_artifact_id=result.strategic_lens_artifact_id,
            accepted=True,
        )

    status = await apply_validation_verdict(
        db_connection,
        workspace_id=workspace_id,
        strategic_lens_artifact_id=result.strategic_lens_artifact_id,
        accepted=True,
    )
    assert status is StrategicLensArtifactStatus.READY
    row = (
        await db_connection.execute(
            select(
                StrategicLensArtifact.status,
                StrategicLensArtifact.validation_accepted_at,
            ).where(
                StrategicLensArtifact.strategic_lens_artifact_id
                == result.strategic_lens_artifact_id
            )
        )
    ).one()
    assert row.status == StrategicLensArtifactStatus.READY
    assert row.validation_accepted_at is not None

    # Terminal artifacts never change again.
    with pytest.raises(LensArtifactImmutable):
        await apply_validation_verdict(
            db_connection,
            workspace_id=workspace_id,
            strategic_lens_artifact_id=result.strategic_lens_artifact_id,
            accepted=False,
        )


@pytest.mark.asyncio
async def test_ready_conflict_blocks_divergent_resubmission(
    db_connection: AsyncConnection,
) -> None:
    workspace_id, _ = await _seed_workspace(db_connection)
    case_id = await _seed_case(db_connection, workspace_id)
    run_id = await _seed_run(db_connection, workspace_id, case_id)
    payload = _payload()
    ledger = _ledger_for(payload)

    first = await persist_lens_stage_output(
        db_connection,
        workspace_id=workspace_id,
        decision_case_id=case_id,
        analysis_run_id=run_id,
        payload=payload,
        ledger=ledger,
    )
    await apply_validation_verdict(
        db_connection,
        workspace_id=workspace_id,
        strategic_lens_artifact_id=first.strategic_lens_artifact_id,
        accepted=True,
    )

    divergent = copy.deepcopy(payload)
    divergent["content"]["verdictRationale"] = (
        divergent["content"]["verdictRationale"] + " Amended narrative for divergence."
    )
    with pytest.raises(LensArtifactConflict):
        await persist_lens_stage_output(
            db_connection,
            workspace_id=workspace_id,
            decision_case_id=case_id,
            analysis_run_id=run_id,
            payload=divergent,
            ledger=ledger,
        )


@pytest.mark.asyncio
async def test_rejected_verdict_keeps_audit_row(
    db_connection: AsyncConnection,
) -> None:
    workspace_id, _ = await _seed_workspace(db_connection)
    case_id = await _seed_case(db_connection, workspace_id)
    run_id = await _seed_run(db_connection, workspace_id, case_id)
    payload = _payload()

    result = await persist_lens_stage_output(
        db_connection,
        workspace_id=workspace_id,
        decision_case_id=case_id,
        analysis_run_id=run_id,
        payload=payload,
        ledger=_ledger_for(payload),
    )
    status = await apply_validation_verdict(
        db_connection,
        workspace_id=workspace_id,
        strategic_lens_artifact_id=result.strategic_lens_artifact_id,
        accepted=False,
    )
    assert status is StrategicLensArtifactStatus.REJECTED
    assert await _artifact_count(db_connection, workspace_id) == 1
    row = (
        await db_connection.execute(
            select(StrategicLensArtifact.validation_accepted_at).where(
                StrategicLensArtifact.strategic_lens_artifact_id
                == result.strategic_lens_artifact_id
            )
        )
    ).scalar_one_or_none()
    assert row is None
