"""Read-only consumption path for persisted StrategicLensArtifact rows.

Lane boundary (Strategic Lens Artifact Read-Path Owner): this module owns
querying, filtering, authorization, and the consumption projection ONLY. The
write path, server-side identity injection, and Validation status
transitions belong to the Ways persistence lane; the ORM model, enums, and
migrations are frozen contract surfaces and are consumed as-is.

Semantics:

- every query is bound to the caller's ``WorkspaceContext``; artifact reads
  never accept a workspace id from unauthenticated input;
- single-artifact reads require the full workspace + case + run anchor
  combination, so cross-tenant ID enumeration is rejected by construction;
- the consumption API returns Validation-accepted (``ready``) artifacts
  only; drafts and rejected artifacts are reachable solely through the
  explicit audit API, which additionally requires the ``review`` capability;
- missing anchors, foreign-workspace combinations, missing artifacts, and
  non-consumable statuses on the consumption path all fail closed with the
  canonical ``CASE_NOT_FOUND`` 404 and one shared message (doc 10: the
  resource "does not exist or is not part of the current Workspace"), so
  existence and lifecycle state cannot be probed;
- ordering is total and deterministic for Report/Run assembly: canonical
  lens EXECUTION order (porter -> counterparty -> pre_mortem -> scenario ->
  meadows), then ``created_at``, then ``strategic_lens_artifact_id``.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence
from uuid import UUID

from sqlalchemy import case, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalysisRun, DecisionCase, StrategicLensArtifact
from app.security.envelope import ApiFailure
from app.tenancy.context import WorkspaceContext
from app.types import (
    LensProducerRole,
    OriginMode,
    StrategicLensArtifactStatus,
    StrategicLensType,
    WorkspaceCapability,
)

# Canonical lens EXECUTION order. Sources: AGENTS.md section 7 (Research/
# Porter -> Critic: Counterparty Matrix BEFORE the Pre-Mortem that consumes
# its result -> Synthesis: Scenario + Meadows), the frozen registry assembly
# in app/strategic_lenses/registry.py, and the PRE_MORTEM LensSpec trigger
# "after_counterparty_matrix_..." in app/agents/lenses.py. Kept as a local
# constant because no importable order tuple exists on the frozen surfaces:
# types.FULL_REQUIRED_STRATEGIC_LENSES is a required-SET contract (not an
# order) and importing the registry would drag in every lens implementation.
_CANONICAL_LENS_EXECUTION_ORDER: tuple[StrategicLensType, ...] = (
    StrategicLensType.PORTER_FIVE_FORCES,
    StrategicLensType.COUNTERPARTY_RESPONSE_MATRIX,
    StrategicLensType.PRE_MORTEM,
    StrategicLensType.SCENARIO_PLANNING,
    StrategicLensType.MEADOWS_LEVERAGE_POINTS,
)

_LENS_ORDER: dict[StrategicLensType, int] = {
    lens: index for index, lens in enumerate(_CANONICAL_LENS_EXECUTION_ORDER)
}


def _lens_scope_not_found() -> ApiFailure:
    """Uniform 404 for the whole case/run/artifact consumption scope.

    One code, one message for every denial reason on the read path; callers
    cannot distinguish "wrong workspace" from "does not exist" from "not
    consumable yet".
    """

    return ApiFailure(
        "CASE_NOT_FOUND",
        "Decision case, analysis run, or artifact not found.",
        http_status=404,
    )


def _audit_capability_required() -> ApiFailure:
    return ApiFailure(
        "MEMBERSHIP_CAPABILITY_REQUIRED",
        "The current membership lacks the capability required for this action.",
        http_status=403,
        details={"requiredCapability": WorkspaceCapability.REVIEW.value},
    )


@dataclass(frozen=True)
class LensArtifactView:
    """Immutable internal consumption projection (NOT a wire DTO).

    HTTP exposure requires generated contracts and stays with the Contract
    Lead; Report/Run assembly consumes this projection in-process.
    """

    strategic_lens_artifact_id: UUID
    workspace_id: UUID
    decision_case_id: UUID
    analysis_run_id: UUID
    charter_id: UUID
    lens_type: StrategicLensType
    producer_role: LensProducerRole
    status: StrategicLensArtifactStatus
    method_id: str
    method_version: str
    method_content_hash: str
    prompt_version: str
    schema_version: str
    origin_modes: tuple[OriginMode, ...]
    content_hash: str
    payload: dict
    claim_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    assumption_refs: tuple[str, ...]
    validation_accepted_at: datetime | None
    created_at: datetime


def _project(row: StrategicLensArtifact) -> LensArtifactView:
    return LensArtifactView(
        strategic_lens_artifact_id=row.strategic_lens_artifact_id,
        workspace_id=row.workspace_id,
        decision_case_id=row.decision_case_id,
        analysis_run_id=row.analysis_run_id,
        charter_id=row.charter_id,
        lens_type=row.lens_type,
        producer_role=row.producer_role,
        status=row.status,
        method_id=row.method_id,
        method_version=row.method_version,
        method_content_hash=row.method_content_hash,
        prompt_version=row.prompt_version,
        schema_version=row.schema_version,
        origin_modes=tuple(row.origin_modes),
        content_hash=row.content_hash,
        # Deep copy so consumers can never mutate ORM-held JSON state.
        payload=copy.deepcopy(row.payload),
        claim_refs=tuple(row.claim_refs),
        evidence_refs=tuple(row.evidence_refs),
        assumption_refs=tuple(row.assumption_refs),
        validation_accepted_at=row.validation_accepted_at,
        created_at=row.created_at,
    )


def _canonical_order():
    """Total ordering: canonical lens EXECUTION order, createdAt, artifact id."""

    lens_rank = case(
        # Enum members as keys so bind parameters render with the PG enum type
        # instead of VARCHAR (asyncpg rejects untyped enum comparisons).
        _LENS_ORDER,
        value=StrategicLensArtifact.lens_type,
        else_=len(_LENS_ORDER),
    )
    return (
        lens_rank.asc(),
        StrategicLensArtifact.created_at.asc(),
        StrategicLensArtifact.strategic_lens_artifact_id.asc(),
    )


class StrategicLensArtifactReadRepository:
    """Pure SELECT layer; workspace binding is mandatory on every query."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def case_anchor_exists(self, workspace_id: UUID, decision_case_id: UUID) -> bool:
        return bool(
            await self._db.scalar(
                select(
                    exists().where(
                        DecisionCase.workspace_id == workspace_id,
                        DecisionCase.decision_case_id == decision_case_id,
                    )
                )
            )
        )

    async def run_anchor_exists(
        self, workspace_id: UUID, decision_case_id: UUID, analysis_run_id: UUID
    ) -> bool:
        return bool(
            await self._db.scalar(
                select(
                    exists().where(
                        AnalysisRun.workspace_id == workspace_id,
                        AnalysisRun.decision_case_id == decision_case_id,
                        AnalysisRun.analysis_run_id == analysis_run_id,
                    )
                )
            )
        )

    async def list_artifacts(
        self,
        workspace_id: UUID,
        *,
        decision_case_id: UUID | None = None,
        analysis_run_id: UUID | None = None,
        lens_types: Sequence[StrategicLensType] | None = None,
        statuses: Sequence[StrategicLensArtifactStatus] | None = None,
    ) -> list[StrategicLensArtifact]:
        query = select(StrategicLensArtifact).where(
            StrategicLensArtifact.workspace_id == workspace_id
        )
        if decision_case_id is not None:
            query = query.where(StrategicLensArtifact.decision_case_id == decision_case_id)
        if analysis_run_id is not None:
            query = query.where(StrategicLensArtifact.analysis_run_id == analysis_run_id)
        if lens_types:
            query = query.where(StrategicLensArtifact.lens_type.in_(list(lens_types)))
        if statuses:
            query = query.where(StrategicLensArtifact.status.in_(list(statuses)))
        query = query.order_by(*_canonical_order())
        return list((await self._db.scalars(query)).all())

    async def get_artifact(
        self,
        workspace_id: UUID,
        decision_case_id: UUID,
        analysis_run_id: UUID,
        strategic_lens_artifact_id: UUID,
    ) -> StrategicLensArtifact | None:
        return await self._db.scalar(
            select(StrategicLensArtifact).where(
                StrategicLensArtifact.workspace_id == workspace_id,
                StrategicLensArtifact.decision_case_id == decision_case_id,
                StrategicLensArtifact.analysis_run_id == analysis_run_id,
                StrategicLensArtifact.strategic_lens_artifact_id
                == strategic_lens_artifact_id,
            )
        )


