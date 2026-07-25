"""Explicit Closed Alpha seed for the prototype stack (compose.prototype.yaml).

Registers the initial owner account and workspace through the public auth
contract (GET /api/auth/csrf + POST /api/auth/register), so no business logic
is duplicated here. The script is idempotent: a 422 VALIDATION_FAILED response
from /api/auth/register means the account already exists and existing data is
left untouched. Run it only via the explicit seed command:

    docker compose --env-file .env.prototype -f compose.prototype.yaml run --rm seed
"""

from __future__ import annotations

import os
import sys

import httpx


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"SEED_ERROR missing required environment variable {name}", file=sys.stderr)
        raise SystemExit(2)
    return value


def main() -> int:
    base_url = os.environ.get("SEED_API_BASE_URL", "http://api:8000").rstrip("/")
    email = require_env("SEED_EMAIL")
    password = require_env("SEED_PASSWORD")
    workspace_name = os.environ.get("SEED_WORKSPACE_NAME", "").strip() or None

    with httpx.Client(base_url=base_url, timeout=15.0) as client:
        csrf = client.get("/api/auth/csrf")
        csrf.raise_for_status()
        # CanonicalModel serializes by alias: the wire key is camelCase.
        token = csrf.json()["data"]["csrfToken"]

        payload: dict[str, str] = {"email": email, "password": password}
        if workspace_name:
            payload["workspace_name"] = workspace_name
        response = client.post(
            "/api/auth/register",
            json=payload,
            headers={"X-CSRF-Token": token},
        )

    if response.status_code == 201:
        print(f"SEEDED owner account {email}")
        return 0
    if response.status_code == 422:
        # Anti-enumeration contract: duplicates answer with a generic 422.
        print(f"SEED_SKIPPED account {email} already registered; data left untouched")
        return 0

    print(
        f"SEED_ERROR unexpected response {response.status_code}: {response.text}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
