"""Deliberation council service (CCR-20260804-DELIB-01).

Business actions with classification-first interventions (RunResolution
precedent): invalid classes are rejected structurally, never side-effected.
The frozen factor snapshot covers the OBJECTIVE basis (packets + influences);
subjective factors declared after creation are append-only interventions,
recorded with a Human stamp — they never rewrite the frozen basis.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analyses.models import AnalysisEvent, ResearchPacket
from app.models import AnalysisRun, DeliberationFactor
from app.simulations.factor_sandbox import factors_from_packets
from app.types import (
    DeliberationEventCategory,
    DeliberationFactorProvenance,
    DeliberationInterventionKind,
    DeliberationMessageKind,
    DeliberationNominationStatus,
    DeliberationProposalStatus,
    DeliberationRunStatus,
    DeliberationSpeaker,
    FactorEvidenceStatus,
    OriginMode,
    ResponsibilityActor,
)

from .orchestrator import snapshot_hash
from .repository import DeliberationNotFound, DeliberationRepository
from .schemas_api import MAX_DELIBERATION_ROUNDS


class DeliberationServiceError(RuntimeError):
    def __init__(self, code: str, message: str, http_status: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


async def load_case_basis(
    db: AsyncSession, workspace_id: UUID, decision_case_id: UUID
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(packets, influences) from the case's most recent analysis run.

    Mirrors reports.routes._latest_run_packets: the deliberation basis is the
    same deterministic factor derivation the sandbox exposes — never a second
    derivation of our own.
    """

    run_id = await db.scalar(
        select(AnalysisRun.analysis_run_id)
        .where(
            AnalysisRun.workspace_id == workspace_id,
            AnalysisRun.decision_case_id == decision_case_id,
        )
        .order_by(AnalysisRun.created_at.desc())
        .limit(1)
    )
    if run_id is None:
        return [], []
    rows = (
        await db.execute(
            select(ResearchPacket)
            .where(
                ResearchPacket.workspace_id == workspace_id,
                ResearchPacket.analysis_run_id == run_id,
            )
            .order_by(ResearchPacket.created_at, ResearchPacket.id)
        )
    ).scalars()
    packets = [
        {
            "factor": p.factor,
            "conclusion": p.conclusion,
            "direction": p.direction,
            "claim_support_score": p.claim_support_score,
        }
        for p in rows
    ]
    influences: list[dict[str, Any]] = []
    event_payloads = (
        await db.execute(
            select(AnalysisEvent.payload)
            .where(
                AnalysisEvent.workspace_id == workspace_id,
                AnalysisEvent.analysis_run_id == run_id,
                AnalysisEvent.type == "analysis.stage.completed",
            )
            .order_by(AnalysisEvent.sequence.desc())
        )
    ).scalars()
    for payload in event_payloads:
        if isinstance(payload, dict) and payload.get("stage") == "retrieving":
            raw = payload.get("influences")
            if isinstance(raw, list):
                influences = [e for e in raw if isinstance(e, dict)]
            break
    return packets, influences


