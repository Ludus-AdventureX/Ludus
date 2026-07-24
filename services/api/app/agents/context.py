"""Workspace / Run / Tool execution context isolation.

Every formal worker and every tool call executes inside a frozen, immutable
context derived from a confirmed ``DeepAnalysisRequest``. The context pins the
tenant (``workspace_id``), the single active formal run, the frozen snapshot
hashes and the permitted tool / connector envelope. Contexts are ``frozen`` so a
worker can never widen its own scope, and delegation can only ever *narrow* the
tool envelope (subset rule).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from uuid import UUID

from app.analyses.schemas import DeepAnalysisRequest
from app.types import FormalAnalysisLevel, OriginMode

# The canonical producer roles. These are orchestration responsibilities that may
# share one model base but never share context, prompt, budget, events or trace.
PRODUCER_ROLES: frozenset[str] = frozenset(
    {"research", "critic", "synthesis", "validation"}
)


@dataclass(frozen=True, slots=True)
class ToolContext:
    """Non-nullable context handed to every tool handler.

    A tool that receives ``context=None`` must raise :class:`MissingToolContext`.
    """

    workspace_id: UUID
    analysis_run_id: UUID
    user_id: UUID
    allowed_connector_ids: frozenset[UUID] = frozenset()
    origin_mode: OriginMode = OriginMode.LIVE


@dataclass(frozen=True, slots=True)
class MethodRef:
    """Frozen reference to the published method pack driving this run."""

    id: str
    version: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class RunContext:
    """Frozen execution context for a single formal AnalysisRun.

    ``allowed_tools`` is the run-level envelope; per-role contexts are derived with
    :meth:`for_role`, whose tool set must be a subset of this envelope.
    """

    workspace_id: UUID
    decision_case_id: UUID
    analysis_run_id: UUID
    user_id: UUID
    charter_id: str
    charter_version: int
    analysis_depth: FormalAnalysisLevel
    method: MethodRef
    case_snapshot_hash: str
    dossier_snapshot_hash: str
    material_snapshot_hash: str
    allowed_tools: frozenset[str] = frozenset()
    allowed_connector_ids: frozenset[UUID] = frozenset()
    producer_role: str | None = None
    delegation_depth: int = 0

    @classmethod
    def from_request(
        cls,
        request: DeepAnalysisRequest,
        *,
        user_id: UUID,
    ) -> "RunContext":
        """Build a run context from a confirmed, frozen ``DeepAnalysisRequest``."""

        return cls(
            workspace_id=UUID(str(request.workspace_id)),
            decision_case_id=UUID(str(request.decision_case_id)),
            analysis_run_id=UUID(str(request.analysis_run_id)),
            user_id=user_id,
            charter_id=str(request.charter_id),
            charter_version=int(request.charter_version),
            analysis_depth=request.analysis_depth,
            method=MethodRef(
                id=str(request.method.id),
                version=str(request.method.version),
                content_hash=str(request.method.content_hash),
            ),
            case_snapshot_hash=str(request.case_snapshot_hash),
            dossier_snapshot_hash=str(request.dossier_snapshot_hash),
            material_snapshot_hash=str(request.material_snapshot_hash),
            allowed_tools=frozenset(str(name) for name in request.allowed_tools),
            allowed_connector_ids=frozenset(
                UUID(str(cid)) for cid in request.allowed_connector_ids
            ),
        )

    def for_role(self, role: str, role_tools: frozenset[str]) -> "RunContext":
        """Narrow the context to one producer role with a subset tool envelope."""

        if role not in PRODUCER_ROLES:
            raise ValueError(f"unknown producer role: {role!r}")
        if not role_tools <= self.allowed_tools:
            raise ValueError(
                "role tool envelope must be a subset of the run envelope: "
                f"{sorted(role_tools - self.allowed_tools)} not permitted"
            )
        return replace(self, producer_role=role, allowed_tools=role_tools)

    def delegate(self, delegated_tools: frozenset[str], *, max_depth: int) -> "RunContext":
        """Derive a delegated child context; tools intersect and depth increases."""

        child_depth = self.delegation_depth + 1
        if child_depth > max_depth:
            from .errors import DelegationError

            raise DelegationError(
                f"delegation depth {child_depth} exceeds max {max_depth}"
            )
        return replace(
            self,
            allowed_tools=self.allowed_tools & delegated_tools,
            delegation_depth=child_depth,
        )

    def tool_context(self) -> ToolContext:
        """Project the run context onto a tool-call context."""

        return ToolContext(
            workspace_id=self.workspace_id,
            analysis_run_id=self.analysis_run_id,
            user_id=self.user_id,
            allowed_connector_ids=self.allowed_connector_ids,
        )


@dataclass(frozen=True, slots=True)
class WorkerInputs:
    """Frozen, role-scoped inputs handed to a worker.

    A worker only ever sees the frozen snapshot summaries, the evidence/claims it
    needs and minimal sibling summaries - never another role's full context or
    another workspace.
    """

    frozen_summary: str
    evidence_refs: tuple[str, ...] = ()
    claim_refs: tuple[str, ...] = ()
    assumption_refs: tuple[str, ...] = ()
    sibling_summaries: tuple[str, ...] = ()
    extra: dict[str, object] = field(default_factory=dict)
