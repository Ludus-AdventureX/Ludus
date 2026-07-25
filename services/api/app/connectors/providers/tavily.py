"""Tavily search adapter (failover for ``search_web``).

Direct HTTP adapter over ``POST https://api.tavily.com/search``; key comes
from ``TAVILY_API_KEY`` and travels only in the Authorization header. All
failures degrade to structured ``ProviderFailure`` values.
"""

from __future__ import annotations

import httpx

from app.types import ConnectorStatus, OriginMode

from .base import (
    ClientFactory,
    ProviderFailure,
    SearchHit,
    SearchOutcome,
    SearchSuccess,
    api_key_from_env,
    classify_http_status,
    default_client_factory,
    missing_credentials,
    transport_failure,
)

PROVIDER = "tavily"
API_KEY_ENV = "TAVILY_API_KEY"
SEARCH_URL = "https://api.tavily.com/search"


class TavilySearchProvider:
    """Backup web search used when Exa degrades."""

    provider = PROVIDER

    def __init__(
        self,
        *,
        client_factory: ClientFactory | None = None,
        api_key: str | None = None,
    ) -> None:
        self._client_factory = client_factory or default_client_factory
        self._explicit_key = api_key

    def _api_key(self) -> str | None:
        return self._explicit_key or api_key_from_env(API_KEY_ENV)

    async def search(self, query: str, *, limit: int = 10) -> SearchOutcome:
        key = self._api_key()
        if key is None:
            return missing_credentials(PROVIDER)
        # SEARCH_URL is a fixed constant endpoint, not caller input; the SSRF
        # guard applies to caller-controlled fetch targets (see firecrawl.py).
        payload = {
            "query": query,
            "max_results": max(1, min(limit, 20)),
            "include_raw_content": False,
        }
        try:
            async with self._client_factory() as client:
                response = await client.post(
                    SEARCH_URL,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                )
        except httpx.HTTPError:
            return transport_failure(PROVIDER)
        if response.status_code != 200:
            return classify_http_status(PROVIDER, response.status_code)
        try:
            body = response.json()
        except ValueError:
            return ProviderFailure(
                provider=PROVIDER,
                status=ConnectorStatus.PROVIDER_ERROR,
                error_code="SEARCH_UNAVAILABLE",
                retryable=True,
                detail="malformed_response",
            )
        hits: list[SearchHit] = []
        for result in body.get("results", []):
            url = result.get("url")
            if not isinstance(url, str) or not url:
                continue
            hits.append(
                SearchHit(
                    url=url,
                    title=str(result.get("title") or url),
                    snippet=str(result.get("content") or ""),
                )
            )
        return SearchSuccess(
            provider=PROVIDER,
            status=ConnectorStatus.AVAILABLE,
            hits=tuple(hits),
            origin_mode=OriginMode.LIVE,
        )
