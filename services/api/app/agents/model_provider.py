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

import json
import os
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import httpx

from .errors import EmptyModelContentError, SchemaValidationError


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
    # Deterministic synthesizer for callers that registered no exact response.
    # Tests leave this None on purpose: an unregistered key must still surface as
    # a structural failure they can assert. The production key-free path injects
    # one, because without it EVERY stage of a FIXTURE_MODE run resolved to {}
    # and the run was parked within seconds - the key-free path promised by
    # compose.prototype.yaml and AGENTS.md section 8 never actually worked.
    fallback: Callable[[Sequence[ModelMessage]], Mapping[str, Any]] | None = None

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
        content = self.responses.get(key)
        if content is None and self.fallback is not None:
            content = self.fallback(messages)
        if content is None:
            content = {}
        raw_text = json.dumps(content, ensure_ascii=False, sort_keys=True)
        return StructuredCompletion(
            content=content,
            raw_text=raw_text,
            request_model=request_model,
            response_model=self.request_model,
            finish_reason="stop",
        )

    async def complete_text(self, messages: Sequence[ModelMessage]) -> str:
        """Deterministic text echo keyed by the last message; no network."""

        key = messages[-1].content if messages else ""
        content = self.responses.get(key)
        if isinstance(content, Mapping) and "text" in content:
            return str(content["text"])
        return f"fixture-reply:{key}"

    async def probe(self) -> ProviderProbe:
        return ProviderProbe(
            provider=self.name,
            ok=True,
            supports_structured_output=self.supports_structured_output,
            detail="deterministic fixture provider; no network, no credentials",
        )


# ---------------------------------------------------------------------------
# Canonical schema validation + single repair retry (18-plan Task 5 Step 2)
# ---------------------------------------------------------------------------


def validate_canonical_schema(
    content: Mapping[str, Any], schema: Mapping[str, Any] | None
) -> tuple[str, ...]:
    """Validate a parsed object against a canonical JSON-schema subset.

    Supports the vocabulary the canonical wire schemas actually use:
    ``type`` / ``properties`` / ``required`` / ``items`` / ``enum``. Returns
    machine-readable findings; empty means valid. Free-text salvage of invalid
    output is deliberately impossible here — the caller either gets a valid
    object or a typed failure.
    """

    if schema is None:
        return ()
    findings: list[str] = []
    _validate_node(content, schema, "$", findings)
    return tuple(findings)


_TYPE_CHECKS = {
    "object": lambda value: isinstance(value, Mapping),
    "array": lambda value: isinstance(value, (list, tuple)),
    "string": lambda value: isinstance(value, str),
    "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
    "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
    "boolean": lambda value: isinstance(value, bool),
    "null": lambda value: value is None,
}


def _validate_node(value: Any, schema: Mapping[str, Any], path: str, findings: list[str]) -> None:
    declared = schema.get("type")
    if declared is not None:
        allowed = declared if isinstance(declared, list) else [declared]
        if not any(_TYPE_CHECKS.get(item, lambda _: True)(value) for item in allowed):
            findings.append(f"{path}: expected type {allowed}, got {type(value).__name__}")
            return
    if "enum" in schema and value not in schema["enum"]:
        findings.append(f"{path}: value not in enum {schema['enum']!r}")
    if isinstance(value, Mapping):
        for key in schema.get("required", ()):  # missing required keys
            if key not in value:
                findings.append(f"{path}.{key}: required property missing")
        properties = schema.get("properties", {})
        for key, subschema in properties.items():
            if key in value and isinstance(subschema, Mapping):
                _validate_node(value[key], subschema, f"{path}.{key}", findings)
    if isinstance(value, (list, tuple)):
        items = schema.get("items")
        if isinstance(items, Mapping):
            for index, item in enumerate(value):
                _validate_node(item, items, f"{path}[{index}]", findings)


async def complete_structured_checked(
    provider: "ModelProvider",
    *,
    system: str,
    messages: Sequence[ModelMessage],
    schema: Mapping[str, Any] | None,
    request_model: str,
    tools: Sequence[Mapping[str, Any]] | None = None,
    **provider_kwargs: Any,
) -> StructuredCompletion:
    """Call the provider, enforce non-empty content + canonical schema.

    Empty content or schema violations trigger AT MOST ONE repair retry with a
    corrective instruction; a second failure raises the typed error. There is
    no free-text fallback parse (official JSON Output can return empty content
    intermittently — that is a structural failure, never an answer).
    """

    attempt_messages = list(messages)
    last_findings: tuple[str, ...] = ()
    for attempt in range(2):
        try:
            completion = await provider.complete_structured(
                system=system,
                messages=attempt_messages,
                schema=schema,
                tools=tools,
                request_model=request_model,
                **provider_kwargs,
            )
            completion.require_non_empty()
        except EmptyModelContentError:
            if attempt == 1:
                raise
            attempt_messages = [
                *messages,
                ModelMessage(
                    role="user",
                    content=(
                        "Your previous reply was empty. Respond again with ONLY the"
                        " JSON object required by the schema."
                    ),
                ),
            ]
            continue
        findings = validate_canonical_schema(completion.content, schema)
        if not findings:
            return completion
        last_findings = findings
        if attempt == 0:
            attempt_messages = [
                *messages,
                ModelMessage(
                    role="user",
                    content=(
                        "Your previous JSON failed schema validation: "
                        + "; ".join(findings)
                        + ". Respond again with ONLY a corrected JSON object."
                    ),
                ),
            ]
    raise SchemaValidationError(
        "model output failed canonical schema validation after one repair retry",
        findings=last_findings,
    )


