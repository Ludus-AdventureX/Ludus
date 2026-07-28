"""Factor sandbox battery: deterministic propagation, drivers, flips.

Pure unit tests - the sandbox is a reproducible calculator, so exact numbers
are pinned: signed factors move the outcome, removing a driver changes it, and
an opposing factor genuinely pulls the verdict to hold.
"""

from __future__ import annotations

from app.simulations.factor_sandbox import factors_from_packets, simulate


def _packet(factor, conclusion, direction, score):
    return {"factor": factor, "conclusion": conclusion, "direction": direction,
            "claim_support_score": score}


def test_factors_from_packets_signs_by_direction_and_skips_empty() -> None:
    factors = factors_from_packets([
        _packet("demand", "buyer committed 40% volume", "supporting", 0.8),
        _packet("clone", "competitor can clone in 60 days", "opposing", 0.7),
        _packet("noise", "x", "supporting", 0.5),  # conclusion too short -> skipped
    ])
    assert [f.id for f in factors] == ["f01", "f02"]
    assert factors[0].weight > 0 and factors[1].weight < 0


def test_supporting_majority_proceeds_opposing_can_flip_to_hold() -> None:
    supportive = simulate(factors_from_packets([
        _packet("a", "strong supporting fact one here", "supporting", 0.9),
        _packet("b", "strong supporting fact two here", "supporting", 0.8),
    ]))
    assert supportive["verdict"] == "proceed"
    assert supportive["outcomeScore"] > 0.5

    mixed = simulate(factors_from_packets([
        _packet("a", "one weak supporting fact here", "supporting", 0.3),
        _packet("b", "one strong opposing fact here", "opposing", 0.95),
    ]))
    assert mixed["verdict"] == "hold"
    assert mixed["outcomeScore"] < 0.5


def test_override_lowering_a_supporting_factor_moves_the_outcome_down() -> None:
    factors = factors_from_packets([
        _packet("a", "supporting fact drives proceed", "supporting", 0.9),
        _packet("b", "opposing fact drives hold here", "opposing", 0.6),
    ])
    base = simulate(factors)["outcomeScore"]
    weakened = simulate(factors, {"f01": 0.1})["outcomeScore"]
    assert weakened < base


def test_top_drivers_rank_by_absolute_impact_and_expose_flip() -> None:
    result = simulate(factors_from_packets([
        _packet("big", "dominant supporting fact here", "supporting", 0.95),
        _packet("small", "minor supporting detail here", "supporting", 0.2),
    ]))
    drivers = result["topDrivers"]
    assert abs(drivers[0]["scoreDelta"]) >= abs(drivers[1]["scoreDelta"])
    assert "flipValue" in drivers[0]


def test_empty_factor_set_is_neutral() -> None:
    result = simulate([])
    assert result["outcomeScore"] == 0.5
    assert result["topDrivers"] == []

# --- multi-level propagation (factor->factor edges, /2.0) ---------------------

from app.simulations.factor_sandbox import edges_from_influences  # noqa: E402


def _two_factor_setup():
    factors = factors_from_packets([
        _packet("funding", "bridge round closes next month", "supporting", 0.8),
        _packet("hiring", "two senior engineers accepted offers", "supporting", 0.6),
        _packet("churn", "top customer renewal is uncertain", "opposing", 0.7),
    ])
    return factors


def test_edges_admit_only_real_factor_labels_no_fabrication() -> None:
    factors = _two_factor_setup()
    edges = edges_from_influences([
        {"from": "funding", "to": "hiring", "polarity": "+"},         # valid
        {"from": "Funding", "to": "HIRING", "polarity": "+"},         # duplicate (case-insensitive)
        {"from": "funding", "to": "funding", "polarity": "+"},        # self-loop -> dropped
        {"from": "made-up factor", "to": "hiring", "polarity": "+"},  # unknown endpoint -> dropped
        {"from": "churn", "to": "hiring", "polarity": "-"},           # valid negative
    ], factors)
    assert [(e.source_id, e.target_id, e.polarity) for e in edges] == [
        ("f01", "f02", 1.0),
        ("f03", "f02", -1.0),
    ]


def test_no_edges_or_no_deviation_reduces_to_flat_engine() -> None:
    factors = _two_factor_setup()
    edges = edges_from_influences([{"from": "funding", "to": "hiring", "polarity": "+"}], factors)
    flat = simulate(factors)
    with_idle_edges = simulate(factors, edges=edges)  # no override -> no deviation
    assert with_idle_edges["outcomeScore"] == flat["outcomeScore"]


def test_deviation_ripples_downstream_and_moves_the_outcome() -> None:
    factors = _two_factor_setup()
    edges = edges_from_influences([{"from": "funding", "to": "hiring", "polarity": "+"}], factors)
    # Killing funding without edges only removes funding's own contribution...
    flat = simulate(factors, overrides={"f01": 0.0})
    # ...with the edge, the funding collapse ALSO drags hiring down (ripple).
    rippled = simulate(factors, overrides={"f01": 0.0}, edges=edges)
    assert rippled["outcomeScore"] < flat["outcomeScore"]
    hiring = next(f for f in rippled["factors"] if f["id"] == "f02")
    assert hiring["effectiveValue"] < hiring["baseline"]
    assert rippled["influences"][0]["fromLabel"] == "funding"


def test_cycles_stay_bounded_and_deterministic() -> None:
    factors = _two_factor_setup()
    edges = edges_from_influences([
        {"from": "funding", "to": "hiring", "polarity": "+"},
        {"from": "hiring", "to": "funding", "polarity": "+"},  # cycle
    ], factors)
    a = simulate(factors, overrides={"f01": 0.1}, edges=edges)
    b = simulate(factors, overrides={"f01": 0.1}, edges=edges)
    assert a["outcomeScore"] == b["outcomeScore"]  # bounded rounds -> reproducible
    assert 0.0 <= a["outcomeScore"] <= 1.0


def test_flip_value_bisection_matches_the_verdict_boundary() -> None:
    factors = _two_factor_setup()
    edges = edges_from_influences([{"from": "funding", "to": "hiring", "polarity": "+"}], factors)
    result = simulate(factors, edges=edges)
    funding = next(d for d in result["topDrivers"] if d["nodeId"] == "f01")
    flip = funding["flipValue"]
    if flip is not None:
        below = simulate(factors, overrides={"f01": max(0.0, flip - 0.05)}, edges=edges)
        above = simulate(factors, overrides={"f01": min(1.0, flip + 0.05)}, edges=edges)
        assert below["verdict"] != above["verdict"]

