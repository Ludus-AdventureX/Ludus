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
