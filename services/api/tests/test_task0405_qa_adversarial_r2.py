"""Task 4/5 adversarial QA battery r2 (independent QA lane, ≥6 gates).

Attacks the candidate `codex/task-04-05-backend-r1 @ a51a4f9` from angles the
owner battery does not cover:

ADV-1  Propose/Reject negative matrix — rejected + pending candidates leave
       zero formal traces and never surface in any snapshot payload.
ADV-2  Losing confirm (stale base 409) leaves ZERO partial writes.
ADV-3  Snapshot rows + companion detail are byte-stable across later formal
       edits; companion rows stay append-only (one per version).
ADV-4  Cross-tenant anti-enumeration on the WRITE path (confirm/reject on a
       foreign candidate) — uniform 404, byte-identical to a ghost id.
ADV-5  Opt-out messages ("不要记住"/"临时想法"/"off the record") produce zero
       candidate rows AND zero extraction model calls (call-count audited).
ADV-6  Hostile envelope: a provider that injects `reasoning_content` into its
       payload — nothing containing that key may reach any committed row
       (messages/candidates/domain_events JSONB serialization scan) and the
       migrated database itself has no reasoning-like column.
ADV-7  complete_structured_checked: empty first response repairs EXACTLY once
       and succeeds; two invalid responses raise after EXACTLY two calls
       (no third attempt, no free-text salvage).
ADV-8  Fixture determinism under adversarial key ordering / unicode payloads.

Zero real network. Uses the owner harness (ASGI transport, fixture provider).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.model_provider import (
    EmptyModelContentError,
    FixtureModelProvider,
    ModelMessage,
    SchemaValidationError,
    StructuredCompletion,
    complete_structured_checked,
)
from app.dossiers.models import DossierVersionSnapshot
from app.dossiers.service import (
    DossierService,
    ProposeEntry,
    RejectEntry,
    ReclassifyEntry,
)
from app.models import (
    CandidateRevision,
    CaseVersion,
    DomainEvent,
    DossierEntry,
    DossierVersion,
    Message,
)
from app.types import CandidateSourceType, DossierStatementType

from test_dossier_versions import (
    seed_dossier_world,
    session,  # noqa: F401  (fixture re-export)
)
from test_task0405_qa_battery import build_task0405_app, owner_context, qa_client


def _proposal(content: str, statement_type: str = "constraint") -> dict:
    return {
        "operation": "add",
        "entry": {
            "scope": "case",
            "statementType": statement_type,
            "content": content,
            "sourceType": "ai_candidate",
        },
    }


async def _propose(service: DossierService, world, content: str, statement_type: str = "constraint"):
    return await service.propose(
        ProposeEntry(
            workspace_id=world.workspace_id,
            decision_subject_id=world.subject_id,
            decision_case_id=world.case_id,
            proposals=[_proposal(content, statement_type)],
            source_type=CandidateSourceType.CONVERSATION,
            source_id=uuid4(),
            base_dossier_version=1,
            base_case_version=1,
        )
    )


async def _count(db: AsyncSession, model, workspace_id) -> int:
    return await db.scalar(
        select(func.count()).select_from(model).where(model.workspace_id == workspace_id)
    )


# ---------------------------------------------------------------------------
# ADV-1: Propose/Reject negative matrix — zero formal traces
# ---------------------------------------------------------------------------


async def test_adv1_rejected_and_pending_candidates_leave_zero_formal_traces(
    session: AsyncSession,  # noqa: F811
) -> None:
    world = await seed_dossier_world(session)
    service = DossierService(session, workspace_id=world.workspace_id)

    entries_before = await _count(session, DossierEntry, world.workspace_id)
    versions_before = await _count(session, DossierVersion, world.workspace_id)
    case_versions_before = await _count(session, CaseVersion, world.workspace_id)

    kept: list[str] = []
    for statement_type in ("fact", "assumption", "judgment", "constraint"):
        candidate = await _propose(
            service, world, f"候选-{statement_type}-绝不入正式", statement_type
        )
        kept.append(str(candidate.id))
    rejected = await service.reject(
        RejectEntry(workspace_id=world.workspace_id, candidate_revision_id=kept[0])
    )
    assert str(rejected.id) == kept[0]

    # The whole matrix wrote candidates + audit events ONLY.
    assert await _count(session, DossierEntry, world.workspace_id) == entries_before
    assert await _count(session, DossierVersion, world.workspace_id) == versions_before
    assert await _count(session, CaseVersion, world.workspace_id) == case_versions_before

    # A formal snapshot built afterwards must not carry ANY candidate content.
    await service.add_entry(
        world.subject_id, "唯一正式条目", "constraint", "confirmed", scope="subject"
    )
    snapshot = await service.create_snapshot(world.case_id, workspace_id=world.workspace_id)
    snapshot_ids = {str(item.id) for item in snapshot.entries}
    assert snapshot_ids.isdisjoint(set(kept)), "candidate ids leaked into a snapshot"
    companion_payload = json.dumps(
        [
            row.entries
            for row in (
                await session.execute(
                    select(DossierVersionSnapshot).where(
                        DossierVersionSnapshot.workspace_id == world.workspace_id
                    )
                )
            ).scalars()
        ],
        ensure_ascii=False,
    )
    assert "绝不入正式" not in companion_payload


# ---------------------------------------------------------------------------
# ADV-2: losing confirm leaves zero partial writes
# ---------------------------------------------------------------------------


async def test_adv2_stale_confirm_409_writes_nothing(
    session: AsyncSession,  # noqa: F811
) -> None:
    world = await seed_dossier_world(session)
    service = DossierService(session, workspace_id=world.workspace_id)
    first = await _propose(service, world, "赢家条目")
    second = await _propose(service, world, "输家条目")

    holder = {"context": owner_context(world)}
    app = build_task0405_app(session, holder, FixtureModelProvider())
    async with qa_client(app) as client:
        base = f"/api/workspaces/{world.workspace_id}"
        winner = await client.post(
            f"{base}/cases/{world.case_id}/candidates/{first.id}/confirm",
            json={"baseDossierVersion": 1, "baseCaseVersion": 1},
        )
        assert winner.status_code == 200, winner.text

        entries_after_win = await _count(session, DossierEntry, world.workspace_id)
        versions_after_win = await _count(session, DossierVersion, world.workspace_id)
        case_versions_after_win = await _count(session, CaseVersion, world.workspace_id)
        events_after_win = await _count(session, DomainEvent, world.workspace_id)

        loser = await client.post(
            f"{base}/cases/{world.case_id}/candidates/{second.id}/confirm",
            json={"baseDossierVersion": 1, "baseCaseVersion": 1},
        )
        assert loser.status_code == 409
        assert loser.json()["error"]["code"] == "DOSSIER_VERSION_CONFLICT"

    # The losing request must be a pure no-op on every persisted surface.
    assert await _count(session, DossierEntry, world.workspace_id) == entries_after_win
    assert await _count(session, DossierVersion, world.workspace_id) == versions_after_win
    assert await _count(session, CaseVersion, world.workspace_id) == case_versions_after_win
    assert await _count(session, DomainEvent, world.workspace_id) == events_after_win
    loser_row = await session.get(CandidateRevision, second.id)
    assert loser_row.status.value == "pending", "loser candidate must stay reviewable"


# ---------------------------------------------------------------------------
# ADV-3: snapshot + companion byte-stability across later formal edits
# ---------------------------------------------------------------------------


async def test_adv3_existing_snapshots_are_byte_stable_after_later_edits(
    session: AsyncSession,  # noqa: F811
) -> None:
    world = await seed_dossier_world(session)
    service = DossierService(session, workspace_id=world.workspace_id)
    entry = await service.add_entry(
        world.subject_id, "初始正式条目", "constraint", "confirmed", scope="subject"
    )
    first_snapshot = await service.create_snapshot(
        world.case_id, workspace_id=world.workspace_id
    )

    def snapshot_state():
        return session.execute(
            select(
                DossierVersion.version,
                DossierVersion.snapshot_hash,
                DossierVersionSnapshot.entries,
            )
            .join(
                DossierVersionSnapshot,
                DossierVersionSnapshot.dossier_version_id == DossierVersion.id,
            )
            .where(DossierVersion.workspace_id == world.workspace_id)
            .order_by(DossierVersion.version)
        )

    before = [tuple(row) for row in (await snapshot_state()).all()]
    frozen = json.dumps(before[:1], ensure_ascii=False, sort_keys=True, default=str)

    # Formal edit AFTER the snapshot: creates NEW versions, never rewrites old.
    await service.reclassify(
        ReclassifyEntry(
            workspace_id=world.workspace_id,
            target_id=entry.id,
            new_statement_type=DossierStatementType.ASSUMPTION,
        )
    )
    await service.create_snapshot(world.case_id, workspace_id=world.workspace_id)

    after = [tuple(row) for row in (await snapshot_state()).all()]
    assert len(after) > len(before), "formal edit must append a new version"
    refrozen = json.dumps(after[:1], ensure_ascii=False, sort_keys=True, default=str)
    assert refrozen == frozen, "an existing snapshot row was rewritten"

    # Companion discipline: exactly one write-once row per snapshotted version.
    per_version = await session.execute(
        select(
            DossierVersionSnapshot.dossier_version_id,
            func.count(),
        )
        .where(DossierVersionSnapshot.workspace_id == world.workspace_id)
        .group_by(DossierVersionSnapshot.dossier_version_id)
    )
    assert all(count == 1 for _, count in per_version.all())
    assert first_snapshot.entries, "snapshot projection must expose its entries"


# ---------------------------------------------------------------------------
# ADV-4: anti-enumeration on the WRITE path (confirm/reject foreign candidate)
# ---------------------------------------------------------------------------


async def test_adv4_write_path_denials_are_byte_identical(
    session: AsyncSession,  # noqa: F811
) -> None:
    world_a = await seed_dossier_world(session, suffix=f"adv4a{uuid4().hex[:4]}")
    world_b = await seed_dossier_world(session, suffix=f"adv4b{uuid4().hex[:4]}")
    service_a = DossierService(session, workspace_id=world_a.workspace_id)
    foreign_candidate = await _propose(service_a, world_a, "他租户的候选")

    holder = {"context": owner_context(world_b)}
    app = build_task0405_app(session, holder, FixtureModelProvider())
    async with qa_client(app) as client:
        base_b = f"/api/workspaces/{world_b.workspace_id}"
        confirm_payload = {"baseDossierVersion": 1, "baseCaseVersion": 1}

        # Foreign case id + foreign candidate id, via tenant B's own workspace.
        foreign = await client.post(
            f"{base_b}/cases/{world_a.case_id}/candidates/{foreign_candidate.id}/confirm",
            json=confirm_payload,
        )
        ghost = await client.post(
            f"{base_b}/cases/{uuid4()}/candidates/{uuid4()}/confirm",
            json=confirm_payload,
        )
        assert foreign.status_code == ghost.status_code == 404
        assert foreign.content == ghost.content, "write-path denials must be identical"

        # Reject path denies the same way.
        foreign_reject = await client.post(
            f"{base_b}/cases/{world_a.case_id}/candidates/{foreign_candidate.id}/reject",
            json={},
        )
        ghost_reject = await client.post(
            f"{base_b}/cases/{uuid4()}/candidates/{uuid4()}/reject", json={}
        )
        assert foreign_reject.status_code == ghost_reject.status_code == 404
        assert foreign_reject.content == ghost_reject.content

    # And the foreign candidate is untouched.
    row = await session.get(CandidateRevision, foreign_candidate.id)
    assert row.status.value == "pending"


# ---------------------------------------------------------------------------
# ADV-5: opt-out => zero candidates AND zero extraction model calls
# ---------------------------------------------------------------------------


@dataclass
class CountingProvider(FixtureModelProvider):
    calls: list[str] = field(default_factory=list)

    async def complete_structured(self, **kwargs: Any) -> StructuredCompletion:
        messages: Sequence[ModelMessage] = kwargs.get("messages") or ()
        self.calls.append(messages[-1].content if messages else "")
        return await super().complete_structured(**kwargs)


@pytest.mark.parametrize("marker", ["这只是临时想法，先不定。", "不要记住这句话。", "keep this off the record please"])
async def test_adv5_opt_out_produces_zero_candidates_and_zero_extraction_calls(
    session: AsyncSession,  # noqa: F811
    marker: str,
) -> None:
    world = await seed_dossier_world(session)
    provider = CountingProvider()
    provider.register(marker, {"assistantMessage": "好的，本句不入档案。"})
    holder = {"context": owner_context(world)}
    app = build_task0405_app(session, holder, provider)

    async with qa_client(app) as client:
        base = f"/api/workspaces/{world.workspace_id}"
        response = await client.post(
            f"{base}/cases/{world.case_id}/messages",
            json={"message": marker, "proposeStructuredUpdates": True},
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["candidateRevisionId"] is None

    assert await _count(session, CandidateRevision, world.workspace_id) == 0
    # Exactly the reply call — the extractor short-circuits before any model IO.
    assert len(provider.calls) == 1, f"unexpected model calls: {provider.calls}"


# ---------------------------------------------------------------------------
# ADV-6: hostile envelope — injected reasoning_content never persists
# ---------------------------------------------------------------------------


async def test_adv6_injected_reasoning_content_never_reaches_any_row(
    session: AsyncSession,  # noqa: F811
) -> None:
    world = await seed_dossier_world(session)
    message = "目标是在 9 个月现金窗口内验证真实需求。"
    hostile_envelope = {
        "assistantMessage": "已记录。",
        "reasoning_content": "LEAKED-CHAIN-OF-THOUGHT",
        "candidates": [
            {
                "statementType": "constraint",
                "content": "现金窗口为9个月",
                "scope": "case",
                "reasoning_content": "LEAKED-NESTED-COT",
            }
        ],
        "decisionQuestions": [],
    }
    provider = FixtureModelProvider()
    provider.register(message, hostile_envelope)
    holder = {"context": owner_context(world)}
    app = build_task0405_app(session, holder, provider)

    async with qa_client(app) as client:
        base = f"/api/workspaces/{world.workspace_id}"
        response = await client.post(
            f"{base}/cases/{world.case_id}/messages",
            json={"message": message, "proposeStructuredUpdates": True},
        )
        assert response.status_code == 200, response.text
        assert "reasoning_content" not in response.text
        assert "LEAKED" not in response.text

    # Serialize every persisted JSONB / text surface this flow can touch.
    surfaces: list[str] = []
    for row in (
        await session.execute(
            select(Message).where(Message.workspace_id == world.workspace_id)
        )
    ).scalars():
        surfaces.append(json.dumps(
            {
                "content": row.content,
                "token_metadata": row.token_metadata,
                "cost_metadata": row.cost_metadata,
            },
            ensure_ascii=False,
            default=str,
        ))
    for row in (
        await session.execute(
            select(CandidateRevision.proposals).where(
                CandidateRevision.workspace_id == world.workspace_id
            )
        )
    ).all():
        surfaces.append(json.dumps(row[0], ensure_ascii=False, default=str))
    for row in (
        await session.execute(
            select(DomainEvent.payload).where(
                DomainEvent.workspace_id == world.workspace_id
            )
        )
    ).all():
        surfaces.append(json.dumps(row[0], ensure_ascii=False, default=str))

    assert surfaces, "the flow must have persisted rows to audit"
    blob = "\n".join(surfaces)
    assert "reasoning_content" not in blob, "hostile envelope key persisted"
    assert "LEAKED" not in blob, "hostile envelope value persisted"

    # DB angle (not ORM): the migrated schema has no reasoning-like column.
    columns = await session.execute(
        text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND column_name ILIKE '%reason%'"
        )
    )
    offending = [
        (table, column)
        for table, column in columns.all()
        if "reasoning" in column.lower()
    ]
    assert offending == [], f"reasoning-like columns in DB schema: {offending}"


# ---------------------------------------------------------------------------
# ADV-7: empty-content / invalid-schema repair budget is EXACTLY one retry
# ---------------------------------------------------------------------------


@dataclass
class ScriptedProvider:
    """Returns a scripted sequence of payloads; counts every call."""

    script: list[Mapping[str, Any]]
    calls: int = 0
    name: str = "scripted"
    supports_structured_output: bool = True

    async def complete_structured(self, **kwargs: Any) -> StructuredCompletion:
        payload = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        return StructuredCompletion(
            content=payload,
            raw_text=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            request_model="scripted",
            response_model="scripted",
            finish_reason="stop",
        )

    async def probe(self):  # pragma: no cover - protocol completeness
        raise AssertionError("probe must not run in unit tests")


_SCHEMA = {
    "type": "object",
    "required": ["assistantMessage"],
    "properties": {"assistantMessage": {"type": "string"}},
}


async def test_adv7_empty_then_valid_repairs_exactly_once() -> None:
    provider = ScriptedProvider(script=[{}, {"assistantMessage": "ok"}])
    completion = await complete_structured_checked(
        provider,
        system="s",
        messages=[ModelMessage(role="user", content="hi")],
        schema=_SCHEMA,
        request_model="scripted",
    )
    assert completion.content["assistantMessage"] == "ok"
    assert provider.calls == 2, "empty content must trigger exactly one repair"


async def test_adv7_two_invalid_responses_fail_after_exactly_two_calls() -> None:
    provider = ScriptedProvider(
        script=[{"assistantMessage": 42}, {"assistantMessage": ["still", "wrong"]}]
    )
    with pytest.raises(SchemaValidationError) as excinfo:
        await complete_structured_checked(
            provider,
            system="s",
            messages=[ModelMessage(role="user", content="hi")],
            schema=_SCHEMA,
            request_model="scripted",
        )
    assert provider.calls == 2, "budget is one repair retry, never a third call"
    assert excinfo.value.findings, "typed failure must carry machine findings"


async def test_adv7_two_empty_responses_raise_empty_content_error() -> None:
    provider = ScriptedProvider(script=[{}, {}])
    with pytest.raises(EmptyModelContentError):
        await complete_structured_checked(
            provider,
            system="s",
            messages=[ModelMessage(role="user", content="hi")],
            schema=_SCHEMA,
            request_model="scripted",
        )
    assert provider.calls == 2


# ---------------------------------------------------------------------------
# ADV-8: fixture determinism under adversarial payload shapes
# ---------------------------------------------------------------------------


async def test_adv8_fixture_determinism_under_adversarial_payloads() -> None:
    provider = FixtureModelProvider()
    payload = {
        "z": "末",
        "a": {"嵌套": [3, 1, 2], "空": None},
        "M": ["混合", 1, True],
    }
    provider.register("advkey", payload)
    outputs = set()
    for _ in range(7):
        completion = await provider.complete_structured(
            system="s",
            messages=[ModelMessage(role="user", content="advkey")],
            schema=None,
            tools=None,
            request_model="x",
        )
        outputs.add(completion.raw_text)
        assert "reasoning_content" not in completion.raw_text
    assert len(outputs) == 1, "fixture output must be byte-identical across calls"
    assert json.loads(next(iter(outputs))) == payload
