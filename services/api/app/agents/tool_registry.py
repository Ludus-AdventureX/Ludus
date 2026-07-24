"""Scoped, read-only tool registry.

Behavior reimplementation (not a source copy) of the Hermes ``ToolRegistry`` idea,
adapted to Pydantic + asyncio and hard workspace/run isolation. Agents only ever
see the stable read-only catalog (``search_web``, ``fetch_url``, ``crawl_site``,
``extract_document``, ``get_source_status``); vendor-specific endpoints, write
tools and credentials are never registered.

Every dispatch requires a non-null :class:`ToolContext`; a tool outside the
caller's permitted (subset) envelope is denied; payloads and results are validated
against the tool's Pydantic models.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from .context import ToolContext
from .errors import (
    MissingToolContext,
    SchemaValidationError,
    ToolScopeError,
    ToolUnavailable,
    UnknownTool,
)

# The stable read-only catalog exposed to agents (method-pack tool_permissions).
STABLE_TOOL_CATALOG: frozenset[str] = frozenset(
    {"search_web", "fetch_url", "crawl_site", "extract_document", "get_source_status"}
)

ToolHandler = Callable[[BaseModel, ToolContext], Awaitable[BaseModel]]
AvailabilityCheck = Callable[[ToolContext], Awaitable[bool]]


@dataclass(frozen=True, slots=True)
class ToolEntry:
    """A single registered tool with its schema, scope and async handler."""

    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    read_only: bool
    required_scopes: frozenset[str]
    handler: ToolHandler
    availability_check: AvailabilityCheck | None = None

    def input_schema(self) -> dict[str, Any]:
        return self.input_model.model_json_schema()


class ToolRegistry:
    """Single registration point, schema retrieval and unified async dispatch."""

    def __init__(self) -> None:
        self._entries: dict[str, ToolEntry] = {}

    def register(self, entry: ToolEntry) -> None:
        if entry.name not in STABLE_TOOL_CATALOG:
            raise ValueError(
                f"tool {entry.name!r} is not part of the stable read-only catalog"
            )
        if entry.name in self._entries:
            raise ValueError(f"tool already registered: {entry.name!r}")
        if not entry.read_only:
            raise ValueError(f"only read-only tools may be registered: {entry.name!r}")
        self._entries[entry.name] = entry

    def get(self, name: str) -> ToolEntry:
        try:
            return self._entries[name]
        except KeyError as exc:
            raise UnknownTool(f"unknown tool: {name!r}") from exc

    def names(self) -> frozenset[str]:
        return frozenset(self._entries)

    def schema(self, name: str) -> dict[str, Any]:
        return self.get(name).input_schema()

    def toolset(self, names: frozenset[str]) -> list[ToolEntry]:
        return [self._entries[name] for name in sorted(names) if name in self._entries]

    async def dispatch(
        self,
        name: str,
        payload: Mapping[str, Any],
        *,
        context: ToolContext | None,
        allowed: frozenset[str] | None = None,
    ) -> BaseModel:
        if context is None:
            raise MissingToolContext(
                f"tool {name!r} requires a workspace/run scoped context"
            )
        entry = self.get(name)
        if allowed is not None and name not in allowed:
            raise ToolScopeError(
                f"tool {name!r} is not in the caller's permitted envelope"
            )
        try:
            parsed = entry.input_model.model_validate(dict(payload))
        except ValidationError as exc:
            raise SchemaValidationError(
                f"invalid input for tool {name!r}",
                findings=tuple(str(error) for error in exc.errors()),
            ) from exc
        if entry.availability_check is not None:
            available = await entry.availability_check(context)
            if not available:
                raise ToolUnavailable(f"tool {name!r} is unavailable in this context")
        result = await entry.handler(parsed, context)
        if not isinstance(result, entry.output_model):
            raise SchemaValidationError(
                f"tool {name!r} returned {type(result).__name__}, "
                f"expected {entry.output_model.__name__}"
            )
        return result
