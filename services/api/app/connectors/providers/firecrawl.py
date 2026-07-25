"""Firecrawl fetch adapter (``fetch_url``) with crawl disabled by default.

Direct HTTP adapter over ``POST https://api.firecrawl.dev/v1/scrape``; key
comes from ``FIRECRAWL_API_KEY``. The target URL is validated by the SSRF
guard before Firecrawl is asked to touch it, so the platform never proxies a
request at an internal address on our behalf. ``crawl_site`` is off unless
explicitly enabled with a domain allowlist and hard depth/page caps.
"""

from __future__ import annotations

import httpx

from app.types import ConnectorStatus, OriginMode

from .base import (
    ClientFactory,
    FetchOutcome,
    FetchSuccess,
    ProviderFailure,
    api_key_from_env,
    classify_http_status,
    default_client_factory,
    missing_credentials,
    transport_failure,
    unsafe_url_failure,
)
from .ssrf import Resolver, UnsafeRemoteUrlError, validate_outbound_url

PROVIDER = "firecrawl"
API_KEY_ENV = "FIRECRAWL_API_KEY"
SCRAPE_URL = "https://api.firecrawl.dev/v1/scrape"

MAX_CRAWL_PAGES = 8
MAX_CRAWL_DEPTH = 2


class FirecrawlFetchProvider:
    """Fetch one already-selected high-value page as markdown."""

    provider = PROVIDER

    def __init__(
        self,
        *,
        client_factory: ClientFactory | None = None,
        api_key: str | None = None,
        crawl_enabled: bool = False,
        crawl_allowed_domains: tuple[str, ...] = (),
        resolver: Resolver | None = None,
    ) -> None:
        self._client_factory = client_factory or default_client_factory
        self._explicit_key = api_key
        self._crawl_enabled = crawl_enabled
        self._crawl_allowed_domains = tuple(d.lower() for d in crawl_allowed_domains)
        self._resolver = resolver

    def _api_key(self) -> str | None:
        return self._explicit_key or api_key_from_env(API_KEY_ENV)

    async def fetch(self, url: str) -> FetchOutcome:
        key = self._api_key()
        if key is None:
            return missing_credentials(PROVIDER)
        try:
            # The target URL is caller-controlled and must pass the SSRF
            # guard; the fixed platform endpoint is a constant, not an input.
            validate_outbound_url(url, resolver=self._resolver)
        except UnsafeRemoteUrlError as exc:
            return unsafe_url_failure(PROVIDER, exc.reason)
        payload = {"url": url, "formats": ["markdown"]}
        try:
            async with self._client_factory() as client:
                response = await client.post(
                    SCRAPE_URL,
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
        data = body.get("data") or {}
        markdown = data.get("markdown")
        if not isinstance(markdown, str) or not markdown.strip():
            return ProviderFailure(
                provider=PROVIDER,
                status=ConnectorStatus.PROVIDER_ERROR,
                error_code="SEARCH_UNAVAILABLE",
                retryable=True,
                detail="empty_content",
            )
        return FetchSuccess(
            provider=PROVIDER,
            status=ConnectorStatus.AVAILABLE,
            url=url,
            content=markdown,
            media_type="text/markdown",
            origin_mode=OriginMode.LIVE,
        )

    async def crawl(
        self,
        url: str,
        *,
        max_pages: int = MAX_CRAWL_PAGES,
        max_depth: int = MAX_CRAWL_DEPTH,
    ) -> FetchOutcome:
        """Crawl is disabled by default and stays domain/depth/page capped."""

        if not self._crawl_enabled:
            return ProviderFailure(
                provider=PROVIDER,
                status=ConnectorStatus.DISABLED,
                error_code="CONNECTOR_NOT_ALLOWED",
                retryable=False,
                detail="crawl_disabled_by_default",
            )
        from urllib.parse import urlsplit

        host = (urlsplit(url).hostname or "").lower()
        if host not in self._crawl_allowed_domains:
            return ProviderFailure(
                provider=PROVIDER,
                status=ConnectorStatus.DISABLED,
                error_code="CONNECTOR_NOT_ALLOWED",
                retryable=False,
                detail="domain_not_in_crawl_allowlist",
            )
        try:
            validate_outbound_url(url, resolver=self._resolver)
        except UnsafeRemoteUrlError as exc:
            return unsafe_url_failure(PROVIDER, exc.reason)
        if max_pages > MAX_CRAWL_PAGES or max_depth > MAX_CRAWL_DEPTH:
            return ProviderFailure(
                provider=PROVIDER,
                status=ConnectorStatus.DISABLED,
                error_code="CONNECTOR_NOT_ALLOWED",
                retryable=False,
                detail="crawl_budget_exceeds_cap",
            )
        # P0 keeps single-page semantics even when crawl is explicitly
        # enabled: the entry page is fetched and no link expansion happens
        # inside this adapter.
        return await self.fetch(url)
