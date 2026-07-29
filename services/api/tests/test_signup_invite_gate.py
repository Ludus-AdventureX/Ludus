"""The public door is closed: registration requires an invite code.

The alpha used to admit anyone through the prototype guest endpoint, and each
admission minted a workspace with its own analysis-run budget. Registration is
now the entry point and it is gated on a code the operator hands out.

What these tests hold in place:

- no code, a wrong code, and "this deployment has no codes configured" are
  byte-identical responses, so the endpoint cannot be probed for its state;
- the gate fails CLOSED - an unset variable admits nobody;
- a valid code produces a real OWNER membership (the invited person can work,
  not just authenticate);
- registration is metered, because it allocates budget-carrying tenants.
"""

from __future__ import annotations

import os
from uuid import uuid4

from app.auth.signup_invites import (
    SIGNUP_INVITE_HASHES_ENV,
    invite_code_digest,
    signup_code_accepted,
)

from tests.conftest import QA_PASSWORD, QA_SIGNUP_CODE, csrf_headers, qa_client


async def _attempt(client, *, email: str, code: str | None) -> object:
    headers = await csrf_headers(client)
    body: dict[str, object] = {"email": email, "password": QA_PASSWORD}
    if code is not None:
        body["inviteCode"] = code
    return await client.post("/api/auth/register", json=body, headers=headers)


def _assert_gate_refusal(response) -> None:
    assert response.status_code == 403, response.text
    error = response.json()["error"]
    assert error["code"] == "SIGNUP_INVITE_REQUIRED"
    assert error["message"] == "Registration requires a valid invite code."


def _fresh_email() -> str:
    # register() commits, so an email persists across runs of this suite; a
    # unique local part keeps each test exercising the gate, not a stale
    # duplicate-email rejection.
    return f"invite-{uuid4().hex[:12]}@example.test"


async def test_valid_code_admits_and_grants_an_owner_workspace() -> None:
    async with qa_client() as client:
        response = await _attempt(client, email=_fresh_email(), code=QA_SIGNUP_CODE)
        assert response.status_code == 201, response.text
        data = response.json()["data"]
        memberships = data["memberships"]
        assert len(memberships) == 1
        assert memberships[0]["role"] == "owner"
        assert memberships[0]["status"] == "active"
        # An invited person must be able to DO something, not merely log in.
        assert memberships[0]["capabilities"]


async def test_missing_and_wrong_codes_are_indistinguishable() -> None:
    async with qa_client() as client:
        without = await _attempt(client, email=_fresh_email(), code=None)
        wrong = await _attempt(client, email=_fresh_email(), code="not-the-code")
    _assert_gate_refusal(without)
    _assert_gate_refusal(wrong)
    assert without.json() == wrong.json()


async def test_gate_fails_closed_when_no_code_is_configured() -> None:
    previous = os.environ.get(SIGNUP_INVITE_HASHES_ENV)
    os.environ.pop(SIGNUP_INVITE_HASHES_ENV, None)
    try:
        async with qa_client() as client:
            response = await _attempt(
                client, email=_fresh_email(), code=QA_SIGNUP_CODE
            )
        _assert_gate_refusal(response)
    finally:
        if previous is not None:
            os.environ[SIGNUP_INVITE_HASHES_ENV] = previous


async def test_registration_is_metered_per_account() -> None:
    """Five refused attempts on one address, then the throttle takes over."""

    email = f"throttled-{uuid4().hex[:12]}@example.test"
    async with qa_client(client_ip="10.90.1.1") as client:
        seen_429 = False
        for _ in range(8):
            response = await _attempt(client, email=email, code="wrong")
            if response.status_code == 429:
                assert response.json()["error"]["code"] == "REQUEST_RATE_LIMITED"
                seen_429 = True
                break
            _assert_gate_refusal(response)
        assert seen_429, "registration must be rate limited like login"


# --- code matching (unit) ----------------------------------------------------


def test_only_correctly_shaped_digests_are_honoured(monkeypatch) -> None:
    # A truncated or malformed digest is a config typo; honouring it would mean
    # comparing against something that cannot be a SHA-256 of any code.
    monkeypatch.setenv(SIGNUP_INVITE_HASHES_ENV, "deadbeef, NOTAHASH")
    assert signup_code_accepted("anything") is False

    good = invite_code_digest("second-code")
    monkeypatch.setenv(SIGNUP_INVITE_HASHES_ENV, f"deadbeef,{good.upper()}")
    # Case-insensitive on the configured side, exact on the code side.
    assert signup_code_accepted("second-code") is True
    assert signup_code_accepted("Second-Code") is False


def test_oversized_code_is_refused_without_hashing(monkeypatch) -> None:
    monkeypatch.setenv(SIGNUP_INVITE_HASHES_ENV, invite_code_digest("x"))
    assert signup_code_accepted("x" * 500) is False
