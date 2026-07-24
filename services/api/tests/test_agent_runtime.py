"""Formal QA for the Task 7 agent runtime seam (lane matrix rows AR-01..AR-09 subset).

Covers the QA_QUEUE_ACTIVATION list: scoped ToolRegistry fail-closed behavior,
allowlist/subset/schema validation, run/tool context isolation, delegation
depth, hard budgets, the single empty-content repair retry, provider-neutral
invocation, LensSpec five-lens completeness, server-owned field guards, and
LensRegistry full-set enforcement. Skips cleanly on baselines without
``app.agents``.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

pytest.importorskip("app.agents", reason="Task 7 agent runtime not delivered yet")

from pydantic import BaseModel

from app.agents.budget import BudgetLedger, BudgetLimits
from app.agents.context import (
    PRODUCER_ROLES,
    MethodRef,
    RunContext,
    ToolContext,
    WorkerInputs,
)
from app.agents.errors import (
    BudgetExhausted,
    DelegationError,
    EmptyModelContentError,
    MissingToolContext,
    SchemaValidationError,
    ServerOwnedFieldError,
    ToolScopeError,
    ToolUnavailable,
    UnknownLensType,
    UnknownTool,
)
from app.agents.lenses import (
    ALLOWED_TOP_LEVEL_FIELDS,
    FORBIDDEN_SERVER_OWNED_FIELDS,
    LENS_SPECS,
    LensRegistry,
    StrategicLensStageOutput,
)
from app.agents.model_provider import StructuredCompletion
from app.agents.runner import PromptLoader, WorkerDefinition, WorkerRunner
from app.agents.tool_registry import STABLE_TOOL_CATALOG, ToolEntry, ToolRegistry
from app.types import (
    FULL_REQUIRED_STRATEGIC_LENSES,
    FormalAnalysisLevel,
    StrategicLensType,
)


class _SearchInput(BaseModel):
    query: str


class _SearchOutput(BaseModel):
    hits: list[str]


def _tool_context() -> ToolContext:
    return ToolContext(
        workspace_id=uuid4(), analysis_run_id=uuid4(), user_id=uuid4()
    )


def _entry(name: str = "search_web", *, read_only: bool = True, availability=None) -> ToolEntry:
    async def handler(payload: _SearchInput, context: ToolContext) -> _SearchOutput:
        return _SearchOutput(hits=[payload.query])

    return ToolEntry(
        name=name,
        description="qa probe",
        input_model=_SearchInput,
        output_model=_SearchOutput,
        read_only=read_only,
        required_scopes=frozenset(),
        handler=handler,
        availability_check=availability,
    )


def _run_context(allowed_tools: frozenset[str] = frozenset({"search_web"})) -> RunContext:
    return RunContext(
        workspace_id=uuid4(),
        decision_case_id=uuid4(),
        analysis_run_id=uuid4(),
        user_id=uuid4(),
        charter_id="charter-1",
        charter_version=1,
        analysis_depth=FormalAnalysisLevel.FULL,
        method=MethodRef(id="hardtech-market-direction", version="1.1.0", content_hash="sha256:qa"),
        case_snapshot_hash="sha256:case",
        dossier_snapshot_hash="sha256:dossier",
        material_snapshot_hash="sha256:material",
        allowed_tools=allowed_tools,
    )


# ---------------------------------------------------------------------------
# Scoped ToolRegistry: fail-closed registration and dispatch
# ---------------------------------------------------------------------------


def test_stable_catalog_is_exactly_the_five_read_only_tools() -> None:
    assert STABLE_TOOL_CATALOG == frozenset(
        {"search_web", "fetch_url", "crawl_site", "extract_document", "get_source_status"}
    )
    for forbidden in ("sign_decision", "transition_to_decided", "write_file", "http_post"):
        assert forbidden not in STABLE_TOOL_CATALOG


def test_registry_rejects_non_catalog_write_and_duplicate_tools() -> None:
    registry = ToolRegistry()
    with pytest.raises(ValueError):
        registry.register(_entry("vendor_private_endpoint"))
    with pytest.raises(ValueError):
        registry.register(_entry("search_web", read_only=False))
    registry.register(_entry("search_web"))
    with pytest.raises(ValueError):
        registry.register(_entry("search_web"))


async def test_dispatch_requires_context_and_known_tool() -> None:
    registry = ToolRegistry()
    registry.register(_entry("search_web"))
    with pytest.raises(MissingToolContext):
        await registry.dispatch("search_web", {"query": "x"}, context=None)
    with pytest.raises(UnknownTool):
        await registry.dispatch("fetch_url", {"url": "x"}, context=_tool_context())


async def test_dispatch_enforces_allowlist_envelope() -> None:
    registry = ToolRegistry()
    registry.register(_entry("search_web"))
    with pytest.raises(ToolScopeError):
        await registry.dispatch(
            "search_web", {"query": "x"}, context=_tool_context(), allowed=frozenset()
        )


async def test_dispatch_validates_input_schema_and_availability() -> None:
    registry = ToolRegistry()
    registry.register(_entry("search_web"))
    with pytest.raises(SchemaValidationError) as excinfo:
        await registry.dispatch("search_web", {"wrong": 1}, context=_tool_context())
    assert excinfo.value.findings

    async def unavailable(context: ToolContext) -> bool:
        return False

    gated = ToolRegistry()
    gated.register(_entry("search_web", availability=unavailable))
    with pytest.raises(ToolUnavailable):
        await gated.dispatch("search_web", {"query": "x"}, context=_tool_context())


async def test_dispatch_valid_call_returns_typed_output() -> None:
    registry = ToolRegistry()
    registry.register(_entry("search_web"))
    result = await registry.dispatch(
        "search_web",
        {"query": "rescue market"},
        context=_tool_context(),
        allowed=frozenset({"search_web"}),
    )
    assert isinstance(result, _SearchOutput)
    assert result.hits == ["rescue market"]


# ---------------------------------------------------------------------------
# Run/Tool context isolation, subset roles, delegation depth
# ---------------------------------------------------------------------------


def test_for_role_requires_known_role_and_subset_envelope() -> None:
    context = _run_context(frozenset({"search_web"}))
    with pytest.raises(ValueError):
        context.for_role("project_manager", frozenset())
    with pytest.raises(ValueError):
        context.for_role(next(iter(PRODUCER_ROLES)), frozenset({"fetch_url"}))
    role = next(iter(PRODUCER_ROLES))
    narrowed = context.for_role(role, frozenset({"search_web"}))
    assert narrowed.producer_role == role
    assert narrowed.allowed_tools == frozenset({"search_web"})


def test_tool_context_projection_pins_tenant_and_run() -> None:
    context = _run_context()
    projected = context.tool_context()
    assert projected.workspace_id == context.workspace_id
    assert projected.analysis_run_id == context.analysis_run_id
    assert projected.user_id == context.user_id
    assert projected.allowed_connector_ids == context.allowed_connector_ids


def test_delegation_intersects_tools_and_caps_depth() -> None:
    context = _run_context(frozenset({"search_web", "fetch_url"}))
    child = context.delegate(frozenset({"fetch_url", "crawl_site"}), max_depth=2)
    assert child.allowed_tools == frozenset({"fetch_url"}), "delegated tools must intersect"
    assert child.delegation_depth == 1
    grandchild = child.delegate(frozenset({"fetch_url"}), max_depth=2)
    assert grandchild.delegation_depth == 2
    with pytest.raises(DelegationError):
        grandchild.delegate(frozenset({"fetch_url"}), max_depth=2)


# ---------------------------------------------------------------------------
# Hard budgets
# ---------------------------------------------------------------------------


def test_budget_charge_fails_closed_at_limit() -> None:
    ledger = BudgetLedger(limits=BudgetLimits(limits={"max_model_calls": 2}))
    ledger.charge("max_model_calls")
    ledger.charge("max_model_calls")
    with pytest.raises(BudgetExhausted) as excinfo:
        ledger.charge("max_model_calls")
    assert excinfo.value.budget_key == "max_model_calls"
    assert excinfo.value.limit == 2


def test_budget_tool_call_charges_aggregate_and_specific_counters() -> None:
    ledger = BudgetLedger(
        limits=BudgetLimits(limits={"max_total_tool_calls": 2, "max_search_calls": 1})
    )
    ledger.charge_tool_call(is_search=True)
    with pytest.raises(BudgetExhausted):
        ledger.charge_tool_call(is_search=True)


def test_budget_manifest_parsing_fails_closed() -> None:
    with pytest.raises(ValueError):
        BudgetLimits.from_manifest({}, "full")
    with pytest.raises(ValueError):
        BudgetLimits.from_manifest({"budgets": {"focused": {}}}, "full")
    limits = BudgetLimits.from_manifest(
        {"budgets": {"full": {"max_model_calls": 3, "strict": True}}}, "full"
    )
    assert limits.get("max_model_calls") == 3.0
    assert limits.get("strict") is None, "boolean flags are not numeric budgets"


# ---------------------------------------------------------------------------
# Empty-content single repair retry + provider-neutral invocation
# ---------------------------------------------------------------------------


class _ScriptedProvider:
    """Provider-neutral fake: only the stable protocol surface is used."""

    name = "qa-fake"
    supports_structured_output = True

    def __init__(self, completions: list[StructuredCompletion]) -> None:
        self._completions = completions
        self.calls: list[dict] = []

    async def complete_structured(self, **kwargs) -> StructuredCompletion:
        self.calls.append(kwargs)
        return self._completions[min(len(self.calls) - 1, len(self._completions) - 1)]


def _completion(content: dict, raw: str) -> StructuredCompletion:
    return StructuredCompletion(
        content=content,
        raw_text=raw,
        request_model="qa",
        response_model="qa",
        finish_reason="stop",
    )


def _runner(provider: _ScriptedProvider) -> WorkerRunner:
    return WorkerRunner(
        provider=provider,
        registry=ToolRegistry(),
        prompt_loader=PromptLoader(lambda ref: f"PROMPT:{ref}"),
    )


def _definition() -> WorkerDefinition:
    return WorkerDefinition(
        role=next(iter(PRODUCER_ROLES)),
        prompt_ref="prompts/research.md",
        output_schema_id="urn:qa",
        allowed_tools=frozenset(),
    )


async def test_empty_content_repairs_exactly_once_then_succeeds() -> None:
    provider = _ScriptedProvider(
        [_completion({}, ""), _completion({"ok": True}, '{"ok": true}')]
    )
    ledger = BudgetLedger(limits=BudgetLimits(limits={"max_model_calls": 5}))
    result = await _runner(provider).run_worker(
        definition=_definition(),
        run_context=_run_context(frozenset()),
        budget=ledger,
        inputs=WorkerInputs(frozen_summary="qa summary"),
    )
    assert result.attempts == 2
    assert result.output == {"ok": True}
    assert ledger.consumed["max_model_calls"] == 2, "each attempt must charge the budget"
    # provider-neutral: repair hint appended as an extra message, same protocol call
    assert len(provider.calls) == 2
    assert len(provider.calls[1]["messages"]) == len(provider.calls[0]["messages"]) + 1


async def test_persistent_empty_content_fails_after_single_retry() -> None:
    provider = _ScriptedProvider([_completion({}, "")])
    with pytest.raises(SchemaValidationError):
        await _runner(provider).run_worker(
            definition=_definition(),
            run_context=_run_context(frozenset()),
            budget=BudgetLedger(limits=BudgetLimits(limits={})),
            inputs=WorkerInputs(frozen_summary="qa summary"),
        )
    assert len(provider.calls) == 2, "exactly one repair retry, never more"


def test_structured_completion_treats_blank_as_structural_failure() -> None:
    with pytest.raises(EmptyModelContentError):
        _completion({"ok": True}, "   ").require_non_empty()
    with pytest.raises(EmptyModelContentError):
        _completion({}, '{"ok": true}').require_non_empty()


def test_structured_completion_carries_no_reasoning_content_slot() -> None:
    fields = set(StructuredCompletion.__dataclass_fields__)
    assert "reasoning_content" not in fields
    assert "reasoningContent" not in fields


# ---------------------------------------------------------------------------
# Five-lens seam: spec completeness, server-owned guard, registry full set
# ---------------------------------------------------------------------------


def test_lens_specs_cover_exactly_the_canonical_five_with_correct_owners() -> None:
    assert set(LENS_SPECS) == set(FULL_REQUIRED_STRATEGIC_LENSES)
    owners = {lens: LENS_SPECS[lens].owner_worker for lens in LENS_SPECS}
    assert owners[StrategicLensType.PORTER_FIVE_FORCES] == "research"
    assert owners[StrategicLensType.PRE_MORTEM] == "critic"
    assert owners[StrategicLensType.COUNTERPARTY_RESPONSE_MATRIX] == "critic"
    assert owners[StrategicLensType.SCENARIO_PLANNING] == "synthesis"
    assert owners[StrategicLensType.MEADOWS_LEVERAGE_POINTS] == "synthesis"
    # counterparty strictly precedes pre-mortem (FL-02)
    assert "after_counterparty_matrix" in LENS_SPECS[StrategicLensType.PRE_MORTEM].trigger


def test_stage_output_rejects_server_owned_and_unknown_fields() -> None:
    valid_payload = {
        "lensType": "porter_five_forces",
        "sourceSkillVersion": "1.0.0",
        "phase": "research",
        "references": {"evidenceIds": []},
        "researchRequests": [],
        "content": {"summary": "qa"},
    }
    parsed = StrategicLensStageOutput.from_payload(valid_payload)
    assert parsed.lens_type is StrategicLensType.PORTER_FIVE_FORCES

    for forbidden in sorted(FORBIDDEN_SERVER_OWNED_FIELDS)[:4] + ["contentHash"]:
        with pytest.raises(ServerOwnedFieldError):
            StrategicLensStageOutput.from_payload({**valid_payload, forbidden: "x"})
    with pytest.raises(ServerOwnedFieldError):
        StrategicLensStageOutput.from_payload({**valid_payload, "qaUnknownField": 1})
    assert FORBIDDEN_SERVER_OWNED_FIELDS.isdisjoint(ALLOWED_TOP_LEVEL_FIELDS)


def test_lens_registry_enforces_known_unique_and_full_set() -> None:
    class _Impl:
        def __init__(self, lens_type: StrategicLensType) -> None:
            self.lens_type = lens_type

    registry = LensRegistry()
    with pytest.raises(UnknownLensType):
        registry.require_full_set()
    registry.register(_Impl(StrategicLensType.PORTER_FIVE_FORCES))
    with pytest.raises(ValueError):
        registry.register(_Impl(StrategicLensType.PORTER_FIVE_FORCES))
    with pytest.raises(UnknownLensType):
        registry.require_full_set()
    for lens in FULL_REQUIRED_STRATEGIC_LENSES[1:]:
        registry.register(_Impl(lens))
    registry.require_full_set()
    assert registry.registered() == frozenset(FULL_REQUIRED_STRATEGIC_LENSES)
