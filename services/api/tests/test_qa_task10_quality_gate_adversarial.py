"""QA adversarial supplements for the Task 10 quality-gate battery (r1).

Red-light matrix hardening beyond the owner suite: every test here attacks an
angle the owner batch asserts from the happy side — smuggled non-bearing
evidence posing as support, a full run with ZERO lenses, ALL five producer
roles rotated, ALL five references smuggled from a foreign run, the focused
rejection firing before any lens row exists, the structural impossibility of
Validation backfilling content, idempotent replay proven at the row-count
level, and the mirror image of the no-majority-vote rule (weak opposing spam
can never outvote one strong supporting primary).
"""

from __future__ import annotations

import dataclasses

import pytest
from sqlalchemy import func, select

from app.analyses.claims import assess_claim_support
from app.analyses.quality_gate import EXPECTED_PRODUCER_BY_LENS
from app.analyses.synthesis import (
    FocusedLensPersistenceRejected,
    ReportArtifactConflict,
    ensure_lens_persistence_allowed,
)
from app.models import StrategicLensArtifact
from app.reports.models import ReportArtifact
from app.strategic_lenses.validators import LensRepairInput
from app.types import (
    EvidenceVerdict,
    FormalAnalysisLevel,
    LensProducerRole,
    StrategicLensType,
)
from tests.test_analysis_quality_gate import (
    factory,  # noqa: F401 (fixture re-export)
    healthy_subject,
    lens_payload,
    link,
    report_gate,  # noqa: F401 (fixture re-export)
    run_audit,
    seed_full_run_world,
    seed_lenses,
)
from tests.test_reports_artifacts import (
    focused_document,
    persist,
    seed_run_world,
)


# --- 1. 无证据命题: non-bearing verdicts smuggled as "support" -------------------


def test_core_claim_backed_only_by_non_bearing_links_is_blocked(report_gate):  # noqa: F811
    """lead_only/rejected links LOOK like evidence rows but must never carry a
    core claim through the gate — the adversarial cousin of the empty-links
    verbatim Step 1 test."""

    smuggled = assess_claim_support(
        "claim-core-1",
        [
            link("supporting", 0.95, EvidenceVerdict.LEAD_ONLY),
            link("supporting", 0.95, EvidenceVerdict.REJECTED),
        ],
    )
    assert smuggled.claim_support == "unsupported"
    assert smuggled.supporting_evidence_ids == ()  # non-bearing ids never leak
    result = report_gate.evaluate(
        healthy_subject(
            claim_assessments=[smuggled], core_claim_ids=frozenset({"claim-core-1"})
        )
    )
    assert result.status == "blocked"
    assert "core_claim_unsupported" in result.reason_codes
    assert not result.pdf_allowed and not result.simulation_allowed


# --- 2. full 缺 lens: zero lenses at all ----------------------------------------


async def test_full_run_with_zero_lenses_is_blocked(factory, report_gate):  # noqa: F811
    world = await seed_full_run_world(factory)
    audit = await run_audit(factory, world, referenced_artifact_ids=[])
    assert not audit.ok
    assert "strategic_lens_incomplete" in audit.reason_codes
    gated = report_gate.evaluate(
        healthy_subject(analysis_level="full", lens_set_reason_codes=audit.reason_codes)
    )
    assert gated.status == "blocked" and not gated.deliverable


# --- 3. 错 producer: ALL five roles rotated -------------------------------------


async def test_full_run_with_all_five_producer_roles_rotated_is_blocked(factory):  # noqa: F811
    rotation = {
        LensProducerRole.RESEARCH: LensProducerRole.CRITIC,
        LensProducerRole.CRITIC: LensProducerRole.SYNTHESIS,
        LensProducerRole.SYNTHESIS: LensProducerRole.RESEARCH,
    }
    world = await seed_full_run_world(factory)
    await seed_lenses(
        factory,
        world,
        overrides={
            lens: {"producer_role": rotation[EXPECTED_PRODUCER_BY_LENS[lens]]}
            for lens in StrategicLensType
        },
    )
    audit = await run_audit(factory, world)
    assert not audit.ok
    assert "strategic_lens_wrong_producer_role" in audit.reason_codes


# --- 4. 跨 Run: ALL five references from a foreign run --------------------------


