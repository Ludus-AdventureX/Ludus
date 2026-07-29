"""Traceability + stale-run recovery tests (the remaining alpha gaps).

Each test pins one thing that was FALSE before this change:

1. The charter's frozen snapshot came from the CALLER. The shipped web client
   sent `sha256:` + random bytes for each of the four fields, so the audit chain
   proved nothing: identical case content produced different hashes and
   different content produced equally unrelated ones.
2. A replacement (amendment) draft inherited the superseded charter's snapshot,
   so the new run claimed to have analysed the OLD case content.
3. `recover_stale_runs` existed but nothing ever called it, so a run whose
   worker died stayed in its executing stage forever and kept the case's single
   active-run slot occupied.

Text fixtures here are deliberately ASCII: this file is edited by tooling that
has corrupted multi-byte literals before, and no assertion needs Chinese.
"""

from __future__ import annotations

from datetime import timedelta

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.analyses.repository import AnalysisRuntimeRepository, utc_now
from app.analyses.snapshots import freeze_case_snapshot
from app.auth.config import get_auth_settings
from app.models import DecisionCase, DossierEntry
from app.types import (
    AnalysisRunStatus,
    DossierScope,
    DossierSourceType,
    DossierStatementType,
    EntryStatus,
    FormalAnalysisLevel,
)

from runtime_world import make_queued_run
from test_analysis_http_handlers import _build_app

S = AnalysisRunStatus


async def _case(session, world) -> DecisionCase:
    case = await session.scalar(
        select(DecisionCase).where(
            DecisionCase.workspace_id == world.workspace_id,
            DecisionCase.decision_case_id == world.case_id,
        )
    )
    assert case is not None
    return case


def _entry(world, content: str, *, status: EntryStatus, case_scoped: bool = True):
    return DossierEntry(
        workspace_id=world.workspace_id,
        decision_subject_id=world.subject_id,
        decision_case_id=world.case_id if case_scoped else None,
        scope=DossierScope.CASE if case_scoped else DossierScope.SUBJECT,
        statement_type=DossierStatementType.FACT,
        content=content,
        status=status,
        source_type=DossierSourceType.USER,
    )


def _charter_client(session, world) -> AsyncClient:
    settings = get_auth_settings()
    return AsyncClient(
        transport=ASGITransport(app=_build_app(session, {world.workspace_id: world.user_id})),
        base_url="http://analyses.test",
        headers={
            "Origin": "http://analyses.test",
            settings.csrf_header_name: "qa-snapshot-csrf",
        },
        cookies={settings.csrf_cookie_name: "qa-snapshot-csrf"},
    )


async def _freeze(session, world):
    return await freeze_case_snapshot(
        session, workspace_id=world.workspace_id, decision_case_id=world.case_id
    )


async def test_snapshot_hash_is_deterministic_and_content_bound(session, world) -> None:
    """The same content must hash identically; different content must not."""

    first = await _freeze(session, world)
    second = await _freeze(session, world)
    assert first == second, "freezing twice over unchanged content must be identical"
    assert first.case_snapshot_hash.startswith("sha256:")
    assert len(first.case_snapshot_hash) == len("sha256:") + 64

    # Change the case itself -> the case hash MUST move.
    case = await _case(session, world)
    case.decision_question = case.decision_question + " (revised)"
    await session.flush()
    after_question = await _freeze(session, world)
    assert after_question.case_snapshot_hash != first.case_snapshot_hash
    # ...and the dossier hash must NOT move: they freeze different things.
    assert after_question.dossier_snapshot_hash == first.dossier_snapshot_hash


async def test_only_confirmed_dossier_entries_enter_the_snapshot(session, world) -> None:
    """A candidate must not change what a frozen charter claims to have analysed."""

    before = await _freeze(session, world)

    session.add(_entry(world, "candidate fact, not yet confirmed", status=EntryStatus.CANDIDATE))
    await session.flush()
    with_candidate = await _freeze(session, world)
    assert with_candidate.dossier_snapshot_hash == before.dossier_snapshot_hash
    assert with_candidate.entry_count == before.entry_count

    session.add(_entry(world, "confirmed fact: cash runway is 9 months", status=EntryStatus.CONFIRMED))
    await session.flush()
    with_confirmed = await _freeze(session, world)
    assert with_confirmed.dossier_snapshot_hash != before.dossier_snapshot_hash
    assert with_confirmed.entry_count == before.entry_count + 1


async def test_subject_scoped_confirmed_facts_are_part_of_the_snapshot(
    session, world
) -> None:
    """Subject-wide confirmed facts are real analysis input, so they count."""

    before = await _freeze(session, world)
    session.add(
        _entry(
            world,
            "subject-wide confirmed fact",
            status=EntryStatus.CONFIRMED,
            case_scoped=False,
        )
    )
    await session.flush()
    after = await _freeze(session, world)
    assert after.dossier_snapshot_hash != before.dossier_snapshot_hash
    assert after.entry_count == before.entry_count + 1


