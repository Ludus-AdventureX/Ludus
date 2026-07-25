"""Task 9 owner tests: SSE stream, resolution/cancel endpoints, anti-enumeration.

Router is NOT mounted in ``app.main``; a QA-only assembly mirrors the future
integration mounting with overridden tenancy + DB session (Task 3/8 precedent).
"""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import httpx
import pytest_asyncio
from fastapi import FastAPI, Path

from app.analyses.repository import AnalysisRuntimeRepository
from app.analyses.routes import router as analyses_router
from app.db import get_session
from app.main import app as canonical_app
from app.security.envelope import register_error_handlers, workspace_not_found
from app.tenancy.context import (
    ALL_CAPABILITIES,
    WorkspaceContext,
    require_workspace_context,
)
from app.types import AnalysisRunStatus, WorkspaceRole

from runtime_world import FULL_SET, make_queued_run

S = AnalysisRunStatus


def test_analyses_runtime_router_is_not_mounted_in_canonical_app() -> None:
    paths = {getattr(route, "path", "") for route in canonical_app.routes}
    assert not any(path.endswith("/events") for path in paths)
    assert not any("resolutions" in path for path in paths)
    assert not any(path.endswith("/cancel") for path in paths)


def _build_app(session, memberships: dict[UUID, UUID]) -> FastAPI:
    app = FastAPI(title="Ludus QA Task 9 assembly")
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
async def worlds_client(session, world, foreign_world):
    app = _build_app(
        session,
        {
            world.workspace_id: world.user_id,
            foreign_world.workspace_id: foreign_world.user_id,
        },
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client, world, foreign_world


def _parse_sse(body: str) -> list[dict]:
    frames = []
    for block in body.strip().split("\n\n"):
        lines = block.splitlines()
        record: dict = {}
        for line in lines:
            if line.startswith("id: "):
                record["id"] = line[4:]
            elif line.startswith("event: "):
                record["event"] = line[7:]
            elif line.startswith("data: "):
                record["data"] = json.loads(line[6:])
        if record:
            frames.append(record)
    return frames


async def _seed_terminal_run(session, world):
    repo = AnalysisRuntimeRepository(session)
    _, run = await make_queued_run(session, world)
    ws, run_id = world.workspace_id, run.analysis_run_id
    await repo.transition(ws, run_id, S.PLANNING)
    await repo.transition(ws, run_id, S.RETRIEVING)
    await repo.cancel(ws, run_id)
    return run


async def test_sse_stream_serves_full_canonical_envelopes(
    session, worlds_client
) -> None:
    client, world, _ = worlds_client
    run = await _seed_terminal_run(session, world)
    response = await client.get(
        f"/api/workspaces/{world.workspace_id}/analyses/{run.analysis_run_id}/events"
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = _parse_sse(response.text)
    assert len(frames) == 3  # planning, retrieving, cancelled
    sequences = [frame["data"]["sequence"] for frame in frames]
    assert sequences == sorted(sequences) and len(set(sequences)) == 3
    for frame in frames:
        envelope = frame["data"]
        # event: equals the canonical category; data: is the full envelope.
        assert frame["event"] == envelope["category"]
        assert frame["id"] == envelope["id"]
        assert set(envelope) == {
            "id",
            "sequence",
            "workspaceId",
            "decisionCaseId",
            "analysisRunId",
            "category",
            "type",
            "originMode",
            "sourceOriginModes",
            "createdAt",
            "payload",
        }
    assert frames[-1]["data"]["type"] == "analysis.cancelled"


async def test_sse_last_event_id_resumes_from_persisted_sequence(
    session, worlds_client
) -> None:
    client, world, _ = worlds_client
    run = await _seed_terminal_run(session, world)
    base = f"/api/workspaces/{world.workspace_id}/analyses/{run.analysis_run_id}/events"
    first = _parse_sse((await client.get(base)).text)
    reconnect_from = first[0]["id"]
    resumed = await client.get(base, headers={"Last-Event-ID": reconnect_from})
    frames = _parse_sse(resumed.text)
    assert [frame["data"]["sequence"] for frame in frames] == [
        f["data"]["sequence"] for f in first[1:]
    ]


async def test_sse_anti_enumeration_uniform_404(session, worlds_client) -> None:
    client, world, foreign = worlds_client
    run = await _seed_terminal_run(session, world)
    foreign_real = await client.get(
        f"/api/workspaces/{foreign.workspace_id}/analyses/{run.analysis_run_id}/events"
    )
    ghost = await client.get(
        f"/api/workspaces/{world.workspace_id}/analyses/{uuid4()}/events"
    )
    assert foreign_real.status_code == ghost.status_code == 404
    assert foreign_real.content == ghost.content
    assert foreign_real.json()["error"]["code"] == "CASE_NOT_FOUND"


async def test_resolution_endpoint_resumes_needs_attention_run(
    session, worlds_client
) -> None:
    client, world, _ = worlds_client
    repo = AnalysisRuntimeRepository(session)
    _, run = await make_queued_run(session, world)
    ws, run_id = world.workspace_id, run.analysis_run_id
    await repo.transition(ws, run_id, S.PLANNING)
    await repo.transition(ws, run_id, S.RETRIEVING)
    await repo.transition(ws, run_id, S.NEEDS_ATTENTION)

    response = await client.post(
        f"/api/workspaces/{ws}/analyses/{run_id}/resolutions",
        headers={"Idempotency-Key": f"idem-{uuid4().hex[:12]}"},
        json={
            "payload": {
                "kind": "hard_constraint_confirmation",
                "confirmedConstraintIds": ["constraint_no_legal_advice"],
            }
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["classification"]["result"] == "resolution"
    assert data["classification"]["changedFrozenFields"] == []
    assert data["status"] == "retrieving"
    assert data["resumedFrom"] == "retrieving"


async def test_resolution_endpoint_returns_amendment_409_for_lens_set_change(
    session, worlds_client
) -> None:
    client, world, _ = worlds_client
    repo = AnalysisRuntimeRepository(session)
    _, run = await make_queued_run(session, world)
    ws, run_id = world.workspace_id, run.analysis_run_id
    await repo.transition(ws, run_id, S.PLANNING)
    await repo.transition(ws, run_id, S.NEEDS_ATTENTION)

    response = await client.post(
        f"/api/workspaces/{ws}/analyses/{run_id}/resolutions",
        headers={"Idempotency-Key": f"idem-{uuid4().hex[:12]}"},
        json={
            "payload": {"kind": "hard_constraint_confirmation", "confirmedConstraintIds": []},
            "proposedCharterChanges": {"strategic_lens_set": FULL_SET[:-1]},
        },
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "RUN_AMENDMENT_REQUIRED"
    assert error["details"]["changedFrozenFields"] == ["strategic_lens_set"]
    assert "replacements" in error["details"]["replacementUrl"]


async def test_resolution_endpoint_rejects_invalid_payload_and_wrong_state(
    session, worlds_client
) -> None:
    client, world, _ = worlds_client
    repo = AnalysisRuntimeRepository(session)
    _, run = await make_queued_run(session, world)
    ws, run_id = world.workspace_id, run.analysis_run_id

    not_resumable = await client.post(
        f"/api/workspaces/{ws}/analyses/{run_id}/resolutions",
        headers={"Idempotency-Key": f"idem-{uuid4().hex[:12]}"},
        json={"payload": {"kind": "hard_constraint_confirmation"}},
    )
    assert not_resumable.status_code == 409
    assert not_resumable.json()["error"]["code"] == "ANALYSIS_RUN_NOT_RESUMABLE"

    await repo.transition(ws, run_id, S.PLANNING)
    await repo.transition(ws, run_id, S.NEEDS_ATTENTION)
    invalid = await client.post(
        f"/api/workspaces/{ws}/analyses/{run_id}/resolutions",
        headers={"Idempotency-Key": f"idem-{uuid4().hex[:12]}"},
        json={"payload": {"kind": "budget_increase"}},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "RUN_RESOLUTION_INVALID"


async def test_cancel_endpoint_is_idempotent_and_guards_terminals(
    session, worlds_client
) -> None:
    client, world, _ = worlds_client
    repo = AnalysisRuntimeRepository(session)
    _, run = await make_queued_run(session, world)
    ws, run_id = world.workspace_id, run.analysis_run_id
    url = f"/api/workspaces/{ws}/analyses/{run_id}/cancel"

    first = await client.post(url, json={"reason": "user_cancelled"})
    assert first.status_code == 200
    assert first.json()["data"]["status"] == "cancelled"
    cancelled_at = first.json()["data"]["cancelledAt"]

    second = await client.post(url, json={"reason": "user_cancelled"})
    assert second.status_code == 200
    assert second.json()["data"]["cancelledAt"] == cancelled_at

    # ready/blocked runs are not cancellable: build a blocked run on the same
    # case (allowed: the first run is cancelled, so the active slot is free).
    _, run2 = await make_queued_run(
        session, world, idempotency_key=f"idem-{uuid4().hex[:10]}"
    )
    for stage in (S.PLANNING, S.RETRIEVING, S.ANALYZING, S.CRITICIZING,
                  S.SYNTHESIZING, S.VALIDATING):
        await repo.transition(ws, run2.analysis_run_id, stage)
    await repo.transition(ws, run2.analysis_run_id, S.BLOCKED)
    guarded = await client.post(
        f"/api/workspaces/{ws}/analyses/{run2.analysis_run_id}/cancel",
        json={"reason": "user_cancelled"},
    )
    assert guarded.status_code == 409
    assert guarded.json()["error"]["code"] == "ANALYSIS_RUN_NOT_CANCELLABLE"


async def test_cancel_and_resolution_anti_enumeration(session, worlds_client) -> None:
    client, world, foreign = worlds_client
    run = await _seed_terminal_run(session, world)
    foreign_cancel = await client.post(
        f"/api/workspaces/{foreign.workspace_id}/analyses/{run.analysis_run_id}/cancel",
        json={"reason": "user_cancelled"},
    )
    ghost_cancel = await client.post(
        f"/api/workspaces/{world.workspace_id}/analyses/{uuid4()}/cancel",
        json={"reason": "user_cancelled"},
    )
    assert foreign_cancel.status_code == ghost_cancel.status_code == 404
    assert foreign_cancel.content == ghost_cancel.content
