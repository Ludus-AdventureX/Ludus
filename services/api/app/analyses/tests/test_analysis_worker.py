"""Task 9 owner tests: worker orchestration over stub role executors.

No model calls: role executors are deterministic stubs, the lens writer is a
recording stub (the default writer's identity with the shipped persistence
path is asserted separately). All state, events, and cancellation semantics
run against the real repository and migrated schema.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
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


@pytest.fixture
def noop_lens_verdict(monkeypatch):
    """Stub the draft->ready acceptance for tests whose recording lens writer
    returns an artifact id that was never persisted (no DB row exists, so the
    real verdict transition would fail closed with LensRunNotFound)."""

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(worker_module, "apply_validation_verdict", _noop)
    return _noop


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


async def test_full_run_pipeline_reaches_ready_with_five_lenses(
    session, world, noop_lens_verdict
) -> None:
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
    # Research packets persisted and announced. The full analyzing stage now
    # runs TWO rounds (grey-goo §7 Think-First/Search-Later): round 1 emits
    # its packet, round 2 folds round-1 gaps back in and emits a second one.
    packets = (
        await session.scalars(
            select(ResearchPacketRow).where(
                ResearchPacketRow.analysis_run_id == run.analysis_run_id
            )
        )
    ).all()
    assert len(packets) == 2  # analyzing round 1 + round 2
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


async def test_validation_failure_blocks_and_never_repairs(
    session, world, noop_lens_verdict
) -> None:
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


async def test_model_denial_surfaces_validator_rejection_in_blocked_findings(
    session, world, noop_lens_verdict
) -> None:
    """A model qualityGatePassed=false must surface WHY it rejected: the
    validating digest's headline/keyFindings ride the blocked findings as a
    validator_rejected code (the structured validatorFindings array is
    optional in practice, so the digest is the honest reason source), while
    the passed deterministic gate stays alongside - never masquerading as the
    blocker."""

    _, run = await make_queued_run(session, world, level=FormalAnalysisLevel.FULL)

    def make(role: str):
        async def executor(run_row, stage, inputs) -> StageResult:
            if inputs.get("substage"):
                return StageResult(output={"substage": inputs["substage"]})
            lens_payloads = {}
            if stage in FULL_LENS_SCHEDULE:
                lens_payloads = {
                    lens: {"lensType": lens, "content": {"stub": True}}
                    for lens in FULL_LENS_SCHEDULE[stage]
                }
            if stage == S.VALIDATING:
                return StageResult(
                    output={
                        "role": role,
                        "stage": stage.value,
                        "digest": {
                            "headline": "追觅先上市仅为推测，未提供市场情报证据",
                            "keyFindings": [
                                "决策所依据的上市时间仅为推测",
                                "5%投诉门槛无法应对低投诉高危害事故",
                            ],
                            "openQuestions": ["是否有内部测试数据"],
                            "risks": [],
                        },
                    },
                    lens_payloads=lens_payloads,
                    quality_gate_passed=False,
                )
            return StageResult(
                output={"role": role, "stage": stage.value},
                lens_payloads=lens_payloads,
            )

        return executor

    executors = RoleExecutors(
        research=make("research"),
        critic=make("critic"),
        synthesis=make("synthesis"),
        validation=make("validation"),
    )
    writer, _written = _recording_lens_writer()
    audit, _audit_calls = _stub_lens_audit(ok=True)
    worker = AnalysisWorker(
        session, executors=executors, lens_writer=writer, lens_audit=audit
    )

    await worker.run_once(workspace_id=world.workspace_id)

    repo = AnalysisRuntimeRepository(session)
    refreshed = await repo.get_run(world.workspace_id, run.analysis_run_id)
    assert AnalysisRunStatus(refreshed.status) == S.BLOCKED
    events = await repo.list_events_after(world.workspace_id, run.analysis_run_id, 0)
    blocked = [event for event in events if event.type == "analysis.blocked"]
    assert blocked
    findings = blocked[-1].payload.get("findings", [])
    rejected = [f for f in findings if f.get("code") == "validator_rejected"]
    assert len(rejected) == 1
    assert "追觅先上市仅为推测" in rejected[0]["headline"]
    assert len(rejected[0]["keyFindings"]) == 2
    gate = [f for f in findings if f.get("code") == "deterministic_gate"]
    assert gate and gate[0]["passed"] is True


async def test_real_audit_blocks_full_run_when_persisted_set_is_corrupt(
    session, world, noop_lens_verdict
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


async def test_lens_behavior_rejection_repairs_with_reason_codes(
    session, world, noop_lens_verdict
) -> None:
    """Grey-goo principle 13 (adversarial feedback loop): a lens behavior gate
    rejection MUST return INTO the producing lens model with its reason codes.
    The worker re-invokes the dedicated lens with a repair instruction and
    persists the repaired payload; one repair pass max, then fail-closed."""

    from app.strategic_lenses.repository import LensBehaviorRejected
    from app.types import StrategicLensType

    _, run = await make_queued_run(session, world, level=FormalAnalysisLevel.FULL)
    executors, _ = _stub_executors()
    rejected_lens = "porter_five_forces"
    rejection_codes = ("forces_missing", "changing_trend_missing")
    repair_requests: list[tuple[str, tuple[str, ...]]] = []
    first_attempt_done = {"done": False}

    async def writer(session, **kwargs) -> UUID:
        lens_type = kwargs["payload"]["lensType"]
        if lens_type == rejected_lens and not first_attempt_done["done"]:
            first_attempt_done["done"] = True
            raise LensBehaviorRejected(
                StrategicLensType(rejected_lens), rejection_codes
            )
        return uuid4()

    async def fake_dedicated(
        run_row, stage, lens_type, parent_result, repair_context=None
    ):
        repair_requests.append((lens_type, repair_context or ()))
        return {
            "lensType": lens_type,
            "sourceSkillVersion": "1.0.0",
            "phase": "analyzing",
            "references": {},
            "researchRequests": [],
            "content": {"repaired": True},
        }

    audit, _ = _stub_lens_audit(ok=True)
    worker = AnalysisWorker(
        session, executors=executors, lens_writer=writer, lens_audit=audit
    )
    worker._execute_dedicated_lens = fake_dedicated  # type: ignore[method-assign]

    await worker.run_once(workspace_id=world.workspace_id)

    # The rejected lens was repaired WITH the exact behavior-gate reason codes
    # (structured feedback, not a blind retry) and the run still lands ready.
    assert (rejected_lens, rejection_codes) in repair_requests
    repo = AnalysisRuntimeRepository(session)
    refreshed = await repo.get_run(world.workspace_id, run.analysis_run_id)
    assert AnalysisRunStatus(refreshed.status) == S.READY
    events = await repo.list_events_after(world.workspace_id, run.analysis_run_id, 0)
    assert [e.type for e in events].count("strategic_lens.completed") == 5


async def test_lens_behavior_rejection_second_failure_stays_fail_closed(
    session, world, noop_lens_verdict
) -> None:
    """A second behavior rejection after the repair pass keeps the established
    fail-closed posture: the lens is skipped (no unbounded retry loop) and the
    validating-gate lens audit blocks the run."""

    from app.strategic_lenses.repository import LensBehaviorRejected
    from app.types import StrategicLensType

    _, run = await make_queued_run(session, world, level=FormalAnalysisLevel.FULL)
    executors, _ = _stub_executors()
    repair_calls: list[str] = []

    async def writer(session, **kwargs) -> UUID:
        lens_type = kwargs["payload"]["lensType"]
        if lens_type == "porter_five_forces":
            raise LensBehaviorRejected(
                StrategicLensType(lens_type), ("forces_missing",)
            )
        return uuid4()

    async def fake_dedicated(
        run_row, stage, lens_type, parent_result, repair_context=None
    ):
        repair_calls.append(lens_type)
        # The repaired payload still fails the gate on the second attempt.
        return {"lensType": lens_type, "content": {"stub": True}}

    worker = AnalysisWorker(session, executors=executors, lens_writer=writer)
    worker._execute_dedicated_lens = fake_dedicated  # type: ignore[method-assign]

    await worker.run_once(workspace_id=world.workspace_id)

    # Exactly ONE repair pass was attempted (bounded retry), then skipped.
    assert repair_calls == ["porter_five_forces"]
    repo = AnalysisRuntimeRepository(session)
    refreshed = await repo.get_run(world.workspace_id, run.analysis_run_id)
    # The missing lens blocks readiness via the DEFAULT (real) audit.
    assert AnalysisRunStatus(refreshed.status) == S.BLOCKED


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


async def test_dossier_assumptions_registered_into_lens_ledger(
    session, world, noop_lens_verdict
) -> None:
    """Dossier CONFIRMED assumption entries become real Claim rows and reach
    the lens writer as ledger.assumption_ids: the counterparty reference
    authority is persisted rows, never model self-declaration."""

    from app.models import DossierEntry
    from app.types import DossierScope, DossierSourceType, DossierStatementType, EntryStatus

    session.add(
        DossierEntry(
            workspace_id=world.workspace_id,
            decision_subject_id=world.subject_id,
            decision_case_id=world.case_id,
            scope=DossierScope.CASE,
            statement_type=DossierStatementType.ASSUMPTION,
            content="procurement cycles run ~9 months",
            status=EntryStatus.CONFIRMED,
            source_type=DossierSourceType.USER,
            version=1,
        )
    )
    session.add(
        DossierEntry(
            workspace_id=world.workspace_id,
            decision_subject_id=world.subject_id,
            decision_case_id=world.case_id,
            scope=DossierScope.CASE,
            statement_type=DossierStatementType.ASSUMPTION,
            content="first mover wins certification lockout",
            status=EntryStatus.CONFIRMED,
            source_type=DossierSourceType.USER,
            version=1,
        )
    )
    await session.flush()
    _, run = await make_queued_run(session, world, level=FormalAnalysisLevel.FULL)
    executors, _ = _stub_executors()
    ledgers = []

    async def writer(session, **kwargs) -> UUID:
        ledgers.append(kwargs["ledger"])
        return uuid4()

    audit, _ = _stub_lens_audit(ok=True)
    worker = AnalysisWorker(session, executors=executors, lens_writer=writer, lens_audit=audit)

    await worker.run_once(workspace_id=world.workspace_id)

    assert ledgers, "lens writer must have been called for a full run"
    assumption_ids = set().union(*(ledger.assumption_ids for ledger in ledgers))
    assert assumption_ids, "registered dossier assumptions must reach the lens ledger"
    # The Claim rows are the persisted authority behind those ids.
    from app.analyses.claims import Claim

    rows = (
        await session.execute(
            select(Claim).where(
                Claim.workspace_id == world.workspace_id,
                Claim.analysis_run_id == run.analysis_run_id,
            )
        )
    ).scalars().all()
    assert len(rows) == 2
    # Ledger ids are the Claim row ids (the persisted authority), not the
    # dossier entry ids recorded as source_span_ids.
    assert {str(row.id) for row in rows} == {
        span for ledger in ledgers for span in ledger.assumption_ids
    }


async def test_lens_ledger_without_dossier_assumptions_stays_empty(
    session, world, noop_lens_verdict
) -> None:
    """No dossier assumptions -> no Claim rows -> empty ledger.assumption_ids:
    the counterparty gate keeps blocking honestly (fail-closed), the worker
    never fabricates references."""

    _, run = await make_queued_run(session, world, level=FormalAnalysisLevel.FULL)
    executors, _ = _stub_executors()
    ledgers = []

    async def writer(session, **kwargs) -> UUID:
        ledgers.append(kwargs["ledger"])
        return uuid4()

    audit, _ = _stub_lens_audit(ok=True)
    worker = AnalysisWorker(session, executors=executors, lens_writer=writer, lens_audit=audit)

    await worker.run_once(workspace_id=world.workspace_id)

    assert ledgers, "lens writer must have been called for a full run"
    assert all(not ledger.assumption_ids for ledger in ledgers)


# --- P2 wave 1: grey-goo Self-Anchor (§8) / logic spot-check (§13) / anchor
# --- downgrade pre-check (v6.9.5) — pure functions, no DB required ----------


def test_self_anchor_all_conflict_caps_score() -> None:
    packet = {
        "factor": "rescue demand",
        "conclusion": "rescue demand is confirmed by procurement data",
        "claim_support_score": 0.9,
        "self_anchor": [
            {"verdict": "conflict", "evidenceId": "ev-1"},
            {"verdict": "conflict", "evidenceId": "ev-2"},
        ],
    }
    sanitized = worker_module._sanitize_packet(packet)
    assert sanitized is not None
    assert sanitized["claim_support_score"] == 0.5  # capped, not kept at 0.9
    assert sanitized["self_anchor"][0]["verdict"] == "conflict"


def test_self_anchor_pass_or_mixed_keeps_score() -> None:
    for verdicts in (
        [{"verdict": "pass", "evidenceId": "ev-1"}],
        [{"verdict": "conflict", "evidenceId": "ev-1"}, {"verdict": "pass", "evidenceId": "ev-2"}],
        [],
    ):
        packet = {
            "factor": "rescue demand",
            "conclusion": "procurement cycles run ~9 months",
            "claim_support_score": 0.8,
            "self_anchor": verdicts,
        }
        sanitized = worker_module._sanitize_packet(packet)
        assert sanitized["claim_support_score"] == 0.8


def test_self_anchor_malformed_dropped_not_crashing() -> None:
    packet = {
        "factor": "rescue demand",
        "conclusion": "procurement cycles run ~9 months",
        "self_anchor": "not-a-list",
    }
    sanitized = worker_module._sanitize_packet(packet)
    assert "self_anchor" not in sanitized
    assert sanitized["claim_support_score"] == 0.5


def test_logic_spot_check_catches_circular_reasoning_and_premise_drift() -> None:
    circular = {
        "factor": "market demand is growing strongly",
        "conclusion": "the market is growing strongly, so demand is strong",
    }
    findings = worker_module._logic_spot_check(circular)
    assert "circular_reasoning" in findings

    drift = {
        "factor": "rescue robot certification",
        "conclusion": "supply chain delays push the timeline",
    }
    findings = worker_module._logic_spot_check(drift)
    assert "premise_drift" in findings


def test_logic_spot_check_clean_packet_returns_empty() -> None:
    clean = {
        "factor": "rescue robot certification timeline",
        "conclusion": "certification takes nine months on average",
    }
    assert worker_module._logic_spot_check(clean) == ()


def test_anchor_blocks_downgrade_when_two_shared_assumptions() -> None:
    blocked, count = worker_module._anchor_blocks_downgrade(
        {
            "safety_anchor": {
                "digest": {
                    "keyFindings": [
                        "all agents assume the LOI converts",
                        "all agents assume buyer funding is committed",
                    ]
                }
            }
        }
    )
    assert blocked is True
    assert count == 2


def test_anchor_does_not_block_with_zero_or_one_finding() -> None:
    for findings in ([], ["single shared assumption"]):
        blocked, count = worker_module._anchor_blocks_downgrade(
            {"safety_anchor": {"digest": {"keyFindings": findings}}}
        )
        assert blocked is False
        assert count == len(findings)
    # Missing anchor / missing digest must never block.
    assert worker_module._anchor_blocks_downgrade({}) == (False, 0)
    assert worker_module._anchor_blocks_downgrade({"safety_anchor": {}}) == (False, 0)


# --- P2 wave 2: retrieval coverage (§3) / funnel audit persistence (原则⑩) /
# --- complexity downgrade (原则⑮) ---------------------------------------------


async def test_retrieve_once_writes_coverage_and_reuses_frozen_row(
    session, world, monkeypatch
) -> None:
    """A repeat query inside the same run reuses the coverage row instead of
    re-hitting the provider (grey-goo §3 idempotency)."""

    from app.workers.analysis_worker import AnalysisWorker as _W

    _, run = await make_queued_run(session, world, level=FormalAnalysisLevel.FULL)
    calls = {"n": 0}

    async def fake_search(question, option_ids, **kwargs):
        calls["n"] += 1
        return [{"title": "source-a", "url": "https://a.test", "tier": "L2"}]

    monkeypatch.setattr(worker_module, "search_web", fake_search)
    worker = _W(session, executors=_stub_executors()[0])

    first = await worker._retrieve_once(
        run, question="enter rescue market?", option_ids=["opt_a"], byok_exa=None, byok_firecrawl=None
    )
    second = await worker._retrieve_once(
        run, question="enter rescue market?", option_ids=["opt_a"], byok_exa=None, byok_firecrawl=None
    )
    assert calls["n"] == 1, "coverage hit must not re-hit the provider"
    assert first and not second  # first returns sources, second reuses frozen row
    from app.models import RetrievalCoverage as _Cov

    rows = (
        await session.execute(
            select(_Cov).where(_Cov.analysis_run_id == run.analysis_run_id)
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].result_hash.startswith("sha256:")


async def test_funnel_audit_persisted_on_retrieving(session, world, noop_lens_verdict) -> None:
    """The TDD discard audit lands in evidence_funnel_audits (原则⑩), so the
    E page can show what was filtered out and why."""

    from app.models import EvidenceFunnelAudit as _Funnel

    _, run = await make_queued_run(session, world, level=FormalAnalysisLevel.FULL)
    executors, _ = _stub_executors()

    # The stub must produce packets in RETRIEVING (the default stub only
    # produces them in ANALYZING), otherwise the funnel never runs.
    def make(role: str):
        async def executor(run_row, stage, inputs) -> StageResult:
            lens_payloads = {}
            if stage in FULL_LENS_SCHEDULE:
                lens_payloads = {
                    lens: {
                        "lensType": lens,
                        "sourceSkillVersion": "1.0.0",
                        "phase": stage.value,
                        "references": {},
                        "researchRequests": [],
                        "content": {"stub": True},
                    }
                    for lens in FULL_LENS_SCHEDULE[stage]
                }
            packets = ()
            if stage == S.RETRIEVING:
                packets = (
                    {"factor": "rescue demand", "conclusion": "demand is confirmed by data"},
                    {"factor": "home market", "conclusion": "home market is smaller"},
                    {"factor": "opposing view", "conclusion": "regulation may block entry"},
                )
            return StageResult(
                output={"role": role, "stage": stage.value},
                packets=packets,
                lens_payloads=lens_payloads,
                quality_gate_passed=True if stage == S.VALIDATING else None,
            )

        return executor

    executors = RoleExecutors(
        research=make("research"),
        critic=make("critic"),
        synthesis=make("synthesis"),
        validation=make("validation"),
    )
    writer, _ = _recording_lens_writer()
    audit, _ = _stub_lens_audit(ok=True)
    worker = AnalysisWorker(
        session, executors=executors, lens_writer=writer, lens_audit=audit
    )

    await worker.run_once(workspace_id=world.workspace_id)

    rows = (
        await session.execute(
            select(_Funnel).where(_Funnel.analysis_run_id == run.analysis_run_id)
        )
    ).scalars().all()
    assert rows, "retrieving stage must persist a funnel audit row"
    assert rows[0].admitted >= 1
    assert rows[0].stage == "retrieving"


async def test_complexity_downgrade_fires_on_strong_evidence(session, world, noop_lens_verdict) -> None:
    """A full run with admitted>=2, opposing>=1, low-trust<=50% and an anchor
    that does NOT block gets downgraded once (full->focused), with the chain
    recorded on the run and the event carrying the downgrade marker."""

    _, run = await make_queued_run(session, world, level=FormalAnalysisLevel.FULL)
    executors, _ = _stub_executors()

    def make(role: str):
        async def executor(run_row, stage, inputs) -> StageResult:
            lens_payloads = {}
            if stage in FULL_LENS_SCHEDULE:
                lens_payloads = {
                    lens: {
                        "lensType": lens,
                        "sourceSkillVersion": "1.0.0",
                        "phase": stage.value,
                        "references": {},
                        "researchRequests": [],
                        "content": {"stub": True},
                    }
                    for lens in FULL_LENS_SCHEDULE[stage]
                }
            if inputs.get("substage") == "safety_anchor":
                return StageResult(
                    output={"digest": {"keyFindings": ["only one shared assumption"]}}
                )
            if stage == S.RETRIEVING:
                return StageResult(
                    output={"role": role, "stage": stage.value},
                    packets=(
                        {
                            "factor": "rescue demand",
                            "conclusion": "demand is confirmed by procurement data",
                            "sources": [{"name": "procurement report", "url": "https://www.gov.uk/1", "tier": "L2"}],
                        },
                        {
                            "factor": "home market",
                            "conclusion": "home market is smaller than rescue",
                            "sources": [{"name": "market study", "url": "https://www.gov.uk/2", "tier": "L2"}],
                        },
                        {
                            "factor": "opposing view",
                            "conclusion": "regulation may block entry in some states",
                            "direction": "opposing",
                            "sources": [{"name": "regulator notice", "url": "https://www.gartner.com/1", "tier": "L3"}],
                        },
                    ),
                    lens_payloads=lens_payloads,
                )
            return StageResult(
                output={"role": role, "stage": stage.value},
                lens_payloads=lens_payloads,
                quality_gate_passed=True if stage == S.VALIDATING else None,
            )

        return executor

    executors = RoleExecutors(
        research=make("research"),
        critic=make("critic"),
        synthesis=make("synthesis"),
        validation=make("validation"),
    )
    writer, _ = _recording_lens_writer()
    audit, _ = _stub_lens_audit(ok=True)
    worker = AnalysisWorker(
        session, executors=executors, lens_writer=writer, lens_audit=audit
    )

    await worker.run_once(workspace_id=world.workspace_id)

    repo = AnalysisRuntimeRepository(session)
    refreshed = await repo.get_run(world.workspace_id, run.analysis_run_id)
    assert refreshed.complexity_downgraded is True
    assert refreshed.downgrade_chain and "full->focused" in refreshed.downgrade_chain[0]
    events = await repo.list_events_after(world.workspace_id, run.analysis_run_id, 0)
    downgrade_events = [
        e for e in events
        if isinstance(e.payload, dict) and e.payload.get("downgrade")
    ]
    assert downgrade_events, "downgrade must be announced on the event stream"
    assert downgrade_events[0].payload["downgrade"]["from"] == "full"


async def test_complexity_downgrade_blocked_by_anchor(session, world, noop_lens_verdict) -> None:
    """Two shared unexamined assumptions block the downgrade (v6.9.5 guard):
    convergence may be echo, not simplicity."""

    _, run = await make_queued_run(session, world, level=FormalAnalysisLevel.FULL)
    executors, _ = _stub_executors()

    def make(role: str):
        async def executor(run_row, stage, inputs) -> StageResult:
            lens_payloads = {}
            if stage in FULL_LENS_SCHEDULE:
                lens_payloads = {
                    lens: {
                        "lensType": lens,
                        "sourceSkillVersion": "1.0.0",
                        "phase": stage.value,
                        "references": {},
                        "researchRequests": [],
                        "content": {"stub": True},
                    }
                    for lens in FULL_LENS_SCHEDULE[stage]
                }
            if inputs.get("substage") == "safety_anchor":
                return StageResult(
                    output={
                        "digest": {
                            "keyFindings": [
                                "all agents assume the LOI converts",
                                "all agents assume buyer funding is committed",
                            ]
                        }
                    }
                )
            if stage == S.RETRIEVING:
                return StageResult(
                    output={"role": role, "stage": stage.value},
                    packets=(
                        {
                            "factor": "rescue demand",
                            "conclusion": "demand is confirmed by procurement data",
                            "sources": [{"name": "procurement report", "url": "https://www.gov.uk/1", "tier": "L2"}],
                        },
                        {
                            "factor": "home market",
                            "conclusion": "home market is smaller than rescue",
                            "sources": [{"name": "market study", "url": "https://www.gov.uk/2", "tier": "L2"}],
                        },
                        {
                            "factor": "opposing view",
                            "conclusion": "regulation may block entry in some states",
                            "direction": "opposing",
                            "sources": [{"name": "regulator notice", "url": "https://www.gartner.com/1", "tier": "L3"}],
                        },
                    ),
                    lens_payloads=lens_payloads,
                )
            return StageResult(
                output={"role": role, "stage": stage.value},
                lens_payloads=lens_payloads,
                quality_gate_passed=True if stage == S.VALIDATING else None,
            )

        return executor

    executors = RoleExecutors(
        research=make("research"),
        critic=make("critic"),
        synthesis=make("synthesis"),
        validation=make("validation"),
    )
    writer, _ = _recording_lens_writer()
    audit, _ = _stub_lens_audit(ok=True)
    worker = AnalysisWorker(
        session, executors=executors, lens_writer=writer, lens_audit=audit
    )

    await worker.run_once(workspace_id=world.workspace_id)

    repo = AnalysisRuntimeRepository(session)
    refreshed = await repo.get_run(world.workspace_id, run.analysis_run_id)
    assert refreshed.complexity_downgraded is False
    assert refreshed.downgrade_chain == []


# --- P2 wave 3: cross-agent calibration (原则⑭ / P2-1) -------------------------


async def test_upstream_lens_digests_exclude_current_and_compress(
    session, world, noop_lens_verdict
) -> None:
    """A later lens sees compressed digests of READY earlier lenses in the SAME
    run, never its own output, never drafts (grey-goo 原则⑭ cross-calibration)."""

    from app.models import StrategicLensArtifact
    from app.types import StrategicLensType, StrategicLensArtifactStatus

    _, run = await make_queued_run(session, world, level=FormalAnalysisLevel.FULL)

    def make_artifact(lens_type: StrategicLensType, status, content) -> StrategicLensArtifact:
        from datetime import datetime, timezone

        return StrategicLensArtifact(
            workspace_id=world.workspace_id,
            decision_case_id=world.case_id,
            analysis_run_id=run.analysis_run_id,
            charter_id=run.charter_id,
            lens_type=lens_type,
            producer_role="research",
            status=status,
            method_id="hardtech-market-direction",
            method_version="1.1.0",
            method_content_hash="sha256:m",
            prompt_version="1.0.0",
            schema_version="1.0.0",
            origin_modes=["live"],
            content_hash="sha256:c",
            payload={"content": content, "references": {}},
            claim_refs=[],
            evidence_refs=[],
            assumption_refs=[],
            # The ready-requires-validation check constraint demands a witness.
            validation_accepted_at=(
                datetime.now(timezone.utc)
                if status == StrategicLensArtifactStatus.READY
                else None
            ),
        )

    session.add(
        make_artifact(
            StrategicLensType.PORTER_FIVE_FORCES,
            StrategicLensArtifactStatus.READY,
            {"headline": "rescue market is competitive", "keyFindings": ["low barriers"]},
        )
    )
    session.add(
        make_artifact(
            StrategicLensType.PRE_MORTEM,
            StrategicLensArtifactStatus.DRAFT,
            {"headline": "draft must not be seen"},
        )
    )
    await session.flush()

    executors, _ = _stub_executors()
    worker = AnalysisWorker(session, executors=executors)
    digests = await worker._load_upstream_lens_digests(
        run, StrategicLensType.COUNTERPARTY_RESPONSE_MATRIX
    )

    assert StrategicLensType.PORTER_FIVE_FORCES in digests
    assert "rescue market is competitive" in digests[StrategicLensType.PORTER_FIVE_FORCES]["summary"]
    assert "low barriers" in digests[StrategicLensType.PORTER_FIVE_FORCES]["summary"]
    # Own lens type and drafts are excluded.
    assert StrategicLensType.COUNTERPARTY_RESPONSE_MATRIX not in digests
    assert StrategicLensType.PRE_MORTEM not in digests


# --- P2 wave 3: narrative-echo prevention (P2-8) ------------------------------


def test_echo_checklist_flags_one_narrative_planning() -> None:
    one_sided = "We will confirm our market opportunity and our product fit."
    checks = worker_module._echo_checklist(one_sided)
    assert checks["perspective_symmetry"] is False  # no risk/against/opposing
    assert checks["prosecutor_forced"] is False
    assert checks["failure_signal"] is False
    assert checks["assumption_pressure"] is False


def test_echo_checklist_passes_adversarial_planning() -> None:
    adversarial = (
        "Stress the risk of failure, examine the assumption that demand "
        "exists, check why competitors never succeeded, and challenge the "
        "funding story."
    )
    checks = worker_module._echo_checklist(adversarial)
    assert checks["perspective_symmetry"] is True
    assert checks["prosecutor_forced"] is True
    assert checks["failure_signal"] is True
    assert checks["assumption_pressure"] is True
    assert checks["capital_market_signal"] is True


def test_echo_checklist_empty_text_is_neutral() -> None:
    checks = worker_module._echo_checklist("")
    assert all(checks.values())


def test_narrative_divergence_scores_independence_and_echo() -> None:
    # Fully disjoint vocabularies -> high divergence (independence).
    high = worker_module._narrative_divergence(
        "rescue robots face certification timelines",
        "marketing budgets depend on investor appetite",
    )
    assert high >= 8.0
    # Near-identical wording -> low divergence (echo). Grey-goo treats
    # <4 as severe echo; the fixture lands just under the flag line.
    low = worker_module._narrative_divergence(
        "rescue market demand is confirmed by procurement data",
        "procurement data confirms rescue market demand is strong",
    )
    assert low < 4.0
    # Empty side -> neutral, never auto-flagged.
    assert worker_module._narrative_divergence("", "anything at all") == 5.0

# --- C: LENS_REPAIR_MAX budget + B4: schema-fragment repair hints ------------

def test_repairable_reason_codes_filters_only_deterministic_codes() -> None:
    """C: deterministic mistakes consume no repair budget; everything else does."""
    assert worker_module._repairable_reason_codes(("forces_missing",)) == ("forces_missing",)
    assert worker_module._repairable_reason_codes(
        ("schema:content.currentInterventions.2",)
    ) == ("schema:content.currentInterventions.2",)
    assert worker_module._repairable_reason_codes(
        ("meadows_level_band_mismatch", "one_to_two_key_actors")
    ) == ("meadows_level_band_mismatch", "one_to_two_key_actors")
    assert worker_module._repairable_reason_codes(("lens_type_mismatch",)) == ()
    assert worker_module._repairable_reason_codes(
        ("phase_must_be_adversarial_stress", "source_skill_version_mismatch")
    ) == ()


def test_env_lens_repair_max_clamped(monkeypatch) -> None:
    """C: LENS_REPAIR_MAX is read from env and clamped to 0..2."""
    monkeypatch.setenv("LENS_REPAIR_MAX", "3")
    assert worker_module._env_lens_repair_max() == 2
    monkeypatch.setenv("LENS_REPAIR_MAX", "-1")
    assert worker_module._env_lens_repair_max() == 0
    monkeypatch.setenv("LENS_REPAIR_MAX", "not-a-number")
    assert worker_module._env_lens_repair_max() == 1
    monkeypatch.delenv("LENS_REPAIR_MAX", raising=False)
    assert worker_module._env_lens_repair_max() == 1


def test_schema_fragments_for_quotes_violated_field_shape() -> None:
    """B4: repair hints carry the violated schema branch, not just the path."""
    from app.agents.lenses import load_lens_content_schema

    branch = load_lens_content_schema("counterpartyContent")
    if not branch:
        pytest.skip("method-pack schema not installed in this environment")
    hint = worker_module._schema_fragments_for(
        ("schema:content.ourActions.1",), "counterpartyContent"
    )
    assert "ourActions.1" in hint
    assert "coreAssumptionIds" in hint or "actionType" in hint
    # No match -> no fragment, no crash.
    assert worker_module._schema_fragments_for(("forces_missing",), "counterpartyContent") == ""
