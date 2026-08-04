"""Repository for the deliberation council (CCR-20260804-DELIB-01).

Every query is workspace-scoped; the repository never commits (route/worker
boundaries own transactions, analyses-repository precedent). Event sequences
are per-run monotonic and assigned here at persist time; Last-Event-ID replay
reads them back in order.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    DeliberationEvent,
    DeliberationFactor,
    DeliberationMessage,
    DeliberationNomination,
    DeliberationOutcome,
    DeliberationProposal,
    DeliberationRound,
    DeliberationRun,
)
from app.types import (
    DeliberationEventCategory,
    DeliberationNominationStatus,
    DeliberationProposalStatus,
    DeliberationRoundKind,
    DeliberationRunStatus,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DeliberationNotFound(LookupError):
    """Uniform lookup failure (missing, foreign, cross-tenant)."""


class DeliberationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # --- runs ---------------------------------------------------------------

    async def create_run(
        self,
        *,
        workspace_id: UUID,
        decision_case_id: UUID,
        max_rounds: int,
        factor_snapshot_hash: str,
        origin_modes: list[str],
    ) -> DeliberationRun:
        run = DeliberationRun(
            workspace_id=workspace_id,
            decision_case_id=decision_case_id,
            status=DeliberationRunStatus.PREPARING,
            current_round_seq=0,
            max_rounds=max_rounds,
            factor_snapshot_hash=factor_snapshot_hash,
            origin_modes=origin_modes,
        )
        self._db.add(run)
        await self._db.flush()
        return run

    async def get_run(self, workspace_id: UUID, run_id: UUID) -> DeliberationRun | None:
        result = await self._db.execute(
            select(DeliberationRun).where(
                DeliberationRun.workspace_id == workspace_id,
                DeliberationRun.id == run_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_runs_for_case(
        self, workspace_id: UUID, decision_case_id: UUID
    ) -> Sequence[DeliberationRun]:
        result = await self._db.execute(
            select(DeliberationRun)
            .where(
                DeliberationRun.workspace_id == workspace_id,
                DeliberationRun.decision_case_id == decision_case_id,
            )
            .order_by(DeliberationRun.created_at.desc(), DeliberationRun.id)
        )
        return result.scalars().all()

    async def transition_run(
        self, workspace_id: UUID, run_id: UUID, status: DeliberationRunStatus,
        *, current_round_seq: int | None = None,
    ) -> DeliberationRun:
        run = await self.get_run(workspace_id, run_id)
        if run is None:
            raise DeliberationNotFound()
        run.status = status
        if current_round_seq is not None:
            run.current_round_seq = current_round_seq
        run.updated_at = _utc_now()
        await self._db.flush()
        return run

    async def claim_next_actionable(self) -> DeliberationRun | None:
        """FOR UPDATE SKIP LOCKED claim of one actionable run (worker queue)."""

        result = await self._db.execute(
            select(DeliberationRun)
            .where(
                DeliberationRun.status.in_(
                    [DeliberationRunStatus.PREPARING, DeliberationRunStatus.RUNNING]
                )
            )
            .order_by(DeliberationRun.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        return result.scalar_one_or_none()

    # --- factors ------------------------------------------------------------

    async def add_factor(self, factor: DeliberationFactor) -> DeliberationFactor:
        self._db.add(factor)
        await self._db.flush()
        return factor

    async def list_factors(
        self, workspace_id: UUID, run_id: UUID
    ) -> Sequence[DeliberationFactor]:
        result = await self._db.execute(
            select(DeliberationFactor)
            .where(
                DeliberationFactor.workspace_id == workspace_id,
                DeliberationFactor.deliberation_run_id == run_id,
            )
            .order_by(DeliberationFactor.created_at, DeliberationFactor.id)
        )
        return result.scalars().all()

    # --- rounds -------------------------------------------------------------

    async def open_round(
        self, *, workspace_id: UUID, run_id: UUID, seq: int, kind: DeliberationRoundKind
    ) -> DeliberationRound:
        round_row = DeliberationRound(
            workspace_id=workspace_id,
            deliberation_run_id=run_id,
            seq=seq,
            kind=kind,
            status="active",
        )
        self._db.add(round_row)
        await self._db.flush()
        return round_row

    async def active_round(self, workspace_id: UUID, run_id: UUID) -> DeliberationRound | None:
        result = await self._db.execute(
            select(DeliberationRound)
            .where(
                DeliberationRound.workspace_id == workspace_id,
                DeliberationRound.deliberation_run_id == run_id,
                DeliberationRound.status == "active",
            )
            .order_by(DeliberationRound.seq.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def complete_round(self, round_row: DeliberationRound) -> None:
        round_row.status = "complete"
        round_row.ended_at = _utc_now()
        await self._db.flush()

    async def count_rounds(self, workspace_id: UUID, run_id: UUID) -> int:
        return int(
            await self._db.scalar(
                select(func.count())
                .select_from(DeliberationRound)
                .where(
                    DeliberationRound.workspace_id == workspace_id,
                    DeliberationRound.deliberation_run_id == run_id,
                )
            )
            or 0
        )

    # --- messages -----------------------------------------------------------

    async def add_message(self, message: DeliberationMessage) -> DeliberationMessage:
        self._db.add(message)
        await self._db.flush()
        return message

    async def list_messages(
        self, workspace_id: UUID, run_id: UUID, *, limit: int, before_id: UUID | None
    ) -> Sequence[DeliberationMessage]:
        query = (
            select(DeliberationMessage)
            .where(
                DeliberationMessage.workspace_id == workspace_id,
                DeliberationMessage.deliberation_run_id == run_id,
            )
            .order_by(DeliberationMessage.created_at.desc(), DeliberationMessage.id.desc())
            .limit(limit)
        )
        if before_id is not None:
            anchor = await self._db.get(DeliberationMessage, (workspace_id, before_id))
            if anchor is not None and anchor.deliberation_run_id == run_id:
                query = query.where(DeliberationMessage.created_at <= anchor.created_at)
        result = await self._db.execute(query)
        return list(reversed(result.scalars().all()))

    # --- proposals / nominations ---------------------------------------------

    async def add_proposal(self, proposal: DeliberationProposal) -> DeliberationProposal:
        self._db.add(proposal)
        await self._db.flush()
        return proposal

    async def get_proposal(
        self, workspace_id: UUID, run_id: UUID, proposal_id: UUID
    ) -> DeliberationProposal | None:
        result = await self._db.execute(
            select(DeliberationProposal).where(
                DeliberationProposal.workspace_id == workspace_id,
                DeliberationProposal.deliberation_run_id == run_id,
                DeliberationProposal.id == proposal_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_proposals(
        self, workspace_id: UUID, run_id: UUID,
        status: DeliberationProposalStatus | None = None,
    ) -> Sequence[DeliberationProposal]:
        query = select(DeliberationProposal).where(
            DeliberationProposal.workspace_id == workspace_id,
            DeliberationProposal.deliberation_run_id == run_id,
        )
        if status is not None:
            query = query.where(DeliberationProposal.status == status)
        result = await self._db.execute(
            query.order_by(DeliberationProposal.created_at, DeliberationProposal.id)
        )
        return result.scalars().all()

    async def add_nomination(self, nomination: DeliberationNomination) -> DeliberationNomination:
        self._db.add(nomination)
        await self._db.flush()
        return nomination

    async def get_nomination(
        self, workspace_id: UUID, run_id: UUID, nomination_id: UUID
    ) -> DeliberationNomination | None:
        result = await self._db.execute(
            select(DeliberationNomination).where(
                DeliberationNomination.workspace_id == workspace_id,
                DeliberationNomination.deliberation_run_id == run_id,
                DeliberationNomination.id == nomination_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_nominations(
        self, workspace_id: UUID, run_id: UUID,
        status: DeliberationNominationStatus | None = None,
    ) -> Sequence[DeliberationNomination]:
        query = select(DeliberationNomination).where(
            DeliberationNomination.workspace_id == workspace_id,
            DeliberationNomination.deliberation_run_id == run_id,
        )
        if status is not None:
            query = query.where(DeliberationNomination.status == status)
        result = await self._db.execute(
            query.order_by(DeliberationNomination.created_at, DeliberationNomination.id)
        )
        return result.scalars().all()

    # --- outcome ------------------------------------------------------------

    async def set_outcome(self, outcome: DeliberationOutcome) -> DeliberationOutcome:
        self._db.add(outcome)
        await self._db.flush()
        return outcome

    async def get_outcome(
        self, workspace_id: UUID, run_id: UUID
    ) -> DeliberationOutcome | None:
        result = await self._db.execute(
            select(DeliberationOutcome).where(
                DeliberationOutcome.workspace_id == workspace_id,
                DeliberationOutcome.deliberation_run_id == run_id,
            )
        )
        return result.scalar_one_or_none()

    # --- events ---------------------------------------------------------------

    async def append_event(
        self,
        *,
        workspace_id: UUID,
        decision_case_id: UUID,
        run_id: UUID,
        category: DeliberationEventCategory,
        type_: str,
        origin_mode: str,
        source_origin_modes: list[str],
        payload: dict[str, Any],
    ) -> DeliberationEvent:
        last_sequence = int(
            await self._db.scalar(
                select(func.max(DeliberationEvent.sequence)).where(
                    DeliberationEvent.workspace_id == workspace_id,
                    DeliberationEvent.deliberation_run_id == run_id,
                )
            )
            or 0
        )
        event = DeliberationEvent(
            workspace_id=workspace_id,
            decision_case_id=decision_case_id,
            deliberation_run_id=run_id,
            sequence=last_sequence + 1,
            category=category,
            type=type_,
            origin_mode=origin_mode,
            source_origin_modes=source_origin_modes,
            payload=payload,
        )
        self._db.add(event)
        await self._db.flush()
        return event

    async def list_events_after(
        self, workspace_id: UUID, run_id: UUID, sequence: int
    ) -> Sequence[DeliberationEvent]:
        result = await self._db.execute(
            select(DeliberationEvent)
            .where(
                DeliberationEvent.workspace_id == workspace_id,
                DeliberationEvent.deliberation_run_id == run_id,
                DeliberationEvent.sequence > sequence,
            )
            .order_by(DeliberationEvent.sequence)
        )
        return result.scalars().all()
