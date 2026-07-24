"""Tenant-scoped read/insert layer for DB-backed simulations.

Every SELECT binds ``workspace_id`` (and, where the anchor exists, ``decision_case_id`` and
the exact frozen version id) inside the SQL statement itself; there is no "fetch by bare
UUID then check tenancy in Python" path. Rows are returned to the assembly layer only —
callers outside this package never receive ORM instances from here.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    DecisionCase,
    GraphEdge,
    GraphNode,
    GraphVersion,
    ScenarioVersion,
    ScoreDefinition,
    SimulationRun,
    StrategicLensArtifact,
    StrategyVersion,
)


class SimulationInputRepository:
    """Pure query layer; workspace binding is mandatory on every statement."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def case_anchor_exists(self, workspace_id: UUID, decision_case_id: UUID) -> bool:
        return bool(
            await self._db.scalar(
                select(
                    exists().where(
                        DecisionCase.workspace_id == workspace_id,
                        DecisionCase.decision_case_id == decision_case_id,
                    )
                )
            )
        )

    async def get_case(
        self, workspace_id: UUID, decision_case_id: UUID
    ) -> DecisionCase | None:
        return await self._db.scalar(
            select(DecisionCase).where(
                DecisionCase.workspace_id == workspace_id,
                DecisionCase.decision_case_id == decision_case_id,
            )
        )

    async def get_graph_version(
        self, workspace_id: UUID, decision_case_id: UUID, graph_version_id: UUID
    ) -> GraphVersion | None:
        return await self._db.scalar(
            select(GraphVersion).where(
                GraphVersion.workspace_id == workspace_id,
                GraphVersion.decision_case_id == decision_case_id,
                GraphVersion.id == graph_version_id,
            )
        )

    async def get_graph_nodes(
        self, workspace_id: UUID, graph_version_id: UUID
    ) -> list[GraphNode]:
        # Total, unique order key: this baseline has no node_key column, so the
        # primary key is the deterministic sort anchor (re-sorted again in assembly).
        rows = await self._db.scalars(
            select(GraphNode)
            .where(
                GraphNode.workspace_id == workspace_id,
                GraphNode.graph_version_id == graph_version_id,
            )
            .order_by(GraphNode.id.asc())
        )
        return list(rows.all())

    async def get_graph_edges(
        self, workspace_id: UUID, graph_version_id: UUID
    ) -> list[GraphEdge]:
        rows = await self._db.scalars(
            select(GraphEdge)
            .where(
                GraphEdge.workspace_id == workspace_id,
                GraphEdge.graph_version_id == graph_version_id,
            )
            .order_by(GraphEdge.id.asc())
        )
        return list(rows.all())

    async def get_strategy_version(
        self, workspace_id: UUID, decision_case_id: UUID, strategy_version_id: UUID
    ) -> StrategyVersion | None:
        return await self._db.scalar(
            select(StrategyVersion).where(
                StrategyVersion.workspace_id == workspace_id,
                StrategyVersion.decision_case_id == decision_case_id,
                StrategyVersion.id == strategy_version_id,
            )
        )

    async def get_scenario_version(
        self, workspace_id: UUID, decision_case_id: UUID, scenario_version_id: UUID
    ) -> ScenarioVersion | None:
        return await self._db.scalar(
            select(ScenarioVersion).where(
                ScenarioVersion.workspace_id == workspace_id,
                ScenarioVersion.decision_case_id == decision_case_id,
                ScenarioVersion.id == scenario_version_id,
            )
        )

    async def get_score_definition(
        self, workspace_id: UUID, decision_case_id: UUID, score_definition_id: UUID
    ) -> ScoreDefinition | None:
        return await self._db.scalar(
            select(ScoreDefinition).where(
                ScoreDefinition.workspace_id == workspace_id,
                ScoreDefinition.decision_case_id == decision_case_id,
                ScoreDefinition.id == score_definition_id,
            )
        )

    async def get_scenario_source_lens(
        self, workspace_id: UUID, decision_case_id: UUID, strategic_lens_artifact_id: UUID
    ) -> StrategicLensArtifact | None:
        return await self._db.scalar(
            select(StrategicLensArtifact).where(
                StrategicLensArtifact.workspace_id == workspace_id,
                StrategicLensArtifact.decision_case_id == decision_case_id,
                StrategicLensArtifact.strategic_lens_artifact_id
                == strategic_lens_artifact_id,
            )
        )

    async def insert_simulation_run(self, row: SimulationRun) -> SimulationRun:
        """Stage one fully computed, immutable result row (no partial lifecycle rows)."""

        self._db.add(row)
        await self._db.flush()
        return row
