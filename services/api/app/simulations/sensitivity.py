"""Single-variable sensitivity analysis and recommendation-flip detection.

Pure and deterministic: it only re-runs the pure engine with perturbed node values and
compares option scores and the recommended option. Per ``09`` the business-unit step is the
node's ``sensitivityStep`` or ``(max - min) * 0.1`` — never "current +/- 10%".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.types import SimulationMode

from .domain import (
    CausalNode,
    FlipCondition,
    GraphVersion,
    NodeType,
    ScenarioVersion,
    ScoreDefinition,
    StrategyVersion,
    TopDriver,
)
from .engine import clamp, run_simulation

_DRIVER_NODE_TYPES = frozenset({NodeType.LEVER, NodeType.EXTERNAL, NodeType.UNKNOWN})
_FLIP_GRID_STEPS = 200


@dataclass(frozen=True, slots=True)
class SensitivityResult:
    base_recommended_option_id: str | None
    top_drivers: tuple[TopDriver, ...]
    flip_conditions: tuple[FlipCondition, ...]
    recommendation_shift: str
    business_steps: dict[str, float] = field(default_factory=dict)


def _business_step(node: CausalNode) -> float:
    if node.sensitivity_step is not None:
        return node.sensitivity_step
    return (node.max - node.min) * 0.1


def analyze_sensitivity(
    graph: GraphVersion,
    strategy: StrategyVersion,
    scenario: ScenarioVersion,
    score_definition: ScoreDefinition,
    risk_tolerance: float,
    mode: SimulationMode,
    node_overrides: dict[str, float] | None = None,
    epsilon: float = 0.001,
    max_steps: int = 12,
) -> SensitivityResult:
    base_overrides = dict(node_overrides or {})

    def run(overrides: dict[str, float]):
        return run_simulation(
            graph,
            strategy,
            scenario,
            score_definition,
            risk_tolerance,
            mode,
            node_overrides=overrides,
            epsilon=epsilon,
            max_steps=max_steps,
        )

    base = run(base_overrides)
    base_reco = base.recommended_option_id
    # Reference option for magnitude: the recommended option, else the current best option.
    if base_reco is not None:
        reference_option = base_reco
    else:
        reference_option = max(base.option_scores, key=lambda entry: entry.score).option_id
    base_reference_score = base.score_for(reference_option)

    drivers = sorted(
        (node for node in graph.nodes if node.type in _DRIVER_NODE_TYPES),
        key=lambda node: node.id,
    )

    driver_rows: list[TopDriver] = []
    flip_conditions: list[FlipCondition] = []
    business_steps: dict[str, float] = {}

    for driver in drivers:
        step = _business_step(driver)
        business_steps[driver.id] = step

        up_value = clamp(driver.baseline + step, driver.min, driver.max)
        down_value = clamp(driver.baseline - step, driver.min, driver.max)
        up_score = run({**base_overrides, driver.id: up_value}).score_for(reference_option)
        down_score = run({**base_overrides, driver.id: down_value}).score_for(reference_option)
        magnitude = max(
            abs(base_reference_score - up_score), abs(base_reference_score - down_score)
        )
        driver_rows.append(TopDriver(node_id=driver.id, score_delta=magnitude))

        flip = _first_flip(driver, base_reco, base_overrides, run)
        if flip is not None:
            threshold, to_option = flip
            flip_conditions.append(
                FlipCondition(
                    node_id=driver.id,
                    threshold=threshold,
                    from_option=base_reco,  # type: ignore[arg-type]
                    to_option=to_option,
                )
            )

    top_drivers = tuple(
        sorted(driver_rows, key=lambda row: (-row.score_delta, row.node_id))
    )
    # Order flips by their driver's sensitivity so the most decisive flip is first.
    driver_rank = {row.node_id: index for index, row in enumerate(top_drivers)}
    ordered_flips = tuple(
        sorted(flip_conditions, key=lambda flip: driver_rank.get(flip.node_id, len(top_drivers)))
    )
    recommendation_shift = _describe_shift(graph, ordered_flips)

    return SensitivityResult(
        base_recommended_option_id=base_reco,
        top_drivers=top_drivers,
        flip_conditions=ordered_flips,
        recommendation_shift=recommendation_shift,
        business_steps=business_steps,
    )


def _first_flip(
    driver: CausalNode,
    base_reco: str | None,
    base_overrides: dict[str, float],
    run,
) -> tuple[float, str] | None:
    """Walk outward from baseline on a fine grid; return the first value that flips reco."""

    if base_reco is None:
        return None
    grid_step = (driver.max - driver.min) / _FLIP_GRID_STEPS
    if grid_step <= 0:
        return None
    for index in range(1, _FLIP_GRID_STEPS + 1):
        offset = index * grid_step
        for value in (driver.baseline + offset, driver.baseline - offset):
            if value < driver.min or value > driver.max:
                continue
            reco = run({**base_overrides, driver.id: value}).recommended_option_id
            if reco is not None and reco != base_reco:
                return (value, reco)
    return None


def _describe_shift(graph: GraphVersion, flips: tuple[FlipCondition, ...]) -> str:
    if not flips:
        return "在已测试范围内推荐保持不变。"
    top = flips[0]
    node = graph.node(top.node_id)
    return (
        f"若{node.label}调整到约 {top.threshold:.1f}{node.unit}，"
        f"推荐从 {top.from_option} 切换为 {top.to_option}。"
    )