class StrategicLensArtifactReadService:
    """Authorization-aware consumption and audit reads."""

    def __init__(self, db: AsyncSession) -> None:
        self._repository = StrategicLensArtifactReadRepository(db)

    async def _require_case_anchor(
        self, context: WorkspaceContext, decision_case_id: UUID
    ) -> None:
        if not await self._repository.case_anchor_exists(
            context.workspace_id, decision_case_id
        ):
            raise _lens_scope_not_found()

    async def _require_run_anchor(
        self, context: WorkspaceContext, decision_case_id: UUID, analysis_run_id: UUID
    ) -> None:
        if not await self._repository.run_anchor_exists(
            context.workspace_id, decision_case_id, analysis_run_id
        ):
            raise _lens_scope_not_found()

    async def list_ready_for_workspace(
        self,
        context: WorkspaceContext,
        *,
        lens_types: Sequence[StrategicLensType] | None = None,
    ) -> list[LensArtifactView]:
        rows = await self._repository.list_artifacts(
            context.workspace_id,
            lens_types=lens_types,
            statuses=[StrategicLensArtifactStatus.READY],
        )
        return [_project(row) for row in rows]

    async def list_ready_for_case(
        self,
        context: WorkspaceContext,
        decision_case_id: UUID,
        *,
        lens_types: Sequence[StrategicLensType] | None = None,
    ) -> list[LensArtifactView]:
        await self._require_case_anchor(context, decision_case_id)
        rows = await self._repository.list_artifacts(
            context.workspace_id,
            decision_case_id=decision_case_id,
            lens_types=lens_types,
            statuses=[StrategicLensArtifactStatus.READY],
        )
        return [_project(row) for row in rows]

    async def list_ready_for_run(
        self,
        context: WorkspaceContext,
        decision_case_id: UUID,
        analysis_run_id: UUID,
        *,
        lens_types: Sequence[StrategicLensType] | None = None,
    ) -> list[LensArtifactView]:
        await self._require_run_anchor(context, decision_case_id, analysis_run_id)
        rows = await self._repository.list_artifacts(
            context.workspace_id,
            decision_case_id=decision_case_id,
            analysis_run_id=analysis_run_id,
            lens_types=lens_types,
            statuses=[StrategicLensArtifactStatus.READY],
        )
        return [_project(row) for row in rows]

    async def get_ready_artifact(
        self,
        context: WorkspaceContext,
        decision_case_id: UUID,
        analysis_run_id: UUID,
        strategic_lens_artifact_id: UUID,
    ) -> LensArtifactView:
        """Consumption get: full anchor combination, ready-only.

        A draft or rejected artifact is NOT consumable and yields the same
        uniform 404 as a missing one; audit flows must use
        ``list_for_audit`` explicitly.
        """

        await self._require_run_anchor(context, decision_case_id, analysis_run_id)
        row = await self._repository.get_artifact(
            context.workspace_id,
            decision_case_id,
            analysis_run_id,
            strategic_lens_artifact_id,
        )
        if row is None or row.status != StrategicLensArtifactStatus.READY:
            raise _lens_scope_not_found()
        return _project(row)

    async def list_for_audit(
        self,
        context: WorkspaceContext,
        decision_case_id: UUID,
        *,
        analysis_run_id: UUID | None = None,
        lens_types: Sequence[StrategicLensType] | None = None,
        statuses: Sequence[StrategicLensArtifactStatus] | None = None,
    ) -> list[LensArtifactView]:
        """Audit read: the only path that can see draft/rejected artifacts.

        Requires the projected ``review`` capability on top of workspace
        membership; anchors are still enforced with the uniform 404 first so
        capability probing cannot reveal foreign resources.
        """

        await self._require_case_anchor(context, decision_case_id)
        if analysis_run_id is not None:
            await self._require_run_anchor(context, decision_case_id, analysis_run_id)
        if not context.has_capability(WorkspaceCapability.REVIEW):
            raise _audit_capability_required()
        rows = await self._repository.list_artifacts(
            context.workspace_id,
            decision_case_id=decision_case_id,
            analysis_run_id=analysis_run_id,
            lens_types=lens_types,
            statuses=statuses,
        )
        return [_project(row) for row in rows]
