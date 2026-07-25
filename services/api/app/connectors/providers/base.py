"""Shared provider adapter contract (Task 8, case_api_data).

Direct HTTP adapters for the audited read-only catalog (Exa / Tavily /
Firecrawl) plus the deterministic fixture provider all speak this contract:

- outcomes are structured values, never raw exceptions: a missing API key
  degrades to ``ConnectorStatus.MISSING_CREDENTIALS`` *before* any request;
  HTTP failures map onto the canonical ``ConnectorStatus`` set;
- no secret (API key, Authorization header) and no raw response body ever
  enters an outcome ``detail`` — details are static policy labels only;
- every outbound URL passes the SSRF guard, including each redirect hop;
- the HTTP client factory is injectable so the whole degradation matrix is
  testable offline with ``httpx.MockTransport``.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

import httpx

from app.types import ConnectorStatus, OriginMode

DEFAULT_TIMEOUT_SECONDS = 20.0
MAX_RESPONSE_BYTES = 5 * 1024 * 1024

ClientFactory = Callable[[], httpx.AsyncClient]


def default_client_factory() -> httpx.AsyncClient:
    # Redirects are handled manually by adapters so each hop can be
    # re-validated by the SSRF guard.
    return httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT_SECONDS,
        follow_redirects=False,
    )


def api_key_from_env(env_name: str) -> str | None:
    """Read a provider key from the environment; empty string counts as missing."""

    value = os.getenv(env_name, "").strip()
    return value or None


@dataclass(frozen=True)
class SearchHit:
    """One provider search result; identity fields only, no page body."""

    url: str
    title: str
    snippet: str
    published_at: datetime | None = None
    cited_source_uri: str | None = None


@dataclass(frozen=True)
class SearchSuccess:
    provider: str
    status: ConnectorStatus  # always AVAILABLE on success
    hits: tuple[SearchHit, ...]
    origin_mode: OriginMode


@dataclass(frozen=True)
class FetchSuccess:
    provider: str
    status: ConnectorStatus  # always AVAILABLE on success
    url: str
    content: str
    media_type: str
    origin_mode: OriginMode


@dataclass(frozen=True)
class ProviderFailure:
    """Structured degradation state; safe for logs, events, and fallbacks."""

    provider: str
    status: ConnectorStatus
    error_code: str
    retryable: bool
    # Static policy label only; never a secret, URL body, or response body.
    detail: str = ""
    fallback_chain: tuple[str, ...] = field(default_factory=tuple)


SearchOutcome = SearchSuccess | ProviderFailure
FetchOutcome = FetchSuccess | ProviderFailure


def missing_credentials(provider: str) -> ProviderFailure:
    return ProviderFailure(
        provider=provider,
        status=ConnectorStatus.MISSING_CREDENTIALS,
        error_code="CONNECTOR_CREDENTIALS_INVALID",
        retryable=True,
        detail="api_key_not_configured",
    )


def classify_http_status(provider: str, status_code: int) -> ProviderFailure:
    """Map an HTTP failure status onto the canonical connector status set."""

    if status_code in (401, 403):
        return ProviderFailure(
            provider=provider,
            status=ConnectorStatus.INVALID_CREDENTIALS,
            error_code="CONNECTOR_CREDENTIALS_INVALID",
            retryable=True,
            detail="credentials_rejected",
        )
    if status_code == 429:
        return ProviderFailure(
            provider=provider,
            status=ConnectorStatus.RATE_LIMITED,
            error_code="CONNECTOR_RATE_LIMITED",
            retryable=True,
            detail="rate_limited",
        )
    if status_code == 402:
        return ProviderFailure(
            provider=provider,
            status=ConnectorStatus.QUOTA_EXHAUSTED,
            error_code="CONNECTOR_QUOTA_EXHAUSTED",
            retryable=False,
            detail="quota_exhausted",
        )
    return ProviderFailure(
        provider=provider,
        status=ConnectorStatus.PROVIDER_ERROR,
        error_code="SEARCH_UNAVAILABLE",
        retryable=True,
        detail=f"http_{status_code}",
    )


def transport_failure(provider: str) -> ProviderFailure:
    return ProviderFailure(
        provider=provider,
        status=ConnectorStatus.PROVIDER_ERROR,
        error_code="SEARCH_UNAVAILABLE",
        retryable=True,
        detail="transport_error",
    )


def unsafe_url_failure(provider: str, reason: str) -> ProviderFailure:
    return ProviderFailure(
        provider=provider,
        status=ConnectorStatus.PROVIDER_ERROR,
        error_code="UNSAFE_REMOTE_URL",
        retryable=False,
        detail=reason,
    )
