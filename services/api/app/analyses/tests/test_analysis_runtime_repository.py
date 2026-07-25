"""Task 9 owner tests: durable runtime repository over the migrated schema."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.analyses.models import AnalysisEvent, RunResolution
from app.analyses.repository import (
    AnalysisRuntimeRepository,
    CharterImmutable,
    CharterNotConfirmed,
    RunAlreadyActive,
    RunAmendmentRequired,
    RunNotCancellable,
    RunNotResumable,
    RunResolutionInvalid,
)
from app.analyses.state_machine import InvalidCharter, InvalidTransition
from app.db import get_database_url
from app.models import AnalysisRun
from app.types import AnalysisRunStatus, FormalAnalysisLevel, OriginMode

from runtime_world import (
    FULL_SET,
    charter_values,
    make_confirmed_charter,
    make_queued_run,
    seed_runtime_world,
)

S = AnalysisRunStatus


# --- charter lifecycle ------------------------------------------------------------


async def test_confirmed_charter_is_immutable(session, world) -> None:
    charter = await make_confirmed_charter(session, world)
    repo = AnalysisRuntimeRepository(session)
    with pytest.raises(CharterImmutable):
        await repo.update_draft_charter(
            world.workspace_id, charter.id, decision_question="new question"
        )


async def test_focused_charter_with_lenses_fails_closed(session, world) -> None:
    repo = AnalysisRuntimeRepository(session)
    with pytest.raises(InvalidCharter):
        await repo.create_charter_draft(
            **charter_values(
                world,
                level=FormalAnalysisLevel.FOCUSED,
                required_strategic_lens_types=["porter_five_forces"],
            )
        )


async def test_full_charter_lens_set_normalized_and_db_checked(session, world) -> None:
    repo = AnalysisRuntimeRepository(session)
    shuffled = list(reversed(FULL_SET))
    charter = await repo.create_charter_draft(
        **charter_values(world, required_strategic_lens_types=shuffled)
    )
    assert charter.required_strategic_lens_types == FULL_SET
    # DB CHECK negative: a full charter with four lenses cannot be forced in.
    with pytest.raises(IntegrityError) as excinfo:
        async with session.begin_nested():
            await session.execute(
                text(
                    "UPDATE analysis_charters SET required_strategic_lens_types = "
                    "'[\"porter_five_forces\"]'::jsonb WHERE id = :id"
                ),
                {"id": str(charter.id)},
            )
    assert "lens_set_matches_level" in str(excinfo.value)


async def test_run_requires_confirmed_and_formal_allowed(session, world) -> None:
    repo = AnalysisRuntimeRepository(session)
    draft = await repo.create_charter_draft(**charter_values(world))
    with pytest.raises(CharterNotConfirmed):
        await repo.create_queued_run(
            workspace_id=world.workspace_id,
            charter_id=draft.id,
            idempotency_key="idem-draft",
            run_manifest_hash="sha256:m",
            cynefin_gate_result_id=uuid4(),
        )
    blocked = await make_confirmed_charter(
        session, world, formal_analysis_allowed=False
    )
    with pytest.raises(CharterNotConfirmed):
        await repo.create_queued_run(
            workspace_id=world.workspace_id,
            charter_id=blocked.id,
            idempotency_key="idem-blocked",
            run_manifest_hash="sha256:m",
            cynefin_gate_result_id=uuid4(),
        )


async def test_second_active_run_rejected_and_idempotent_replay(session, world) -> None:
    repo = AnalysisRuntimeRepository(session)
    charter, run = await make_queued_run(session, world, idempotency_key="idem-1")
    # Idempotent replay: same key returns the existing run.
    replay, created = await repo.create_queued_run(
        workspace_id=world.workspace_id,
        charter_id=charter.id,
        idempotency_key="idem-1",
        run_manifest_hash="sha256:manifest",
        cynefin_gate_result_id=uuid4(),
    )
    assert created is False
    assert replay.analysis_run_id == run.analysis_run_id
    # A different key while the first run is active: rejected with the
    # existing run id.
    with pytest.raises(RunAlreadyActive) as excinfo:
        await repo.create_queued_run(
            workspace_id=world.workspace_id,
            charter_id=charter.id,
            idempotency_key="idem-2",
            run_manifest_hash="sha256:manifest",
            cynefin_gate_result_id=uuid4(),
        )
    assert excinfo.value.existing_analysis_run_id == run.analysis_run_id


async def test_active_run_partial_unique_constraint_exists_in_db(session, world) -> None:
    rows = (
        await session.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE indexname = 'uq_analysis_runs_one_active_per_case'"
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert "UNIQUE" in rows[0].upper()
    assert "needs_attention" in rows[0]


async def test_replacement_charter_confirm_supersedes_and_cancels_old_run(
    session, world
) -> None:
    repo = AnalysisRuntimeRepository(session)
    charter, run = await make_queued_run(session, world)
    replacement = await repo.create_replacement_draft(
        world.workspace_id, charter.id, changes={"decision_question": "pivot?"}
    )
    assert replacement.status == "draft"
    assert replacement.replaces_charter_id == charter.id
    # Old confirmed charter stays valid until the replacement confirms.
    assert (await repo.get_charter(world.workspace_id, charter.id)).status == "confirmed"

    await repo.submit_charter(world.workspace_id, replacement.id)
    await repo.confirm_charter(world.workspace_id, replacement.id)

    old = await repo.get_charter(world.workspace_id, charter.id)
    assert old.status == "superseded"
    assert old.superseded_by_charter_id == replacement.id
    cancelled = await repo.get_run(world.workspace_id, run.analysis_run_id)
    assert AnalysisRunStatus(cancelled.status) == S.CANCELLED
    assert cancelled.cancellation_reason == "charter_replaced"


# --- transitions, events, hashes ----------------------------------------------------


async def test_transitions_write_events_with_increasing_sequence_and_hashes(
    session, world
) -> None:
    repo = AnalysisRuntimeRepository(session)
    _, run = await make_queued_run(session, world)
    ws, run_id = world.workspace_id, run.analysis_run_id

    await repo.transition(ws, run_id, S.PLANNING, stage_input={"plan": 1})
    await repo.record_stage_completed(
        ws, run_id, stage=S.PLANNING, output={"plan": "done"}, progress=0.14
    )
    await repo.transition(ws, run_id, S.RETRIEVING, stage_input={"queries": 2})

    events = await repo.list_events_after(ws, run_id, 0)
    sequences = [event.sequence for event in events]
    assert sequences == sorted(sequences)
    assert len(set(sequences)) == len(sequences)
    assert [event.type for event in events] == [
        "analysis.stage.started",
        "analysis.stage.completed",
        "analysis.stage.started",
    ]

    refreshed = await repo.get_run(ws, run_id)
    planning = refreshed.stage_results["planning"]
    assert planning["inputHash"].startswith("sha256:")
    assert planning["outputHash"].startswith("sha256:")
    assert refreshed.stage_results["retrieving"]["inputHash"].startswith("sha256:")


async def test_event_sequence_unique_constraint_in_db(session, world) -> None:
    repo = AnalysisRuntimeRepository(session)
    _, run = await make_queued_run(session, world)
    event = await repo.append_event(
        run, category="agent.status", type="analysis.stage.started", payload={}
    )
    async with session.begin_nested():
        session.add(
            AnalysisEvent(
                id=uuid4(),
                workspace_id=world.workspace_id,
                decision_case_id=world.case_id,
                analysis_run_id=run.analysis_run_id,
                sequence=event.sequence,
                category="agent.status",
                type="analysis.stage.started",
                origin_mode=OriginMode.FIXTURE,
                payload={},
            )
        )
        with pytest.raises(IntegrityError) as excinfo:
            await session.flush()
    assert "uq_analysis_events_workspace_run_sequence" in str(excinfo.value)


async def test_invalid_db_transition_is_rejected_and_nothing_written(
    session, world
) -> None:
    repo = AnalysisRuntimeRepository(session)
    _, run = await make_queued_run(session, world)
    with pytest.raises(InvalidTransition):
        await repo.transition(world.workspace_id, run.analysis_run_id, S.READY)
    events = await repo.list_events_after(world.workspace_id, run.analysis_run_id, 0)
    assert events == []


# --- cancellation --------------------------------------------------------------------


async def test_cancel_is_idempotent_and_keeps_events(session, world) -> None:
    repo = AnalysisRuntimeRepository(session)
    _, run = await make_queued_run(session, world)
    ws, run_id = world.workspace_id, run.analysis_run_id
    await repo.transition(ws, run_id, S.PLANNING)

    first = await repo.cancel(ws, run_id, reason="user_cancelled")
    assert AnalysisRunStatus(first.status) == S.CANCELLED
    events_after_first = await repo.list_events_after(ws, run_id, 0)

    second = await repo.cancel(ws, run_id, reason="user_cancelled")
    assert AnalysisRunStatus(second.status) == S.CANCELLED
    assert second.cancelled_at == first.cancelled_at
    events_after_second = await repo.list_events_after(ws, run_id, 0)
    # Idempotent: no new records on repeat.
    assert len(events_after_second) == len(events_after_first)
    assert events_after_second[-1].type == "analysis.cancelled"


async def test_ready_and_blocked_are_not_cancellable(session, world) -> None:
    repo = AnalysisRuntimeRepository(session)
    _, run = await make_queued_run(session, world)
    ws, run_id = world.workspace_id, run.analysis_run_id
    for stage in (S.PLANNING, S.RETRIEVING, S.ANALYZING, S.CRITICIZING,
                  S.SYNTHESIZING, S.VALIDATING):
        await repo.transition(ws, run_id, stage)
    await repo.transition(ws, run_id, S.BLOCKED)
    with pytest.raises(RunNotCancellable):
        await repo.cancel(ws, run_id)


# --- needs_attention: resolution vs amendment ----------------------------------------


async def _park_in_needs_attention(repo, world, run) -> None:
    ws, run_id = world.workspace_id, run.analysis_run_id
    await repo.transition(ws, run_id, S.PLANNING)
    await repo.transition(ws, run_id, S.RETRIEVING)
    await repo.transition(ws, run_id, S.NEEDS_ATTENTION)


async def test_resolution_resumes_to_last_resumable_stage_only(session, world) -> None:
    repo = AnalysisRuntimeRepository(session)
    _, run = await make_queued_run(session, world)
    await _park_in_needs_attention(repo, world, run)

    classification, resolution, record = await repo.classify_and_resolve(
        world.workspace_id,
        run.analysis_run_id,
        payload={
            "kind": "hard_constraint_confirmation",
            "confirmedConstraintIds": ["constraint_no_legal_advice"],
        },
        created_by=world.user_id,
    )
    assert classification.result == "resolution"
    assert classification.changed_frozen_fields == []
    assert record.to_status == S.RETRIEVING  # exactly lastResumableStage
    refreshed = await repo.get_run(world.workspace_id, run.analysis_run_id)
    assert AnalysisRunStatus(refreshed.status) == S.RETRIEVING
    assert refreshed.last_resumable_stage is None
    stored = await session.scalar(
        select(RunResolution).where(RunResolution.id == resolution.id)
    )
    assert stored is not None
    assert AnalysisRunStatus(stored.resume_stage) == S.RETRIEVING


async def test_lens_set_change_is_amendment_never_a_resolution(session, world) -> None:
    repo = AnalysisRuntimeRepository(session)
    _, run = await make_queued_run(session, world)
    await _park_in_needs_attention(repo, world, run)

    with pytest.raises(RunAmendmentRequired) as excinfo:
        await repo.classify_and_resolve(
            world.workspace_id,
            run.analysis_run_id,
            payload={"kind": "hard_constraint_confirmation", "confirmedConstraintIds": []},
            created_by=world.user_id,
            proposed_charter_changes={"strategic_lens_set": FULL_SET[:-1]},
        )
    assert excinfo.value.changed_frozen_fields == ["strategic_lens_set"]
    # The amendment classification is persisted; NO resolution was created and
    # the run stays parked.
    refreshed = await repo.get_run(world.workspace_id, run.analysis_run_id)
    assert AnalysisRunStatus(refreshed.status) == S.NEEDS_ATTENTION
    resolutions = (
        await session.scalars(
            select(RunResolution).where(
                RunResolution.analysis_run_id == run.analysis_run_id
            )
        )
    ).all()
    assert resolutions == []
    events = await repo.list_events_after(world.workspace_id, run.analysis_run_id, 0)
    assert events[-1].type == "analysis.amendment_required"


async def test_unknown_resolution_kind_fails_closed(session, world) -> None:
    repo = AnalysisRuntimeRepository(session)
    _, run = await make_queued_run(session, world)
    await _park_in_needs_attention(repo, world, run)
    with pytest.raises(RunResolutionInvalid):
        await repo.classify_and_resolve(
            world.workspace_id,
            run.analysis_run_id,
            payload={"kind": "budget_increase", "amount": 999},
            created_by=world.user_id,
        )


async def test_provider_recovery_only_within_charter_allowlist(session, world) -> None:
    repo = AnalysisRuntimeRepository(session)
    _, run = await make_queued_run(session, world)
    await _park_in_needs_attention(repo, world, run)
    with pytest.raises(RunResolutionInvalid):
        await repo.classify_and_resolve(
            world.workspace_id,
            run.analysis_run_id,
            payload={
                "kind": "provider_recovery",
                "action": "switch_allowed_connector",
                "connectorId": "not-in-allowlist",
            },
            created_by=world.user_id,
        )


async def test_resolution_rejected_outside_needs_attention(session, world) -> None:
    repo = AnalysisRuntimeRepository(session)
    _, run = await make_queued_run(session, world)
    with pytest.raises(RunNotResumable):
        await repo.classify_and_resolve(
            world.workspace_id,
            run.analysis_run_id,
            payload={"kind": "hard_constraint_confirmation", "confirmedConstraintIds": []},
            created_by=world.user_id,
        )


# --- heartbeat recovery ---------------------------------------------------------------


async def test_stale_heartbeat_moves_active_run_to_needs_attention(session, world) -> None:
    repo = AnalysisRuntimeRepository(session)
    _, run = await make_queued_run(session, world)
    ws, run_id = world.workspace_id, run.analysis_run_id
    await repo.transition(ws, run_id, S.PLANNING)
    await repo.transition(ws, run_id, S.RETRIEVING)
    # Simulate a crashed worker: heartbeat far in the past.
    await session.execute(
        update(AnalysisRun)
        .where(AnalysisRun.analysis_run_id == run_id)
        .values(heartbeat_at=text("now() - interval '1 hour'"))
    )
    recovered = await repo.recover_stale_runs(timeout=timedelta(seconds=120))
    assert run_id in recovered
    refreshed = await repo.get_run(ws, run_id)
    assert AnalysisRunStatus(refreshed.status) == S.NEEDS_ATTENTION
    assert AnalysisRunStatus(refreshed.last_resumable_stage) == S.RETRIEVING
    events = await repo.list_events_after(ws, run_id, 0)
    assert events[-1].type == "analysis.needs_attention"
    assert events[-1].payload["reason"] == "heartbeat_expired"


async def test_fresh_heartbeat_is_not_recovered(session, world) -> None:
    repo = AnalysisRuntimeRepository(session)
    _, run = await make_queued_run(session, world)
    await repo.transition(world.workspace_id, run.analysis_run_id, S.PLANNING)
    await repo.heartbeat(world.workspace_id, run.analysis_run_id)
    recovered = await repo.recover_stale_runs(timeout=timedelta(seconds=120))
    assert run.analysis_run_id not in recovered


# --- queue claim: FOR UPDATE SKIP LOCKED double-claim proof ---------------------------


async def test_concurrent_claims_never_double_claim() -> None:
    """Two committed sessions racing on one queued run: exactly one claims it.

    Uses committed data (SKIP LOCKED is invisible inside one rolled-back
    transaction), then cleans the tenant up via workspace CASCADE.
    """

    engine_a = create_async_engine(get_database_url(), pool_pre_ping=True)
    engine_b = create_async_engine(get_database_url(), pool_pre_ping=True)
    ws_id = None
    try:
        async with engine_a.connect() as conn_a:
            session_a = AsyncSession(bind=conn_a, expire_on_commit=False)
            world = await seed_runtime_world(session_a, f"c{uuid4().hex[:10]}")
            ws_id = world.workspace_id
            _, run = await make_queued_run(session_a, world)
            await session_a.commit()

            # Session A claims (uncommitted lock held).
            repo_a = AnalysisRuntimeRepository(session_a)
            claimed_a = await repo_a.claim_next_queued(workspace_id=world.workspace_id)
            assert claimed_a is not None
            assert claimed_a.analysis_run_id == run.analysis_run_id

            # Session B must skip the locked row instead of blocking/claiming.
            async with engine_b.connect() as conn_b:
                session_b = AsyncSession(bind=conn_b, expire_on_commit=False)
                repo_b = AnalysisRuntimeRepository(session_b)
                claimed_b = await repo_b.claim_next_queued(
                    workspace_id=world.workspace_id
                )
                assert claimed_b is None or (
                    claimed_b.analysis_run_id != run.analysis_run_id
                )
                await session_b.rollback()
            await session_a.commit()

            refreshed = await repo_a.get_run(world.workspace_id, run.analysis_run_id)
            assert AnalysisRunStatus(refreshed.status) == S.PLANNING
            await session_a.close()
    finally:
        if ws_id is not None:
            async with engine_a.begin() as cleanup:
                await cleanup.execute(
                    text("DELETE FROM workspaces WHERE id = :ws"), {"ws": str(ws_id)}
                )
        await engine_a.dispose()
        await engine_b.dispose()
