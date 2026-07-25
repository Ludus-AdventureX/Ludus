"""Candidate memory extraction from daily dialogue (Task 5 Step 4).

Extraction results are written ONLY to ``candidate_revisions`` — never to
``dossier_entries`` or ``case_versions``. Each candidate stores the
``base_dossier_version`` (and ``base_case_version`` when a Case is bound) so
the confirm endpoint can validate both inside one transaction.

Besides facts, constraints and assumptions, the extractor also surfaces
candidate decision questions and options for user confirmation. Explicit
opt-out instructions ("临时想法", "不要记住", …) deterministically yield an
empty candidate set without any model call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.model_provider import (
    ModelMessage,
    ModelProvider,
    complete_structured_checked,
)
from app.types import DossierStatementType, EntryStatus

# Deterministic opt-out markers (task charter: explicit instructions must
# produce an empty candidate list).
OPT_OUT_MARKERS: tuple[str, ...] = (
    "临时想法",
    "不要记住",
    "不用记住",
    "别记住",
    "不要记录",
    "off the record",
    "do not remember",
    "don't remember this",
)

# Canonical schema (JSON-schema subset) for the structured extraction reply.
EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["candidates"],
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["statementType", "content"],
                "properties": {
                    "statementType": {
                        "type": "string",
                        "enum": [item.value for item in DossierStatementType],
                    },
                    "content": {"type": "string"},
                    "scope": {"type": "string", "enum": ["subject", "case"]},
                },
            },
        },
        "decisionQuestions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["question"],
                "properties": {
                    "question": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}

_SYSTEM_PROMPT = (
    "You extract long-term decision memory candidates from one user message. "
    "Classify each into fact / constraint / assumption / judgment / preference "
    "/ unknown, keep content concise and declarative, and also list candidate "
    "decision questions with their options when the message implies a choice. "
    "Reply with ONLY a JSON object matching the given schema."
)


@dataclass(frozen=True)
class ExtractedCandidate:
    """One proposed dossier statement. Status is always ``candidate``."""

    statement_type: str
    content: str
    scope: str = "subject"
    status: str = EntryStatus.CANDIDATE.value


@dataclass(frozen=True)
class ExtractionResult:
    candidates: tuple[ExtractedCandidate, ...] = ()
    decision_questions: tuple[dict[str, Any], ...] = ()

    def __iter__(self):
        return iter(self.candidates)

    def __getitem__(self, index: int) -> ExtractedCandidate:
        return self.candidates[index]

    def __len__(self) -> int:
        return len(self.candidates)

    def to_proposals(self, *, case_bound: bool = False) -> list[dict[str, Any]]:
        """Project onto CandidateRevision.proposals (operation=add)."""

        question_scope = "case" if case_bound else "subject"
        proposals = [
            {
                "operation": "add",
                "entry": {
                    "scope": item.scope,
                    "statementType": item.statement_type,
                    "content": item.content,
                    "sourceType": "ai_candidate",
                },
            }
            for item in self.candidates
        ]
        proposals.extend(
            {
                "operation": "add",
                "entry": {
                    "scope": question_scope,
                    "statementType": DossierStatementType.UNKNOWN.value,
                    "content": _question_text(question),
                    "sourceType": "ai_candidate",
                    "decisionQuestion": question,
                },
            }
            for question in self.decision_questions
        )
        return proposals


def _question_text(question: dict[str, Any]) -> str:
    options = question.get("options") or []
    if options:
        return f"候选决策问题：{question['question']}（备选项：{'、'.join(options)}）"
    return f"候选决策问题：{question['question']}"


def is_opt_out(message: str) -> bool:
    lowered = message.lower()
    return any(marker in message or marker in lowered for marker in OPT_OUT_MARKERS)


@dataclass
class MemoryExtractor:
    """Structured extraction over the provider-neutral ModelProvider seam."""

    provider: ModelProvider
    request_model: str = ""

    async def extract(self, message: str, *, case_bound: bool = False) -> ExtractionResult:
        if is_opt_out(message):
            # Explicit "don't remember" instruction: no candidates, no model call.
            return ExtractionResult()

        completion = await complete_structured_checked(
            self.provider,
            system=_SYSTEM_PROMPT,
            messages=[ModelMessage(role="user", content=message)],
            schema=EXTRACTION_SCHEMA,
            request_model=self.request_model,
        )
        payload = completion.content
        candidates = tuple(
            ExtractedCandidate(
                statement_type=item["statementType"],
                content=item["content"],
                scope=item.get("scope", "case" if case_bound else "subject"),
            )
            for item in payload.get("candidates", [])
        )
        decision_questions = tuple(dict(item) for item in payload.get("decisionQuestions", []))
        return ExtractionResult(candidates=candidates, decision_questions=decision_questions)
