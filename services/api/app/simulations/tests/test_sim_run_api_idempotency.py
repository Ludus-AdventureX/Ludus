"""Owner verification for the SIM-02A Idempotency-Key runtime flow (§4).

Same harness as ``test_sim_run_api_routes``: real router + real DB flows, with
tenancy supplied through the documented context override. Covers header format
gating, replay identity, conflict detection (body and path-anchor variants),
key non-consumption on pre-persistence failures, run+record atomicity, the 48h
retention stamp, and the lost-concurrency-race service path.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import IdempotencyRecord
from app.simulations.idempotency import (
    RUN_CREATE_ROUTE_KEY,
    IdempotencyRaceError,
    build_idempotency_record,
    normalized_request_hash,
)
from app.simulations.service import SimulationRunService
from test_simulation_repository_service import (
    request_for,
    scoped_run_count,
    seed_world,
)
from test_sim_run_api_routes import (
    api_client,
    idem_headers,
    post_run,
    run_body,
    runs_url,
    scoped_record_count,
    world_and_client,
)

# --- header format gate (§4.3) ------------------------------------------------------------------


async def test_missing_or_malformed_key_is_422_and_not_consumed(session):
    world, _, app = await world_and_client(session, "idem-header-gate")
    async with api_client(app) as client:
        missing = await client.post(runs_url(world), json=run_body(world))
        oversized = await client.post(
            runs_url(world), json=run_body(world), headers=idem_headers("k" * 201)
        )
        non_ascii = await client.post(
            runs_url(world), json=run_body(world), headers=idem_headers("bad key\t")
        )

    for response in (missing, oversized, non_ascii):
        assert response.status_code == 422, response.text
        error = response.json()["error"]
        assert error["code"] == "VALIDATION_FAILED"
        assert error["details"]["errors"][0]["loc"] == ["header", "Idempotency-Key"]
    assert await scoped_record_count(session, world) == 0
    assert await scoped_run_count(session, world) == 0


# --- replay and conflict (§4.5-4.8) --------------------------------------------------------------


async def test_same_key_same_body_replays_committed_outcome_once(session):
    world, _, app = await world_and_client(session, "idem-replay")
    key = f"replay-{uuid4().hex}"
    async with api_client(app) as client:
        first = await post_run(client, world, key=key)
        second = await post_run(client, world, key=key)

    assert first.status_code == 201
    assert second.status_code == 201  # original terminal status replayed
    assert "meta" not in first.json()
    assert second.json()["meta"] == {"idempotencyReplay": True}
    assert second.json()["data"] == first.json()["data"]
    # Exactly ONE run and ONE record: the replay executed no engine work.
    assert await scoped_run_count(session, world) == 1
    assert await scoped_record_count(session, world) == 1


async def test_same_key_different_body_is_409_conflict_without_hash_echo(session):
    world, _, app = await world_and_client(session, "idem-conflict")
    key = f"conflict-{uuid4().hex}"
    async with api_client(app) as client:
        first = await post_run(client, world, key=key)
        conflicting = await post_run(client, world, key=key, maxSteps=13)

    assert first.status_code == 201
    assert conflicting.status_code == 409
    error = conflicting.json()["error"]
    assert error["code"] == "IDEMPOTENCY_CONFLICT"
    assert "details" not in error  # §4.8: no details beyond the code
    assert await scoped_run_count(session, world) == 1


async def test_same_key_on_a_different_graph_anchor_is_a_conflict(session):
    # §4.2: the path graphId enters the normalized hash, so reusing a key
    # against another graph is a different request, not a replay.
    world, _, app = await world_and_client(session, "idem-graph-anchor")
    key = f"anchor-{uuid4().hex}"
    async with api_client(app) as client:
        first = await post_run(client, world, key=key)
        moved = await client.post(
            runs_url(world, uuid4()), json=run_body(world), headers=idem_headers(key)
        )

    assert first.status_code == 201
    assert moved.status_code == 409
    assert moved.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


async def test_failed_request_never_consumes_the_key(session):
    world, _, app = await world_and_client(session, "idem-not-consumed")
    key = f"unconsumed-{uuid4().hex}"
    async with api_client(app) as client:
        # 404 scope denial: ghost graphVersionId, nothing persisted (§4.6).
        denied = await post_run(client, world, key=key, graphVersionId=str(uuid4()))
        assert denied.status_code == 404
        assert await scoped_record_count(session, world) == 0

        # The SAME key is then usable for a fresh (non-replay) success.
        fresh = await post_run(client, world, key=key)

    assert fresh.status_code == 201
    assert "meta" not in fresh.json()
    assert await scoped_run_count(session, world) == 1


# --- atomicity and retention (§4.4) ---------------------------------------------------------------


async def test_run_and_record_commit_in_one_transaction_with_48h_retention(session):
    world, _, app = await world_and_client(session, "idem-atomic")
    key = f"atomic-{uuid4().hex}"
    async with api_client(app) as client:
        response = await post_run(client, world, key=key)

    assert response.status_code == 201
    run_id = response.json()["data"]["simulationRunId"]
    record = await session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.workspace_id == world.workspace_id,
            IdempotencyRecord.route_key == RUN_CREATE_ROUTE_KEY,
            IdempotencyRecord.idempotency_key == key,
        )
    )
    assert record is not None
    assert str(record.resource_id) == run_id
    assert record.resource_type == "simulation_run"
    assert (record.http_status, record.response_kind) == (201, "success")
    assert record.expires_at - record.created_at == timedelta(hours=48)


async def test_lost_unique_race_rolls_back_the_run_and_signals_replay(session):
    # Service-level loser path (§4.5): the record's (workspace, route, key) is
    # already committed by "another writer"; the second transaction must roll
    # back completely — no zombie run row — and surface the race marker.
    world = await seed_world(session, "idem-race")
    service = SimulationRunService(session)
    key = f"race-{uuid4().hex}"
    request_hash = normalized_request_hash({"probe": "winner"}, world.graph_id)

    winner = build_idempotency_record(
        workspace_id=world.workspace_id,
        idempotency_key=key,
        request_hash=request_hash,
        resource_id=uuid4(),
        http_status=201,
        response_kind="success",
    )
    session.add(winner)
    await session.flush()

    before = await scoped_run_count(session, world)
    with pytest.raises(IdempotencyRaceError):
        await service.run_and_record_idempotent(
            world.context,
            request_for(world),
            lambda view: build_idempotency_record(
                workspace_id=world.workspace_id,
                idempotency_key=key,
                request_hash=request_hash,
                resource_id=view.id,
                http_status=201,
                response_kind="success",
            ),
        )
    assert await scoped_run_count(session, world) == before  # loser persisted nothing
