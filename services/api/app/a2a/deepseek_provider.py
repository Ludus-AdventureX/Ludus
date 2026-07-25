"""OpenAI-compatible DeepSeek binding for the A2A prototype surface.

The canonical ``app.agents.model_provider`` module ships only the protocol and
the fixture provider; a live binding never landed on the frozen surfaces. This
prototype-scoped implementation satisfies :class:`ModelProvider` using the
``openai`` client against the ``MODEL_*`` environment (same keys as
``.env.example``). Invariants preserved from the seam contract:

* empty content raises via ``require_non_empty`` at the caller, never here;
* DeepSeek ``reasoning_content`` is dropped on the floor — it is never parsed,
  stored, logged or surfaced;
* structured output uses JSON mode with the target schema embedded in the
  system prompt, so the binding works on the stable base URL without the
  strict-beta endpoint.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from typing import Any

from openai import AsyncOpenAI

from app.agents.model_provider import (
    ModelMessage,
    ModelProvider,
    ProviderProbe,
    StructuredCompletion,
)


def _parse_json_object(raw: str) -> Mapping[str, Any]:
    """Best-effort extraction of one JSON object from model text."""

    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        parsed = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            parsed = json.loads(text[start : end + 1])
        except ValueError:
            return {}
    return parsed if isinstance(parsed, Mapping) else {}


class DeepSeekModelProvider:
    """Live provider bound to an OpenAI-compatible chat-completions endpoint."""

    name = "deepseek"
    supports_structured_output = True

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model_name: str,
        timeout_seconds: float,
        thinking_enabled: bool,
    ) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key, base_url=base_url, timeout=timeout_seconds
        )
        self._model_name = model_name
        self._thinking_enabled = thinking_enabled

    async def complete_structured(
        self,
        *,
        system: str,
        messages: Sequence[ModelMessage],
        schema: Mapping[str, Any] | None,
        tools: Sequence[Mapping[str, Any]] | None,
        request_model: str,
    ) -> StructuredCompletion:
        system_text = system
        if schema is not None:
            system_text += (
                "\n\nReturn ONLY one JSON object that validates against this "
                "JSON Schema (no prose, no markdown fences):\n"
                + json.dumps(schema, ensure_ascii=False)
            )
        chat_messages: list[dict[str, str]] = [{"role": "system", "content": system_text}]
        for message in messages:
            role = message.role if message.role in {"user", "assistant", "system"} else "user"
            chat_messages.append({"role": role, "content": message.content})

        extra_body: dict[str, Any] = {}
        if not self._thinking_enabled:
            extra_body["thinking"] = {"type": "disabled"}

        response = await self._client.chat.completions.create(
            model=self._model_name,
            messages=chat_messages,
            response_format={"type": "json_object"},
            extra_body=extra_body or None,
        )
        choice = response.choices[0]
        raw_text = choice.message.content or ""
        # reasoning_content (thinking mode) is intentionally never read.
        return StructuredCompletion(
            content=_parse_json_object(raw_text),
            raw_text=raw_text,
            request_model=request_model,
            response_model=response.model or self._model_name,
            finish_reason=choice.finish_reason or "stop",
        )

    async def probe(self) -> ProviderProbe:
        try:
            await self._client.models.list()
        except Exception as exc:  # noqa: BLE001 - probe reports, never raises
            return ProviderProbe(
                provider=self.name,
                ok=False,
                supports_structured_output=True,
                detail=f"model endpoint unreachable: {type(exc).__name__}",
            )
        return ProviderProbe(
            provider=self.name, ok=True, supports_structured_output=True
        )


def build_model_provider() -> ModelProvider:
    """MODEL_* env -> live DeepSeek provider; fail fast on a missing key.

    Fixture selection stays with the caller (tests inject
    ``FixtureModelProvider`` directly), so a live deployment can never silently
    downgrade to canned answers.
    """

    api_key = os.getenv("MODEL_API_KEY", "").strip()
    if not api_key:
        raise ValueError("MODEL_API_KEY is not configured")
    return DeepSeekModelProvider(
        api_key=api_key,
        base_url=os.getenv("MODEL_BASE_URL", "https://api.deepseek.com").strip(),
        model_name=os.getenv("MODEL_NAME", "deepseek-v4-pro").strip(),
        timeout_seconds=float(os.getenv("MODEL_TIMEOUT_SECONDS", "90") or 90),
        thinking_enabled=(
            os.getenv("MODEL_THINKING_ENABLED", "true").strip().lower()
            in {"1", "true", "yes", "on"}
        ),
    )
