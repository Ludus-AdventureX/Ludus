"""Ways / Agent Pipeline runtime.

A scoped, provider-neutral agent runtime for the four formal producer roles
(research / critic / synthesis / validation) plus the stable five-lens contract
seam. Nothing here persists Run state, SSE events or canonical schemas - those are
owned by case_api_data and contract_lead. This package provides the execution
primitives (model provider, tool registry, budgets, context isolation, worker
runner) and the lens contract the five lens specialists implement against.
"""

from __future__ import annotations

from .budget import BudgetLedger, BudgetLimits
from .context import (
    PRODUCER_ROLES,
    MethodRef,
    RunContext,
    ToolContext,
    WorkerInputs,
)
from .errors import (
    AgentRuntimeError,
    BudgetExhausted,
    DelegationError,
    EmptyModelContentError,
    LensBehaviorError,
    MissingToolContext,
    SchemaValidationError,
    ServerOwnedFieldError,
    ToolScopeError,
    ToolUnavailable,
    UnknownLensType,
    UnknownTool,
)
from .lenses import (
    ALLOWED_TOP_LEVEL_FIELDS,
    FORBIDDEN_SERVER_OWNED_FIELDS,
    LENS_OUTPUT_SCHEMA_ID,
    LENS_SPECS,
    METHOD_ID,
    METHOD_VERSION,
    SOURCE_SKILL_VERSION,
    LensBehaviorReport,
    LensImplementation,
    LensPromptInputs,
    LensRegistry,
    LensRequest,
    LensSpec,
    StrategicLensStageOutput,
    lens_spec,
)
from .model_provider import (
    FixtureModelProvider,
    ModelMessage,
    ModelProvider,
    ProviderProbe,
    StructuredCompletion,
)
from .provider_adapter import (
    ConnectorStatus,
    FetchProviderAdapter,
    RetrievalResult,
    SearchProviderAdapter,
    SourceStatus,
)
from .runner import (
    PromptLoader,
    ToolTraceEntry,
    WorkerDefinition,
    WorkerResult,
    WorkerRunner,
)
from .tool_registry import STABLE_TOOL_CATALOG, ToolEntry, ToolRegistry

__all__ = [
    "ALLOWED_TOP_LEVEL_FIELDS",
    "AgentRuntimeError",
    "BudgetExhausted",
    "BudgetLedger",
    "BudgetLimits",
    "ConnectorStatus",
    "DelegationError",
    "EmptyModelContentError",
    "FORBIDDEN_SERVER_OWNED_FIELDS",
    "FetchProviderAdapter",
    "FixtureModelProvider",
    "LENS_OUTPUT_SCHEMA_ID",
    "LENS_SPECS",
    "LensBehaviorError",
    "LensBehaviorReport",
    "LensImplementation",
    "LensPromptInputs",
    "LensRegistry",
    "LensRequest",
    "LensSpec",
    "METHOD_ID",
    "METHOD_VERSION",
    "MethodRef",
    "MissingToolContext",
    "ModelMessage",
    "ModelProvider",
    "PRODUCER_ROLES",
    "PromptLoader",
    "ProviderProbe",
    "RetrievalResult",
    "RunContext",
    "SOURCE_SKILL_VERSION",
    "STABLE_TOOL_CATALOG",
    "SchemaValidationError",
    "SearchProviderAdapter",
    "ServerOwnedFieldError",
    "SourceStatus",
    "StrategicLensStageOutput",
    "StructuredCompletion",
    "ToolContext",
    "ToolEntry",
    "ToolRegistry",
    "ToolScopeError",
    "ToolTraceEntry",
    "ToolUnavailable",
    "UnknownLensType",
    "UnknownTool",
    "WorkerDefinition",
    "WorkerInputs",
    "WorkerResult",
    "WorkerRunner",
    "lens_spec",
]
