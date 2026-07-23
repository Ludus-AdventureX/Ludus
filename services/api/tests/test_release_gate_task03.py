"""Task 3 release gate: canonical ``app.main`` assembly (CT-01 flip evidence).

Unlike the other Task 3 suites (which tolerate a QA assembly fallback), this
file asserts the shipped canonical app directly: router mounting, error
handler registration, and envelope behavior per CCR-20260724-005. The chosen
probes never need a database, so they verify pure assembly.
"""

from __future__ import annotations

import pytest

pytest.importorskip("app.auth", reason="Task 3 auth implementation not delivered yet")

import httpx

from app.main import app as canonical_app

AUTH_PATHS = {
    "/api/auth/csrf",
    "/api/auth/register",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/session",
}


def _canonical_client(origin: str | None = "http://testserver") -> httpx.AsyncClient:
    headers = {"Origin": origin} if origin else {}
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=canonical_app),
        base_url="http://testserver",
        headers=headers,
    )


def test_canonical_app_mounts_all_auth_endpoints() -> None:
    """All five doc-10 auth endpoints exist on the shipped app.

    Uses the app's own OpenAPI projection: on this FastAPI version,
    ``include_router`` registers a wrapper route whose ``path`` is empty, so
    scanning ``app.routes`` would miss mounted sub-routes even though they
    are reachable.
    """

    paths = set(canonical_app.openapi()["paths"])
    missing = AUTH_PATHS - paths
    assert not missing, f"canonical app.main is missing auth endpoints: {missing}"


# Note: workspace_router owns no business endpoints yet, so mounting it adds
# no paths to inspect here; its guard behavior on the canonical assembly is
# exercised end-to-end in test_workspace_isolation.py via the probe router.


async def test_canonical_error_handler_shapes_session_failure() -> None:
    """register_error_handlers is active: unauth session → enveloped 401."""

    async with _canonical_client() as client:
        response = await client.get("/api/auth/session")
    assert response.status_code == 401
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "SESSION_REVOKED_OR_EXPIRED"


async def test_canonical_csrf_guard_active_on_register() -> None:
    """CSRF dependency is enforced on the shipped app (no token → 403)."""

    async with _canonical_client() as client:
        response = await client.post(
            "/api/auth/register",
            json={"email": "qa-canonical@example.test", "password": "irrelevant-here"},
        )
    assert response.status_code == 403
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "CSRF_VALIDATION_FAILED"


async def test_canonical_validation_error_uses_envelope() -> None:
    """RequestValidationError handler returns the uniform 422 envelope.

    QA-TASK03-003 (P1): on the pinned FastAPI, ``exc.errors(include_url=...,
    include_input=...)`` raises TypeError, so every malformed request body
    escapes as an unhandled 500 instead of the enveloped 422. This test is
    the release-gate regression; it must pass before the candidate ships.
    """

    async with _canonical_client() as client:
        csrf = await client.get("/api/auth/csrf")
        token = csrf.json()["data"]["csrfToken"]
        response = await client.post(
            "/api/auth/register",
            json={"email": "not-an-email", "password": "x"},
            headers={"X-CSRF-Token": token},
        )
    assert response.status_code == 422
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "VALIDATION_FAILED"


def test_canonical_openapi_contains_auth_contract() -> None:
    """Committed canonical OpenAPI + generated types include the endpoints."""

    import json
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    openapi = json.loads(
        (repo_root / "packages" / "contracts" / "openapi.json").read_text(encoding="utf-8")
    )
    for path in AUTH_PATHS:
        assert path in openapi["paths"], f"openapi.json missing {path}"

    types_text = (repo_root / "packages" / "contracts" / "src" / "types.gen.ts").read_text(
        encoding="utf-8"
    )
    for path in AUTH_PATHS:
        assert f'"{path}"' in types_text, f"types.gen.ts missing {path}"
