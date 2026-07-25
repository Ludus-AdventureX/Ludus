"""Seeding helpers for the Task 9 owner suite (uniquely named module).

Kept outside ``conftest.py`` so test modules can import these helpers by a
collision-free module name (three owner suites each carry a ``conftest.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.analyses.models import AnalysisCharter
from app.analyses.repository import AnalysisRuntimeRepository
from app.models import DecisionCase, DecisionSubject, User, Workspace, WorkspaceMembership
from app.types import FormalAnalysisLevel, WorkspaceRole

FULL_SET = [
    "porter_five_forces",
    "pre_mortem",
    "counterparty_response_matrix",
    "scenario_planning",
    "meadows_leverage_points",
]


@dataclass(slots=True)
class RuntimeWorld:
    workspace_id: UUID
    user_id: UUID
    subject_id: UUID
    case_id: UUID


async def seed_runtime_world(session: AsyncSession, slug: str) -> RuntimeWorld:
    ws_id, user_id, subject_id, case_id = uuid4(), uuid4(), uuid4(), uuid4()
    session.add(User(id=user_id, email=f"runtime-{slug}@example.test", password_hash="x"))
    await session.flush()
    session.add(Workspace(id=ws_id, name=f"ws-{slug}", created_by_user_id=user_id))
    await session.flush()
    session.add(
        WorkspaceMembership(
            id=uuid4(), workspace_id=ws_id, user_id=user_id, role=WorkspaceRole.OWNER
        )
    )
    session.add(
        DecisionSubject(id=subject_id, workspace_id=ws_id, name=f"subject-{slug}", slug=slug)
    )
    await session.flush()
    session.add(
        DecisionCase(
            decision_case_id=case_id,
            workspace_id=ws_id,
            decision_subject_id=subject_id,
            title=f"case-{slug}",
            decision_question="enter the rescue market?",
        )
    )
    await session.flush()
    return RuntimeWorld(
        workspace_id=ws_id, user_id=user_id, subject_id=subject_id, case_id=case_id
    )


def charter_values(
    world: RuntimeWorld,
    *,
    level: FormalAnalysisLevel = FormalAnalysisLevel.FULL,
    **overrides,
) -> dict:
    values = dict(
        workspace_id=world.workspace_id,
        decision_subject_id=world.subject_id,
        decision_case_id=world.case_id,
        case_version=1,
        case_snapshot_hash="sha256:case",
        analysis_level=level,
        decision_question="enter the rescue market?",
        dossier_snapshot_version=1,
        dossier_snapshot_hash="sha256:dossier",
        method_id="hardtech-market-direction",
        method_version="1.1.0",
        method_content_hash="sha256:method",
        formal_analysis_allowed=True,
        required_strategic_lens_types=(
            list(FULL_SET) if level == FormalAnalysisLevel.FULL else []
        ),
        allowed_connector_ids=["exa", "tavily"],
        budget={"max_model_calls": 20},
    )
    values.update(overrides)
    return values


async def make_confirmed_charter(
    session: AsyncSession,
    world: RuntimeWorld,
    *,
    level: FormalAnalysisLevel = FormalAnalysisLevel.FULL,
    **overrides,
) -> AnalysisCharter:
    repo = AnalysisRuntimeRepository(session)
    charter = await repo.create_charter_draft(**charter_values(world, level=level, **overrides))
    await repo.submit_charter(world.workspace_id, charter.id)
    return await repo.confirm_charter(world.workspace_id, charter.id)


async def make_queued_run(
    session: AsyncSession,
    world: RuntimeWorld,
    *,
    level: FormalAnalysisLevel = FormalAnalysisLevel.FULL,
    idempotency_key: str | None = None,
    **overrides,
):
    repo = AnalysisRuntimeRepository(session)
    charter = await make_confirmed_charter(session, world, level=level, **overrides)
    run, created = await repo.create_queued_run(
        workspace_id=world.workspace_id,
        charter_id=charter.id,
        idempotency_key=idempotency_key or f"idem-{uuid4().hex[:12]}",
        run_manifest_hash="sha256:manifest",
        cynefin_gate_result_id=uuid4(),
    )
    assert created
    return charter, run
