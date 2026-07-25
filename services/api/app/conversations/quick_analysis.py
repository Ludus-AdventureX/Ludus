"""Quick framework analysis (Task 5 Step 5).

``QuickAnalysisResult`` is generated ONLY from confirmed dossier entries. It
never runs MethodRouter, never creates an AnalysisCharter or a formal
AnalysisRun, and never produces a formal report, PDF or sandbox. Every
persisted row and projection permanently carries the "非正式方法输出" flag
(``formality`` is a single-member enum).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.model_provider import (
    ModelMessage,
    ModelProvider,
    complete_structured_checked,
)
from app.models import Conversation, DossierEntry, QuickAnalysisResult
from app.types import QuickAnalysisFormality

# The permanent non-formal marker surfaced with every projection (the frozen
# table stores formality as a single-member enum; the label is presentation).
NON_FORMAL_DISCLAIMER = "非正式方法输出"

QUICK_ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["judgment", "counterArguments", "keyUnknowns", "nextActions"],
    "properties": {
        "judgment": {"type": "string"},
        "counterArguments": {"type": "array", "items": {"type": "string"}},
        "keyUnknowns": {"type": "array", "items": {"type": "string"}},
        "nextActions": {"type": "array", "items": {"type": "string"}},
    },
}

_SYSTEM_PROMPT = (
    "You produce a short, non-formal quick analysis strictly from the CONFIRMED "
    "dossier entries provided. Return a structured judgment, the strongest "
    "counter-arguments, the key unknowns and concrete next actions. Do not "
    "invent facts beyond the provided entries. Reply with ONLY a JSON object "
    "matching the given schema."
)


def _entries_digest(entries: list[DossierEntry]) -> str:
    lines = [
        f"- [{entry.statement_type.value}/{entry.scope.value}] {entry.content}"
        for entry in entries
    ]
    return "\n".join(lines) if lines else "(no confirmed entries yet)"


async def generate_quick_analysis(
    session: AsyncSession,
    provider: ModelProvider,
    *,
    conversation: Conversation,
    confirmed_entries: list[DossierEntry],
    source_dossier_version: int,
    request_model: str = "",
    question: str | None = None,
) -> QuickAnalysisResult:
    """Generate + persist one non-formal QuickAnalysisResult in the session."""

    prompt = (
        "Confirmed dossier entries:\n"
        + _entries_digest(confirmed_entries)
        + ("\n\nUser focus: " + question if question else "")
    )
    completion = await complete_structured_checked(
        provider,
        system=_SYSTEM_PROMPT,
        messages=[ModelMessage(role="user", content=prompt)],
        schema=QUICK_ANALYSIS_SCHEMA,
        request_model=request_model,
    )
    payload = completion.content
    result = QuickAnalysisResult(
        workspace_id=conversation.workspace_id,
        conversation_id=conversation.id,
        decision_case_id=conversation.decision_case_id,
        formality=QuickAnalysisFormality.NON_FORMAL,
        judgment=str(payload["judgment"]),
        counter_arguments=[str(item) for item in payload["counterArguments"]],
        key_unknowns=[str(item) for item in payload["keyUnknowns"]],
        next_actions=[str(item) for item in payload["nextActions"]],
    )
    session.add(result)
    await session.flush()
    return result


def quick_analysis_projection(result: QuickAnalysisResult) -> dict[str, Any]:
    """Frozen QuickAnalysisResult wire shape (06-data-model) + disclaimer."""

    return {
        "id": str(result.id),
        "workspaceId": str(result.workspace_id),
        "conversationId": str(result.conversation_id),
        "decisionCaseId": (
            str(result.decision_case_id) if result.decision_case_id is not None else None
        ),
        "formality": result.formality.value,
        "judgment": result.judgment,
        "counterArguments": list(result.counter_arguments),
        "keyUnknowns": list(result.key_unknowns),
        "nextActions": list(result.next_actions),
        "disclaimer": NON_FORMAL_DISCLAIMER,
        "createdAt": result.created_at.isoformat(),
    }
