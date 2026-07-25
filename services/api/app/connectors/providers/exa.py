"""Exa search adapter (default ``search_web`` provider).

Direct HTTP adapter over ``POST https://api.exa.ai/search``; key comes from
``EXA_API_KEY``. All failures degrade to structured ``ProviderFailure``
values; the key is only ever placed in the request header, never logged.
"""

from __future__ import annotations

from datetime import datetime

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

PROVIDER = "exa"
API_KEY_ENV = "EXA_API_KEY"
SEARCH_URL = "https://api.exa.ai/search"


def _parse_published(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class ExaSearchProvider:
    """Free-tier friendly candidate search: 10-20 candidates per call."""

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
            "numResults": max(1, min(limit, 20)),
            "contents": {"text": False},
        }
        try:
            async with self._client_factory() as client:
                response = await client.post(
                    SEARCH_URL,
                    json=payload,
                    headers={"x-api-key": key, "Content-Type": "application/json"},
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
                    snippet=str(result.get("snippet") or result.get("highlight") or ""),
                    published_at=_parse_published(result.get("publishedDate")),
                )
            )
        return SearchSuccess(
            provider=PROVIDER,
            status=ConnectorStatus.AVAILABLE,
            hits=tuple(hits),
            origin_mode=OriginMode.LIVE,
        )
