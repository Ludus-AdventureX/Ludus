"""Guest alpha prototype QA: ``POST /api/auth/guest`` bootstrap + isolation.

Runs against the canonical app assembly from ``conftest.build_qa_app`` on a
migrated test database. The guest flag is toggled per test through the
``ENABLE_GUEST_ALPHA`` environment variable (read per request by the route).

Isolation battery (counted for the release report):

1.  disabled flag answers the uniform 404;
2.  route is absent from the generated OpenAPI schema;
3.  CSRF is mandatory;
4.  caller-supplied userId/workspaceId are ignored (no input is accepted);
5.  bootstrap creates the full demo scope + HttpOnly session cookie;
6.  a valid guest session is reused verbatim (same IDs, no new rows);
7.  two independent cookie clients get fully disjoint identities/IDs;
8.  guest A probing guest B's workspace answers the uniform 404;
9.  guest A using guest B's graph/profile in a simulation run answers 404;
10. guest A's own scope stays runnable (positive control, sim-engine-1.1.0);
11. a bootstrap failure rolls back the entire creation.
"""

from __future__ import annotations

from functools import lru_cache
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from conftest import QA_ORIGIN, build_qa_app, csrf_headers

from app.db import get_database_url
from app.models import GraphVersion, User, Workspace, WorkspaceMembership
from app.security.envelope import ApiFailure
from app.tenancy.context import WorkspaceContext, project_capabilities
from app.types import WorkspaceRole

GUEST_FLAG = "ENABLE_GUEST_ALPHA"


@lru_cache(maxsize=1)
def _guest_app():
    """QA assembly + the guest router.

    ``conftest.build_qa_app`` detects canonical routes by path, but this
    FastAPI version registers included routers lazily (``_IncludedRouter``
    without ``.path``), so the QA fallback assembly is used and the guest
    router must be mounted here explicitly. Double inclusion on a canonical
    assembly is harmless: the first matching route wins and both bind the
    same handler.
    """

    from app.auth.guest import router as guest_router

    app = build_qa_app()
    app.include_router(guest_router)
    return app


def guest_client(client_ip: str | None = None) -> httpx.AsyncClient:
    address = client_ip or f"10.78.{uuid4().bytes[0]}.{uuid4().bytes[1]}"
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_guest_app(), client=(address, 51234)),
        base_url=QA_ORIGIN,
        headers={"Origin": QA_ORIGIN},
    )

ID_FIELDS = (
    "workspaceId",
    "decisionCaseId",
    "graphId",
    "graphVersionId",
    "strategyVersionId",
    "scenarioVersionId",
    "scoreDefinitionId",
    "decisionMakerProfileId",
)


async def _post_guest(client, *, json=None):
    headers = await csrf_headers(client)
    return await client.post("/api/auth/guest", headers=headers, json=json)


async def _bootstrap_guest(client) -> dict:
    response = await _post_guest(client)
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    for field in ID_FIELDS:
        assert data.get(field), f"missing {field} in guest bootstrap response"
    assert data["decisionMakerProfileVersion"] == 1
    return data


def _null_pool_sessionmaker():
    engine = create_async_engine(get_database_url(), poolclass=NullPool)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _workspace_context(workspace_id: str) -> WorkspaceContext:
    """Rebuild guest A/B's real workspace context from the committed membership."""

    engine, factory = _null_pool_sessionmaker()
    try:
        async with factory() as db:
            membership = await db.scalar(
                select(WorkspaceMembership).where(
                    WorkspaceMembership.workspace_id == UUID(workspace_id)
                )
            )
            assert membership is not None
            return WorkspaceContext(
                user_id=membership.user_id,
                workspace_id=membership.workspace_id,
                role=membership.role,
                capabilities=project_capabilities(membership.role, membership.capabilities),
            )
    finally:
        await engine.dispose()


