"""Regression tests for the three defects the live golden-path run exposed.

Each test pins one fact that was FALSE before this change:

- P0-A: the run advanced inside a single transaction, so nothing about it was
  observable until it finished (a run five minutes and six model calls deep
  still read ``queued / progress 0`` through the API). Stage boundaries are now
  commit boundaries, and the worker exposes the run it claimed so a failure can
  be parked precisely instead of re-claiming the queue head.
- P0-B: ``FIXTURE_MODE=true`` could not complete an analysis at all - every
  stage resolved to ``{}`` and the run was parked within seconds.
- P1: covered in test_analysis_sse_and_commands (stream closing set).

No network and no model key: the fixture path is deterministic by construction.
"""

from __future__ import annotations

import json

import pytest

from app.agents.model_provider import FixtureModelProvider, ModelMessage
from app.analyses.repository import AnalysisRuntimeRepository
from app.types import AnalysisRunStatus, FormalAnalysisLevel, OriginMode
from app.workers.analysis_worker import (
    AnalysisWorker,
    RoleExecutors,
    StageResult,
    build_role_executors_from_env,
    build_role_executors_from_model_provider,
)
from app.workers.fixture_stages import synthesize_stage_response

from runtime_world import make_queued_run

S = AnalysisRunStatus


def _passing_executors():
    """Stub executors that satisfy the deterministic gate at the validating stage."""

    async def executor(run, stage, inputs) -> StageResult:
        return StageResult(
            output={"stage": stage.value, "digest": {"headline": f"stage {stage.value}"}},
            quality_gate_passed=True if stage == S.VALIDATING else None,
        )

    return RoleExecutors(
        research=executor, critic=executor, synthesis=executor, validation=executor
    )


def _failing_at(target: AnalysisRunStatus):
    async def executor(run, stage, inputs) -> StageResult:
        if stage == target:
            raise RuntimeError(f"executor blew up during {stage.value}")
        return StageResult(
            output={"stage": stage.value},
            quality_gate_passed=True if stage == S.VALIDATING else None,
        )

    return RoleExecutors(
        research=executor, critic=executor, synthesis=executor, validation=executor
    )


async def test_every_stage_boundary_publishes_progress_before_the_run_ends(
    session, world
) -> None:
    """P0-A: progress/status must be published DURING the run, not only at the end.

    The recorder captures what a reader would see at each commit boundary. The
    pre-fix worker had exactly one boundary (after the terminal transition), so
    the observable sequence was 'queued' then 'ready' with nothing in between.
    """

    _, run = await make_queued_run(session, world, level=FormalAnalysisLevel.FOCUSED)
    repo = AnalysisRuntimeRepository(session)
    seen: list[tuple[str, float]] = []

    async def recording_checkpoint() -> None:
        current = await repo.get_run(world.workspace_id, run.analysis_run_id)
        assert current is not None
        seen.append((AnalysisRunStatus(current.status).value, float(current.progress)))
        await session.commit()

    worker = AnalysisWorker(
        session, executors=_passing_executors(), checkpoint=recording_checkpoint
    )
    claimed = await worker.run_once(workspace_id=world.workspace_id)
    assert claimed == run.analysis_run_id

    statuses = [status for status, _ in seen]
    progresses = [progress for _, progress in seen]

    # The claim itself is published: the run stops looking unclaimed at once.
    assert statuses[0] == S.PLANNING.value
    # Every executing stage is observable while the run is still in flight.
    for stage in (S.PLANNING, S.RETRIEVING, S.ANALYZING, S.CRITICIZING, S.SYNTHESIZING, S.VALIDATING):
        assert stage.value in statuses, f"{stage.value} was never observable"
    # Partial progress exists strictly before the terminal state - the exact
    # thing that was impossible before (progress jumped 0 -> 1 at the very end).
    mid = [p for status, p in seen if status not in {S.READY.value, S.BLOCKED.value}]
    assert any(0.0 < p < 1.0 for p in mid), f"no mid-run progress was published: {seen}"
    assert progresses[-1] == 1.0
    assert statuses[-1] == S.READY.value
    # Monotonic: a boundary never publishes a lower progress than a prior one.
    assert progresses == sorted(progresses)


async def test_claimed_run_is_exposed_and_parkable_in_place_after_a_failure(
    session, world, foreign_world
) -> None:
    """P0-A companion: precise parking replaces 're-claim the queue head'.

    Because earlier stages committed, the failed run is still sitting in its
    executing stage (NOT rolled back to queued), which is exactly why
    ``executing -> needs_attention`` is legal. The old strategy re-claimed the
    GLOBAL queue head with no workspace filter, so it could even have parked
    another tenant's queued run; the foreign run here pins that it does not.
    """

    _, run = await make_queued_run(session, world, level=FormalAnalysisLevel.FOCUSED)
    _, other = await make_queued_run(
        session, foreign_world, level=FormalAnalysisLevel.FOCUSED
    )
    worker = AnalysisWorker(session, executors=_failing_at(S.ANALYZING))

    with pytest.raises(RuntimeError):
        await worker.run_once(workspace_id=world.workspace_id)

    assert worker.claimed == (world.workspace_id, run.analysis_run_id)

    repo = AnalysisRuntimeRepository(session)
    failed = await repo.get_run(world.workspace_id, run.analysis_run_id)
    assert failed is not None
    assert AnalysisRunStatus(failed.status) == S.ANALYZING

    # The runner's park path: legal from an executing stage, and it targets the
    # claimed run only.
    await repo.transition(
        *worker.claimed,
        S.NEEDS_ATTENTION,
        payload={"reason": "worker_execution_error"},
    )
    parked = await repo.get_run(world.workspace_id, run.analysis_run_id)
    assert parked is not None
    assert AnalysisRunStatus(parked.status) == S.NEEDS_ATTENTION
    assert AnalysisRunStatus(parked.last_resumable_stage) == S.ANALYZING

    untouched = await repo.get_run(
        foreign_world.workspace_id, other.analysis_run_id
    )
    assert untouched is not None
    assert AnalysisRunStatus(untouched.status) == S.QUEUED


