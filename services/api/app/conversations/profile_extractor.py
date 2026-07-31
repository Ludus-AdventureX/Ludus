"""Profile extractor: distills decision-maker and question profiles from
conversation history.

Called as best-effort enrichment after each message round. Failures never
block the conversation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.agents.model_provider import (
    ModelMessage,
    ModelProvider,
    complete_structured_checked,
)

PROFILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["decisionMaker", "question"],
    "properties": {
        "decisionMaker": {
            "type": "object",
            "required": ["riskTolerance", "timeConstraints", "resourceConstraints",
                         "expressedPreferences", "bottomLines"],
            "properties": {
                "riskTolerance": {"type": "string", "enum": ["conservative", "moderate", "aggressive"]},
                "timeConstraints": {"type": "array", "items": {"type": "string"}},
                "resourceConstraints": {"type": "array", "items": {"type": "string"}},
                "expressedPreferences": {"type": "array", "items": {"type": "string"}},
                "bottomLines": {"type": "array", "items": {"type": "string"}},
            },
        },
        "question": {
            "type": "object",
            "required": ["coreTradeoff", "confirmedFacts", "keyAssumptions",
                         "unknowns", "options", "refinedQuestion"],
            "properties": {
                "coreTradeoff": {"type": "string"},
                "confirmedFacts": {"type": "array", "items": {"type": "string"}},
                "keyAssumptions": {"type": "array", "items": {"type": "string"}},
                "unknowns": {"type": "array", "items": {"type": "string"}},
                "options": {"type": "array", "items": {"type": "string"}},
                "refinedQuestion": {"type": "string"},
            },
        },
    },
}

_SYSTEM_PROMPT = (
    "\u4f60\u662f Ludus \u753b\u50cf\u6574\u7406 Agent\u3002\u4f60\u7684\u4efb\u52a1\u662f\u4ece\u7528\u6237\u4e0e\u51b3\u7b56\u52a9\u624b\u7684\u5bf9\u8bdd\u5386\u53f2\u4e2d\uff0c"
    "\u63d0\u70bc\u51fa\u4e24\u4efd\u7ed3\u6784\u5316\u753b\u50cf\u3002\n\n"
    "## \u51b3\u7b56\u8005\u753b\u50cf\uff08decisionMaker\uff09\n"
    "\u4ece\u5bf9\u8bdd\u4e2d\u63a8\u65ad\u51b3\u7b56\u4eba\u7684\uff1a\n"
    "- riskTolerance\uff1a\u98ce\u9669\u503e\u5411\uff08conservative/moderate/aggressive\uff09\n"
    "- timeConstraints\uff1a\u65f6\u95f4\u7ea6\u675f\n"
    "- resourceConstraints\uff1a\u8d44\u6e90\u7ea6\u675f\n"
    "- expressedPreferences\uff1a\u660e\u786e\u8868\u8fbe\u7684\u504f\u597d\n"
    "- bottomLines\uff1a\u4e0d\u53ef\u903e\u8d8a\u7684\u5e95\u7ebf\n\n"
    "## \u95ee\u9898\u753b\u50cf\uff08question\uff09\n"
    "- coreTradeoff\uff1a\u6838\u5fc3\u53d6\u820d\uff08\u4e00\u53e5\u8bdd\uff09\n"
    "- confirmedFacts\uff1a\u5df2\u786e\u8ba4\u7684\u4e8b\u5b9e\n"
    "- keyAssumptions\uff1a\u5173\u952e\u5047\u8bbe\n"
    "- unknowns\uff1a\u5f85\u9a8c\u8bc1\u7684\u672a\u77e5\u9879\n"
    "- options\uff1a\u5f53\u524d\u9009\u9879\u6e05\u5355\n"
    "- refinedQuestion\uff1a\u7ecf\u8fc7\u5bf9\u8bdd\u6f84\u6e05\u540e\u7684\u7cbe\u70bc\u95ee\u9898\n\n"
    "\u89c4\u5219\uff1a1.\u53ea\u4ece\u5bf9\u8bdd\u5df2\u6709\u4fe1\u606f\u63d0\u70bc\uff0c\u4e0d\u7f16\u9020\u3002"
    "2.\u5bf9\u8bdd\u592a\u77ed\u65e0\u6cd5\u5224\u65ad\u67d0\u9879\uff0c\u7ed9\u7a7a\u6570\u7ec4\u6216\u7a7a\u5b57\u7b26\u4e32\u3002"
    "3.\u8f93\u51fa\u4e25\u683c\u5339\u914d JSON schema\u3002"
    "4.\u4f7f\u7528\u4e2d\u6587\u3002"
)


def _format_messages(messages: Sequence[Mapping[str, Any]]) -> str:
    lines: list[str] = []
    for msg in messages[-50:]:
        role = msg.get("role", "user")
        content = str(msg.get("content", ""))[:800]
        prefix = "\u7528\u6237" if role == "user" else "\u7cfb\u7edf"
        lines.append(f"[{prefix}] {content}")
    return "\n".join(lines)


async def extract_profiles(
    provider: ModelProvider,
    messages: Sequence[Mapping[str, Any]],
    confirmed_entries: Sequence[str] | None = None,
) -> dict[str, Any] | None:
    if not messages:
        return None
    context_parts = [_format_messages(messages)]
    if confirmed_entries:
        context_parts.append("\n[\u5df2\u786e\u8ba4\u6863\u6848\u6761\u76ee]\n" + "\n".join(
            f"- {entry}" for entry in confirmed_entries[:20]
        ))
    try:
        completion = await complete_structured_checked(
            provider,
            system=_SYSTEM_PROMPT,
            messages=(ModelMessage(role="user", content="\n".join(context_parts)),),
            schema=PROFILE_SCHEMA,
            request_model="",
        )
        content = completion.content
        if not isinstance(content.get("decisionMaker"), Mapping):
            return None
        if not isinstance(content.get("question"), Mapping):
            return None
        return dict(content)
    except Exception:
        return None
