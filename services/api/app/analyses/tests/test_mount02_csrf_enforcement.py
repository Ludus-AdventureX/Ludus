"""MOUNT-02 M8 wave regression: CSRF enforcement on analyses unsafe writes.

Closes the MOUNT-01 M8 stop-report. Every unsafe write on the analyses router
must reject a request without the same-origin double-submit proof with 403
CSRF_VALIDATION_FAILED (SIM-02A parity), while safe reads stay CSRF-free.
Assembly mirrors the owner suites (tenancy + session overridden); require_csrf
is deliberately NOT overridden — it is the subject under test.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, Path

from app.analyses.routes import router as analyses_router
from app.db import get_session
from app.security.envelope import register_error_handlers, workspace_not_found
from app.tenancy.context import (
    ALL_CAPABILITIES,
    WorkspaceContext,
    require_workspace_context,
)
from app.types import WorkspaceRole

from runtime_world import make_queued_run


def _build_app(session, memberships: dict[UUID, UUID]) -> FastAPI:
    app = FastAPI(title="Ludus MOUNT-02 CSRF gate assembly")
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
async def bare_client(session, world):
    """Client WITHOUT any CSRF proof (no Origin, no cookie, no header)."""

    app = _build_app(session, {world.workspace_id: world.user_id})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


@pytest.mark.parametrize(
    ("method", "path_template", "kwargs"),
    [
        ("POST", "/cases/{case_id}/analysis-charters", {"json": {}}),
        ("PATCH", "/analysis-charters/{ghost}", {"json": {"decisionQuestion": "x"}}),
        ("POST", "/analysis-charters/{ghost}/replacements", {"json": {}}),
        ("POST", "/analysis-charters/{ghost}/confirm", {}),
        (
            "POST",
            "/analysis-charters/{ghost}/runs",
            {"json": {}, "headers": {"Idempotency-Key": "csrf-gate"}},
        ),
        (
            "POST",
            "/analyses/{ghost}/resolutions",
            {"json": {}, "headers": {"Idempotency-Key": "csrf-gate"}},
        ),
        (
            "POST",
            "/analyses/{ghost}/cancel",
            {"headers": {"Idempotency-Key": "csrf-gate"}},
        ),
    ],
)
async def test_unsafe_writes_without_csrf_proof_are_403(
    bare_client, world, method, path_template, kwargs
):
    path = path_template.format(case_id=world.case_id, ghost=uuid4())
    url = f"/api/workspaces/{world.workspace_id}{path}"
    response = await bare_client.request(method, url, **kwargs)
    assert response.status_code == 403, response.text
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "CSRF_VALIDATION_FAILED"


async def test_safe_reads_require_no_csrf(bare_client, session, world):
    _charter, run = await make_queued_run(session, world)
    ws = f"/api/workspaces/{world.workspace_id}"
    status = await bare_client.get(f"{ws}/analyses/{run.analysis_run_id}")
    assert status.status_code == 200, status.text
    lenses = await bare_client.get(
        f"{ws}/analyses/{run.analysis_run_id}/strategic-lenses"
    )
    assert lenses.status_code == 200