# ---------------------------------------------------------------------------
# DeepSeek OpenAI-compatible provider (default deployment binding)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DeepSeekModelProvider:
    """OpenAI-compatible chat-completions provider for DeepSeek V4 Pro.

    Every construction parameter comes from the environment (see
    :func:`build_model_provider_from_env`); nothing vendor-specific is
    hard-coded. ``reasoning_content`` (thinking mode is enabled by default on
    V4 Pro) is stripped inside :meth:`complete_structured` before the result
    object is built: it is never returned, stored, logged or traced.

    ``transport`` allows tests to inject an ``httpx.MockTransport``; unit
    tests must never reach the real network (Gate 0 model probe runs apart).
    """

    base_url: str
    api_key: str
    default_model: str
    timeout_seconds: float = 90.0
    thinking_enabled: bool = True
    name: str = "deepseek"
    supports_structured_output: bool = True
    transport: httpx.AsyncBaseTransport | None = None

    def _client(self) -> httpx.AsyncClient:
        # When no test transport is injected, use a default transport WITH
        # connection-level retries: DeepSeek intermittently drops the first cold
        # TLS connection, and a multi-stage analysis run makes many sequential
        # calls, so a single un-retried ConnectError would fail the whole run.
        # httpx retries only the connection establishment (before any bytes are
        # sent), so it stays idempotent and never replays a partial request.
        transport = self.transport
        if transport is None:
            transport = httpx.AsyncHTTPTransport(retries=3)
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            transport=transport,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

    async def complete_structured(
        self,
        *,
        system: str,
        messages: Sequence[ModelMessage],
        schema: Mapping[str, Any] | None,
        tools: Sequence[Mapping[str, Any]] | None,
        request_model: str,
    ) -> StructuredCompletion:
        payload: dict[str, Any] = {
            "model": request_model or self.default_model,
            "messages": [
                {"role": "system", "content": system},
                *({"role": item.role, "content": item.content} for item in messages),
            ],
            "stream": False,
            "response_format": {"type": "json_object"},
        }
        if tools:
            # Strict tool calls cover thinking and non-thinking modes alike.
            payload["tools"] = list(tools)
        async with self._client() as client:
            response = await client.post("/chat/completions", json=payload)
            response.raise_for_status()
            body = response.json()

        choice = (body.get("choices") or [{}])[0]
        message = dict(choice.get("message") or {})
        # reasoning_content is transient protocol data for ONE tool-call chain.
        # Drop it immediately; it must not survive into the returned object,
        # any persistence layer, any event, or any log line.
        message.pop("reasoning_content", None)

        raw_text = message.get("content") or ""
        if not raw_text.strip():
            raise EmptyModelContentError("model returned empty content")
        try:
            content = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise SchemaValidationError(f"model output is not valid JSON: {exc}") from exc
        if not isinstance(content, Mapping):
            raise SchemaValidationError("model output is not a JSON object")

        tool_calls = tuple(
            ToolCallRequest(
                call_id=str(item.get("id", "")),
                tool_name=str(item.get("function", {}).get("name", "")),
                arguments=json.loads(item.get("function", {}).get("arguments") or "{}"),
            )
            for item in message.get("tool_calls") or ()
        )
        return StructuredCompletion(
            content=content,
            raw_text=raw_text,
            request_model=payload["model"],
            response_model=str(body.get("model", "")),
            finish_reason=str(choice.get("finish_reason", "")),
            tool_calls=tool_calls,
        )

    async def complete_text(self, messages: Sequence[ModelMessage]) -> str:
        """Plain text completion (no schema); still drops reasoning_content."""

        payload = {
            "model": self.default_model,
            "messages": [{"role": item.role, "content": item.content} for item in messages],
            "stream": False,
        }
        async with self._client() as client:
            response = await client.post("/chat/completions", json=payload)
            response.raise_for_status()
            body = response.json()
        message = dict((body.get("choices") or [{}])[0].get("message") or {})
        message.pop("reasoning_content", None)
        text = message.get("content") or ""
        if not text.strip():
            raise EmptyModelContentError("model returned empty content")
        return text

    async def probe(self) -> ProviderProbe:
        """Read-only capability probe — Gate 0 / diagnostics only, never tests."""

        try:
            async with self._client() as client:
                response = await client.get("/models")
                ok = response.status_code == 200
        except httpx.HTTPError as exc:
            return ProviderProbe(
                provider=self.name,
                ok=False,
                supports_structured_output=self.supports_structured_output,
                detail=f"probe failed: {type(exc).__name__}",
            )
        return ProviderProbe(
            provider=self.name,
            ok=ok,
            supports_structured_output=self.supports_structured_output,
            detail=None if ok else f"probe returned HTTP {response.status_code}",
        )


