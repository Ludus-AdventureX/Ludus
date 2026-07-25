"""QA r2 adversarial probes: Task 9 idempotency wire protocol (candidate e403c66).

QA-owned file (codex/qa-task-09-idempotency-wire-r2). Uses a PRODUCTION-LIKE
session lifecycle (fresh session per request from a sessionmaker, real
commits/rollbacks — unlike the owner suite's shared-savepoint fixture) so the
probes exercise what the mounted app would actually do:

- dual-connection concurrent same-key race (CCR-20260725-ANALYSIS-01 §2.2)
- workspace scoping of idempotency records (anti cross-tenant replay)
- key reuse after a non-success (amendment 409) response
- §2.3 amendment classification durability under the real session lifecycle
- backstop ANALYSIS_TRANSITION_INVALID never shadows RUN_AMENDMENT_REQUIRED
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

from app.analyses.models import RunInterventionClassification, RunResolution
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

S = AnalysisRunStatus

FULL_SET = [
    "porter_five_forces",
    "pre_mortem",
    "counterparty_response_matrix",
    "scenario_planning",
    "meadows_leverage_points",
]
RESOLUTION_BODY = {
    "payload": {
        "kind": "hard_constraint_confirmation",
        "confirmedConstraintIds": ["constraint_no_legal_advice"],
    }
}


@pytest_asyncio.fixture
async def qa_engine():
    engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def qa_sessionmaker(qa_engine):
    return async_sessionmaker(qa_engine, expire_on_commit=False)


async def _seed_needs_attention_world(factory) -> tuple[UUID, UUID, UUID]:
    """Commit (for real) a workspace + needs_attention run; return ids."""

    slug = f"qa-{uuid4().hex[:10]}"
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
    """One FRESH session per request with real commit/rollback semantics
    (mirrors ``app.db.get_session``), unlike the owner suite's shared session."""

    app = FastAPI(title="Ludus QA Task 9 r2 prod-like assembly")
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


async def _count(factory, model, run_id: UUID) -> int:
    async with factory() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(model)
                .where(model.analysis_run_id == run_id)
            )
            or 0
        )


# --- §2.2 dual-connection concurrent same-key race -----------------------------------


async def test_dual_connection_same_key_race_appends_exactly_one_resolution(
    qa_sessionmaker,
) -> None:
    """Hard invariants that must hold under a real two-connection race:
    exactly one RunResolution row, at least one 200, and the loser answers a
    documented non-corrupting response (200 replay or 409 specific code)."""

    factory = qa_sessionmaker
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

    statuses = sorted([first.status_code, second.status_code])
    assert statuses[0] == 200, (first.text, second.text)
    winner, loser = (first, second) if first.status_code == 200 else (second, first)
    if loser.status_code == 200:
        # strict §2.2 outcome: the loser replayed the winner's success.
        assert loser.json().get("meta", {}).get("idempotencyReplay") is True
        assert loser.json()["data"] == winner.json()["data"]
    else:
        # tolerated non-corrupting outcome: a specific documented 409 (the
        # loser blocked on the run row and saw the resumed state). Strict §2.2
        # replay for this window is asserted by the xfail probe below.
        assert loser.status_code == 409
        assert loser.json()["error"]["code"] == "ANALYSIS_RUN_NOT_RESUMABLE"

    assert await _count(factory, RunResolution, run_id) == 1


# Promoted from xfail (QA-P2) after the r3 fast-fix 628f672: strict §2.2 — a
# concurrent same-key same-body duplicate ALWAYS replays the original success
# (the RunNotResumable handler now re-checks the idempotency record).
async def test_dual_connection_same_key_race_loser_replays_strict_ccr(
    qa_sessionmaker,
) -> None:
    factory = qa_sessionmaker
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
    assert first.status_code == 200
    assert second.status_code == 200
    replays = [
        response.json().get("meta", {}).get("idempotencyReplay") is True
        for response in (first, second)
    ]
    assert sorted(replays) == [False, True]


# --- workspace scoping ----------------------------------------------------------------


