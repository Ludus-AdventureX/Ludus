"""Task 3 QA gate: CSRF double-submit protection (acceptance rows C-01..C-03).

Skips until the case_api_data lane delivers ``app.security.csrf``.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

pytest.importorskip(
    "app.security.csrf", reason="Task 3 CSRF implementation not delivered yet"
)

import httpx

from app.main import app

REGISTER_PATH = "/api/auth/register"
CSRF_PATH = "/api/auth/csrf"

QA_PASSWORD = "correct horse battery staple"


def _client(origin: str | None = "http://testserver") -> httpx.AsyncClient:
    headers = {"Origin": origin} if origin else {}
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers=headers,
    )


def _payload() -> dict[str, str]:
    return {"email": f"qa-csrf-{uuid4().hex[:10]}@example.test", "password": QA_PASSWORD}


async def test_csrf_endpoint_issues_double_submit_token() -> None:
    """C-01: GET /api/auth/csrf returns a token and a readable cookie pair."""

    async with _client() as client:
        response = await client.get(CSRF_PATH)
        assert response.status_code == 200
        body = response.json()
        token = body.get("data", {}).get("token") or body.get("token")
        assert token
        set_cookie = response.headers.get("set-cookie", "")
        assert set_cookie, "CSRF cookie must be set"
        assert "httponly" not in set_cookie.lower(), (
            "double-submit CSRF cookie must be readable by the frontend"
        )


async def test_mutation_without_csrf_token_is_rejected() -> None:
    """C-02: cookie mutation without the CSRF header fails with structured error."""

    async with _client() as client:
        await client.get(CSRF_PATH)  # cookie present, header missing
        response = await client.post(REGISTER_PATH, json=_payload())
        assert response.status_code in (400, 403)
        assert "CSRF_VALIDATION_FAILED" in response.text


async def test_mutation_with_mismatched_token_is_rejected() -> None:
    """C-02: header/cookie token mismatch fails."""

    async with _client() as client:
        await client.get(CSRF_PATH)
        response = await client.post(
            REGISTER_PATH,
            json=_payload(),
            headers={"X-CSRF-Token": "qa-mismatched-token-value"},
        )
        assert response.status_code in (400, 403)
        assert "CSRF_VALIDATION_FAILED" in response.text


async def test_mutation_with_foreign_origin_is_rejected() -> None:
    """C-02: exact-Origin check rejects a foreign origin even with a valid token."""

    async with _client(origin="https://evil.example") as client:
        csrf = await client.get(CSRF_PATH)
        token = csrf.json().get("data", {}).get("token") or csrf.json().get("token")
        response = await client.post(
            REGISTER_PATH,
            json=_payload(),
            headers={"X-CSRF-Token": token or ""},
        )
        assert response.status_code in (400, 403)
        assert "CSRF_VALIDATION_FAILED" in response.text


async def test_csrf_error_does_not_leak_token_values() -> None:
    """C-03: the failure envelope never echoes cookie or header token values."""

    async with _client() as client:
        csrf = await client.get(CSRF_PATH)
        token = csrf.json().get("data", {}).get("token") or csrf.json().get("token")
        response = await client.post(
            REGISTER_PATH,
            json=_payload(),
            headers={"X-CSRF-Token": "qa-mismatched-token-value"},
        )
        assert response.status_code in (400, 403)
        assert token not in response.text
        assert "qa-mismatched-token-value" not in response.text
