"""Report factor sandbox: a deterministic, reproducible causal-propagation
layer over a report's factors (the three-layer "what-if" the SIM-02A persisted
engine does not cover for un-confirmed graphs).

This is Layer 1 of the hybrid: a REAL algorithm, not a fake progress bar. From
the report's research packets it derives signed factor nodes (supporting =
positive influence on "proceed", opposing = negative), each with a weight
(claim support) and an editable value (current strength 0-1). Propagation is a
deterministic weighted sum -> outcome score in [0,1]; the verdict flips at 0.5
(proceed vs hold). Sensitivity is genuine recomputation: each factor's driver
delta = outcome(with it) - outcome(without it); a flip condition is the factor
value at which the outcome crosses 0.5.

Layer 2 (LLM semantic evaluation of the top drivers) and Layer 3 (one-click
full re-analysis) are wired above this module; this module stays pure,
deterministic and unit-testable so the numbers are reproducible.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

_FLIP_THRESHOLD = 0.5


@dataclass(frozen=True)
class FactorNode:
    id: str
    label: str
    # Signed influence on "proceed": >0 supporting, <0 opposing.
    weight: float
    # Current strength in [0,1]; user overrides edit this.
    value: float
    direction: str
    source: str


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def factors_from_packets(packets: Sequence[Mapping[str, Any]]) -> list[FactorNode]:
    """Derive signed factor nodes from persisted research packets.

    Deterministic and order-stable: opposing packets get a negative weight so
    they genuinely pull the outcome toward "hold". Packets without a usable
    conclusion are skipped (they are not decision factors).
    """

    factors: list[FactorNode] = []
    for index, packet in enumerate(packets, start=1):
        if not isinstance(packet, Mapping):
            continue
        conclusion = _text(packet.get("conclusion"))
        if len(conclusion) < 5:
            continue
        direction = _text(packet.get("direction")).lower() or "neutral"
        try:
            support = float(packet.get("claim_support_score", packet.get("claimSupportScore", 0.5)))
        except (TypeError, ValueError):
            support = 0.5
        support = _clamp01(support)
        sign = -1.0 if direction == "opposing" else (0.0 if direction == "neutral" else 1.0)
        # Neutral facts still inform the picture but do not push the verdict;
        # give them a small positive weight so they are visible yet non-decisive.
        weight = sign * support if sign != 0.0 else 0.15 * support
        factors.append(
            FactorNode(
                id=f"f{index:02d}",
                label=_text(packet.get("factor")) or conclusion[:60],
                weight=round(weight, 4),
                value=round(support, 4),
                direction=direction,
                source=conclusion[:200],
            )
        )
    return factors


def _outcome(factors: Sequence[FactorNode], overrides: Mapping[str, float]) -> float:
    """Deterministic weighted-mean propagation to a [0,1] proceed score.

    baseline 0.5 (undecided) + normalized signed contribution. A factor's
    contribution is weight * (value - 0.5) * 2, so a fully-present supporting
    factor pushes up and a fully-present opposing factor pushes down.
    """

    total_abs = sum(abs(f.weight) for f in factors)
    if total_abs == 0:
        return _FLIP_THRESHOLD
    contribution = 0.0
    for factor in factors:
        value = _clamp01(overrides.get(factor.id, factor.value))
        contribution += factor.weight * (value - 0.5) * 2.0
    return _clamp01(_FLIP_THRESHOLD + contribution / (2.0 * total_abs))


def _flip_value(factor: FactorNode, factors: Sequence[FactorNode], overrides: Mapping[str, float]) -> float | None:
    """The factor value (0..1) at which the outcome crosses 0.5, if reachable."""

    if factor.weight == 0:
        return None
    others = {k: v for k, v in overrides.items() if k != factor.id}
    base = _outcome([f for f in factors if f.id != factor.id], others)
    total_abs = sum(abs(f.weight) for f in factors)
    if total_abs == 0:
        return None
    # base + weight*(v-0.5)*2 / (2*total_abs) == 0.5  ->  solve for v
    needed = (_FLIP_THRESHOLD - base) * (2.0 * total_abs) / (factor.weight * 2.0) + 0.5
    return round(needed, 3) if 0.0 <= needed <= 1.0 else None


def simulate(
    factors: Sequence[FactorNode],
    overrides: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Run the deterministic sandbox: outcome, verdict, ranked drivers, flips."""

    overrides = {k: _clamp01(float(v)) for k, v in (overrides or {}).items() if k}
    outcome = _outcome(factors, overrides)
    verdict = "proceed" if outcome >= _FLIP_THRESHOLD else "hold"

    drivers = []
    for factor in factors:
        without = _outcome([f for f in factors if f.id != factor.id], overrides)
        delta = round(outcome - without, 4)
        drivers.append({
            "nodeId": factor.id,
            "label": factor.label,
            "scoreDelta": delta,
            "direction": factor.direction,
            "flipValue": _flip_value(factor, factors, overrides),
        })
    drivers.sort(key=lambda d: abs(d["scoreDelta"]), reverse=True)

    return {
        "outcomeScore": round(outcome, 4),
        "verdict": verdict,
        "factors": [
            {
                "id": f.id,
                "label": f.label,
                "weight": f.weight,
                "value": round(_clamp01(overrides.get(f.id, f.value)), 4),
                "baseline": f.value,
                "direction": f.direction,
                "source": f.source,
            }
            for f in factors
        ],
        "topDrivers": drivers[:5],
        "flipThreshold": _FLIP_THRESHOLD,
        "engine": "report-factor-sandbox/1.0 (deterministic)",
    }
