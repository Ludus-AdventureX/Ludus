"""Question clarifier (R2): help the founder ASK THE RIGHT QUESTION first.

Grey-goo question-reframing discipline, run BEFORE any charter exists. Three
verdicts on the raw decision question:

* pseudo-decision - is this a real open decision, or a decided one shopping
  for endorsement?
* false dilemma - is the either/or framing hiding a third option?
* reversibility - Type 1 (irreversible: worth a full analysis) vs Type 2
  (reversible: decide fast, instrument a retrospective instead).

The model proposes; deterministic normalization bounds every field. This
module never creates a charter, never persists anything - it returns an
advisory card the student may adopt (the adopted rewrite then travels into
the charter as the decision question).
"""

from __future__ import annotations

from typing import Any

from app.agents.model_provider import (
    ModelMessage,
    ModelProvider,
    complete_structured_checked,
)

CLARIFIER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["pseudoDecision", "falseDilemma", "reversibility", "refinedQuestion"],
    "properties": {
        # Text fields tolerate null/omission - a verdict without prose is
        # honest and normalize_clarifier_output bounds everything anyway.
        # Only the verdicts themselves are hard-required.
        "pseudoDecision": {
            "type": "object",
            "required": ["verdict"],
            "properties": {
                "verdict": {"type": "boolean"},
                "reason": {"type": ["string", "null"]},
            },
        },
        "falseDilemma": {
            "type": "object",
            "required": ["verdict"],
            "properties": {
                "verdict": {"type": "boolean"},
                "thirdOption": {"type": ["string", "null"]},
            },
        },
        "reversibility": {
            "type": "object",
            "required": ["type"],
            "properties": {
                "type": {"type": "string", "enum": ["type1", "type2"]},
                "advice": {"type": ["string", "null"]},
            },
        },
        "refinedQuestion": {"type": ["string", "null"]},
    },
}

_SYSTEM_PROMPT = (
    "You are Ludus's question clarifier. Founders often ask the WRONG question; "
    "your job is to fix the question before any analysis is spent on it. "
    "Return ONLY a JSON object matching the required schema. Judge honestly: "
    "pseudoDecision.verdict=true ONLY when the phrasing reveals the asker has "
    "already decided and wants endorsement (cite the phrasing in reason). "
    "falseDilemma.verdict=true ONLY when a concrete, actionable third option "
    "exists - name it in thirdOption, or leave thirdOption empty. "
    "reversibility: type1 = hard/costly to undo (worth deep analysis), "
    "type2 = cheap to undo (advise deciding fast + scheduling a review). "
    "refinedQuestion: rewrite the question so it is decidable, falsifiable and "
    "framed around the real tradeoff. Answer in the user's language "
    "(Chinese question -> Chinese output). Never flatter; never invent facts."
)


def _text(value: Any, limit: int = 400) -> str:
    return str(value).strip()[:limit] if isinstance(value, str) else ""


def normalize_clarifier_output(content: dict[str, Any] | Any, question: str) -> dict[str, Any]:
    """Deterministic bounds over the model's card; never invents verdicts."""

    content = content if isinstance(content, dict) else {}
    pseudo = content.get("pseudoDecision") if isinstance(content.get("pseudoDecision"), dict) else {}
    dilemma = content.get("falseDilemma") if isinstance(content.get("falseDilemma"), dict) else {}
    reversibility = (
        content.get("reversibility") if isinstance(content.get("reversibility"), dict) else {}
    )
    rev_type = reversibility.get("type")
    if rev_type not in ("type1", "type2"):
        rev_type = "type1"  # unknown reversibility defaults to the cautious path
    refined = _text(content.get("refinedQuestion")) or question.strip()[:400]
    return {
        "pseudoDecision": {
            "verdict": bool(pseudo.get("verdict")),
            "reason": _text(pseudo.get("reason")),
        },
        "falseDilemma": {
            "verdict": bool(dilemma.get("verdict")),
            "thirdOption": _text(dilemma.get("thirdOption")),
        },
        "reversibility": {
            "type": rev_type,
            "advice": _text(reversibility.get("advice")),
        },
        "refinedQuestion": refined,
        "originalQuestion": question.strip()[:400],
    }


async def clarify_question(
    provider: ModelProvider,
    *,
    question: str,
    goals: list[str] | None = None,
    constraints: list[str] | None = None,
) -> dict[str, Any]:
    """One bounded model pass + deterministic normalization."""

    parts = [f"Decision question: {question.strip()[:400]}"]
    if goals:
        parts.append("Goals: " + "; ".join(g.strip()[:200] for g in goals[:3]))
    if constraints:
        parts.append("Constraints: " + "; ".join(c.strip()[:200] for c in constraints[:3]))
    completion = await complete_structured_checked(
        provider,
        system=_SYSTEM_PROMPT,
        messages=(ModelMessage(role="user", content="\n".join(parts)),),
        schema=CLARIFIER_SCHEMA,
        request_model=getattr(provider, "default_model", None) or "default",
    )
    return normalize_clarifier_output(dict(completion.content), question)
