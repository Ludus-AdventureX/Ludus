"""Task 9 r3 fast-fix owner tests: QA-P1 + QA-P2 closure (hard assertions).

QA report QA_TASK_09_IDEMPOTENCY_WIRE_R2_REPORT.md findings, fixed here:

- QA-P1 (§2.3): the amendment classification + analysis.amendment_required
  event must SURVIVE the 409 under the production ``get_session`` lifecycle
  (commit-before-raise). Owner suite previously could not see this through its
  shared-savepoint fixture, so these tests use a production-like
  one-fresh-session-per-request assembly with real commits.
- QA-P2 (§2.2): a same-key same-body duplicate that loses the concurrency race
  must REPLAY the winner's success (the RunNotResumable path now re-checks the
  idempotency record), never answer 409 for an idempotent hit.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import httpx
import pytest_asyncio
from fastapi import FastAPI, Path
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.analyses.models import AnalysisEvent, RunInterventionClassification
from app.analyses.repository import AnalysisRuntimeRepository
from app.analyses.routes import router as analyses_router
from app.db import get_database_url, get_session
from app.models import (
    DecisionCase,
    DecisionSubject,
    User,
    Workspace,
    WorkspaceMembership,
)
from app.security.envelope import register_error_handlers, workspace_not_found
from app.tenancy.context import (
    ALL_CAPABILITIES,
    WorkspaceContext,
    require_workspace_context,
)
from app.types import AnalysisRunStatus, FormalAnalysisLevel, WorkspaceRole

from runtime_world import FULL_SET

S = AnalysisRunStatus

RESOLUTION_BODY = {
    "payload": {
        "kind": "hard_constraint_confirmation",
        "confirmedConstraintIds": ["constraint_no_legal_advice"],
    }
}


@pytest_asyncio.fixture
async def prod_like_factory():
    engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _seed_needs_attention_world(factory) -> tuple[UUID, UUID, UUID]:
    """Commit (for real) a workspace + needs_attention run; return ids."""

    slug = f"r3-{uuid4().hex[:10]}"
    async with factory() as session:
        ws_id, user_id, subject_id, case_id = uuid4(), uuid4(), uuid4(), uuid4()
        session.add(User(id=user_id, email=f"{slug}@example.test", password_hash="x"))
        await session.flush()
        session.add(Workspace(id=ws_id, name=f"ws-{slug}", created_by_user_id=user_id))
        await session.flush()
        session.add(
            WorkspaceMembership(
                id=uuid4(), workspace_id=ws_id, user_id=user_id, role=WorkspaceRole.OWNER
            )
        )
        session.add(
            DecisionSubject(
                id=subject_id, workspace_id=ws_id, name=f"subject-{slug}", slug=slug
            )
        )
        await session.flush()
        session.add(
            DecisionCase(
                decision_case_id=case_id,
                workspace_id=ws_id,
                decision_subject_id=subject_id,
                title=f"case-{slug}",
                decision_question="enter the rescue market?",
            )
        )
        await session.flush()

        repo = AnalysisRuntimeRepository(session)
        charter = await repo.create_charter_draft(
            workspace_id=ws_id,
            decision_subject_id=subject_id,
            decision_case_id=case_id,
            case_version=1,
            case_snapshot_hash="sha256:case",
            analysis_level=FormalAnalysisLevel.FULL,
            decision_question="enter the rescue market?",
            dossier_snapshot_version=1,
            dossier_snapshot_hash="sha256:dossier",
            method_id="hardtech-market-direction",
            method_version="1.1.0",
            method_content_hash="sha256:method",
            formal_analysis_allowed=True,
            required_strategic_lens_types=list(FULL_SET),
            allowed_connector_ids=["exa", "tavily"],
            budget={"max_model_calls": 20},
        )
        await repo.submit_charter(ws_id, charter.id)
        await repo.confirm_charter(ws_id, charter.id)
        run, created = await repo.create_queued_run(
            workspace_id=ws_id,
            charter_id=charter.id,
            idempotency_key=f"run-{uuid4().hex[:12]}",
            run_manifest_hash="sha256:manifest",
            cynefin_gate_result_id=uuid4(),
        )
        assert created
        run_id = run.analysis_run_id
        await repo.transition(ws_id, run_id, S.PLANNING)
        await repo.transition(ws_id, run_id, S.RETRIEVING)
        await repo.transition(ws_id, run_id, S.NEEDS_ATTENTION)
        await session.commit()
    return ws_id, user_id, run_id


def _build_prod_like_app(factory, memberships: dict[UUID, UUID]) -> FastAPI:
    """One FRESH session per request (mirrors ``app.db.get_session``)."""

    app = FastAPI(title="Ludus Task 9 r3 prod-like assembly")
    app.include_router(analyses_router)
    register_error_handlers(app)

    async def fake_context(
        workspace_id: UUID = Path(alias="workspaceId"),
    ) -> WorkspaceContext:
        user_id = memberships.get(workspace_id)
        if user_id is None:
            raise workspace_not_found()
        return WorkspaceContext(
            user_id=user_id,
            workspace_id=workspace_id,
            role=WorkspaceRole.OWNER,
            capabilities=ALL_CAPABILITIES,
        )

    async def prod_like_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[require_workspace_context] = fake_context
    app.dependency_overrides[get_session] = prod_like_session
    return app


def _url(ws_id: UUID, run_id: UUID) -> str:
    return f"/api/workspaces/{ws_id}/analyses/{run_id}/resolutions"


AMENDMENT_BODY = {
    **RESOLUTION_BODY,
    "proposedCharterChanges": {"strategic_lens_set": FULL_SET[:-1]},
}


# --- QA-P1: §2.3 amendment durability -------------------------------------------------


async def test_amendment_classification_survives_the_409(prod_like_factory) -> None:
    factory = prod_like_factory
    ws_id, user_id, run_id = await _seed_needs_attention_world(factory)
    app = _build_prod_like_app(factory, {ws_id: user_id})

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            _url(ws_id, run_id),
            headers={"Idempotency-Key": f"idem-{uuid4().hex[:12]}"},
            json=AMENDMENT_BODY,
        )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "RUN_AMENDMENT_REQUIRED"

    # a brand-new session (request scope is gone) must still see both rows.
    async with factory() as session:
        classifications = list(
            await session.scalars(
                select(RunInterventionClassification).where(
                    RunInterventionClassification.analysis_run_id == run_id
                )
            )
        )
        assert len(classifications) == 1
        assert classifications[0].result == "amendment"
        assert classifications[0].changed_frozen_fields == ["strategic_lens_set"]
        assert str(classifications[0].id) == error["details"]["classificationId"]

        events = list(
            await session.scalars(
                select(AnalysisEvent).where(
                    AnalysisEvent.analysis_run_id == run_id,
                    AnalysisEvent.type == "analysis.amendment_required",
                )
            )
        )
        assert len(events) == 1
        assert events[0].payload["changedFrozenFields"] == ["strategic_lens_set"]


async def test_repeated_amendments_append_only(prod_like_factory) -> None:
    factory = prod_like_factory
    ws_id, user_id, run_id = await _seed_needs_attention_world(factory)
    app = _build_prod_like_app(factory, {ws_id: user_id})

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        for _ in range(2):
            response = await client.post(
                _url(ws_id, run_id),
                headers={"Idempotency-Key": f"idem-{uuid4().hex[:12]}"},
                json=AMENDMENT_BODY,
            )
            assert response.status_code == 409

    async with factory() as session:
        count = int(
            await session.scalar(
                select(func.count())
                .select_from(RunInterventionClassification)
                .where(RunInterventionClassification.analysis_run_id == run_id)
            )
            or 0
        )
        assert count == 2  # append-only ledger, one row per attempt


# --- QA-P2: race loser replays --------------------------------------------------------


async def test_dual_connection_same_key_race_both_sides_get_the_success(
    prod_like_factory,
) -> None:
    factory = prod_like_factory
    ws_id, user_id, run_id = await _seed_needs_attention_world(factory)
    app = _build_prod_like_app(factory, {ws_id: user_id})
    key = f"race-{uuid4().hex[:12]}"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        first, second = await asyncio.gather(
            client.post(_url(ws_id, run_id), headers={"Idempotency-Key": key}, json=RESOLUTION_BODY),
            client.post(_url(ws_id, run_id), headers={"Idempotency-Key": key}, json=RESOLUTION_BODY),
        )

    # strict §2.2: BOTH duplicates answer the original success.
    assert first.status_code == 200, (first.text, second.text)
    assert second.status_code == 200, (first.text, second.text)
    assert first.json()["data"] == second.json()["data"]
    replays = [
        response.json().get("meta", {}).get("idempotencyReplay") is True
        for response in (first, second)
    ]
    assert sorted(replays) == [False, True]


async def test_not_resumable_is_preserved_for_a_fresh_key(prod_like_factory) -> None:
    """The QA-P2 replay re-check must not shadow the specific code: a NEW key
    on an already-resumed run is a real client error, not an idempotent hit."""

    factory = prod_like_factory
    ws_id, user_id, run_id = await _seed_needs_attention_world(factory)
    app = _build_prod_like_app(factory, {ws_id: user_id})

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        winner = await client.post(
            _url(ws_id, run_id),
            headers={"Idempotency-Key": f"idem-{uuid4().hex[:12]}"},
            json=RESOLUTION_BODY,
        )
        assert winner.status_code == 200
        fresh_key = await client.post(
            _url(ws_id, run_id),
            headers={"Idempotency-Key": f"idem-{uuid4().hex[:12]}"},
            json=RESOLUTION_BODY,
        )
    assert fresh_key.status_code == 409
    assert fresh_key.json()["error"]["code"] == "ANALYSIS_RUN_NOT_RESUMABLE"
