"""Report factor sandbox: a deterministic, reproducible causal-propagation
layer over a report's factors (the three-layer "what-if" the SIM-02A persisted
engine does not cover for un-confirmed graphs).

This is Layer 1 of the hybrid: a REAL algorithm, not a fake progress bar. From
the report's research packets it derives signed factor nodes (supporting =
positive influence on "proceed", opposing = negative), each with a weight
(claim support) and an editable value (current strength 0-1).

Since /2.0 the graph is no longer flat: the retrieving stage may emit
factor->factor influence edges (admitted only when both endpoints are REAL
admitted factors - never fabricated here), and propagation becomes multi-level:
a factor's deviation from baseline ripples into its downstream factors over
bounded iterations (cycle-safe), Meadows-style. With no edges or no deviations
the engine reduces exactly to the 1.0 weighted sum, so baselines stay stable.

Sensitivity is genuine recomputation; flip values are found by deterministic
bisection (the closed form no longer holds under propagation).

Layer 2 (LLM semantic evaluation of the top drivers) and Layer 3 (one-click
full re-analysis with injected assumptions) are wired above this module; this
module stays pure, deterministic and unit-testable so numbers are reproducible.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

_FLIP_THRESHOLD = 0.5
_MAX_EDGES = 12
_PROPAGATION_ROUNDS = 2  # bounded -> cycles cannot loop forever
_EDGE_GAIN = 0.5  # how strongly an upstream deviation moves a downstream factor


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


@dataclass(frozen=True)
class InfluenceEdge:
    """A factor->factor causal edge (by node id, polarity +1/-1)."""

    source_id: str
    target_id: str
    polarity: float
    note: str


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


def edges_from_influences(
    influences: Sequence[Mapping[str, Any]] | None,
    factors: Sequence[FactorNode],
) -> list[InfluenceEdge]:
    """Admit factor->factor edges by DETERMINISTIC validation, never invention.

    An edge survives only when both endpoints resolve to real factor labels
    (exact or case-insensitive match), it is not a self-loop, and it is not a
    duplicate. Capped at _MAX_EDGES, order-stable.
    """

    if not influences:
        return []
    by_label: dict[str, str] = {}
    for factor in factors:
        by_label[factor.label.strip().lower()] = factor.id
    edges: list[InfluenceEdge] = []
    seen: set[tuple[str, str]] = set()
    for entry in influences:
        if not isinstance(entry, Mapping):
            continue
        source = by_label.get(_text(entry.get("from")).lower())
        target = by_label.get(_text(entry.get("to")).lower())
        if not source or not target or source == target:
            continue
        if (source, target) in seen:
            continue
        polarity_raw = _text(entry.get("polarity")).lower() or "+"
        polarity = -1.0 if polarity_raw in {"-", "negative", "opposing", "inverse"} else 1.0
        seen.add((source, target))
        edges.append(
            InfluenceEdge(
                source_id=source,
                target_id=target,
                polarity=polarity,
                note=_text(entry.get("evidenceNote") or entry.get("note"))[:160],
            )
        )
        if len(edges) >= _MAX_EDGES:
            break
    return edges


def _effective_values(
    factors: Sequence[FactorNode],
    overrides: Mapping[str, float],
    edges: Sequence[InfluenceEdge],
) -> dict[str, float]:
    """Multi-level propagation of DEVIATIONS along influence edges.

    Each factor starts at its overridden (or baseline) value. For a bounded
    number of rounds, every edge pushes the upstream factor's deviation from
    its analysed baseline into the downstream factor (scaled by _EDGE_GAIN and
    the edge polarity). Bounded rounds keep cycles finite and deterministic.
    With no edges or no deviations this is exactly the plain override map.
    """

    values = {f.id: _clamp01(overrides.get(f.id, f.value)) for f in factors}
    if not edges:
        return values
    baselines = {f.id: f.value for f in factors}
    for _ in range(_PROPAGATION_ROUNDS):
        deltas: dict[str, float] = {}
        for edge in edges:
            deviation = values[edge.source_id] - baselines[edge.source_id]
            if deviation == 0.0:
                continue
            deltas[edge.target_id] = deltas.get(edge.target_id, 0.0) + (
                edge.polarity * _EDGE_GAIN * deviation
            )
        if not deltas:
            break
        for node_id, delta in deltas.items():
            values[node_id] = _clamp01(values[node_id] + delta)
    return values


def _outcome(
    factors: Sequence[FactorNode],
    overrides: Mapping[str, float],
    edges: Sequence[InfluenceEdge] = (),
) -> float:
    """Deterministic propagation to a [0,1] proceed score.

    baseline 0.5 (undecided) + normalized signed contribution over the
    EFFECTIVE (post-ripple) factor values. A factor's contribution is
    weight * (value - 0.5) * 2, so a fully-present supporting factor pushes up
    and a fully-present opposing factor pushes down.
    """

    total_abs = sum(abs(f.weight) for f in factors)
    if total_abs == 0:
        return _FLIP_THRESHOLD
    live_ids = {f.id for f in factors}
    live_edges = [e for e in edges if e.source_id in live_ids and e.target_id in live_ids]
    effective = _effective_values(factors, overrides, live_edges)
    contribution = 0.0
    for factor in factors:
        contribution += factor.weight * (effective[factor.id] - 0.5) * 2.0
    return _clamp01(_FLIP_THRESHOLD + contribution / (2.0 * total_abs))


def _flip_value(
    factor: FactorNode,
    factors: Sequence[FactorNode],
    overrides: Mapping[str, float],
    edges: Sequence[InfluenceEdge],
) -> float | None:
    """The factor value (0..1) at which the outcome crosses 0.5, if reachable.

    Under multi-level propagation the closed form no longer holds, so this is
    a deterministic bisection over the (monotone in this factor) outcome.
    """

    if factor.weight == 0:
        return None

    def outcome_at(v: float) -> float:
        return _outcome(factors, {**overrides, factor.id: v}, edges)

    lo_val, hi_val = outcome_at(0.0), outcome_at(1.0)
    if (lo_val - _FLIP_THRESHOLD) * (hi_val - _FLIP_THRESHOLD) > 0:
        return None  # this factor alone cannot flip the verdict
    lo, hi = 0.0, 1.0
    rising = hi_val >= lo_val
    for _ in range(24):
        mid = (lo + hi) / 2.0
        if (outcome_at(mid) >= _FLIP_THRESHOLD) == rising:
            hi = mid
        else:
            lo = mid
    return round((lo + hi) / 2.0, 3)


def simulate(
    factors: Sequence[FactorNode],
    overrides: Mapping[str, float] | None = None,
    edges: Sequence[InfluenceEdge] = (),
) -> dict[str, Any]:
    """Run the deterministic sandbox: outcome, verdict, ranked drivers, flips."""

    overrides = {k: _clamp01(float(v)) for k, v in (overrides or {}).items() if k}
    outcome = _outcome(factors, overrides, edges)
    verdict = "proceed" if outcome >= _FLIP_THRESHOLD else "hold"
    effective = _effective_values(factors, overrides, list(edges))

    drivers = []
    for factor in factors:
        without = _outcome([f for f in factors if f.id != factor.id], overrides, edges)
        delta = round(outcome - without, 4)
        drivers.append({
            "nodeId": factor.id,
            "label": factor.label,
            "scoreDelta": delta,
            "direction": factor.direction,
            "flipValue": _flip_value(factor, factors, overrides, edges),
        })
    drivers.sort(key=lambda d: abs(d["scoreDelta"]), reverse=True)

    labels = {f.id: f.label for f in factors}
    return {
        "outcomeScore": round(outcome, 4),
        "verdict": verdict,
        "factors": [
            {
                "id": f.id,
                "label": f.label,
                "weight": f.weight,
                "value": round(_clamp01(overrides.get(f.id, f.value)), 4),
                "effectiveValue": round(effective[f.id], 4),
                "baseline": f.value,
                "direction": f.direction,
                "source": f.source,
            }
            for f in factors
        ],
        "influences": [
            {
                "from": e.source_id,
                "fromLabel": labels.get(e.source_id, e.source_id),
                "to": e.target_id,
                "toLabel": labels.get(e.target_id, e.target_id),
                "polarity": "+" if e.polarity > 0 else "-",
                "note": e.note,
            }
            for e in edges
            if e.source_id in labels and e.target_id in labels
        ],
        "topDrivers": drivers[:5],
        "flipThreshold": _FLIP_THRESHOLD,
        "engine": "report-factor-sandbox/2.0 (deterministic, multi-level)",
    }
