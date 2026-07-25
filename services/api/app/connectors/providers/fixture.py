"""Deterministic spherical-robot fixture provider (offline tests and demo).

Returns stable evidence candidates keyed by the golden-case query keys from
``docs/product-plan/08-deep-research-pipeline.md``. Results are honestly
marked ``origin_mode == fixture`` and never impersonate live retrieval. If a
deterministic payload file exists under ``fixtures/spherical-robot/external``
it is loaded read-only; otherwise the embedded index below is used, so the
provider works in any worktree without touching task-15-owned fixture files.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.types import ConnectorStatus, OriginMode

from .base import (
    FetchOutcome,
    FetchSuccess,
    ProviderFailure,
    SearchHit,
    SearchOutcome,
    SearchSuccess,
)

PROVIDER = "fixture"

_EXTERNAL_DIR = Path("fixtures") / "spherical-robot" / "external"
_INDEX_FILENAME = "search_index.json"

# Query keys straight from the golden-case research plan (08 doc L130-L136).
_EMBEDDED_INDEX: dict[str, list[dict[str, str]]] = {
    "search and rescue ground robot procurement cycle": [
        {
            "url": "https://fixtures.ludus.invalid/rescue/procurement-report-2026",
            "title": "State rescue agency ground robot procurement review 2026",
            "snippet": (
                "Procurement cycles for search-and-rescue ground robots average "
                "14-22 months from pilot to framework contract."
            ),
            "published_at": "2026-03-02T00:00:00+00:00",
        },
        {
            "url": "https://fixtures.ludus.invalid/rescue/budget-brief",
            "title": "Emergency response robotics budget brief",
            "snippet": (
                "Regional budgets earmark reconnaissance robotics under disaster "
                "preparedness lines, not general IT."
            ),
            "published_at": "2026-01-15T00:00:00+00:00",
        },
    ],
    "emergency response reconnaissance robot buyer requirements": [
        {
            "url": "https://fixtures.ludus.invalid/rescue/buyer-interviews",
            "title": "Rescue organization interview summary: remote reconnaissance",
            "snippet": (
                "3 of 5 interviewed rescue teams identified pre-entry remote "
                "reconnaissance as a recurring operational need."
            ),
            "published_at": "2026-02-10T00:00:00+00:00",
        }
    ],
    "search rescue robot terrain reliability safety requirements": [
        {
            "url": "https://fixtures.ludus.invalid/rescue/terrain-safety-standard",
            "title": "Terrain reliability and safety requirements for rescue robots",
            "snippet": (
                "Deployments require debris-field mobility certification and "
                "fail-safe communication loss behavior."
            ),
            "published_at": "2025-11-20T00:00:00+00:00",
        }
    ],
}

_EMBEDDED_PAGES: dict[str, str] = {
    "https://fixtures.ludus.invalid/rescue/procurement-report-2026": (
        "# Procurement review\n\nSearch-and-rescue ground robot procurement "
        "runs 14-22 months from pilot to framework contract, anchored in "
        "disaster preparedness budgets."
    ),
    "https://fixtures.ludus.invalid/rescue/budget-brief": (
        "# Budget brief\n\nReconnaissance robotics is funded under disaster "
        "preparedness budget lines."
    ),
    "https://fixtures.ludus.invalid/rescue/buyer-interviews": (
        "# Interview summary\n\n3 of 5 interviewed rescue teams identified "
        "pre-entry remote reconnaissance as a recurring operational need."
    ),
    "https://fixtures.ludus.invalid/rescue/terrain-safety-standard": (
        "# Terrain and safety\n\nDebris-field mobility certification and "
        "fail-safe communication loss behavior are mandatory."
    ),
}


def _parse_at(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _load_external_index(repo_root: Path | None) -> dict[str, list[dict[str, str]]] | None:
    if repo_root is None:
        return None
    candidate = repo_root / _EXTERNAL_DIR / _INDEX_FILENAME
    if not candidate.is_file():
        return None
    try:
        loaded = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


class FixtureProvider:
    """Deterministic ``search_web`` + ``fetch_url`` over the golden case."""

    provider = PROVIDER

    def __init__(self, *, repo_root: Path | None = None) -> None:
        self._index = _load_external_index(repo_root) or _EMBEDDED_INDEX
        self._pages = dict(_EMBEDDED_PAGES)

    async def search(self, query: str, *, limit: int = 10) -> SearchOutcome:
        entries = self._index.get(query, [])
        hits = tuple(
            SearchHit(
                url=entry["url"],
                title=entry["title"],
                snippet=entry["snippet"],
                published_at=(
                    _parse_at(entry["published_at"]) if entry.get("published_at") else None
                ),
                cited_source_uri=entry.get("cited_source_uri"),
            )
            for entry in entries[: max(1, limit)]
        )
        return SearchSuccess(
            provider=PROVIDER,
            status=ConnectorStatus.AVAILABLE,
            hits=hits,
            origin_mode=OriginMode.FIXTURE,
        )

    async def fetch(self, url: str) -> FetchOutcome:
        content = self._pages.get(url)
        if content is None:
            return ProviderFailure(
                provider=PROVIDER,
                status=ConnectorStatus.PROVIDER_ERROR,
                error_code="SEARCH_UNAVAILABLE",
                retryable=False,
                detail="fixture_page_not_indexed",
            )
        return FetchSuccess(
            provider=PROVIDER,
            status=ConnectorStatus.AVAILABLE,
            url=url,
            content=content,
            media_type="text/markdown",
            origin_mode=OriginMode.FIXTURE,
        )
