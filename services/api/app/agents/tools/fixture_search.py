"""Deterministic fixture-backed retrieval tools.

These tools return canned, workspace-scoped ``RawArtifact`` references keyed by a
stable query key for the spherical-robot golden case. They contact no network and
require no credentials, so the pipeline runs end-to-end offline while every result
is honestly marked ``origin_mode == fixture``. Live Exa / Firecrawl / Tavily
adapters live behind the same tool contract in ``connectors/**`` (case_api_data).

Tool IO models live here (not in a ``schemas.py``) because canonical wire schemas
are owned by contract_lead; these are internal tool payloads, not the OpenAPI
contract surface.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field

from app.types import OriginMode

from ..context import ToolContext
from ..tool_registry import ToolEntry


class _ToolModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SearchResultRef(_ToolModel):
    """A reference to a persisted RawArtifact; never the raw page body."""

    raw_artifact_ref: str
    url: str
    title: str
    snippet: str
    origin_mode: OriginMode
    content_hash: str


class SearchWebInput(_ToolModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=50)


class SearchWebOutput(_ToolModel):
    results: list[SearchResultRef]
    origin_mode: OriginMode


class GetSourceStatusInput(_ToolModel):
    provider: str = Field(min_length=1)


class GetSourceStatusOutput(_ToolModel):
    provider: str
    status: str
    degraded: bool = False


def build_fixture_search_tool(
    fixture_index: Mapping[str, list[SearchResultRef]],
) -> ToolEntry:
    """Build a deterministic ``search_web`` tool from a query-keyed fixture index."""

    async def handler(payload: BaseModel, context: ToolContext) -> BaseModel:
        assert isinstance(payload, SearchWebInput)
        matches = list(fixture_index.get(payload.query, []))[: payload.limit]
        return SearchWebOutput(results=matches, origin_mode=OriginMode.FIXTURE)

    return ToolEntry(
        name="search_web",
        description="Deterministic fixture search returning RawArtifact references.",
        input_model=SearchWebInput,
        output_model=SearchWebOutput,
        read_only=True,
        required_scopes=frozenset({"contribute"}),
        handler=handler,
    )


def build_fixture_source_status_tool(
    statuses: Mapping[str, str] | None = None,
) -> ToolEntry:
    """Build a deterministic ``get_source_status`` tool."""

    resolved = dict(statuses or {})

    async def handler(payload: BaseModel, context: ToolContext) -> BaseModel:
        assert isinstance(payload, GetSourceStatusInput)
        status = resolved.get(payload.provider, "available")
        return GetSourceStatusOutput(
            provider=payload.provider,
            status=status,
            degraded=status != "available",
        )

    return ToolEntry(
        name="get_source_status",
        description="Report provider health without exposing credentials.",
        input_model=GetSourceStatusInput,
        output_model=GetSourceStatusOutput,
        read_only=True,
        required_scopes=frozenset(),
        handler=handler,
    )
