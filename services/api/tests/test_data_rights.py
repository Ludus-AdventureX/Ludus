"""Interlude B battery: workspace data rights (export + confirmed purge).

Both are OWNER-only; the purge demands the workspace id echoed verbatim and
cascades every business table (schema-level, not application loops).
"""

from __future__ import annotations

from functools import lru_cache
from uuid import uuid4

import httpx

from tests.conftest import QA_ORIGIN, build_qa_app, csrf_headers

GUEST_FLAG = "ENABLE_GUEST_ALPHA"


@lru_cache(maxsize=1)
def _app():
    from app.auth.guest import router as guest_router

    app = build_qa_app()
    app.include_router(guest_router)
    return app


def qa_client() -> httpx.AsyncClient:
    address = f"10.82.{uuid4().bytes[0]}.{uuid4().bytes[1]}"
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(), client=(address, 51234)),
        base_url=QA_ORIGIN,
        headers={"Origin": QA_ORIGIN},
    )


async def _guest(client: httpx.AsyncClient) -> dict:
    headers = await csrf_headers(client)
    response = await client.post("/api/auth/guest", headers=headers)
    assert response.status_code in (200, 201), response.text
    return response.json()["data"]


async def test_export_is_owner_only_and_projects_real_tables(monkeypatch) -> None:
    monkeypatch.setenv(GUEST_FLAG, "true")
    async with qa_client() as owner, qa_client() as stranger:
        data = await _guest(owner)
        ws = data["workspaceId"]
        await _guest(stranger)

        # Non-member: uniform 404.
        foreign = await stranger.get(f"/api/workspaces/{ws}/export")
        assert foreign.status_code == 404

        export = await owner.get(f"/api/workspaces/{ws}/export")
        assert export.status_code == 200, export.text
        tables = export.json()["data"]["tables"]
        assert "decision_cases" in tables and len(tables["decision_cases"]) >= 1
        assert "decision_records" in tables  # empty list is honest, key must exist
        # The demo case row really carries this workspace id.
        assert tables["decision_cases"][0]["workspace_id"] == ws


async def test_purge_demands_exact_confirmation_then_cascades(monkeypatch) -> None:
    monkeypatch.setenv(GUEST_FLAG, "true")
    async with qa_client() as owner:
        data = await _guest(owner)
        ws = data["workspaceId"]
        headers = await csrf_headers(owner)

        # Wrong echo -> 422, nothing deleted.
        wrong = await owner.post(
            f"/api/workspaces/{ws}/purge",
            json={"confirmWorkspaceId": "not-the-id"},
            headers=headers,
        )
        assert wrong.status_code == 422
        assert (await owner.get(f"/api/workspaces/{ws}/export")).status_code == 200

        # Exact echo -> purged; afterwards the workspace answers uniform 404.
        purged = await owner.post(
            f"/api/workspaces/{ws}/purge",
            json={"confirmWorkspaceId": ws},
            headers=headers,
        )
        assert purged.status_code == 200, purged.text
        assert purged.json()["data"]["purged"] is True
        gone = await owner.get(f"/api/workspaces/{ws}/export")
        assert gone.status_code == 404
