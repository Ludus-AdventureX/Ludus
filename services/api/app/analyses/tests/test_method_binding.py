"""methodContentHash is resolved by the server, never accepted from the caller.

Before this lane the field was whatever the client sent, and the shipped web
client sent ``sha256:`` + 32 random bytes. A charter therefore carried a method
provenance hash that matched no method bytes anywhere, which is the one thing
the field exists to prove.

Coverage: the caller's value is ignored on create, the default binding matches
the published pack the router itself selects, an unknown method is the caller's
error (422), a PATCH that touches method identity re-binds, and a catalog the
server cannot read fails closed (500) instead of inventing a hash.
"""

from __future__ import annotations

from uuid import UUID

import httpx
import pytest_asyncio
from fastapi import FastAPI, Path

from app.analyses.routes import router as analyses_router
from app.auth.config import get_auth_settings
from app.db import get_session
from app.methods.catalog import (
    CATALOG_ROOT_ENV,
    DEFAULT_METHOD_ID,
    DEFAULT_METHOD_VERSION,
    method_catalog_root,
    reset_binding_cache,
    resolve_method_binding,
)
from app.methods.loader import MethodPackLoader
from app.methods.router import MethodRouter
from app.security.envelope import register_error_handlers, workspace_not_found
from app.tenancy.context import (
    ALL_CAPABILITIES,
    WorkspaceContext,
    require_workspace_context,
)
from app.types import WorkspaceRole

from runtime_world import RuntimeWorld

FABRICATED_HASH = "sha256:" + "0" * 64


def _build_app(session, memberships: dict[UUID, UUID]) -> FastAPI:
    app = FastAPI(title="Ludus QA method-binding assembly")
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
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://methods.test",
        headers={
            "Origin": "http://methods.test",
            get_auth_settings().csrf_header_name: "qa-methods-csrf",
        },
        cookies={get_auth_settings().csrf_cookie_name: "qa-methods-csrf"},
    ) as http_client:
        yield http_client


def _ws(world: RuntimeWorld) -> str:
    return f"/api/workspaces/{world.workspace_id}"


def _body(world: RuntimeWorld, **overrides) -> dict:
    body = {
        "decisionSubjectId": str(world.subject_id),
        "analysisLevel": "focused",
        "decisionQuestion": "enter the rescue market?",
        "goals": [{"id": "g1", "text": "validate demand"}],
        "constraints": [{"id": "c1", "text": "9-month cash window"}],
        "optionIds": ["opt_rescue", "opt_home"],
        "preferenceWeights": {"risk": 0.4, "speed": 0.6},
        "requiredStrategicLensTypes": [],
        "formalAnalysisAllowed": True,
    }
    body.update(overrides)
    return body


async def _create(client, world, **overrides) -> httpx.Response:
    return await client.post(
        f"{_ws(world)}/cases/{world.case_id}/analysis-charters",
        json=_body(world, **overrides),
    )


# --- create ------------------------------------------------------------------


async def test_create_ignores_caller_supplied_method_hash(client, world):
    authoritative = resolve_method_binding().content_hash
    response = await _create(
        client,
        world,
        methodId=DEFAULT_METHOD_ID,
        methodVersion=DEFAULT_METHOD_VERSION,
        methodContentHash=FABRICATED_HASH,
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["methodContentHash"] == authoritative
    assert data["methodContentHash"] != FABRICATED_HASH


async def test_create_without_method_fields_binds_the_published_pack(client, world):
    response = await _create(client, world)
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["methodId"] == DEFAULT_METHOD_ID
    assert data["methodVersion"] == DEFAULT_METHOD_VERSION
    assert data["methodContentHash"] == resolve_method_binding().content_hash


async def test_binding_agrees_with_the_published_pack_and_the_router():
    """A charter and a routing decision must name the same method bytes."""

    root = str(method_catalog_root())
    pack = MethodPackLoader(root).load_from_catalog(
        DEFAULT_METHOD_ID, DEFAULT_METHOD_VERSION
    )
    binding = resolve_method_binding()
    assert (binding.method_id, binding.method_version) == (pack.method_id, pack.version)
    # The loader reports the bare digest; the wire form carries the algorithm.
    assert binding.content_hash == f"sha256:{pack.content_hash}"
    # Reaching into the router's default resolution on purpose: if the two sides
    # ever default to different packs, a charter would record a method the router
    # never selected, and nothing else in the suite would notice.
    routed = MethodRouter(root)._load_published_method()
    assert (routed.method_id, routed.version) == (
        DEFAULT_METHOD_ID,
        DEFAULT_METHOD_VERSION,
    )


async def test_create_rejects_a_method_the_catalog_does_not_publish(client, world):
    response = await _create(
        client, world, methodId="no-such-method", methodVersion="9.9.9"
    )
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_FAILED"
    assert error["details"]["methodId"] == "no-such-method"
    # The catalog path must never reach the caller.
    assert "method-packs" not in response.text


# --- patch -------------------------------------------------------------------


async def test_patch_method_version_rebinds_and_rejects_unknown(client, world):
    created = await _create(client, world)
    charter_id = created.json()["data"]["charterId"]

    unknown = await client.patch(
        f"{_ws(world)}/analysis-charters/{charter_id}",
        json={"methodVersion": "0.0.0-not-published"},
    )
    assert unknown.status_code == 422, unknown.text
    assert unknown.json()["error"]["details"]["methodVersion"] == "0.0.0-not-published"

    # Re-stating the published version keeps the authoritative hash, and the
    # caller's hash is not an accepted edit field at all.
    same = await client.patch(
        f"{_ws(world)}/analysis-charters/{charter_id}",
        json={
            "methodVersion": DEFAULT_METHOD_VERSION,
            "methodContentHash": FABRICATED_HASH,
        },
    )
    assert same.status_code == 200, same.text
    assert same.json()["data"]["methodContentHash"] == resolve_method_binding().content_hash


# --- fail closed -------------------------------------------------------------


async def test_unreadable_catalog_fails_closed(client, world, tmp_path, monkeypatch):
    """No catalog means no charter - never a fabricated provenance hash."""

    monkeypatch.setenv(CATALOG_ROOT_ENV, str(tmp_path / "absent"))
    reset_binding_cache()
    try:
        response = await _create(client, world)
        assert response.status_code == 500, response.text
        error = response.json()["error"]
        assert error["code"] == "METHOD_CATALOG_UNAVAILABLE"
        assert "absent" not in response.text
    finally:
        monkeypatch.delenv(CATALOG_ROOT_ENV, raising=False)
        reset_binding_cache()
