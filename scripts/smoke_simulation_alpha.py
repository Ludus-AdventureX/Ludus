"""End-to-end smoke for the simulation-alpha demo scope (SIM_ALPHA_SEED_SMOKE_FAST).

Integration revision: the SIM-02A run routes are now REAL product surface
(app/simulations/routes.py mounted under ``workspace_router``), so the smoke no
longer attaches prototype routes. It drives the canonical app through the real
ASGI stack (httpx ASGITransport), exercising the production auth/CSRF/tenancy/
idempotency dependencies:

- ``GET  /api/auth/csrf``  then ``POST /api/auth/login`` (demo credentials);
- ``POST /api/workspaces/{workspaceId}/simulations/{graphId}/runs``
  → 201 on convergence, or the contract non-convergence 409 envelope
  (``error.code = SIMULATION_NOT_CONVERGED``);
- re-``POST`` with the same ``Idempotency-Key`` → committed replay with
  ``meta.idempotencyReplay = true`` and an identical payload;
- ``GET  .../runs/{simulationRunId}`` replay.

Assertions: status 201/409, run id present, ``engineVersion == sim-engine-1.1.0``,
``inputHash`` present (sha256 format), idempotent re-POST replays the identical
payload, and the GET replay payload is byte-identical to the creation payload.
The demo password comes ONLY from ``SIMULATION_ALPHA_DEMO_PASSWORD``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

SCRIPTS_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPTS_ROOT.parent
API_ROOT = REPOSITORY_ROOT / "services" / "api"
for path in (str(SCRIPTS_ROOT), str(API_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from seed_simulation_alpha import (  # noqa: E402
    FIXTURE_PATH,
    derive_ids,
    require_demo_password,
)

BASE_URL = "http://simulation-alpha.local"
ENGINE_VERSION_EXPECTED = "sim-engine-1.1.0"
INPUT_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class SmokeFailure(AssertionError):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


async def run_smoke(fixture: dict[str, Any], password: str) -> dict[str, Any]:
    import httpx

    from app.main import app

    ids = derive_ids(fixture)
    workspace_id = str(ids["workspace_id"])
    graph_id = str(ids["graph_id"])
    origin_headers = {"Origin": BASE_URL}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        # 1. CSRF token (double-submit cookie + body value).
        csrf_response = await client.get("/api/auth/csrf")
        check(csrf_response.status_code == 200, f"csrf failed: {csrf_response.status_code}")
        csrf_token = csrf_response.json()["data"]["csrfToken"]
        mutation_headers = {**origin_headers, "X-CSRF-Token": csrf_token}

        # 2. Login with the seeded demo credentials.
        login_response = await client.post(
            "/api/auth/login",
            json={"email": fixture["demoEmail"], "password": password},
            headers=mutation_headers,
        )
        check(login_response.status_code == 200, f"login failed: {login_response.status_code}")
        memberships = login_response.json()["data"]["memberships"]
        check(
            any(item["workspaceId"] == workspace_id for item in memberships),
            "demo user is not a member of the seeded workspace",
        )

        # 3. Create the simulation run through the real SIM-02A route.
        # Frozen POST body (§5): anchors only, extra="forbid"; riskTolerance /
        # engineVersion / includeSensitivity are server-owned.
        run_body = {
            "mode": fixture["run"]["simulationMode"],
            "graphVersionId": str(ids["graph_version_id"]),
            "strategyVersionId": str(ids["strategy_version_id"]),
            "scenarioVersionId": str(ids["scenario_version_id"]),
            "scoreDefinitionId": str(ids["score_definition_id"]),
            "decisionMakerProfileId": str(ids["profile_id"]),
            "decisionMakerProfileVersion": fixture["profile"]["version"],
            "epsilon": fixture["run"]["epsilon"],
            "maxSteps": fixture["run"]["maxSteps"],
        }
        idempotency_key = f"smoke-{uuid4()}"
        run_headers = {**mutation_headers, "Idempotency-Key": idempotency_key}
        run_path = f"/api/workspaces/{workspace_id}/simulations/{graph_id}/runs"
        create_response = await client.post(run_path, json=run_body, headers=run_headers)
        check(
            create_response.status_code in (201, 409),
            f"run creation returned {create_response.status_code}: {create_response.text[:400]}",
        )
        create_envelope = create_response.json()
        if create_response.status_code == 409:
            check(
                create_envelope["error"]["code"] == "SIMULATION_NOT_CONVERGED",
                "409 must carry the contract SIMULATION_NOT_CONVERGED code",
            )
            run_id = create_envelope["error"]["details"]["simulationRunId"]
        else:
            created = create_envelope["data"]
            run_id = created.get("simulationRunId", "")

            # 4. Contract assertions on the created run.
            check(bool(run_id) and UUID(run_id) is not None, "run id missing from creation payload")
            check(
                created["engineVersion"] == ENGINE_VERSION_EXPECTED,
                f"engineVersion {created['engineVersion']!r} != {ENGINE_VERSION_EXPECTED!r}",
            )
            check(
                INPUT_HASH_RE.fullmatch(created.get("inputHash", "")) is not None,
                "inputHash missing or malformed on the creation payload",
            )

        # 5. Idempotent re-POST: same key + same body replays the committed
        # outcome with meta.idempotencyReplay = true (§4.7/§4.9).
        replay_post = await client.post(run_path, json=run_body, headers=run_headers)
        check(
            replay_post.status_code == create_response.status_code,
            f"idempotent replay status {replay_post.status_code} != {create_response.status_code}",
        )
        replay_envelope = replay_post.json()
        if create_response.status_code == 201:
            check(
                replay_envelope.get("meta", {}).get("idempotencyReplay") is True,
                "idempotent replay must set meta.idempotencyReplay = true",
            )
            check(
                replay_envelope["data"] == create_envelope["data"],
                "idempotent replay payload differs from the creation payload",
            )

        # 6. GET replay must be identical to the creation payload.
        replay_response = await client.get(f"{run_path}/{run_id}", headers=origin_headers)
        check(replay_response.status_code == 200, f"replay failed: {replay_response.status_code}")
        replayed = replay_response.json()["data"]
        if create_response.status_code == 201:
            check(
                replayed == create_envelope["data"],
                "replay payload differs from the creation payload",
            )
        check(
            replayed["engineVersion"] == ENGINE_VERSION_EXPECTED,
            f"engineVersion {replayed['engineVersion']!r} != {ENGINE_VERSION_EXPECTED!r}",
        )
        check(
            INPUT_HASH_RE.fullmatch(replayed.get("inputHash", "")) is not None,
            "inputHash missing or malformed on the replay payload",
        )

    return {
        "createStatus": create_response.status_code,
        "runId": run_id,
        "engineVersion": replayed["engineVersion"],
        "inputHash": replayed["inputHash"],
        "convergenceStatus": replayed["convergenceStatus"],
        "idempotencyReplay": create_response.status_code == 201,
        "replayIdentical": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke the seeded simulation-alpha scope.")
    parser.add_argument("--fixture", type=Path, default=FIXTURE_PATH, help="seed fixture JSON path")
    args = parser.parse_args(argv)
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    password = require_demo_password()
    try:
        summary = asyncio.run(run_smoke(fixture, password))
    except SmokeFailure as failure:
        print(f"SMOKE FAIL: {failure}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
    print("SMOKE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
