"""QA adversarial supplement for the Task 9 analyses HTTP handlers (r1b).

Independent QA lane for candidate 0f92b17 (codex/task-09-analyses-http-handlers-r1).
Attack angles beyond the owner suite, per the QA lightweight-gate spec:

- idempotency-key reuse across charters (same workspace) and across tenants;
- replay-after-cancel: terminal state must replay, never resurrect or duplicate;
- body-smuggled Idempotency-Key on cancel (owner covered runs only);
- byte-identical 404 anti-enumeration across ALL new GET endpoints
  (foreign-tenant id vs ghost id must be indistinguishable);
- PATCH privilege probe: non-editable fields (status) must not be applied;
- hostile payloads must degrade into the {ok:false,error} envelope;
- confirm bridge entered from awaiting_confirmation (not only draft).

QA-only assembly mirrors the owner suite exactly (tenancy + session overrides);
no product code is touched.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import httpx
import pytest_asyncio
from fastapi import FastAPI, Path

from app.analyses.repository import AnalysisRuntimeRepository
from app.analyses.routes import router as analyses_router
from app.db import get_session
from app.security.envelope import register_error_handlers, workspace_not_found
from app.tenancy.context import (
    ALL_CAPABILITIES,
    WorkspaceContext,
    require_workspace_context,
)
from app.types import WorkspaceRole

from runtime_world import (
    RuntimeWorld,
    charter_values,
    make_confirmed_charter,
    make_queued_run,
)


def _build_app(session, memberships: dict[UUID, UUID]) -> FastAPI:
    app = FastAPI(title="Ludus QA adversarial r1b assembly")
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
        transport=httpx.ASGITransport(app=app), base_url="http://qa-adversarial.test"
    ) as http_client:
        yield http_client


def _ws(world: RuntimeWorld) -> str:
    return f"/api/workspaces/{world.workspace_id}"


def _run_body() -> dict:
    return {"cynefinGateResultId": str(uuid4()), "runManifestHash": "sha256:manifest"}


# --- A1: key reuse on a DIFFERENT charter in the same workspace --------------


async def test_run_key_reuse_across_charters_conflicts(client, session, world):
    """The replay lookup is workspace-scoped; a reused key pointed at another
    charter is a same-key-different-body replay and must be 409, never a
    silent replay of the foreign charter's run."""

    charter_a = await make_confirmed_charter(session, world)
    body = _run_body()
    first = await client.post(
        f"{_ws(world)}/analysis-charters/{charter_a.id}/runs",
        json=body,
        headers={"Idempotency-Key": "qa-cross-charter"},
    )
    assert first.status_code == 201, first.text

    repo = AnalysisRuntimeRepository(session)
    charter_b = await repo.create_charter_draft(**charter_values(world))
    confirm = await client.post(
        f"{_ws(world)}/analysis-charters/{charter_b.id}/confirm"
    )
    assert confirm.status_code == 200, confirm.text

    hijack = await client.post(
        f"{_ws(world)}/analysis-charters/{charter_b.id}/runs",
        json=body,
        headers={"Idempotency-Key": "qa-cross-charter"},
    )
    assert hijack.status_code == 409
    assert hijack.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


# --- A2: the same key must NOT leak across tenants ----------------------------


async def test_run_key_not_replayed_across_tenants(
    client, session, world, foreign_world
):
    charter_own = await make_confirmed_charter(session, world)
    own = await client.post(
        f"{_ws(world)}/analysis-charters/{charter_own.id}/runs",
        json=_run_body(),
        headers={"Idempotency-Key": "qa-tenant-shared-key"},
    )
    assert own.status_code == 201, own.text

    charter_foreign = await make_confirmed_charter(session, foreign_world)
    foreign = await client.post(
        f"{_ws(foreign_world)}/analysis-charters/{charter_foreign.id}/runs",
        json=_run_body(),
        headers={"Idempotency-Key": "qa-tenant-shared-key"},
    )
    # A fresh run in the foreign tenant: no cross-tenant replay, no conflict,
    # and definitely not the other tenant's run id.
    assert foreign.status_code == 201, foreign.text
    assert "meta" not in foreign.json() or not foreign.json().get("meta", {}).get(
        "idempotencyReplay"
    )
    assert (
        foreign.json()["data"]["analysisRunId"] != own.json()["data"]["analysisRunId"]
    )


# --- A3: replay after cancel returns the terminal state, no resurrection ------


