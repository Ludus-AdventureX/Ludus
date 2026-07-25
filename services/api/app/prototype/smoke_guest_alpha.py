"""Real HTTP smoke for the Guest Simulation Technical Alpha (release evidence).

Drives the DEPLOYED stack over real HTTP (no ASGI shortcut, no prototype
route mounting):

    GET  /api/auth/csrf
    POST /api/auth/guest
    POST /api/workspaces/{workspaceId}/simulations/{graphId}/runs
    GET  /api/workspaces/{workspaceId}/simulations/{graphId}/runs/{simulationRunId}

Run it inside the compose network (``docker compose ... run --rm smoke``) or
against any base URL:

    python -m app.prototype.smoke_guest_alpha

Configuration (env):
    SMOKE_BASE_URL  target origin (default http://web:3000 — the same-origin
                    proxy path browsers use);
    SMOKE_ORIGIN    Origin header for CSRF checks (default WEB_ORIGIN, then
                    SMOKE_BASE_URL).

Asserted:
    - two independent cookie clients create two fully isolated guests;
    - re-POST /api/auth/guest on the same cookie jar restores the SAME guest;
    - POST run answers 201 with engineVersion sim-engine-1.1.0 and a
      well-formed sha256 inputHash;
    - GET replay equals the POST payload exactly;
    - guest A cannot see guest B's workspace/graph/profile/run (uniform 404),
      and vice versa.
"""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from typing import Any

import httpx

ENGINE_VERSION_EXPECTED = "sim-engine-1.1.0"
INPUT_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
RUN_BODY_KEYS = (
    "graphVersionId",
    "strategyVersionId",
    "scenarioVersionId",
    "scoreDefinitionId",
    "decisionMakerProfileId",
    "decisionMakerProfileVersion",
)


class SmokeFailure(AssertionError):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def base_url() -> str:
    return os.environ.get("SMOKE_BASE_URL", "http://web:3000").rstrip("/")


def origin() -> str:
    return (
        os.environ.get("SMOKE_ORIGIN")
        or os.environ.get("WEB_ORIGIN")
        or base_url()
    ).rstrip("/")


def new_client() -> httpx.Client:
    """Independent cookie jar per client = independent browser."""

    return httpx.Client(
        base_url=base_url(),
        headers={"Origin": origin()},
        timeout=30,
        trust_env=False,
    )


def csrf_token(client: httpx.Client) -> str:
    response = client.get("/api/auth/csrf")
    check(response.status_code == 200, f"csrf failed: {response.status_code}")
    token = response.json()["data"]["csrfToken"]
    check(bool(token), "csrf token missing")
    return token


def bootstrap_guest(client: httpx.Client) -> dict[str, Any]:
    response = client.post(
        "/api/auth/guest",
        headers={"X-CSRF-Token": csrf_token(client)},
    )
    check(response.status_code == 201, f"guest bootstrap failed: {response.status_code}")
    data = response.json()["data"]
    for key in ("workspaceId", "graphId", *RUN_BODY_KEYS):
        check(bool(data.get(key)), f"guest payload missing {key}")
    return data


def create_run(client: httpx.Client, guest: dict[str, Any]) -> dict[str, Any]:
    body = {"mode": "experimental", **{key: guest[key] for key in RUN_BODY_KEYS}}
    response = client.post(
        f"/api/workspaces/{guest['workspaceId']}/simulations/{guest['graphId']}/runs",
        json=body,
        headers={
            "X-CSRF-Token": csrf_token(client),
            "Idempotency-Key": f"smoke-{uuid.uuid4()}",
        },
    )
    check(
        response.status_code == 201,
        f"run creation returned {response.status_code}: {response.text[:300]}",
    )
    run = response.json()["data"]
    check(bool(run.get("simulationRunId")), "simulationRunId missing")
    check(
        run.get("engineVersion") == ENGINE_VERSION_EXPECTED,
        f"engineVersion {run.get('engineVersion')!r} != {ENGINE_VERSION_EXPECTED!r}",
    )
    check(
        INPUT_HASH_RE.fullmatch(run.get("inputHash", "")) is not None,
        "inputHash missing or malformed",
    )
    return run


