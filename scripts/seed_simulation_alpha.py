"""Idempotent seeder for the simulation-alpha demo scope (SIM_ALPHA_SEED_SMOKE_FAST).

Seeds — in FK order — a demo user, workspace + owner membership, decision
subject/case anchor, a confirmed causal graph version (nodes + edges), one
strategy/scenario/score-definition version, and one immutable decision-maker
profile, then prints a JSON summary of every identity the smoke script needs.

Discipline:

- every row UUID is uuid5-derived from ``fixtures/simulation-alpha/seed/
  simulation_alpha.json``, so re-running converges on the same rows (idempotent);
- the demo password comes ONLY from ``SIMULATION_ALPHA_DEMO_PASSWORD`` and is
  never written to the repository or printed;
- no product code or migrations are touched: only existing models/repository
  write paths are used.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPOSITORY_ROOT / "services" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

FIXTURE_PATH = REPOSITORY_ROOT / "fixtures" / "simulation-alpha" / "seed" / "simulation_alpha.json"
PASSWORD_ENV = "SIMULATION_ALPHA_DEMO_PASSWORD"
NAMESPACE = uuid5(NAMESPACE_URL, "https://ludus.local/fixtures/simulation-alpha")
# Fixed witness timestamp so re-seeded confirmation/acceptance rows stay stable.
SEED_INSTANT = datetime(2026, 7, 25, 0, 0, 0, tzinfo=timezone.utc)


def stable_id(kind: str) -> UUID:
    return uuid5(NAMESPACE, kind)


def load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def content_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def derive_ids(fixture: dict[str, Any]) -> dict[str, Any]:
    """Pure derivation of every seeded identity; shared with the smoke script."""

    node_ids = {node["key"]: stable_id(f"node:{node['key']}") for node in fixture["graph"]["nodes"]}
    edge_ids = {edge["key"]: stable_id(f"edge:{edge['key']}") for edge in fixture["graph"]["edges"]}
    option_ids = {key: stable_id(f"option:{key}") for key in fixture["case"]["optionKeys"]}
    return {
        "user_id": stable_id("user"),
        "workspace_id": stable_id("workspace"),
        "membership_id": stable_id("membership"),
        "subject_id": stable_id("subject"),
        "dossier_id": stable_id("dossier"),
        "case_id": stable_id("case"),
        "charter_id": stable_id("charter"),
        "analysis_run_id": stable_id("analysis-run"),
        "run_manifest_id": stable_id("run-manifest"),
        "cynefin_gate_result_id": stable_id("cynefin-gate-result"),
        "report_artifact_id": stable_id("report-artifact"),
        "lens_artifact_id": stable_id("lens-artifact:scenario-planning"),
        "graph_id": stable_id("graph"),
        "graph_version_id": stable_id("graph-version:1"),
        "strategy_version_id": stable_id("strategy-version:option-a:1"),
        "scenario_version_id": stable_id("scenario-version:1"),
        "scenario_id": stable_id("scenario"),
        "score_definition_id": stable_id("score-definition:1"),
        "profile_id": stable_id("profile"),
        "node_ids": node_ids,
        "edge_ids": edge_ids,
        "option_ids": option_ids,
    }


def require_demo_password() -> str:
    password = os.environ.get(PASSWORD_ENV, "")
    if len(password) < 8:
        raise SystemExit(
            f"{PASSWORD_ENV} must be set in the environment (>= 8 chars); "
            "the demo password is never stored in the repository."
        )
    return password


async def seed(fixture: dict[str, Any], password: str) -> dict[str, Any]:
    # Imported lazily so DATABASE_URL/POSTGRES_* are read from the caller's env.
    from sqlalchemy import select

    from app.auth.passwords import hash_password, verify_password
    from app.db import async_session_factory
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
        User,
        Workspace,
        WorkspaceMembership,
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
        WorkspaceRole,
    )

    ids = derive_ids(fixture)
    method = fixture["method"]
    fixture_hash = content_hash(fixture)

    async with async_session_factory() as db:
        # 1. Demo user (idempotent by email; password re-aligned to the env value).
        user = await db.scalar(select(User).where(User.email == fixture["demoEmail"]))
        if user is None:
            user = User(
                id=ids["user_id"],
                email=fixture["demoEmail"],
                password_hash=hash_password(password),
            )
            db.add(user)
            await db.flush()
        elif not verify_password(user.password_hash, password):
            user.password_hash = hash_password(password)
            await db.flush()

        # 2. Workspace + owner membership.
        if await db.get(Workspace, ids["workspace_id"]) is None:
            db.add(
                Workspace(
                    id=ids["workspace_id"],
                    name=fixture["workspaceName"],
                    created_by_user_id=user.id,
                )
            )
            await db.flush()
        membership = await db.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == ids["workspace_id"],
                WorkspaceMembership.user_id == user.id,
            )
        )
        if membership is None:
            db.add(
                WorkspaceMembership(
                    id=ids["membership_id"],
                    workspace_id=ids["workspace_id"],
                    user_id=user.id,
                    role=WorkspaceRole.OWNER,
                    capabilities=[],
                )
            )
            await db.flush()

        # 3. Case anchor (subject -> case).
        if await db.get(DecisionSubject, ids["subject_id"]) is None:
            db.add(
                DecisionSubject(
                    id=ids["subject_id"],
                    workspace_id=ids["workspace_id"],
                    name=fixture["subject"]["name"],
                    slug=fixture["subject"]["slug"],
                    description=fixture["subject"]["description"],
                    dossier_id=ids["dossier_id"],
                )
            )
            await db.flush()
        if await db.get(DecisionCase, ids["case_id"]) is None:
            db.add(
                DecisionCase(
                    decision_case_id=ids["case_id"],
                    workspace_id=ids["workspace_id"],
                    decision_subject_id=ids["subject_id"],
                    title=fixture["case"]["title"],
                    decision_question=fixture["case"]["decisionQuestion"],
                    option_ids=[str(ids["option_ids"][key]) for key in fixture["case"]["optionKeys"]],
                    charter_ids=[str(ids["charter_id"])],
                    analysis_run_ids=[str(ids["analysis_run_id"])],
                    report_artifact_ids=[str(ids["report_artifact_id"])],
                    causal_graph_ids=[str(ids["graph_id"])],
                )
            )
            await db.flush()

        # 3b. Analysis-run + ready scenario_planning lens: scenario provenance
        # required by the simulation service's frozen-input validation.
        if await db.get(AnalysisRun, ids["analysis_run_id"]) is None:
            db.add(
                AnalysisRun(
                    analysis_run_id=ids["analysis_run_id"],
                    workspace_id=ids["workspace_id"],
                    decision_case_id=ids["case_id"],
                    charter_id=ids["charter_id"],
                    charter_version=1,
                    run_manifest_id=ids["run_manifest_id"],
                    run_manifest_hash=content_hash({"manifest": "simulation-alpha"}),
                    cynefin_gate_result_id=ids["cynefin_gate_result_id"],
                    analysis_level=FormalAnalysisLevel.FOCUSED,
                    status=AnalysisRunStatus.READY,
                    progress=1.0,
                    origin_modes=[OriginMode.FIXTURE],
                    case_version=1,
                    case_snapshot_hash=fixture_hash,
                    dossier_snapshot_version=1,
                    dossier_snapshot_hash=fixture_hash,
                    method_id=method["methodId"],
                    method_version=method["methodVersion"],
                    method_content_hash=content_hash(method),
                    idempotency_key="simulation-alpha-seed-analysis-run",
                    strategic_lens_artifact_ids=[str(ids["lens_artifact_id"])],
                    started_at=SEED_INSTANT,
                    completed_at=SEED_INSTANT,
                )
            )
            await db.flush()
        if await db.get(StrategicLensArtifact, ids["lens_artifact_id"]) is None:
            lens_payload = {
                "scenarios": [
                    {
                        "id": fixture["scenario"]["sourceStrategicScenarioId"],
                        "name": fixture["scenario"]["name"],
                        "description": fixture["scenario"]["description"],
                    }
                ]
            }
            db.add(
                StrategicLensArtifact(
                    strategic_lens_artifact_id=ids["lens_artifact_id"],
                    workspace_id=ids["workspace_id"],
                    decision_case_id=ids["case_id"],
                    analysis_run_id=ids["analysis_run_id"],
                    charter_id=ids["charter_id"],
                    lens_type=StrategicLensType.SCENARIO_PLANNING,
                    producer_role=LensProducerRole.SYNTHESIS,
                    status=StrategicLensArtifactStatus.READY,
                    method_id=method["methodId"],
                    method_version=method["methodVersion"],
                    method_content_hash=content_hash(method),
                    prompt_version="1",
                    schema_version="1",
                    origin_modes=[OriginMode.FIXTURE],
                    content_hash=content_hash(lens_payload),
                    payload=lens_payload,
                    validation_accepted_at=SEED_INSTANT,
                )
            )
            await db.flush()

        # 4 + 5. Confirmed graph version with nodes/edges.
        if await db.get(CausalGraph, ids["graph_id"]) is None:
            db.add(
                CausalGraph(
                    id=ids["graph_id"],
                    workspace_id=ids["workspace_id"],
                    decision_case_id=ids["case_id"],
                    report_artifact_id=ids["report_artifact_id"],
                    title=fixture["graph"]["title"],
                    origin_modes=[OriginMode.FIXTURE],
                )
            )
            await db.flush()
        if await db.get(GraphVersion, ids["graph_version_id"]) is None:
            db.add(
                GraphVersion(
                    id=ids["graph_version_id"],
                    workspace_id=ids["workspace_id"],
                    graph_id=ids["graph_id"],
                    decision_case_id=ids["case_id"],
                    case_version=1,
                    source_report_artifact_id=ids["report_artifact_id"],
                    version=1,
                    status=GraphVersionStatus.CONFIRMED,
                    origin_modes=[OriginMode.FIXTURE],
                    title=fixture["graph"]["title"],
                    content_hash=content_hash(fixture["graph"]),
                    created_by=user.id,
                    confirmed_at=SEED_INSTANT,
                )
            )
            await db.flush()
            for node in fixture["graph"]["nodes"]:
                db.add(
                    GraphNode(
                        id=ids["node_ids"][node["key"]],
                        workspace_id=ids["workspace_id"],
                        graph_version_id=ids["graph_version_id"],
                        label=node["label"],
                        node_type=node["type"],
                        baseline_value=node["baseline"],
                        current_value=node["baseline"],
                        min_value=node["min"],
                        max_value=node["max"],
                        unit=node["unit"],
                        normalization=node["normalization"],
                        controllability=node["controllability"],
                        authorship=node["authorship"],
                        evidence_status=node["evidenceStatus"],
                        evidence_quality_score=node["evidenceQualityScore"],
                        assumption_ids=list(node["assumptionIds"]),
                        rationale=node["rationale"],
                        review_status=node["status"],
                    )
                )
            await db.flush()
            for edge in fixture["graph"]["edges"]:
                db.add(
                    GraphEdge(
                        id=ids["edge_ids"][edge["key"]],
                        workspace_id=ids["workspace_id"],
                        graph_version_id=ids["graph_version_id"],
                        source_node_id=ids["node_ids"][edge["sourceKey"]],
                        target_node_id=ids["node_ids"][edge["targetKey"]],
                        polarity=edge["polarity"],
                        strength=edge["strength"],
                        delay_steps=edge["delaySteps"],
                        authorship=edge["authorship"],
                        evidence_status=edge["evidenceStatus"],
                        relationship_quality_score=edge["relationshipQualityScore"],
                        rationale=edge["rationale"],
                        claim_ids=list(edge["claimIds"]),
                        review_status=edge["status"],
                    )
                )
            await db.flush()
        graph = await db.get(CausalGraph, ids["graph_id"])
        if graph is not None and graph.current_graph_version_id != ids["graph_version_id"]:
            graph.current_graph_version_id = ids["graph_version_id"]
            await db.flush()

        # 6. Strategy / scenario / score definition versions.
        if await db.get(StrategyVersion, ids["strategy_version_id"]) is None:
            db.add(
                StrategyVersion(
                    id=ids["strategy_version_id"],
                    workspace_id=ids["workspace_id"],
                    graph_id=ids["graph_id"],
                    decision_case_id=ids["case_id"],
                    version=fixture["strategy"]["version"],
                    option_id=ids["option_ids"][fixture["strategy"]["optionKey"]],
                    node_overrides={
                        str(ids["node_ids"][key]): value
                        for key, value in fixture["strategy"]["nodeOverrides"].items()
                    },
                    enabled_edge_ids=[],
                )
            )
            await db.flush()
        if await db.get(ScenarioVersion, ids["scenario_version_id"]) is None:
            scenario = fixture["scenario"]
            db.add(
                ScenarioVersion(
                    id=ids["scenario_version_id"],
                    workspace_id=ids["workspace_id"],
                    graph_id=ids["graph_id"],
                    decision_case_id=ids["case_id"],
                    source_lens_artifact_id=ids["lens_artifact_id"],
                    source_strategic_scenario_id=scenario["sourceStrategicScenarioId"],
                    scenario_id=ids["scenario_id"],
                    version=scenario["version"],
                    name=scenario["name"],
                    description=scenario["description"],
                    default_edge_multiplier=scenario["defaultEdgeMultiplier"],
                    edge_multipliers={
                        str(ids["edge_ids"][key]): value
                        for key, value in scenario["edgeMultipliers"].items()
                    },
                    node_shifts={
                        str(ids["node_ids"][key]): value
                        for key, value in scenario["nodeShifts"].items()
                    },
                    strategy_survives=scenario["strategySurvives"],
                    early_warning_signals=[],
                    damping=scenario["damping"],
                )
            )
            await db.flush()
        if await db.get(ScoreDefinition, ids["score_definition_id"]) is None:
            score = fixture["scoreDefinition"]
            mappings = [
                {
                    "optionId": str(ids["option_ids"][item["optionKey"]]),
                    "outcomeNodeId": str(ids["node_ids"][item["outcomeNodeKey"]]),
                    "goalId": item["goalId"],
                    "weight": item["weight"],
                }
                for item in score["optionOutcomeMappings"]
            ]
            risks = [
                {
                    "optionId": str(ids["option_ids"][item["optionKey"]]),
                    "riskNodeId": str(ids["node_ids"][item["riskNodeKey"]]),
                    "weight": item["weight"],
                }
                for item in score["riskWeights"]
            ]
            rules = [
                {
                    "optionId": str(ids["option_ids"][item["optionKey"]]),
                    "constraintNodeId": str(ids["node_ids"][item["constraintNodeKey"]]),
                    "operator": item["operator"],
                    "threshold": item["threshold"],
                    "penalty": item["penalty"],
                }
                for item in score["constraintRules"]
            ]
            db.add(
                ScoreDefinition(
                    id=ids["score_definition_id"],
                    workspace_id=ids["workspace_id"],
                    graph_id=ids["graph_id"],
                    decision_case_id=ids["case_id"],
                    version=score["version"],
                    option_outcome_mappings=mappings,
                    risk_weights=risks,
                    constraint_rules=rules,
                    content_hash=content_hash(
                        {"mappings": mappings, "risks": risks, "rules": rules}
                    ),
                )
            )
            await db.flush()

        # 7. Decision-maker profile (append-only repository write path only).
        repository = SimulationInputRepository(db)
        profile_row = await db.scalar(
            select(DecisionMakerProfile).where(
                DecisionMakerProfile.workspace_id == ids["workspace_id"],
                DecisionMakerProfile.profile_id == ids["profile_id"],
                DecisionMakerProfile.version == fixture["profile"]["version"],
            )
        )
        if profile_row is None:
            profile_row = await repository.insert_decision_maker_profile(
                workspace_id=ids["workspace_id"],
                profile_id=ids["profile_id"],
                version=fixture["profile"]["version"],
                user_id=user.id,
                display_name=fixture["profile"]["displayName"],
                preference_weights=fixture["profile"]["preferenceWeights"],
                risk_tolerance=fixture["profile"]["riskTolerance"],
                decision_case_id=ids["case_id"],
            )

        await db.commit()

    # 8. JSON summary (no secrets).
    return {
        "demoEmail": fixture["demoEmail"],
        "workspaceId": str(ids["workspace_id"]),
        "caseId": str(ids["case_id"]),
        "graphId": str(ids["graph_id"]),
        "versionIds": {
            "graphVersionId": str(ids["graph_version_id"]),
            "strategyVersionId": str(ids["strategy_version_id"]),
            "scenarioVersionId": str(ids["scenario_version_id"]),
            "scoreDefinitionId": str(ids["score_definition_id"]),
            "scoreDefinitionVersion": fixture["scoreDefinition"]["version"],
        },
        "profile": {
            "profileId": str(ids["profile_id"]),
            "version": fixture["profile"]["version"],
        },
        "lensArtifactId": str(ids["lens_artifact_id"]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the simulation-alpha demo scope (idempotent).")
    parser.add_argument("--fixture", type=Path, default=FIXTURE_PATH, help="seed fixture JSON path")
    args = parser.parse_args(argv)
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    password = require_demo_password()
    summary = asyncio.run(seed(fixture, password))
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
