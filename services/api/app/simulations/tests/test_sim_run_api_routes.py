"""Owner verification for the SIM-02A run routes (POST create / GET replay).

Run (disposable clean PostgreSQL + already-installed venv; no new environment):

    $env:DATABASE_URL = "postgresql+asyncpg://<user>:<password>@localhost:<port>/decision_lab"
    <mainvenv>python -m pytest app/simulations/tests -q

Route tests exercise the real router module over an ASGI transport. Tenancy is
supplied through a ``require_workspace_context`` override (router mounting and
the canonical membership guard belong to the Contract Lead's integration lane;
the full HTTP auth battery is the QA owner's I3 scope) while CSRF, capability
projection, rate limiting, budget, error mapping, and the DB flows are the real
shipped code paths against the migrated database.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, FastAPI
from fastapi import Path as PathParam
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.config import get_auth_settings
from app.db import get_session
from app.models import (
    CausalGraph,
    IdempotencyRecord,
    SimulationRun as SimulationRunRow,
    StrategyVersion as StrategyVersionRow,
)
from app.security.envelope import register_error_handlers, workspace_not_found
from app.simulations import run_policy
from app.simulations.routes import router as simulations_router
from app.tenancy.context import WorkspaceContext, require_workspace_context
from app.types import SimulationConvergenceStatus, WorkspaceCapability, WorkspaceRole
from test_simulation_repository_service import (
    SEED_PROFILE_RISK_TOLERANCE,
    SEED_PROFILE_VERSION,
    World,
    scoped_run_count,
    seed_world,
)

TEST_ORIGIN = "http://testserver"
CSRF_TOKEN = "sim-run-api-csrf-token"


def build_sim_api_app(session: AsyncSession, context_holder: dict) -> FastAPI:
    """Mount the relative simulations router exactly as §10 instructs the Contract Lead."""

    app = FastAPI(title="SIM-02A owner test assembly")
    mount = APIRouter(prefix="/api/workspaces/{workspaceId}")
    mount.include_router(simulations_router)
    app.include_router(mount)
    register_error_handlers(app)

    async def _session_override():
        yield session

    async def _context_override(
        workspace_id: UUID = PathParam(alias="workspaceId"),
    ) -> WorkspaceContext:
        context: WorkspaceContext = context_holder["context"]
        # Mirror the real guard's uniform denial: a context that does not match
        # the path workspace behaves like a missing membership.
        if context.workspace_id != workspace_id:
            raise workspace_not_found()
        return context

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[require_workspace_context] = _context_override
    return app


def api_client(app: FastAPI, *, with_csrf: bool = True) -> httpx.AsyncClient:
    settings = get_auth_settings()
    headers = {"Origin": TEST_ORIGIN}
    cookies = {}
    if with_csrf:
        headers[settings.csrf_header_name] = CSRF_TOKEN
        cookies[settings.csrf_cookie_name] = CSRF_TOKEN
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url=TEST_ORIGIN,
        headers=headers,
        cookies=cookies,
    )


def member_context(world: World, *capabilities: WorkspaceCapability) -> WorkspaceContext:
    return WorkspaceContext(
        user_id=world.user_id,
        workspace_id=world.workspace_id,
        role=WorkspaceRole.MEMBER,
        capabilities=frozenset(capabilities),
    )


def runs_url(world: World, graph_id: UUID | None = None) -> str:
    return (
        f"/api/workspaces/{world.workspace_id}"
        f"/simulations/{graph_id or world.graph_id}/runs"
    )


def run_body(world: World, **overrides) -> dict:
    body = {
        "mode": "experimental",
        "graphVersionId": str(world.graph_version_id),
        "strategyVersionId": str(world.strategy_version_id),
        "scenarioVersionId": str(world.scenario_version_id),
        "scoreDefinitionId": str(world.score_definition_id),
        "decisionMakerProfileId": str(world.profile_id),
        "decisionMakerProfileVersion": SEED_PROFILE_VERSION,
    }
    body.update(overrides)
    return body


def idem_headers(key: str | None = None) -> dict:
    return {"Idempotency-Key": key or f"sim-run-{uuid4().hex}"}


async def post_run(client: httpx.AsyncClient, world: World, *, key=None, **overrides):
    return await client.post(
        runs_url(world), json=run_body(world, **overrides), headers=idem_headers(key)
    )


async def scoped_record_count(session: AsyncSession, world: World) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(IdempotencyRecord)
            .where(IdempotencyRecord.workspace_id == world.workspace_id)
        )
        or 0
    )


async def world_and_client(session: AsyncSession, slug: str, **seed_kwargs):
    world = await seed_world(session, slug, **seed_kwargs)
    holder = {"context": world.context}
    app = build_sim_api_app(session, holder)
    return world, holder, app


# --- POST create: success surface -------------------------------------------------------------


async def test_post_experimental_returns_201_with_server_owned_authority(session):
    world, _, app = await world_and_client(session, "api-post-exp")
    async with api_client(app) as client:
        response = await post_run(client, world)

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert "meta" not in payload  # §4.9: meta only on replays
    data = payload["data"]
    # Server-owned authority fields (§5 rulings 3-5): resolved, never client-sent.
    assert data["riskTolerance"] == SEED_PROFILE_RISK_TOLERANCE
    assert data["engineVersion"] == "sim-engine-1.1.0"
    assert data["scoreDefinitionVersion"] == "1"
    assert data["workspaceId"] == str(world.workspace_id)
    assert data["decisionCaseId"] == str(world.case_id)
    assert data["graphId"] == str(world.graph_id)
    assert data["simulationMode"] == "experimental"
    assert data["convergenceStatus"] == "converged"
    assert data["inputHash"].startswith("sha256:")
    assert data["recommendedOptionId"] == world.option_a
    assert data["topDrivers"], "includeSensitivity is server-fixed true (§5.6)"
    assert await scoped_run_count(session, world) == 1
    assert await scoped_record_count(session, world) == 1


async def test_post_formal_converged_returns_201(session):
    world, _, app = await world_and_client(session, "api-post-formal")
    async with api_client(app) as client:
        response = await post_run(client, world, mode="formal")

    assert response.status_code == 201, response.text
    assert response.json()["data"]["simulationMode"] == "formal"


async def test_post_and_get_return_identical_replay_data(session):
    world, _, app = await world_and_client(session, "api-replay-identity")
    async with api_client(app) as client:
        created = await post_run(client, world)
        assert created.status_code == 201
        run_id = created.json()["data"]["simulationRunId"]
        fetched = await client.get(f"{runs_url(world)}/{run_id}")

    assert fetched.status_code == 200
    assert fetched.json()["ok"] is True
    # §6.1: POST and GET share one data schema and are byte-equal replays.
    assert fetched.json()["data"] == created.json()["data"]
    assert "meta" not in fetched.json()


# --- POST create: authorization and CSRF -------------------------------------------------------


async def test_post_without_contribute_capability_is_403(session):
    world, holder, app = await world_and_client(session, "api-cap-denied")
    holder["context"] = member_context(world, WorkspaceCapability.REVIEW)
    async with api_client(app) as client:
        response = await post_run(client, world)

    assert response.status_code == 403
    error = response.json()["error"]
    assert error["code"] == "MEMBERSHIP_CAPABILITY_REQUIRED"
    assert error["details"] == {"requiredCapability": "contribute"}
    assert await scoped_run_count(session, world) == 0


async def test_post_without_csrf_proof_is_403_and_consumes_nothing(session):
    world, _, app = await world_and_client(session, "api-csrf-denied")
    async with api_client(app, with_csrf=False) as client:
        response = await post_run(client, world, key="csrf-denied-key")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_VALIDATION_FAILED"
    # §4.6: failures before persistence never consume the key.
    assert await scoped_record_count(session, world) == 0
    assert await scoped_run_count(session, world) == 0


async def test_get_requires_no_csrf_but_membership_context(session):
    world, _, app = await world_and_client(session, "api-get-member")
    holder_member = member_context(world)  # membership only, zero capabilities
    async with api_client(app) as client:
        created = await post_run(client, world)
        run_id = created.json()["data"]["simulationRunId"]

    world_holder = {"context": holder_member}
    member_app = build_sim_api_app(session, world_holder)
    async with api_client(member_app, with_csrf=False) as client:
        fetched = await client.get(f"{runs_url(world)}/{run_id}")

    assert fetched.status_code == 200  # §9 read parity: membership only


# --- GET replay: three-anchor tenant scoping ----------------------------------------------------


async def test_get_uniform_404_for_every_foreign_or_mixed_anchor(session):
    world_a, _, app_a = await world_and_client(session, "api-anchor-a")
    world_b = await seed_world(session, "api-anchor-b")
    async with api_client(app_a) as client:
        created = await post_run(client, world_a)
        run_id = created.json()["data"]["simulationRunId"]

        # Second graph in the SAME workspace: mixed-anchor probe (run exists,
        # graph anchor is wrong) must be indistinguishable from a ghost.
        second_graph = CausalGraph(
            id=uuid4(),
            workspace_id=world_a.workspace_id,
            decision_case_id=world_a.case_id,
            report_artifact_id=uuid4(),
            title="api-anchor-a-second-graph",
        )
        session.add(second_graph)
        await session.flush()

        probes = [
            f"{runs_url(world_a)}/{uuid4()}",  # ghost run id
            f"{runs_url(world_a, second_graph.id)}/{run_id}",  # wrong graph anchor
        ]
        responses = [await client.get(url) for url in probes]

    # Foreign workspace principal probing tenant A's run through its own path.
    app_b = build_sim_api_app(session, {"context": world_b.context})
    async with api_client(app_b) as client:
        responses.append(
            await client.get(f"{runs_url(world_b)}/{run_id}")
        )

    bodies = [(r.status_code, r.json()["error"]) for r in responses]
    assert {status for status, _ in bodies} == {404}
    assert {error["code"] for _, error in bodies} == {"CASE_NOT_FOUND"}
    assert len({error["message"] for _, error in bodies}) == 1  # one signature


async def test_post_path_graph_mismatch_is_uniform_404(session):
    world, _, app = await world_and_client(session, "api-path-mismatch")
    second_graph = CausalGraph(
        id=uuid4(),
        workspace_id=world.workspace_id,
        decision_case_id=world.case_id,
        report_artifact_id=uuid4(),
        title="api-path-mismatch-second-graph",
    )
    session.add(second_graph)
    await session.flush()

    async with api_client(app) as client:
        # Path names the second graph; the body's graphVersionId belongs to the
        # first: §5.2 rules this the uniform 404, not a distinguishable mismatch.
        response = await client.post(
            runs_url(world, second_graph.id),
            json=run_body(world),
            headers=idem_headers(),
        )
        ghost = await client.post(
            runs_url(world, uuid4()), json=run_body(world), headers=idem_headers()
        )

    for probe in (response, ghost):
        assert probe.status_code == 404
        assert probe.json()["error"]["code"] == "CASE_NOT_FOUND"
    assert await scoped_run_count(session, world) == 0


# --- POST create: request contract --------------------------------------------------------------


async def test_post_rejects_client_supplied_authority_fields(session):
    world, _, app = await world_and_client(session, "api-extra-forbid")
    async with api_client(app) as client:
        responses = [
            await post_run(client, world, riskTolerance=0.9),
            await post_run(client, world, engineVersion="sim-engine-9.9.9"),
            await post_run(client, world, decisionCaseId=str(world.case_id)),
            await post_run(client, world, includeSensitivity=False),
        ]

    for response in responses:
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    assert await scoped_run_count(session, world) == 0


async def test_post_formal_with_node_overrides_fails_closed_422(session):
    world, _, app = await world_and_client(session, "api-formal-overrides")
    async with api_client(app) as client:
        response = await post_run(
            client, world, mode="formal", nodeOverrides={str(world.lever_id): 80.0}
        )

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "SIMULATION_INPUT_INVALID"
    assert error["details"] == {"domainCode": "strategy_override_invalid"}
    assert await scoped_run_count(session, world) == 0


async def test_post_formal_on_draft_graph_is_graph_not_confirmed_409(session):
    from app.types import GraphVersionStatus

    world, _, app = await world_and_client(
        session, "api-formal-draft", graph_status=GraphVersionStatus.DRAFT
    )
    async with api_client(app) as client:
        response = await post_run(client, world, mode="formal")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "GRAPH_NOT_CONFIRMED"
    assert await scoped_run_count(session, world) == 0


async def test_post_formal_non_convergence_persists_run_and_returns_409(session):
    world, _, app = await world_and_client(session, "api-nonconverged")
    # A frozen strategy that actually moves the lever: with maxSteps=1 the first
    # propagation round still changes values (> epsilon), so the formal run ends
    # in max_steps instead of the seed world's trivial converged equilibrium.
    intervening_strategy = StrategyVersionRow(
        id=uuid4(),
        workspace_id=world.workspace_id,
        graph_id=world.graph_id,
        decision_case_id=world.case_id,
        version=2,
        option_id=UUID(world.option_a),
        node_overrides={str(world.lever_id): 95.0},
        enabled_edge_ids=[],
    )
    session.add(intervening_strategy)
    await session.flush()

    key = f"nonconv-{uuid4().hex}"
    body = dict(
        mode="formal", maxSteps=1, strategyVersionId=str(intervening_strategy.id)
    )
    async with api_client(app) as client:
        response = await post_run(client, world, key=key, **body)
        replay = await post_run(client, world, key=key, **body)

    assert response.status_code == 409, response.text
    error = response.json()["error"]
    assert error["code"] == "SIMULATION_NOT_CONVERGED"
    run_id = UUID(error["details"]["simulationRunId"])
    assert error["details"]["convergenceStatus"] in {
        status.value
        for status in SimulationConvergenceStatus
        if status != SimulationConvergenceStatus.CONVERGED
    }
    # §7: the run IS persisted for audit, atomically with its 409 record.
    row = await session.get(SimulationRunRow, run_id)
    assert row is not None and row.workspace_id == world.workspace_id
    record = await session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.workspace_id == world.workspace_id,
            IdempotencyRecord.idempotency_key == key,
        )
    )
    assert record is not None
    assert (record.http_status, record.response_kind) == (409, "non_converged")
    # Same key + same body replays the SAME 409 with the same details.
    assert replay.status_code == 409
    assert replay.json()["error"] == error
    assert await scoped_run_count(session, world) == 1


# --- POST create: budget + rate limit (minimal contract implementation) ------------------------


async def test_post_over_graph_budget_is_422_before_any_run(session, monkeypatch):
    world, _, app = await world_and_client(session, "api-budget")
    monkeypatch.setattr(run_policy, "MAX_GRAPH_NODES", 2)
    async with api_client(app) as client:
        response = await post_run(client, world)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "SIMULATION_BUDGET_EXCEEDED"
    assert error["details"] == {"budget": "graphNodes"}
    assert await scoped_run_count(session, world) == 0
    assert await scoped_record_count(session, world) == 0


async def test_post_rate_limit_is_429_and_never_consumes_the_key(session, monkeypatch):
    world, _, app = await world_and_client(session, "api-ratelimit")
    monkeypatch.setattr(run_policy, "RUN_RATE_MAX_ATTEMPTS", 2)
    key = f"ratelimited-{uuid4().hex}"
    async with api_client(app) as client:
        first = await post_run(client, world)
        second = await post_run(client, world)
        limited = await post_run(client, world, key=key)

    assert (first.status_code, second.status_code) == (201, 201)
    assert limited.status_code == 429
    error = limited.json()["error"]
    assert error["code"] == "REQUEST_RATE_LIMITED"
    assert error["retryable"] is True
    assert error["details"]["retryAfterSeconds"] >= 60
    # §9: a 429 never consumes an Idempotency-Key.
    record = await session.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.workspace_id == world.workspace_id,
            IdempotencyRecord.idempotency_key == key,
        )
    )
    assert record is None
    assert await scoped_run_count(session, world) == 2
