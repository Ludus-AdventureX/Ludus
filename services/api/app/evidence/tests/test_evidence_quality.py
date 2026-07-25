"""Task 8 owner tests: same-source dedup and the blocking quality gate.

Pure-function tests over ``app.evidence.quality`` and
``app.evidence.normalizer``; no database or network involved.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.evidence.normalizer import (
    SourceIdentity,
    canonicalize_url,
    group_independent_sources,
    source_domain,
)
from app.evidence.quality import (
    EvidenceCandidate,
    InformationQualityGate,
    REMEDIATIONS,
)
from app.types import EvidenceVerdict

NOW = datetime(2026, 7, 25, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def gate() -> InformationQualityGate:
    return InformationQualityGate()


def _candidate(key: str, **overrides) -> EvidenceCandidate:
    defaults = dict(
        candidate_key=key,
        source_grade="L2_reputable",
        identity=SourceIdentity(candidate_key=key, canonical_uri=f"https://site-{key}.test/a"),
        supports_core_claim=True,
        verifiable=True,
        authenticity=0.9,
        relevance=0.85,
        applicability=0.8,
        extraction_reliability=0.9,
        published_at=NOW - timedelta(days=30),
        retrieved_at=NOW,
    )
    defaults.update(overrides)
    return EvidenceCandidate(**defaults)


def claim_fixture_same_report() -> list[EvidenceCandidate]:
    """Three articles all citing the same underlying market report."""

    report = "https://research.example.test/reports/rescue-market-2026"
    return [
        _candidate(
            f"article-{index}",
            identity=SourceIdentity(
                candidate_key=f"article-{index}",
                canonical_uri=f"https://news-{index}.test/rescue-market?utm_source=x",
                cited_source_uri=report,
            ),
        )
        for index in range(1, 4)
    ]


def unverifiable_social_post_fixture() -> list[EvidenceCandidate]:
    return [
        _candidate(
            "social-post",
            source_grade="L6_unverified",
            verifiable=False,
            authenticity=0.4,
            identity=SourceIdentity(
                candidate_key="social-post",
                canonical_uri="https://social.example.test/p/123",
            ),
        )
    ]


# --- same-source dedup ------------------------------------------------------


def test_three_articles_citing_same_report_count_as_one_independent_source(gate) -> None:
    result = gate.evaluate(claim_fixture_same_report())
    assert result.independent_source_count == 1
    assert result.verdict == EvidenceVerdict.CONDITIONAL
    decisions = list(result.decisions.values())
    assert {d.independent_source_group_id for d in decisions} == {
        decisions[0].independent_source_group_id
    }
    for decision in decisions:
        assert decision.verdict == EvidenceVerdict.CONDITIONAL
        assert "same_source_citations_collapsed" in decision.reason_codes
        assert decision.applicability_limits


def test_distinct_root_sources_count_separately(gate) -> None:
    result = gate.evaluate([_candidate("a"), _candidate("b")])
    assert result.independent_source_count == 2
    assert result.verdict == EvidenceVerdict.ACCEPTED


def test_tracking_params_and_case_do_not_split_groups() -> None:
    grouping = group_independent_sources(
        [
            SourceIdentity("a", canonical_uri="https://Site.Test/Report?utm_source=x"),
            SourceIdentity("b", canonical_uri="https://site.test/Report/"),
        ]
    )
    assert grouping.independent_source_count == 1


def test_canonicalize_url_is_deterministic() -> None:
    left = canonicalize_url("HTTPS://Example.Test:443/path/?b=2&a=1&fbclid=zzz#frag")
    right = canonicalize_url("https://example.test/path?a=1&b=2")
    assert left == right
    assert source_domain("https://Example.Test/x") == "example.test"


def test_content_hash_identity_used_when_no_uri() -> None:
    grouping = group_independent_sources(
        [
            SourceIdentity("a", content_sha256="ABC123"),
            SourceIdentity("b", content_sha256="abc123"),
            SourceIdentity("c"),
        ]
    )
    assert grouping.independent_source_count == 2


# --- four-tier verdict ------------------------------------------------------


def test_unverifiable_source_cannot_support_core_claim(gate) -> None:
    result = gate.evaluate(unverifiable_social_post_fixture())
    decision = result.decisions["social-post"]
    assert decision.verdict == EvidenceVerdict.LEAD_ONLY
    assert decision.triggers_next_retrieval is True
    assert decision.enters_worker_evidence_set is False
    assert "unverifiable_source" in decision.reason_codes


def test_l1_grade_alone_never_auto_accepts(gate) -> None:
    result = gate.evaluate([_candidate("solo-l1", source_grade="L1_primary")])
    decision = result.decisions["solo-l1"]
    assert decision.dimensions.source_quality == 1.0
    assert decision.verdict == EvidenceVerdict.CONDITIONAL
    assert "l1_requires_corroboration" in decision.reason_codes
    assert decision.applicability_limits


def test_l1_with_independent_corroboration_can_accept(gate) -> None:
    result = gate.evaluate(
        [_candidate("l1", source_grade="L1_primary"), _candidate("l2")]
    )
    assert result.decisions["l1"].verdict == EvidenceVerdict.ACCEPTED


def test_rejected_on_authenticity_floor_and_excluded_from_worker_set(gate) -> None:
    result = gate.evaluate([_candidate("fake", authenticity=0.1), _candidate("ok")])
    decision = result.decisions["fake"]
    assert decision.verdict == EvidenceVerdict.REJECTED
    assert decision.enters_worker_evidence_set is False
    assert decision.triggers_next_retrieval is False
    assert "authenticity_below_floor" in decision.reason_codes


def test_rejected_on_extraction_and_relevance_floors(gate) -> None:
    result = gate.evaluate(
        [
            _candidate("bad-extract", extraction_reliability=0.2),
            _candidate("off-topic", relevance=0.1),
            _candidate("anchor"),
        ]
    )
    assert result.decisions["bad-extract"].verdict == EvidenceVerdict.REJECTED
    assert result.decisions["off-topic"].verdict == EvidenceVerdict.REJECTED


def test_conditional_always_carries_limits_and_remediations(gate) -> None:
    result = gate.evaluate(
        [
            _candidate(
                "stale",
                published_at=NOW - timedelta(days=900),
                bias_flags=("vendor_funded",),
            ),
            _candidate("anchor"),
        ]
    )
    decision = result.decisions["stale"]
    assert decision.verdict == EvidenceVerdict.CONDITIONAL
    assert decision.applicability_limits
    assert set(decision.reason_codes) >= {"stale_evidence", "bias_flagged"}
    assert decision.remediation_actions
    for code in decision.reason_codes:
        assert code in REMEDIATIONS


def test_supporting_claim_relaxes_core_only_rules(gate) -> None:
    result = gate.evaluate(
        [_candidate("support-only", supports_core_claim=False)]
    )
    assert result.decisions["support-only"].verdict == EvidenceVerdict.ACCEPTED


def test_conflict_and_completeness_route_to_conditional(gate) -> None:
    result = gate.evaluate(
        [
            _candidate(
                "conflicted",
                in_conflict_group=True,
                completeness_warnings=("partial_extract",),
            ),
            _candidate("anchor"),
        ]
    )
    decision = result.decisions["conflicted"]
    assert decision.verdict == EvidenceVerdict.CONDITIONAL
    assert set(decision.reason_codes) >= {
        "conflicting_evidence_present",
        "completeness_warning",
    }


def test_unknown_source_grade_fails_closed(gate) -> None:
    with pytest.raises(ValueError):
        gate.evaluate([_candidate("bad-grade", source_grade="L7_secret")])


def test_freshness_banding_reflected_in_dimensions(gate) -> None:
    fresh = gate.evaluate([_candidate("fresh")]).decisions["fresh"]
    stale = gate.evaluate(
        [_candidate("old", published_at=NOW - timedelta(days=900))]
    ).decisions["old"]
    unknown = gate.evaluate([_candidate("nodate", published_at=None)]).decisions["nodate"]
    assert fresh.dimensions.freshness_status == "fresh"
    assert stale.dimensions.freshness_status == "stale"
    assert unknown.dimensions.freshness_status == "unknown"
