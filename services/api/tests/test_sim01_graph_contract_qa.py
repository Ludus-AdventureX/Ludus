"""QA regressions for CCR-20260724-SIM-01 (qa_release-owned).

Covers ORM/DB negative regressions (cross-workspace frozen refs, edge
same-version discipline, graph-version confirmation rules, lens-artifact
tenancy, score-definition hygiene), canonical wire-schema validation, and
Python/PostgreSQL enum exactness. Skips cleanly on trees without the SIM-01
contract. Known gaps are tracked as xfail probes with QA finding ids.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio

pytest.importorskip("app.simulations.schemas", reason="SIM-01 not delivered yet")

from pydantic import ValidationError
from sqlalchemy import String, insert, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError, StatementError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

from app.db import Base, get_database_url
from app.models import (
    GraphEdge,
    GraphNode,
    GraphVersion,
    ScenarioVersion,
    ScoreDefinition,
    SimulationRun,
)
from app.simulations import schemas as wire
from app.types import (
    ConstraintComparison,
    EdgePolarity,
    FactorAuthorship,
    FactorControllability,
    FactorEvidenceStatus,
    GraphBranchStatus,
    GraphVersionStatus,
    NodeType,
)

from tests.test_models import (
    seed_case,
    seed_simulation_reference_stack,
    seed_subject_pair,
    seed_user_and_workspaces,
)


@pytest_asyncio.fixture
async def db() -> AsyncIterator[AsyncConnection]:
    engine = create_async_engine(get_database_url(), poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            yield connection
        finally:
            await transaction.rollback()
    await engine.dispose()


async def _two_workspace_stacks(db: AsyncConnection) -> tuple[dict, dict, Any, Any]:
    """Full legal SIM reference stacks in two different workspaces."""

    _, ws_a, ws_b = await seed_user_and_workspaces(db)
    subject_a, _ = await seed_subject_pair(db, ws_a)
    case_a = await seed_case(db, ws_a, subject_a)
    subject_b, _ = await seed_subject_pair(db, ws_b)
    case_b = await seed_case(db, ws_b, subject_b)
    stack_a = await seed_simulation_reference_stack(db, ws_a, case_a)
    stack_b = await seed_simulation_reference_stack(db, ws_b, case_b)
    stack_a["ws"], stack_a["case"] = ws_a, case_a
    stack_b["ws"], stack_b["case"] = ws_b, case_b
    return stack_a, stack_b, ws_a, ws_b


def _run_values(stack: dict) -> dict:
    return {
        "id": uuid4(),
        "workspace_id": stack["ws"],
        "decision_case_id": stack["case"],
        "graph_id": stack["graph"],
        "graph_version_id": stack["graph_version"],
        "strategy_version_id": stack["strategy_version"],
        "scenario_version_id": stack["scenario_version"],
        "score_definition_id": stack["score_definition"],
        "score_definition_version": "1.0.0",
        "decision_maker_profile_id": uuid4(),
        "decision_maker_profile_version": 1,
        "risk_tolerance": 0.5,
        "engine_version": "1.0.0",
        "scenario_id": uuid4(),
        "simulation_mode": "formal",
        "epsilon": 0.001,
        "max_steps": 20,
        "steps": 10,
        "input_hash": "sha256:qa-sim01",
        "node_results": {},
        "option_scores": [],
        "top_drivers": [],
        "recommendation_shift": "No change",
        "convergence_status": "converged",
        "origin_modes": ["fixture"],
    }


def _node_values(workspace_id, graph_version_id) -> dict:
    return {
        "id": uuid4(),
        "workspace_id": workspace_id,
        "graph_version_id": graph_version_id,
        "label": "QA node",
        "node_type": "outcome",
        "baseline_value": 0.5,
        "current_value": 0.5,
        "min_value": 0.0,
        "max_value": 1.0,
        "normalization": "linear",
        "controllability": FactorControllability.CONTROLLABLE,
        "authorship": FactorAuthorship.GENERATED,
        "evidence_status": FactorEvidenceStatus.ASSUMED,
        "evidence_quality_score": 0.5,
        "evidence_ids": [],
        "assumption_ids": ["assumption-1"],
        "rationale": "QA probe node",
        "review_status": "draft",
        "editable": True,
    }


def _edge_values(workspace_id, graph_version_id, source_id, target_id) -> dict:
    return {
        "id": uuid4(),
        "workspace_id": workspace_id,
        "graph_version_id": graph_version_id,
        "source_node_id": source_id,
        "target_node_id": target_id,
        "polarity": EdgePolarity.POSITIVE,
        "strength": 0.5,
        "delay_steps": 0,
        "authorship": FactorAuthorship.GENERATED,
        "evidence_status": FactorEvidenceStatus.ASSUMED,
        "relationship_quality_score": 0.5,
        "rationale": "QA probe edge",
        "claim_ids": ["claim-1"],
        "evidence_ids": [],
        "assumption_ids": [],
        "review_status": "draft",
    }


async def _expect_rejected(db: AsyncConnection, statement) -> None:
    savepoint = await db.begin_nested()
    with pytest.raises((IntegrityError, DBAPIError, StatementError)):
        await db.execute(statement)
    await savepoint.rollback()


# ---------------------------------------------------------------------------
# 五: enum and schema exactness
# ---------------------------------------------------------------------------


def test_python_enums_are_exact() -> None:
    assert {e.value for e in GraphVersionStatus} == {"draft", "confirmed", "archived"}
    assert {e.value for e in EdgePolarity} == {"positive", "negative"}
    assert {e.value for e in FactorAuthorship} == {
        "generated",
        "user_added",
        "user_modified",
    }
    assert {e.value for e in FactorEvidenceStatus} == {
        "supported",
        "conditional",
        "assumed",
        "unknown",
    }
    assert {e.value for e in FactorControllability} == {
        "controllable",
        "partially_controllable",
        "uncontrollable",
    }
    assert {e.value for e in GraphBranchStatus} == {"active", "archived"}
    # canonical 06-data-model ConstraintRule.operator: five symbols incl. "=".
    assert {e.value for e in ConstraintComparison} == {">", ">=", "<", "<=", "="}


async def test_pg_enums_are_exact_and_constraint_comparison_has_no_pg_enum(
    db: AsyncConnection,
) -> None:
    rows = (
        await db.execute(
            text(
                "SELECT t.typname, array_agg(e.enumlabel ORDER BY e.enumsortorder) "
                "FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid "
                "WHERE t.typname IN ('graph_version_status','edge_polarity',"
                "'factor_authorship','factor_evidence_status',"
                "'factor_controllability','graph_branch_status') "
                "GROUP BY t.typname"
            )
        )
    ).all()
    labels = {name: set(values) for name, values in rows}
    assert set(labels) == {
        "graph_version_status",
        "edge_polarity",
        "factor_authorship",
        "factor_evidence_status",
        "factor_controllability",
        "graph_branch_status",
    }, "exactly six new PG enums"
    assert labels["graph_version_status"] == {e.value for e in GraphVersionStatus}
    assert labels["edge_polarity"] == {e.value for e in EdgePolarity}
    assert labels["factor_authorship"] == {e.value for e in FactorAuthorship}
    assert labels["factor_evidence_status"] == {e.value for e in FactorEvidenceStatus}
    assert labels["factor_controllability"] == {e.value for e in FactorControllability}
    assert labels["graph_branch_status"] == {e.value for e in GraphBranchStatus}

    missing = (
        await db.execute(
            text("SELECT count(*) FROM pg_type WHERE typname = 'constraint_comparison'")
        )
    ).scalar_one()
    assert missing == 0, "ConstraintComparison must stay JSONB/wire-only"


def test_node_type_reuse_and_review_status_column_shape() -> None:
    node_table = Base.metadata.tables["graph_nodes"]
    assert isinstance(node_table.c.node_type.type, String), (
        "graph_nodes.node_type is a CHECK-constrained string, not a PG enum"
    )
    assert "review_status" in node_table.c and "status" not in node_table.c
    edge_table = Base.metadata.tables["graph_edges"]
    assert "review_status" in edge_table.c and "status" not in edge_table.c
    # wire keeps `status`; ORM keeps `review_status`
    assert "status" in wire.CausalNode.model_fields
    assert "status" in wire.CausalEdge.model_fields
    assert "review_status" not in wire.CausalNode.model_fields
    # NodeType is the reused canonical enum on the wire
    assert wire.CausalNode.model_fields["type"].annotation is NodeType
    # causal_graphs.current_graph_version_id is a service-validated pointer, no FK
    graph_table = Base.metadata.tables["causal_graphs"]
    assert not list(graph_table.c.current_graph_version_id.foreign_keys)
    # scenario_versions has no risk_tolerance column by contract
    assert "risk_tolerance" not in Base.metadata.tables["scenario_versions"].c


# ---------------------------------------------------------------------------
# 三 A: simulation_runs frozen refs reject real-but-foreign targets
# ---------------------------------------------------------------------------


async def test_simulation_run_frozen_refs_reject_cross_workspace_targets(
    db: AsyncConnection,
) -> None:
    stack_a, stack_b, _, _ = await _two_workspace_stacks(db)
    baseline = _run_values(stack_a)
    await db.execute(insert(SimulationRun).values(baseline))

    for field, foreign in (
        ("graph_version_id", stack_b["graph_version"]),
        ("strategy_version_id", stack_b["strategy_version"]),
        ("scenario_version_id", stack_b["scenario_version"]),
        ("score_definition_id", stack_b["score_definition"]),
    ):
        attack = {**_run_values(stack_a), field: foreign}
        await _expect_rejected(db, insert(SimulationRun).values(attack))


# ---------------------------------------------------------------------------
# 三 B: graph edge same-version / same-workspace discipline
# ---------------------------------------------------------------------------


async def _second_graph_version(db: AsyncConnection, stack: dict):
    return (
        await db.execute(
            insert(GraphVersion)
            .values(
                id=uuid4(),
                workspace_id=stack["ws"],
                graph_id=stack["graph"],
                decision_case_id=stack["case"],
                case_version=1,
                source_report_artifact_id=uuid4(),
                version=2,
                status="draft",
                provenance=[],
                origin_modes=["fixture"],
                title="QA graph v2",
                content_hash="sha256:graph-v2",
                created_by=uuid4(),
            )
            .returning(GraphVersion.id)
        )
    ).scalar_one()


async def test_graph_edge_same_version_and_workspace_discipline(
    db: AsyncConnection,
) -> None:
    stack_a, stack_b, _, _ = await _two_workspace_stacks(db)
    version_1 = stack_a["graph_version"]
    version_2 = await _second_graph_version(db, stack_a)

    async def _node(version_id, workspace=None):
        values = _node_values(workspace or stack_a["ws"], version_id)
        return (
            await db.execute(insert(GraphNode).values(values).returning(GraphNode.id))
        ).scalar_one()

    node_v1_a = await _node(version_1)
    node_v1_b = await _node(version_1)
    node_v2 = await _node(version_2)
    node_ws_b = await _node(stack_b["graph_version"], workspace=stack_b["ws"])

    # legal edge inside one version
    await db.execute(
        insert(GraphEdge).values(
            _edge_values(stack_a["ws"], version_1, node_v1_a, node_v1_b)
        )
    )
    # source from another version of the same graph
    await _expect_rejected(
        db,
        insert(GraphEdge).values(
            _edge_values(stack_a["ws"], version_1, node_v2, node_v1_b)
        ),
    )
    # target from another version
    await _expect_rejected(
        db,
        insert(GraphEdge).values(
            _edge_values(stack_a["ws"], version_1, node_v1_a, node_v2)
        ),
    )
    # source/target real but owned by another workspace
    await _expect_rejected(
        db,
        insert(GraphEdge).values(
            _edge_values(stack_a["ws"], version_1, node_ws_b, node_v1_b)
        ),
    )
    await _expect_rejected(
        db,
        insert(GraphEdge).values(
            _edge_values(stack_b["ws"], stack_b["graph_version"], node_v1_a, node_ws_b)
        ),
    )


async def test_graph_edge_self_loop_is_rejected(db: AsyncConnection) -> None:
    stack_a, _, _, _ = await _two_workspace_stacks(db)
    node = (
        await db.execute(
            insert(GraphNode)
            .values(_node_values(stack_a["ws"], stack_a["graph_version"]))
            .returning(GraphNode.id)
        )
    ).scalar_one()
    await _expect_rejected(
        db,
        insert(GraphEdge).values(
            _edge_values(stack_a["ws"], stack_a["graph_version"], node, node)
        ),
    )


# ---------------------------------------------------------------------------
# 三 C: graph version confirmation rules
# ---------------------------------------------------------------------------


async def test_graph_version_confirmation_rules(db: AsyncConnection) -> None:
    stack_a, _, _, _ = await _two_workspace_stacks(db)

    def _version_values(version: int, status: str, confirmed_at=None) -> dict:
        return {
            "id": uuid4(),
            "workspace_id": stack_a["ws"],
            "graph_id": stack_a["graph"],
            "decision_case_id": stack_a["case"],
            "case_version": 1,
            "source_report_artifact_id": uuid4(),
            "version": version,
            "status": status,
            "provenance": [],
            "origin_modes": ["fixture"],
            "title": f"QA graph v{version}",
            "content_hash": f"sha256:graph-v{version}",
            "created_by": uuid4(),
            "confirmed_at": confirmed_at,
        }

    # confirmed without confirmed_at -> CHECK rejection
    await _expect_rejected(
        db, insert(GraphVersion).values(_version_values(10, "confirmed"))
    )
    # multiple confirmed versions of one graph are the history model
    now = datetime.now(timezone.utc)
    await db.execute(insert(GraphVersion).values(_version_values(11, "confirmed", now)))
    await db.execute(insert(GraphVersion).values(_version_values(12, "confirmed", now)))
    confirmed = (
        await db.execute(
            select(GraphVersion.id).where(
                GraphVersion.graph_id == stack_a["graph"],
                GraphVersion.status == GraphVersionStatus.CONFIRMED,
            )
        )
    ).all()
    assert len(confirmed) >= 3, "seed + two more confirmed versions coexist"
    # no erroneous confirmed partial unique index exists
    indexes = (
        await db.execute(
            text("SELECT indexdef FROM pg_indexes WHERE tablename = 'graph_versions'")
        )
    ).scalars()
    assert not [d for d in indexes if "confirmed" in d.lower()], (
        "there must be no confirmed partial unique index; latest-version "
        "ordering is a contract rule, not a DB current pointer"
    )


# ---------------------------------------------------------------------------
# 三 D: scenario source lens artifact tenancy
# ---------------------------------------------------------------------------


async def test_scenario_source_lens_artifact_tenancy(db: AsyncConnection) -> None:
    stack_a, stack_b, _, _ = await _two_workspace_stacks(db)
    values = {
        "id": uuid4(),
        "workspace_id": stack_a["ws"],
        "graph_id": stack_a["graph"],
        "decision_case_id": stack_a["case"],
        "source_lens_artifact_id": stack_b["lens_artifact"],  # real, foreign
        "source_strategic_scenario_id": "scenario-frame-x",
        "scenario_id": uuid4(),
        "version": 2,
        "name": "QA foreign lens",
        "description": "must fail",
        "default_edge_multiplier": 1.0,
        "edge_multipliers": {},
        "node_shifts": {},
        "strategy_survives": True,
        "early_warning_signals": [],
        "damping": 0.5,
    }
    await _expect_rejected(db, insert(ScenarioVersion).values(values))
    # same workspace stays legal
    await db.execute(
        insert(ScenarioVersion).values(
            {**values, "source_lens_artifact_id": stack_a["lens_artifact"]}
        )
    )


# ---------------------------------------------------------------------------
# 三 E: score definition hygiene
# ---------------------------------------------------------------------------


async def test_score_definition_content_hash_not_empty(db: AsyncConnection) -> None:
    stack_a, _, _, _ = await _two_workspace_stacks(db)
    values = {
        "id": uuid4(),
        "workspace_id": stack_a["ws"],
        "graph_id": stack_a["graph"],
        "decision_case_id": stack_a["case"],
        "version": "1.0.1",
        "option_outcome_mappings": [],
        "risk_weights": [],
        "constraint_rules": [],
        "content_hash": "",
    }
    await _expect_rejected(db, insert(ScoreDefinition).values(values))


def test_constraint_rule_wire_validates_operator_and_threshold() -> None:
    base = {
        "optionId": "option-1",
        "constraintNodeId": "node-1",
        "operator": ">=",
        "threshold": 0.5,
        "penalty": 1.0,
    }
    assert wire.ConstraintRule.model_validate(base).operator is ConstraintComparison.GE
    with pytest.raises(ValidationError):
        wire.ConstraintRule.model_validate({**base, "operator": "!="})
    with pytest.raises(ValidationError):
        wire.ConstraintRule.model_validate({**base, "threshold": float("nan")})
    with pytest.raises(ValidationError):
        wire.ConstraintRule.model_validate({**base, "penalty": -1})
