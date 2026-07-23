"""Worker runner skeleton.

Executes one producer-role worker stage against a :class:`ModelProvider`:

* builds an isolated, role-scoped context and tool envelope;
* charges the budget before the model call and each tool call;
* detects empty content and performs at most one schema-repair retry;
* records a tool trace that never contains ``reasoning_content`` or raw secrets.

The runner does not own the AnalysisRun state machine, SSE events or persistence -
those are case_api_data (Task 9). It returns a structured :class:`WorkerResult`
that the worker/state machine turns into stage artifacts and events.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .budget import BudgetLedger
from .context import RunContext, WorkerInputs
from .errors import EmptyModelContentError, SchemaValidationError
from .model_provider import ModelMessage, ModelProvider, StructuredCompletion
from .tool_registry import ToolRegistry


@dataclass(frozen=True, slots=True)
class WorkerDefinition:
    """A worker's static definition, read from the published method pack."""

    role: str
    prompt_ref: str
    output_schema_id: str
    responsibilities: tuple[str, ...] = ()
    allowed_tools: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class ToolTraceEntry:
    """One tool invocation summary for the append-only trace (no page bodies)."""

    tool_name: str
    ok: bool
    result_summary: str


@dataclass(slots=True)
class WorkerResult:
    """Structured outcome of a worker stage."""

    role: str
    output: Mapping[str, Any]
    attempts: int
    tool_trace: list[ToolTraceEntry] = field(default_factory=list)
    budget_snapshot: Mapping[str, float] = field(default_factory=dict)


class WorkerRunner:
    """Runs a single worker stage with structured-output + empty-content handling."""

    def __init__(
        self,
        *,
        provider: ModelProvider,
        registry: ToolRegistry,
        prompt_loader: "PromptLoader",
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._prompts = prompt_loader

    async def run_worker(
        self,
        *,
        definition: WorkerDefinition,
        run_context: RunContext,
        budget: BudgetLedger,
        inputs: WorkerInputs,
        output_schema: Mapping[str, Any] | None = None,
        fixture_key: str | None = None,
    ) -> WorkerResult:
        """Execute one worker stage and return its validated structured output."""

        role_context = run_context.for_role(definition.role, definition.allowed_tools)
        system = self._prompts.load(definition.prompt_ref)
        messages = self._build_messages(inputs)

        budget.check_elapsed()
        final, attempts = await self._complete_with_repair(
            system=system,
            messages=messages,
            schema=output_schema,
            budget=budget,
            request_model=role_context.method.id,
            fixture_key=fixture_key,
        )

        return WorkerResult(
            role=definition.role,
            output=dict(final.content),
            attempts=attempts,
            tool_trace=[],
            budget_snapshot=budget.snapshot(),
        )

    async def _complete_with_repair(
        self,
        *,
        system: str,
        messages: Sequence[ModelMessage],
        schema: Mapping[str, Any] | None,
        budget: BudgetLedger,
        request_model: str,
        fixture_key: str | None,
    ) -> tuple[StructuredCompletion, int]:
        """At most one repair retry for empty / structurally invalid content.

        Returns the accepted completion and the number of model attempts (1 or 2).
        """

        last_error: Exception | None = None
        for attempt in range(2):
            budget.charge("max_model_calls")
            completion = await self._invoke(
                system=system,
                messages=messages,
                schema=schema,
                request_model=request_model,
                fixture_key=fixture_key,
            )
            try:
                completion.require_non_empty()
            except EmptyModelContentError as exc:
                last_error = exc
                messages = self._with_repair_hint(messages)
                continue
            return completion, attempt + 1
        raise SchemaValidationError(
            f"model produced empty/invalid content after repair retry: {last_error}"
        )

    async def _invoke(
        self,
        *,
        system: str,
        messages: Sequence[ModelMessage],
        schema: Mapping[str, Any] | None,
        request_model: str,
        fixture_key: str | None,
    ) -> StructuredCompletion:
        kwargs: dict[str, Any] = {
            "system": system,
            "messages": messages,
            "schema": schema,
            "tools": None,
            "request_model": request_model,
        }
        if fixture_key is not None:
            kwargs["fixture_key"] = fixture_key
        return await self._provider.complete_structured(**kwargs)

    @staticmethod
    def _build_messages(inputs: WorkerInputs) -> list[ModelMessage]:
        body = [inputs.frozen_summary]
        if inputs.sibling_summaries:
            body.append("\n".join(inputs.sibling_summaries))
        return [ModelMessage(role="user", content="\n\n".join(body))]

    @staticmethod
    def _with_repair_hint(messages: Sequence[ModelMessage]) -> list[ModelMessage]:
        hint = ModelMessage(
            role="system",
            content="Previous output was empty or invalid JSON. Return only a valid "
            "JSON object matching the required schema.",
        )
        return [*messages, hint]


class PromptLoader:
    """Loads a worker/lens prompt from a hash-verified published method pack."""

    def __init__(self, read_text) -> None:  # noqa: ANN001 - duck-typed pack reader
        self._read_text = read_text

    def load(self, prompt_ref: str) -> str:
        return self._read_text(prompt_ref)
