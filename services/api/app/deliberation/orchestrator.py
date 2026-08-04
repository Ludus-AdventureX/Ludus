"""Deliberation council orchestrator (CCR-20260804-DELIB-01).

One witness agent per factor, one moderator; rounds advance one step per
worker claim so users can intervene between rounds (SSE shows progress).

Engine adjudication iron rule: EVERY number (projection, flip point, delta)
comes from the deterministic ``factor_sandbox.simulate()``; agents never
self-report numbers. Fixture mode is fully deterministic and key-free; live
mode calls the locked ModelProvider with strict structured schemas (at most
one repair retry, then the output is dropped and recorded — agents never
fabricate).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from app.agents.model_provider import (
    ModelMessage,
    ModelProvider,
    complete_structured_checked,
)
from app.models import (
    DeliberationFactor,
    DeliberationMessage,
    DeliberationNomination,
    DeliberationOutcome,
    DeliberationProposal,
)
from app.simulations.factor_sandbox import (
    FactorNode,
    InfluenceEdge,
    edges_from_influences,
    factors_from_packets,
    simulate,
)
from app.types import (
    DeliberationEventCategory,
    DeliberationFactorProvenance,
    DeliberationMessageKind,
    DeliberationNominationStatus,
    DeliberationProposalKind,
    DeliberationProposalStatus,
    DeliberationRoundKind,
    DeliberationRunStatus,
    DeliberationSpeaker,
    OriginMode,
    ResponsibilityActor,
)

from .repository import DeliberationRepository

MAX_MESSAGES_PER_ROUND = 24
MAX_MODEL_CALLS_PER_RUN = 40
MAX_PROPOSALS_PER_ROUND = 6

WITNESS_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["stance", "argument"],
    "properties": {
        "stance": {"type": "string", "minLength": 1, "maxLength": 400},
        "argument": {"type": "string", "minLength": 1, "maxLength": 1200},
        "challengeTo": {"type": ["string", "null"]},
        "challengeText": {"type": ["string", "null"], "maxLength": 600},
        "proposal": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "required": ["factorId", "afterStrength"],
            "properties": {
                "factorId": {"type": "string"},
                "afterStrength": {"type": "number", "minimum": 0, "maximum": 1},
            },
        },
    },
}

MODERATOR_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary"],
    "properties": {"summary": {"type": "string", "minLength": 1, "maxLength": 1600}},
}


def snapshot_hash(
    packets: Sequence[Mapping[str, Any]],
    influences: Sequence[Mapping[str, Any]],
    subjective_declarations: Sequence[Mapping[str, Any]],
) -> str:
    canonical = json.dumps(
        {
            "packets": [dict(p) for p in packets],
            "influences": [dict(i) for i in influences],
            "subjective": [dict(s) for s in subjective_declarations],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def subjective_factor_node(factor: DeliberationFactor, index: int) -> FactorNode:
    """Engine node for a subjective factor: declared strength, human source.

    Direction derives from the declaration (supporting/opposing/neutral);
    weight magnitude is the declared strength — the number is the USER's,
    the arithmetic stays the engine's.
    """

    payload = factor.statement or ""
    direction = "supporting"
    if payload.startswith("[opposing]"):
        direction = "opposing"
    elif payload.startswith("[neutral]"):
        direction = "neutral"
    sign = -1.0 if direction == "opposing" else (0.0 if direction == "neutral" else 1.0)
    weight = sign * factor.strength if sign != 0.0 else 0.15 * factor.strength
    return FactorNode(
        id=factor.source_factor_id or f"s{index:02d}",
        label=factor.label,
        weight=round(weight, 4),
        value=round(factor.strength, 4),
        direction=direction,
        source=f"主观声明（Human 署名，{factor.evidence_status.value if factor.evidence_status else 'assumed'}）",
    )


class DeliberationOrchestrator:
    """Advances ONE step per claim; never loops over rounds in one claim."""

    def __init__(
        self,
        repo: DeliberationRepository,
        *,
        provider: ModelProvider | None,
        origin_mode: OriginMode,
        request_model: str = "deliberation-council/1.0",
    ) -> None:
        self._repo = repo
        self._provider = provider
        self._origin_mode = origin_mode
        self._request_model = request_model
        self._model_calls = 0

    # --- engine assembly ------------------------------------------------------

    def _engine_inputs(
        self,
        factors: Sequence[DeliberationFactor],
        packets: Sequence[Mapping[str, Any]],
        influences: Sequence[Mapping[str, Any]],
    ) -> tuple[list[FactorNode], list[InfluenceEdge]]:
        objective = factors_from_packets(packets)
        edges = edges_from_influences(influences, objective)
        nodes = list(objective)
        subjective = [f for f in factors if f.provenance is DeliberationFactorProvenance.SUBJECTIVE]
        for index, factor in enumerate(subjective, start=1):
            nodes.append(subjective_factor_node(factor, index))
        return nodes, edges

    @staticmethod
    def _engine_ids(factors: Sequence[DeliberationFactor]) -> dict[str, str]:
        """DeliberationFactor id (uuid str) -> engine node id (f01../s01..)."""

        mapping: dict[str, str] = {}
        subjective_index = 0
        for factor in factors:
            if factor.provenance is DeliberationFactorProvenance.SUBJECTIVE:
                subjective_index += 1
                mapping[str(factor.id)] = factor.source_factor_id or f"s{subjective_index:02d}"
            else:
                mapping[str(factor.id)] = factor.source_factor_id or ""
        return mapping

    def _simulate_current(
        self,
        factors: Sequence[DeliberationFactor],
        packets: Sequence[Mapping[str, Any]],
        influences: Sequence[Mapping[str, Any]],
        overrides: Mapping[str, float] | None = None,
    ) -> dict[str, Any]:
        nodes, edges = self._engine_inputs(factors, packets, influences)
        return simulate(nodes, overrides, edges)

    # --- messaging helpers ------------------------------------------------------

    async def _record_message(
        self,
        *,
        workspace_id: UUID,
        run_id: UUID,
        round_id: UUID,
        speaker: DeliberationSpeaker,
        kind: DeliberationMessageKind,
        content: str,
        speaker_factor_id: str | None = None,
        structured_payload: dict[str, Any] | None = None,
        actor: ResponsibilityActor = ResponsibilityActor.ANALYSIS,
    ) -> DeliberationMessage:
        message = DeliberationMessage(
            workspace_id=workspace_id,
            deliberation_run_id=run_id,
            round_id=round_id,
            speaker=speaker,
            speaker_factor_id=speaker_factor_id,
            kind=kind,
            content=content,
            structured_payload=structured_payload,
            stamp_actor=actor,
            origin_mode=self._origin_mode,
            source_origin_modes=[self._origin_mode],
        )
        saved = await self._repo.add_message(message)
        await self._repo.append_event(
            workspace_id=workspace_id,
            decision_case_id=(await self._repo.get_run(workspace_id, run_id)).decision_case_id,  # type: ignore[union-attr]
            run_id=run_id,
            category=DeliberationEventCategory.MESSAGE,
            type_="deliberation.message.recorded",
            origin_mode=self._origin_mode.value,
            source_origin_modes=[self._origin_mode.value],
            payload={
                "messageId": str(saved.id),
                "speaker": speaker.value,
                "speakerFactorId": speaker_factor_id,
                "kind": kind.value,
                "content": content,
            },
        )
        return saved

    async def _live_completion(self, *, system: str, prompt: str, schema: Mapping[str, Any]) -> Mapping[str, Any] | None:
        """Live structured output; None = drop-and-record on failure (§8 discipline)."""

        if self._provider is None or self._origin_mode is OriginMode.FIXTURE:
            return None
        if self._model_calls >= MAX_MODEL_CALLS_PER_RUN:
            return None
        self._model_calls += 1
        try:
            completion = await complete_structured_checked(
                self._provider,
                system=system,
                messages=[ModelMessage(role="user", content=prompt)],
                schema=dict(schema),
                request_model=self._request_model,
            )
            return completion.content
        except Exception:
            return None

    # --- fixture witnesses/moderator (deterministic) ---------------------------

    @staticmethod
    def _fixture_statement(factor: DeliberationFactor, result: Mapping[str, Any]) -> tuple[str, str]:
        delta = next(
            (d.get("scoreDelta") for d in result.get("topDrivers", [])
             if isinstance(d, Mapping) and d.get("label") == factor.label),
            None,
        )
        if factor.provenance is DeliberationFactorProvenance.SUBJECTIVE:
            stance = f"我持有主观判断「{factor.label}」，声明强度 {factor.strength:.2f}（assumed，Human 署名）。"
            argument = factor.statement or "该判断来自决策人声明，尚无可追溯证据。"
        else:
            stance = f"我持有客观因子「{factor.label}」，分析强度 {factor.strength:.2f}。"
            argument = f"依据来自研究 packet 的结论；引擎测得该因子对结论的边际影响为 {delta if delta is not None else 0:.4f}。"
        return stance, argument

    @staticmethod
    def _fixture_proposal(
        factor: DeliberationFactor, factors: Sequence[DeliberationFactor], result: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        # Deterministic rule: a witness whose factor sits on the OPPOSITE side
        # of the strongest driver asks to weaken that driver by one step (0.05).
        result_factors = {
            f.get("label"): f for f in result.get("factors", []) if isinstance(f, Mapping)
        }
        own = result_factors.get(factor.label)
        if own is None:
            return None  # subjective witness: no engine-side stance to argue from
        drivers = [d for d in result.get("topDrivers", []) if isinstance(d, Mapping)]
        if not drivers:
            return None
        top = drivers[0]
        top_label = top.get("label")
        if top_label == factor.label:
            return None
        target_result = result_factors.get(top_label)
        target = next((f for f in factors if f.label == top_label), None)
        if target is None or target_result is None:
            return None
        same_side = own.get("direction") == target_result.get("direction")
        if same_side:
            return None
        after = max(0.0, min(1.0, round(target.strength - 0.05, 4)))
        return {
            "kind": DeliberationProposalKind.FACTOR_STRENGTH.value,
            "proposerFactorId": str(factor.id),
            "targetFactorId": str(target.id),
            "before": {"factorId": str(target.id), "strength": target.strength},
            "after": {"factorId": str(target.id), "strength": after},
        }

    # --- nomination -------------------------------------------------------------

    async def _maybe_nominate(
        self,
        *,
        workspace_id: UUID,
        run_id: UUID,
        round_id: UUID,
        factors: Sequence[DeliberationFactor],
        result: Mapping[str, Any],
    ) -> bool:
        """Moderator nominates a missing subjective judgment when the most
        sensitive driver has NO subjective coverage. Never auto-activates: the
        nomination sits pending until the user confirms it."""

        existing_pending = await self._repo.list_nominations(
            workspace_id, run_id, status=DeliberationNominationStatus.PENDING
        )
        if existing_pending:
            return True  # already awaiting the user
        drivers = [d for d in result.get("topDrivers", []) if isinstance(d, Mapping)]
        if not drivers:
            return False
        top = drivers[0]
        top_label = top.get("label")
        covered = any(
            f.provenance is DeliberationFactorProvenance.SUBJECTIVE and f.label == top_label
            for f in factors
        )
        if covered:
            return False
        nomination = DeliberationNomination(
            workspace_id=workspace_id,
            deliberation_run_id=run_id,
            rationale=(
                f"最敏感驱动因子「{top_label}」目前没有任何主观判断覆盖；"
                "若你对它有内部认知（直觉/内部数据/对手反应判断），声明后会进入棋盘参与推演。"
            ),
            target_description=str(top_label),
            status=DeliberationNominationStatus.PENDING,
        )
        saved = await self._repo.add_nomination(nomination)
        await self._record_message(
            workspace_id=workspace_id,
            run_id=run_id,
            round_id=round_id,
            speaker=DeliberationSpeaker.MODERATOR,
            kind=DeliberationMessageKind.NOMINATION,
            content=f"提名：请就「{top_label}」补充主观判断（需你确认后生效）。",
            structured_payload={"nominationId": str(saved.id)},
        )
        run = await self._repo.get_run(workspace_id, run_id)
        await self._repo.append_event(
            workspace_id=workspace_id,
            decision_case_id=run.decision_case_id,  # type: ignore[union-attr]
            run_id=run_id,
            category=DeliberationEventCategory.NOMINATION,
            type_="deliberation.nomination.pending",
            origin_mode=self._origin_mode.value,
            source_origin_modes=[self._origin_mode.value],
            payload={"nominationId": str(saved.id), "target": str(top_label)},
        )
        return True

    # --- main advance step --------------------------------------------------------

    async def advance(
        self,
        workspace_id: UUID,
        run_id: UUID,
        *,
        packets: Sequence[Mapping[str, Any]],
        influences: Sequence[Mapping[str, Any]],
    ) -> DeliberationRunStatus:
        """Advance the run by at most one round/phase. Returns the new status."""

        run = await self._repo.get_run(workspace_id, run_id)
        if run is None or run.status not in (
            DeliberationRunStatus.PREPARING,
            DeliberationRunStatus.RUNNING,
        ):
            return run.status if run is not None else DeliberationRunStatus.CANCELLED

        # Snapshot integrity: the frozen OBJECTIVE basis must not have drifted.
        # Subjective factors are append-only interventions (recorded with a
        # Human stamp) and are deliberately outside the frozen hash.
        factors = await self._repo.list_factors(workspace_id, run_id)
        expected = snapshot_hash(packets, influences, [])
        if expected != run.factor_snapshot_hash:
            # Fail closed: never deliberate on a drifted basis.
            return (await self._repo.transition_run(
                workspace_id, run_id, DeliberationRunStatus.CANCELLED
            )).status

        result = self._simulate_current(factors, packets, influences)

        if run.status is DeliberationRunStatus.PREPARING:
            return await self._run_opening(workspace_id, run_id, factors, result)
        return await self._run_next_phase(workspace_id, run_id, factors, result, packets, influences)

    async def _run_opening(
        self,
        workspace_id: UUID,
        run_id: UUID,
        factors: Sequence[DeliberationFactor],
        result: Mapping[str, Any],
    ) -> DeliberationRunStatus:
        run = await self._repo.transition_run(
            workspace_id, run_id, DeliberationRunStatus.RUNNING, current_round_seq=1
        )
        round_row = await self._repo.open_round(
            workspace_id=workspace_id, run_id=run_id, seq=1, kind=DeliberationRoundKind.OPENING
        )
        await self._repo.append_event(
            workspace_id=workspace_id,
            decision_case_id=run.decision_case_id,
            run_id=run_id,
            category=DeliberationEventCategory.ROUND,
            type_="deliberation.round.opened",
            origin_mode=self._origin_mode.value,
            source_origin_modes=[self._origin_mode.value],
            payload={"roundSeq": 1, "kind": DeliberationRoundKind.OPENING.value},
        )
        count = 0
        for factor in factors:
            if count >= MAX_MESSAGES_PER_ROUND:
                break
            count += 1
            live = await self._live_completion(
                system=(
                    f"你是因子「{factor.label}」的持证人。只陈述与该因子相关的立场与依据；"
                    "禁止给出任何概率化断言；禁止自报数值结果（数值由引擎计算）。"
                ),
                prompt=(
                    f"因子：{factor.label}\n来源：{'主观声明' if factor.provenance is DeliberationFactorProvenance.SUBJECTIVE else '客观证据'}\n"
                    "请给出开场陈述（stance + argument）。"
                ),
                schema=WITNESS_SCHEMA,
            )
            if live is not None:
                stance = str(live.get("stance", "")) or "（立场为空，已按纪律丢弃）"
                argument = str(live.get("argument", "")) or "（陈述为空，已按纪律丢弃）"
            else:
                stance, argument = self._fixture_statement(factor, result)
            await self._record_message(
                workspace_id=workspace_id,
                run_id=run_id,
                round_id=round_row.id,
                speaker=DeliberationSpeaker.WITNESS,
                speaker_factor_id=str(factor.id),
                kind=DeliberationMessageKind.STATEMENT,
                content=f"{stance}\n{argument}",
            )
        await self._repo.complete_round(round_row)
        return DeliberationRunStatus.RUNNING

    async def _run_next_phase(
        self,
        workspace_id: UUID,
        run_id: UUID,
        factors: Sequence[DeliberationFactor],
        result: Mapping[str, Any],
        packets: Sequence[Mapping[str, Any]],
        influences: Sequence[Mapping[str, Any]],
    ) -> DeliberationRunStatus:
        run = await self._repo.get_run(workspace_id, run_id)
        assert run is not None
        rounds_used = await self._repo.count_rounds(workspace_id, run_id)
        # Budget exhausted -> straight to verdict (honest note included there).
        if rounds_used >= run.max_rounds:
            return await self._run_verdict(
                workspace_id, run_id, factors, packets, influences, budget_exhausted=True
            )

        round_row = await self._repo.open_round(
            workspace_id=workspace_id,
            run_id=run_id,
            seq=rounds_used + 1,
            kind=DeliberationRoundKind.CHALLENGE,
        )
        await self._repo.transition_run(
            workspace_id, run_id, DeliberationRunStatus.RUNNING, current_round_seq=rounds_used + 1
        )
        await self._repo.append_event(
            workspace_id=workspace_id,
            decision_case_id=run.decision_case_id,
            run_id=run_id,
            category=DeliberationEventCategory.ROUND,
            type_="deliberation.round.opened",
            origin_mode=self._origin_mode.value,
            source_origin_modes=[self._origin_mode.value],
            payload={"roundSeq": rounds_used + 1, "kind": DeliberationRoundKind.CHALLENGE.value},
        )

        # Witnesses cross-examine: deterministic fixture proposals, or live ones.
        proposals_made = 0
        messages_made = 0
        for factor in factors:
            if messages_made >= MAX_MESSAGES_PER_ROUND or proposals_made >= MAX_PROPOSALS_PER_ROUND:
                break
            live = await self._live_completion(
                system=(
                    f"你是因子「{factor.label}」的持证人，正在质证轮。你可以对其他因子提出强度调整提议；"
                    "禁止概率化断言；禁止自报数值结果。"
                ),
                prompt=f"当前引擎结论：{result.get('verdict')}。请给出质证发言，可选提交一个 factor_strength 提议。",
                schema=WITNESS_SCHEMA,
            )
            proposal_payload = None
            if live is not None:
                raw = live.get("proposal")
                if isinstance(raw, Mapping) and isinstance(raw.get("afterStrength"), (int, float)):
                    target_id = str(raw.get("factorId", ""))
                    target = next((f for f in factors if str(f.id) == target_id), None)
                    if target is not None:
                        proposal_payload = {
                            "kind": DeliberationProposalKind.FACTOR_STRENGTH.value,
                            "proposerFactorId": str(factor.id),
                            "targetFactorId": target_id,
                            "before": {"strength": target.strength},
                            "after": {"strength": max(0.0, min(1.0, float(raw["afterStrength"])))},
                        }
                content = str(live.get("argument", "")) or "（质证为空，已按纪律丢弃）"
            else:
                proposal_payload = self._fixture_proposal(factor, factors, result)
                content = (
                    f"质证：「{factor.label}」要求复核对结论影响最大的因子，并提议按引擎重算后的 delta 校准其强度。"
                    if proposal_payload is not None
                    else f"质证：「{factor.label}」维持当前立场，暂无提议。"
                )
            messages_made += 1
            await self._record_message(
                workspace_id=workspace_id,
                run_id=run_id,
                round_id=round_row.id,
                speaker=DeliberationSpeaker.WITNESS,
                speaker_factor_id=str(factor.id),
                kind=DeliberationMessageKind.REBUTTAL,
                content=content,
            )
            if proposal_payload is not None:
                proposals_made += 1
                engine_ids = self._engine_ids(factors)
                target_factor = next(
                    (f for f in factors if str(f.id) == proposal_payload["targetFactorId"]), None
                )
                engine_preview = None
                if target_factor is not None:
                    target_engine_id = engine_ids.get(str(target_factor.id), "")
                    proposal_payload["before"]["engineId"] = target_engine_id
                    proposal_payload["after"]["engineId"] = target_engine_id
                    nodes, edges = self._engine_inputs(factors, packets, influences)
                    engine_preview = simulate(
                        nodes,
                        {target_engine_id: float(proposal_payload["after"]["strength"])},
                        edges,
                    )
                proposal = DeliberationProposal(
                    workspace_id=workspace_id,
                    deliberation_run_id=run_id,
                    proposer_factor_id=proposal_payload["proposerFactorId"],
                    kind=DeliberationProposalKind(proposal_payload["kind"]),
                    before=proposal_payload["before"],
                    after=proposal_payload["after"],
                    status=DeliberationProposalStatus.PENDING,
                    engine_preview=engine_preview,
                )
                saved = await self._repo.add_proposal(proposal)
                await self._repo.append_event(
                    workspace_id=workspace_id,
                    decision_case_id=run.decision_case_id,
                    run_id=run_id,
                    category=DeliberationEventCategory.PROPOSAL,
                    type_="deliberation.proposal.pending",
                    origin_mode=self._origin_mode.value,
                    source_origin_modes=[self._origin_mode.value],
                    payload={"proposalId": str(saved.id), "kind": proposal_payload["kind"]},
                )

        await self._repo.complete_round(round_row)

        # Moderator: nominate missing subjective coverage; may park the run.
        nominated = await self._maybe_nominate(
            workspace_id=workspace_id, run_id=run_id, round_id=round_row.id,
            factors=factors, result=result,
        )
        if nominated:
            return (await self._repo.transition_run(
                workspace_id, run_id, DeliberationRunStatus.AWAITING_USER
            )).status
        return DeliberationRunStatus.RUNNING

    async def _run_verdict(
        self,
        workspace_id: UUID,
        run_id: UUID,
        factors: Sequence[DeliberationFactor],
        packets: Sequence[Mapping[str, Any]],
        influences: Sequence[Mapping[str, Any]],
        *,
        budget_exhausted: bool,
    ) -> DeliberationRunStatus:
        run = await self._repo.get_run(workspace_id, run_id)
        assert run is not None
        round_row = await self._repo.open_round(
            workspace_id=workspace_id,
            run_id=run_id,
            seq=(await self._repo.count_rounds(workspace_id, run_id)) + 1,
            kind=DeliberationRoundKind.VERDICT,
        )

        accepted = await self._repo.list_proposals(
            workspace_id, run_id, status=DeliberationProposalStatus.ACCEPTED
        )
        overrides: dict[str, float] = {}
        for proposal in accepted:
            if proposal.kind is DeliberationProposalKind.FACTOR_STRENGTH:
                engine_id = str(proposal.after.get("engineId") or "")
                strength = proposal.after.get("strength")
                if engine_id and isinstance(strength, (int, float)):
                    overrides[engine_id] = float(strength)
        nodes, edges = self._engine_inputs(factors, packets, influences)
        baseline = simulate(nodes, {}, edges)
        projected = simulate(nodes, overrides, edges) if overrides else baseline

        dissent_log: list[dict[str, Any]] = []
        rejected_proposers = {
            p.proposer_factor_id
            for p in await self._repo.list_proposals(workspace_id, run_id, status=DeliberationProposalStatus.REJECTED)
        }
        for factor in factors:
            if str(factor.id) in rejected_proposers:
                dissent_log.append({
                    "factorId": str(factor.id),
                    "witnessLabel": factor.label,
                    "originalStance": f"提议被用户驳回（强度主张 {factor.strength:.2f}）",
                    "overturnedBasis": "用户裁决：提议未获采纳；引擎按既有基线计算。",
                })

        flip_conditions = [
            {
                "factorId": str(d.get("nodeId")),
                "label": str(d.get("label")),
                "flipValue": d.get("flipValue"),
                "scoreDelta": d.get("scoreDelta"),
            }
            for d in projected.get("topDrivers", [])
            if isinstance(d, Mapping) and d.get("flipValue") is not None
        ][:5]

        outcome = DeliberationOutcome(
            workspace_id=workspace_id,
            deliberation_run_id=run_id,
            condition_projections=[
                {
                    "acceptedProposalIds": [],
                    "projection": {
                        "outcomeScore": baseline.get("outcomeScore"),
                        "verdict": baseline.get("verdict"),
                        "flipThreshold": baseline.get("flipThreshold"),
                    },
                    "condition": "基线：不采纳任何提议时，引擎的确定性投影。",
                },
                *(
                    [{
                        "acceptedProposalIds": [str(p.id) for p in accepted],
                        "projection": {
                            "outcomeScore": projected.get("outcomeScore"),
                            "verdict": projected.get("verdict"),
                            "flipThreshold": projected.get("flipThreshold"),
                        },
                        "condition": f"采纳全部 {len(accepted)} 条已接受提议后的引擎投影。",
                    }]
                    if accepted
                    else []
                ),
            ],
            flip_conditions=flip_conditions,
            dissent_log=dissent_log,
            assumption_ledger=[
                {
                    "factorId": str(f.id),
                    "label": f.label,
                    "provenance": f.provenance.value,
                    "evidenceStatus": f.evidence_status.value if f.evidence_status else None,
                    "finalStrength": f.strength,
                }
                for f in factors
            ],
            disclaimer="沙盘与议会不代表精确预测。",
        )
        await self._repo.set_outcome(outcome)

        summary = (
            f"裁决：基线结论 {baseline.get('verdict')}（倾向得分 {baseline.get('outcomeScore')}）；"
            + (f"采纳 {len(accepted)} 条提议后投影 {projected.get('verdict')}（{projected.get('outcomeScore')}）。" if accepted else "无已采纳提议。")
            + ("注：轮次预算已用尽，本轮为预算触顶裁决。" if budget_exhausted else "")
        )
        live = await self._live_completion(
            system="你是推演议会主持。只允许条件化表述；禁止任何概率化断言。",
            prompt=f"请基于以下引擎结果作裁决总结：{json.dumps({'baseline': baseline.get('verdict'), 'projected': projected.get('verdict')}, ensure_ascii=False)}",
            schema=MODERATOR_SCHEMA,
        )
        if live is not None and live.get("summary"):
            summary = str(live["summary"])
        await self._record_message(
            workspace_id=workspace_id,
            run_id=run_id,
            round_id=round_row.id,
            speaker=DeliberationSpeaker.MODERATOR,
            kind=DeliberationMessageKind.VERDICT_SUMMARY,
            content=summary,
        )
        await self._repo.complete_round(round_row)
        await self._repo.append_event(
            workspace_id=workspace_id,
            decision_case_id=run.decision_case_id,
            run_id=run_id,
            category=DeliberationEventCategory.OUTCOME,
            type_="deliberation.outcome.ready",
            origin_mode=self._origin_mode.value,
            source_origin_modes=[self._origin_mode.value],
            payload={
                "outcomeId": str(outcome.id),
                "baselineVerdict": baseline.get("verdict"),
                "projectedVerdict": projected.get("verdict"),
            },
        )
        return (await self._repo.transition_run(
            workspace_id, run_id, DeliberationRunStatus.COMPLETE
        )).status