def replay_run(client: httpx.Client, guest: dict[str, Any], run: dict[str, Any]) -> None:
    response = client.get(
        f"/api/workspaces/{guest['workspaceId']}/simulations/{guest['graphId']}"
        f"/runs/{run['simulationRunId']}"
    )
    check(response.status_code == 200, f"replay failed: {response.status_code}")
    check(response.json()["data"] == run, "replay payload differs from creation payload")


def assert_cross_guest_denied(
    attacker: httpx.Client,
    attacker_guest: dict[str, Any],
    victim: dict[str, Any],
    victim_run: dict[str, Any],
    label: str,
) -> None:
    """Every cross-guest anchor combination must collapse into a uniform 404."""

    probes = {
        "foreign workspace replay": attacker.get(
            f"/api/workspaces/{victim['workspaceId']}/simulations/{victim['graphId']}"
            f"/runs/{victim_run['simulationRunId']}"
        ),
        "foreign graph in own workspace": attacker.get(
            f"/api/workspaces/{attacker_guest['workspaceId']}/simulations"
            f"/{victim['graphId']}/runs/{victim_run['simulationRunId']}"
        ),
        "foreign run id in own scope": attacker.get(
            f"/api/workspaces/{attacker_guest['workspaceId']}/simulations"
            f"/{attacker_guest['graphId']}/runs/{victim_run['simulationRunId']}"
        ),
        "foreign workspace run create": attacker.post(
            f"/api/workspaces/{victim['workspaceId']}/simulations/{victim['graphId']}/runs",
            json={"mode": "experimental", **{key: victim[key] for key in RUN_BODY_KEYS}},
            headers={
                "X-CSRF-Token": csrf_token(attacker),
                "Idempotency-Key": f"smoke-{uuid.uuid4()}",
            },
        ),
        "foreign profile in own workspace": attacker.post(
            f"/api/workspaces/{attacker_guest['workspaceId']}/simulations"
            f"/{attacker_guest['graphId']}/runs",
            json={
                "mode": "experimental",
                **{key: attacker_guest[key] for key in RUN_BODY_KEYS},
                "decisionMakerProfileId": victim["decisionMakerProfileId"],
            },
            headers={
                "X-CSRF-Token": csrf_token(attacker),
                "Idempotency-Key": f"smoke-{uuid.uuid4()}",
            },
        ),
    }
    for name, response in probes.items():
        check(
            response.status_code == 404,
            f"{label}: {name} answered {response.status_code}, expected uniform 404",
        )


def run_smoke() -> dict[str, Any]:
    with new_client() as client_a, new_client() as client_b:
        guest_a = bootstrap_guest(client_a)
        guest_b = bootstrap_guest(client_b)

        # Two independent cookie jars = two fully isolated guests.
        for key in ("workspaceId", "graphId", "decisionMakerProfileId"):
            check(guest_a[key] != guest_b[key], f"guest isolation violated on {key}")

        # Same cookie jar restores the same guest.
        restored = bootstrap_guest(client_a)
        check(
            restored["workspaceId"] == guest_a["workspaceId"]
            and restored["graphId"] == guest_a["graphId"],
            "same-cookie re-POST did not restore the same guest",
        )
        check(restored.get("reused") is True, "restored guest must report reused=true")

        run_a = create_run(client_a, guest_a)
        run_b = create_run(client_b, guest_b)
        replay_run(client_a, guest_a, run_a)
        replay_run(client_b, guest_b, run_b)

        assert_cross_guest_denied(client_a, guest_a, guest_b, run_b, "guest A -> B")
        assert_cross_guest_denied(client_b, guest_b, guest_a, run_a, "guest B -> A")

    return {
        "baseUrl": base_url(),
        "guestAWorkspace": guest_a["workspaceId"],
        "guestBWorkspace": guest_b["workspaceId"],
        "runA": run_a["simulationRunId"],
        "runB": run_b["simulationRunId"],
        "engineVersion": run_a["engineVersion"],
        "inputHashA": run_a["inputHash"],
        "sameCookieReuse": True,
        "crossGuestUniform404": True,
        "replayIdentical": True,
    }


def main() -> int:
    try:
        summary = run_smoke()
    except SmokeFailure as failure:
        print(f"SMOKE FAIL: {failure}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
    print("SMOKE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
