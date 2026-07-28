"""Web retrieval battery: deterministic domain grading, query classes,
fail-open behaviour. No live network - httpx MockTransport pins the contract.
"""

from __future__ import annotations

import httpx
import pytest

from app.workers.web_retrieval import build_queries, grade_domain, search_web


def test_grade_domain_is_deterministic_by_source() -> None:
    assert grade_domain("https://www.sec.gov/filing/123") == "L1"
    assert grade_domain("https://data.stats.gov.cn/x") == "L2"
    assert grade_domain("https://arxiv.org/abs/2401.1") == "L3"
    assert grade_domain("https://www.reuters.com/a") == "L4"
    assert grade_domain("https://someone.substack.com/p") == "L5"
    assert grade_domain("https://random-blog.example/x") == "L6"
    assert grade_domain("not a url") == "L6"


def test_build_queries_includes_the_opposing_class() -> None:
    queries = build_queries("Sign exclusive with buyer A?", ["a", "b"])
    classes = [q["class"] for q in queries]
    assert "core" in classes and "opposing" in classes
    assert len(queries) <= 3


@pytest.mark.anyio
async def test_search_web_fails_open_without_a_key() -> None:
    assert await search_web("q", [], api_key="") == []


@pytest.mark.anyio
async def test_search_web_parses_and_grades_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": "SEC 10-K", "url": "https://www.sec.gov/x", "text": "filing text"},
                    {"title": "blog", "url": "https://foo.substack.com/p", "text": "opinion"},
                    {"title": "dup", "url": "https://www.sec.gov/x", "text": "dup"},  # deduped
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    sources = await search_web("question", ["a"], api_key="test-key", transport=transport)
    urls = [s.url for s in sources]
    assert "https://www.sec.gov/x" in urls
    assert urls.count("https://www.sec.gov/x") == 1  # dedup across query classes
    sec = next(s for s in sources if "sec.gov" in s.url)
    assert sec.tier == "L1"
    blog = next(s for s in sources if "substack" in s.url)
    assert blog.tier == "L5"


@pytest.mark.anyio
async def test_search_web_fails_open_on_http_error() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    transport = httpx.MockTransport(boom)
    assert await search_web("q", [], api_key="k", transport=transport) == []
