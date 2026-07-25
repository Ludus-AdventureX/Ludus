"""End-to-end smoke for the simulation-alpha demo scope (SIM_ALPHA_SEED_SMOKE_FAST).

Because this baseline ships the simulation service without HTTP routes, the
smoke attaches two PROTOTYPE routes to the real app AT RUNTIME ONLY (no product
file is modified) and drives them through the real ASGI stack (httpx
ASGITransport), exercising the production auth/CSRF/tenancy dependencies:

- ``GET  /api/auth/csrf``  then ``POST /api/auth/login`` (demo credentials);
- ``POST /api/workspaces/{workspaceId}/cases/{caseId}/simulation-runs``
  → 201 on convergence, or the agreed non-convergence 409 envelope
  (``error.code = SIMULATION_NOT_CONVERGED`` with the persisted run in ``data``);
- ``GET  .../simulation-runs/{runId}`` replay.

Assertions: status 201/409, run id present, ``engineVersion == sim-engine-1.1.0``,
``inputHash`` present (sha256 format), and the replay payload is byte-identical
to the creation payload. The demo password comes ONLY from
``SIMULATION_ALPHA_DEMO_PASSWORD``.
"""

# NOTE: no ``from __future__ import annotations`` here — the prototype routes are
# defined inside a function, and FastAPI must introspect their annotations as
# real objects (stringified annotations cannot resolve function-local models).

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

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


def _run_payload(view: Any) -> dict[str, Any]:
    """Persisted-field projection shared by create and replay responses."""

    return {
        "id": str(view.id),
        "workspaceId": str(view.workspace_id),
        "decisionCaseId": str(view.decision_case_id),
        "graphId": str(view.graph_id),
        "graphVersionId": str(view.graph_version_id),
        "strategyVersionId": str(view.strategy_version_id),
        "scenarioVersionId": str(view.scenario_version_id),
        "scoreDefinitionId": str(view.score_definition_id),
        "scoreDefinitionVersion": view.score_definition_version,
        "decisionMakerProfileId": str(view.decision_maker_profile_id),
        "decisionMakerProfileVersion": view.decision_maker_profile_version,
        "riskTolerance": view.risk_tolerance,
        "engineVersion": view.engine_version,
        "scenarioId": str(view.scenario_id),
        "simulationMode": view.simulation_mode.value,
        "epsilon": view.epsilon,
        "maxSteps": view.max_steps,
        "steps": view.steps,
        "inputHash": view.input_hash,
        "nodeResults": dict(view.node_results),
        "optionScores": [
            {"optionId": entry.option_id, "score": entry.score} for entry in view.option_scores
        ],
        "topDrivers": [
            {"nodeId": entry.node_id, "scoreDelta": entry.score_delta}
            for entry in view.top_drivers
        ],
        "recommendationShift": view.recommendation_shift,
        "convergenceStatus": view.convergence_status.value,
        "originModes": [mode.value for mode in view.origin_modes],
        "createdAt": view.created_at.isoformat(),
    }


