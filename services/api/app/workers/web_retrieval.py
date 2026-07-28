"""Real web retrieval for the retrieving stage (the missing external leg).

Grey-goo v6 discipline, now with REAL sources: before the retrieving model
call, the worker runs bounded Exa searches derived from the confirmed charter
(three query classes per the rag-pool spec: core facts, OPPOSING evidence,
historical parallels). Results carry real URLs and are graded DETERMINISTICALLY
by domain (the tier is a checkable property of the source, not a model claim).

Fail-open by design: no EXA_API_KEY / network failure -> empty evidence list,
and the stage falls back to model-internal knowledge which the funnel then
honestly sinks to L6. The system never fakes a retrieval.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_EXA_URL = "https://api.exa.ai/search"
_MAX_RESULTS_PER_QUERY = 4
_MAX_QUERIES = 3
_SNIPPET_CHARS = 400

# Deterministic domain -> L1-L6 grading (a property of the source itself).
# L1 primary/official filings, L2 regulator/official statistics, L3 research,
# L4 quality press, L5 secondary commentary, L6 unknown.
_DOMAIN_TIERS: tuple[tuple[str, str], ...] = (
    ("sec.gov", "L1"), ("cninfo.com.cn", "L1"), ("hkexnews.hk", "L1"),
    (".gov", "L2"), (".gov.cn", "L2"), ("europa.eu", "L2"), ("oecd.org", "L2"),
    ("worldbank.org", "L2"), ("imf.org", "L2"), ("stats.gov.cn", "L2"),
    ("nature.com", "L3"), ("science.org", "L3"), ("arxiv.org", "L3"),
    ("nber.org", "L3"), ("ssrn.com", "L3"), ("mckinsey.com", "L3"),
    ("gartner.com", "L3"), ("statista.com", "L3"),
    ("sciencedirect.com", "L3"), ("sagepub.com", "L3"), ("springer.com", "L3"),
    ("wiley.com", "L3"), ("jstor.org", "L3"), ("ieee.org", "L3"),
    ("acm.org", "L3"), ("tandfonline.com", "L3"), ("nih.gov", "L2"),
    ("hbr.org", "L3"), ("bcg.com", "L3"), ("bain.com", "L3"),
    ("reuters.com", "L4"), ("bloomberg.com", "L4"), ("ft.com", "L4"),
    ("wsj.com", "L4"), ("economist.com", "L4"), ("nikkei.com", "L4"),
    ("caixin.com", "L4"), ("36kr.com", "L5"), ("techcrunch.com", "L5"),
    ("medium.com", "L5"), ("substack.com", "L5"), ("zhihu.com", "L5"),
)


def grade_domain(url: str) -> str:
    """Deterministic L1-L6 tier from the source domain (checkable, not claimed)."""

    try:
        host = url.split("//", 1)[-1].split("/", 1)[0].lower()
    except Exception:
        return "L6"
    for needle, tier in _DOMAIN_TIERS:
        if needle in host:
            return tier
    return "L6"


@dataclass(frozen=True)
class WebSource:
    title: str
    url: str
    domain: str
    tier: str
    snippet: str
    query_class: str  # core | opposing | historical


def build_queries(decision_question: str, option_ids: list[str]) -> list[dict[str, str]]:
    """The grey-goo three-class query set, bounded to _MAX_QUERIES."""

    question = decision_question.strip()[:200]
    queries = [
        {"class": "core", "q": question},
        {"class": "opposing", "q": f"risks problems failure evidence against: {question}"},
    ]
    if option_ids:
        queries.append({"class": "historical", "q": f"case study precedent outcome: {question}"})
    return queries[:_MAX_QUERIES]


def _exa_key() -> str:
    return os.environ.get("EXA_API_KEY", "").strip()


async def search_web(
    decision_question: str,
    option_ids: list[str],
    *,
    api_key: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[WebSource]:
    """Bounded Exa retrieval; [] on any failure (fail-open, never fabricated)."""

    key = api_key if api_key is not None else _exa_key()
    if not key:
        logger.info("web retrieval skipped: EXA_API_KEY not configured")
        return []

    sources: list[WebSource] = []
    seen_urls: set[str] = set()
    try:
        async with httpx.AsyncClient(
            timeout=20.0, transport=transport, headers={"x-api-key": key}
        ) as client:
            for query in build_queries(decision_question, option_ids):
                response = await client.post(
                    _EXA_URL,
                    json={
                        "query": query["q"],
                        "numResults": _MAX_RESULTS_PER_QUERY,
                        "contents": {"text": {"maxCharacters": _SNIPPET_CHARS}},
                    },
                )
                if response.status_code != 200:
                    logger.warning("exa search HTTP %s for class=%s", response.status_code, query["class"])
                    continue
                for item in response.json().get("results", []):
                    url = str(item.get("url") or "").strip()
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    domain = url.split("//", 1)[-1].split("/", 1)[0].lower()
                    sources.append(
                        WebSource(
                            title=str(item.get("title") or "")[:160],
                            url=url[:400],
                            domain=domain,
                            tier=grade_domain(url),
                            snippet=str(item.get("text") or "")[:_SNIPPET_CHARS],
                            query_class=query["class"],
                        )
                    )
    except httpx.HTTPError as exc:
        logger.warning("web retrieval failed (%s); falling back to model-internal", type(exc).__name__)
    return sources[:10]


def sources_as_stage_input(sources: list[WebSource]) -> list[dict[str, Any]]:
    """Wire shape handed to the retrieving model call."""

    return [
        {
            "title": s.title,
            "url": s.url,
            "domain": s.domain,
            "tier": s.tier,
            "snippet": s.snippet,
            "queryClass": s.query_class,
        }
        for s in sources
    ]
