"""Task 9 r2 fast-fix owner tests: idempotency wire protocol alignment.

Asserts the four CCR-20260725-ANALYSIS-01 items this fast-fix delivers
(contract consumed read-only from codex/ccr-guest-analysis-contracts
@ d6675693fd2b7709d9ed4756489e633c49c869ee):

1. §2.1 — the resolutions endpoint requires the ``Idempotency-Key`` HTTP
   header; the key never travels in the request body.
2. §2.2 — same key + different normalized body ⇒ 409 IDEMPOTENCY_CONFLICT.
3. §2.2 — same key + same body ⇒ replay of the original success with
   ``meta.idempotencyReplay: true`` and no second resolution row.
4. §5 — ANALYSIS_TRANSITION_INVALID is the registered 409 backstop for
   API-reachable out-of-matrix transitions and never shadows specific codes.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import httpx
import pytest_asyncio
from fastapi import FastAPI, Path
from sqlalchemy import func, select

from app.analyses.repository import (
    RESOLUTIONS_ROUTE_KEY,
    AnalysisRuntimeRepository,
)
from app.analyses.models import RunResolution
from app.analyses.routes import router as analyses_router
from app.analyses.state_machine import InvalidTransition
from app.db import get_session
from app.models import IdempotencyRecord
from app.security.envelope import register_error_handlers, workspace_not_found
from app.tenancy.context import (
    ALL_CAPABILITIES,
    WorkspaceContext,
    require_workspace_context,
)
from app.types import AnalysisRunStatus, WorkspaceRole

from runtime_world import make_queued_run

S = AnalysisRunStatus

RESOLUTION_BODY = {
    "payload": {
        "kind": "hard_constraint_confirmation",
        "confirmedConstraintIds": ["constraint_no_legal_advice"],
    }
}
DIFFERENT_BODY = {
    "payload": {
        "kind": "hard_constraint_confirmation",
        "confirmedConstraintIds": ["constraint_budget_cap"],
    }
}


def _build_app(session, memberships: dict[UUID, UUID]) -> FastAPI:
    app = FastAPI(title="Ludus QA Task 9 idempotency assembly")
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

    async def override_session():
        yield session

    app.dependency_overrides[require_workspace_context] = fake_context
    app.dependency_overrides[get_session] = override_session
    return app


@pytest_asyncio.fixture
async def client_world(session, world):
    app = _build_app(session, {world.workspace_id: world.user_id})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client, world


async def _seed_needs_attention_run(session, world):
    repo = AnalysisRuntimeRepository(session)
    _, run = await make_queued_run(session, world)
    ws, run_id = world.workspace_id, run.analysis_run_id
    await repo.transition(ws, run_id, S.PLANNING)
    await repo.transition(ws, run_id, S.RETRIEVING)
    await repo.transition(ws, run_id, S.NEEDS_ATTENTION)
    return run


def _url(world, run_id: UUID) -> str:
    return f"/api/workspaces/{world.workspace_id}/analyses/{run_id}/resolutions"


async def _count_resolutions(session, run_id: UUID) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(RunResolution)
            .where(RunResolution.analysis_run_id == run_id)
        )
        or 0
    )


# --- item 1: mandatory Idempotency-Key header --------------------------------------


async def test_resolution_with_header_succeeds_and_persists_record(
    session, client_world
) -> None:
    client, world = client_world
    run = await _seed_needs_attention_run(session, world)
    key = f"idem-{uuid4().hex[:12]}"

    response = await client.post(
        _url(world, run.analysis_run_id),
        headers={"Idempotency-Key": key},
        json=RESOLUTION_BODY,
    )
    assert response.status_code == 200, response.text
    envelope = response.json()
    assert envelope["ok"] is True
    # fresh success carries the frozen §2.1 envelope incl. eventId, no meta.
    assert envelope["eventId"]
    assert "meta" not in envelope
    assert envelope["data"]["status"] == "retrieving"

    record = await session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.workspace_id == world.workspace_id,
            IdempotencyRecord.route_key == RESOLUTIONS_ROUTE_KEY,
            IdempotencyRecord.idempotency_key == key,
        )
    )
    assert record is not None
    assert record.resource_type == "run_resolution"
    assert str(record.resource_id) == envelope["data"]["resolutionId"]
    assert record.http_status == 200
    assert record.response_kind == "success"
    assert record.normalized_request_hash.startswith("sha256:")
    assert record.expires_at > record.created_at


async def test_resolution_without_header_is_rejected_422(
    session, client_world
) -> None:
    client, world = client_world
    run = await _seed_needs_attention_run(session, world)

    response = await client.post(_url(world, run.analysis_run_id), json=RESOLUTION_BODY)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_FAILED"
    assert error["details"]["header"] == "Idempotency-Key"
    # rejection happened before any state change: run untouched, no resolution.
    assert await _count_resolutions(session, run.analysis_run_id) == 0


async def test_resolution_key_must_not_travel_in_body(session, client_world) -> None:
    client, world = client_world
    run = await _seed_needs_attention_run(session, world)

    for body_key in ("idempotencyKey", "idempotency_key"):
        response = await client.post(
            _url(world, run.analysis_run_id),
            headers={"Idempotency-Key": f"idem-{uuid4().hex[:12]}"},
            json={**RESOLUTION_BODY, body_key: "smuggled-key"},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_FAILED"


async def test_resolution_header_length_bound_follows_sim_02a_precedent(
    session, client_world
) -> None:
    client, world = client_world
    run = await _seed_needs_attention_run(session, world)

    over_long = await client.post(
        _url(world, run.analysis_run_id),
        headers={"Idempotency-Key": "k" * 201},
        json=RESOLUTION_BODY,
    )
    assert over_long.status_code == 422
    assert over_long.json()["error"]["code"] == "VALIDATION_FAILED"

    blank = await client.post(
        _url(world, run.analysis_run_id),
        headers={"Idempotency-Key": "   "},
        json=RESOLUTION_BODY,
    )
    assert blank.status_code == 422
    assert blank.json()["error"]["code"] == "VALIDATION_FAILED"


# --- items 2+3: replay vs conflict ---------------------------------------------------


async def test_same_key_same_body_replays_with_meta_flag(
    session, client_world
) -> None:
    client, world = client_world
    run = await _seed_needs_attention_run(session, world)
    key = f"idem-{uuid4().hex[:12]}"
    url = _url(world, run.analysis_run_id)

    first = await client.post(url, headers={"Idempotency-Key": key}, json=RESOLUTION_BODY)
    assert first.status_code == 200, first.text
    original = first.json()

    replay = await client.post(url, headers={"Idempotency-Key": key}, json=RESOLUTION_BODY)
    assert replay.status_code == 200  # original HTTP status
    replayed = replay.json()
    assert replayed["meta"] == {"idempotencyReplay": True}
    # same body: data + eventId byte-identical to the original success.
    assert replayed["data"] == original["data"]
    assert replayed["eventId"] == original["eventId"]
    # replay appended nothing: still exactly one resolution row.
    assert await _count_resolutions(session, run.analysis_run_id) == 1
    # the replay is not an ANALYSIS_RUN_NOT_RESUMABLE error even though the
    # run already resumed (an idempotent hit is never expressed as an error).
    assert replayed["ok"] is True


async def test_same_key_body_normalization_ignores_key_order(
    session, client_world
) -> None:
    client, world = client_world
    run = await _seed_needs_attention_run(session, world)
    key = f"idem-{uuid4().hex[:12]}"
    url = _url(world, run.analysis_run_id)

    first = await client.post(url, headers={"Idempotency-Key": key}, json=RESOLUTION_BODY)
    assert first.status_code == 200
    reordered = {
        "payload": {
            "confirmedConstraintIds": ["constraint_no_legal_advice"],
            "kind": "hard_constraint_confirmation",
        }
    }
    replay = await client.post(url, headers={"Idempotency-Key": key}, json=reordered)
    assert replay.status_code == 200
    assert replay.json()["meta"] == {"idempotencyReplay": True}


async def test_same_key_different_body_conflicts_409(session, client_world) -> None:
    client, world = client_world
    run = await _seed_needs_attention_run(session, world)
    key = f"idem-{uuid4().hex[:12]}"
    url = _url(world, run.analysis_run_id)

    first = await client.post(url, headers={"Idempotency-Key": key}, json=RESOLUTION_BODY)
    assert first.status_code == 200

    conflict = await client.post(
        url, headers={"Idempotency-Key": key}, json=DIFFERENT_BODY
    )
    assert conflict.status_code == 409
    error = conflict.json()["error"]
    assert error["code"] == "IDEMPOTENCY_CONFLICT"
    # the conflicting request appended nothing.
    assert await _count_resolutions(session, run.analysis_run_id) == 1


async def test_different_key_is_not_a_replay(session, client_world) -> None:
    client, world = client_world
    run = await _seed_needs_attention_run(session, world)
    url = _url(world, run.analysis_run_id)

    first = await client.post(
        url, headers={"Idempotency-Key": f"idem-{uuid4().hex[:12]}"}, json=RESOLUTION_BODY
    )
    assert first.status_code == 200
    # a NEW key on a run that already resumed hits the specific state guard,
    # not the idempotency layer.
    second = await client.post(
        url, headers={"Idempotency-Key": f"idem-{uuid4().hex[:12]}"}, json=RESOLUTION_BODY
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "ANALYSIS_RUN_NOT_RESUMABLE"


# --- item 4: ANALYSIS_TRANSITION_INVALID backstop -----------------------------------


async def test_transition_invalid_backstop_on_resolutions(
    session, client_world, monkeypatch
) -> None:
    client, world = client_world
    run = await _seed_needs_attention_run(session, world)

    async def raise_invalid_transition(self, *args, **kwargs):
        raise InvalidTransition("needs_attention", "analyzing", "race lost")

    # Simulate the §5 documented race: the state check passed but the act
    # surfaced an out-of-matrix transition.
    monkeypatch.setattr(
        AnalysisRuntimeRepository, "classify_and_resolve", raise_invalid_transition
    )
    response = await client.post(
        _url(world, run.analysis_run_id),
        headers={"Idempotency-Key": f"idem-{uuid4().hex[:12]}"},
        json=RESOLUTION_BODY,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ANALYSIS_TRANSITION_INVALID"


async def test_transition_invalid_backstop_on_cancel(
    session, client_world, monkeypatch
) -> None:
    client, world = client_world
    run = await _seed_needs_attention_run(session, world)

    async def raise_invalid_transition(self, *args, **kwargs):
        raise InvalidTransition("retrieving", "cancelled", "race lost")

    monkeypatch.setattr(AnalysisRuntimeRepository, "cancel", raise_invalid_transition)
    response = await client.post(
        f"/api/workspaces/{world.workspace_id}/analyses/{run.analysis_run_id}/cancel",
        json={"reason": "user_cancelled"},
        headers={"Idempotency-Key": "cancel-race"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ANALYSIS_TRANSITION_INVALID"


async def test_backstop_never_shadows_specific_codes(session, client_world) -> None:
    client, world = client_world
    repo = AnalysisRuntimeRepository(session)
    _, run = await make_queued_run(session, world)
    ws, run_id = world.workspace_id, run.analysis_run_id

    # queued run: the specific ANALYSIS_RUN_NOT_RESUMABLE answers, never the
    # generic backstop.
    not_resumable = await client.post(
        _url(world, run_id),
        headers={"Idempotency-Key": f"idem-{uuid4().hex[:12]}"},
        json=RESOLUTION_BODY,
    )
    assert not_resumable.status_code == 409
    assert not_resumable.json()["error"]["code"] == "ANALYSIS_RUN_NOT_RESUMABLE"

    # blocked run: cancel answers the specific ANALYSIS_RUN_NOT_CANCELLABLE.
    for stage in (
        S.PLANNING,
        S.RETRIEVING,
        S.ANALYZING,
        S.CRITICIZING,
        S.SYNTHESIZING,
        S.VALIDATING,
    ):
        await repo.transition(ws, run_id, stage)
    await repo.transition(ws, run_id, S.BLOCKED)
    guarded = await client.post(
        f"/api/workspaces/{ws}/analyses/{run_id}/cancel",
        json={"reason": "user_cancelled"},
        headers={"Idempotency-Key": "cancel-guarded-backstop"},
    )
    assert guarded.status_code == 409
    assert guarded.json()["error"]["code"] == "ANALYSIS_RUN_NOT_CANCELLABLE"
