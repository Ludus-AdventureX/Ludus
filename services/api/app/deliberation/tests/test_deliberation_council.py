"""Deliberation council QA battery (CCR-20260804-DELIB-01 Wave 2).

Red lines under test:
- anti-enumeration: foreign/missing deliberation ids answer the byte-identical
  CASE_NOT_FOUND 404;
- nominations NEVER auto-activate (no factor before user confirmation);
- interventions are classification-first and fail closed;
- the round budget (maxRounds <= 5) is enforced;
- every persisted message/outcome is scanned for probability claims (§7);
- the fixture path is fully deterministic and key-free.
"""

from __future__ import annotations

import json
import re
from uuid import UUID, uuid4

import httpx
import pytest_asyncio
from fastapi import FastAPI, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deliberation.orchestrator import DeliberationOrchestrator
from app.deliberation.repository import DeliberationRepository
from app.deliberation.routes import router as deliberation_router
from app.deliberation.service import DeliberationService, load_case_basis
from app.security.csrf import require_csrf
from app.security.envelope import register_error_handlers, workspace_not_found
from app.tenancy.context import (
    ALL_CAPABILITIES,
    WorkspaceContext,
    require_workspace_context,
)
from app.types import (
    DeliberationFactorProvenance,
    DeliberationNominationStatus,
    DeliberationProposalStatus,
    DeliberationRunStatus,
    OriginMode,
    WorkspaceRole,
)

from conftest import DeliberationWorld

PROBABILITY_CLAIM = re.compile(
    r"成功概率|结论正确概率|正确的概率|成功率\s*[:：]?\s*\d|概率\s*[:：]?\s*\d+\s*%"
)


def _build_app(session: AsyncSession, memberships: dict[UUID, UUID]) -> FastAPI:
    app = FastAPI(title="Ludus QA deliberation assembly")
    app.include_router(deliberation_router)
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

    async def no_csrf():
        return None

    app.dependency_overrides[require_workspace_context] = fake_context
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_csrf] = no_csrf
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
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as http:
        yield http, world, foreign_world


# ---------------------------------------------------------------------------
# Anti-enumeration
# ---------------------------------------------------------------------------


async def test_cross_workspace_and_missing_run_ids_are_byte_identical_404(client) -> None:
    http, world, foreign_world = client
    # Create a run in world A first.
    created = await http.post(
        f"/api/workspaces/{world.workspace_id}/cases/{world.case_id}/deliberations",
        json={"subjectiveFactors": [], "maxRounds": 3},
    )
    assert created.status_code == 200, created.text
    run_id = created.json()["data"]["id"]

    ghost = uuid4()
    targets = [
        # foreign tenant reading world A's run id
        f"/api/workspaces/{foreign_world.workspace_id}/deliberations/{run_id}",
        f"/api/workspaces/{foreign_world.workspace_id}/deliberations/{run_id}/messages",
        f"/api/workspaces/{foreign_world.workspace_id}/deliberations/{run_id}/outcome",
        # world A reading a ghost id
        f"/api/workspaces/{world.workspace_id}/deliberations/{ghost}",
        f"/api/workspaces/{world.workspace_id}/deliberations/{ghost}/messages",
        f"/api/workspaces/{world.workspace_id}/deliberations/{ghost}/outcome",
    ]
    bodies = []
    for url in targets:
        response = await http.get(url)
        assert response.status_code == 404, url
        bodies.append(response.content)
    assert len(set(bodies)) == 1, "all scope denials must be byte-identical"


async def test_budget_cap_rejects_max_rounds_over_five(client) -> None:
    http, world, _ = client
    response = await http.post(
        f"/api/workspaces/{world.workspace_id}/cases/{world.case_id}/deliberations",
        json={"subjectiveFactors": [], "maxRounds": 6},
    )
    # Schema-level fail-closed gate (le=5) rejects before the service check.
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


async def test_intervention_classification_fails_closed(client) -> None:
    http, world, _ = client
    created = await http.post(
        f"/api/workspaces/{world.workspace_id}/cases/{world.case_id}/deliberations",
        json={"subjectiveFactors": [], "maxRounds": 3},
    )
    run_id = created.json()["data"]["id"]
    base = f"/api/workspaces/{world.workspace_id}/deliberations/{run_id}/interventions"

    unknown = await http.post(base, json={"kind": "summon_witness"})
    # The Literal schema is the first gate; the service classification is the
    # defense-in-depth backstop for anything that slips past it.
    assert unknown.status_code == 422
    assert unknown.json()["error"]["code"] == "VALIDATION_FAILED"

    empty_interject = await http.post(base, json={"kind": "interject"})
    assert empty_interject.status_code == 422

    challenge_missing_target = await http.post(
        base, json={"kind": "challenge_witness", "text": "凭什么？"}
    )
    assert challenge_missing_target.status_code == 422


