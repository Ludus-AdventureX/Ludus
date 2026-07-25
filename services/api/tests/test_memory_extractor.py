"""Task 5 owner tests: structured extraction + provider seam.

Zero real network: every provider here is either the deterministic fixture
provider or a DeepSeek provider bound to an httpx.MockTransport. The Gate 0
model probe runs separately and is not part of this suite.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.agents.errors import EmptyModelContentError, SchemaValidationError
from app.agents.model_provider import (
    DeepSeekModelProvider,
    FixtureModelProvider,
    ModelMessage,
    ModelProviderConfigError,
    build_model_provider_from_env,
    complete_structured_checked,
    validate_canonical_schema,
)
from app.conversations.memory_extractor import (
    EXTRACTION_SCHEMA,
    MemoryExtractor,
    is_opt_out,
)

RESOURCE_STATEMENT = "我们最多只能投入两名工程师六个月"


@pytest.fixture
def fixture_model() -> FixtureModelProvider:
    provider = FixtureModelProvider()
    provider.register(
        RESOURCE_STATEMENT,
        {
            "candidates": [
                {
                    "statementType": "constraint",
                    "content": "工程资源上限为2名工程师、6个月",
                    "scope": "subject",
                }
            ],
            "decisionQuestions": [],
        },
    )
    return provider


@pytest.fixture
def extractor(fixture_model: FixtureModelProvider) -> MemoryExtractor:
    return MemoryExtractor(provider=fixture_model)


# ---------------------------------------------------------------------------
# 18-plan Task 5 Step 1: structured extraction
# ---------------------------------------------------------------------------


async def test_resource_statement_becomes_candidate(
    extractor: MemoryExtractor, fixture_model: FixtureModelProvider
) -> None:
    result = await extractor.extract(RESOURCE_STATEMENT)
    assert result[0].statement_type == "constraint"
    assert result[0].status == "candidate"
    assert result[0].content == "工程资源上限为2名工程师、6个月"


async def test_decision_question_and_options_become_candidates(
    fixture_model: FixtureModelProvider,
) -> None:
    message = "到底应该先做救援市场还是家庭市场？"
    fixture_model.register(
        message,
        {
            "candidates": [],
            "decisionQuestions": [
                {"question": "优先进入哪个市场？", "options": ["救援市场", "家庭服务市场"]}
            ],
        },
    )
    extractor = MemoryExtractor(provider=fixture_model)
    result = await extractor.extract(message, case_bound=True)
    assert len(result.decision_questions) == 1
    proposals = result.to_proposals(case_bound=True)
    assert len(proposals) == 1
    assert "候选决策问题" in proposals[0]["entry"]["content"]
    assert "救援市场" in proposals[0]["entry"]["content"]


@pytest.mark.parametrize(
    "message",
    [
        "这只是一个临时想法：也许可以做水下版本",
        "不要记住这句话，预算数字还没定",
        "off the record: we may pivot entirely",
    ],
)
async def test_explicit_opt_out_returns_empty_candidates(
    fixture_model: FixtureModelProvider, message: str
) -> None:
    extractor = MemoryExtractor(provider=fixture_model)
    result = await extractor.extract(message)
    assert len(result) == 0
    assert result.to_proposals() == []
    assert is_opt_out(message)


# ---------------------------------------------------------------------------
# Canonical schema validation + single repair retry
# ---------------------------------------------------------------------------


def test_validate_canonical_schema_reports_findings() -> None:
    findings = validate_canonical_schema(
        {"candidates": [{"statementType": "constraint"}]}, EXTRACTION_SCHEMA
    )
    assert any("content" in finding for finding in findings)
    assert validate_canonical_schema(
        {"candidates": [{"statementType": "constraint", "content": "x"}]},
        EXTRACTION_SCHEMA,
    ) == ()


class _CountingProvider:
    """Wraps a provider to count calls (FixtureModelProvider uses slots)."""

    def __init__(self, inner: FixtureModelProvider) -> None:
        self.inner = inner
        self.name = inner.name
        self.supports_structured_output = inner.supports_structured_output
        self.calls: list[str] = []

    async def complete_structured(self, **kwargs):
        self.calls.append(kwargs["messages"][-1].content)
        return await self.inner.complete_structured(**kwargs)

    async def probe(self):
        return await self.inner.probe()


async def test_schema_violation_triggers_exactly_one_repair_retry(
    fixture_model: FixtureModelProvider,
) -> None:
    counting = _CountingProvider(fixture_model)
    # The fixture returns {} for unknown keys -> empty content -> repair retry
    # also resolves to empty -> typed failure after exactly two attempts.
    with pytest.raises(EmptyModelContentError):
        await complete_structured_checked(
            counting,
            system="s",
            messages=[ModelMessage(role="user", content="unregistered")],
            schema=EXTRACTION_SCHEMA,
            request_model="fixture",
        )
    assert len(counting.calls) == 2


def _deepseek_transport(responses: list[dict[str, Any]]) -> httpx.MockTransport:
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        body = queue.pop(0) if len(queue) > 1 else queue[0]
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handler)


def _chat_body(content: str | None, *, reasoning: str | None = None) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if reasoning is not None:
        message["reasoning_content"] = reasoning
    return {
        "model": "deepseek-v4-pro-20260701",
        "choices": [{"message": message, "finish_reason": "stop"}],
    }


def _provider(transport: httpx.MockTransport) -> DeepSeekModelProvider:
    return DeepSeekModelProvider(
        base_url="http://deepseek.mock",
        api_key="test-key-not-real",
        default_model="deepseek-v4-pro",
        transport=transport,
    )


async def test_deepseek_empty_content_then_repair_succeeds() -> None:
    good = json.dumps({"candidates": [], "decisionQuestions": []})
    provider = _provider(
        _deepseek_transport([_chat_body(""), _chat_body(good)])
    )
    completion = await complete_structured_checked(
        provider,
        system="s",
        messages=[ModelMessage(role="user", content="hello")],
        schema=EXTRACTION_SCHEMA,
        request_model="deepseek-v4-pro",
    )
    assert completion.content == {"candidates": [], "decisionQuestions": []}


async def test_deepseek_double_schema_failure_raises_without_free_text_fallback() -> None:
    # Both replies are valid JSON but violate the canonical schema; there must
    # be no free-text salvage, only the typed error after one repair retry.
    bad = json.dumps({"unexpected": True})
    provider = _provider(_deepseek_transport([_chat_body(bad), _chat_body(bad)]))
    with pytest.raises(SchemaValidationError):
        await complete_structured_checked(
            provider,
            system="s",
            messages=[ModelMessage(role="user", content="hello")],
            schema=EXTRACTION_SCHEMA,
            request_model="deepseek-v4-pro",
        )


async def test_reasoning_content_is_dropped_and_never_logged(caplog) -> None:
    hidden = "SECRET-CHAIN-OF-THOUGHT-MUST-NOT-LEAK"
    good = json.dumps({"candidates": [], "decisionQuestions": []})
    provider = _provider(
        _deepseek_transport([_chat_body(good, reasoning=hidden)])
    )
    with caplog.at_level("DEBUG"):
        completion = await provider.complete_structured(
            system="s",
            messages=[ModelMessage(role="user", content="hi")],
            schema=EXTRACTION_SCHEMA,
            tools=None,
            request_model="deepseek-v4-pro",
        )
    # Not on the result object (the type has no such attribute), not in the
    # raw text, not anywhere in captured logs.
    assert not hasattr(completion, "reasoning_content")
    assert hidden not in completion.raw_text
    assert hidden not in json.dumps(dict(completion.content), ensure_ascii=False)
    assert hidden not in caplog.text


# ---------------------------------------------------------------------------
# Env factory: all construction parameters come from the environment
# ---------------------------------------------------------------------------


def test_env_factory_builds_deepseek_from_env_only() -> None:
    provider = build_model_provider_from_env(
        {
            "MODEL_PROVIDER": "deepseek",
            "MODEL_BASE_URL": "http://deepseek.mock",
            "MODEL_API_KEY": "k",
            "MODEL_NAME": "deepseek-v4-pro",
            "MODEL_TIMEOUT_SECONDS": "5",
            "MODEL_THINKING_ENABLED": "true",
        }
    )
    assert isinstance(provider, DeepSeekModelProvider)
    assert provider.base_url == "http://deepseek.mock"
    assert provider.default_model == "deepseek-v4-pro"
    assert provider.timeout_seconds == 5.0
    assert provider.thinking_enabled is True


def test_env_factory_requires_all_deepseek_parameters() -> None:
    with pytest.raises(ModelProviderConfigError):
        build_model_provider_from_env({"MODEL_PROVIDER": "deepseek"})


def test_env_factory_fixture_mode_yields_fixture_provider() -> None:
    provider = build_model_provider_from_env({"MODEL_PROVIDER": "fixture"})
    assert isinstance(provider, FixtureModelProvider)
    provider = build_model_provider_from_env({"FIXTURE_MODE": "true"})
    assert isinstance(provider, FixtureModelProvider)
