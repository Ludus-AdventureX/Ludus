"""Deterministic evidence funnel for the retrieving stage (information funnel).

Compiled from the grey-goo v6 retrieval discipline (v6-analysis-agent §1 TDD
Review + rag-pool L1-L6 source grading): every model-emitted fact passes three
deterministic checks BEFORE persistence, so garbage never becomes a
ResearchPacket and the report can cite a graded, auditable evidence set.

  Check 1 - relevance: a fact must carry a non-trivial, specific conclusion
            (filler like "more research needed" is discarded, not persisted);
  Check 2 - direction: supporting/opposing/neutral is normalized, and a set
            with ZERO opposing facts raises an honest warning (never invented);
  Check 3 - source grade: every fact needs a named source with an L1-L6 tier;
            missing/unknown sources sink to L6, and an L5+L6 share above 30%
            raises a poisoning/quality warning.

The funnel is fail-closed per fact (bad facts are dropped with a logged
reason) and fail-open per run (warnings degrade trust, they do not kill the
stage - the quality gate stays the final judge).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.workers.web_retrieval import grade_domain

_VALID_TIERS = {"L0", "L1", "L2", "L3", "L4", "L5", "L6"}
# L0 = the decision-maker's own first-party input (dossier facts). It is
# honest but externally UNVERIFIED - counted separately, never punished as
# low-trust (punishing a founder for knowing their own cash position would be
# absurd) and never inflating external-source quality either.
_LOW_TIERS = {"L5", "L6"}
_LOW_TIER_MAX_SHARE = 0.30

# Filler phrases that mark a "fact" as non-specific (relevance check).
_FILLER_MARKERS = (
    "more research needed",
    "further research",
    "analysis complete",
    "无法确定",
    "需要更多研究",
    "有待进一步",
)

_DIRECTION_ALIASES: Mapping[str, str] = {
    "supporting": "supporting",
    "support": "supporting",
    "supports": "supporting",
    "opposing": "opposing",
    "oppose": "opposing",
    "opposes": "opposing",
    "against": "opposing",
    "neutral": "neutral",
    "mixed": "neutral",
}


@dataclass
class FunnelResult:
    """Admitted packets (persistence-ready) + the auditable funnel record."""

    admitted: list[dict[str, Any]] = field(default_factory=list)
    audit: dict[str, Any] = field(default_factory=dict)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _normalize_direction(value: Any) -> str | None:
    return _DIRECTION_ALIASES.get(_text(value).lower()) or None


def _normalize_tier(value: Any) -> str:
    tier = _text(value).upper()
    return tier if tier in _VALID_TIERS else "L6"


def _sources_of(packet: Mapping[str, Any]) -> list[dict[str, str]]:
    """Normalized [{name, tier, url}] from a raw packet; unnamed sources drop.

    When a source carries a REAL url, its tier is re-graded deterministically
    from the domain - the model's claimed tier never outranks the checkable
    property of the source itself.
    """

    raw = packet.get("sources")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    sources = []
    for entry in raw:
        if isinstance(entry, Mapping):
            name = _text(entry.get("name") or entry.get("source") or entry.get("domain"))
            url = _text(entry.get("url"))
            if url:
                tier = grade_domain(url)
                if not name:
                    name = url.split("//", 1)[-1].split("/", 1)[0]
            else:
                tier = _normalize_tier(entry.get("tier") or entry.get("grade"))
        else:
            name = _text(entry)
            url = ""
            tier = "L6"
        if name:
            sources.append({"name": name[:120], "tier": tier, "url": url[:400]})
    return sources[:5]


def _relevance_failure(packet: Mapping[str, Any]) -> str | None:
    conclusion = _text(packet.get("conclusion"))
    if len(conclusion) < 15:
        return "conclusion too thin to be a checkable fact"
    lowered = conclusion.lower()
    for marker in _FILLER_MARKERS:
        if marker in lowered:
            return f"filler phrase ('{marker}') - not a fact"
    return None


def apply_evidence_funnel(
    packets: Sequence[Mapping[str, Any]],
    *,
    stage: str = "retrieving",
) -> FunnelResult:
    """Run the three-check funnel; mint graded evidence ids for survivors.

    Admitted packets carry ``evidence_ids`` of the form ``ev-{stage}-{seq}
    [{tier}] {source}`` so the id itself is a human-auditable provenance
    statement (id + grade + source name travel together into the report).
    """

    admitted: list[dict[str, Any]] = []
    discards: list[dict[str, str]] = []
    warnings: list[str] = []
    tier_counts: dict[str, int] = {}
    opposing_evidence_ids: list[str] = []
    all_evidence_ids: list[str] = []
    seq = 0

    for packet in packets:
        if not isinstance(packet, Mapping):
            discards.append({"factor": "?", "reason": "not an object", "check": "relevance"})
            continue
        factor = _text(packet.get("factor")) or "unnamed factor"

        reason = _relevance_failure(packet)
        if reason is not None:
            discards.append({"factor": factor[:80], "reason": reason, "check": "relevance"})
            continue

        direction = _normalize_direction(packet.get("direction"))
        if direction is None:
            # An unlabeled direction defaults to neutral but is flagged, per
            # the TDD spec (ambiguity must stay visible, not be smoothed over).
            direction = "neutral"
            warnings.append(f"'{factor[:60]}' had no direction label; recorded as neutral")

        sources = _sources_of(packet)
        if not sources:
            sources = [{"name": "model-internal reasoning (no external source)", "tier": "L6", "url": ""}]

        evidence_ids = []
        for source in sources:
            seq += 1
            locator = source["url"] or source["name"]
            evidence_id = f"ev-{stage}-{seq:03d} [{source['tier']}] {locator}"
            evidence_ids.append(evidence_id)
            tier_counts[source["tier"]] = tier_counts.get(source["tier"], 0) + 1
        all_evidence_ids.extend(evidence_ids)
        if direction == "opposing":
            opposing_evidence_ids.extend(evidence_ids)

        clean = dict(packet)
        clean["direction"] = direction
        clean["evidence_ids"] = evidence_ids
        clean.pop("sources", None)
        admitted.append(clean)

    # L0 first-party facts stay OUT of the trust ratio entirely: they are the
    # decision-maker's own inputs, not external sources to be graded.
    first_party_count = tier_counts.get("L0", 0)
    external_sources = sum(count for tier, count in tier_counts.items() if tier != "L0")
    total_sources = external_sources
    low_share = (
        sum(tier_counts.get(t, 0) for t in _LOW_TIERS) / total_sources
        if total_sources
        else 1.0
    )
    if admitted and total_sources and low_share > _LOW_TIER_MAX_SHARE:
        warnings.append(
            f"low-trust sources (L5/L6) make up {low_share:.0%} of the evidence set "
            f"(discipline cap {_LOW_TIER_MAX_SHARE:.0%}) - conclusions lean on weak ground"
        )
    opposing_count = len([p for p in admitted if p.get("direction") == "opposing"])
    if admitted and opposing_count == 0:
        warnings.append(
            "zero opposing facts survived the funnel - the evidence set may share "
            "one narrative; treat convergence as unverified"
        )

    audit = {
        "stage": stage,
        "admitted": len(admitted),
        "discarded": discards,
        "tierCounts": tier_counts,
        "lowTierShare": round(low_share, 3) if total_sources else None,
        "firstPartyCount": first_party_count,
        "opposingCount": opposing_count,
        "warnings": warnings,
        "evidenceIds": all_evidence_ids[:20],
        "opposingEvidenceIds": opposing_evidence_ids[:10],
    }
    return FunnelResult(admitted=admitted, audit=audit)
