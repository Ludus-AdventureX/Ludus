"""Task 9 owner follow-up (MOUNT-01 M3/M4/M5 + M9): HTTP handler tests.

The Charter lifecycle / Run creation / run status / strategic-lens read
handlers plus the M9 cancel Idempotency-Key enforcement live on the RELATIVE,
UNMOUNTED analyses router. A QA-only assembly mirrors the future integration
mounting (Task 3/8/9 precedent): tenancy + DB session are overridden, so these
tests exercise the handlers without touching ``app.main`` or the contracts.

Coverage: every endpoint positive + negative, idempotency (run create, cancel
header), and the cross-tenant / missing-id 404 matrix (uniform CASE_NOT_FOUND).
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
import pytest_asyncio
from fastapi import FastAPI, Path

from app.analyses.repository import AnalysisRuntimeRepository
from app.analyses.routes import router as analyses_router
from app.auth.config import get_auth_settings
from app.db import get_session
from app.models import StrategicLensArtifact
from app.security.envelope import register_error_handlers, workspace_not_found
from app.tenancy.context import (
    ALL_CAPABILITIES,
    WorkspaceContext,
    require_workspace_context,
)
from app.types import (
    LensProducerRole,
    OriginMode,
    StrategicLensArtifactStatus,
    StrategicLensType,
    WorkspaceRole,
)

from runtime_world import (
    FULL_SET,
    RuntimeWorld,
    charter_values,
    make_confirmed_charter,
    make_queued_run,
)


def _build_app(session, memberships: dict[UUID, UUID]) -> FastAPI:
    app = FastAPI(title="Ludus QA Task 9 analyses-http assembly")
    app.include_router(analyses_router)
    register_error_handlers(app)

    async def fake_context(
        workspace_id: UUID = Path(alias="workspaceId"),
    ) -> WorkspaceContext:
        user_id = memberships.get(workspace_id)
        if user_id is None:
            raise workspace_not_found()
        return WorkspaceContext(
            user_id=user_id,
            workspace_id=workspace_id,
            role=WorkspaceRole.OWNER,
            capabilities=ALL_CAPABILITIES,
        )

    async def override_session():
        yield session

    app.dependency_overrides[require_workspace_context] = fake_context
    app.dependency_overrides[get_session] = override_session
    return app


@pytest_asyncio.fixture
async def client(session, world, foreign_world):
    app = _build_app(
        session,
        {
            world.workspace_id: world.user_id,
            foreign_world.workspace_id: foreign_world.user_id,
        },
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://analyses.test",
        # MOUNT-02 M8: unsafe writes now carry require_csrf (SIM-02A parity);
        # same-origin + double-submit proof mirrors the production browser.
        headers={
            "Origin": "http://analyses.test",
            get_auth_settings().csrf_header_name: "qa-analyses-csrf",
        },
        cookies={get_auth_settings().csrf_cookie_name: "qa-analyses-csrf"},
    ) as http_client:
        yield http_client


def _ws(world: RuntimeWorld) -> str:
    return f"/api/workspaces/{world.workspace_id}"


def _charter_body(world: RuntimeWorld, *, level: str = "full", lenses=None) -> dict:
    return {
        "decisionSubjectId": str(world.subject_id),
        "caseVersion": 1,
        "caseSnapshotHash": "sha256:case",
        "analysisLevel": level,
        "decisionQuestion": "enter the rescue market?",
        "dossierSnapshotVersion": 1,
        "dossierSnapshotHash": "sha256:dossier",
        "goals": [{"id": "g1", "text": "validate demand"}],
        "constraints": [{"id": "c1", "text": "9-month cash window"}],
        "optionIds": ["opt_rescue", "opt_home"],
        "preferenceWeights": {"risk": 0.4, "speed": 0.6},
        "requiredStrategicLensTypes": (
            (list(FULL_SET) if level == "full" else []) if lenses is None else lenses
        ),
        "methodId": "hardtech-market-direction",
        "methodVersion": "1.1.0",
        "methodContentHash": "sha256:method",
        "formalAnalysisAllowed": True,
        "allowedConnectorIds": ["exa", "tavily"],
        "budget": {"max_model_calls": 20},
    }


def _run_body() -> dict:
    return {"cynefinGateResultId": str(uuid4()), "runManifestHash": "sha256:manifest"}


def _seed_ready_lens(
    world: RuntimeWorld,
    run,
    *,
    lens_type: StrategicLensType = StrategicLensType.PORTER_FIVE_FORCES,
    status: StrategicLensArtifactStatus = StrategicLensArtifactStatus.READY,
) -> StrategicLensArtifact:
    accepted = (
        datetime.now(timezone.utc)
        if status == StrategicLensArtifactStatus.READY
        else None
    )
    return StrategicLensArtifact(
        strategic_lens_artifact_id=uuid4(),
        workspace_id=world.workspace_id,
        decision_case_id=world.case_id,
        analysis_run_id=run.analysis_run_id,
        charter_id=run.charter_id,
        lens_type=lens_type,
        producer_role=LensProducerRole.RESEARCH,
        status=status,
        method_id="hardtech-market-direction",
        method_version="1.1.0",
        method_content_hash="sha256:method",
        prompt_version="1.0.0",
        schema_version="1.0.0",
        origin_modes=[OriginMode.FIXTURE],
        content_hash="sha256:lens_content",
        payload={"summary": "five forces"},
        claim_refs=["claim_1"],
        evidence_refs=["ev_1", "ev_2"],
        assumption_refs=[],
        validation_accepted_at=accepted,
    )


# --- Charter create ----------------------------------------------------------


async def test_create_charter_draft_full(client, world):
    response = await client.post(
        f"{_ws(world)}/cases/{world.case_id}/analysis-charters",
        json=_charter_body(world),
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["status"] == "draft"
    assert data["analysisLevel"] == "full"
    assert data["requiredStrategicLensTypes"] == list(FULL_SET)
    assert data["decisionCaseId"] == str(world.case_id)


async def test_create_charter_missing_fields(client, world):
    # Revised with the server-authoritative snapshot change: caseSnapshotHash is
    # no longer a caller-required field (the server freezes it from the database),
    # so omitting it is legal and only the genuinely caller-owned field is
    # reported missing. Omitting decisionSubjectId is added here to keep the
    # multi-field shape of the assertion covered.
    body = _charter_body(world)
    del body["decisionQuestion"]
    del body["caseSnapshotHash"]
    del body["decisionSubjectId"]
    response = await client.post(
        f"{_ws(world)}/cases/{world.case_id}/analysis-charters", json=body
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_FAILED"
    assert set(error["details"]["missingFields"]) == {
        "decisionSubjectId",
        "decisionQuestion",
    }


async def test_create_charter_full_wrong_lens_set(client, world):
    response = await client.post(
        f"{_ws(world)}/cases/{world.case_id}/analysis-charters",
        json=_charter_body(world, lenses=["porter_five_forces"]),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


async def test_create_charter_unknown_workspace_404(client):
    ghost_ws = uuid4()
    response = await client.post(
        f"/api/workspaces/{ghost_ws}/cases/{uuid4()}/analysis-charters",
        json={"decisionSubjectId": str(uuid4())},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"


# --- Charter PATCH -----------------------------------------------------------


async def test_patch_draft_charter(client, session, world):
    repo = AnalysisRuntimeRepository(session)
    charter = await repo.create_charter_draft(**charter_values(world))
    original_version = charter.version
    response = await client.patch(
        f"{_ws(world)}/analysis-charters/{charter.id}",
        json={"decisionQuestion": "enter home services first?"},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["decisionQuestion"] == "enter home services first?"
    assert data["version"] == original_version + 1


async def test_patch_confirmed_charter_rejected(client, session, world):
    charter = await make_confirmed_charter(session, world)
    response = await client.patch(
        f"{_ws(world)}/analysis-charters/{charter.id}",
        json={"decisionQuestion": "changed"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CHARTER_IMMUTABLE"


async def test_patch_missing_charter_404(client, world):
    response = await client.patch(
        f"{_ws(world)}/analysis-charters/{uuid4()}", json={"decisionQuestion": "x"}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CASE_NOT_FOUND"


# --- Charter confirm ---------------------------------------------------------


async def test_confirm_draft_charter(client, session, world):
    repo = AnalysisRuntimeRepository(session)
    charter = await repo.create_charter_draft(**charter_values(world))
    response = await client.post(f"{_ws(world)}/analysis-charters/{charter.id}/confirm")
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "confirmed"
    assert data["confirmedAt"] is not None


async def test_confirm_already_confirmed_rejected(client, session, world):
    charter = await make_confirmed_charter(session, world)
    response = await client.post(f"{_ws(world)}/analysis-charters/{charter.id}/confirm")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CHARTER_IMMUTABLE"


async def test_confirm_missing_charter_404(client, world):
    response = await client.post(f"{_ws(world)}/analysis-charters/{uuid4()}/confirm")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CASE_NOT_FOUND"


# --- Charter replacements ----------------------------------------------------


async def test_replacement_of_confirmed(client, session, world):
    charter = await make_confirmed_charter(session, world)
    response = await client.post(
        f"{_ws(world)}/analysis-charters/{charter.id}/replacements",
        json={"decisionQuestion": "revised question"},
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["status"] == "draft"
    assert data["replacesCharterId"] == str(charter.id)
    assert data["decisionQuestion"] == "revised question"


async def test_replacement_of_draft_rejected(client, session, world):
    repo = AnalysisRuntimeRepository(session)
    charter = await repo.create_charter_draft(**charter_values(world))
    response = await client.post(
        f"{_ws(world)}/analysis-charters/{charter.id}/replacements", json={}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CHARTER_NOT_CONFIRMED"


async def test_replacement_missing_charter_404(client, world):
    response = await client.post(
        f"{_ws(world)}/analysis-charters/{uuid4()}/replacements", json={}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CASE_NOT_FOUND"


# --- Run create --------------------------------------------------------------


async def test_create_run(client, session, world):
    charter = await make_confirmed_charter(session, world)
    response = await client.post(
        f"{_ws(world)}/analysis-charters/{charter.id}/runs",
        json=_run_body(),
        headers={"Idempotency-Key": "run-key-001"},
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["status"] == "queued"
    assert data["charterId"] == str(charter.id)
    assert data["eventsUrl"].endswith(f"/analyses/{data['analysisRunId']}/events")


async def test_create_run_requires_idempotency_key(client, session, world):
    charter = await make_confirmed_charter(session, world)
    response = await client.post(
        f"{_ws(world)}/analysis-charters/{charter.id}/runs", json=_run_body()
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"]["header"] == "Idempotency-Key"


async def test_create_run_body_smuggled_key_rejected(client, session, world):
    charter = await make_confirmed_charter(session, world)
    body = {**_run_body(), "idempotencyKey": "smuggled"}
    response = await client.post(
        f"{_ws(world)}/analysis-charters/{charter.id}/runs",
        json=body,
        headers={"Idempotency-Key": "run-key-002"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


async def test_create_run_idempotent_replay(client, session, world):
    charter = await make_confirmed_charter(session, world)
    body = _run_body()
    headers = {"Idempotency-Key": "run-key-replay"}
    first = await client.post(
        f"{_ws(world)}/analysis-charters/{charter.id}/runs", json=body, headers=headers
    )
    second = await client.post(
        f"{_ws(world)}/analysis-charters/{charter.id}/runs", json=body, headers=headers
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["meta"]["idempotencyReplay"] is True
    assert first.json()["data"]["analysisRunId"] == second.json()["data"]["analysisRunId"]


async def test_create_run_same_key_different_body_conflicts(client, session, world):
    charter = await make_confirmed_charter(session, world)
    headers = {"Idempotency-Key": "run-key-conflict"}
    await client.post(
        f"{_ws(world)}/analysis-charters/{charter.id}/runs",
        json=_run_body(),
        headers=headers,
    )
    conflict = await client.post(
        f"{_ws(world)}/analysis-charters/{charter.id}/runs",
        json=_run_body(),
        headers=headers,
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


async def test_create_run_unconfirmed_charter_rejected(client, session, world):
    repo = AnalysisRuntimeRepository(session)
    charter = await repo.create_charter_draft(**charter_values(world))
    response = await client.post(
        f"{_ws(world)}/analysis-charters/{charter.id}/runs",
        json=_run_body(),
        headers={"Idempotency-Key": "run-key-draft"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CHARTER_NOT_CONFIRMED"


async def test_create_run_second_active_conflicts(client, session, world):
    charter = await make_confirmed_charter(session, world)
    await client.post(
        f"{_ws(world)}/analysis-charters/{charter.id}/runs",
        json=_run_body(),
        headers={"Idempotency-Key": "run-key-a"},
    )
    second = await client.post(
        f"{_ws(world)}/analysis-charters/{charter.id}/runs",
        json=_run_body(),
        headers={"Idempotency-Key": "run-key-b"},
    )
    assert second.status_code == 409
    body = second.json()["error"]
    assert body["code"] == "ANALYSIS_RUN_ALREADY_ACTIVE"
    assert "existingAnalysisRunId" in body["details"]


async def test_create_run_missing_charter_404(client, world):
    response = await client.post(
        f"{_ws(world)}/analysis-charters/{uuid4()}/runs",
        json=_run_body(),
        headers={"Idempotency-Key": "run-key-ghost"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CASE_NOT_FOUND"


# --- Run status GET ----------------------------------------------------------


async def test_get_run_status(client, session, world):
    _charter, run = await make_queued_run(session, world)
    response = await client.get(f"{_ws(world)}/analyses/{run.analysis_run_id}")
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["analysisRunId"] == str(run.analysis_run_id)
    assert data["status"] == "queued"
    assert data["decisionCaseId"] == str(world.case_id)


async def test_get_run_missing_404(client, world):
    response = await client.get(f"{_ws(world)}/analyses/{uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CASE_NOT_FOUND"


async def test_get_run_cross_tenant_404(client, session, world, foreign_world):
    _charter, run = await make_queued_run(session, foreign_world)
    # Foreign run id queried through the caller's own workspace: uniform 404.
    response = await client.get(f"{_ws(world)}/analyses/{run.analysis_run_id}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CASE_NOT_FOUND"


# --- Strategic-lenses read ---------------------------------------------------


async def test_list_strategic_lenses_ready(client, session, world):
    _charter, run = await make_queued_run(session, world)
    session.add(_seed_ready_lens(world, run))
    await session.flush()
    response = await client.get(
        f"{_ws(world)}/analyses/{run.analysis_run_id}/strategic-lenses"
    )
    assert response.status_code == 200, response.text
    items = response.json()["data"]
    assert len(items) == 1
    assert items[0]["lensType"] == "porter_five_forces"
    assert items[0]["status"] == "ready"
    assert items[0]["referenceCounts"]["evidenceCount"] == 2


async def test_list_strategic_lenses_empty(client, session, world):
    _charter, run = await make_queued_run(session, world)
    response = await client.get(
        f"{_ws(world)}/analyses/{run.analysis_run_id}/strategic-lenses"
    )
    assert response.status_code == 200
    assert response.json()["data"] == []


async def test_list_strategic_lenses_missing_run_404(client, world):
    response = await client.get(f"{_ws(world)}/analyses/{uuid4()}/strategic-lenses")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CASE_NOT_FOUND"


async def test_get_strategic_lens_item(client, session, world):
    _charter, run = await make_queued_run(session, world)
    artifact = _seed_ready_lens(world, run)
    session.add(artifact)
    await session.flush()
    response = await client.get(
        f"{_ws(world)}/analyses/{run.analysis_run_id}"
        f"/strategic-lenses/{artifact.strategic_lens_artifact_id}"
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["id"] == str(artifact.strategic_lens_artifact_id)
    assert data["content"] == {"summary": "five forces"}
    assert data["evidenceRefs"] == ["ev_1", "ev_2"]


async def test_get_strategic_lens_draft_not_consumable_404(client, session, world):
    _charter, run = await make_queued_run(session, world)
    artifact = _seed_ready_lens(world, run, status=StrategicLensArtifactStatus.DRAFT)
    session.add(artifact)
    await session.flush()
    response = await client.get(
        f"{_ws(world)}/analyses/{run.analysis_run_id}"
        f"/strategic-lenses/{artifact.strategic_lens_artifact_id}"
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CASE_NOT_FOUND"


async def test_get_strategic_lens_missing_404(client, session, world):
    _charter, run = await make_queued_run(session, world)
    response = await client.get(
        f"{_ws(world)}/analyses/{run.analysis_run_id}/strategic-lenses/{uuid4()}"
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CASE_NOT_FOUND"


# --- M9: cancel now requires the Idempotency-Key header ----------------------


async def test_cancel_requires_idempotency_key(client, session, world):
    _charter, run = await make_queued_run(session, world)
    response = await client.post(f"{_ws(world)}/analyses/{run.analysis_run_id}/cancel")
    assert response.status_code == 422
    assert response.json()["error"]["details"]["header"] == "Idempotency-Key"


async def test_cancel_with_key_succeeds_and_is_idempotent(client, session, world):
    _charter, run = await make_queued_run(session, world)
    headers = {"Idempotency-Key": "cancel-key-1"}
    first = await client.post(
        f"{_ws(world)}/analyses/{run.analysis_run_id}/cancel", headers=headers
    )
    second = await client.post(
        f"{_ws(world)}/analyses/{run.analysis_run_id}/cancel",
        headers={"Idempotency-Key": "cancel-key-2"},
    )
    assert first.status_code == 200, first.text
    assert first.json()["data"]["status"] == "cancelled"
    # Naturally idempotent: a second cancel returns the same terminal state.
    assert second.status_code == 200
    assert second.json()["data"]["status"] == "cancelled"
