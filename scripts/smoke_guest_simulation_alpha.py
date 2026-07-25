"""Guest alpha smoke (SEED + AUTO SMOKE — GUEST ISOLATION FAST IMPLEMENTATION).

Drives the real ASGI app in-process (httpx ASGITransport) through:

1. ``GET  /api/auth/csrf``;
2. ``POST /api/auth/guest``  (server-side bootstrap, HttpOnly cookie);
3. ``POST .../simulation-runs``  (prototype route, runtime-mounted only);
4. ``GET  .../simulation-runs/{runId}``  replay identity;
5. a SECOND independent cookie client repeating 1-4, then isolation checks:
   all identity/workspace/demo IDs disjoint, A using B's graph/profile 404,
   A probing B's workspace 404, A replaying B's run 404.

The disabled-flag gate (uniform 404 without ``ENABLE_GUEST_ALPHA``) is
verified first, then the flag is enabled in-process for the bootstrap flow.
No product file is modified; simulations stay route-less in the repo.
"""

# NOTE: no ``from __future__ import annotations`` — FastAPI must introspect the
# function-local prototype route annotations as real objects.

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

SCRIPTS_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPTS_ROOT.parent
API_ROOT = REPOSITORY_ROOT / "services" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

BASE_URL = "http://guest-alpha.local"
ENGINE_VERSION_EXPECTED = "sim-engine-1.1.0"
INPUT_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
GUEST_FLAG = "ENABLE_GUEST_ALPHA"

ID_FIELDS = (
    "workspaceId",
    "decisionCaseId",
    "graphId",
    "graphVersionId",
    "strategyVersionId",
    "scenarioVersionId",
    "scoreDefinitionId",
    "decisionMakerProfileId",
)


class SmokeFailure(AssertionError):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def assert_guest_payload(data: dict) -> None:
    """Unit-verifiable helper: every contract field present and UUID-shaped."""

    for field in ID_FIELDS:
        value = data.get(field, "")
        check(bool(value), f"guest payload missing {field}")
        UUID(value)  # raises on malformed ids
    check(
        data.get("decisionMakerProfileVersion") == 1,
        "decisionMakerProfileVersion must be 1 for a fresh guest",
    )


def assert_disjoint(data_a: dict, data_b: dict) -> None:
    """Unit-verifiable helper: two guests share no identity/workspace/demo id."""

    for field in ID_FIELDS:
        check(
            data_a.get(field) != data_b.get(field),
            f"guest isolation breached: shared {field}",
        )


