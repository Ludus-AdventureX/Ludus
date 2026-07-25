"""Task 8 owner tests: provenance/conflict routes and anti-enumeration.

The router is NOT mounted in ``app.main``; tests assemble a QA-only app the
same way the Task 3 QA conftest does, overriding tenancy with a seeded
context and the DB session with the transactional test session.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import httpx
import pytest_asyncio
from fastapi import FastAPI, Path

from app.db import get_session
from app.evidence.routes import router as evidence_router
from app.main import app as canonical_app
from app.security.envelope import register_error_handlers, workspace_not_found
from app.tenancy.context import (
    ALL_CAPABILITIES,
    WorkspaceContext,
    require_workspace_context,
)
from app.types import WorkspaceRole

from test_evidence_models import seed_chain


def test_evidence_router_is_not_mounted_in_canonical_app() -> None:
    paths = {getattr(route, "path", "") for route in canonical_app.routes}
    assert not any("/evidence" in path for path in paths)
    assert not any("evidence-conflicts" in path for path in paths)


def _build_app(session, memberships: dict[UUID, UUID]) -> FastAPI:
    """QA assembly mirroring how the integration layer would mount the router.

    ``memberships`` maps workspace_id -> user_id for workspaces the fake
    principal belongs to; any other workspaceId path resolves to the uniform
    tenancy 404, matching require_workspace_context semantics.
    """

    app = FastAPI(title="Ludus QA Task 8 assembly")
    app.include_router(evidence_router)
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


async def test_evidence_detail_quality_provenance_and_direction(
    session, worlds_client
) -> None:
    client, world, _ = worlds_client
    item = await seed_chain(session, world)
    base = f"/api/workspaces/{world.workspace_id}/evidence/{item.id}"

    detail = await client.get(base)
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["ok"] is True
    assert payload["data"]["id"] == str(item.id)
    assert payload["data"]["sourceGrade"] == "L2_reputable"
    assert payload["data"]["verdict"] == "accepted"

    quality = await client.get(f"{base}/quality")
    assert quality.status_code == 200
    dims = quality.json()["data"]
    assert set(dims) >= {
        "authenticity",
        "sourceQuality",
        "relevance",
        "freshness",
        "applicability",
        "independence",
        "extractionReliability",
        "biasFlags",
        "completenessWarnings",
        "conflictGroupIds",
        "verdict",
        "reasonCodes",
    }

    provenance = await client.get(f"{base}/provenance")
    assert provenance.status_code == 200
    chain = provenance.json()["data"]
    assert chain["rawArtifact"]["sha256"] == "a" * 64
    assert "storagePath" not in chain["rawArtifact"], "no storage pointer on the wire"
    assert chain["sourceRecord"]["spans"], "source spans must be present"

    direction = await client.get(f"{base}/direction")
    assert direction.status_code == 200
    assert direction.json()["data"]["supportsClaimIds"] == []

    group = await client.get(f"{base}/same-source-group")
    assert group.status_code == 200
    assert group.json()["data"]["memberEvidenceItemIds"] == [str(item.id)]


async def test_run_evidence_list_and_conflicts(session, worlds_client) -> None:
    client, world, _ = worlds_client
    item = await seed_chain(session, world)
    listed = await client.get(
        f"/api/workspaces/{world.workspace_id}/analyses/{world.analysis_run_id}/evidence"
    )
    assert listed.status_code == 200
    body = listed.json()["data"]
    assert [entry["id"] for entry in body["items"]] == [str(item.id)]

    conflicts = await client.get(
        f"/api/workspaces/{world.workspace_id}/analyses/"
        f"{world.analysis_run_id}/evidence-conflicts"
    )
    assert conflicts.status_code == 200
    assert conflicts.json()["data"]["conflicts"] == []


async def test_cross_workspace_and_missing_ids_are_byte_identical_404(
    session, worlds_client
) -> None:
    client, world, foreign = worlds_client
    item = await seed_chain(session, world)

    # Foreign workspace reading a real id vs anyone reading a ghost id:
    # responses must be byte-identical.
    foreign_real = await client.get(
        f"/api/workspaces/{foreign.workspace_id}/evidence/{item.id}"
    )
    own_ghost = await client.get(
        f"/api/workspaces/{world.workspace_id}/evidence/{uuid4()}"
    )
    assert foreign_real.status_code == own_ghost.status_code == 404
    assert foreign_real.content == own_ghost.content
    assert foreign_real.json()["error"]["code"] == "CASE_NOT_FOUND"

    # Foreign run id enumeration through the list endpoints: same uniform 404.
    foreign_run = await client.get(
        f"/api/workspaces/{foreign.workspace_id}/analyses/"
        f"{world.analysis_run_id}/evidence"
    )
    ghost_run = await client.get(
        f"/api/workspaces/{world.workspace_id}/analyses/{uuid4()}/evidence"
    )
    assert foreign_run.status_code == ghost_run.status_code == 404
    assert foreign_run.content == ghost_run.content


async def test_unknown_workspace_uses_uniform_tenancy_404(session, worlds_client) -> None:
    client, world, _ = worlds_client
    item = await seed_chain(session, world)
    response = await client.get(f"/api/workspaces/{uuid4()}/evidence/{item.id}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"
