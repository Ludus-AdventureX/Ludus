"""Stable retrieval provider seam.

The agent runtime depends only on these provider-neutral protocols. Concrete
adapters for Exa / Firecrawl / Tavily and the ``RawArtifact`` persistence live in
``services/api/app/connectors/**`` (owned by case_api_data, Task 8) and must not be
implemented here. This module exists so tools and workers can be wired and tested
against a stable interface before the concrete connectors land.
"""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from app.types import OriginMode

# The exact connector status vocabulary (AGENTS.md section 8). The canonical
# persisted enum is owned by contract_lead / case_api_data; this Literal is only
# the stable *tool-facing* projection returned by ``get_source_status`` so the
# runtime does not fabricate a competing enum authority.
ConnectorStatus = Literal[
    "available",
    "missing_credentials",
    "invalid_credentials",
    "rate_limited",
    "quota_exhausted",
    "provider_error",
    "disabled",
]


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    """A reference to a persisted ``RawArtifact`` produced by a provider adapter.

    Tools return *references*, never raw page bodies injected into a system prompt.
    """

    raw_artifact_ref: str
    url: str
    title: str
    snippet: str
    origin_mode: OriginMode
    content_hash: str


@dataclass(frozen=True, slots=True)
class SourceStatus:
    """Provider health as seen by ``get_source_status``."""

    provider: str
    status: ConnectorStatus
    degraded: bool = False
    detail: str | None = None


@runtime_checkable
class SearchProviderAdapter(Protocol):
    """Search seam. Default Exa, falling back to Tavily, is a connector concern."""

    name: str

    def search(
        self, query: str, *, limit: int, context: object
    ) -> Awaitable[list[RetrievalResult]]: ...

    def status(self, context: object) -> Awaitable[SourceStatus]: ...


@runtime_checkable
class FetchProviderAdapter(Protocol):
    """Fetch/crawl/extract seam. Default Firecrawl with HTTP fallback."""

    name: str

    def fetch(self, url: str, *, context: object) -> Awaitable[RetrievalResult]: ...

    def status(self, context: object) -> Awaitable[SourceStatus]: ...