async def _run_simulation(context: WorkspaceContext, data: dict, **overrides):
    """Drive the real simulation service with a guest scope (no route changes)."""

    from app.simulations.service import SimulationRunRequest, SimulationRunService
    from app.types import SimulationMode

    request = SimulationRunRequest(
        decision_case_id=UUID(overrides.get("case_id") or data["decisionCaseId"]),
        graph_version_id=UUID(overrides.get("graph_version_id") or data["graphVersionId"]),
        strategy_version_id=UUID(overrides.get("strategy_version_id") or data["strategyVersionId"]),
        scenario_version_id=UUID(overrides.get("scenario_version_id") or data["scenarioVersionId"]),
        score_definition_id=UUID(overrides.get("score_definition_id") or data["scoreDefinitionId"]),
        simulation_mode=SimulationMode.FORMAL,
        decision_maker_profile_id=UUID(
            overrides.get("profile_id") or data["decisionMakerProfileId"]
        ),
        decision_maker_profile_version=data["decisionMakerProfileVersion"],
        include_sensitivity=False,
    )
    engine, factory = _null_pool_sessionmaker()
    try:
        async with factory() as db:
            return await SimulationRunService(db).run_and_record(context, request)
    finally:
        await engine.dispose()


async def _count(statement) -> int:
    engine, factory = _null_pool_sessionmaker()
    try:
        async with factory() as db:
            return int(await db.scalar(statement) or 0)
    finally:
        await engine.dispose()


# --- flag / schema / input surface --------------------------------------------------------


async def test_guest_disabled_answers_uniform_404(monkeypatch):
    monkeypatch.delenv(GUEST_FLAG, raising=False)
    async with guest_client() as client:
        response = await _post_guest(client)
    assert response.status_code == 404
    assert response.json()["ok"] is False


async def test_guest_route_is_hidden_from_openapi(monkeypatch):
    monkeypatch.setenv(GUEST_FLAG, "true")
    app = _guest_app()
    app.openapi_schema = None  # force regeneration under the enabled flag
    assert "/api/auth/guest" not in app.openapi().get("paths", {})


async def test_guest_requires_csrf(monkeypatch):
    monkeypatch.setenv(GUEST_FLAG, "true")
    async with guest_client() as client:
        response = await client.post("/api/auth/guest")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_VALIDATION_FAILED"


async def test_guest_ignores_caller_supplied_identity(monkeypatch):
    monkeypatch.setenv(GUEST_FLAG, "true")
    smuggled = "11111111-1111-1111-1111-111111111111"
    async with guest_client() as client:
        response = await _post_guest(
            client, json={"userId": smuggled, "workspaceId": smuggled, "password": "nope"}
        )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["workspaceId"] != smuggled
    assert all(data[field] != smuggled for field in ID_FIELDS)


# --- bootstrap / reuse ---------------------------------------------------------------------


async def test_guest_bootstrap_creates_isolated_scope(monkeypatch):
    monkeypatch.setenv(GUEST_FLAG, "true")
    async with guest_client() as client:
        headers = await csrf_headers(client)
        response = await client.post("/api/auth/guest", headers=headers)
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["reused"] is False

    set_cookie = response.headers.get("set-cookie", "")
    assert "decision_lab_session=" in set_cookie
    assert "HttpOnly" in set_cookie

    workspace_id = UUID(data["workspaceId"])
    workspace_row = await _count(
        select(func.count()).select_from(Workspace).where(Workspace.id == workspace_id)
    )
    assert workspace_row == 1
    owner_memberships = await _count(
        select(func.count())
        .select_from(WorkspaceMembership)
        .where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.role == WorkspaceRole.OWNER,
        )
    )
    assert owner_memberships == 1

    engine, factory = _null_pool_sessionmaker()
    try:
        async with factory() as db:
            graph_version = await db.get(GraphVersion, UUID(data["graphVersionId"]))
            assert graph_version is not None
            assert graph_version.workspace_id == workspace_id
            assert graph_version.status.value == "confirmed"
            owner = await db.scalar(
                select(User)
                .join(WorkspaceMembership, WorkspaceMembership.user_id == User.id)
                .where(WorkspaceMembership.workspace_id == workspace_id)
            )
            assert owner is not None
            assert owner.email.startswith("guest-")
            assert owner.email.endswith("@guest.invalid")
    finally:
        await engine.dispose()


