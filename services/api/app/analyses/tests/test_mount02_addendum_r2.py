"""MOUNT-02 addendum (r2) acceptance: deliverables ⑥ and ⑦.

⑦ P3 combination-only fix: the run-create §2.2 replay compare set now includes
``supersedesAnalysisRunId`` — a reused key whose body only changes the
supersedes target answers 409 IDEMPOTENCY_CONFLICT (previously it silently
replayed the original run). An exact replay including a non-null supersedes
target still replays with ``meta.idempotencyReplay: true``.

⑥ ``strategicLensArtifactIds`` passthrough pinning: the run-status projection
forwards the persisted ids VERBATIM (no route-layer UUID parsing, casing
normalization, dedup, or reordering). The Task 10 ``audit_full_run_lens_set``
consumer (A1+A2 joint wave, not yet on main) relies on exact-equality
semantics — the QA red-light meaning from Addendum A1: a route-layer
normalization would mask a persisted-set corruption the audit must catch.
Negative acceptance: hostile non-UUID strings survive the projection unchanged
and never 500.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import httpx
import pytest_asyncio
from fastapi import FastAPI, Path

from app.analyses.routes import router as analyses_router
from app.auth.config import get_auth_settings
from app.db import get_session
from app.security.envelope import register_error_handlers, workspace_not_found
from app.tenancy.context import (
    ALL_CAPABILITIES,
    WorkspaceContext,
    require_workspace_context,
)
from app.types import WorkspaceRole

from runtime_world import RuntimeWorld, make_confirmed_charter, make_queued_run


def _build_app(session, memberships: dict[UUID, UUID]) -> FastAPI:
    app = FastAPI(title="Ludus MOUNT-02 addendum r2 assembly")
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
async def client(session, world):
    app = _build_app(session, {world.workspace_id: world.user_id})
    settings = get_auth_settings()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://addendum.test",
        headers={
            "Origin": "http://addendum.test",
            settings.csrf_header_name: "r2-csrf",
        },
        cookies={settings.csrf_cookie_name: "r2-csrf"},
    ) as http_client:
        yield http_client


def _ws(world: RuntimeWorld) -> str:
    return f"/api/workspaces/{world.workspace_id}"


# --- ⑦ supersedesAnalysisRunId joins the replay compare set -------------------


async def test_same_key_supersedes_only_change_conflicts(client, session, world):
    charter = await make_confirmed_charter(session, world)
    body = {"cynefinGateResultId": str(uuid4()), "runManifestHash": "sha256:m1"}
    headers = {"Idempotency-Key": "r2-supersedes-conflict"}
    first = await client.post(
        f"{_ws(world)}/analysis-charters/{charter.id}/runs", json=body, headers=headers
    )
    assert first.status_code == 201, first.text

    # Same key, same body EXCEPT a supersedes target appears: must be 409,
    # never a silent replay of the original run (the pre-fix behavior).
    conflict = await client.post(
        f"{_ws(world)}/analysis-charters/{charter.id}/runs",
        json={**body, "supersedesAnalysisRunId": str(uuid4())},
        headers=headers,
    )
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


async def test_exact_replay_with_supersedes_still_replays(client, session, world):
    charter = await make_confirmed_charter(session, world)

    seed = await client.post(
        f"{_ws(world)}/analysis-charters/{charter.id}/runs",
        json={"cynefinGateResultId": str(uuid4()), "runManifestHash": "sha256:m2"},
        headers={"Idempotency-Key": "r2-seed"},
    )
    assert seed.status_code == 201, seed.text
    seed_run_id = seed.json()["data"]["analysisRunId"]
    cancelled = await client.post(
        f"{_ws(world)}/analyses/{seed_run_id}/cancel",
        headers={"Idempotency-Key": "r2-seed-cancel"},
    )
    assert cancelled.status_code == 200, cancelled.text

    body = {
        "cynefinGateResultId": str(uuid4()),
        "runManifestHash": "sha256:m3",
        "supersedesAnalysisRunId": seed_run_id,
    }
    headers = {"Idempotency-Key": "r2-supersedes-replay"}
    created = await client.post(
        f"{_ws(world)}/analysis-charters/{charter.id}/runs", json=body, headers=headers
    )
    assert created.status_code == 201, created.text

    replay = await client.post(
        f"{_ws(world)}/analysis-charters/{charter.id}/runs", json=body, headers=headers
    )
    assert replay.status_code == 201, replay.text
    assert replay.json()["meta"]["idempotencyReplay"] is True
    assert (
        replay.json()["data"]["analysisRunId"]
        == created.json()["data"]["analysisRunId"]
    )
    assert replay.json()["data"]["supersedesAnalysisRunId"] == seed_run_id


# --- ⑥ strategicLensArtifactIds verbatim passthrough pinning ------------------


async def test_lens_artifact_ids_pass_through_verbatim(client, session, world):
    """The projection must not parse, normalize, dedup, or reorder the ids.

    Exact equality is what audit_full_run_lens_set (Task 10, A1+A2 wave)
    compares against; any route-layer normalization would mask a persisted-set
    corruption (A1 QA red-light semantics).
    """

    _charter, run = await make_queued_run(session, world)
    hostile = [
        "NOT-A-UUID",
        "0F92B172-C5D9-3153-1A1D-450254655ED8",  # uppercase must stay uppercase
        "dup",
        "dup",  # duplicates must survive
        str(uuid4()),
    ]
    run.strategic_lens_artifact_ids = list(hostile)
    await session.flush()

    response = await client.get(f"{_ws(world)}/analyses/{run.analysis_run_id}")
    assert response.status_code == 200, response.text
    assert response.json()["data"]["strategicLensArtifactIds"] == hostile
