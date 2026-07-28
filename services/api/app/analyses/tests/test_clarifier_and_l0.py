"""R2 battery: question clarifier normalization + the L0 first-party tier.

The clarifier is advisory and bounded (the model proposes, deterministic
normalization rules); L0 dossier facts are counted separately and never
punished as low-trust external sources.
"""

from __future__ import annotations

import pytest

from app.agents.model_provider import FixtureModelProvider
from app.cases.clarifier import clarify_question, normalize_clarifier_output
from app.workers.evidence_funnel import apply_evidence_funnel


def test_normalize_bounds_and_defaults_are_cautious() -> None:
    card = normalize_clarifier_output(
        {
            "pseudoDecision": {"verdict": "yes-ish", "reason": "r" * 999},
            "falseDilemma": {"verdict": False, "thirdOption": ""},
            "reversibility": {"type": "type9", "advice": "a"},
            "refinedQuestion": "",
        },
        "  original question?  ",
    )
    assert card["pseudoDecision"]["verdict"] is True  # truthy -> bool
    assert len(card["pseudoDecision"]["reason"]) == 400  # bounded
    assert card["reversibility"]["type"] == "type1"  # unknown -> cautious path
    assert card["refinedQuestion"] == "original question?"  # falls back, never empty
    assert card["originalQuestion"] == "original question?"


def test_normalize_survives_garbage_shapes() -> None:
    card = normalize_clarifier_output("not a dict", "q?")
    assert card["pseudoDecision"]["verdict"] is False
    assert card["falseDilemma"]["thirdOption"] == ""
    assert card["refinedQuestion"] == "q?"


@pytest.mark.anyio
async def test_clarify_question_end_to_end_with_fixture_provider() -> None:
    provider = FixtureModelProvider()
    prompt_key = (
        "Decision question: 签独家还是不签？\n"
        "Constraints: 现金仅支撑8个月"
    )
    provider.register(
        prompt_key,
        {
            "pseudoDecision": {"verdict": False, "reason": ""},
            "falseDilemma": {"verdict": True, "thirdOption": "限期排他+销量对赌"},
            "reversibility": {"type": "type1", "advice": "独家条款难回退，值得全分析"},
            "refinedQuestion": "以什么条件签订有限期独家，才不至于锁死渠道？",
        },
    )
    card = await clarify_question(
        provider, question="签独家还是不签？", constraints=["现金仅支撑8个月"]
    )
    assert card["falseDilemma"]["verdict"] is True
    assert "对赌" in card["falseDilemma"]["thirdOption"]
    assert card["reversibility"]["type"] == "type1"
    assert card["refinedQuestion"].startswith("以什么条件")


# --- L0 first-party tier through the funnel -----------------------------------


def _packet(factor, conclusion, direction, sources):
    return {
        "factor": factor,
        "conclusion": conclusion,
        "direction": direction,
        "claimSupportScore": 0.7,
        "sources": sources,
    }


def test_l0_first_party_facts_are_admitted_and_counted_separately() -> None:
    result = apply_evidence_funnel(
        [
            _packet("cash", "现金仅支撑8个月，无新融资在途", "opposing",
                    [{"name": "decision-maker dossier", "tier": "L0"}]),
            _packet("market", "market grows 20% yoy per regulator data", "supporting",
                    [{"name": "regulator", "url": "https://data.stats.gov.cn/x"}]),
        ],
        stage="retrieving",
    )
    assert result.audit["admitted"] == 2
    assert result.audit["firstPartyCount"] == 1
    ids = " ".join(result.audit["evidenceIds"])
    assert "[L0]" in ids and "[L2]" in ids
    # L0 stays OUT of the external trust ratio: 0 low-tier / 1 external.
    assert result.audit["lowTierShare"] == 0.0
    warnings = " ".join(result.audit["warnings"])
    assert "low-trust" not in warnings


def test_all_l0_evidence_never_triggers_the_low_trust_warning() -> None:
    result = apply_evidence_funnel(
        [
            _packet("cash", "现金仅支撑8个月，无新融资在途", "opposing",
                    [{"name": "decision-maker dossier", "tier": "L0"}]),
        ],
        stage="retrieving",
    )
    assert result.audit["firstPartyCount"] == 1
    assert all("low-trust" not in w for w in result.audit["warnings"])
