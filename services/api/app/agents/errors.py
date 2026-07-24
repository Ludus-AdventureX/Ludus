"""Error taxonomy for the Ways / Agent Pipeline runtime.

These exceptions are the stable failure surface that workers, the tool registry
and lens implementations raise. They are deterministic and carry machine-readable
reason codes so the AnalysisRun state machine (owned by case_api_data) can map them
onto canonical Run outcomes (``needs_attention`` / ``blocked``) without parsing
free text.
"""

from __future__ import annotations


class AgentRuntimeError(RuntimeError):
    """Base class for every recoverable agent-runtime failure."""

    code: str = "agent_runtime_error"


class MissingToolContext(AgentRuntimeError):
    """A tool was dispatched without a workspace/run scoped :class:`ToolContext`."""

    code = "missing_tool_context"


class UnknownTool(AgentRuntimeError):
    """The requested tool name is not registered in the stable read-only catalog."""

    code = "unknown_tool"


class ToolScopeError(AgentRuntimeError):
    """The tool is not inside the caller's permitted (subset) tool envelope."""

    code = "tool_scope_denied"


class ToolUnavailable(AgentRuntimeError):
    """The tool's availability check failed (e.g. connector missing/invalid)."""

    code = "tool_unavailable"


class ConnectorScopeError(AgentRuntimeError):
    """A connector id outside the frozen ``allowed_connector_ids`` was requested."""

    code = "connector_scope_denied"


class BudgetExhausted(AgentRuntimeError):
    """A budget counter or wall-clock limit was reached.

    The runner persists partial artifacts and asks the state machine to enter
    ``needs_attention``; the budget itself is never silently increased.
    """

    code = "budget_exhausted"

    def __init__(self, budget_key: str, limit: float, attempted: float) -> None:
        super().__init__(
            f"budget exhausted for {budget_key!r}: limit={limit}, attempted={attempted}"
        )
        self.budget_key = budget_key
        self.limit = limit
        self.attempted = attempted


class DelegationError(AgentRuntimeError):
    """A delegated sub-task violated depth or permission-subset constraints."""

    code = "delegation_denied"


class StructuredOutputError(AgentRuntimeError):
    """Base class for model structured-output failures."""

    code = "structured_output_error"


class EmptyModelContentError(StructuredOutputError):
    """Empty ``content`` is treated as a structural failure, not a valid answer."""

    code = "empty_model_content"


class SchemaValidationError(StructuredOutputError):
    """Model output failed schema/Pydantic validation after the single repair retry."""

    code = "schema_validation_failed"

    def __init__(self, message: str, *, findings: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.findings = findings


class LensContractError(AgentRuntimeError):
    """Base class for strategic-lens contract violations."""

    code = "lens_contract_error"


class UnknownLensType(LensContractError):
    """A lens type outside the canonical five-lens set was referenced."""

    code = "unknown_lens_type"


class ServerOwnedFieldError(LensContractError):
    """The untrusted model output tried to set a server-owned identity/provenance field."""

    code = "server_owned_field_present"

    def __init__(self, fields: tuple[str, ...]) -> None:
        super().__init__(f"model output must not set server-owned fields: {sorted(fields)}")
        self.fields = fields


class LensBehaviorError(LensContractError):
    """A lens stage output passed JSON shape but failed its behavior contract."""

    code = "lens_behavior_failed"

    def __init__(self, message: str, *, reason_codes: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.reason_codes = reason_codes