async def test_full_run_with_all_references_from_foreign_run_is_blocked(factory):  # noqa: F811
    world = await seed_full_run_world(factory)
    foreign_world = await seed_full_run_world(factory)
    await seed_lenses(factory, world)  # own lenses exist and are ready...
    foreign_ids = await seed_lenses(factory, foreign_world)
    audit = await run_audit(factory, world, referenced_artifact_ids=foreign_ids)
    assert not audit.ok  # ...yet a wholesale foreign reference set still blocks
    assert "strategic_lens_reference_mismatch" in audit.reason_codes


# --- 5. focused 拒 lens: rejection fires before any lens row exists --------------


async def test_focused_rejection_fires_before_any_lens_row_exists(factory):  # noqa: F811
    world = await seed_run_world(factory, level=FormalAnalysisLevel.FOCUSED)
    ws_id, _, _, run_id = world
    with pytest.raises(FocusedLensPersistenceRejected):
        ensure_lens_persistence_allowed(FormalAnalysisLevel.FOCUSED)
    async with factory() as session:
        count = (
            await session.execute(
                select(func.count())
                .select_from(StrategicLensArtifact)
                .where(
                    StrategicLensArtifact.workspace_id == ws_id,
                    StrategicLensArtifact.analysis_run_id == run_id,
                )
            )
        ).scalar_one()
    assert count == 0  # the guard sits BEFORE the repository: nothing was written


# --- 6. Validation 零补写: structural impossibility + stored payload untouched ---


async def test_repair_inputs_structurally_cannot_carry_content(factory, report_gate):  # noqa: F811
    field_names = {field.name for field in dataclasses.fields(LensRepairInput)}
    assert field_names == {
        "lens_type",
        "owner_worker",
        "phase",
        "reason_codes",
        "findings",
        "resolved_references",
    }  # closed shape: no field can smuggle repaired or completed content
    assert "content" not in field_names and "payload" not in field_names

    world = await seed_full_run_world(factory)
    broken = lens_payload(StrategicLensType.PORTER_FIVE_FORCES)
    broken["content"]["scoreIsNotDecisionFormula"] = False
    await seed_lenses(
        factory,
        world,
        overrides={StrategicLensType.PORTER_FIVE_FORCES: {"payload": broken}},
    )
    audit = await run_audit(factory, world)
    assert "lens_behavior_failed" in audit.reason_codes

    # the stored payload is byte-identical after the audit: reported, not repaired
    ws_id, _, _, run_id = world
    async with factory() as session:
        stored = (
            await session.execute(
                select(StrategicLensArtifact.payload).where(
                    StrategicLensArtifact.workspace_id == ws_id,
                    StrategicLensArtifact.analysis_run_id == run_id,
                    StrategicLensArtifact.lens_type
                    == StrategicLensType.PORTER_FIVE_FORCES,
                )
            )
        ).scalar_one()
    assert stored == broken
    assert stored["content"]["scoreIsNotDecisionFormula"] is False


# --- 7. 幂等 hash: replay proven at the row-count level --------------------------


async def test_idempotent_replay_never_creates_a_second_row(factory):  # noqa: F811
    world = await seed_run_world(factory)
    ws_id, _, _, run_id = world
    document = focused_document()
    first_id, first_hash, _ = await persist(factory, world, document)
    replay_id, _, _ = await persist(factory, world, document)
    assert replay_id == first_id

    tampered = focused_document()
    tampered["executiveBrief"] = {
        **document["executiveBrief"],
        "decision": "An adversarially rewritten decision.",
    }
    with pytest.raises(ReportArtifactConflict):
        await persist(factory, world, tampered)

    async with factory() as session:
        rows = (
            await session.execute(
                select(ReportArtifact.id, ReportArtifact.content_hash).where(
                    ReportArtifact.workspace_id == ws_id,
                    ReportArtifact.analysis_run_id == run_id,
                )
            )
        ).all()
    assert len(rows) == 1  # replay + conflict left exactly the original row
    assert rows[0] == (first_id, first_hash)


# --- 8. 支持/反对非投票: the mirror image of the owner test ----------------------


def test_weak_opposing_spam_never_outvotes_one_strong_supporting_primary():
    links = [link("opposing", 0.1, EvidenceVerdict.ACCEPTED) for _ in range(10)]
    links.append(link("supporting", 0.9, EvidenceVerdict.ACCEPTED))
    assessment = assess_claim_support("claim-1", links)
    assert assessment.claim_support == "conflicted"  # both sides recorded separately
    assert "claim_conflicting_evidence" in assessment.reason_codes
    assert assessment.support_score >= 0.9
    assert assessment.opposition_score < assessment.support_score
    assert assessment.opposition_score < 0.9  # corroboration is not a vote count