async def test_guest_session_is_reused_without_duplicates(monkeypatch):
    monkeypatch.setenv(GUEST_FLAG, "true")
    async with guest_client() as client:
        first = await _bootstrap_guest(client)
        guests_before = await _count(
            select(func.count()).select_from(User).where(User.email.like("%@guest.invalid"))
        )
        headers = await csrf_headers(client)
        second_response = await client.post("/api/auth/guest", headers=headers)
    assert second_response.status_code == 200, second_response.text
    second = second_response.json()["data"]
    assert second["reused"] is True
    for field in (*ID_FIELDS, "decisionMakerProfileVersion"):
        assert second[field] == first[field], f"reused guest changed {field}"

    guests_after = await _count(
        select(func.count()).select_from(User).where(User.email.like("%@guest.invalid"))
    )
    assert guests_after == guests_before
    versions = await _count(
        select(func.count())
        .select_from(GraphVersion)
        .where(GraphVersion.workspace_id == UUID(first["workspaceId"]))
    )
    assert versions == 1


# --- cross-guest isolation ------------------------------------------------------------------


async def test_two_guest_clients_are_fully_disjoint(monkeypatch):
    monkeypatch.setenv(GUEST_FLAG, "true")
    async with guest_client() as client_a, guest_client() as client_b:
        data_a = await _bootstrap_guest(client_a)
        data_b = await _bootstrap_guest(client_b)
    for field in ID_FIELDS:
        assert data_a[field] != data_b[field], f"guests share {field}"


async def test_guest_cannot_probe_foreign_workspace(monkeypatch):
    monkeypatch.setenv(GUEST_FLAG, "true")
    async with guest_client() as client_a, guest_client() as client_b:
        data_a = await _bootstrap_guest(client_a)
        data_b = await _bootstrap_guest(client_b)
        own = await client_a.get(
            f"/api/workspaces/{data_a['workspaceId']}/qa-tenancy-probe"
        )
        foreign = await client_a.get(
            f"/api/workspaces/{data_b['workspaceId']}/qa-tenancy-probe"
        )
    assert own.status_code == 200
    assert foreign.status_code == 404


async def test_guest_cannot_use_foreign_graph_or_profile(monkeypatch):
    monkeypatch.setenv(GUEST_FLAG, "true")
    async with guest_client() as client_a, guest_client() as client_b:
        data_a = await _bootstrap_guest(client_a)
        data_b = await _bootstrap_guest(client_b)
    context_a = await _workspace_context(data_a["workspaceId"])

    # A referencing B's graph version: uniform 404 (CASE_NOT_FOUND).
    with pytest.raises(ApiFailure) as denied_graph:
        await _run_simulation(
            context_a, data_a, graph_version_id=data_b["graphVersionId"]
        )
    assert denied_graph.value.http_status == 404

    # A referencing B's frozen profile: uniform 404 as well.
    with pytest.raises(ApiFailure) as denied_profile:
        await _run_simulation(
            context_a, data_a, profile_id=data_b["decisionMakerProfileId"]
        )
    assert denied_profile.value.http_status == 404


async def test_guest_own_scope_is_runnable(monkeypatch):
    monkeypatch.setenv(GUEST_FLAG, "true")
    async with guest_client() as client:
        data = await _bootstrap_guest(client)
    context = await _workspace_context(data["workspaceId"])
    view = await _run_simulation(context, data)
    assert view.engine_version == "sim-engine-1.1.0"
    assert view.input_hash.startswith("sha256:")
    assert str(view.workspace_id) == data["workspaceId"]


# --- rollback --------------------------------------------------------------------------------


async def test_guest_bootstrap_failure_rolls_back_everything(monkeypatch):
    monkeypatch.setenv(GUEST_FLAG, "true")

    from sqlalchemy.exc import SQLAlchemyError

    import app.auth.guest as guest_module

    async def exploding_bootstrap(*args, **kwargs):
        raise SQLAlchemyError("qa: forced bootstrap failure")

    monkeypatch.setattr(guest_module, "bootstrap_guest_demo", exploding_bootstrap)

    guests_before = await _count(
        select(func.count()).select_from(User).where(User.email.like("%@guest.invalid"))
    )
    workspaces_before = await _count(select(func.count()).select_from(Workspace))

    async with guest_client() as client:
        response = await _post_guest(client)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "GUEST_BOOTSTRAP_FAILED"
    assert "set-cookie" not in {key.lower() for key in response.headers.keys()} or (
        "decision_lab_session=" not in response.headers.get("set-cookie", "")
    )

    guests_after = await _count(
        select(func.count()).select_from(User).where(User.email.like("%@guest.invalid"))
    )
    workspaces_after = await _count(select(func.count()).select_from(Workspace))
    assert guests_after == guests_before
    assert workspaces_after == workspaces_before
