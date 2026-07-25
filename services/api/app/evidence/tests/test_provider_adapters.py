"""Task 8 owner tests: provider degradation matrix and failover routing.

All HTTP is mocked with ``httpx.MockTransport``; no network, no real keys.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.connectors.providers.base import (
    ProviderFailure,
    SearchSuccess,
    FetchSuccess,
)
from app.connectors.providers.exa import ExaSearchProvider
from app.connectors.providers.firecrawl import FirecrawlFetchProvider
from app.connectors.providers.fixture import FixtureProvider
from app.connectors.providers.router import ProviderRouter
from app.connectors.providers.tavily import TavilySearchProvider
from app.types import ConnectorStatus, OriginMode

FAKE_KEY = "task08-test-only-key-000000"


def _public_resolver(host: str):
    return ["93.184.216.34"]


def _factory(handler):
    def make() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    return make


def _json_response(status_code: int, payload: dict) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


def exa_ok_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["x-api-key"] == FAKE_KEY
    return _json_response(
        200,
        {
            "results": [
                {
                    "url": "https://public.example.test/report",
                    "title": "Report",
                    "snippet": "snippet",
                    "publishedDate": "2026-03-02T00:00:00Z",
                }
            ]
        },
    )


def tavily_ok_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["Authorization"] == f"Bearer {FAKE_KEY}"
    return _json_response(
        200,
        {
            "results": [
                {
                    "url": "https://tavily.example.test/report",
                    "title": "Tavily report",
                    "content": "content",
                }
            ]
        },
    )


def _status_handler(status_code: int):
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(status_code, {"error": "redacted"})

    return handler


# --- missing credentials (no request is ever sent) --------------------------


async def test_missing_credentials_degrades_before_any_request(monkeypatch) -> None:
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)

    def explode(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no HTTP request may be sent without credentials")

    for outcome in [
        await ExaSearchProvider(client_factory=_factory(explode)).search("q"),
        await TavilySearchProvider(client_factory=_factory(explode)).search("q"),
        await FirecrawlFetchProvider(client_factory=_factory(explode)).fetch(
            "https://public.example.test/x"
        ),
    ]:
        assert isinstance(outcome, ProviderFailure)
        assert outcome.status == ConnectorStatus.MISSING_CREDENTIALS
        assert outcome.retryable is True


# --- HTTP status classification matrix ---------------------------------------


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (401, ConnectorStatus.INVALID_CREDENTIALS),
        (403, ConnectorStatus.INVALID_CREDENTIALS),
        (429, ConnectorStatus.RATE_LIMITED),
        (402, ConnectorStatus.QUOTA_EXHAUSTED),
        (500, ConnectorStatus.PROVIDER_ERROR),
        (503, ConnectorStatus.PROVIDER_ERROR),
    ],
)
async def test_exa_http_failures_map_to_canonical_statuses(
    status_code: int, expected: ConnectorStatus
) -> None:
    provider = ExaSearchProvider(
        client_factory=_factory(_status_handler(status_code)), api_key=FAKE_KEY
    )
    outcome = await provider.search("q")
    assert isinstance(outcome, ProviderFailure)
    assert outcome.status == expected


async def test_transport_error_is_provider_error_not_exception() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection reset", request=request)

    outcome = await ExaSearchProvider(
        client_factory=_factory(boom), api_key=FAKE_KEY
    ).search("q")
    assert isinstance(outcome, ProviderFailure)
    assert outcome.status == ConnectorStatus.PROVIDER_ERROR
    assert outcome.detail == "transport_error"


# --- Exa -> Tavily failover ---------------------------------------------------


async def test_router_switches_to_tavily_when_exa_degrades() -> None:
    router = ProviderRouter(
        search_providers=(
            ExaSearchProvider(client_factory=_factory(_status_handler(429)), api_key=FAKE_KEY),
            TavilySearchProvider(client_factory=_factory(tavily_ok_handler), api_key=FAKE_KEY),
        ),
        fetch_provider=FirecrawlFetchProvider(api_key=FAKE_KEY),
    )
    outcome = await router.search_web("rescue robots")
    assert isinstance(outcome, SearchSuccess)
    assert outcome.provider == "tavily"
    assert outcome.origin_mode == OriginMode.LIVE
    assert outcome.hits[0].url == "https://tavily.example.test/report"


async def test_router_reports_full_fallback_chain_when_all_search_degrades() -> None:
    router = ProviderRouter(
        search_providers=(
            ExaSearchProvider(client_factory=_factory(_status_handler(401)), api_key=FAKE_KEY),
            TavilySearchProvider(client_factory=_factory(_status_handler(429)), api_key=FAKE_KEY),
        ),
        fetch_provider=FirecrawlFetchProvider(api_key=FAKE_KEY),
    )
    outcome = await router.search_web("rescue robots")
    assert isinstance(outcome, ProviderFailure)
    assert outcome.fallback_chain == ("exa", "tavily")
    assert outcome.status == ConnectorStatus.RATE_LIMITED


async def test_exa_success_never_reaches_tavily() -> None:
    def tavily_explodes(request: httpx.Request) -> httpx.Response:
        raise AssertionError("tavily must not be called when exa succeeds")

    router = ProviderRouter(
        search_providers=(
            ExaSearchProvider(client_factory=_factory(exa_ok_handler), api_key=FAKE_KEY),
            TavilySearchProvider(client_factory=_factory(tavily_explodes), api_key=FAKE_KEY),
        ),
        fetch_provider=FirecrawlFetchProvider(api_key=FAKE_KEY),
    )
    outcome = await router.search_web("rescue robots")
    assert isinstance(outcome, SearchSuccess)
    assert outcome.provider == "exa"


# --- Firecrawl fetch + crawl gating ------------------------------------------


async def test_firecrawl_fetch_success_returns_markdown() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["url"] == "https://public.example.test/page"
        return _json_response(200, {"data": {"markdown": "# Page\ncontent"}})

    outcome = await FirecrawlFetchProvider(
        client_factory=_factory(handler), api_key=FAKE_KEY, resolver=_public_resolver
    ).fetch("https://public.example.test/page")
    assert isinstance(outcome, FetchSuccess)
    assert outcome.media_type == "text/markdown"
    assert outcome.origin_mode == OriginMode.LIVE


async def test_firecrawl_refuses_internal_target_before_calling_platform() -> None:
    def explode(request: httpx.Request) -> httpx.Response:
        raise AssertionError("SSRF-unsafe URL must never reach the provider")

    outcome = await FirecrawlFetchProvider(
        client_factory=_factory(explode), api_key=FAKE_KEY
    ).fetch("http://169.254.169.254/latest/meta-data/")
    assert isinstance(outcome, ProviderFailure)
    assert outcome.error_code == "UNSAFE_REMOTE_URL"
    assert outcome.retryable is False


async def test_crawl_is_disabled_by_default() -> None:
    outcome = await FirecrawlFetchProvider(api_key=FAKE_KEY).crawl(
        "https://public.example.test/"
    )
    assert isinstance(outcome, ProviderFailure)
    assert outcome.status == ConnectorStatus.DISABLED
    assert outcome.detail == "crawl_disabled_by_default"


async def test_crawl_requires_domain_allowlist_even_when_enabled() -> None:
    provider = FirecrawlFetchProvider(
        api_key=FAKE_KEY,
        crawl_enabled=True,
        crawl_allowed_domains=("allowed.example.test",),
    )
    outcome = await provider.crawl("https://other.example.test/")
    assert isinstance(outcome, ProviderFailure)
    assert outcome.detail == "domain_not_in_crawl_allowlist"


# --- fixture provider ---------------------------------------------------------


async def test_fixture_provider_returns_stable_results_marked_fixture() -> None:
    provider = FixtureProvider()
    first = await provider.search("search and rescue ground robot procurement cycle")
    second = await provider.search("search and rescue ground robot procurement cycle")
    assert isinstance(first, SearchSuccess)
    assert first == second
    assert first.origin_mode == OriginMode.FIXTURE
    assert len(first.hits) == 2

    page = await provider.fetch(first.hits[0].url)
    assert isinstance(page, FetchSuccess)
    assert page.origin_mode == OriginMode.FIXTURE

    missing = await provider.fetch("https://fixtures.ludus.invalid/unknown")
    assert isinstance(missing, ProviderFailure)
    assert missing.detail == "fixture_page_not_indexed"


async def test_fixture_provider_unknown_query_returns_empty_not_error() -> None:
    outcome = await FixtureProvider().search("query that has no fixture key")
    assert isinstance(outcome, SearchSuccess)
    assert outcome.hits == ()


# --- secrets hygiene ----------------------------------------------------------


async def test_api_key_never_appears_in_structured_outcomes() -> None:
    provider = ExaSearchProvider(
        client_factory=_factory(_status_handler(401)), api_key=FAKE_KEY
    )
    outcome = await provider.search("q")
    assert isinstance(outcome, ProviderFailure)
    assert FAKE_KEY not in repr(outcome)
    assert FAKE_KEY not in outcome.detail


async def test_provider_error_detail_never_contains_response_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(500, {"secret_body": "must-not-leak"})

    outcome = await ExaSearchProvider(
        client_factory=_factory(handler), api_key=FAKE_KEY
    ).search("q")
    assert isinstance(outcome, ProviderFailure)
    assert "must-not-leak" not in repr(outcome)
