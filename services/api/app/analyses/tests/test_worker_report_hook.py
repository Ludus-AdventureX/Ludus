"""READY report hook tests: canonical report artifacts materialize from runs.

The worker's _persist_run_report assembles a deterministic canonical document
(report_builder) and persists + publishes it through the shipped synthesis
path. Invariants pinned here: READY produces exactly one ready report,
re-persistence is canonical-hash idempotent, and blocked runs produce zero
reports ("no qualifying run, no report").
"""

from __future__ import annotations

from sqlalchemy import select

from app.analyses.repository import AnalysisRuntimeRepository
from app.analyses.synthesis import validate_content_for_level
from app.reports.models import ReportArtifact
from app.types import AnalysisRunStatus, FormalAnalysisLevel, OriginMode
from app.workers.analysis_worker import AnalysisWorker, _extract_digest
from app.workers.report_builder import build_focused_document

from runtime_world import make_queued_run
from test_analysis_worker import _stub_executors, _recording_lens_writer, _stub_lens_audit

S = AnalysisRunStatus


async def _reports_for(session, workspace_id, run_id):
    rows = (
        await session.execute(
            select(ReportArtifact).where(
                ReportArtifact.workspace_id == workspace_id,
                ReportArtifact.analysis_run_id == run_id,
            )
        )
    ).scalars()
    return list(rows)


async def test_focused_ready_run_persists_and_publishes_brief_report(session, world) -> None:
    _, run = await make_queued_run(session, world, level=FormalAnalysisLevel.FOCUSED)
    executors, _ = _stub_executors(with_lenses=False)
    worker = AnalysisWorker(session, executors=executors)

    claimed = await worker.run_once(workspace_id=world.workspace_id)
    assert claimed == run.analysis_run_id

    repo = AnalysisRuntimeRepository(session)
    refreshed = await repo.get_run(world.workspace_id, run.analysis_run_id)
    assert AnalysisRunStatus(refreshed.status) == S.READY

    reports = await _reports_for(session, world.workspace_id, run.analysis_run_id)
    assert len(reports) == 1
    report = reports[0]
    assert report.type == "brief"
    assert report.status == "ready"
    assert report.structured_content["schemaVersion"] == "report-1.0.0"
    assert report.structured_content["qualityGate"]["passed"] is True
    assert report.source_judgment_set_id is not None
    assert report.source_dissent_record_id is not None


async def test_report_hook_is_idempotent_for_the_same_run(session, world) -> None:
    _, run = await make_queued_run(session, world, level=FormalAnalysisLevel.FOCUSED)
    executors, _ = _stub_executors(with_lenses=False)
    worker = AnalysisWorker(session, executors=executors)
    await worker.run_once(workspace_id=world.workspace_id)

    repo = AnalysisRuntimeRepository(session)
    refreshed = await repo.get_run(world.workspace_id, run.analysis_run_id)

    # Deterministic same-day re-run: same canonical content -> same row reused.
    await worker._persist_run_report(refreshed, {})
    reports = await _reports_for(session, world.workspace_id, run.analysis_run_id)
    assert len(reports) == 1


async def test_blocked_run_produces_no_report(session, world) -> None:
    _, run = await make_queued_run(session, world, level=FormalAnalysisLevel.FOCUSED)
    executors, _ = _stub_executors(quality_gate_passed=False, with_lenses=False)
    worker = AnalysisWorker(session, executors=executors)

    await worker.run_once(workspace_id=world.workspace_id)

    repo = AnalysisRuntimeRepository(session)
    refreshed = await repo.get_run(world.workspace_id, run.analysis_run_id)
    assert AnalysisRunStatus(refreshed.status) == S.BLOCKED
    assert await _reports_for(session, world.workspace_id, run.analysis_run_id) == []


async def test_full_ready_run_persists_detailed_report_with_five_lens_ids(session, world) -> None:
    _, run = await make_queued_run(session, world, level=FormalAnalysisLevel.FULL)
    executors, _ = _stub_executors()
    writer, _ = _recording_lens_writer()
    audit, _ = _stub_lens_audit(ok=True)
    worker = AnalysisWorker(session, executors=executors, lens_writer=writer, lens_audit=audit)

    await worker.run_once(workspace_id=world.workspace_id)

    reports = await _reports_for(session, world.workspace_id, run.analysis_run_id)
    assert len(reports) == 1
    assert reports[0].type == "detailed"
    assert reports[0].status == "ready"
    assert len(reports[0].structured_content["lensArtifactIds"]) == 5

class _FakeCharter:
    decision_question = "Exclusive terms in 90 days or exit?"
    option_ids = ["opt_go", "opt_wait"]
    goals = [{"id": "g1", "text": "secure the channel"}]
    constraints = [{"id": "c1", "text": "cash window closes in 6 months"}]
    method_id = "hardtech-market-direction"
    method_version = "1.1.0"
    method_content_hash = "sha256:method"


def test_digest_material_feeds_the_report_body() -> None:
    """Stage digests become counterarguments/risks/uncertainty - and the
    document stays canonical (validate_content_for_level is the judge)."""

    stage_outputs = {
        "analyzing": {"digest": {"headline": "Channel demand is real but conditional.",
                                 "risks": ["tender cycle may exceed the cash window"]}},
        "criticizing": {
            "strongestObjection": "The counterparty can clone the offer in 60 days.",
            "digest": {
                "keyFindings": ["pilot fails if certification slips past Q3"],
                "risks": ["single-buyer dependency"],
                "openQuestions": ["will the buyer sign exclusivity at all?"],
            },
        },
        "synthesizing": {"decision": "Proceed only with a signed exclusivity LOI.", "digest": {}},
    }
    document = build_focused_document(
        charter=_FakeCharter(), stage_outputs=stage_outputs, origin_mode=OriginMode.LIVE
    )
    validate_content_for_level(FormalAnalysisLevel.FOCUSED, document)  # fail-loud gate

    texts = [c["text"] for c in document["counterArguments"]]
    assert "The counterparty can clone the offer in 60 days." in texts
    assert "pilot fails if certification slips past Q3" in texts
    assert "single-buyer dependency" in document["recommendation"]["risks"]
    questions = [u["question"] for u in document["residualUncertainty"]]
    assert "will the buyer sign exclusivity at all?" in questions
    assert document["executiveBrief"]["decision"] == "Proceed only with a signed exclusivity LOI."


def test_extract_digest_is_bounded_and_fail_open() -> None:
    assert _extract_digest({}) is None
    assert _extract_digest({"summary": "plain summary"}) == {"headline": "plain summary"}
    big = _extract_digest({"digest": {"headline": "h" * 999, "keyFindings": ["x"] * 99, "risks": 42}})
    assert len(big["headline"]) == 300
    assert len(big["keyFindings"]) == 5
    assert "risks" not in big