class ModelProviderConfigError(RuntimeError):
    """A required MODEL_* environment variable is missing or malformed."""


def build_model_provider_from_env(
    env: Mapping[str, str] | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ModelProvider:
    """Construct the configured provider strictly from the environment.

    ``MODEL_PROVIDER=deepseek`` requires ``MODEL_BASE_URL``, ``MODEL_API_KEY``
    and ``MODEL_NAME`` — no silent hard-coded endpoint or model defaults.
    ``MODEL_PROVIDER=fixture`` (or ``FIXTURE_MODE=true``) yields the
    deterministic, network-free :class:`FixtureModelProvider`.
    """

    source = env if env is not None else os.environ
    provider_name = source.get("MODEL_PROVIDER", "").strip().lower()
    fixture_mode = source.get("FIXTURE_MODE", "").strip().lower() in ("1", "true", "yes")
    if provider_name == "fixture" or (not provider_name and fixture_mode) or (
        provider_name == "deepseek" and fixture_mode and not source.get("MODEL_API_KEY")
    ):
        return FixtureModelProvider()
    if provider_name != "deepseek":
        raise ModelProviderConfigError(
            f"unsupported MODEL_PROVIDER {provider_name!r}; expected 'deepseek' or 'fixture'"
        )
    missing = [
        key for key in ("MODEL_BASE_URL", "MODEL_API_KEY", "MODEL_NAME") if not source.get(key)
    ]
    if missing:
        raise ModelProviderConfigError(
            "missing required environment variables: " + ", ".join(missing)
        )
    return DeepSeekModelProvider(
        base_url=source["MODEL_BASE_URL"],
        api_key=source["MODEL_API_KEY"],
        default_model=source["MODEL_NAME"],
        timeout_seconds=float(source.get("MODEL_TIMEOUT_SECONDS", "90")),
        thinking_enabled=source.get("MODEL_THINKING_ENABLED", "true").strip().lower()
        in ("1", "true", "yes"),
        transport=transport,
    )


def build_secondary_model_provider_from_env(
    env: Mapping[str, str] | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ModelProvider | None:
    """Optional HETEROGENEOUS second brain for the adversarial stages.

    Configured via ``MODEL_B_BASE_URL`` / ``MODEL_B_API_KEY`` / ``MODEL_B_NAME``
    (any OpenAI-compatible endpoint - Kimi/GLM/Qwen all qualify, so the same
    client binds them). ALL three must be present; anything less returns None
    and the caller falls back to the primary model - the thinking trace then
    honestly labels the opposition as same-model. Never fabricates a provider.
    """

    source = env if env is not None else os.environ
    keys = ("MODEL_B_BASE_URL", "MODEL_B_API_KEY", "MODEL_B_NAME")
    if not all(source.get(key, "").strip() for key in keys):
        return None
    return DeepSeekModelProvider(
        base_url=source["MODEL_B_BASE_URL"],
        api_key=source["MODEL_B_API_KEY"],
        default_model=source["MODEL_B_NAME"],
        timeout_seconds=float(source.get("MODEL_B_TIMEOUT_SECONDS", source.get("MODEL_TIMEOUT_SECONDS", "90"))),
        thinking_enabled=False,  # adversary answers, it does not hide reasoning
        name="secondary",
        transport=transport,
    )


def build_model_provider_from_connector(
    *,
    base_url: str,
    api_key: str,
    model_name: str,
) -> ModelProvider:
    """Construct a provider from a workspace model connector (BYOK endpoint).

    Uses the same DeepSeekModelProvider which is OpenAI-compatible and works
    with any compliant endpoint (Kimi, Qwen, GPT, etc.).
    """

    return DeepSeekModelProvider(
        base_url=base_url,
        api_key=api_key,
        default_model=model_name,
        timeout_seconds=90.0,
        thinking_enabled=False,
        name="workspace-custom",
    )