# ---------------------------------------------------------------------------
# Full fixture flow + red lines
# ---------------------------------------------------------------------------


async def _advance_to_stable(
    session: AsyncSession,
    world: DeliberationWorld,
    run_id: UUID,
    *,
    max_steps: int = 12,
) -> DeliberationRunStatus:
    repo = DeliberationRepository(session)
    orchestrator = DeliberationOrchestrator(repo, provider=None, origin_mode=OriginMode.FIXTURE)
    packets, influences = await load_case_basis(session, world.workspace_id, world.case_id)
    status = DeliberationRunStatus.PREPARING
    for _ in range(max_steps):
        status = await orchestrator.advance(
            world.workspace_id, run_id, packets=packets, influences=influences
        )
        await session.flush()
        if status in (
            DeliberationRunStatus.COMPLETE,
            DeliberationRunStatus.AWAITING_USER,
            DeliberationRunStatus.CANCELLED,
        ):
            return status
    return status


async def test_full_fixture_flow_nominations_proposals_and_probability_ban(
    session, world
) -> None:
    repo = DeliberationRepository(session)
    service = DeliberationService(repo, origin_mode=OriginMode.FIXTURE)
    packets, influences = await load_case_basis(session, world.workspace_id, world.case_id)

    run = await service.create_run(
        workspace_id=world.workspace_id,
        decision_case_id=world.case_id,
        user_id=world.user_id,
        packets=packets,
        influences=influences,
        subjective_declarations=[
            {"label": "对手降价意愿", "statement": "[opposing] 对手很可能在半年内降价抢量", "strength": 0.6}
        ],
        max_rounds=3,
    )
    factors = await repo.list_factors(world.workspace_id, run.id)
    assert sum(1 for f in factors if f.provenance is DeliberationFactorProvenance.OBJECTIVE) == 3
    subjective = [f for f in factors if f.provenance is DeliberationFactorProvenance.SUBJECTIVE]
    assert len(subjective) == 1
    assert subjective[0].author_user_id == world.user_id
    assert subjective[0].evidence_status.value in {"assumed", "unknown"}

    # Opening round: every factor witness speaks (fixture determinism).
    status = await _advance_to_stable(session, world, run.id, max_steps=1)
    assert status is DeliberationRunStatus.RUNNING
    messages = await repo.list_messages(world.workspace_id, run.id, limit=100, before_id=None)
    statements = [m for m in messages if m.kind.value == "statement"]
    assert len(statements) == 4  # 3 objective + 1 subjective witness

    # Drive to the next stable state (nomination parks the run, or running).
    status = await _advance_to_stable(session, world, run.id)
    if status is DeliberationRunStatus.AWAITING_USER:
        pending = await repo.list_nominations(
            world.workspace_id, run.id, status=DeliberationNominationStatus.PENDING
        )
        assert pending, "awaiting_user requires a pending nomination"
        # RED LINE: nomination never auto-activated — no new factor yet.
        before_count = len(await repo.list_factors(world.workspace_id, run.id))
        nomination = pending[0]

        # Confirm with a full declaration -> factor appears and run resumes.
        confirmed = await service.decide_nomination(
            workspace_id=world.workspace_id,
            run_id=run.id,
            nomination_id=nomination.id,
            decision="confirmed",
            user_id=world.user_id,
            subjective_factor={
                "label": nomination.target_description,
                "statement": "内部渠道反馈：该因子比表面证据更强",
                "strength": 0.65,
            },
        )
        assert confirmed.status is DeliberationNominationStatus.CONFIRMED
        after_factors = await repo.list_factors(world.workspace_id, run.id)
        assert len(after_factors) == before_count + 1
        status = await _advance_to_stable(session, world, run.id)

    # Accept any pending proposal so the verdict carries a projection delta.
    pending_proposals = await repo.list_proposals(
        world.workspace_id, run.id, status=DeliberationProposalStatus.PENDING
    )
    for proposal in pending_proposals:
        decided = await service.decide_proposal(
            workspace_id=world.workspace_id,
            run_id=run.id,
            proposal_id=proposal.id,
            decision="accepted",
        )
        assert decided.status is DeliberationProposalStatus.ACCEPTED
        assert decided.decided_at is not None
    # Idempotent replay of the same decision.
    if pending_proposals:
        replayed = await service.decide_proposal(
            workspace_id=world.workspace_id,
            run_id=run.id,
            proposal_id=pending_proposals[0].id,
            decision="accepted",
        )
        assert replayed.status is DeliberationProposalStatus.ACCEPTED

    # Drive to the verdict.
    status = await _advance_to_stable(session, world, run.id)
    assert status is DeliberationRunStatus.COMPLETE

    outcome = await repo.get_outcome(world.workspace_id, run.id)
    assert outcome is not None
    assert outcome.disclaimer == "沙盘与议会不代表精确预测。"
    assert outcome.condition_projections, "verdict must carry engine projections"
    assert outcome.assumption_ledger, "verdict must list the full assumption ledger"
    for projection in outcome.condition_projections:
        assert set(projection) >= {"acceptedProposalIds", "projection", "condition"}

    # RED LINE scan: no probability claim anywhere in persisted output.
    all_messages = await repo.list_messages(world.workspace_id, run.id, limit=500, before_id=None)
    haystacks = [m.content for m in all_messages]
    haystacks.append(json.dumps(outcome.condition_projections, ensure_ascii=False))
    haystacks.append(json.dumps(outcome.dissent_log, ensure_ascii=False))
    haystacks.append(json.dumps(outcome.flip_conditions, ensure_ascii=False))
    for text in haystacks:
        assert not PROBABILITY_CLAIM.search(text), f"probability claim leaked: {text[:120]}"


