"""Evidence funnel battery: TDD checks, grading, minted ids, honest warnings.

Pure unit tests (no DB): the funnel is deterministic by design so its
behaviour is pinned exactly - discard reasons, tier accounting, the L5/L6
share cap, and the zero-opposing warning.
"""

from __future__ import annotations

from app.workers.evidence_funnel import apply_evidence_funnel


def _fact(**overrides):
    base = {
        "factor": "channel demand",
        "conclusion": "Buyer A committed 40% of pilot volume in the June LOI.",
        "direction": "supporting",
        "claimSupportScore": 0.7,
        "sources": [{"name": "signed LOI (June)", "tier": "L1"}],
    }
    base.update(overrides)
    return base


def test_relevance_check_discards_filler_and_thin_facts() -> None:
    result = apply_evidence_funnel(
        [
            _fact(),
            _fact(factor="filler", conclusion="More research needed on this."),
            _fact(factor="thin", conclusion="ok"),
            "not-an-object",
        ]
    )
    assert len(result.admitted) == 1
    checks = [d["check"] for d in result.audit["discarded"]]
    assert checks == ["relevance", "relevance", "relevance"]


def test_direction_is_normalized_and_missing_direction_is_flagged() -> None:
    result = apply_evidence_funnel(
        [_fact(direction="AGAINST"), _fact(factor="unlabeled", direction=None)]
    )
    directions = [p["direction"] for p in result.admitted]
    assert directions == ["opposing", "neutral"]
    assert any("no direction label" in w for w in result.audit["warnings"])


def test_minted_evidence_ids_carry_tier_and_source() -> None:
    result = apply_evidence_funnel([_fact()])
    (packet,) = result.admitted
    assert packet["evidence_ids"] == ["ev-retrieving-001 [L1] signed LOI (June)"]
    assert "sources" not in packet  # normalized away after minting
    assert result.audit["tierCounts"] == {"L1": 1}


def test_unknown_tier_and_missing_sources_sink_to_l6() -> None:
    result = apply_evidence_funnel(
        [
            _fact(sources=[{"name": "some blog", "tier": "AAA"}]),
            _fact(factor="sourceless", sources=[]),
        ]
    )
    assert result.audit["tierCounts"] == {"L6": 2}
    assert any("low-trust sources" in w for w in result.audit["warnings"])


def test_low_tier_cap_stays_quiet_for_a_strong_set() -> None:
    # Four sources, one L5 -> 25% low-tier, under the 30% cap.
    result = apply_evidence_funnel(
        [
            _fact(direction="supporting"),
            _fact(factor="counter", direction="opposing",
                  sources=[{"name": "competitor filing", "tier": "L2"}]),
            _fact(factor="audit", sources=[{"name": "regulator data", "tier": "L2"}]),
            _fact(factor="press", sources=[{"name": "trade press", "tier": "L5"}]),
        ]
    )
    assert result.audit["lowTierShare"] <= 0.30
    assert not any("low-trust sources" in w for w in result.audit["warnings"])
    assert not any("zero opposing" in w for w in result.audit["warnings"])


def test_zero_opposing_set_raises_the_narrative_warning() -> None:
    result = apply_evidence_funnel([_fact(), _fact(factor="second")])
    assert result.audit["opposingCount"] == 0
    assert any("zero opposing" in w for w in result.audit["warnings"])
