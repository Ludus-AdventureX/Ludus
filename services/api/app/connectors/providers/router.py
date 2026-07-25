"""Provider routing: Exa (default) -> Tavily failover; Firecrawl fetch.

The router owns the degradation policy from 08-deep-research-pipeline.md:

- ``search_web``: Exa first; on any structured failure (missing/invalid
  credentials, rate limit, quota, provider error) switch to Tavily; when both
  degrade, return the last failure with the full ``fallback_chain`` so the
  caller can fall back to cached evidence or the fixture provider without
  losing the source status.
- ``fetch_url``: Firecrawl; failures surface as structured states so callers
  can use an existing RawArtifact or cached body instead — never a silent
  loss of source status.

The router performs no persistence; RawArtifact-first writes live in
``app.evidence.ingest`` which wraps these outcomes.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from .base import FetchOutcome, ProviderFailure, SearchOutcome, SearchSuccess


class SearchProvider(Protocol):
    provider: str

    async def search(self, query: str, *, limit: int = 10) -> SearchOutcome: ...


class FetchProvider(Protocol):
    provider: str

    async def fetch(self, url: str) -> FetchOutcome: ...


class ProviderRouter:
    """Failover orchestration over the audited provider catalog."""

    def __init__(
        self,
        *,
        search_providers: tuple[SearchProvider, ...],
        fetch_provider: FetchProvider,
    ) -> None:
        if not search_providers:
            raise ValueError("at least one search provider is required")
        self._search_providers = search_providers
        self._fetch_provider = fetch_provider

    async def search_web(self, query: str, *, limit: int = 10) -> SearchOutcome:
        attempted: list[str] = []
        last_failure: ProviderFailure | None = None
        for provider in self._search_providers:
            outcome = await provider.search(query, limit=limit)
            if isinstance(outcome, SearchSuccess):
                return outcome
            attempted.append(provider.provider)
            last_failure = replace(outcome, fallback_chain=tuple(attempted))
        assert last_failure is not None
        return last_failure

    async def fetch_url(self, url: str) -> FetchOutcome:
        outcome = await self._fetch_provider.fetch(url)
        if isinstance(outcome, ProviderFailure):
            return replace(
                outcome, fallback_chain=(self._fetch_provider.provider,)
            )
        return outcome


def default_router() -> ProviderRouter:
    """Assemble the canonical Exa -> Tavily / Firecrawl router from env keys."""

    from .exa import ExaSearchProvider
    from .firecrawl import FirecrawlFetchProvider
    from .tavily import TavilySearchProvider

    return ProviderRouter(
        search_providers=(ExaSearchProvider(), TavilySearchProvider()),
        fetch_provider=FirecrawlFetchProvider(),
    )
