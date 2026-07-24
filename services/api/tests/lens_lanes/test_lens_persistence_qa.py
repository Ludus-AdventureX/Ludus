"""QA probes for the StrategicLensArtifact write path (qa_release-owned).

Adversarial additions on top of the lane-authored suite: the double-ready
concurrency shape, canonical content-hash determinism under key reordering,
and origin-mode dedup/enum discipline. Self-contained seeds; product source is
never modified by this QA lane.
"""

from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

from app.db import get_database_url

from app.models import AnalysisRun, DecisionCase, DecisionSubject, StrategicLensArtifact, User, Workspace
from app.strategic_lenses.repository import (
    FrozenReferenceLedger,
    LensArtifactConflict,
    LensArtifactImmutable,
    LensRunNotFound,
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

    Tightened for the QA-WAYS-PERSIST-001 fix (009e0df): the loser MUST get
    the stable domain error ``LensArtifactConflict`` - a raw IntegrityError
    is a failure - and the repository's internal savepoint must keep the
    caller's transaction healthy without any QA-side savepoint shielding.
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

    # No QA-side savepoint: the repository's internal savepoint must contain
    # the failure entirely (QA-WAYS-PERSIST-001 acceptance shape B).
    with pytest.raises(LensArtifactConflict) as excinfo:
        await apply_validation_verdict(
            db_connection,
            workspace_id=workspace_id,
            strategic_lens_artifact_id=draft_b.strategic_lens_artifact_id,
            accepted=True,
        )
    assert not isinstance(excinfo.value, IntegrityError), (
        "raw SQLAlchemy IntegrityError must never escape the write path"
    )

    # Savepoint health: the same caller transaction keeps working - both for
    # reads and for a subsequent successful write on the losing draft.
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
    assert ready_count == 1, "exactly one winner may hold the ready slot"

    rejected = await apply_validation_verdict(
        db_connection,
        workspace_id=workspace_id,
        strategic_lens_artifact_id=draft_b.strategic_lens_artifact_id,
        accepted=False,
    )
    assert rejected is StrategicLensArtifactStatus.REJECTED, (
        "the caller's transaction must remain usable after the contained conflict"
    )


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


# ---------------------------------------------------------------------------
# QA-WAYS-PERSIST-001 fix acceptance: rowcount fail-closed (shape C)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ghost_artifact_fails_closed_with_not_found(
    db_connection: AsyncConnection,
) -> None:
    """C: a vanished/unknown row must raise LensRunNotFound, never no-op."""

    workspace_id, _, _ = await _seed_run_context(db_connection)
    with pytest.raises(LensRunNotFound):
        await apply_validation_verdict(
            db_connection,
            workspace_id=workspace_id,
            strategic_lens_artifact_id=uuid4(),
            accepted=True,
        )


@pytest.mark.asyncio
async def test_terminal_artifact_is_immutable(db_connection: AsyncConnection) -> None:
    """C/D: verdicts on ready artifacts fail closed with LensArtifactImmutable."""

    workspace_id, case_id, run_id = await _seed_run_context(db_connection)
    payload = _payload()
    draft = await persist_lens_stage_output(
        db_connection,
        workspace_id=workspace_id,
        decision_case_id=case_id,
        analysis_run_id=run_id,
        payload=payload,
        ledger=_ledger_for(payload),
    )
    await apply_validation_verdict(
        db_connection,
        workspace_id=workspace_id,
        strategic_lens_artifact_id=draft.strategic_lens_artifact_id,
        accepted=True,
    )
    with pytest.raises(LensArtifactImmutable):
        await apply_validation_verdict(
            db_connection,
            workspace_id=workspace_id,
            strategic_lens_artifact_id=draft.strategic_lens_artifact_id,
            accepted=False,
        )


@pytest.mark.asyncio
async def test_concurrent_verdicts_on_one_draft_fail_closed_for_the_loser() -> None:
    """C: two real connections race one draft; the loser's guarded UPDATE hits
    rowcount 0 (or the terminal re-read) and MUST fail closed - silent success
    or returning a not-actually-ready artifact are forbidden outcomes.
    """

    engine = create_async_engine(get_database_url(), poolclass=NullPool)
    run_id = None
    try:
        async with engine.begin() as seed_connection:
            workspace_id, case_id, run_id = await _seed_run_context(seed_connection)
            payload = _payload()
            draft = await persist_lens_stage_output(
                seed_connection,
                workspace_id=workspace_id,
                decision_case_id=case_id,
                analysis_run_id=run_id,
                payload=payload,
                ledger=_ledger_for(payload),
            )

        async def one_racer() -> object:
            async with engine.connect() as racer:
                transaction = await racer.begin()
                try:
                    outcome = await apply_validation_verdict(
                        racer,
                        workspace_id=workspace_id,
                        strategic_lens_artifact_id=draft.strategic_lens_artifact_id,
                        accepted=True,
                    )
                    await transaction.commit()
                    return outcome
                except (LensArtifactImmutable, LensArtifactConflict) as exc:
                    await transaction.rollback()
                    return exc

        outcomes = await asyncio.gather(one_racer(), one_racer())
        winners = [o for o in outcomes if o is StrategicLensArtifactStatus.READY]
        losers = [
            o for o in outcomes if isinstance(o, (LensArtifactImmutable, LensArtifactConflict))
        ]
        assert len(winners) == 1, f"exactly one racer may win, got {outcomes!r}"
        assert len(losers) == 1, "the loser must receive a stable domain error"
        assert not isinstance(losers[0], IntegrityError)

        async with engine.connect() as verify:
            ready_count = (
                await verify.execute(
                    select(func.count())
                    .select_from(StrategicLensArtifact)
                    .where(
                        StrategicLensArtifact.analysis_run_id == run_id,
                        StrategicLensArtifact.status
                        == StrategicLensArtifactStatus.READY,
                    )
                )
            ).scalar_one()
        assert ready_count == 1, "database must end with exactly one ready row"
    finally:
        # Self-cleanup: this is the only test that must COMMIT real rows (a
        # genuine cross-connection race cannot be rollback-only). Remove them
        # so suites using unscoped global-count assertions stay unaffected.
        try:
            if run_id is not None:
                async with engine.begin() as cleanup:
                    await cleanup.execute(
                        delete(StrategicLensArtifact).where(
                            StrategicLensArtifact.analysis_run_id == run_id
                        )
                    )
        finally:
            await engine.dispose()