async def test_replay_after_cancel_no_resurrection(client, session, world):
    charter = await make_confirmed_charter(session, world)
    body = _run_body()
    headers = {"Idempotency-Key": "qa-replay-after-cancel"}
    created = await client.post(
        f"{_ws(world)}/analysis-charters/{charter.id}/runs", json=body, headers=headers
    )
    assert created.status_code == 201, created.text
    run_id = created.json()["data"]["analysisRunId"]

    cancelled = await client.post(
        f"{_ws(world)}/analyses/{run_id}/cancel",
        json={"reason": "user_cancelled"},
        headers={"Idempotency-Key": "qa-cancel-1"},
    )
    assert cancelled.status_code == 200, cancelled.text

    replay = await client.post(
        f"{_ws(world)}/analysis-charters/{charter.id}/runs", json=body, headers=headers
    )
    assert replay.status_code == 201
    assert replay.json()["meta"]["idempotencyReplay"] is True
    assert replay.json()["data"]["analysisRunId"] == run_id
    assert replay.json()["data"]["status"] == "cancelled"

    # And a NEW key now creates a fresh queued run (cancelled is not active).
    fresh = await client.post(
        f"{_ws(world)}/analysis-charters/{charter.id}/runs",
        json=_run_body(),
        headers={"Idempotency-Key": "qa-fresh-after-cancel"},
    )
    assert fresh.status_code == 201, fresh.text
    assert fresh.json()["data"]["analysisRunId"] != run_id
    assert fresh.json()["data"]["status"] == "queued"


# --- A4: body-smuggled Idempotency-Key on cancel (owner covered runs only) ----


async def test_cancel_body_smuggled_key_rejected(client, session, world):
    _charter, run = await make_queued_run(session, world)
    response = await client.post(
        f"{_ws(world)}/analyses/{run.analysis_run_id}/cancel",
        json={"reason": "user_cancelled", "idempotencyKey": "smuggled"},
        headers={"Idempotency-Key": "qa-smuggle-cancel"},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_FAILED"
    assert error["details"]["header"] == "Idempotency-Key"


# --- A5: byte-identical 404s across ALL new GET endpoints ---------------------


async def test_new_get_endpoints_uniform_404_bytes(
    client, session, world, foreign_world
):
    """Foreign-tenant probes and ghost-id probes must be indistinguishable at
    the byte level on every new read endpoint (anti-enumeration)."""

    _charter, foreign_run = await make_queued_run(session, foreign_world)
    foreign_id = foreign_run.analysis_run_id
    ghost_id = uuid4()

    paths = (
        "/analyses/{rid}",
        "/analyses/{rid}/strategic-lenses",
        f"/analyses/{{rid}}/strategic-lenses/{uuid4()}",
    )
    for template in paths:
        foreign_probe = await client.get(
            f"{_ws(world)}{template.format(rid=foreign_id)}"
        )
        ghost_probe = await client.get(f"{_ws(world)}{template.format(rid=ghost_id)}")
        assert foreign_probe.status_code == ghost_probe.status_code == 404, template
        assert foreign_probe.content == ghost_probe.content, template
        assert foreign_probe.json()["error"]["code"] == "CASE_NOT_FOUND"


# --- A6: PATCH must not apply non-editable fields (status flip probe) ---------


async def test_patch_cannot_flip_status_or_smuggle_unknown_fields(
    client, session, world
):
    repo = AnalysisRuntimeRepository(session)
    charter = await repo.create_charter_draft(**charter_values(world))
    response = await client.patch(
        f"{_ws(world)}/analysis-charters/{charter.id}",
        json={"status": "confirmed", "confirmedAt": "2026-07-26T00:00:00Z"},
    )
    # Neither field is editable: the request carries no effective edit.
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"

    fetch_fresh = await client.post(
        f"{_ws(world)}/analysis-charters/{charter.id}/confirm"
    )
    # The charter was still a pristine draft: the confirm bridge succeeds,
    # proving the hostile PATCH neither flipped status nor corrupted state.
    assert fetch_fresh.status_code == 200, fetch_fresh.text
    assert fetch_fresh.json()["data"]["status"] == "confirmed"


# --- A7: hostile payloads degrade into the canonical failure envelope ---------


async def test_hostile_payloads_degrade_to_envelope(client, session, world):
    # Non-object JSON body: FastAPI validation must come back enveloped.
    array_body = await client.post(
        f"{_ws(world)}/cases/{world.case_id}/analysis-charters",
        json=["not", "an", "object"],
    )
    assert array_body.status_code == 422
    payload = array_body.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "VALIDATION_FAILED"

    # Weaponized enum value: ValueError path must be enveloped, not a 500.
    body = {
        "decisionSubjectId": str(world.subject_id),
        "caseVersion": 1,
        "caseSnapshotHash": "sha256:case",
        "analysisLevel": "weaponized-level",
        "decisionQuestion": "q",
        "dossierSnapshotVersion": 1,
        "dossierSnapshotHash": "sha256:dossier",
    }
    bad_enum = await client.post(
        f"{_ws(world)}/cases/{world.case_id}/analysis-charters", json=body
    )
    assert bad_enum.status_code == 422
    assert bad_enum.json()["error"]["code"] == "VALIDATION_FAILED"


# --- A8: confirm bridge entered from awaiting_confirmation --------------------


async def test_confirm_from_awaiting_confirmation(client, session, world):
    repo = AnalysisRuntimeRepository(session)
    charter = await repo.create_charter_draft(**charter_values(world))
    await repo.submit_charter(world.workspace_id, charter.id)

    response = await client.post(
        f"{_ws(world)}/analysis-charters/{charter.id}/confirm"
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "confirmed"
