"""Prepared QA for the auth security hardening lane (matrix rows SH-01/SH-08).

Verifies the Postgres-backed login rate limiter and tokenVersion enforcement
from the QA_QUEUE_ACTIVATION list. Skips cleanly until ``app.security.rate_limits``
exists. The ``login_rate_buckets`` schema is created explicitly via the lane's
``ensure_login_rate_schema`` helper because the canonical migration is still a
pending Contract Lead deliverable — the final release verdict for this lane
therefore waits for the combined implementation+migration+env HEAD.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

pytest.importorskip(
    "app.security.rate_limits", reason="auth security hardening not delivered yet"
)

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import create_async_engine

from app.db import get_database_url
from app.models import UserSession
from app.security.envelope import ApiFailure
from app.security.rate_limits import (
    ensure_login_rate_schema,
    login_account_key,
    login_ip_key,
    login_rate_buckets,
)

from tests.conftest import QA_PASSWORD, csrf_headers, execute_committed, fetch_committed, qa_client, register_user

LOGIN = "/api/auth/login"


@pytest.fixture(autouse=True)
async def _rate_schema():
    """Create the throttle table on the disposable DB (pre-migration parity)."""

    engine = create_async_engine(get_database_url())
    try:
        await ensure_login_rate_schema(engine)
    finally:
        await engine.dispose()


async def _login(client, email: str, password: str = QA_PASSWORD):
    headers = await csrf_headers(client)
    return await client.post(LOGIN, json={"email": email, "password": password}, headers=headers)


def _assert_rate_limited(response) -> None:
    assert response.status_code == 429, response.text
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "REQUEST_RATE_LIMITED"
    retry = body["error"]["details"]["retryAfterSeconds"]
    assert isinstance(retry, int) and 60 <= retry <= 24 * 3600, (
        "retryAfter must be a sane bounded integer"
    )


async def test_account_bucket_throttles_repeated_failures() -> None:
    """SH-01: per-account limit trips after the configured failed attempts."""

    from app.auth.config import get_auth_settings

    limit = get_auth_settings().login_rate_account_max_attempts
    async with qa_client() as client:
        email, _ = await register_user(client)
        response = None
        for _ in range(limit + 1):
            response = await _login(client, email, "wrong-password-attempt")
        _assert_rate_limited(response)


async def test_ip_bucket_counts_across_accounts() -> None:
    """SH-01: one address rotating across many accounts hits the IP limit."""

    from app.auth.config import get_auth_settings

    ip_limit = get_auth_settings().login_rate_ip_max_attempts
    shared_ip = f"10.99.{uuid4().bytes[0]}.{uuid4().bytes[1]}"
    async with qa_client(client_ip=shared_ip) as client:
        response = None
        for index in range(ip_limit + 1):
            response = await _login(
                client, f"qa-rotate-{index}-{uuid4().hex[:8]}@example.test", "wrong-pass-123"
            )
        _assert_rate_limited(response)


async def test_correct_password_is_still_429_while_throttled() -> None:
    """SH-01: the limiter meters the attempt before any credential work."""

    from app.auth.config import get_auth_settings

    limit = get_auth_settings().login_rate_account_max_attempts
    async with qa_client() as client:
        email, _ = await register_user(client)
        for _ in range(limit + 1):
            await _login(client, email, "wrong-password-attempt")
        correct = await _login(client, email, QA_PASSWORD)
        _assert_rate_limited(correct)


async def test_successful_login_clears_only_the_account_bucket() -> None:
    """SH-01: success releases the account dimension; the IP budget keeps counting."""

    async with qa_client() as client:
        email, _ = await register_user(client)
        await _login(client, email, "wrong-password-attempt")
        ok = await _login(client, email, QA_PASSWORD)
        assert ok.status_code == 200

    account_rows = await fetch_committed(
        select(func.count()).where(
            login_rate_buckets.c.bucket_key == login_account_key(email)
        )
    )
    assert account_rows[0][0] == 0, "account bucket must be cleared on success"


async def test_ip_bucket_survives_successful_login() -> None:
    shared_ip = f"10.98.{uuid4().bytes[0]}.{uuid4().bytes[1]}"
    async with qa_client(client_ip=shared_ip) as client:
        email, _ = await register_user(client)
        ok = await _login(client, email, QA_PASSWORD)
        assert ok.status_code == 200

    ip_rows = await fetch_committed(
        select(func.coalesce(func.sum(login_rate_buckets.c.attempts), 0)).where(
            login_rate_buckets.c.bucket_key == login_ip_key(shared_ip)
        )
    )
    assert ip_rows[0][0] >= 1, "IP dimension must keep counting after success"


async def test_store_contains_no_raw_email_or_ip() -> None:
    """SH-01 privacy: bucket keys are digests; raw identifiers never persist."""

    marker_ip = f"10.96.{uuid4().bytes[0]}.{uuid4().bytes[1]}"
    async with qa_client(client_ip=marker_ip) as client:
        email, _ = await register_user(client)
        await _login(client, email, "wrong-password-attempt")

    rows = await fetch_committed(select(login_rate_buckets.c.bucket_key))
    keys = [row[0] for row in rows]
    assert keys, "throttle rows must exist"
    for key in keys:
        assert len(key) == 64 and all(c in "0123456789abcdef" for c in key)
        assert "@" not in key and marker_ip not in key


async def test_missing_table_fails_closed() -> None:
    """SH-01: storage failure rejects the attempt instead of admitting it."""

    from app.auth.config import get_auth_settings
    from app.security.rate_limits import LoginRateLimiter

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from sqlalchemy.pool import NullPool
    from sqlalchemy import text

    engine = create_async_engine(get_database_url(), poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("ALTER TABLE login_rate_buckets RENAME TO qa_hidden_rate_buckets")
            )
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        limiter = LoginRateLimiter(get_auth_settings())
        async with factory() as session:
            with pytest.raises(ApiFailure) as excinfo:
                await limiter.check_login_attempt(
                    session, client_ip="10.95.0.1", email="qa-failclosed@example.test"
                )
        assert excinfo.value.code == "REQUEST_RATE_LIMITED"
        assert excinfo.value.http_status == 429
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("ALTER TABLE qa_hidden_rate_buckets RENAME TO login_rate_buckets")
            )
        await engine.dispose()


async def test_concurrent_attempts_count_atomically() -> None:
    """SH-01: parallel workers upsert via ON CONFLICT; no attempt is lost."""

    import asyncio

    from app.auth.config import get_auth_settings
    from app.security.rate_limits import LoginRateLimiter

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from sqlalchemy.pool import NullPool

    email = f"qa-atomic-{uuid4().hex[:10]}@example.test"
    engine = create_async_engine(get_database_url(), poolclass=NullPool)
    limiter = LoginRateLimiter(get_auth_settings())
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def one_attempt() -> None:
        async with factory() as session:
            try:
                await limiter.check_login_attempt(
                    session, client_ip=f"10.94.0.{uuid4().bytes[0]}", email=email
                )
            except ApiFailure:
                pass  # over-limit is fine; the row count below is the assertion

    try:
        await asyncio.gather(*(one_attempt() for _ in range(8)))
        totals = await fetch_committed(
            select(func.coalesce(func.sum(login_rate_buckets.c.attempts), 0)).where(
                login_rate_buckets.c.bucket_key == login_account_key(email)
            )
        )
        assert totals[0][0] == 8, "every concurrent attempt must be counted exactly once"
    finally:
        await engine.dispose()


async def test_token_version_bump_rejects_live_session_formally() -> None:
    """SH-08: QA-TASK03-002 flip — version bump must reject old tokens.

    This is the formal (non-xfail) twin of the historical regression; the
    xfail marker in test_auth_sessions.py is removed together with the lane's
    combined-HEAD release review.
    """

    async with qa_client() as client:
        email, _ = await register_user(client)
        token = client.cookies.get("decision_lab_session")
        assert token

        import base64
        import json as jsonlib
        from uuid import UUID

        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        session_id = UUID(str(jsonlib.loads(base64.urlsafe_b64decode(payload))["session_id"]))

        await execute_committed(
            update(UserSession)
            .where(UserSession.id == session_id)
            .values(token_version=UserSession.token_version + 1)
        )

        replay = await client.get("/api/auth/session")
        assert replay.status_code == 401
        assert replay.json()["error"]["code"] == "SESSION_REVOKED_OR_EXPIRED"


async def test_expired_slices_do_not_extend_throttle_forever() -> None:
    """retryAfter sanity: old slices age out of the sliding window."""

    from app.auth.config import get_auth_settings
    from app.security.rate_limits import LoginRateLimiter

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from sqlalchemy.pool import NullPool

    settings = get_auth_settings()
    email = f"qa-window-{uuid4().hex[:10]}@example.test"
    stale = datetime.now(timezone.utc) - timedelta(
        minutes=settings.login_rate_window_minutes + 5
    )
    # Seed an over-limit count entirely outside the window.
    await execute_committed(
        login_rate_buckets.insert().values(
            bucket_key=login_account_key(email),
            slice_start=stale,
            attempts=settings.login_rate_account_max_attempts + 10,
        )
    )
    engine = create_async_engine(get_database_url(), poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        limiter = LoginRateLimiter(settings)
        async with factory() as session:
            # Must NOT raise: stale attempts are outside the sliding window.
            await limiter.check_login_attempt(
                session, client_ip=f"10.93.0.{uuid4().bytes[0]}", email=email
            )
    finally:
        await engine.dispose()
