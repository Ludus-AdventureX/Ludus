"""Task 10 owner tests: claims, adversarial arc, formal quality gate (r1).

Red-light batch first (18-plan Task 10 Step 1): unsupported core claim blocks;
full runs block on any missing/duplicate/wrong-role/cross-run/non-ready lens;
focused lens persistence is rejected; Validation only reports and never
completes content. Then the pure-computation contracts: separated
support/opposition (no majority vote), four-category fact reconciliation,
mandatory adversarial dispositions, four orthogonal checks with the
multiplicative deliverability value, and the six-dimension profile as a pure
projection of the four checks.

DB-backed audits run against the migrated schema with a production-like
committed session (QA r2 precedent), seeding an isolated world per test.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.analyses.claims import (
    EvidenceLink,
    FactObservation,
    assess_claim_support,
    reconcile_facts,
)
from app.analyses.devils_advocate import (
    ChallengeFinding,
    evaluate_adversarial_arc,
)
from app.analyses.quality_gate import (
    EXPECTED_PRODUCER_BY_LENS,
    GateSubject,
    LogicAudit,
    ReportQualityGate,
    SynthesisAudit,
    audit_full_run_lens_set,
)
from app.analyses.repository import AnalysisRuntimeRepository
from app.analyses.synthesis import (
    FocusedLensPersistenceRejected,
    SimulationNotAllowed,
    ensure_lens_persistence_allowed,
    ensure_simulation_allowed,
)
from app.db import get_database_url
from app.models import (
    DecisionCase,
    DecisionSubject,
    StrategicLensArtifact,
    User,
    Workspace,
    WorkspaceMembership,
)
from app.strategic_lenses.repository import canonical_content_hash
from app.types import (
    AnalysisRunStatus,
    EvidenceVerdict,
    FormalAnalysisLevel,
    LensProducerRole,
    StrategicLensArtifactStatus,
    StrategicLensType,
    WorkspaceRole,
)
from tests.test_strategic_lens_validators import (
    COUNTERPARTY_FIXTURE,
    PRE_MORTEM_FIXTURE,
    load_json,
    meadows_content,
    meadows_references_wire,
    porter_content,
    porter_references_wire,
    scenario_content,
    scenario_references_wire,
)

S = AnalysisRunStatus
FULL_SET = [lens.value for lens in StrategicLensType]


# --- pure helpers --------------------------------------------------------------


def link(direction: str, strength: float, verdict: EvidenceVerdict) -> EvidenceLink:
    return EvidenceLink(
        evidence_id=f"ev-{uuid4().hex[:8]}",
        direction=direction,
        support_strength=strength,
        verdict=verdict,
        rationale="test link",
    )


def passing_arc() -> ChallengeFinding:
    return ChallengeFinding(
        challenge_id=f"ch-{uuid4().hex[:8]}",
        category="counterargument",
        severity="high",
        disposition="accepted_change",
        changed_report=True,
    )


def healthy_subject(**overrides) -> GateSubject:
    supported = assess_claim_support(
        "claim-core-1",
        [link("supporting", 0.9, EvidenceVerdict.ACCEPTED)],
    )
    values = dict(
        analysis_level="focused",
        claim_assessments=[supported],
        core_claim_ids=frozenset({"claim-core-1"}),
        adversarial=evaluate_adversarial_arc([passing_arc(), passing_arc()]),
    )
    values.update(overrides)
    return GateSubject(**values)


def structured_report_with_unsupported_core_claim() -> GateSubject:
    unsupported = assess_claim_support("claim-core-1", [])
    return healthy_subject(
        claim_assessments=[unsupported], core_claim_ids=frozenset({"claim-core-1"})
    )


@pytest.fixture()
def report_gate() -> ReportQualityGate:
    return ReportQualityGate()


# --- Step 1 red-light batch ----------------------------------------------------


def test_core_claim_without_accepted_or_conditional_evidence_is_blocked(report_gate):
    report = structured_report_with_unsupported_core_claim()
    result = report_gate.evaluate(report)
    assert result.status == "blocked"
    assert "core_claim_unsupported" in result.reason_codes


def test_focused_run_lens_persistence_is_rejected():
    with pytest.raises(FocusedLensPersistenceRejected):
        ensure_lens_persistence_allowed(FormalAnalysisLevel.FOCUSED)
    ensure_lens_persistence_allowed(FormalAnalysisLevel.FULL)  # full passes


def test_validation_reports_failure_without_writing_content(report_gate):
    """Validation 不补写: a behavior-failed lens blocks and only hands back a
    repair input naming what failed — never repaired or completed content."""

    from app.strategic_lenses.validators import ResolvedLensReferences, validate_lens_behavior

    broken = porter_content()
    broken["scoreIsNotDecisionFormula"] = False
    verdict = validate_lens_behavior(
        StrategicLensType.PORTER_FIVE_FORCES,
        broken,
        ResolvedLensReferences.from_wire(porter_references_wire()),
    )
    assert not verdict.passed
    result = report_gate.evaluate(healthy_subject(lens_verdicts=[verdict]))
    assert result.status == "blocked"
    assert "lens_behavior_failed" in result.reason_codes
    assert result.repair_inputs, "the repair input must name the failure"
    repair = result.repair_inputs[0]
    assert not hasattr(repair, "content")
    assert repair.reason_codes == verdict.reason_codes


def test_blocked_gate_disables_pdf_and_simulation(report_gate):
    result = report_gate.evaluate(structured_report_with_unsupported_core_claim())
    assert result.status == "blocked"
    assert not result.pdf_allowed
    assert not result.simulation_allowed
    with pytest.raises(SimulationNotAllowed):
        ensure_simulation_allowed(result.status)


# --- support computation (Step 2) ----------------------------------------------


def test_support_and_opposition_are_computed_separately_not_by_vote():
    # ten weak L5-grade supporting opinions vs one strong opposing primary:
    # a majority vote would say "supported"; the canonical rule says conflicted
    # and the opposition side keeps its own strength.
    links = [link("supporting", 0.1, EvidenceVerdict.ACCEPTED) for _ in range(10)]
    links.append(link("opposing", 0.9, EvidenceVerdict.ACCEPTED))
    assessment = assess_claim_support("claim-1", links)
    assert assessment.claim_support == "conflicted"
    assert assessment.opposition_score >= 0.9
    assert assessment.support_score < 0.9  # corroboration never out-votes strength


def test_non_bearing_verdicts_never_support():
    links = [
        link("supporting", 0.9, EvidenceVerdict.LEAD_ONLY),
        link("supporting", 0.9, EvidenceVerdict.REJECTED),
    ]
    assessment = assess_claim_support("claim-1", links)
    assert assessment.claim_support == "unsupported"
    assert assessment.support_score == 0.0


def test_assumption_only_claims_are_projected_as_assumption_only():
    assessment = assess_claim_support("claim-1", [], has_assumptions=True)
    assert assessment.claim_support == "assumption_only"


# --- fact reconciliation (Step 3) -----------------------------------------------


def obs(metric: str, value: float, *, period="2026-Q2", definition="revenue-gaap",
        source="a.example", claim_ids=("claim-core-1",)) -> FactObservation:
    return FactObservation(
        evidence_id=f"ev-{uuid4().hex[:8]}",
        metric=metric,
        value=value,
        unit="usd",
        period=period,
        definition=definition,
        source_domain=source,
        claim_ids=tuple(claim_ids),
    )


def test_fact_reconciliation_classifies_the_four_categories():
    outcome = reconcile_facts(
        [
            # factual conflict: same metric/period/definition, incompatible
            obs("arr", 100.0), obs("arr", 200.0, source="b.example"),
            # definition mismatch
            obs("margin", 0.5), obs("margin", 0.7, definition="margin-non-gaap",
                                     source="b.example"),
            # freshness gap
            obs("headcount", 40.0), obs("headcount", 55.0, period="2025-Q2",
                                        source="b.example"),
            # source divergence (within tolerance, different domains)
            obs("nps", 60.0), obs("nps", 61.0, source="b.example"),
        ]
    )
    categories = {finding.category for finding in outcome.findings}
    assert categories == {
        "factual_conflict",
        "definition_mismatch",
        "freshness_gap",
        "source_divergence",
    }


def test_unresolved_conflicts_ship_in_report_and_downgrade_claims():
    outcome = reconcile_facts([obs("arr", 100.0), obs("arr", 200.0, source="b.example")])
    assert outcome.unresolved, "the factual conflict is not adjudicable"
    assert "claim-core-1" in outcome.downgraded_claim_ids
    entry = outcome.unresolved[0].report_entry()
    assert entry["category"] == "factual_conflict" and entry["resolvable"] is False


# --- adversarial feedback arc (Step 4) ------------------------------------------


def finding(**overrides) -> ChallengeFinding:
    values = dict(
        challenge_id=f"ch-{uuid4().hex[:8]}",
        category="counterargument",
        severity="high",
        disposition=None,
        disposition_reason="",
        changed_report=False,
    )
    values.update(overrides)
    return ChallengeFinding(**values)


def test_important_finding_without_disposition_is_arc_violation():
    arc = evaluate_adversarial_arc([finding()])
    assert "challenge_without_disposition" in arc.reason_codes


def test_rejection_without_reason_is_arc_violation():
    arc = evaluate_adversarial_arc([finding(disposition="rejected_with_reason")])
    assert "challenge_rejection_without_reason" in arc.reason_codes


def test_fatal_flaw_returns_to_synthesis(report_gate):
    arc = evaluate_adversarial_arc(
        [finding(category="fatal_flaw", severity="critical", disposition="escalated")]
    )
    assert arc.return_to_synthesis
    result = report_gate.evaluate(healthy_subject(adversarial=arc))
    assert result.status == "blocked"
    assert result.return_to_synthesis
    assert "fatal_flaw_returns_to_synthesis" in result.reason_codes


def test_complete_arc_with_all_three_dispositions_passes():
    arc = evaluate_adversarial_arc(
        [
            finding(disposition="accepted_change", changed_report=True),
            finding(disposition="accepted_change", changed_report=True),
            finding(disposition="rejected_with_reason", disposition_reason="out of scope"),
            finding(disposition="escalated"),
        ]
    )
    assert arc.arc_complete
    assert (arc.accepted_changes, arc.rejected_with_reason, arc.escalated) == (2, 1, 1)


# --- four orthogonal checks + six-dimension projection (Step 5) -----------------


def test_gate_passes_and_multiplicative_value_only_decides_deliverability(report_gate):
    result = report_gate.evaluate(healthy_subject())
    assert result.status == "passed" and result.deliverable
    expected = 1.0
    for outcome in result.checks:
        expected *= outcome.score
    assert result.multiplicative_value == pytest.approx(expected)


def test_any_severe_failure_blocks_regardless_of_other_scores(report_gate):
    result = report_gate.evaluate(
        healthy_subject(logic=LogicAudit(recommendation_contradicted=True))
    )
    assert result.status == "blocked" and not result.deliverable
    assert "recommendation_contradicts_evidence" in result.reason_codes


def test_six_dimension_profile_is_a_projection_of_the_four_checks(report_gate):
    # severe evidence failure projects blocked evidence + blocked process
    blocked = report_gate.evaluate(structured_report_with_unsupported_core_claim())
    profile = blocked.quality_profile
    assert profile["evidenceAvailability"] == "blocked"
    assert profile["claimSupport"] == "unsupported"
    assert profile["processQuality"] == "blocked"

    # warnings project the conditional/fragile middle states
    conflicted = assess_claim_support(
        "claim-core-1",
        [
            link("supporting", 0.8, EvidenceVerdict.ACCEPTED),
            link("opposing", 0.6, EvidenceVerdict.ACCEPTED),
        ],
    )
    warned = report_gate.evaluate(
        healthy_subject(
            claim_assessments=[conflicted],
            adversarial=evaluate_adversarial_arc([finding(disposition="escalated")]),
        )
    )
    assert warned.status == "passed"
    assert warned.quality_profile["evidenceAvailability"] == "conditional"
    assert warned.quality_profile["claimSupport"] == "conflicted"
    assert warned.quality_profile["assumptionStability"] == "fragile"
    assert warned.quality_profile["processQuality"] == "warning"

    # a killed recommended strategy projects flip_detected
    flipped = report_gate.evaluate(
        healthy_subject(synthesis=SynthesisAudit(recommended_strategy_flipped=True))
    )
    assert flipped.quality_profile["strategicRobustness"] == "flip_detected"

    # weakestDimension always names one of the six canonical dimensions
    assert blocked.quality_profile["weakestDimension"] in {
        "evidence_availability",
        "claim_support",
        "assumption_stability",
        "causal_reliability",
        "strategic_robustness",
        "process_quality",
    }


def test_healthy_full_profile_is_all_green(report_gate):
    result = report_gate.evaluate(healthy_subject())
    profile = result.quality_profile
    assert profile["evidenceAvailability"] == "sufficient"
    assert profile["claimSupport"] == "supported"
    assert profile["assumptionStability"] == "stable"
    assert profile["causalReliability"] == "confirmed"
    assert profile["strategicRobustness"] == "robust"
    assert profile["processQuality"] == "passed"


# --- DB-backed full-run lens-set audit (Steps 5-6 red lights) -------------------


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def seed_full_run_world(factory, *, to_status: S = S.VALIDATING):
    """Commit a workspace + confirmed full charter + run at ``to_status``."""

    slug = f"t10-{uuid4().hex[:10]}"
    async with factory() as session:
        ws_id, user_id, subject_id, case_id = uuid4(), uuid4(), uuid4(), uuid4()
        session.add(User(id=user_id, email=f"{slug}@example.test", password_hash="x"))
        await session.flush()
        session.add(Workspace(id=ws_id, name=f"ws-{slug}", created_by_user_id=user_id))
        await session.flush()
        session.add(
            WorkspaceMembership(
                id=uuid4(), workspace_id=ws_id, user_id=user_id, role=WorkspaceRole.OWNER
            )
        )
        session.add(
            DecisionSubject(id=subject_id, workspace_id=ws_id, name=f"s-{slug}", slug=slug)
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
        repo = AnalysisRuntimeRepository(session)
        charter = await repo.create_charter_draft(
            workspace_id=ws_id,
            decision_subject_id=subject_id,
            decision_case_id=case_id,
            case_version=1,
            case_snapshot_hash="sha256:case",
            analysis_level=FormalAnalysisLevel.FULL,
            decision_question="enter the rescue market?",
            dossier_snapshot_version=1,
            dossier_snapshot_hash="sha256:dossier",
            method_id="hardtech-market-direction",
            method_version="1.1.0",
            method_content_hash="sha256:method",
            formal_analysis_allowed=True,
            required_strategic_lens_types=list(FULL_SET),
            allowed_connector_ids=["exa"],
            budget={"max_model_calls": 20},
        )
        await repo.submit_charter(ws_id, charter.id)
        await repo.confirm_charter(ws_id, charter.id)
        run, created = await repo.create_queued_run(
            workspace_id=ws_id,
            charter_id=charter.id,
            idempotency_key=f"run-{uuid4().hex[:12]}",
            run_manifest_hash="sha256:manifest",
            cynefin_gate_result_id=uuid4(),
        )
        assert created
        run_id = run.analysis_run_id
        chain = [S.PLANNING, S.RETRIEVING, S.ANALYZING, S.CRITICIZING, S.SYNTHESIZING,
                 S.VALIDATING, S.READY]
        for stage in chain:
            if stage is S.READY and to_status is not S.READY:
                break
            await repo.transition(
                ws_id, run_id, stage, quality_gate_passed=(stage is S.READY)
            )
            if stage is to_status:
                break
        await session.commit()
    return ws_id, case_id, charter.id, run_id


def lens_payload(lens_type: StrategicLensType) -> dict:
    """Behavior-passing canonical payload per lens (validator golden samples)."""

    if lens_type is StrategicLensType.PORTER_FIVE_FORCES:
        references, content = porter_references_wire(), porter_content()
        phase = "research_interpretation"
    elif lens_type is StrategicLensType.PRE_MORTEM:
        fixture = load_json(PRE_MORTEM_FIXTURE)
        references, content = fixture["references"], fixture["content"]
        phase = fixture["phase"]
    elif lens_type is StrategicLensType.COUNTERPARTY_RESPONSE_MATRIX:
        fixture = load_json(COUNTERPARTY_FIXTURE)
        references, content = fixture["references"], fixture["content"]
        phase = fixture["phase"]
    elif lens_type is StrategicLensType.SCENARIO_PLANNING:
        references, content = scenario_references_wire(), scenario_content()
        phase = "synthesis_alignment"
    else:
        references, content = meadows_references_wire(), meadows_content()
        phase = "synthesis_alignment"
    return {
        "lensType": lens_type.value,
        "sourceSkillVersion": "1.0.0",
        "phase": phase,
        "references": references,
        "researchRequests": [],
        "content": content,
    }


def lens_row(
    *,
    ws_id: UUID,
    case_id: UUID,
    run_id: UUID,
    charter_id: UUID,
    lens_type: StrategicLensType,
    payload: dict | None = None,
    status: StrategicLensArtifactStatus = StrategicLensArtifactStatus.READY,
    producer_role: LensProducerRole | None = None,
) -> StrategicLensArtifact:
    document = payload if payload is not None else lens_payload(lens_type)
    return StrategicLensArtifact(
        strategic_lens_artifact_id=uuid4(),
        workspace_id=ws_id,
        decision_case_id=case_id,
        analysis_run_id=run_id,
        charter_id=charter_id,
        lens_type=lens_type,
        producer_role=(
            producer_role if producer_role is not None else EXPECTED_PRODUCER_BY_LENS[lens_type]
        ),
        status=status,
        method_id="hardtech-market-direction",
        method_version="1.1.0",
        method_content_hash="sha256:method",
        prompt_version="1.1.0",
        schema_version="1.1.0",
        origin_modes=[],
        content_hash=canonical_content_hash(document),
        payload=document,
        claim_refs=list(document["references"].get("claimIds", [])),
        evidence_refs=list(document["references"].get("evidenceIds", [])),
        assumption_refs=list(document["references"].get("assumptionIds", [])),
        validation_accepted_at=(
            datetime.now(timezone.utc)
            if status is StrategicLensArtifactStatus.READY
            else None
        ),
    )


async def seed_lenses(factory, world, *, skip=None, overrides=None) -> list[str]:
    ws_id, case_id, charter_id, run_id = world
    overrides = overrides or {}
    ids: list[str] = []
    async with factory() as session:
        for lens_type in StrategicLensType:
            if skip is not None and lens_type is skip:
                continue
            row = lens_row(
                ws_id=ws_id, case_id=case_id, run_id=run_id, charter_id=charter_id,
                lens_type=lens_type, **overrides.get(lens_type, {}),
            )
            session.add(row)
            ids.append(str(row.strategic_lens_artifact_id))
        await session.commit()
    return ids


async def run_audit(factory, world, **kwargs):
    ws_id, case_id, charter_id, run_id = world
    async with factory() as session:
        return await audit_full_run_lens_set(
            session,
            workspace_id=ws_id,
            decision_case_id=case_id,
            analysis_run_id=run_id,
            charter_id=charter_id,
            frozen_lens_types=FULL_SET,
            **kwargs,
        )


async def test_full_run_with_five_ready_behavior_passing_lenses_is_ok(factory):
    world = await seed_full_run_world(factory)
    ids = await seed_lenses(factory, world)
    audit = await run_audit(factory, world, referenced_artifact_ids=ids)
    assert audit.ok, (audit.reason_codes, audit.findings)
    assert len(audit.behavior_verdicts) == 5
    assert all(verdict.passed for verdict in audit.behavior_verdicts)


async def test_full_run_missing_any_lens_is_blocked(factory, report_gate):
    world = await seed_full_run_world(factory)
    await seed_lenses(factory, world, skip=StrategicLensType.PRE_MORTEM)
    audit = await run_audit(factory, world)
    assert "strategic_lens_incomplete" in audit.reason_codes
    gated = report_gate.evaluate(
        healthy_subject(analysis_level="full", lens_set_reason_codes=audit.reason_codes)
    )
    assert gated.status == "blocked"


async def test_full_run_non_ready_lens_is_blocked(factory):
    world = await seed_full_run_world(factory)
    await seed_lenses(
        factory, world,
        overrides={
            StrategicLensType.MEADOWS_LEVERAGE_POINTS: {
                "status": StrategicLensArtifactStatus.DRAFT
            }
        },
    )
    audit = await run_audit(factory, world)
    assert "strategic_lens_incomplete" in audit.reason_codes


async def test_full_run_wrong_producer_role_is_blocked(factory):
    world = await seed_full_run_world(factory)
    await seed_lenses(
        factory, world,
        overrides={
            StrategicLensType.PORTER_FIVE_FORCES: {"producer_role": LensProducerRole.CRITIC}
        },
    )
    audit = await run_audit(factory, world)
    assert "strategic_lens_wrong_producer_role" in audit.reason_codes


async def test_full_run_cross_run_reference_is_blocked(factory):
    world = await seed_full_run_world(factory)
    other_world = await seed_full_run_world(factory)
    ids = await seed_lenses(factory, world)
    foreign = await seed_lenses(factory, other_world)
    referenced = ids[:4] + foreign[:1]  # one id smuggled from another run
    audit = await run_audit(factory, world, referenced_artifact_ids=referenced)
    assert "strategic_lens_reference_mismatch" in audit.reason_codes


async def test_full_run_duplicate_reference_is_blocked(factory):
    world = await seed_full_run_world(factory)
    ids = await seed_lenses(factory, world)
    duplicated = ids[:4] + ids[:1]  # five entries, only four distinct artifacts
    audit = await run_audit(factory, world, referenced_artifact_ids=duplicated)
    assert "strategic_lens_reference_mismatch" in audit.reason_codes


async def test_schema_passing_behavior_failing_lens_never_reaches_ready(factory, report_gate):
    """Porter payload passes the pack JSON schema but violates the behavior
    contract (score used as a decision formula) — the run must block and no
    completed replacement content may appear anywhere."""

    world = await seed_full_run_world(factory)
    broken = lens_payload(StrategicLensType.PORTER_FIVE_FORCES)
    broken["content"]["scoreIsNotDecisionFormula"] = False
    await seed_lenses(
        factory, world,
        overrides={StrategicLensType.PORTER_FIVE_FORCES: {"payload": broken}},
    )
    audit = await run_audit(factory, world)
    assert "lens_behavior_failed" in audit.reason_codes
    gated = report_gate.evaluate(
        healthy_subject(
            analysis_level="full",
            lens_verdicts=audit.behavior_verdicts,
            lens_set_reason_codes=audit.reason_codes,
        )
    )
    assert gated.status == "blocked"
    assert gated.repair_inputs  # Validation reports; it never repairs
