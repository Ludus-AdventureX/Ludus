"""Task 4/5 QA battery (≥6 supplementary gates).

Covers, per the task charter's QA standard:
1. Whole-codebase + whole-metadata scan: ``reasoning_content`` has zero
   persistence and zero logging paths.
2. Full chain over HTTP: candidate -> confirm -> version+1 -> snapshot
   excludes unconfirmed.
3. Confirm with a stale base version returns HTTP 409.
4. Expire/Reclassify fork between candidates and confirmed entries.
5. Tenant anti-enumeration: foreign and nonexistent resources are
   indistinguishable 404s.
6. Fixture provider determinism (byte-identical across repeated calls).
7. Migration lifecycle: this lane ships no Alembic revision yet (deferred on
   Task 10's 0004), and the ORM metadata materialises cleanly instead.

Zero real network: the app under test runs on an ASGI transport with the
deterministic fixture provider injected.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, FastAPI
from fastapi import Path as PathParam
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.model_provider import FixtureModelProvider, ModelMessage
from app.auth.config import get_auth_settings
from app.db import Base, get_session
from app.security.envelope import register_error_handlers, workspace_not_found
from app.tenancy.context import WorkspaceContext, require_workspace_context
from app.types import WorkspaceCapability, WorkspaceRole

from test_dossier_versions import (
    DossierWorld,
    seed_dossier_world,
    session,  # noqa: F401  (fixture re-export)
)

TEST_ORIGIN = "http://testserver"
CSRF_TOKEN = "task0405-qa-csrf-token"

APP_DIR = Path(__file__).resolve().parents[1] / "app"


# ---------------------------------------------------------------------------
# App assembly: relative routers mounted exactly as the Contract Lead will
# ---------------------------------------------------------------------------


def build_task0405_app(
    db_session: AsyncSession,
    context_holder: dict,
    provider: FixtureModelProvider,
) -> FastAPI:
    from app.cases.routes import router as cases_router
    from app.conversations.routes import get_model_provider
    from app.conversations.routes import router as conversations_router
    from app.dossiers.routes import router as dossiers_router

    app = FastAPI(title="Task 4/5 QA assembly")
    mount = APIRouter(prefix="/api/workspaces/{workspaceId}")
    mount.include_router(cases_router)
    mount.include_router(dossiers_router)
    mount.include_router(conversations_router)
    app.include_router(mount)
    register_error_handlers(app)

    async def _session_override():
        yield db_session

    async def _context_override(
        workspace_id: UUID = PathParam(alias="workspaceId"),
    ) -> WorkspaceContext:
        context: WorkspaceContext = context_holder["context"]
        if context.workspace_id != workspace_id:
            raise workspace_not_found()
        return context

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[require_workspace_context] = _context_override
    app.dependency_overrides[get_model_provider] = lambda: provider
    return app


def qa_client(app: FastAPI) -> httpx.AsyncClient:
    settings = get_auth_settings()
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url=TEST_ORIGIN,
        headers={"Origin": TEST_ORIGIN, settings.csrf_header_name: CSRF_TOKEN},
        cookies={settings.csrf_cookie_name: CSRF_TOKEN},
    )


def owner_context(world: DossierWorld) -> WorkspaceContext:
    return WorkspaceContext(
        user_id=uuid4(),
        workspace_id=world.workspace_id,
        role=WorkspaceRole.OWNER,
        capabilities=frozenset(WorkspaceCapability),
    )


def reply_provider() -> FixtureModelProvider:
    provider = FixtureModelProvider()
    message = "目标是在 9 个月现金窗口内验证真实需求，只能优先投入一个方向。"
    provider.register(message, {"assistantMessage": "已记录现金窗口约束，待确认。"})
    # The extractor keys on the same last-message content.
    provider.register(
        message,
        {"assistantMessage": "已记录现金窗口约束，待确认。"},
    )
    return provider


# ---------------------------------------------------------------------------
# QA-1: reasoning_content — zero persistence, zero logging
# ---------------------------------------------------------------------------


def test_qa1_reasoning_content_has_no_orm_column_anywhere() -> None:
    offending = [
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if "reasoning" in column.name.lower()
    ]
    assert offending == [], f"reasoning_content must never persist: {offending}"


def test_qa1_reasoning_content_source_scan_no_persistence_no_logging() -> None:
    """Every mention in app/** must be transient-drop or documentation.

    A line mentioning reasoning_content may never also reference a column
    mapping, a log call, an event payload, or an assignment into a persisted
    structure.
    """

    forbidden = re.compile(
        r"(mapped_column|Column\(|logger\.|logging\.|\.info\(|\.debug\(|\.warning\("
        r"|payload\[|token_usage|session\.add)"
    )
    mentions: list[tuple[Path, str]] = []
    for path in APP_DIR.rglob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if "reasoning_content" in line:
                mentions.append((path, line.strip()))
                assert not forbidden.search(line), (
                    f"{path}: reasoning_content near a persistence/logging call: {line!r}"
                )
    # The transient-drop seam itself must exist (provider strips the field).
    assert any(
        "pop(\"reasoning_content\"" in line.replace("'", '"')
        for _, line in mentions
    ), "the provider must actively drop reasoning_content"


# ---------------------------------------------------------------------------
# QA-2 + QA-3: full HTTP chain and stale-version 409
# ---------------------------------------------------------------------------


async def test_qa2_full_chain_candidate_confirm_version_snapshot(
    session: AsyncSession,  # noqa: F811
) -> None:
    world = await seed_dossier_world(session)
    provider = reply_provider()
    holder = {"context": owner_context(world)}
    app = build_task0405_app(session, holder, provider)
    message = "目标是在 9 个月现金窗口内验证真实需求，只能优先投入一个方向。"
    provider.register(
        message,
        {
            "assistantMessage": "已记录现金窗口约束，待确认。",
            "candidates": [
                {
                    "statementType": "constraint",
                    "content": "现金窗口为9个月",
                    "scope": "case",
                }
            ],
            "decisionQuestions": [],
        },
    )
    async with qa_client(app) as client:
        base = f"/api/workspaces/{world.workspace_id}"
        # 1. message -> candidate only (case version unchanged)
        response = await client.post(
            f"{base}/cases/{world.case_id}/messages",
            json={"message": message, "proposeStructuredUpdates": True},
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        candidate_id = data["candidateRevisionId"]
        assert candidate_id is not None
        assert data["baseDossierVersion"] == 1
        assert data["baseCaseVersion"] == 1

        # 2. candidate visible in review queue
        response = await client.get(f"{base}/cases/{world.case_id}/candidates")
        assert response.status_code == 200
        items = response.json()["data"]["items"]
        assert [item["candidateRevisionId"] for item in items] == [candidate_id]

        # 3. confirm bumps both versions transactionally
        response = await client.post(
            f"{base}/cases/{world.case_id}/candidates/{candidate_id}/confirm",
            json={"baseDossierVersion": 1, "baseCaseVersion": 1},
        )
        assert response.status_code == 200, response.text
        confirm_data = response.json()["data"]
        assert confirm_data["dossierVersion"] == 2
        assert confirm_data["caseVersion"] == 2

        # 4. detail projection reflects version+1 and only confirmed content
        response = await client.get(f"{base}/cases/{world.case_id}")
        detail = response.json()["data"]
        assert detail["caseVersion"] == 2
        assert detail["confirmedDossierVersion"] == 2
        texts = [node["text"] for node in detail["argumentNodes"]]
        assert "现金窗口为9个月" in texts

        # 5. immutable case version row is readable
        response = await client.get(f"{base}/cases/{world.case_id}/versions/2")
        assert response.status_code == 200
        assert response.json()["data"]["dossierVersion"] == 2


async def test_qa3_confirm_with_stale_base_version_returns_409(
    session: AsyncSession,  # noqa: F811
) -> None:
    from app.dossiers.service import DossierService, ProposeEntry
    from app.types import CandidateSourceType

    world = await seed_dossier_world(session)
    service = DossierService(session, workspace_id=world.workspace_id)

    def proposal(content: str) -> dict:
        return {
            "operation": "add",
            "entry": {
                "scope": "case",
                "statementType": "constraint",
                "content": content,
                "sourceType": "ai_candidate",
            },
        }

    first = await service.propose(
        ProposeEntry(
            workspace_id=world.workspace_id,
            decision_subject_id=world.subject_id,
            decision_case_id=world.case_id,
            proposals=[proposal("约束1")],
            source_type=CandidateSourceType.CONVERSATION,
            source_id=uuid4(),
            base_dossier_version=1,
            base_case_version=1,
        )
    )
    second = await service.propose(
        ProposeEntry(
            workspace_id=world.workspace_id,
            decision_subject_id=world.subject_id,
            decision_case_id=world.case_id,
            proposals=[proposal("约束2")],
            source_type=CandidateSourceType.CONVERSATION,
            source_id=uuid4(),
            base_dossier_version=1,
            base_case_version=1,
        )
    )
    holder = {"context": owner_context(world)}
    app = build_task0405_app(session, holder, reply_provider())
    async with qa_client(app) as client:
        base = f"/api/workspaces/{world.workspace_id}"
        response = await client.post(
            f"{base}/cases/{world.case_id}/candidates/{first.id}/confirm",
            json={"baseDossierVersion": 1, "baseCaseVersion": 1},
        )
        assert response.status_code == 200, response.text

        response = await client.post(
            f"{base}/cases/{world.case_id}/candidates/{second.id}/confirm",
            json={"baseDossierVersion": 1, "baseCaseVersion": 1},
        )
        assert response.status_code == 409
        body = response.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "DOSSIER_VERSION_CONFLICT"
        assert body["error"]["details"]["expected"] == 2


# ---------------------------------------------------------------------------
# QA-4: expire/reclassify fork (candidate vs confirmed)
# ---------------------------------------------------------------------------


async def test_qa4_expire_and_reclassify_fork_candidate_vs_confirmed(
    session: AsyncSession,  # noqa: F811
) -> None:
    from sqlalchemy import func, select

    from app.dossiers.service import DossierService, ExpireEntry, ReclassifyEntry
    from app.models import DossierVersion
    from app.types import DossierStatementType

    world = await seed_dossier_world(session)
    service = DossierService(session, workspace_id=world.workspace_id)
    confirmed = await service.add_entry(
        world.subject_id, "已确认约束", "constraint", "confirmed", scope="subject"
    )
    candidate = await service.add_entry(
        world.subject_id, "候选判断", "judgment", "candidate", scope="subject"
    )

    async def version_count() -> int:
        return await session.scalar(
            select(func.count()).select_from(DossierVersion).where(
                DossierVersion.workspace_id == world.workspace_id
            )
        )

    # Candidate branch: no formal version may be created.
    before = await version_count()
    soft = await service.reclassify(
        ReclassifyEntry(
            workspace_id=world.workspace_id,
            target_id=candidate.id,
            new_statement_type=DossierStatementType.ASSUMPTION,
        )
    )
    assert soft["formal"] is False and await version_count() == before

    # Confirmed branch: formal edits create exactly one new version each.
    formal = await service.reclassify(
        ReclassifyEntry(
            workspace_id=world.workspace_id,
            target_id=confirmed.id,
            new_statement_type=DossierStatementType.ASSUMPTION,
        )
    )
    assert formal["formal"] is True and await version_count() == before + 1
    expired = await service.expire(
        ExpireEntry(workspace_id=world.workspace_id, target_id=confirmed.id)
    )
    assert expired["formal"] is True and await version_count() == before + 2
    # The expired entry disappears from the next snapshot.
    snapshot = await service.create_snapshot(world.case_id, workspace_id=world.workspace_id)
    assert confirmed.id not in [item.id for item in snapshot.entries]


# ---------------------------------------------------------------------------
# QA-5: tenant anti-enumeration over HTTP
# ---------------------------------------------------------------------------


async def test_qa5_foreign_and_nonexistent_resources_are_indistinguishable(
    session: AsyncSession,  # noqa: F811
) -> None:
    world_a = await seed_dossier_world(session, suffix=f"qa5a{uuid4().hex[:4]}")
    world_b = await seed_dossier_world(session, suffix=f"qa5b{uuid4().hex[:4]}")
    holder = {"context": owner_context(world_b)}
    app = build_task0405_app(session, holder, reply_provider())
    async with qa_client(app) as client:
        base_b = f"/api/workspaces/{world_b.workspace_id}"
        # Foreign (tenant A's) case via tenant B's workspace path.
        foreign = await client.get(f"{base_b}/cases/{world_a.case_id}")
        # A case id that simply does not exist.
        ghost = await client.get(f"{base_b}/cases/{uuid4()}")
        assert foreign.status_code == ghost.status_code == 404
        assert foreign.json() == ghost.json(), "denial bodies must be identical"

        # Tenant A's workspace path itself denies with the same body.
        base_a = f"/api/workspaces/{world_a.workspace_id}"
        cross = await client.get(f"{base_a}/cases/{world_a.case_id}")
        assert cross.status_code == 404
        assert cross.json() == ghost.json()

        # Candidate review surfaces deny the same way.
        foreign_candidates = await client.get(
            f"{base_b}/cases/{world_a.case_id}/candidates"
        )
        assert foreign_candidates.status_code == 404
        assert foreign_candidates.json() == ghost.json()


# ---------------------------------------------------------------------------
# QA-6: fixture provider determinism
# ---------------------------------------------------------------------------


async def test_qa6_fixture_provider_is_deterministic_across_calls() -> None:
    provider = FixtureModelProvider()
    provider.register(
        "k1", {"b": 2, "a": 1, "nested": {"y": [3, 1], "x": "值"}}
    )
    outputs = []
    for _ in range(5):
        completion = await provider.complete_structured(
            system="s",
            messages=[ModelMessage(role="user", content="k1")],
            schema=None,
            tools=None,
            request_model="fixture-deterministic",
        )
        outputs.append(completion.raw_text)
        assert completion.response_model == "fixture-deterministic"
        assert completion.tool_calls == ()
    assert len(set(outputs)) == 1, "fixture provider must be byte-identical"
    assert json.loads(outputs[0]) == {"b": 2, "a": 1, "nested": {"y": [3, 1], "x": "值"}}


# ---------------------------------------------------------------------------
# QA-7: migration lifecycle (released revision chained to Task 10)
# ---------------------------------------------------------------------------


def test_qa7_lane_migration_chained_to_task10_revision() -> None:
    """Integration release keeps Task 10 -> Task 4/5 -> decision records linear.

    The standalone QA branch originally asserted a dangling Task 10 parent before
    integration. In the release branch all migration files are present, so the
    guard now pins the exact integrated migration set and single Alembic head.
    """

    versions_dir = APP_DIR.parent / "migrations" / "versions"
    files = sorted(p.name for p in versions_dir.glob("*.py") if p.name != "__init__.py")
    assert files == [
        "0001_core_tenancy_and_dossiers.py",
        "2b2d34dacee0_add_p2w2_retrieval_funnel_downgrade.py",
        "6b246c283d7a_add_canonical_contract_foundations.py",
        "a1b2c3d4e5f6_add_case_profiles.py",
        "a3f8c2d47e19_add_canonical_simulation_graph_contract.py",
        "a4b5c6d7e8f9_harden_connector_status_enum.py",
        "a7c3e9f1b5d8_add_dossier_version_snapshots.py",
        "a9f1e2d3c4b5_add_deliberation_council.py",
        "b2c3d4e5f6a7_add_workspace_connectors.py",
        "b2c7e9d4a1f6_add_decision_maker_profiles_and_idempotency_records.py",
        "b3c5d7e9f1a2_add_workspace_invites.py",
        "b6e8f3a1d7c2_add_analysis_outputs.py",
        "c3d4e5f6a7b8_extend_connectors_model_mcp.py",
        "c4a1f0b2d9e7_add_login_rate_buckets.py",
        "c8d4e6f0a1b2_add_decision_records_reviews.py",
        "d4e6f8a0b2c4_add_mentor_and_decision_reviews.py",
        "d7e2a91c5b48_add_strategic_lens_artifacts.py",
        "e7f3a2c9d5b1_add_evidence_ledger.py",
        "f850d361ee42_harden_canonical_contract_invariants.py",
        "f9a4b7e2c8d3_add_analysis_runtime.py",
    ], "integrated release migration set must stay explicit"

    revisions: dict[str, str | None] = {}
    pattern_rev = re.compile(r"^revision(?::\s*str)?\s*=\s*['\"]([^'\"]+)['\"]", re.M)
    pattern_down = re.compile(
        r"^down_revision(?::[^=]+)?\s*=\s*(?:['\"]([^'\"]+)['\"]|None)", re.M
    )
    for name in files:
        text = (versions_dir / name).read_text(encoding="utf-8")
        revisions[pattern_rev.search(text).group(1)] = (
            pattern_down.search(text).group(1) if pattern_down.search(text) else None
        )
    assert revisions["b6e8f3a1d7c2"] == "f9a4b7e2c8d3", (
        "Task 10 migration must chain after the analysis runtime baseline"
    )
    assert revisions["a7c3e9f1b5d8"] == "b6e8f3a1d7c2", (
        "Task 4/5 migration must chain after Task 10 outputs"
    )
    assert revisions["c8d4e6f0a1b2"] == "a7c3e9f1b5d8", (
        "decision records migration must land after Task 4/5 dossier snapshots"
    )
    assert revisions["b3c5d7e9f1a2"] == "c8d4e6f0a1b2", (
        "workspace invites migration must chain after decision records"
    )
    assert revisions["d4e6f8a0b2c4"] == "b3c5d7e9f1a2", (
        "mentor reviews migration must chain after workspace invites"
    )
    heads = set(revisions) - {parent for parent in revisions.values() if parent}
    assert heads == {"a9f1e2d3c4b5"}, f"unexpected integrated Alembic heads: {heads}"


def test_qa7_lane_tables_materialise_from_metadata() -> None:
    """The lane migration a7c3e9f1b5d8 was generated from this metadata; the
    canonical tables (frozen in the Task 19A migration) plus this lane's
    single companion table must all be registered and consistent."""

    canonical = {
        "dossier_entries",
        "dossier_versions",
        "candidate_revisions",
        "case_versions",
        "conversations",
        "messages",
        "quick_analysis_results",
        "domain_events",
    }
    lane_new = {"dossier_version_snapshots"}
    assert canonical | lane_new <= set(Base.metadata.tables), (
        "all Task 4/5 tables must be registered on the shared metadata"
    )
