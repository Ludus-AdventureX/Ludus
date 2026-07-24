"""Graph construction helpers: from-report draft builder, confirmation, and the canonical
spherical-robot confirmed fixture graph.

Per ``09``: ``from-report`` may only create an immutable ``draft`` GraphVersion; a confirmed
version is produced only after an explicit per-node / per-edge bulk review. Confirmed edges
must carry traceable claims. The spherical-robot fixture is the P0 golden graph used to
verify positive/negative propagation, delay, clipping, hard constraints, determinism and the
procurement-driven recommendation flip.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.types import NodeType

from .domain import (
    CausalEdge,
    CausalNode,
    Comparison,
    ConstraintRule,
    Controllability,
    EarlyWarningSignal,
    EdgePolarity,
    ElementStatus,
    EvidenceStatus,
    GraphInvariantError,
    GraphVersion,
    GraphVersionStatus,
    Normalization,
    OptionOutcomeMapping,
    RiskWeight,
    ScenarioVersion,
    ScoreDefinition,
    StrategyVersion,
)

RESCUE_PILOT = "rescue_pilot"
CONTINUE_RESEARCH = "continue_research"
HOME_SERVICE = "home_service"

SPHERICAL_ROBOT_RISK_TOLERANCE = 0.5


# --- from-report draft + confirmation ----------------------------------------------------


def build_from_report(nodes: tuple[CausalNode, ...], edges: tuple[CausalEdge, ...]) -> GraphVersion:
    """Wrap report-derived nodes/edges into an immutable DRAFT graph version.

    Every node and edge is forced to ``draft`` — a ``from-report`` graph can never be
    auto-confirmed. Assumption-only edges are retained as draft (their non-empty
    ``assumption_ids`` are enforced by :class:`CausalEdge`), while edges with no
    claim/evidence/assumption are rejected upstream by the edge invariant.
    """

    draft_nodes = tuple(replace(node, status=ElementStatus.DRAFT) for node in nodes)
    draft_edges = tuple(replace(edge, status=ElementStatus.DRAFT) for edge in edges)
    return GraphVersion(
        id="graphver_from_report_draft",
        graph_id="graph_from_report",
        status=GraphVersionStatus.DRAFT,
        nodes=draft_nodes,
        edges=draft_edges,
    )


def confirm_graph_version(
    draft: GraphVersion,
    *,
    version_id: str,
    confirm_node_ids: frozenset[str],
    confirm_edge_ids: frozenset[str],
    conditional_edge_ids: frozenset[str] = frozenset(),
) -> GraphVersion:
    """Produce a new immutable CONFIRMED graph version from an explicit bulk review.

    Nodes/edges not listed are rejected (excluded from propagation but preserved for audit
    by keeping them with a ``rejected`` status). Confirming an edge without traceable claims
    is refused, honoring the "confirmed edges require claims" invariant.
    """

    if draft.status != GraphVersionStatus.DRAFT:
        raise GraphInvariantError("only draft graph versions can be confirmed")

    new_nodes = tuple(
        replace(
            node,
            status=ElementStatus.CONFIRMED if node.id in confirm_node_ids else ElementStatus.REJECTED,
        )
        for node in draft.nodes
    )

    new_edges = []
    for edge in draft.edges:
        if edge.id in conditional_edge_ids:
            new_edges.append(replace(edge, status=ElementStatus.CONDITIONAL))
        elif edge.id in confirm_edge_ids:
            if not edge.claim_ids:
                raise GraphInvariantError(
                    f"edge {edge.id}: cannot confirm without traceable claimIds"
                )
            new_edges.append(replace(edge, status=ElementStatus.CONFIRMED))
        else:
            new_edges.append(replace(edge, status=ElementStatus.REJECTED))

    return GraphVersion(
        id=version_id,
        graph_id=draft.graph_id,
        status=GraphVersionStatus.CONFIRMED,
        nodes=new_nodes,
        edges=tuple(new_edges),
    )


# --- Spherical-robot golden fixture ------------------------------------------------------


def _node(
    node_id: str,
    label: str,
    node_type: NodeType,
    baseline: float,
    minimum: float,
    maximum: float,
    unit: str,
    *,
    normalization: Normalization = Normalization.LINEAR,
    sensitivity_step: float | None = None,
    controllability: Controllability = Controllability.UNCONTROLLABLE,
    evidence_status: EvidenceStatus = EvidenceStatus.CONDITIONAL,
    evidence_ids: tuple[str, ...] = ("ev_seed",),
    editable: bool = False,
) -> CausalNode:
    return CausalNode(
        id=node_id,
        label=label,
        type=node_type,
        baseline=baseline,
        min=minimum,
        max=maximum,
        unit=unit,
        normalization=normalization,
        sensitivity_step=sensitivity_step,
        controllability=controllability,
        evidence_status=evidence_status,
        evidence_ids=evidence_ids,
        status=ElementStatus.CONFIRMED,
        editable=editable,
    )


def spherical_robot_confirmed_graph() -> GraphVersion:
    """The P0 confirmed spherical-robot causal graph (9 nodes, 12 edges)."""

    nodes = (
        _node(
            "procurement_cycle_months",
            "采购周期",
            NodeType.EXTERNAL,
            baseline=9.0,
            minimum=3.0,
            maximum=24.0,
            unit="个月",
            normalization=Normalization.INVERSE_LINEAR,
            sensitivity_step=2.1,
            editable=True,
        ),
        _node(
            "rescue_demand_intensity",
            "救援需求强度",
            NodeType.EXTERNAL,
            baseline=72.0,
            minimum=0.0,
            maximum=100.0,
            unit="指数",
            editable=True,
        ),
        _node(
            "terrain_capability",
            "复杂地形能力",
            NodeType.LEVER,
            baseline=68.0,
            minimum=0.0,
            maximum=100.0,
            unit="指数",
            controllability=Controllability.CONTROLLABLE,
            editable=True,
        ),
        _node(
            "safety_liability_risk",
            "安全责任风险",
            NodeType.EXTERNAL,
            baseline=40.0,
            minimum=0.0,
            maximum=100.0,
            unit="指数",
            editable=True,
        ),
        _node(
            "cash_safety",
            "现金安全度",
            NodeType.INTERMEDIATE,
            baseline=55.0,
            minimum=0.0,
            maximum=100.0,
            unit="指数",
        ),
        _node(
            "rescue_feasibility",
            "救援试点可行性",
            NodeType.INTERMEDIATE,
            baseline=60.0,
            minimum=0.0,
            maximum=100.0,
            unit="指数",
        ),
        _node(
            "rescue_outcome",
            "救援战略结果",
            NodeType.OUTCOME,
            baseline=64.0,
            minimum=0.0,
            maximum=100.0,
            unit="指数",
        ),
        _node(
            "research_outcome",
            "继续研究结果",
            NodeType.OUTCOME,
            baseline=50.0,
            minimum=0.0,
            maximum=100.0,
            unit="指数",
        ),
        _node(
            "home_outcome",
            "家庭服务结果",
            NodeType.OUTCOME,
            baseline=42.0,
            minimum=0.0,
            maximum=100.0,
            unit="指数",
        ),
    )

    def edge(
        edge_id: str,
        source: str,
        target: str,
        polarity: EdgePolarity,
        strength: float,
        delay: int = 0,
    ) -> CausalEdge:
        return CausalEdge(
            id=edge_id,
            source_node_id=source,
            target_node_id=target,
            polarity=polarity,
            strength=strength,
            delay_steps=delay,
            relationship_quality_score=0.6,
            claim_ids=(f"claim_{edge_id}",),
            evidence_ids=("ev_seed",),
            status=ElementStatus.CONFIRMED,
        )

    edges = (
        edge("edge_procurement_cash", "procurement_cycle_months", "cash_safety", EdgePolarity.POSITIVE, 0.9, delay=1),
        edge("edge_demand_feasibility", "rescue_demand_intensity", "rescue_feasibility", EdgePolarity.POSITIVE, 0.6),
        edge("edge_terrain_feasibility", "terrain_capability", "rescue_feasibility", EdgePolarity.POSITIVE, 0.5),
        edge("edge_safety_feasibility", "safety_liability_risk", "rescue_feasibility", EdgePolarity.NEGATIVE, 0.4),
        edge("edge_cash_rescue", "cash_safety", "rescue_outcome", EdgePolarity.POSITIVE, 0.8, delay=1),
        edge("edge_feasibility_rescue", "rescue_feasibility", "rescue_outcome", EdgePolarity.POSITIVE, 0.6),
        edge("edge_demand_rescue", "rescue_demand_intensity", "rescue_outcome", EdgePolarity.POSITIVE, 0.3, delay=1),
        edge("edge_cash_research", "cash_safety", "research_outcome", EdgePolarity.POSITIVE, 0.3, delay=1),
        edge("edge_procurement_research", "procurement_cycle_months", "research_outcome", EdgePolarity.POSITIVE, 0.2, delay=1),
        edge("edge_terrain_home", "terrain_capability", "home_outcome", EdgePolarity.POSITIVE, 0.3),
        edge("edge_safety_home", "safety_liability_risk", "home_outcome", EdgePolarity.NEGATIVE, 0.2),
        edge("edge_feasibility_cash", "rescue_feasibility", "cash_safety", EdgePolarity.NEGATIVE, 0.2, delay=1),
    )

    return GraphVersion(
        id="graphver_spherical_robot_v1",
        graph_id="graph_spherical_robot",
        status=GraphVersionStatus.CONFIRMED,
        nodes=nodes,
        edges=edges,
    )


def spherical_robot_score_definition() -> ScoreDefinition:
    return ScoreDefinition(
        id="scoredef_spherical_robot_v1",
        version="1",
        option_ids=(RESCUE_PILOT, CONTINUE_RESEARCH, HOME_SERVICE),
        option_outcomes=(
            OptionOutcomeMapping(RESCUE_PILOT, "rescue_outcome", "goal_market_traction", 1.0),
            OptionOutcomeMapping(CONTINUE_RESEARCH, "research_outcome", "goal_market_traction", 1.0),
            OptionOutcomeMapping(HOME_SERVICE, "home_outcome", "goal_market_traction", 1.0),
        ),
        risk_weights=(
            RiskWeight(RESCUE_PILOT, "safety_liability_risk", 0.5),
            RiskWeight(HOME_SERVICE, "safety_liability_risk", 0.1),
        ),
        constraint_rules=(
            ConstraintRule(
                id="constraint_rescue_cash",
                option_id=RESCUE_PILOT,
                constraint_node_id="cash_safety",
                comparison=Comparison.LESS_THAN,
                threshold=0.45,
                penalty=1.0,
            ),
        ),
    )


def spherical_robot_strategies() -> dict[str, StrategyVersion]:
    return {
        RESCUE_PILOT: StrategyVersion(
            id="strategyver_rescue_pilot_v1",
            version=1,
            node_overrides={"terrain_capability": 68.0},
        ),
        CONTINUE_RESEARCH: StrategyVersion(
            id="strategyver_continue_research_v1",
            version=1,
            node_overrides={"terrain_capability": 60.0},
        ),
    }


def spherical_robot_scenarios() -> dict[str, ScenarioVersion]:
    base = ScenarioVersion(
        id="scenariover_agency_pull_v1",
        version=1,
        source_lens_artifact_id="lens_scenario_base",
        source_strategic_scenario_id="scenario_agency_pull_source",
        strategy_survives=True,
        early_warning_signals=(
            EarlyWarningSignal(
                signal_id="signal_budget_code",
                type="structural",
                observable="试点意向是否转为正式预算编号",
                threshold_or_pattern="连续两个复盘周期仍无预算编号",
                cadence="monthly",
            ),
        ),
    )
    procurement_delay = ScenarioVersion(
        id="scenariover_procurement_delay_v1",
        version=1,
        source_lens_artifact_id="lens_scenario_delay",
        source_strategic_scenario_id="scenario_procurement_delay_source",
        strategy_survives=False,
        early_warning_signals=(
            EarlyWarningSignal(
                signal_id="signal_procurement_90d",
                type="quantitative",
                observable="采购立项等待天数",
                threshold_or_pattern="> 90 days",
                cadence="biweekly",
            ),
        ),
        edge_multipliers={"edge_procurement_cash": 1.2},
        node_shifts={"procurement_cycle_months": -0.25},
    )
    regulation = ScenarioVersion(
        id="scenariover_regulation_tighten_v1",
        version=1,
        source_lens_artifact_id="lens_scenario_regulation",
        source_strategic_scenario_id="scenario_regulation_source",
        strategy_survives=False,
        node_shifts={"safety_liability_risk": -0.2},
    )
    return {
        "agency_pull": base,
        "procurement_delay": procurement_delay,
        "regulation_tighten": regulation,
    }


@dataclass(frozen=True, slots=True)
class SphericalRobotFixture:
    graph: GraphVersion
    score_definition: ScoreDefinition
    strategies: dict[str, StrategyVersion]
    scenarios: dict[str, ScenarioVersion]
    risk_tolerance: float


def spherical_robot_fixture() -> SphericalRobotFixture:
    return SphericalRobotFixture(
        graph=spherical_robot_confirmed_graph(),
        score_definition=spherical_robot_score_definition(),
        strategies=spherical_robot_strategies(),
        scenarios=spherical_robot_scenarios(),
        risk_tolerance=SPHERICAL_ROBOT_RISK_TOLERANCE,
    )
