"""Sandbox read projections over the canonical graph contract (CCR-20260726-READ-01).

Two routers, both GET-only:

* ``router`` (relative ``/simulations/{graphId}``) — the two canonical 10-api
  rows the sandbox waits on:
  ``GET /simulations/{graphId}/versions`` (paged history) and
  ``GET /simulations/{graphId}/versions/{graphVersionId}`` (exact version with
  nodes and edges). Mounted under ``workspace_router`` next to the SIM-02A run
  surface.
* ``case_anchor_router`` — ``GET /cases/{decisionCaseId}/simulations``: the
  case→graph anchor resolution `sandboxCaseDataRouteAvailable` waits on (NEW
  canonical row adjudicated by CCR-20260726-READ-01).

Error discipline: every scope denial collapses into the uniform
``CASE_NOT_FOUND`` envelope via :func:`simulation_scope_not_found` (§8
anti-enumeration). Safe reads carry no CSRF dependency.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import CausalGraph, DecisionCase, GraphEdge, GraphNode, GraphVersion
from app.tenancy.context import WorkspaceContext, require_workspace_context

from .errors import simulation_scope_not_found

router = APIRouter(prefix="/simulations/{graphId}", tags=["simulations"])
case_anchor_router = APIRouter(tags=["simulations"])

_MAX_PAGE = 200


def _envelope(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


async def _require_graph(
    db: AsyncSession, workspace_id: UUID, graph_id: UUID
) -> CausalGraph:
    graph = (
        await db.execute(
            select(CausalGraph).where(
                CausalGraph.workspace_id == workspace_id,
                CausalGraph.id == graph_id,
            )
        )
    ).scalar_one_or_none()
    if graph is None:
        raise simulation_scope_not_found()
    return graph


def _version_summary(version: GraphVersion) -> dict[str, Any]:
    return {
        "graphVersionId": str(version.id),
        "graphId": str(version.graph_id),
        "decisionCaseId": str(version.decision_case_id),
        "version": version.version,
        "status": version.status.value,
        "title": version.title,
        "caseVersion": version.case_version,
        "branchId": str(version.branch_id) if version.branch_id else None,
        "parentVersionId": (
            str(version.parent_version_id) if version.parent_version_id else None
        ),
        "sourceGraphVersionId": (
            str(version.source_graph_version_id)
            if version.source_graph_version_id
            else None
        ),
        "sourceReportArtifactId": str(version.source_report_artifact_id),
        "contentHash": version.content_hash,
        "originModes": [mode.value for mode in version.origin_modes],
        "createdAt": version.created_at.isoformat(),
        "confirmedAt": (
            version.confirmed_at.isoformat() if version.confirmed_at else None
        ),
    }


def _node_data(node: GraphNode) -> dict[str, Any]:
    return {
        "nodeId": str(node.id),
        "label": node.label,
        "nodeType": node.node_type,
        "baselineValue": node.baseline_value,
        "currentValue": node.current_value,
        "minValue": node.min_value,
        "maxValue": node.max_value,
        "unit": node.unit,
        "normalization": node.normalization,
        "sensitivityStep": node.sensitivity_step,
        "controllability": node.controllability.value,
        "authorship": node.authorship.value,
        "evidenceStatus": node.evidence_status.value,
        "evidenceQualityScore": node.evidence_quality_score,
        "evidenceIds": list(node.evidence_ids),
        "assumptionIds": list(node.assumption_ids),
        "rationale": node.rationale,
        "reviewStatus": node.review_status,
        "editable": node.editable,
    }


def _edge_data(edge: GraphEdge) -> dict[str, Any]:
    return {
        "edgeId": str(edge.id),
        "sourceNodeId": str(edge.source_node_id),
        "targetNodeId": str(edge.target_node_id),
        "polarity": edge.polarity.value,
        "strength": edge.strength,
        "delaySteps": edge.delay_steps,
        "authorship": edge.authorship.value,
        "evidenceStatus": edge.evidence_status.value,
        "relationshipQualityScore": edge.relationship_quality_score,
        "rationale": edge.rationale,
        "claimIds": list(edge.claim_ids),
        "evidenceIds": list(edge.evidence_ids),
        "assumptionIds": list(edge.assumption_ids),
        "reviewStatus": edge.review_status,
    }


@router.get("/versions")
async def list_graph_versions(
    graph_id: UUID = Path(alias="graphId"),
    limit: int = Query(default=50, ge=1, le=_MAX_PAGE),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Paged graph-version history, newest first (canonical 10-api row)."""

    await _require_graph(db, context.workspace_id, graph_id)
    rows = (
        (
            await db.execute(
                select(GraphVersion)
                .where(
                    GraphVersion.workspace_id == context.workspace_id,
                    GraphVersion.graph_id == graph_id,
                )
                .order_by(GraphVersion.version.desc(), GraphVersion.id)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return _envelope(
        {"graphId": str(graph_id), "items": [_version_summary(row) for row in rows]}
    )


@router.get("/versions/{graphVersionId}")
async def get_graph_version(
    graph_id: UUID = Path(alias="graphId"),
    graph_version_id: UUID = Path(alias="graphVersionId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Exact immutable graph version with nodes and edges (canonical row)."""

    await _require_graph(db, context.workspace_id, graph_id)
    version = (
        await db.execute(
            select(GraphVersion).where(
                GraphVersion.workspace_id == context.workspace_id,
                GraphVersion.graph_id == graph_id,
                GraphVersion.id == graph_version_id,
            )
        )
    ).scalar_one_or_none()
    if version is None:
        # Cross-graph anchors inside the same workspace collapse identically.
        raise simulation_scope_not_found()
    nodes = (
        (
            await db.execute(
                select(GraphNode)
                .where(
                    GraphNode.workspace_id == context.workspace_id,
                    GraphNode.graph_version_id == version.id,
                )
                .order_by(GraphNode.label, GraphNode.id)
            )
        )
        .scalars()
        .all()
    )
    edges = (
        (
            await db.execute(
                select(GraphEdge)
                .where(
                    GraphEdge.workspace_id == context.workspace_id,
                    GraphEdge.graph_version_id == version.id,
                )
                .order_by(GraphEdge.id)
            )
        )
        .scalars()
        .all()
    )
    data = _version_summary(version)
    data["nodes"] = [_node_data(node) for node in nodes]
    data["edges"] = [_edge_data(edge) for edge in edges]
    return _envelope(data)


@case_anchor_router.get("/cases/{decisionCaseId}/simulations")
async def list_case_simulation_anchors(
    decision_case_id: UUID = Path(alias="decisionCaseId"),
    limit: int = Query(default=50, ge=1, le=_MAX_PAGE),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Case→graph anchor list (CCR-20260726-READ-01 §2).

    Anchors only: graph id, title, current-version pointer and the source
    report — enough for the sandbox to key the mounted graph/run reads.
    """

    case = (
        await db.execute(
            select(DecisionCase).where(
                DecisionCase.workspace_id == context.workspace_id,
                DecisionCase.decision_case_id == decision_case_id,
            )
        )
    ).scalar_one_or_none()
    if case is None:
        raise simulation_scope_not_found()
    graphs = (
        (
            await db.execute(
                select(CausalGraph)
                .where(
                    CausalGraph.workspace_id == context.workspace_id,
                    CausalGraph.decision_case_id == decision_case_id,
                )
                .order_by(CausalGraph.created_at.desc(), CausalGraph.id)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return _envelope(
        {
            "decisionCaseId": str(decision_case_id),
            "items": [
                {
                    "graphId": str(graph.id),
                    "title": graph.title,
                    "currentGraphVersionId": (
                        str(graph.current_graph_version_id)
                        if graph.current_graph_version_id
                        else None
                    ),
                    "reportArtifactId": str(graph.report_artifact_id),
                    "originModes": [mode.value for mode in graph.origin_modes],
                    "createdAt": graph.created_at.isoformat(),
                    "updatedAt": graph.updated_at.isoformat(),
                }
                for graph in graphs
            ],
        }
    )