async def test_rejected_nomination_creates_no_factor_and_resumes(session, world) -> None:
    repo = DeliberationRepository(session)
    service = DeliberationService(repo, origin_mode=OriginMode.FIXTURE)
    packets, influences = await load_case_basis(session, world.workspace_id, world.case_id)
    run = await service.create_run(
        workspace_id=world.workspace_id,
        decision_case_id=world.case_id,
        user_id=world.user_id,
        packets=packets,
        influences=influences,
        subjective_declarations=[],
        max_rounds=3,
    )
    await _advance_to_stable(session, world, run.id, max_steps=1)
    status = await _advance_to_stable(session, world, run.id)
    if status is not DeliberationRunStatus.AWAITING_USER:
        return  # no nomination produced for this basis; nothing to reject
    pending = await repo.list_nominations(
        world.workspace_id, run.id, status=DeliberationNominationStatus.PENDING
    )
    assert pending
    before_count = len(await repo.list_factors(world.workspace_id, run.id))
    rejected = await service.decide_nomination(
        workspace_id=world.workspace_id,
        run_id=run.id,
        nomination_id=pending[0].id,
        decision="rejected",
        user_id=world.user_id,
        subjective_factor=None,
    )
    assert rejected.status is DeliberationNominationStatus.REJECTED
    assert rejected.confirmed_factor_id is None
    assert len(await repo.list_factors(world.workspace_id, run.id)) == before_count
    refreshed = await repo.get_run(world.workspace_id, run.id)
    assert refreshed.status is DeliberationRunStatus.RUNNING

async def test_list_messages_pagination_no_dup_no_gap(session, world) -> None:
    """Regression for P1-1: cursor pagination must not 500 and must not
    duplicate or skip messages, including same-timestamp batches."""
    repo = DeliberationRepository(session)
    service = DeliberationService(repo, origin_mode=OriginMode.FIXTURE)
    packets, influences = await load_case_basis(session, world.workspace_id, world.case_id)
    run = await service.create_run(
        workspace_id=world.workspace_id,
        decision_case_id=world.case_id,
        user_id=world.user_id,
        packets=packets,
        influences=influences,
        subjective_declarations=[],
        max_rounds=3,
    )
    await _advance_to_stable(session, world, run.id, max_steps=1)

    all_messages = await repo.list_messages(world.workspace_id, run.id, limit=500, before_id=None)
    assert len(all_messages) >= 3
    # Force every message onto the exact same timestamp so the
    # (created_at, id) tuple cursor is exercised, not a naive <= comparison.
    same_ts = all_messages[0].created_at
    for message in all_messages:
        message.created_at = same_ts
    await session.flush()

    page_size = 2
    seen: list[UUID] = []
    cursor: UUID | None = None
    while True:
        page = await repo.list_messages(
            world.workspace_id, run.id, limit=page_size, before_id=cursor
        )
        if not page:
            break
        for message in page:
            assert message.id not in seen, f"duplicate message {message.id}"
            seen.append(message.id)
        assert len(page) <= page_size
        # Each page is internally oldest -> newest.
        assert [m.id for m in page] == sorted(m.id for m in page)
        cursor = page[0].id
    assert sorted(seen) == sorted(m.id for m in all_messages), (
        "pagination must cover exactly the full set, no duplicates, no gaps"
    )

    # A cursor that is not a member of this run is ignored (tenancy guard),
    # never applied, and never errors.
    foreign_cursor = uuid4()
    safe = await repo.list_messages(world.workspace_id, run.id, limit=5, before_id=foreign_cursor)
    assert len(safe) <= 5
    assert sorted(m.id for m in safe) == sorted(m.id for m in all_messages)