def build_prototype_app() -> Any:
    """Mount prototype run/replay routes onto the real app (runtime only)."""

    from fastapi import APIRouter, Depends
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db import get_session
    from app.main import app
    from app.models import SimulationRun as SimulationRunRow
    from app.simulations.domain import SimulationError
    from app.simulations.errors import simulation_scope_not_found
    from app.simulations.service import SimulationRunRequest, SimulationRunService
    from app.tenancy.context import WorkspaceContext, require_workspace_context
    from app.types import SimulationConvergenceStatus, SimulationMode

    marker = "/api/workspaces/{workspaceId}/cases/{caseId}/simulation-runs"
    if any(getattr(route, "path", "") == marker for route in app.routes):
        return app  # already mounted in this process

    class RunRequestBody(BaseModel):
        graphVersionId: UUID
        strategyVersionId: UUID
        scenarioVersionId: UUID
        scoreDefinitionId: UUID
        simulationMode: SimulationMode
        decisionMakerProfileId: UUID
        decisionMakerProfileVersion: int
        epsilon: float = 0.001
        maxSteps: int = 12
        includeSensitivity: bool = False

    def payload_from(view: Any) -> dict:
        return {
            "id": str(view.id),
            "workspaceId": str(view.workspace_id),
            "decisionCaseId": str(view.decision_case_id),
            "graphId": str(view.graph_id),
            "graphVersionId": str(view.graph_version_id),
            "engineVersion": view.engine_version,
            "simulationMode": view.simulation_mode.value,
            "epsilon": view.epsilon,
            "maxSteps": view.max_steps,
            "steps": view.steps,
            "inputHash": view.input_hash,
            "nodeResults": dict(view.node_results),
            "convergenceStatus": view.convergence_status.value,
            "createdAt": view.created_at.isoformat(),
        }

    router = APIRouter(
        prefix="/api/workspaces/{workspaceId}",
        dependencies=[Depends(require_workspace_context)],
        tags=["guest-alpha-smoke-prototype"],
    )

    @router.post("/cases/{caseId}/simulation-runs", status_code=201)
    async def create_simulation_run(
        caseId: UUID,
        body: RunRequestBody,
        context: WorkspaceContext = Depends(require_workspace_context),
        db: AsyncSession = Depends(get_session),
    ) -> JSONResponse:
        service = SimulationRunService(db)
        try:
            view = await service.run_and_record(
                context,
                SimulationRunRequest(
                    decision_case_id=caseId,
                    graph_version_id=body.graphVersionId,
                    strategy_version_id=body.strategyVersionId,
                    scenario_version_id=body.scenarioVersionId,
                    score_definition_id=body.scoreDefinitionId,
                    simulation_mode=body.simulationMode,
                    decision_maker_profile_id=body.decisionMakerProfileId,
                    decision_maker_profile_version=body.decisionMakerProfileVersion,
                    epsilon=body.epsilon,
                    max_steps=body.maxSteps,
                    include_sensitivity=body.includeSensitivity,
                ),
            )
        except SimulationError as exc:
            return JSONResponse(
                status_code=422,
                content={
                    "ok": False,
                    "error": {
                        "code": getattr(exc, "code", "simulation_input_rejected"),
                        "message": str(exc),
                        "retryable": False,
                    },
                },
            )
        payload = payload_from(view)
        if view.convergence_status is not SimulationConvergenceStatus.CONVERGED:
            return JSONResponse(
                status_code=409,
                content={
                    "ok": False,
                    "error": {
                        "code": "SIMULATION_NOT_CONVERGED",
                        "message": "The simulation run persisted without convergence.",
                        "retryable": False,
                    },
                    "data": payload,
                },
            )
        return JSONResponse(status_code=201, content={"ok": True, "data": payload})

    @router.get("/cases/{caseId}/simulation-runs/{runId}")
    async def replay_simulation_run(
        caseId: UUID,
        runId: UUID,
        context: WorkspaceContext = Depends(require_workspace_context),
        db: AsyncSession = Depends(get_session),
    ) -> dict:
        row = await db.scalar(
            select(SimulationRunRow).where(
                SimulationRunRow.workspace_id == context.workspace_id,
                SimulationRunRow.decision_case_id == caseId,
                SimulationRunRow.id == runId,
            )
        )
        if row is None:
            raise simulation_scope_not_found()
        return {
            "ok": True,
            "data": {
                "id": str(row.id),
                "workspaceId": str(row.workspace_id),
                "decisionCaseId": str(row.decision_case_id),
                "graphId": str(row.graph_id),
                "graphVersionId": str(row.graph_version_id),
                "engineVersion": row.engine_version,
                "simulationMode": row.simulation_mode.value,
                "epsilon": row.epsilon,
                "maxSteps": row.max_steps,
                "steps": row.steps,
                "inputHash": row.input_hash,
                "nodeResults": dict(row.node_results),
                "convergenceStatus": row.convergence_status.value,
                "createdAt": row.created_at.isoformat(),
            },
        }

    app.include_router(router)
    return app


async def _csrf_headers(client) -> dict:
    response = await client.get("/api/auth/csrf")
    check(response.status_code == 200, f"csrf failed: {response.status_code}")
    return {"X-CSRF-Token": response.json()["data"]["csrfToken"], "Origin": BASE_URL}


async def _guest_flow(client) -> tuple[dict, dict]:
    """csrf -> guest -> run -> replay for one cookie client; returns (guest, run)."""

    headers = await _csrf_headers(client)
    guest_response = await client.post("/api/auth/guest", headers=headers)
    check(
        guest_response.status_code == 201,
        f"guest bootstrap returned {guest_response.status_code}: {guest_response.text[:300]}",
    )
    set_cookie = guest_response.headers.get("set-cookie", "")
    check("HttpOnly" in set_cookie, "guest session cookie must be HttpOnly")
    guest = guest_response.json()["data"]
    assert_guest_payload(guest)

    run_body = {
        "graphVersionId": guest["graphVersionId"],
        "strategyVersionId": guest["strategyVersionId"],
        "scenarioVersionId": guest["scenarioVersionId"],
        "scoreDefinitionId": guest["scoreDefinitionId"],
        "simulationMode": "formal",
        "decisionMakerProfileId": guest["decisionMakerProfileId"],
        "decisionMakerProfileVersion": guest["decisionMakerProfileVersion"],
    }
    run_url = (
        f"/api/workspaces/{guest['workspaceId']}"
        f"/cases/{guest['decisionCaseId']}/simulation-runs"
    )
    run_response = await client.post(run_url, json=run_body, headers=headers)
    check(
        run_response.status_code in (201, 409),
        f"run returned {run_response.status_code}: {run_response.text[:300]}",
    )
    envelope = run_response.json()
    if run_response.status_code == 409:
        check(
            envelope["error"]["code"] == "SIMULATION_NOT_CONVERGED",
            "409 must carry SIMULATION_NOT_CONVERGED",
        )
    run = envelope["data"]
    check(bool(run.get("id")), "run id missing")
    check(
        run["engineVersion"] == ENGINE_VERSION_EXPECTED,
        f"engineVersion {run['engineVersion']!r} != {ENGINE_VERSION_EXPECTED!r}",
    )
    check(
        INPUT_HASH_RE.fullmatch(run.get("inputHash", "")) is not None,
        "inputHash missing or malformed",
    )

    replay_response = await client.get(f"{run_url}/{run['id']}", headers=headers)
    check(replay_response.status_code == 200, f"replay failed: {replay_response.status_code}")
    check(
        replay_response.json()["data"] == run,
        "replay payload differs from the creation payload",
    )
    return guest, run