class DeliberationService:
    def __init__(self, repo: DeliberationRepository, *, origin_mode: OriginMode) -> None:
        self._repo = repo
        self._origin_mode = origin_mode

    # --- creation -------------------------------------------------------------

    async def create_run(
        self,
        *,
        workspace_id: UUID,
        decision_case_id: UUID,
        user_id: UUID,
        packets: Sequence[Mapping[str, Any]],
        influences: Sequence[Mapping[str, Any]],
        subjective_declarations: Sequence[Mapping[str, Any]],
        max_rounds: int,
    ):
        if not 1 <= max_rounds <= MAX_DELIBERATION_ROUNDS:
            raise DeliberationServiceError(
                "DELIBERATION_BUDGET_INVALID", "maxRounds 必须在 1-5 之间。", 422
            )
        engine_factors = factors_from_packets(packets)
        if not engine_factors:
            raise DeliberationServiceError(
                "DELIBERATION_BASIS_EMPTY",
                "该 Case 尚无分析因子基线；先完成一次分析再开议会。",
                409,
            )
        for declaration in subjective_declarations:
            statement = str(declaration.get("statement") or "").strip()
            strength = declaration.get("strength")
            if not statement or not isinstance(strength, (int, float)) or not 0 <= float(strength) <= 1:
                raise DeliberationServiceError(
                    "DELIBERATION_DECLARATION_INVALID",
                    "主观因子声明必须携带非空陈述与 0-1 强度。",
                    422,
                )

        run = await self._repo.create_run(
            workspace_id=workspace_id,
            decision_case_id=decision_case_id,
            max_rounds=max_rounds,
            factor_snapshot_hash=snapshot_hash(packets, influences, []),
            origin_modes=[self._origin_mode.value],
        )

        for engine_factor in engine_factors:
            await self._repo.add_factor(
                DeliberationFactor(
                    workspace_id=workspace_id,
                    deliberation_run_id=run.id,
                    provenance=DeliberationFactorProvenance.OBJECTIVE,
                    label=engine_factor.label,
                    strength=round(engine_factor.value, 4),
                    source_factor_id=engine_factor.id,
                    evidence_status=None,
                )
            )
        for declaration in subjective_declarations:
            await self._repo.add_factor(
                DeliberationFactor(
                    workspace_id=workspace_id,
                    deliberation_run_id=run.id,
                    provenance=DeliberationFactorProvenance.SUBJECTIVE,
                    label=str(declaration.get("label") or "未命名主观因子")[:240],
                    strength=round(float(declaration["strength"]), 4),
                    statement=self._directional_statement(declaration),
                    author_user_id=user_id,
                    dossier_assumption_id=(
                        str(declaration["dossierAssumptionId"])
                        if declaration.get("dossierAssumptionId")
                        else None
                    ),
                    evidence_status=FactorEvidenceStatus.ASSUMED,
                )
            )
        await self._repo.append_event(
            workspace_id=workspace_id,
            decision_case_id=decision_case_id,
            run_id=run.id,
            category=DeliberationEventCategory.ROUND,
            type_="deliberation.run.created",
            origin_mode=self._origin_mode.value,
            source_origin_modes=[self._origin_mode.value],
            payload={
                "deliberationRunId": str(run.id),
                "factorSnapshotHash": run.factor_snapshot_hash,
                "maxRounds": max_rounds,
            },
        )
        return run

    @staticmethod
    def _directional_statement(declaration: Mapping[str, Any]) -> str:
        """Encode the declared direction as a statement prefix (engine seam)."""

        direction = str(declaration.get("direction") or "supporting").lower()
        statement = str(declaration.get("statement") or "").strip()
        if direction == "opposing":
            return f"[opposing] {statement}"
        if direction == "neutral":
            return f"[neutral] {statement}"
        return statement

    # --- interventions ----------------------------------------------------------

    async def intervene(
        self,
        *,
        workspace_id: UUID,
        run_id: UUID,
        user_id: UUID,
        kind: str,
        text: str | None,
        target_factor_id: str | None,
        subjective_factor: Mapping[str, Any] | None,
    ):
        run = await self._repo.get_run(workspace_id, run_id)
        if run is None:
            raise DeliberationNotFound()
        if run.status in (DeliberationRunStatus.COMPLETE, DeliberationRunStatus.CANCELLED):
            raise DeliberationServiceError(
                "DELIBERATION_RUN_CLOSED", "议会已结束，不能再介入。", 409
            )
        try:
            intervention_kind = DeliberationInterventionKind(kind)
        except ValueError:
            raise DeliberationServiceError(
                "DELIBERATION_INTERVENTION_INVALID", f"未知介入分类：{kind}", 422
            )

        round_row = await self._repo.active_round(workspace_id, run_id)

        if intervention_kind is DeliberationInterventionKind.INTERJECT:
            if not (text or "").strip():
                raise DeliberationServiceError(
                    "DELIBERATION_INTERVENTION_INVALID", "插话必须携带文本。", 422
                )
            await self._record_user_message(
                workspace_id=workspace_id,
                run=run,
                round_id=round_row.id if round_row else run.id,
                kind=DeliberationMessageKind.INTERVENTION,
                content=text.strip(),
                structured_payload={"intervention": intervention_kind.value},
            )
            return {"kind": intervention_kind.value, "recorded": True}

        if intervention_kind is DeliberationInterventionKind.CHALLENGE_WITNESS:
            if not target_factor_id or not (text or "").strip():
                raise DeliberationServiceError(
                    "DELIBERATION_INTERVENTION_INVALID",
                    "质询必须指定因子并携带问题文本。",
                    422,
                )
            await self._record_user_message(
                workspace_id=workspace_id,
                run=run,
                round_id=round_row.id if round_row else run.id,
                kind=DeliberationMessageKind.CHALLENGE,
                content=text.strip(),
                structured_payload={
                    "intervention": intervention_kind.value,
                    "targetFactorId": target_factor_id,
                },
            )
            return {"kind": intervention_kind.value, "recorded": True}

        if intervention_kind is DeliberationInterventionKind.DECLARE_SUBJECTIVE_FACTOR:
            if subjective_factor is None:
                raise DeliberationServiceError(
                    "DELIBERATION_INTERVENTION_INVALID",
                    "声明主观因子必须携带完整声明。",
                    422,
                )
            statement = str(subjective_factor.get("statement") or "").strip()
            strength = subjective_factor.get("strength")
            if not statement or not isinstance(strength, (int, float)) or not 0 <= float(strength) <= 1:
                raise DeliberationServiceError(
                    "DELIBERATION_DECLARATION_INVALID",
                    "主观因子声明必须携带非空陈述与 0-1 强度。",
                    422,
                )
            factor = await self._repo.add_factor(
                DeliberationFactor(
                    workspace_id=workspace_id,
                    deliberation_run_id=run_id,
                    provenance=DeliberationFactorProvenance.SUBJECTIVE,
                    label=str(subjective_factor.get("label") or "未命名主观因子")[:240],
                    strength=round(float(strength), 4),
                    statement=self._directional_statement(subjective_factor),
                    author_user_id=user_id,
                    dossier_assumption_id=(
                        str(subjective_factor["dossierAssumptionId"])
                        if subjective_factor.get("dossierAssumptionId")
                        else None
                    ),
                    evidence_status=FactorEvidenceStatus.ASSUMED,
                )
            )
            await self._record_user_message(
                workspace_id=workspace_id,
                run=run,
                round_id=round_row.id if round_row else run.id,
                kind=DeliberationMessageKind.INTERVENTION,
                content=f"声明主观因子「{factor.label}」（强度 {factor.strength:.2f}，assumed）。",
                structured_payload={
                    "intervention": intervention_kind.value,
                    "factorId": str(factor.id),
                },
            )
            return {"kind": intervention_kind.value, "factorId": str(factor.id)}

        # REOPEN_ROUND
        rounds_used = await self._repo.count_rounds(workspace_id, run_id)
        if rounds_used >= run.max_rounds:
            raise DeliberationServiceError(
                "DELIBERATION_BUDGET_EXHAUSTED",
                "轮次预算已用尽，不能再开一轮；议会将按现有状态走向裁决。",
                409,
            )
        await self._record_user_message(
            workspace_id=workspace_id,
            run=run,
            round_id=round_row.id if round_row else run.id,
            kind=DeliberationMessageKind.INTERVENTION,
            content="用户要求重开一轮质证。",
            structured_payload={"intervention": intervention_kind.value},
        )
        if run.status is DeliberationRunStatus.AWAITING_USER:
            await self._repo.transition_run(workspace_id, run_id, DeliberationRunStatus.RUNNING)
        return {"kind": intervention_kind.value, "recorded": True}

    async def _record_user_message(
        self,
        *,
        workspace_id: UUID,
        run,
        round_id: UUID,
        kind: DeliberationMessageKind,
        content: str,
        structured_payload: dict[str, Any],
    ) -> None:
        from app.models import DeliberationMessage

        message = DeliberationMessage(
            workspace_id=workspace_id,
            deliberation_run_id=run.id,
            round_id=round_id,
            speaker=DeliberationSpeaker.USER,
            kind=kind,
            content=content,
            structured_payload=structured_payload,
            stamp_actor=ResponsibilityActor.HUMAN,
            origin_mode=OriginMode.LIVE,
            source_origin_modes=[OriginMode.LIVE],
        )
        await self._repo.add_message(message)
        await self._repo.append_event(
            workspace_id=workspace_id,
            decision_case_id=run.decision_case_id,
            run_id=run.id,
            category=DeliberationEventCategory.MESSAGE,
            type_="deliberation.intervention.recorded",
            origin_mode=OriginMode.LIVE.value,
            source_origin_modes=[OriginMode.LIVE.value],
            payload={"kind": kind.value, "content": content},
        )

    # --- user decisions -----------------------------------------------------------

    async def decide_proposal(
        self, *, workspace_id: UUID, run_id: UUID, proposal_id: UUID, decision: str
    ):
        run = await self._repo.get_run(workspace_id, run_id)
        if run is None:
            raise DeliberationNotFound()
        proposal = await self._repo.get_proposal(workspace_id, run_id, proposal_id)
        if proposal is None:
            raise DeliberationNotFound()
        if decision not in ("accepted", "rejected"):
            raise DeliberationServiceError(
                "DELIBERATION_DECISION_INVALID", "决策必须是 accepted 或 rejected。", 422
            )
        target_status = (
            DeliberationProposalStatus.ACCEPTED
            if decision == "accepted"
            else DeliberationProposalStatus.REJECTED
        )
        if proposal.status is not DeliberationProposalStatus.PENDING:
            # Idempotent replay of an identical decision; conflicts rejected.
            if proposal.status is target_status:
                return proposal
            raise DeliberationServiceError(
                "DELIBERATION_PROPOSAL_DECIDED", "该提议已被裁决。", 409
            )
        from app.models import utc_now

        proposal.status = target_status
        proposal.decided_at = utc_now()
        if target_status is DeliberationProposalStatus.ACCEPTED and isinstance(proposal.after, dict):
            strength = proposal.after.get("strength")
            factor_id = proposal.after.get("factorId")
            if isinstance(strength, (int, float)) and factor_id:
                factors = await self._repo.list_factors(workspace_id, run_id)
                for factor in factors:
                    if str(factor.id) == str(factor_id):
                        factor.strength = round(float(strength), 4)
                        break
        await self._repo.append_event(
            workspace_id=workspace_id,
            decision_case_id=run.decision_case_id,
            run_id=run_id,
            category=DeliberationEventCategory.PROPOSAL,
            type_=f"deliberation.proposal.{target_status.value}",
            origin_mode=OriginMode.LIVE.value,
            source_origin_modes=[OriginMode.LIVE.value],
            payload={"proposalId": str(proposal.id), "decision": target_status.value},
        )
        return proposal

    async def decide_nomination(
        self,
        *,
        workspace_id: UUID,
        run_id: UUID,
        nomination_id: UUID,
        decision: str,
        user_id: UUID,
        subjective_factor: Mapping[str, Any] | None,
    ):
        run = await self._repo.get_run(workspace_id, run_id)
        if run is None:
            raise DeliberationNotFound()
        nomination = await self._repo.get_nomination(workspace_id, run_id, nomination_id)
        if nomination is None:
            raise DeliberationNotFound()
        if nomination.status is not DeliberationNominationStatus.PENDING:
            if decision in ("confirmed", "rejected") and nomination.status.value == decision:
                return nomination
            raise DeliberationServiceError(
                "DELIBERATION_NOMINATION_DECIDED", "该提名已被裁决。", 409
            )
        if decision == "confirmed":
            if subjective_factor is None:
                raise DeliberationServiceError(
                    "DELIBERATION_DECLARATION_INVALID",
                    "确认提名必须随附完整的主观因子声明。",
                    422,
                )
            statement = str(subjective_factor.get("statement") or "").strip()
            strength = subjective_factor.get("strength")
            if not statement or not isinstance(strength, (int, float)) or not 0 <= float(strength) <= 1:
                raise DeliberationServiceError(
                    "DELIBERATION_DECLARATION_INVALID",
                    "主观因子声明必须携带非空陈述与 0-1 强度。",
                    422,
                )
            factor = await self._repo.add_factor(
                DeliberationFactor(
                    workspace_id=workspace_id,
                    deliberation_run_id=run_id,
                    provenance=DeliberationFactorProvenance.SUBJECTIVE,
                    label=str(subjective_factor.get("label") or nomination.target_description)[:240],
                    strength=round(float(strength), 4),
                    statement=self._directional_statement(subjective_factor),
                    author_user_id=user_id,
                    dossier_assumption_id=(
                        str(subjective_factor["dossierAssumptionId"])
                        if subjective_factor.get("dossierAssumptionId")
                        else None
                    ),
                    evidence_status=FactorEvidenceStatus.ASSUMED,
                )
            )
            nomination.status = DeliberationNominationStatus.CONFIRMED
            nomination.confirmed_factor_id = str(factor.id)
            # Resume the run: the worker picks it up on the next claim.
            if run.status is DeliberationRunStatus.AWAITING_USER:
                await self._repo.transition_run(workspace_id, run_id, DeliberationRunStatus.RUNNING)
        elif decision == "rejected":
            nomination.status = DeliberationNominationStatus.REJECTED
            if run.status is DeliberationRunStatus.AWAITING_USER:
                pending = await self._repo.list_nominations(
                    workspace_id, run_id, status=DeliberationNominationStatus.PENDING
                )
                if not pending:
                    await self._repo.transition_run(
                        workspace_id, run_id, DeliberationRunStatus.RUNNING
                    )
        else:
            raise DeliberationServiceError(
                "DELIBERATION_DECISION_INVALID", "决策必须是 confirmed 或 rejected。", 422
            )
        await self._repo.append_event(
            workspace_id=workspace_id,
            decision_case_id=run.decision_case_id,
            run_id=run_id,
            category=DeliberationEventCategory.NOMINATION,
            type_=f"deliberation.nomination.{nomination.status.value}",
            origin_mode=OriginMode.LIVE.value,
            source_origin_modes=[OriginMode.LIVE.value],
            payload={"nominationId": str(nomination.id), "decision": nomination.status.value},
        )
        return nomination
