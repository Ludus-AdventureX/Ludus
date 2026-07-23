"""Task 3 QA gate: authentication basics (acceptance matrix rows A-01, A-03, S-02).

Skips until the case_api_data lane delivers ``app.auth``; afterwards it runs
against the QA app assembly that mirrors the CONTRACT_CHANGE_REQUEST mounting.
"""

from __future__ import annotations

import pytest

pytest.importorskip("app.auth", reason="Task 3 auth implementation not delivered yet")

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.models import User

from tests.conftest import QA_PASSWORD, csrf_headers, qa_client, register_user


async def test_register_stores_argon2_hash_only(db_connection: AsyncConnection) -> None:
    """A-01: password persisted as Argon2 hash, never plaintext or reversible."""

    async with qa_client() as client:
        email, _ = await register_user(client)

    row = (
        await db_connection.execute(select(User.password_hash).where(User.email == email))
    ).scalar_one_or_none()
    assert row is not None
    assert row.startswith("$argon2"), "password_hash must be an Argon2 hash"
    assert QA_PASSWORD not in row


async def test_login_sets_hardened_session_cookie() -> None:
    """A-03: session cookie is HttpOnly with SameSite=Lax; Secure is env-driven."""

    async with qa_client() as client:
        email, _ = await register_user(client)
        headers = await csrf_headers(client)
        response = await client.post(
            "/api/auth/login",
            json={"email": email, "password": QA_PASSWORD},
            headers=headers,
        )
        assert response.status_code == 200
        cookie_headers = [
            value
            for key, value in response.headers.multi_items()
            if key.lower() == "set-cookie" and value.startswith("decision_lab_session=")
        ]
        assert cookie_headers, "login must set the decision_lab_session cookie"
        lowered = cookie_headers[0].lower()
        assert "httponly" in lowered
        assert "samesite=lax" in lowered


async def test_duplicate_email_registration_is_uniformly_rejected() -> None:
    """S-02 support: duplicate registration cannot enumerate existing emails."""

    async with qa_client() as client:
        email, _ = await register_user(client)
        headers = await csrf_headers(client)
        duplicate = await client.post(
            "/api/auth/register",
            json={"email": email, "password": QA_PASSWORD},
            headers=headers,
        )
        assert duplicate.status_code == 422
        body = duplicate.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "VALIDATION_FAILED"
        assert email not in duplicate.text


async def test_auth_responses_never_echo_secrets() -> None:
    """S-02: bodies of register/login/failed-login never leak password or hash."""

    async with qa_client() as client:
        email, register_data = await register_user(client)
        headers = await csrf_headers(client)
        good = await client.post(
            "/api/auth/login",
            json={"email": email, "password": QA_PASSWORD},
            headers=headers,
        )
        bad = await client.post(
            "/api/auth/login",
            json={"email": email, "password": "wrong-password-attempt"},
            headers=headers,
        )
    assert "passwordHash" not in str(register_data)
    for response in (good, bad):
        body = response.text
        assert QA_PASSWORD not in body
        assert "$argon2" not in body
        assert "password_hash" not in body and "passwordHash" not in body


async def test_unknown_email_and_wrong_password_are_indistinguishable() -> None:
    """S-02/enumeration: unknown email and bad password return identical failures."""

    async with qa_client() as client:
        email, _ = await register_user(client)
        headers = await csrf_headers(client)
        wrong_password = await client.post(
            "/api/auth/login",
            json={"email": email, "password": "wrong-password-attempt"},
            headers=headers,
        )
        unknown_email = await client.post(
            "/api/auth/login",
            json={"email": "qa-nobody-here@example.test", "password": QA_PASSWORD},
            headers=headers,
        )
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert wrong_password.json()["error"]["code"] == "AUTH_INVALID_CREDENTIALS"