async def test_charter_freezes_the_server_snapshot_not_the_caller_value(
    session, world
) -> None:
    """HTTP contract: a caller-supplied snapshot hash is ignored."""

    expected = await _freeze(session, world)
    body = {
        "decisionSubjectId": str(world.subject_id),
        "analysisLevel": "focused",
        "decisionQuestion": "rescue market or home service market first?",
        # A lying client: fabricated values, exactly what the web app used to send.
        "caseVersion": 999,
        "caseSnapshotHash": "sha256:" + "0" * 64,
        "dossierSnapshotVersion": 999,
        "dossierSnapshotHash": "sha256:" + "f" * 64,
    }
    async with _charter_client(session, world) as client:
        response = await client.post(
            f"/api/workspaces/{world.workspace_id}"
            f"/cases/{world.case_id}/analysis-charters",
            json=body,
        )

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["caseSnapshotHash"] == expected.case_snapshot_hash
    assert data["dossierSnapshotHash"] == expected.dossier_snapshot_hash
    assert data["caseVersion"] == expected.case_version
    assert data["dossierSnapshotVersion"] == expected.dossier_snapshot_version
    # The fabricated values must appear nowhere.
    assert data["caseSnapshotHash"] != body["caseSnapshotHash"]
    assert data["caseVersion"] != 999


async def test_charter_no_longer_requires_the_snapshot_fields(session, world) -> None:
    """The web client must be able to omit them entirely."""

    async with _charter_client(session, world) as client:
        response = await client.post(
            f"/api/workspaces/{world.workspace_id}"
            f"/cases/{world.case_id}/analysis-charters",
            json={
                "decisionSubjectId": str(world.subject_id),
                "analysisLevel": "focused",
                "decisionQuestion": "a question",
            },
        )

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["caseSnapshotHash"].startswith("sha256:")
    assert data["dossierSnapshotHash"].startswith("sha256:")


async def test_two_charters_over_unchanged_content_share_one_hash(session, world) -> None:
    """The point of the hash: same input, same fingerprint.

    Before this change two charters over identical content carried unrelated
    random hashes, so nothing downstream could tell 'same input' from
    'different input'.
    """

    body = {
        "decisionSubjectId": str(world.subject_id),
        "analysisLevel": "focused",
        "decisionQuestion": "a question",
    }
    async with _charter_client(session, world) as client:
        first = await client.post(
            f"/api/workspaces/{world.workspace_id}"
            f"/cases/{world.case_id}/analysis-charters",
            json=body,
        )
        second = await client.post(
            f"/api/workspaces/{world.workspace_id}"
            f"/cases/{world.case_id}/analysis-charters",
            json=body,
        )

    assert first.status_code == 201 and second.status_code == 201
    left, right = first.json()["data"], second.json()["data"]
    assert left["caseSnapshotHash"] == right["caseSnapshotHash"]
    assert left["dossierSnapshotHash"] == right["dossierSnapshotHash"]
    assert left["charterId"] != right["charterId"]


async def test_stale_run_recovery_parks_a_dead_workers_run(session, world) -> None:
    """A run whose heartbeat expired must become recoverable, not immortal."""

    _, run = await make_queued_run(session, world, level=FormalAnalysisLevel.FOCUSED)
    repo = AnalysisRuntimeRepository(session)
    ws, run_id = world.workspace_id, run.analysis_run_id

    await repo.transition(ws, run_id, S.PLANNING)
    await repo.transition(ws, run_id, S.RETRIEVING)
    fresh = await repo.get_run(ws, run_id)
    assert fresh is not None
    assert AnalysisRunStatus(fresh.status) == S.RETRIEVING

    # A live heartbeat must NOT be reclaimed. Asserted against THIS run only:
    # the shared dev database also holds unrelated runs left mid-stage by earlier
    # sessions, so a global emptiness assertion would depend on that state.
    assert run_id not in await repo.recover_stale_runs()

    # Simulate the worker dying mid-stage.
    fresh.heartbeat_at = utc_now() - timedelta(minutes=10)
    await session.flush()

    recovered = await repo.recover_stale_runs()
    assert run_id in recovered

    parked = await repo.get_run(ws, run_id)
    assert parked is not None
    assert AnalysisRunStatus(parked.status) == S.NEEDS_ATTENTION
    # It must be resumable from where it died, not from the start.
    assert AnalysisRunStatus(parked.last_resumable_stage) == S.RETRIEVING

    events = await repo.list_events_after(ws, run_id, 0)
    assert events[-1].type == "analysis.needs_attention"
    assert events[-1].payload["reason"] == "heartbeat_expired"


def test_worker_loop_calls_stale_recovery_when_idle() -> None:
    """Wiring: the shipped recovery must actually be reachable from the loop."""

    import inspect

    from app.workers import run as worker_run

    assert hasattr(worker_run, "_recover_stale_runs")
    source = inspect.getsource(worker_run.main)
    assert "_recover_stale_runs" in source
    # Recovery belongs on the idle branch, after the drain-without-sleeping path.
    drain_index = source.index("drain the queue without sleeping")
    recovery_index = source.index("_recover_stale_runs")
    assert drain_index < recovery_index
