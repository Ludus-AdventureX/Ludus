"""Task 3 QA gate: authentication basics (acceptance matrix rows A-01, A-03, S-02).

These tests skip until the case_api_data lane delivers ``app.auth``. They then
run unchanged as acceptance tests against the real implementation.
"""

from __future__ import annotations

import pytest

pytest.importorskip("app.auth", reason="Task 3 auth implementation not delivered yet")

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.main import app
from app.models import User

REGISTER_PATH = "/api/auth/register"
LOGIN_PATH = "/api/auth/login"
CSRF_PATH = "/api/auth/csrf"

QA_PASSWORD = "correct horse battery staple"


def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Origin": "http://testserver"},
    )


async def _csrf_headers(client: httpx.AsyncClient) -> dict[str, str]:
    response = await client.get(CSRF_PATH)
    assert response.status_code == 200, "CSRF token endpoint must exist (C-01)"
    token = response.json().get("data", {}).get("token") or response.json().get("token")
    assert token, "CSRF endpoint must return a token"
    return {"X-CSRF-Token": token}


async def test_register_stores_argon2_hash_only(db_connection: AsyncConnection) -> None:
    """A-01: password persisted as Argon2 hash, never plaintext or reversible."""

    email = "qa-register-a01@example.test"
    async with _client() as client:
        headers = await _csrf_headers(client)
        response = await client.post(
            REGISTER_PATH,
            json={"email": email, "password": QA_PASSWORD},
            headers=headers,
        )
        assert response.status_code in (200, 201)

    row = (
        await db_connection.execute(select(User.password_hash).where(User.email == email))
    ).scalar_one_or_none()
    assert row is not None
    assert row.startswith("$argon2"), "password_hash must be an Argon2 hash"
    assert QA_PASSWORD not in row


async def test_login_sets_hardened_session_cookie() -> None:
    """A-03: session cookie is HttpOnly with SameSite=Lax; Secure is env-driven."""

    email = "qa-cookie-a03@example.test"
    async with _client() as client:
        headers = await _csrf_headers(client)
        register = await client.post(
            REGISTER_PATH,
            json={"email": email, "password": QA_PASSWORD},
            headers=headers,
        )
        assert register.status_code in (200, 201)
        response = await client.post(
            LOGIN_PATH,
            json={"email": email, "password": QA_PASSWORD},
            headers=headers,
        )
        assert response.status_code == 200
        set_cookie = response.headers.get("set-cookie", "")
        assert set_cookie, "login must set a session cookie"
        lowered = set_cookie.lower()
        assert "httponly" in lowered
        assert "samesite=lax" in lowered


async def test_auth_responses_never_echo_secrets() -> None:
    """S-02: bodies of register/login/failed-login never leak password or hash."""

    email = "qa-secret-s02@example.test"
    async with _client() as client:
        headers = await _csrf_headers(client)
        register = await client.post(
            REGISTER_PATH,
            json={"email": email, "password": QA_PASSWORD},
            headers=headers,
        )
        good = await client.post(
            LOGIN_PATH,
            json={"email": email, "password": QA_PASSWORD},
            headers=headers,
        )
        bad = await client.post(
            LOGIN_PATH,
            json={"email": email, "password": "wrong-password-attempt"},
            headers=headers,
        )
    for response in (register, good, bad):
        body = response.text
        assert QA_PASSWORD not in body
        assert "$argon2" not in body
        assert "password_hash" not in body
