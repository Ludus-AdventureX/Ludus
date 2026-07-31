"""Deterministic fixture fallback for the CONVERSATION-side model calls.

The worker's key-free path already binds ``synthesize_stage_response``, but the
API-side companion reply and question clarifier previously received a BARE
``FixtureModelProvider`` — so in a fixture deployment every chat message and
every quality check died with ``EmptyModelContentError`` (surfaced to the user
as a 502). This module gives those two call sites one deterministic superset
payload: it satisfies the required fields of both wire schemas at once (the
canonical validator ignores unknown keys), and every sentence carries the
``[fixture]`` prefix so it can never pass for live output.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .model_provider import FixtureModelProvider, ModelMessage, ModelProvider


def _conversation_fixture_response(messages: Sequence[ModelMessage]) -> Mapping[str, Any]:
    # Deterministic on purpose: the demo reply never mirrors user text back as
    # if it were analysis, and the clarifier verdicts stay conservative.
    del messages
    return {
        # companion reply schema (POST /cases/{id}/messages)
        "assistantMessage": (
            "[fixture] 演示模式回应：你的札记已保存。当前部署未接入真实模型，"
            "系统不会伪造分析性回应；候选提炼与画像更新在本条消息上跳过。"
        ),
        # clarifier card schema (POST /cases/{id}/question-clarifier)
        "pseudoDecision": {"verdict": False, "reason": "[fixture] 演示模式不做真实判定"},
        "falseDilemma": {"verdict": False, "thirdOption": None},
        "reversibility": {"type": "type1", "advice": "[fixture] 演示模式默认按难逆决定谨慎处理"},
        "refinedQuestion": None,
    }


def with_conversation_fixture_fallback(provider: ModelProvider) -> ModelProvider:
    """Bind the deterministic conversation fallback once on fixture providers."""

    if isinstance(provider, FixtureModelProvider) and provider.fallback is None:
        provider.fallback = _conversation_fixture_response
    return provider