async def test_idempotency_records_are_workspace_scoped(qa_sessionmaker) -> None:
    factory = qa_sessionmaker
    ws_a, user_a, run_a = await _seed_needs_attention_world(factory)
    ws_b, user_b, run_b = await _seed_needs_attention_world(factory)
    app = _build_prod_like_app(factory, {ws_a: user_a, ws_b: user_b})
    shared_key = f"shared-{uuid4().hex[:12]}"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        first = await client.post(
            _url(ws_a, run_a), headers={"Idempotency-Key": shared_key}, json=RESOLUTION_BODY
        )
        assert first.status_code == 200, first.text
        # same key, DIFFERENT workspace: fresh success — never a cross-tenant
        # replay (and never IDEMPOTENCY_CONFLICT despite a different implied
        # scope), because records are workspace-scoped.
        second = await client.post(
            _url(ws_b, run_b), headers={"Idempotency-Key": shared_key}, json=RESOLUTION_BODY
        )
        assert second.status_code == 200, second.text
        assert "meta" not in second.json()
        assert second.json()["data"]["resolutionId"] != first.json()["data"]["resolutionId"]


# --- key reuse after a non-success response --------------------------------------------


async def test_amendment_409_does_not_consume_the_idempotency_key(
    qa_sessionmaker,
) -> None:
    """Only SUCCESS responses are recorded (§2.2 defines replay of the original
    success); after an amendment 409 the same key must still be usable for the
    corrected resolution request."""

    factory = qa_sessionmaker
    ws_id, user_id, run_id = await _seed_needs_attention_world(factory)
    app = _build_prod_like_app(factory, {ws_id: user_id})
    key = f"reuse-{uuid4().hex[:12]}"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        amendment = await client.post(
            _url(ws_id, run_id),
            headers={"Idempotency-Key": key},
            json={
                **RESOLUTION_BODY,
                "proposedCharterChanges": {"strategic_lens_set": FULL_SET[:-1]},
            },
        )
        assert amendment.status_code == 409
        assert amendment.json()["error"]["code"] == "RUN_AMENDMENT_REQUIRED"

        corrected = await client.post(
            _url(ws_id, run_id), headers={"Idempotency-Key": key}, json=RESOLUTION_BODY
        )
        assert corrected.status_code == 200, corrected.text
        assert "meta" not in corrected.json()


# --- §5 backstop must not shadow the amendment code -------------------------------------


async def test_amendment_code_not_shadowed_by_transition_backstop(
    qa_sessionmaker,
) -> None:
    factory = qa_sessionmaker
    ws_id, user_id, run_id = await _seed_needs_attention_world(factory)
    app = _build_prod_like_app(factory, {ws_id: user_id})

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            _url(ws_id, run_id),
            headers={"Idempotency-Key": f"idem-{uuid4().hex[:12]}"},
            json={
                **RESOLUTION_BODY,
                "proposedCharterChanges": {"strategic_lens_set": FULL_SET[:-1]},
            },
        )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RUN_AMENDMENT_REQUIRED"


# --- §2.3 amendment classification durability (Phase B r1 scope) ------------------------


# Promoted from xfail (QA-P1) after the r3 fast-fix 628f672: §2.3 — the
# amendment classification and its event are committed before the 409 and
# survive the production get_session lifecycle.
async def test_amendment_classification_is_durable_under_production_session(
    qa_sessionmaker,
) -> None:
    factory = qa_sessionmaker
    ws_id, user_id, run_id = await _seed_needs_attention_world(factory)
    app = _build_prod_like_app(factory, {ws_id: user_id})

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post(
            _url(ws_id, run_id),
            headers={"Idempotency-Key": f"idem-{uuid4().hex[:12]}"},
            json={
                **RESOLUTION_BODY,
                "proposedCharterChanges": {"strategic_lens_set": FULL_SET[:-1]},
            },
        )
    assert response.status_code == 409
    # §2.3: the amendment classification must survive the 409 response.
    assert await _count(factory, RunInterventionClassification, run_id) == 1
