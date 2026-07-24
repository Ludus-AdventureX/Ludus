"""Formal QA for the StrategicLensArtifact read-only consumption path.

Converts the lane's one-off 24-item DB probe into permanent qa_release-owned
regressions: canonical ordering, tenancy/anti-enumeration, ready-only
consumption, review-capability audit reads, and projection immutability.
Runs against the real migrated PostgreSQL. Skips cleanly on trees without
``app.analyses.lens_artifact_reads``.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

pytest.importorskip(
    "app.analyses.lens_artifact_reads", reason="read path not delivered yet"
)

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.analyses.lens_artifact_reads import (
    LensArtifactView,
    StrategicLensArtifactReadService,
)
from app.db import get_database_url
from app.models import StrategicLensArtifact
from app.security.envelope import ApiFailure
from app.tenancy.context import WorkspaceContext
from app.types import (
    LensProducerRole,
    StrategicLensArtifactStatus,
    StrategicLensType,
    WorkspaceCapability,
    WorkspaceRole,
)

from tests.test_models import (
    seed_analysis_run,
    seed_case,
    seed_subject_pair,
    seed_user_and_workspaces,
)

CANONICAL_ORDER = (
    StrategicLensType.PORTER_FIVE_FORCES,
    StrategicLensType.COUNTERPARTY_RESPONSE_MATRIX,
    StrategicLensType.PRE_MORTEM,
    StrategicLensType.SCENARIO_PLANNING,
    StrategicLensType.MEADOWS_LEVERAGE_POINTS,
)

_ROLE_FOR_LENS = {
    StrategicLensType.PORTER_FIVE_FORCES: LensProducerRole.RESEARCH,
    StrategicLensType.COUNTERPARTY_RESPONSE_MATRIX: LensProducerRole.CRITIC,
    StrategicLensType.PRE_MORTEM: LensProducerRole.CRITIC,
    StrategicLensType.SCENARIO_PLANNING: LensProducerRole.SYNTHESIS,
    StrategicLensType.MEADOWS_LEVERAGE_POINTS: LensProducerRole.SYNTHESIS,
}


@pytest.fixture
async def read_stack():
    """Committed two-workspace stack with its own NullPool session."""

    engine = create_async_engine(get_database_url(), poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = factory()
    try:
        user_id, ws_a, ws_b = await seed_user_and_workspaces(session)
        subject_a, subject_b = await seed_subject_pair(session, ws_a)
        case_a = await seed_case(session, ws_a, subject_a)
        case_a2 = await seed_case(session, ws_a, subject_b)
        run_a = await seed_analysis_run(session, ws_a, case_a)
        run_a2 = await seed_analysis_run(session, ws_a, case_a2)
        # foreign tenant anchor (workspace B)
        subject_b1, _ = await seed_subject_pair(session, ws_b)
        case_b = await seed_case(session, ws_b, subject_b1)
        run_b = await seed_analysis_run(session, ws_b, case_b)
        await session.commit()
        yield {
            "session": session,
            "user": user_id,
            "ws_a": ws_a,
            "ws_b": ws_b,
            "case_a": case_a,
            "case_a2": case_a2,
            "case_b": case_b,
            "run_a": run_a,
            "run_a2": run_a2,
            "run_b": run_b,
        }
    finally:
        await session.close()
        await engine.dispose()


def _context(stack, *, workspace=None, capabilities=None, role=WorkspaceRole.OWNER):
    caps = (
        frozenset(WorkspaceCapability)
        if capabilities is None
        else frozenset(capabilities)
    )
    return WorkspaceContext(
        user_id=stack["user"] if isinstance(stack["user"], UUID) else uuid4(),
        workspace_id=workspace or stack["ws_a"],
        role=role,
        capabilities=caps,
    )


async def _add_artifact(
    session: AsyncSession,
    stack,
    lens_type: StrategicLensType,
    *,
    case=None,
    run=None,
    workspace=None,
    status=StrategicLensArtifactStatus.READY,
    created_at: datetime | None = None,
) -> UUID:
    artifact_id = uuid4()
    values = {
        "strategic_lens_artifact_id": artifact_id,
        "workspace_id": workspace or stack["ws_a"],
        "decision_case_id": case or stack["case_a"],
        "analysis_run_id": run or stack["run_a"],
        "charter_id": uuid4(),
        "lens_type": lens_type,
        "producer_role": _ROLE_FOR_LENS[lens_type],
        "status": status,
        "method_id": "hardtech-market-direction",
        "method_version": "1.1.0",
        "method_content_hash": "sha256:method",
        "prompt_version": "1.0.0",
        "schema_version": "1.1.0",
        "origin_modes": ["fixture"],
        "content_hash": f"sha256:lens-{artifact_id.hex[:12]}",
        "payload": {"summary": "qa", "nested": {"keep": True}},
        "claim_refs": ["claim-1"],
        "evidence_refs": ["evidence-1"],
        "assumption_refs": [],
    }
    if status is StrategicLensArtifactStatus.READY:
        values["validation_accepted_at"] = datetime.now(timezone.utc)
    if created_at is not None:
        values["created_at"] = created_at
    await session.execute(insert(StrategicLensArtifact).values(**values))
    await session.commit()
    return artifact_id


def _failure_signature(exc: ApiFailure) -> tuple:
    return (exc.code, exc.message, exc.http_status)


# ---------------------------------------------------------------------------
# A. canonical ordering
# ---------------------------------------------------------------------------


async def test_shuffled_inserts_return_canonical_execution_order(read_stack) -> None:
    session = read_stack["session"]
    shuffled = (
        StrategicLensType.MEADOWS_LEVERAGE_POINTS,
        StrategicLensType.PORTER_FIVE_FORCES,
        StrategicLensType.SCENARIO_PLANNING,
        StrategicLensType.COUNTERPARTY_RESPONSE_MATRIX,
        StrategicLensType.PRE_MORTEM,
    )
    for lens in shuffled:
        await _add_artifact(session, read_stack, lens)

    service = StrategicLensArtifactReadService(session)
    views = await service.list_ready_for_run(
        _context(read_stack), read_stack["case_a"], read_stack["run_a"]
    )
    returned = tuple(view.lens_type for view in views)
    assert returned == CANONICAL_ORDER, "must return canonical execution order"
    assert returned.index(StrategicLensType.COUNTERPARTY_RESPONSE_MATRIX) < returned.index(
        StrategicLensType.PRE_MORTEM
    ), "counterparty must strictly precede pre_mortem"


async def test_created_at_then_artifact_id_break_ties(read_stack) -> None:
    session = read_stack["session"]
    base = datetime.now(timezone.utc) - timedelta(hours=1)
    later = await _add_artifact(
        session,
        read_stack,
        StrategicLensType.PORTER_FIVE_FORCES,
        status=StrategicLensArtifactStatus.DRAFT,
        created_at=base + timedelta(minutes=5),
    )
    earlier = await _add_artifact(
        session,
        read_stack,
        StrategicLensType.PORTER_FIVE_FORCES,
        status=StrategicLensArtifactStatus.DRAFT,
        created_at=base,
    )
    service = StrategicLensArtifactReadService(session)
    views = await service.list_for_audit(
        _context(read_stack),
        read_stack["case_a"],
        analysis_run_id=read_stack["run_a"],
        statuses=[StrategicLensArtifactStatus.DRAFT],
    )
    ids = [view.strategic_lens_artifact_id for view in views]
    assert ids.index(earlier) < ids.index(later), "created_at is the first tie-breaker"

    twin_time = base + timedelta(minutes=30)
    first = await _add_artifact(
        session,
        read_stack,
        StrategicLensType.PORTER_FIVE_FORCES,
        status=StrategicLensArtifactStatus.REJECTED,
        created_at=twin_time,
    )
    second = await _add_artifact(
        session,
        read_stack,
        StrategicLensType.PORTER_FIVE_FORCES,
        status=StrategicLensArtifactStatus.REJECTED,
        created_at=twin_time,
    )
    views = await service.list_for_audit(
        _context(read_stack),
        read_stack["case_a"],
        analysis_run_id=read_stack["run_a"],
        statuses=[StrategicLensArtifactStatus.REJECTED],
    )
    ids = [view.strategic_lens_artifact_id for view in views]
    assert ids == sorted(ids), "artifact id is the stable final tie-breaker"
    assert {first, second} == set(ids)


# ---------------------------------------------------------------------------
# B. tenancy and existence hiding
# ---------------------------------------------------------------------------


async def test_foreign_and_ghost_anchors_share_one_404(read_stack) -> None:
    session = read_stack["session"]
    service = StrategicLensArtifactReadService(session)
    context = _context(read_stack)

    with pytest.raises(ApiFailure) as foreign_case:
        await service.list_ready_for_case(context, read_stack["case_b"])
    with pytest.raises(ApiFailure) as ghost_case:
        await service.list_ready_for_case(context, uuid4())
    with pytest.raises(ApiFailure) as foreign_run:
        await service.list_ready_for_run(
            context, read_stack["case_b"], read_stack["run_b"]
        )
    with pytest.raises(ApiFailure) as ghost_run:
        await service.list_ready_for_run(context, read_stack["case_a"], uuid4())

    signatures = {
        _failure_signature(excinfo.value)
        for excinfo in (foreign_case, ghost_case, foreign_run, ghost_run)
    }
    assert len(signatures) == 1, "foreign and ghost anchors must be indistinguishable"
    code, _, status = signatures.pop()
    assert code == "CASE_NOT_FOUND" and status == 404


async def test_foreign_artifact_id_with_local_anchor_is_404(read_stack) -> None:
    session = read_stack["session"]
    foreign_artifact = await _add_artifact(
        session,
        read_stack,
        StrategicLensType.PORTER_FIVE_FORCES,
        workspace=read_stack["ws_b"],
        case=read_stack["case_b"],
        run=read_stack["run_b"],
    )
    service = StrategicLensArtifactReadService(session)
    with pytest.raises(ApiFailure) as excinfo:
        await service.get_ready_artifact(
            _context(read_stack),
            read_stack["case_a"],
            read_stack["run_a"],
            foreign_artifact,
        )
    assert excinfo.value.code == "CASE_NOT_FOUND"


async def test_mixed_workspace_case_run_anchors_are_404(read_stack) -> None:
    session = read_stack["session"]
    service = StrategicLensArtifactReadService(session)
    context = _context(read_stack)
    # case from A, run from B
    with pytest.raises(ApiFailure) as mixed_one:
        await service.list_ready_for_run(
            context, read_stack["case_a"], read_stack["run_b"]
        )
    # case from A subject-2, run from A case-1 (cross-case within tenant)
    with pytest.raises(ApiFailure) as mixed_two:
        await service.list_ready_for_run(
            context, read_stack["case_a2"], read_stack["run_a"]
        )
    assert (
        _failure_signature(mixed_one.value)
        == _failure_signature(mixed_two.value)
    )
    assert mixed_one.value.code == "CASE_NOT_FOUND"


async def test_anchor_404_precedes_review_capability_403(read_stack) -> None:
    session = read_stack["session"]
    service = StrategicLensArtifactReadService(session)
    no_review = _context(
        read_stack,
        capabilities=[WorkspaceCapability.CONTRIBUTE],
        role=WorkspaceRole.MEMBER,
    )
    with pytest.raises(ApiFailure) as foreign:
        await service.list_for_audit(no_review, read_stack["case_b"])
    with pytest.raises(ApiFailure) as ghost:
        await service.list_for_audit(no_review, uuid4())
    assert foreign.value.code == ghost.value.code == "CASE_NOT_FOUND", (
        "anchor 404 must fire before the capability 403 to avoid probing"
    )


# ---------------------------------------------------------------------------
# C. ready-only consumption
# ---------------------------------------------------------------------------


async def test_consumption_returns_ready_only(read_stack) -> None:
    session = read_stack["session"]
    ready = await _add_artifact(session, read_stack, StrategicLensType.PRE_MORTEM)
    await _add_artifact(
        session,
        read_stack,
        StrategicLensType.PRE_MORTEM,
        status=StrategicLensArtifactStatus.DRAFT,
    )
    await _add_artifact(
        session,
        read_stack,
        StrategicLensType.PRE_MORTEM,
        status=StrategicLensArtifactStatus.REJECTED,
    )
    service = StrategicLensArtifactReadService(session)
    views = await service.list_ready_for_run(
        _context(read_stack), read_stack["case_a"], read_stack["run_a"]
    )
    assert [view.strategic_lens_artifact_id for view in views] == [ready]


async def test_draft_rejected_and_missing_get_identical_errors(read_stack) -> None:
    session = read_stack["session"]
    draft = await _add_artifact(
        session,
        read_stack,
        StrategicLensType.SCENARIO_PLANNING,
        status=StrategicLensArtifactStatus.DRAFT,
    )
    rejected = await _add_artifact(
        session,
        read_stack,
        StrategicLensType.SCENARIO_PLANNING,
        status=StrategicLensArtifactStatus.REJECTED,
    )
    service = StrategicLensArtifactReadService(session)
    context = _context(read_stack)
    signatures = set()
    for artifact_id in (draft, rejected, uuid4()):
        with pytest.raises(ApiFailure) as excinfo:
            await service.get_ready_artifact(
                context, read_stack["case_a"], read_stack["run_a"], artifact_id
            )
        signatures.add(_failure_signature(excinfo.value))
    assert len(signatures) == 1, "lifecycle state must not be probeable via get"


async def test_lens_type_filter_and_scope_levels(read_stack) -> None:
    session = read_stack["session"]
    porter_a = await _add_artifact(
        session, read_stack, StrategicLensType.PORTER_FIVE_FORCES
    )
    meadows_a = await _add_artifact(
        session, read_stack, StrategicLensType.MEADOWS_LEVERAGE_POINTS
    )
    porter_a2 = await _add_artifact(
        session,
        read_stack,
        StrategicLensType.PORTER_FIVE_FORCES,
        case=read_stack["case_a2"],
        run=read_stack["run_a2"],
    )
    service = StrategicLensArtifactReadService(session)
    context = _context(read_stack)

    workspace_views = await service.list_ready_for_workspace(context)
    workspace_ids = {view.strategic_lens_artifact_id for view in workspace_views}
    assert {porter_a, meadows_a, porter_a2} <= workspace_ids

    case_views = await service.list_ready_for_case(context, read_stack["case_a"])
    case_ids = {view.strategic_lens_artifact_id for view in case_views}
    assert porter_a in case_ids and meadows_a in case_ids and porter_a2 not in case_ids

    run_views = await service.list_ready_for_run(
        context,
        read_stack["case_a"],
        read_stack["run_a"],
        lens_types=[StrategicLensType.PORTER_FIVE_FORCES],
    )
    assert [view.strategic_lens_artifact_id for view in run_views] == [porter_a], (
        "lens_type filter must be exact"
    )


# ---------------------------------------------------------------------------
# D. audit reads and capability contract
# ---------------------------------------------------------------------------


async def test_review_capability_gates_audit_reads(read_stack) -> None:
    session = read_stack["session"]
    draft = await _add_artifact(
        session,
        read_stack,
        StrategicLensType.COUNTERPARTY_RESPONSE_MATRIX,
        status=StrategicLensArtifactStatus.DRAFT,
    )
    service = StrategicLensArtifactReadService(session)

    owner_views = await service.list_for_audit(
        _context(read_stack), read_stack["case_a"]
    )
    assert draft in {view.strategic_lens_artifact_id for view in owner_views}, (
        "owner (full projected capability set) can audit drafts"
    )

    reviewer_views = await service.list_for_audit(
        _context(
            read_stack,
            capabilities=[WorkspaceCapability.REVIEW],
            role=WorkspaceRole.MEMBER,
        ),
        read_stack["case_a"],
    )
    assert draft in {view.strategic_lens_artifact_id for view in reviewer_views}

    with pytest.raises(ApiFailure) as excinfo:
        await service.list_for_audit(
            _context(
                read_stack,
                capabilities=[WorkspaceCapability.CONTRIBUTE],
                role=WorkspaceRole.MEMBER,
            ),
            read_stack["case_a"],
        )
    assert excinfo.value.code == "MEMBERSHIP_CAPABILITY_REQUIRED"
    assert excinfo.value.http_status == 403
    assert excinfo.value.details == {"requiredCapability": "review"}


# ---------------------------------------------------------------------------
# E. projection safety
# ---------------------------------------------------------------------------


async def test_projection_is_immutable_and_detached_from_orm(read_stack) -> None:
    session = read_stack["session"]
    artifact_id = await _add_artifact(
        session, read_stack, StrategicLensType.PORTER_FIVE_FORCES
    )
    service = StrategicLensArtifactReadService(session)
    context = _context(read_stack)
    view = await service.get_ready_artifact(
        context, read_stack["case_a"], read_stack["run_a"], artifact_id
    )

    assert isinstance(view, LensArtifactView)
    assert dataclasses.is_dataclass(view)
    with pytest.raises(dataclasses.FrozenInstanceError):
        view.content_hash = "sha256:tampered"  # type: ignore[misc]
    assert isinstance(view.claim_refs, tuple)
    assert isinstance(view.evidence_refs, tuple)
    assert isinstance(view.assumption_refs, tuple)
    assert isinstance(view.origin_modes, tuple)

    # deep-copied payload: consumer mutation must not leak back
    view.payload["nested"]["keep"] = False
    view.payload["injected"] = True
    fresh = await service.get_ready_artifact(
        context, read_stack["case_a"], read_stack["run_a"], artifact_id
    )
    assert fresh.payload == {"summary": "qa", "nested": {"keep": True}}, (
        "consumer mutations of the projection must never reach ORM state"
    )
