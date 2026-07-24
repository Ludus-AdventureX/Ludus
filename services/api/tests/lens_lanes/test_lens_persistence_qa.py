"""QA probes for the StrategicLensArtifact write path (qa_release-owned).

Adversarial additions on top of the lane-authored suite: the double-ready
concurrency shape, canonical content-hash determinism under key reordering,
and origin-mode dedup/enum discipline. Self-contained seeds; product source is
never modified by this QA lane.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.models import AnalysisRun, DecisionCase, DecisionSubject, StrategicLensArtifact, User, Workspace
from app.strategic_lenses.repository import (
    FrozenReferenceLedger,
    LensPersistenceError,
    apply_validation_verdict,
    canonical_content_hash,
    persist_lens_stage_output,
)
from app.types import OriginMode, StrategicLensArtifactStatus

REPO_ROOT = Path(__file__).resolve().parents[4]
PRE_MORTEM_EXPECTED = (
    REPO_ROOT / "fixtures" / "spherical-robot" / "expected" / "strategic-lenses" / "pre_mortem.json"
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


async def _seed_run_context(connection: AsyncConnection) -> tuple[object, object, object]:
    user_id = (
        await connection.execute(
            insert(User)
            .values(email=f"qa-lens-{uuid4()}@example.invalid", password_hash="not-a-real-hash")
            .returning(User.id)
        )
    ).scalar_one()
    workspace_id = (
        await connection.execute(
            insert(Workspace)
            .values(name="QA Lens WS", created_by_user_id=user_id)
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
                title=f"QA Case {uuid4()}",
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
                idempotency_key=f"qa-lens-{uuid4()}",
            )
            .returning(AnalysisRun.analysis_run_id)
        )
    ).scalar_one()
    return workspace_id, case_id, run_id


@pytest.mark.asyncio
async def test_double_ready_never_yields_two_ready_rows(
    db_connection: AsyncConnection,
) -> None:
    """Two coexisting drafts must never both become ready.

    The partial unique index is the last line of defense. The accepted error
    contract is a stable domain error (LensPersistenceError family); a raw
    IntegrityError still protects integrity but is recorded as the documented
    P2 error-mapping gap - this probe accepts either so it keeps guarding the
    invariant after the owner fixes the mapping.
    """

    workspace_id, case_id, run_id = await _seed_run_context(db_connection)
    payload_a = _payload()
    payload_b = copy.deepcopy(payload_a)
    payload_b["content"]["verdictRationale"] = (
        payload_b["content"]["verdictRationale"] + " Divergent draft for QA probe."
    )
    ledger = _ledger_for(payload_a)

    draft_a = await persist_lens_stage_output(
        db_connection,
        workspace_id=workspace_id,
        decision_case_id=case_id,
        analysis_run_id=run_id,
        payload=payload_a,
        ledger=ledger,
    )
    draft_b = await persist_lens_stage_output(
        db_connection,
        workspace_id=workspace_id,
        decision_case_id=case_id,
        analysis_run_id=run_id,
        payload=payload_b,
        ledger=ledger,
    )
    assert draft_a.strategic_lens_artifact_id != draft_b.strategic_lens_artifact_id

    first = await apply_validation_verdict(
        db_connection,
        workspace_id=workspace_id,
        strategic_lens_artifact_id=draft_a.strategic_lens_artifact_id,
        accepted=True,
    )
    assert first is StrategicLensArtifactStatus.READY

    savepoint = await db_connection.begin_nested()
    with pytest.raises((LensPersistenceError, IntegrityError)):
        await apply_validation_verdict(
            db_connection,
            workspace_id=workspace_id,
            strategic_lens_artifact_id=draft_b.strategic_lens_artifact_id,
            accepted=True,
        )
    await savepoint.rollback()

    ready_count = (
        await db_connection.execute(
            select(func.count())
            .select_from(StrategicLensArtifact)
            .where(
                StrategicLensArtifact.analysis_run_id == run_id,
                StrategicLensArtifact.status == StrategicLensArtifactStatus.READY,
            )
        )
    ).scalar_one()
    assert ready_count == 1


def test_content_hash_is_deterministic_under_key_reordering() -> None:
    payload = _payload()
    reordered = json.loads(
        json.dumps({key: payload[key] for key in sorted(payload, reverse=True)})
    )
    assert canonical_content_hash(payload) == canonical_content_hash(reordered)
    mutated = copy.deepcopy(payload)
    mutated["content"]["failureHorizon"] = mutated["content"]["failureHorizon"] + " (x)"
    assert canonical_content_hash(payload) != canonical_content_hash(mutated)


@pytest.mark.asyncio
async def test_origin_modes_are_deduped_and_canonical(
    db_connection: AsyncConnection,
) -> None:
    workspace_id, case_id, run_id = await _seed_run_context(db_connection)
    payload = _payload()

    result = await persist_lens_stage_output(
        db_connection,
        workspace_id=workspace_id,
        decision_case_id=case_id,
        analysis_run_id=run_id,
        payload=payload,
        ledger=_ledger_for(payload),
        origin_modes=(OriginMode.FIXTURE, OriginMode.FIXTURE, OriginMode.LIVE),
    )
    row = (
        await db_connection.execute(
            select(StrategicLensArtifact.origin_modes).where(
                StrategicLensArtifact.strategic_lens_artifact_id
                == result.strategic_lens_artifact_id
            )
        )
    ).scalar_one()
    assert row == [OriginMode.FIXTURE, OriginMode.LIVE]