async def run_smoke() -> dict:
    import httpx

    app = build_prototype_app()

    def new_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url=BASE_URL,
            headers={"Origin": BASE_URL},
        )

    # Gate check: without the flag the route answers the uniform 404.
    os.environ.pop(GUEST_FLAG, None)
    async with new_client() as gate_client:
        headers = await _csrf_headers(gate_client)
        gated = await gate_client.post("/api/auth/guest", headers=headers)
        check(gated.status_code == 404, f"disabled flag must 404, got {gated.status_code}")

    os.environ[GUEST_FLAG] = "true"
    try:
        async with new_client() as client_a, new_client() as client_b:
            guest_a, run_a = await _guest_flow(client_a)
            guest_b, run_b = await _guest_flow(client_b)

            # Isolation: disjoint identities and demo scopes.
            assert_disjoint(guest_a, guest_b)

            # A using B's graph (and profile) inside A's own scope: 404.
            headers_a = await _csrf_headers(client_a)
            stolen = {
                "graphVersionId": guest_b["graphVersionId"],
                "strategyVersionId": guest_a["strategyVersionId"],
                "scenarioVersionId": guest_a["scenarioVersionId"],
                "scoreDefinitionId": guest_a["scoreDefinitionId"],
                "simulationMode": "formal",
                "decisionMakerProfileId": guest_b["decisionMakerProfileId"],
                "decisionMakerProfileVersion": guest_b["decisionMakerProfileVersion"],
            }
            cross_input = await client_a.post(
                f"/api/workspaces/{guest_a['workspaceId']}"
                f"/cases/{guest_a['decisionCaseId']}/simulation-runs",
                json=stolen,
                headers=headers_a,
            )
            check(
                cross_input.status_code == 404,
                f"A using B's graph/profile must 404, got {cross_input.status_code}",
            )

            # A entering B's workspace path: uniform 404 from tenancy.
            cross_workspace = await client_a.post(
                f"/api/workspaces/{guest_b['workspaceId']}"
                f"/cases/{guest_b['decisionCaseId']}/simulation-runs",
                json=stolen,
                headers=headers_a,
            )
            check(
                cross_workspace.status_code == 404,
                f"A in B's workspace must 404, got {cross_workspace.status_code}",
            )

            # A replaying B's run inside A's scope: 404.
            cross_replay = await client_a.get(
                f"/api/workspaces/{guest_a['workspaceId']}"
                f"/cases/{guest_a['decisionCaseId']}/simulation-runs/{run_b['id']}",
                headers=headers_a,
            )
            check(
                cross_replay.status_code == 404,
                f"A replaying B's run must 404, got {cross_replay.status_code}",
            )
    finally:
        os.environ.pop(GUEST_FLAG, None)

    return {
        "gateWhenDisabled": 404,
        "guestA": {"workspaceId": guest_a["workspaceId"], "runId": run_a["id"]},
        "guestB": {"workspaceId": guest_b["workspaceId"], "runId": run_b["id"]},
        "engineVersion": run_a["engineVersion"],
        "inputHashA": run_a["inputHash"],
        "inputHashB": run_b["inputHash"],
        "isolation": {
            "disjointIds": True,
            "crossInput404": True,
            "crossWorkspace404": True,
            "crossReplay404": True,
        },
    }


def main(argv: list | None = None) -> int:
    argparse.ArgumentParser(
        description="Smoke the guest alpha bootstrap + isolation contract."
    ).parse_args(argv)
    try:
        summary = asyncio.run(run_smoke())
    except SmokeFailure as failure:
        print(f"SMOKE FAIL: {failure}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
    print("SMOKE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
