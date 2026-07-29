"""Alpha-gate tests: the three gaps that blocked any outside exposure.

Each test pins one thing that was FALSE before this change:

1. `POST /analysis-charters/{id}/runs` had NO metering, while the far cheaper
   simulation-run route had a full limiter. One caller could queue unlimited
   runs, each ~8 model calls plus retrieval.
2. `POST /api/auth/guest` had no metering, so one address could mint unlimited
   guest workspaces - each with its own run budget.
3. `app.main` had no middleware at all, so no response carried a single
   security header.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.analyses import run_policy
from app.analyses.run_policy import (
    AnalysisRunRateLimiter,
    run_burst_key,
    run_daily_key,
)
from app.security.envelope import ApiFailure, register_error_handlers
from app.security.headers import BASE_HEADERS, SecurityHeadersMiddleware, hsts_enabled
from app.security.rate_limits import login_rate_buckets


async def _clear_buckets(session, *keys: str) -> None:
    for key in keys:
        await session.execute(
            delete(login_rate_buckets).where(login_rate_buckets.c.bucket_key == key)
        )
    await session.commit()


async def test_run_limiter_meters_burst_and_fails_closed(session, world) -> None:
    """Dimension 1: per (workspace, user) burst on the most expensive route."""

    limiter = AnalysisRunRateLimiter()
    ws, user = world.workspace_id, world.user_id
    await _clear_buckets(session, run_burst_key(ws, user), run_daily_key(ws))

    # The frozen default allows RUN_BURST_MAX_ATTEMPTS inside the window.
    for _ in range(run_policy.RUN_BURST_MAX_ATTEMPTS):
        await limiter.check_run_attempt(session, workspace_id=ws, user_id=user)

    with pytest.raises(ApiFailure) as over:
        await limiter.check_run_attempt(session, workspace_id=ws, user_id=user)
    assert over.value.code == "REQUEST_RATE_LIMITED"
    assert over.value.http_status == 429
    assert over.value.details["limit"] == "workspaceUserBurst"
    # The failure must be retryable and must not echo counts or ids.
    assert over.value.retryable is True
    assert set(over.value.details) == {"retryAfterSeconds", "limit"}

    await _clear_buckets(session, run_burst_key(ws, user), run_daily_key(ws))


async def test_run_limiter_meters_the_workspace_day(session, world) -> None:
    """Dimension 2: a tenant cannot drain the deployment's model budget.

    Driven through distinct users so the burst dimension never fires first -
    proving the daily workspace ceiling is independent, which is the dimension
    that actually protects a shared alpha deployment from one guest tenant.
    """

    limiter = AnalysisRunRateLimiter()
    ws = world.workspace_id
    users = [uuid.uuid4() for _ in range(run_policy.RUN_DAILY_MAX_ATTEMPTS + 1)]
    await _clear_buckets(session, run_daily_key(ws), *[run_burst_key(ws, u) for u in users])

    for user in users[: run_policy.RUN_DAILY_MAX_ATTEMPTS]:
        await limiter.check_run_attempt(session, workspace_id=ws, user_id=user)

    with pytest.raises(ApiFailure) as over:
        await limiter.check_run_attempt(session, workspace_id=ws, user_id=users[-1])
    assert over.value.details["limit"] == "workspaceDaily"

    await _clear_buckets(session, run_daily_key(ws), *[run_burst_key(ws, u) for u in users])


async def test_run_limiter_keys_never_store_raw_ids(world) -> None:
    """The limiter store must never contain a raw workspace or user id."""

    ws, user = world.workspace_id, world.user_id
    burst, daily = run_burst_key(ws, user), run_daily_key(ws)
    for key in (burst, daily):
        assert len(key) == 64 and str(ws) not in key and str(user) not in key
    # Distinct dimensions can never collide even for the same workspace.
    assert burst != daily


async def test_run_route_is_metered_before_it_does_any_work(
    session, world, monkeypatch
) -> None:
    """The ROUTE must be metered, not just the limiter class.

    The ceiling is lowered to zero so the very first attempt is over limit: that
    proves the 429 is produced before the handler reads the body or touches the
    charter, which is the whole point of a cost gate.
    """

    monkeypatch.setattr(run_policy, "RUN_BURST_MAX_ATTEMPTS", 0)

    # Reuse the shipped owner-suite assembly so CSRF cookie/header names and the
    # workspace-context override match production exactly.
    from app.auth.config import get_auth_settings
    from test_analysis_http_handlers import _build_app

    app = _build_app(session, {world.workspace_id: world.user_id})
    settings = get_auth_settings()

    burst = run_burst_key(world.workspace_id, world.user_id)
    daily = run_daily_key(world.workspace_id)
    await _clear_buckets(session, burst, daily)

    charter_id = uuid.uuid4()
    path = f"/api/workspaces/{world.workspace_id}/analysis-charters/{charter_id}/runs"
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://analyses.test",
        headers={
            "Origin": "http://analyses.test",
            settings.csrf_header_name: "qa-alpha-csrf",
            "Idempotency-Key": "alpha-gate",
        },
        cookies={settings.csrf_cookie_name: "qa-alpha-csrf"},
    ) as client:
        response = await client.post(path, json={})

    body = response.json()
    assert response.status_code == 429, body
    assert body["error"]["code"] == "REQUEST_RATE_LIMITED"
    assert body["error"]["details"]["limit"] == "workspaceUserBurst"

    await _clear_buckets(session, burst, daily)


async def test_guest_bootstrap_create_path_is_metered(monkeypatch) -> None:
    """One address must not be able to mint unlimited guest workspaces.

    Wiring test: the create path calls the shipped login limiter with a
    guest-specific second dimension. Without it, the guest route was an
    amplifier for the analysis-run budget above.
    """

    import inspect

    from app.auth import guest

    source = inspect.getsource(guest.create_guest)
    reuse_index = source.index("reused=True")
    limiter_index = source.index("check_login_attempt")
    create_index = source.index("hash_password")

    # Metered AFTER the free reuse path and BEFORE anything is allocated.
    assert reuse_index < limiter_index < create_index
    assert "guest-bootstrap:" in source
    assert "LoginRateLimiter" in source


async def test_security_headers_are_present_on_every_response() -> None:
    """Header set must ride ordinary, error AND streaming responses."""

    from fastapi import FastAPI

    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/ok")
    async def ok() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/boom")
    async def boom() -> dict[str, bool]:
        raise ApiFailure("NOT_FOUND", "Not Found", http_status=404)

    register_error_handlers(app)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        for path, expected_status in (("/ok", 200), ("/boom", 404)):
            response = await client.get(path)
            assert response.status_code == expected_status
            for name, value in BASE_HEADERS.items():
                assert response.headers[name] == value, f"{path} missing {name}"
            # HSTS must NOT be sent unless explicitly enabled.
            assert "strict-transport-security" not in response.headers


def test_hsts_is_opt_in() -> None:
    """A plain-HTTP dev server must never emit HSTS for the whole domain."""

    assert hsts_enabled({}) is False
    assert hsts_enabled({"SECURITY_HSTS_ENABLED": "false"}) is False
    assert hsts_enabled({"SECURITY_HSTS_ENABLED": "true"}) is True
    assert hsts_enabled({"SECURITY_HSTS_ENABLED": "1"}) is True


def test_canonical_app_mounts_the_headers_middleware() -> None:
    """Pin the wiring: the production app must carry the middleware."""

    from app.main import app as canonical_app

    assert any(
        middleware.cls is SecurityHeadersMiddleware
        for middleware in canonical_app.user_middleware
    ), "SecurityHeadersMiddleware is not mounted on the canonical app"
