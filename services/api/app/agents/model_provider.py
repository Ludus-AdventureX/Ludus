"""Provider-neutral model abstraction.

Business code depends only on :class:`ModelProvider`. The default deployment binds
DeepSeek V4 Pro through an OpenAI-compatible endpoint (configured via ``MODEL_*``
env), but no vendor-private field leaks into the domain contract. A deterministic
:class:`FixtureModelProvider` lets the whole pipeline run with no key and no
network for tests and the audited offline fallback.

Two invariants from AGENTS.md are enforced at this seam:

* Empty ``content`` is a *structural* failure (:class:`EmptyModelContentError`),
  never a valid answer. The runner performs at most one schema-repair retry.
* ``reasoning_content`` (DeepSeek thinking mode) may only live in a transient
  in-memory envelope for the duration of one tool-call chain. It MUST NOT be
  returned, stored, logged, traced or reported - so this module never surfaces it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from .errors import EmptyModelContentError


@dataclass(frozen=True, slots=True)
class ModelMessage:
    """A single prompt message. ``role`` is orchestration-level, not a chat loop."""

    role: str
    content: str


@dataclass(frozen=True, slots=True)
class ToolCallRequest:
    """A strict tool call the model asked to make (name + validated arguments)."""

    call_id: str
    tool_name: str
    arguments: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class StructuredCompletion:
    """The provider result surfaced to the runtime.

    ``content`` is the parsed JSON object. ``reasoning_content`` is intentionally
    absent from this type - it is dropped as soon as a tool-call chain ends.
    """

    content: Mapping[str, Any]
    raw_text: str
    request_model: str
    response_model: str
    finish_reason: str
    tool_calls: tuple[ToolCallRequest, ...] = ()

    def require_non_empty(self) -> "StructuredCompletion":
        """Treat empty / whitespace-only content as a structural failure."""

        if not self.raw_text or not self.raw_text.strip():
            raise EmptyModelContentError("model returned empty content")
        if not self.content:
            raise EmptyModelContentError("model returned no structured object")
        return self


@dataclass(frozen=True, slots=True)
class ProviderProbe:
    """Result of a read-only capability probe (used by Gate 0 / diagnostics)."""

    provider: str
    ok: bool
    supports_structured_output: bool
    detail: str | None = None


@runtime_checkable
class ModelProvider(Protocol):
    """Stable interface every worker uses to reach a model."""

    name: str
    supports_structured_output: bool

    def complete_structured(
        self,
        *,
        system: str,
        messages: Sequence[ModelMessage],
        schema: Mapping[str, Any] | None,
        tools: Sequence[Mapping[str, Any]] | None,
        request_model: str,
    ) -> Awaitable[StructuredCompletion]: ...

    def probe(self) -> Awaitable[ProviderProbe]: ...


@dataclass(slots=True)
class FixtureModelProvider:
    """Deterministic, key-free provider for tests and the audited fallback path.

    Canned structured outputs are keyed by a caller-supplied ``fixture_key``. The
    provider never contacts the network and never emits a ``reasoning_content``
    field, so fixture runs cannot masquerade as live and cannot leak hidden CoT.
    """

    name: str = "fixture"
    supports_structured_output: bool = True
    responses: dict[str, Mapping[str, Any]] = field(default_factory=dict)
    request_model: str = "fixture-deterministic"

    def register(self, fixture_key: str, content: Mapping[str, Any]) -> None:
        self.responses[fixture_key] = content

    async def complete_structured(
        self,
        *,
        system: str,
        messages: Sequence[ModelMessage],
        schema: Mapping[str, Any] | None,
        tools: Sequence[Mapping[str, Any]] | None,
        request_model: str,
        fixture_key: str | None = None,
    ) -> StructuredCompletion:
        import json

        key = fixture_key or (messages[-1].content if messages else "")
        content = self.responses.get(key, {})
        raw_text = json.dumps(content, ensure_ascii=False, sort_keys=True)
        return StructuredCompletion(
            content=content,
            raw_text=raw_text,
            request_model=request_model,
            response_model=self.request_model,
            finish_reason="stop",
        )

    async def probe(self) -> ProviderProbe:
        return ProviderProbe(
            provider=self.name,
            ok=True,
            supports_structured_output=self.supports_structured_output,
            detail="deterministic fixture provider; no network, no credentials",
        )