def _request(stage: str, role: str | None = None) -> list[ModelMessage]:
    inputs: dict[str, object] = {"analysisRunId": "fixture"}
    if role:
        inputs["roleOverride"] = role
    return [
        ModelMessage(
            role="user",
            content=json.dumps({"stage": stage, "inputs": inputs}, sort_keys=True),
        )
    ]


def test_fixture_stage_synthesizer_is_deterministic_and_survives_its_own_funnel() -> None:
    """P0-B: the key-free path needs stage content that can pass the real checks."""

    first = synthesize_stage_response(_request("retrieving"))
    second = synthesize_stage_response(_request("retrieving"))
    assert first == second, "fixture output must be byte-identical across calls"

    packets = first["packets"]
    assert len(packets) >= 3
    directions = {packet["direction"] for packet in packets}
    assert "opposing" in directions, "a fact base with no counter-fact is incomplete"
    for packet in packets:
        # The funnel drops conclusions under 15 chars or containing filler.
        assert len(packet["conclusion"]) >= 15
        assert packet["sources"] and packet["sources"][0]["name"]
        # Fixture facts must never claim a credible tier or invent a url.
        assert packet["sources"][0]["tier"] == "L6"
        assert "url" not in packet["sources"][0]

    # The influence edges must reference admitted factor labels, or admission
    # drops them and the sandbox graph stays empty.
    labels = {packet["factor"] for packet in packets}
    edges = first["output"]["influences"]
    assert edges
    for edge in edges:
        assert edge["from"] in labels and edge["to"] in labels

    # Stage-specific fields the deterministic gate and the asks require.
    assert synthesize_stage_response(_request("criticizing"))["output"]["strongestObjection"]
    assert synthesize_stage_response(_request("synthesizing"))["output"]["decision"]
    validating = synthesize_stage_response(_request("validating"))
    assert validating["qualityGatePassed"] is True
    assert validating["validatorFindings"] == []
    for role in ("safety_anchor", "chief_of_staff"):
        assert synthesize_stage_response(_request("criticizing", role))["output"]["digest"]

    # Nothing may pass for live analysis.
    for stage in ("planning", "retrieving", "analyzing", "criticizing", "synthesizing", "validating"):
        digest = synthesize_stage_response(_request(stage))["output"]["digest"]
        assert digest["headline"].startswith("[fixture]")

    # An unknown stage still yields a structurally valid envelope, never {}.
    unknown = synthesize_stage_response(_request("no-such-stage"))
    assert unknown["output"]["digest"]["headline"]


def test_environment_seam_binds_the_fixture_synthesizer(monkeypatch) -> None:
    """P0-B: FIXTURE_MODE must arrive pre-wired, not silently unusable."""

    monkeypatch.setenv("MODEL_PROVIDER", "fixture")
    monkeypatch.setenv("FIXTURE_MODE", "true")
    monkeypatch.delenv("MODEL_API_KEY", raising=False)

    executors, origin_mode = build_role_executors_from_env()
    assert origin_mode == OriginMode.FIXTURE
    assert executors.research is not None


async def test_fixture_mode_focused_run_reaches_ready_without_any_model_key(
    session, world, monkeypatch
) -> None:
    """P0-B end to end: this is the run that used to park within ~3 seconds.

    Everything real is exercised (repository, state machine, evidence funnel,
    deterministic quality gate, report hook); only the model call is replaced.
    """

    # No retrieval keys: the external leg must fail open, not fail the run.
    for key in ("EXA_API_KEY", "FIRECRAWL_API_KEY", "TAVILY_API_KEY", "MODEL_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    _, run = await make_queued_run(session, world, level=FormalAnalysisLevel.FOCUSED)
    provider = FixtureModelProvider(fallback=synthesize_stage_response)
    executors = build_role_executors_from_model_provider(provider)
    worker = AnalysisWorker(session, executors=executors, origin_mode=OriginMode.FIXTURE)

    claimed = await worker.run_once(workspace_id=world.workspace_id)
    assert claimed == run.analysis_run_id

    repo = AnalysisRuntimeRepository(session)
    final = await repo.get_run(world.workspace_id, run.analysis_run_id)
    assert final is not None
    assert AnalysisRunStatus(final.status) == S.READY, (
        f"key-free run did not reach ready: {final.status}"
    )
    assert float(final.progress) == 1.0
    assert OriginMode.FIXTURE.value in [
        mode.value if hasattr(mode, "value") else str(mode) for mode in final.origin_modes
    ]

    events = await repo.list_events_after(world.workspace_id, run.analysis_run_id, 0)
    types = [event.type for event in events]
    assert "analysis.ready" in types
    assert types.count("analysis.stage.completed") == 6
    # The digests the UI trace renders must actually be present.
    assert any("digest" in dict(event.payload) for event in events)

    # P0-C: a READY run must actually HAVE its report. The fixture evidence set
    # is entirely L6, so the funnel emits quality warnings - which used to be
    # written as bare strings into a dict-typed field, failing report
    # persistence silently and leaving `ready` with an empty report page.
    from sqlalchemy import func, select

    from app.reports.models import ReportArtifact

    report_count = await session.scalar(
        select(func.count())
        .select_from(ReportArtifact)
        .where(
            ReportArtifact.workspace_id == world.workspace_id,
            ReportArtifact.analysis_run_id == run.analysis_run_id,
        )
    )
    assert report_count == 1, "a READY run must have persisted its report"