def build_prototype_app() -> Any:
    """Mount the prototype run/replay routes onto the real app (runtime only)."""

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

    def _row_payload(row: SimulationRunRow) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "workspaceId": str(row.workspace_id),
            "decisionCaseId": str(row.decision_case_id),
            "graphId": str(row.graph_id),
            "graphVersionId": str(row.graph_version_id),
            "strategyVersionId": str(row.strategy_version_id),
            "scenarioVersionId": str(row.scenario_version_id),
            "scoreDefinitionId": str(row.score_definition_id),
            "scoreDefinitionVersion": row.score_definition_version,
            "decisionMakerProfileId": str(row.decision_maker_profile_id),
            "decisionMakerProfileVersion": row.decision_maker_profile_version,
            "riskTolerance": row.risk_tolerance,
            "engineVersion": row.engine_version,
            "scenarioId": str(row.scenario_id),
            "simulationMode": row.simulation_mode.value,
            "epsilon": row.epsilon,
            "maxSteps": row.max_steps,
            "steps": row.steps,
            "inputHash": row.input_hash,
            "nodeResults": dict(row.node_results),
            "optionScores": list(row.option_scores),
            "topDrivers": list(row.top_drivers),
            "recommendationShift": row.recommendation_shift,
            "convergenceStatus": row.convergence_status.value,
            "originModes": [mode.value for mode in row.origin_modes],
            "createdAt": row.created_at.isoformat(),
        }

    router = APIRouter(
        prefix="/api/workspaces/{workspaceId}",
        dependencies=[Depends(require_workspace_context)],
        tags=["simulation-alpha-prototype"],
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
        payload = _run_payload(view)
        if view.convergence_status is not SimulationConvergenceStatus.CONVERGED:
            # Agreed prototype contract: persisted-but-non-converged runs answer 409.
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
    ) -> dict[str, Any]:
        row = await db.scalar(
            select(SimulationRunRow).where(
                SimulationRunRow.workspace_id == context.workspace_id,
                SimulationRunRow.decision_case_id == caseId,
                SimulationRunRow.id == runId,
            )
        )
        if row is None:
            raise simulation_scope_not_found()
        return {"ok": True, "data": _row_payload(row)}

    app.include_router(router)
    return app


async def run_smoke(fixture: dict[str, Any], password: str) -> dict[str, Any]:
    import httpx

    app = build_prototype_app()
    ids = derive_ids(fixture)
    workspace_id = str(ids["workspace_id"])
    case_id = str(ids["case_id"])
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

        # 3. Create the simulation run.
        run_body = {
            "graphVersionId": str(ids["graph_version_id"]),
            "strategyVersionId": str(ids["strategy_version_id"]),
            "scenarioVersionId": str(ids["scenario_version_id"]),
            "scoreDefinitionId": str(ids["score_definition_id"]),
            "simulationMode": fixture["run"]["simulationMode"],
            "decisionMakerProfileId": str(ids["profile_id"]),
            "decisionMakerProfileVersion": fixture["profile"]["version"],
            "epsilon": fixture["run"]["epsilon"],
            "maxSteps": fixture["run"]["maxSteps"],
            "includeSensitivity": fixture["run"]["includeSensitivity"],
        }
        create_response = await client.post(
            f"/api/workspaces/{workspace_id}/cases/{case_id}/simulation-runs",
            json=run_body,
            headers=mutation_headers,
        )
        check(
            create_response.status_code in (201, 409),
            f"run creation returned {create_response.status_code}: {create_response.text[:400]}",
        )
        create_envelope = create_response.json()
        if create_response.status_code == 409:
            check(
                create_envelope["error"]["code"] == "SIMULATION_NOT_CONVERGED",
                "409 must carry the agreed SIMULATION_NOT_CONVERGED code",
            )
        created = create_envelope["data"]

        # 4. Contract assertions on the created run.
        run_id = created.get("id", "")
        check(bool(run_id) and UUID(run_id) is not None, "run id missing from creation payload")
        check(
            created["engineVersion"] == ENGINE_VERSION_EXPECTED,
            f"engineVersion {created['engineVersion']!r} != {ENGINE_VERSION_EXPECTED!r}",
        )
        check(
            INPUT_HASH_RE.fullmatch(created.get("inputHash", "")) is not None,
            "inputHash missing or malformed on the creation payload",
        )

        # 5. Replay must be identical to the creation payload.
        replay_response = await client.get(
            f"/api/workspaces/{workspace_id}/cases/{case_id}/simulation-runs/{run_id}",
            headers=origin_headers,
        )
        check(replay_response.status_code == 200, f"replay failed: {replay_response.status_code}")
        replayed = replay_response.json()["data"]
        check(replayed == created, "replay payload differs from the creation payload")

    return {
        "createStatus": create_response.status_code,
        "runId": run_id,
        "engineVersion": created["engineVersion"],
        "inputHash": created["inputHash"],
        "convergenceStatus": created["convergenceStatus"],
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
