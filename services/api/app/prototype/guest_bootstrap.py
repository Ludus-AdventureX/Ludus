"""Guest demo bootstrap (PROTOTYPE ONLY — guest alpha, no product contract).

Builds one fully isolated demo decision scope for a freshly minted guest user:
case anchor, ready ``scenario_planning`` lens provenance, a CONFIRMED causal
graph version (4 nodes / 4 edges, converging), one strategy / scenario /
score-definition version, and one immutable decision-maker profile.

Discipline:

- every row UUID is uuid5-derived from the guest user id, so the bootstrap is
  deterministic per guest and re-entrant: an existing guest resolves to the
  exact same demo identifiers without duplicating rows;
- this module never commits — the caller owns the single transaction, so a
  failure anywhere rolls back the guest user, workspace, membership, session,
  and demo rows together;
- only existing models and the append-only profile repository write path are
  used; no migration, no simulations route, no contract change.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AnalysisRun,
    CausalGraph,
    DecisionCase,
    DecisionMakerProfile,
    DecisionSubject,
    GraphEdge,
    GraphNode,
    GraphVersion,
    ScenarioVersion,
    ScoreDefinition,
    StrategicLensArtifact,
    StrategyVersion,
)
from app.simulations.repository import SimulationInputRepository
from app.types import (
    AnalysisRunStatus,
    FormalAnalysisLevel,
    GraphVersionStatus,
    LensProducerRole,
    OriginMode,
    StrategicLensArtifactStatus,
    StrategicLensType,
)

_GUEST_NAMESPACE = uuid5(NAMESPACE_URL, "https://ludus.local/prototype/guest-alpha")
# Fixed witness timestamp: confirmation/acceptance columns stay byte-stable
# across re-entrant bootstraps of the same guest.
_BOOTSTRAP_INSTANT = datetime(2026, 7, 25, 0, 0, 0, tzinfo=timezone.utc)

PROFILE_VERSION = 1
_SCORE_DEFINITION_VERSION = "1.0.0"

# Compact converging demo graph (mirrors the simulation-alpha fixture shape).
_NODES: tuple[dict[str, Any], ...] = (
    {
        "key": "price_point",
        "label": "Launch price point",
        "type": "decision",
        "baseline": 100.0,
        "min": 50.0,
        "max": 200.0,
        "unit": "USD",
        "controllability": "controllable",
        "assumption_id": "asm-price-elasticity",
        "rationale": "Price is the only decision lever in the guest demo.",
    },
    {
        "key": "adoption_rate",
        "label": "Adoption rate",
        "type": "intermediate",
        "baseline": 0.3,
        "min": 0.0,
        "max": 1.0,
        "unit": "ratio",
        "controllability": "partially_controllable",
        "assumption_id": "asm-adoption-curve",
        "rationale": "Adoption mediates price into revenue.",
    },
    {
        "key": "annual_revenue",
        "label": "First-year revenue",
        "type": "outcome",
        "baseline": 1.2,
        "min": 0.0,
        "max": 10.0,
        "unit": "MUSD",
        "controllability": "uncontrollable",
        "assumption_id": "asm-revenue-model",
        "rationale": "Scored outcome node.",
    },
    {
        "key": "burn_rate",
        "label": "Burn rate",
        "type": "constraint",
        "baseline": 0.4,
        "min": 0.0,
        "max": 1.0,
        "unit": "ratio",
        "controllability": "partially_controllable",
        "assumption_id": "asm-burn-baseline",
        "rationale": "Constraint node guarded by the score definition.",
    },
)

_EDGES: tuple[dict[str, Any], ...] = (
    {
        "key": "price_to_adoption",
        "source": "price_point",
        "target": "adoption_rate",
        "polarity": "negative",
        "strength": 0.6,
        "delay_steps": 0,
        "claim_id": "clm-price-adoption",
        "rationale": "Higher price dampens adoption.",
    },
    {
        "key": "adoption_to_revenue",
        "source": "adoption_rate",
        "target": "annual_revenue",
        "polarity": "positive",
        "strength": 0.8,
        "delay_steps": 0,
        "claim_id": "clm-adoption-revenue",
        "rationale": "Adoption drives revenue.",
    },
    {
        "key": "price_to_revenue",
        "source": "price_point",
        "target": "annual_revenue",
        "polarity": "positive",
        "strength": 0.5,
        "delay_steps": 0,
        "claim_id": "clm-price-revenue",
        "rationale": "Unit economics improve with price.",
    },
    {
        "key": "adoption_to_burn",
        "source": "adoption_rate",
        "target": "burn_rate",
        "polarity": "negative",
        "strength": 0.3,
        "delay_steps": 1,
        "claim_id": "clm-adoption-burn",
        "rationale": "Faster adoption relieves the burn constraint.",
    },
)


@dataclass(frozen=True, slots=True)
class GuestDemoIds:
    """Deterministic per-guest demo identifiers (business identities only)."""

    case_id: UUID
    graph_id: UUID
    graph_version_id: UUID
    strategy_version_id: UUID
    scenario_version_id: UUID
    score_definition_id: UUID
    profile_id: UUID
    profile_version: int = PROFILE_VERSION


def _content_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _stable_id(user_id: UUID, kind: str) -> UUID:
    return uuid5(_GUEST_NAMESPACE, f"{user_id}:{kind}")


def derive_demo_ids(user_id: UUID) -> GuestDemoIds:
    """Pure per-guest identity derivation; also used to answer reused sessions."""

    return GuestDemoIds(
        case_id=_stable_id(user_id, "case"),
        graph_id=_stable_id(user_id, "graph"),
        graph_version_id=_stable_id(user_id, "graph-version:1"),
        strategy_version_id=_stable_id(user_id, "strategy-version:1"),
        scenario_version_id=_stable_id(user_id, "scenario-version:1"),
        score_definition_id=_stable_id(user_id, "score-definition:1"),
        profile_id=_stable_id(user_id, "profile"),
    )


async def bootstrap_guest_demo(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID,
) -> GuestDemoIds:
    """Stage the full demo scope for one guest inside the caller's transaction.

    Flush-only (never commits). Re-entrant: existing rows are detected by
    their deterministic primary keys and left untouched.
    """

    ids = derive_demo_ids(user_id)
    node_ids = {node["key"]: _stable_id(user_id, f"node:{node['key']}") for node in _NODES}
    edge_ids = {edge["key"]: _stable_id(user_id, f"edge:{edge['key']}") for edge in _EDGES}
    option_id = _stable_id(user_id, "option:a")
    subject_id = _stable_id(user_id, "subject")
    charter_id = _stable_id(user_id, "charter")
    analysis_run_id = _stable_id(user_id, "analysis-run")
    report_artifact_id = _stable_id(user_id, "report-artifact")
    lens_artifact_id = _stable_id(user_id, "lens-artifact:scenario-planning")
    scenario_id = _stable_id(user_id, "scenario")
    method = {"methodId": "hardtech-market-direction", "methodVersion": "1.1.0"}

    # 1. Case anchor (subject -> case).
    if await db.get(DecisionSubject, subject_id) is None:
        db.add(
            DecisionSubject(
                id=subject_id,
                workspace_id=workspace_id,
                name="Guest Demo Subject",
                slug="guest-demo",
                description="Prototype guest demo subject.",
                dossier_id=_stable_id(user_id, "dossier"),
            )
        )
        await db.flush()
    if await db.get(DecisionCase, ids.case_id) is None:
        db.add(
            DecisionCase(
                decision_case_id=ids.case_id,
                workspace_id=workspace_id,
                decision_subject_id=subject_id,
                title="Guest Demo Pricing Case",
                decision_question=(
                    "Which launch price point maximizes first-year revenue "
                    "without breaching the burn-rate constraint?"
                ),
                option_ids=[str(option_id)],
                charter_ids=[str(charter_id)],
                analysis_run_ids=[str(analysis_run_id)],
                report_artifact_ids=[str(report_artifact_id)],
                causal_graph_ids=[str(ids.graph_id)],
            )
        )
        await db.flush()

    # 2. Analysis run + ready scenario_planning lens (scenario provenance).
    if await db.get(AnalysisRun, analysis_run_id) is None:
        db.add(
            AnalysisRun(
                analysis_run_id=analysis_run_id,
                workspace_id=workspace_id,
                decision_case_id=ids.case_id,
                charter_id=charter_id,
                charter_version=1,
                run_manifest_id=_stable_id(user_id, "run-manifest"),
                run_manifest_hash=_content_hash({"manifest": "guest-alpha"}),
                cynefin_gate_result_id=_stable_id(user_id, "cynefin-gate-result"),
                analysis_level=FormalAnalysisLevel.FOCUSED,
                status=AnalysisRunStatus.READY,
                progress=1.0,
                origin_modes=[OriginMode.FIXTURE],
                case_version=1,
                case_snapshot_hash=_content_hash({"case": str(ids.case_id)}),
                dossier_snapshot_version=1,
                dossier_snapshot_hash=_content_hash({"dossier": str(subject_id)}),
                method_id=method["methodId"],
                method_version=method["methodVersion"],
                method_content_hash=_content_hash(method),
                idempotency_key=f"guest-alpha-bootstrap-{user_id}",
                strategic_lens_artifact_ids=[str(lens_artifact_id)],
                started_at=_BOOTSTRAP_INSTANT,
                completed_at=_BOOTSTRAP_INSTANT,
            )
        )
        await db.flush()
    if await db.get(StrategicLensArtifact, lens_artifact_id) is None:
        lens_payload = {
            "scenarios": [
                {
                    "id": "scn-baseline",
                    "name": "Baseline demand scenario",
                    "description": "Stable demand with a mild adoption tailwind.",
                }
            ]
        }
        db.add(
            StrategicLensArtifact(
                strategic_lens_artifact_id=lens_artifact_id,
                workspace_id=workspace_id,
                decision_case_id=ids.case_id,
                analysis_run_id=analysis_run_id,
                charter_id=charter_id,
                lens_type=StrategicLensType.SCENARIO_PLANNING,
                producer_role=LensProducerRole.SYNTHESIS,
                status=StrategicLensArtifactStatus.READY,
                method_id=method["methodId"],
                method_version=method["methodVersion"],
                method_content_hash=_content_hash(method),
                prompt_version="1",
                schema_version="1",
                origin_modes=[OriginMode.FIXTURE],
                content_hash=_content_hash(lens_payload),
                payload=lens_payload,
                validation_accepted_at=_BOOTSTRAP_INSTANT,
            )
        )
        await db.flush()

    # 3. Confirmed graph version with nodes/edges.
    if await db.get(CausalGraph, ids.graph_id) is None:
        db.add(
            CausalGraph(
                id=ids.graph_id,
                workspace_id=workspace_id,
                decision_case_id=ids.case_id,
                report_artifact_id=report_artifact_id,
                current_graph_version_id=ids.graph_version_id,
                title="Guest Demo Pricing Graph",
                origin_modes=[OriginMode.FIXTURE],
            )
        )
        await db.flush()
    if await db.get(GraphVersion, ids.graph_version_id) is None:
        db.add(
            GraphVersion(
                id=ids.graph_version_id,
                workspace_id=workspace_id,
                graph_id=ids.graph_id,
                decision_case_id=ids.case_id,
                case_version=1,
                source_report_artifact_id=report_artifact_id,
                version=1,
                status=GraphVersionStatus.CONFIRMED,
                origin_modes=[OriginMode.FIXTURE],
                title="Guest Demo Pricing Graph",
                content_hash=_content_hash({"nodes": _NODES, "edges": _EDGES}),
                created_by=user_id,
                confirmed_at=_BOOTSTRAP_INSTANT,
            )
        )
        await db.flush()
        for node in _NODES:
            db.add(
                GraphNode(
                    id=node_ids[node["key"]],
                    workspace_id=workspace_id,
                    graph_version_id=ids.graph_version_id,
                    label=node["label"],
                    node_type=node["type"],
                    baseline_value=node["baseline"],
                    current_value=node["baseline"],
                    min_value=node["min"],
                    max_value=node["max"],
                    unit=node["unit"],
                    normalization="linear",
                    controllability=node["controllability"],
                    authorship="generated",
                    evidence_status="assumed",
                    evidence_quality_score=0.5,
                    assumption_ids=[node["assumption_id"]],
                    rationale=node["rationale"],
                    review_status="confirmed",
                )
            )
        await db.flush()
        for edge in _EDGES:
            db.add(
                GraphEdge(
                    id=edge_ids[edge["key"]],
                    workspace_id=workspace_id,
                    graph_version_id=ids.graph_version_id,
                    source_node_id=node_ids[edge["source"]],
                    target_node_id=node_ids[edge["target"]],
                    polarity=edge["polarity"],
                    strength=edge["strength"],
                    delay_steps=edge["delay_steps"],
                    authorship="generated",
                    evidence_status="assumed",
                    relationship_quality_score=0.5,
                    rationale=edge["rationale"],
                    claim_ids=[edge["claim_id"]],
                    review_status="confirmed",
                )
            )
        await db.flush()

    # 4. Strategy / scenario / score definition versions.
    if await db.get(StrategyVersion, ids.strategy_version_id) is None:
        db.add(
            StrategyVersion(
                id=ids.strategy_version_id,
                workspace_id=workspace_id,
                graph_id=ids.graph_id,
                decision_case_id=ids.case_id,
                version=1,
                option_id=option_id,
                node_overrides={str(node_ids["price_point"]): 120.0},
                enabled_edge_ids=[],
            )
        )
        await db.flush()
    if await db.get(ScenarioVersion, ids.scenario_version_id) is None:
        db.add(
            ScenarioVersion(
                id=ids.scenario_version_id,
                workspace_id=workspace_id,
                graph_id=ids.graph_id,
                decision_case_id=ids.case_id,
                source_lens_artifact_id=lens_artifact_id,
                source_strategic_scenario_id="scn-baseline",
                scenario_id=scenario_id,
                version=1,
                name="Baseline demand scenario",
                description="Stable demand with a mild adoption tailwind.",
                default_edge_multiplier=1.0,
                edge_multipliers={},
                node_shifts={str(node_ids["adoption_rate"]): 0.05},
                strategy_survives=True,
                early_warning_signals=[],
                damping=0.85,
            )
        )
        await db.flush()
    if await db.get(ScoreDefinition, ids.score_definition_id) is None:
        mappings = [
            {
                "optionId": str(option_id),
                "outcomeNodeId": str(node_ids["annual_revenue"]),
                "goalId": "goal-growth",
                "weight": 0.7,
            }
        ]
        risks = [
            {
                "optionId": str(option_id),
                "riskNodeId": str(node_ids["burn_rate"]),
                "weight": 0.3,
            }
        ]
        rules = [
            {
                "optionId": str(option_id),
                "constraintNodeId": str(node_ids["burn_rate"]),
                "operator": "<=",
                "threshold": 0.8,
                "penalty": 0.5,
            }
        ]
        db.add(
            ScoreDefinition(
                id=ids.score_definition_id,
                workspace_id=workspace_id,
                graph_id=ids.graph_id,
                decision_case_id=ids.case_id,
                version=_SCORE_DEFINITION_VERSION,
                option_outcome_mappings=mappings,
                risk_weights=risks,
                constraint_rules=rules,
                content_hash=_content_hash({"mappings": mappings, "risks": risks, "rules": rules}),
            )
        )
        await db.flush()

    # 5. Decision-maker profile via the append-only repository write path
    # (content_hash is computed server-side; never caller-supplied).
    existing_profile = await db.scalar(
        select(DecisionMakerProfile).where(
            DecisionMakerProfile.workspace_id == workspace_id,
            DecisionMakerProfile.profile_id == ids.profile_id,
            DecisionMakerProfile.version == PROFILE_VERSION,
        )
    )
    if existing_profile is None:
        await SimulationInputRepository(db).insert_decision_maker_profile(
            workspace_id=workspace_id,
            profile_id=ids.profile_id,
            version=PROFILE_VERSION,
            user_id=user_id,
            display_name="Guest Demo Maker",
            preference_weights={"growth": 0.6, "risk": 0.4},
            risk_tolerance=0.5,
            decision_case_id=ids.case_id,
        )

    return ids
