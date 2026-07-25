"""Task 9 owner tests: worker orchestration over stub role executors.

No model calls: role executors are deterministic stubs, the lens writer is a
recording stub (the default writer's identity with the shipped persistence
path is asserted separately). All state, events, and cancellation semantics
run against the real repository and migrated schema.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select

from app.analyses.models import ResearchPacket as ResearchPacketRow
from app.analyses.repository import AnalysisRuntimeRepository
from app.strategic_lenses.repository import (
    apply_validation_verdict,
    persist_lens_stage_output,
)
from app.types import AnalysisRunStatus, FormalAnalysisLevel
from app.workers import analysis_worker as worker_module
from app.workers.analysis_worker import (
    FULL_LENS_SCHEDULE,
    AnalysisWorker,
    LENS_VALIDATION_VERDICT,
    RoleExecutors,
    StageResult,
)

from runtime_world import make_queued_run

S = AnalysisRunStatus


def _stub_executors(*, quality_gate_passed: bool = True, with_lenses: bool = True):
    calls: list[tuple[str, str, str | None]] = []

    def make(role: str):
        async def executor(run, stage, inputs) -> StageResult:
            calls.append((role, stage.value, inputs.get("substage")))
            lens_payloads = {}
            if with_lenses and stage in FULL_LENS_SCHEDULE:
                lens_payloads = {
                    lens: {"lensType": lens, "content": {"stub": True}}
                    for lens in FULL_LENS_SCHEDULE[stage]
                }
            packets = ()
            if stage == S.ANALYZING and role == "research":
                packets = (
                    {
                        "factor": "rescue demand",
                        "conclusion": "conditional demand confirmed",
                        "claim_support_score": 0.64,
                    },
                )
            return StageResult(
                output={"role": role, "stage": stage.value},
                packets=packets,
                lens_payloads=lens_payloads,
                quality_gate_passed=(
                    quality_gate_passed if stage == S.VALIDATING else None
                ),
            )

        return executor

    executors = RoleExecutors(
        research=make("research"),
        critic=make("critic"),
        synthesis=make("synthesis"),
        validation=make("validation"),
    )
    return executors, calls


def _recording_lens_writer():
    written: list[str] = []

    async def writer(session, **kwargs) -> UUID:
        artifact_id = uuid4()
        written.append(kwargs["payload"]["lensType"])
        return artifact_id

    return writer, written


def _stub_lens_audit(*, ok: bool = True):
    """Recording audit stub (MOUNT-02 Addendum A1 §A1-⑥ binding tests).

    The stub records the referenced_artifact_ids EXACTLY as the worker passed
    them so the as-is (no parse/normalize/dedup/reorder) contract is pinned;
    the real audit's own semantics are covered by test_analysis_quality_gate.
    """

    from app.analyses.quality_gate import LensSetAudit

    calls: list[dict] = []

    async def audit(session, **kwargs) -> LensSetAudit:
        calls.append(dict(kwargs))
        return LensSetAudit(
            ok=ok,
            reason_codes=() if ok else ("strategic_lens_incomplete",),
            findings=(),
        )

    return audit, calls


async def test_full_run_pipeline_reaches_ready_with_five_lenses(session, world) -> None:
    _, run = await make_queued_run(session, world, level=FormalAnalysisLevel.FULL)
    executors, calls = _stub_executors()
    writer, written = _recording_lens_writer()
    audit, audit_calls = _stub_lens_audit(ok=True)
    worker = AnalysisWorker(
        session, executors=executors, lens_writer=writer, lens_audit=audit
    )

    claimed = await worker.run_once(workspace_id=world.workspace_id)
    assert claimed == run.analysis_run_id

    repo = AnalysisRuntimeRepository(session)
    refreshed = await repo.get_run(world.workspace_id, run.analysis_run_id)
    assert AnalysisRunStatus(refreshed.status) == S.READY
    # Five lenses, fixed role schedule, persisted ids recorded on the run.
    assert written == [
        "porter_five_forces",
        "counterparty_response_matrix",
        "pre_mortem",
        "scenario_planning",
        "meadows_leverage_points",
    ]
    assert len(refreshed.strategic_lens_artifact_ids) == 5
    # §A1-⑥ binding: the audit ran once for the full run and received the
    # persisted id list AS-IS (same order, same values, no normalization).
    assert len(audit_calls) == 1
    assert audit_calls[0]["referenced_artifact_ids"] == list(
        refreshed.strategic_lens_artifact_ids
    )
    assert audit_calls[0]["charter_id"] == refreshed.charter_id
    # Safety Anchor sub-stage ran inside criticizing before the main call.
    assert ("critic", "criticizing", "safety_anchor") in calls
    anchor_index = calls.index(("critic", "criticizing", "safety_anchor"))
    main_index = calls.index(("critic", "criticizing", None))
    assert anchor_index < main_index
    # Stage hashes persisted for every executing stage.
    for stage in ("planning", "retrieving", "analyzing", "criticizing",
                  "synthesizing", "validating"):
        assert refreshed.stage_results[stage]["inputHash"].startswith("sha256:")
        assert refreshed.stage_results[stage]["outputHash"].startswith("sha256:")

    events = await repo.list_events_after(world.workspace_id, run.analysis_run_id, 0)
    types = [event.type for event in events]
    assert types[-1] == "analysis.ready"
    assert types.count("strategic_lens.completed") == 5
    # strategic_lens.completed only AFTER persistence: every such event carries
    # the persisted artifact id.
    for event in events:
        if event.type == "strategic_lens.completed":
            assert event.payload["lensArtifactId"]
            assert event.payload["lensType"] in written
    # Research packet persisted and announced.
    packets = (
        await session.scalars(
            select(ResearchPacketRow).where(
                ResearchPacketRow.analysis_run_id == run.analysis_run_id
            )
        )
    ).all()
    assert len(packets) == 1
    assert "research.packet.completed" in types


async def test_focused_run_skips_all_lens_stages(session, world) -> None:
    _, run = await make_queued_run(session, world, level=FormalAnalysisLevel.FOCUSED)
    executors, calls = _stub_executors()
    writer, written = _recording_lens_writer()
    audit, audit_calls = _stub_lens_audit(ok=True)
    worker = AnalysisWorker(
        session, executors=executors, lens_writer=writer, lens_audit=audit
    )

    await worker.run_once(workspace_id=world.workspace_id)

    repo = AnalysisRuntimeRepository(session)
    refreshed = await repo.get_run(world.workspace_id, run.analysis_run_id)
    assert AnalysisRunStatus(refreshed.status) == S.READY
    assert written == []  # no lens scheduling at all
    assert refreshed.strategic_lens_artifact_ids == []
    # Focused runs have zero lens surface: the audit never runs (§A1-⑥).
    assert audit_calls == []
    # Safety Anchor still mandatory for focused critics.
    assert ("critic", "criticizing", "safety_anchor") in calls
    events = await repo.list_events_after(world.workspace_id, run.analysis_run_id, 0)
    assert all(event.type != "strategic_lens.completed" for event in events)


async def test_validation_failure_blocks_and_never_repairs(session, world) -> None:
    _, run = await make_queued_run(session, world, level=FormalAnalysisLevel.FULL)
    executors, _ = _stub_executors(quality_gate_passed=False)
    writer, written = _recording_lens_writer()
    audit, _audit_calls = _stub_lens_audit(ok=True)
    worker = AnalysisWorker(
        session, executors=executors, lens_writer=writer, lens_audit=audit
    )

    await worker.run_once(workspace_id=world.workspace_id)

    repo = AnalysisRuntimeRepository(session)
    refreshed = await repo.get_run(world.workspace_id, run.analysis_run_id)
    assert AnalysisRunStatus(refreshed.status) == S.BLOCKED
    # Validation validated and blocked; it wrote no lens artifacts of its own:
    # the five artifacts written earlier by their producer stages remain.
    assert len(written) == 5
    events = await repo.list_events_after(world.workspace_id, run.analysis_run_id, 0)
    assert events[-1].type == "analysis.blocked"


async def test_real_audit_blocks_full_run_when_persisted_set_is_corrupt(
    session, world
) -> None:
    """§A1-⑥ red light with the DEFAULT (real) audit: the recording writer
    persists NO ready rows, so the persisted five-lens set is corrupt and the
    validating gate must land on blocked — the executor's own quality verdict
    (passed) cannot override the audit."""

    _, run = await make_queued_run(session, world, level=FormalAnalysisLevel.FULL)
    executors, _ = _stub_executors(quality_gate_passed=True)
    writer, written = _recording_lens_writer()
    worker = AnalysisWorker(session, executors=executors, lens_writer=writer)

    await worker.run_once(workspace_id=world.workspace_id)

    repo = AnalysisRuntimeRepository(session)
    refreshed = await repo.get_run(world.workspace_id, run.analysis_run_id)
    assert AnalysisRunStatus(refreshed.status) == S.BLOCKED
    assert len(written) == 5  # the stages did hand payloads to the writer
    events = await repo.list_events_after(world.workspace_id, run.analysis_run_id, 0)
    blocked = [event for event in events if event.type == "analysis.blocked"]
    assert blocked, "corrupt persisted lens set must block readiness"
    codes = {
        finding["code"]
        for finding in blocked[-1].payload.get("findings", [])
        if finding.get("source") == "lens_set_audit"
    }
    assert "strategic_lens_incomplete" in codes


async def test_cooperative_cancellation_stops_at_next_boundary(session, world) -> None:
    _, run = await make_queued_run(session, world, level=FormalAnalysisLevel.FULL)
    repo = AnalysisRuntimeRepository(session)
    cancel_during = S.ANALYZING
    stages_entered: list[str] = []

    def make(role: str):
        async def executor(run_row, stage, inputs) -> StageResult:
            if inputs.get("substage"):
                return StageResult(output={"substage": inputs["substage"]})
            stages_entered.append(stage.value)
            if stage == cancel_during:
                # An external cancel command lands while the stage executes.
                await repo.cancel(
                    world.workspace_id, run_row.analysis_run_id, reason="user_cancelled"
                )
            return StageResult(
                output={"stage": stage.value},
                quality_gate_passed=True if stage == S.VALIDATING else None,
            )

        return executor

    executors = RoleExecutors(
        research=make("research"),
        critic=make("critic"),
        synthesis=make("synthesis"),
        validation=make("validation"),
    )
    writer, written = _recording_lens_writer()
    worker = AnalysisWorker(session, executors=executors, lens_writer=writer)

    await worker.run_once(workspace_id=world.workspace_id)

    refreshed = await repo.get_run(world.workspace_id, run.analysis_run_id)
    assert AnalysisRunStatus(refreshed.status) == S.CANCELLED
    # The worker stopped at the boundary right after the cancelled stage:
    # criticizing/synthesizing/validating never ran, nothing was published.
    assert stages_entered == ["planning", "retrieving", "analyzing"]
    assert written == []  # analyzing's lens write boundary refused after cancel
    events = await repo.list_events_after(world.workspace_id, run.analysis_run_id, 0)
    types = [event.type for event in events]
    assert "analysis.cancelled" in types
    assert "analysis.ready" not in types
    assert "strategic_lens.completed" not in types
    # Events persisted before the stop are kept.
    assert types.count("analysis.stage.started") >= 3


async def test_queue_empty_returns_none(session, world) -> None:
    executors, _ = _stub_executors()
    worker = AnalysisWorker(session, executors=executors)
    assert await worker.run_once(workspace_id=world.workspace_id) is None


def test_default_lens_writer_uses_shipped_persistence_path_import_only() -> None:
    """Reuse proof: the worker consumes the shipped write path, never a copy."""

    import inspect

    source = inspect.getsource(worker_module.default_lens_writer)
    assert "persist_lens_stage_output(" in source
    assert worker_module.persist_lens_stage_output is persist_lens_stage_output
    assert LENS_VALIDATION_VERDICT is apply_validation_verdict
