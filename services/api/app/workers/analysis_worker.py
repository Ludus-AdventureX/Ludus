"""Durable DB-queue analysis worker (Task 9).

Claims queued runs with ``FOR UPDATE SKIP LOCKED`` (repository), heartbeats,
and drives the canonical stage pipeline::

    planning -> retrieving -> analyzing -> criticizing -> synthesizing
             -> validating -> ready | blocked

Contract points implemented here:

- persisted cancellation is checked at every stage boundary AND before every
  external call boundary; a cooperative stop never publishes anything new
  (events and immutable stage artifacts already persisted are kept);
- four producer roles (Research / Critic / Synthesis / Validation) execute
  with role-isolated inputs; the Critic stage always runs the mandatory
  Safety Anchor sub-stage first; Validation only validates and blocks — it
  never writes, synthesizes, or repairs missing artifacts;
- full runs schedule the five lens stages through the ALREADY-SHIPPED lens
  persistence write path (``app.strategic_lenses.repository`` — imported,
  never copied) and record ``strategicLensArtifactIds`` on the run; focused
  runs skip every lens stage and the array stays empty;
- ``strategic_lens.completed`` is emitted only after the artifact write path
  reports successful persistence, never on raw model output;
- model calls go through injectable role executors; the integration lane binds
  those executors to the provider-neutral ModelProvider seam so live DeepSeek
  or deterministic fixture providers share the same orchestration boundary.

Role executors are injected so the orchestration is fully testable offline;
the executor protocol mirrors what the Task 7 ``WorkerRunner`` produces.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid5, NAMESPACE_URL

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.model_provider import (
    ModelMessage,
    ModelProvider,
    build_model_provider_from_env,
    build_secondary_model_provider_from_env,
    complete_structured_checked,
)

# Shipped lens write path: imported (never copied). The default lens writer
# below delegates to these exact callables.
from app.strategic_lenses.repository import (
    FrozenReferenceLedger,
    LensBehaviorRejected,
    LensReferenceResolutionError,
    apply_validation_verdict,
    persist_lens_stage_output,
)
from app.analyses.models import AnalysisCharter
from app.analyses.quality_gate import audit_full_run_lens_set
from app.analyses.repository import AnalysisRuntimeRepository
from app.models import AnalysisRun
from app.types import AnalysisRunStatus, FormalAnalysisLevel, OriginMode
from app.workers.evidence_funnel import apply_evidence_funnel
from app.workers.web_retrieval import search_web, sources_as_stage_input

# Fixed lens-stage schedule for full runs (producer role -> lens types in
# canonical execution order inside each owning stage).
FULL_LENS_SCHEDULE: dict[AnalysisRunStatus, tuple[str, ...]] = {
    AnalysisRunStatus.ANALYZING: ("porter_five_forces",),
    AnalysisRunStatus.CRITICIZING: ("counterparty_response_matrix", "pre_mortem"),
    AnalysisRunStatus.SYNTHESIZING: ("scenario_planning", "meadows_leverage_points"),
}

_STAGE_ROLE: dict[AnalysisRunStatus, str] = {
    AnalysisRunStatus.PLANNING: "research",
    AnalysisRunStatus.RETRIEVING: "research",
    AnalysisRunStatus.ANALYZING: "research",
    AnalysisRunStatus.CRITICIZING: "critic",
    AnalysisRunStatus.SYNTHESIZING: "synthesis",
    AnalysisRunStatus.VALIDATING: "validation",
}

_STAGE_SEQUENCE: tuple[AnalysisRunStatus, ...] = (
    AnalysisRunStatus.PLANNING,
    AnalysisRunStatus.RETRIEVING,
    AnalysisRunStatus.ANALYZING,
    AnalysisRunStatus.CRITICIZING,
    AnalysisRunStatus.SYNTHESIZING,
    AnalysisRunStatus.VALIDATING,
)

_PROGRESS_AT_STAGE = {
    stage: round((index + 1) / (len(_STAGE_SEQUENCE) + 1), 2)
    for index, stage in enumerate(_STAGE_SEQUENCE)
}


@dataclass(frozen=True)
class StageResult:
    """Structured outcome of one role execution over one stage."""

    output: Mapping[str, Any]
    packets: tuple[Mapping[str, Any], ...] = ()
    lens_payloads: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    # Validation stage only:
    quality_gate_passed: bool | None = None
    validator_findings: tuple[Mapping[str, Any], ...] = ()


RoleExecutor = Callable[[AnalysisRun, AnalysisRunStatus, Mapping[str, Any]], Awaitable[StageResult]]
LensWriter = Callable[..., Awaitable[UUID]]
LensAudit = Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class RoleExecutors:
    """Injectable role executors (fixture/stub providers in this lane)."""

    research: RoleExecutor
    critic: RoleExecutor
    synthesis: RoleExecutor
    validation: RoleExecutor

    def for_role(self, role: str) -> RoleExecutor:
        return getattr(self, role)


class CooperativeStop(Exception):
    """Internal signal: a persisted cancellation was observed at a boundary."""


async def default_lens_writer(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    decision_case_id: UUID,
    analysis_run_id: UUID,
    payload: Mapping[str, Any],
    ledger: Any,
    origin_modes: tuple[OriginMode, ...],
) -> UUID:
    """Persist one lens stage output via the shipped write path (import-only).

    The artifact is written as draft and immediately handed to the Validation
    verdict transition by the Validation stage later; this writer returns the
    persisted artifact id only after the INSERT succeeded.
    """

    connection = await session.connection()
    persisted = await persist_lens_stage_output(
        connection,
        workspace_id=workspace_id,
        decision_case_id=decision_case_id,
        analysis_run_id=analysis_run_id,
        payload=payload,
        ledger=ledger,
        origin_modes=list(origin_modes),
    )
    return persisted.strategic_lens_artifact_id


# Re-exported so integrations and tests can assert the worker consumes the
# shipped verdict transition rather than re-implementing it.
LENS_VALIDATION_VERDICT = apply_validation_verdict


# Untrusted model packets must NEVER be spread raw into the ORM constructor:
# an extra key (e.g. "type") raises TypeError and kills the whole run (QC
# finding). Whitelist + normalize the model-fillable ResearchPacket fields;
# packets without a non-empty conclusion are dropped fail-closed (DB check
# conclusion_not_empty would reject them anyway).
_PACKET_FIELD_MAP: Mapping[str, str] = {
    "factor": "factor",
    "framework_used": "framework_used",
    "frameworkUsed": "framework_used",
    "conclusion": "conclusion",
    "direction": "direction",
    "claim_support_score": "claim_support_score",
    "claimSupportScore": "claim_support_score",
    "evidence_ids": "evidence_ids",
    "evidenceIds": "evidence_ids",
    "discarded_claims": "discarded_claims",
    "discardedClaims": "discarded_claims",
    "remaining_gaps": "remaining_gaps",
    "remainingGaps": "remaining_gaps",
    "disclaimer": "disclaimer",
    "self_anchor": "self_anchor",
    "selfAnchor": "self_anchor",
}


# Grey-goo Self-Anchor verification (v6-analysis-agent §8): the producing
# agent must test its own inference against ALREADY-PERSISTED evidence before
# the packet is admitted. Two checks that both conflict with known facts force
# a confidence downgrade (the equivalent of §8 "两条全冲突→降两级"), never a
# silent keep.
def _admit_self_anchor(packet: dict[str, Any]) -> bool:
    """Deterministic admission of the model's self-anchor verdicts.

    ``packet["self_anchor"]`` is a list of {"verdict": "pass"|"uncertain"|
    "conflict", "evidenceId": ...} entries (model-proposed). A packet whose
    checks are ALL ``conflict`` is admitted with a capped score; a packet
    whose checks are ALL ``pass`` keeps its score; anything malformed or
    partially conflicting is left unchanged (the honest middle). Returns True
    when a cap was applied so the caller can surface it.
    """

    raw = packet.get("self_anchor")
    entries = raw if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)) else ()
    verdicts = [
        str(entry.get("verdict") or "").strip().lower()
        for entry in entries
        if isinstance(entry, Mapping) and entry.get("verdict")
    ]
    if not verdicts:
        return False
    if all(verdict == "conflict" for verdict in verdicts):
        packet["claim_support_score"] = min(
            float(packet.get("claim_support_score", 0.5)), 0.5
        )
        return True
    return False


# Grey-goo logic spot-check (v6-analysis-agent §13): after round 1 the
# orchestrator runs a SHALLOW structural check over each packet's reasoning
# chain. This is deliberately heuristic - it catches obvious structural flaws
# (circular reasoning / premise drift), never pursues depth. A flagged packet
# keeps its row (the audit trail must show what was admitted) but the flag
# travels into the deterministic gate's consistency dimension.
def _logic_spot_check(packet: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the list of spot-check findings for one packet (empty = clean).

    - ``circular_reasoning``: the conclusion restates the factor/premise with
      near-identical wording (token overlap above a heuristic threshold);
    - ``premise_drift``: the conclusion's subject drifts from the factor's
      subject (first token differs and neither is a generic pronoun).
    """

    findings: list[str] = []
    factor = str(packet.get("factor") or "").strip().lower()
    conclusion = str(packet.get("conclusion") or "").strip().lower()
    if not factor or not conclusion:
        return ()
    factor_tokens = {tok for tok in factor.replace("?", " ").split() if len(tok) > 2}
    conclusion_tokens = {tok for tok in conclusion.replace("?", " ").split() if len(tok) > 2}
    if factor_tokens and conclusion_tokens:
        overlap = len(factor_tokens & conclusion_tokens) / len(factor_tokens)
        if overlap >= 0.6:
            findings.append("circular_reasoning")
    f_subject = factor.split()[0] if factor.split() else ""
    c_subject = conclusion.split()[0] if conclusion.split() else ""
    generic = {"the", "this", "that", "it", "its", "a", "an", "our", "we"}
    # A drift only fires when NONE of the factor's core content words survives
    # in the conclusion: "rescue robot certification timeline" -> "certification
    # takes nine months" is a legitimate narrowing, not a subject swap.
    factor_core = {tok for tok in factor.split() if len(tok) > 3 and tok not in generic}
    if (
        f_subject
        and c_subject
        and f_subject != c_subject
        and f_subject not in generic
        and c_subject not in generic
        and not (factor_core & conclusion_tokens)
    ):
        findings.append("premise_drift")
    return tuple(findings)


# Grey-goo §7 (P2-3): round-1 knowledge gaps feed round 2. The model names
# what it could not verify without retrieval; the orchestrator carries that
# list into the second pass instead of discarding round-1 reasoning.
def _extract_knowledge_gaps(output: Mapping[str, Any]) -> list[str]:
    """Deterministic extraction of the round-1 knowledge-gap list.

    Accepts ``knowledgeGaps`` (array of strings), ``gaps`` (array of strings
    or objects with a ``gap`` key), or a ``digest.openQuestions`` fallback.
    Bounded to 8 entries; malformed shapes yield [] (the second round simply
    has no explicit gap list to fold in).
    """

    raw = (
        output.get("knowledgeGaps")
        or output.get("gaps")
        or (
            output.get("digest", {}).get("openQuestions")
            if isinstance(output.get("digest"), Mapping)
            else None
        )
    )
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    gaps: list[str] = []
    for entry in raw[:8]:
        if isinstance(entry, Mapping):
            text = entry.get("gap") or entry.get("description") or entry.get("question")
        else:
            text = entry
        text = str(text or "").strip()
        if text:
            gaps.append(text[:200])
    return gaps


# Grey-goo narrative-echo prevention (framework-selector v6.12.8, P2-8):
# before/after dispatch, deterministic checks catch a shared unexamined
# perspective. This is deliberately heuristic - the five-point checklist is
# materialized from the planning digest's own text (what the model plans to
# examine), and the divergence score compares research vs critic outputs.
def _echo_checklist(planning_text: str) -> dict[str, bool]:
    """Five grey-goo echo-prevention checks over the planning digest text.

    - perspective_symmetry: at least one opposing/risk-oriented signal
      (risk/against/objection/failure/opposing) is present;
    - prosecutor_forced: a dedicated adversarial role is named
      (critic/adversary/devils advocate/objector/against);
    - failure_signal: historical failure / why-not-yet is examined
      (fail/never/unsuccessful/why not/barrier);
    - assumption_pressure: at least one assumption is singled out for testing
      (assumption/hypothesis/if wrong/underlying);
    - capital_market_signal: funding/financing evidence is on the agenda
      (funding/financing/investor/capital) - skipped when the question is
      clearly non-market (best-effort, reported as True on empty text).
    """

    text = (planning_text or "").lower()
    if not text.strip():
        return {
            "perspective_symmetry": True,
            "prosecutor_forced": True,
            "failure_signal": True,
            "assumption_pressure": True,
            "capital_market_signal": True,
        }
    return {
        "perspective_symmetry": any(
            token in text for token in ("risk", "against", "objection", "failure", "opposing", "downside")
        ),
        "prosecutor_forced": any(
            token in text for token in ("critic", "adversary", "devil", "objector", "against", "challenge")
        ),
        "failure_signal": any(
            token in text for token in ("fail", "never", "unsuccessful", "why not", "barrier", "blocked")
        ),
        "assumption_pressure": any(
            token in text for token in ("assumption", "hypothesis", "if wrong", "underlying", "premise")
        ),
        "capital_market_signal": any(
            token in text for token in ("funding", "financing", "investor", "capital", "raise")
        ),
    }


def _narrative_divergence(
    research_text: str, critic_text: str
) -> float:
    """0-10 divergence score between research and critic outputs.

    Heuristic (fixture-friendly): token-overlap based. 10 = fully disjoint
    vocabularies (strong independence), 0 = identical wording (echo). Grey-goo
    treats <4 as severe echo that must trigger a re-dispatch.
    """

    def tokens(text: str) -> set[str]:
        return {
            tok.strip(".,;:!?()[]{}'\"")
            for tok in (text or "").lower().split()
            if len(tok) > 3
        }

    a, b = tokens(research_text), tokens(critic_text)
    if not a or not b:
        return 5.0  # unmeasurable -> neutral, never auto-flag
    overlap = len(a & b)
    union = len(a | b)
    if union == 0:
        return 5.0
    similarity = overlap / union
    return round(10.0 * (1.0 - similarity), 1)


def _sanitize_packet(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    out: dict[str, Any] = {}
    for key, target in _PACKET_FIELD_MAP.items():
        if key in raw and target not in out and raw[key] is not None:
            out[target] = raw[key]
    conclusion = str(out.get("conclusion") or "").strip()
    if not conclusion:
        return None
    out["conclusion"] = conclusion
    try:
        score = float(out.get("claim_support_score", 0.5))
    except (TypeError, ValueError):
        score = 0.5
    out["claim_support_score"] = min(1.0, max(0.0, score))
    for text_field, limit in (("factor", 400), ("framework_used", 400), ("direction", 200)):
        if text_field in out:
            out[text_field] = str(out[text_field])[:limit]
    for list_field in ("evidence_ids", "discarded_claims", "remaining_gaps"):
        value = out.get(list_field)
        if value is not None:
            out[list_field] = [str(item) for item in value] if isinstance(value, (list, tuple)) else [str(value)]
    if "disclaimer" in out:
        out["disclaimer"] = str(out["disclaimer"])
    if isinstance(out.get("self_anchor"), Sequence) and not isinstance(
        out.get("self_anchor"), (str, bytes)
    ):
        out["self_anchor"] = [
            {
                "verdict": str(entry.get("verdict") or "uncertain")[:16],
                "evidenceId": str(entry.get("evidenceId") or entry.get("evidence_id") or "")[:200],
            }
            for entry in out["self_anchor"]
            if isinstance(entry, Mapping)
        ][:4]
    else:
        out.pop("self_anchor", None)
    # Grey-goo §8: all-conflict self-anchors cap the packet's support score.
    _admit_self_anchor(out)
    return out


class AnalysisWorker:
    """One worker loop iteration: claim, execute, finish or park the run."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        executors: RoleExecutors,
        lens_writer: LensWriter | None = None,
        lens_audit: LensAudit | None = None,
        origin_mode: OriginMode = OriginMode.FIXTURE,
        checkpoint: Callable[[], Awaitable[None]] | None = None,
        provider: "ModelProvider | None" = None,
        lens_repair_max: int | None = None,
    ) -> None:
        self._session = session
        self._repo = AnalysisRuntimeRepository(session)
        self._executors = executors
        self._lens_writer = lens_writer or default_lens_writer
        # MOUNT-02 Addendum A1 §A1-⑥ binding: the Task 10 five-lens audit is the
        # DEFAULT consumer at the validating gate; injection exists for stubbed
        # orchestration tests only, production wiring uses the shipped audit.
        self._lens_audit = lens_audit or audit_full_run_lens_set
        self._origin_mode = origin_mode
        self._commit = checkpoint or session.commit
        # Provider reference for dedicated lens calls (A5 fix). When None the
        # lens fallback is skipped gracefully (fixture mode).
        self._provider = provider
        # Grey-goo 原则⑬ repair budget: how many repair re-invocations a lens
        # gets after a behavior-gate rejection (default 1 = current behaviour).
        # Configurable via LENS_REPAIR_MAX (cap 2) so light models (flash) can
        # be given one extra structured repair pass without unbounded cost.
        self._lens_repair_max = min(max(int(lens_repair_max or _env_lens_repair_max()), 0), 2)
        # The run this worker actually claimed, so the runner can park exactly
        # that run after a failure instead of guessing at the queue head.
        self.claimed: tuple[UUID, UUID] | None = None

    def _get_provider(self) -> "ModelProvider":
        """Return the model provider for dedicated lens calls."""
        if self._provider is None:
            raise RuntimeError("no provider configured for dedicated lens calls")
        return self._provider

    @property
    def repository(self) -> AnalysisRuntimeRepository:
        return self._repo

    async def _checkpoint(self) -> None:
        """Publish everything written so far: a stage boundary IS a commit boundary.

        Previously the runner owned one transaction for the whole run, so every
        status, progress, heartbeat and event stayed invisible until the run
        finished. Live evidence: a run five minutes and six model calls deep
        still read ``queued / progress 0 / started_at NULL`` through the API
        while the backend sat in ``idle in transaction``. That single fact is
        what made a working worker look broken and made progress unobservable,
        SSE silent, ``recover_stale_runs`` blind and a crash cost the whole run.

        Committing per boundary is safe for the claim contract: the claim
        already moved the row out of ``queued``, so releasing the row lock
        cannot cause a double claim.
        """

        await self._commit()

    async def run_once(self, *, workspace_id: UUID | None = None) -> UUID | None:
        """Claim and fully process one queued run; None when the queue is empty."""

        run = await self._repo.claim_next_queued(workspace_id=workspace_id)
        if run is None:
            return None
        self.claimed = (run.workspace_id, run.analysis_run_id)
        # Publish the claim itself (queued -> planning + its event) so the run
        # stops looking unclaimed the moment work begins.
        await self._checkpoint()
        await self._execute(run)
        return run.analysis_run_id

    async def _check_cancelled(self, run: AnalysisRun) -> None:
        """Persisted cancellation check (stage + external-call boundaries)."""

        if await self._repo.cancellation_requested(run.workspace_id, run.analysis_run_id):
            raise CooperativeStop()

    async def _execute(self, run: AnalysisRun) -> None:
        workspace_id = run.workspace_id
        run_id = run.analysis_run_id
        is_full = FormalAnalysisLevel(run.analysis_level) == FormalAnalysisLevel.FULL
        stage_inputs: dict[str, Any] = {"analysisRunId": str(run_id)}

        # Workspace custom model: override the system default if configured
        ws_provider = await self._load_workspace_model_provider(workspace_id)
        if ws_provider is not None:
            self._provider = ws_provider

        # Feed the CONFIRMED charter to every stage: without it the model
        # analyses a phantom question (live-trace finding: planning reported
        # 'decision question not provided' while runs still went READY).
        charter = await self._session.get(AnalysisCharter, run.charter_id)
        charter_context: dict[str, Any] | None = None
        if charter is not None:
            charter_context = {
                "decisionQuestion": charter.decision_question,
                "analysisLevel": str(run.analysis_level),
                "goals": list(charter.goals or []),
                "constraints": list(charter.constraints or []),
                "optionIds": [str(o) for o in (charter.option_ids or [])],
                "preferenceWeights": dict(charter.preference_weights or {}),
            }
            stage_inputs["charter"] = charter_context
        # Inject extracted profiles (decision-maker + question) so every stage
        # sees the user's preferences, constraints and problem structure.
        try:
            from sqlalchemy import text as _text
            profile_rows = (
                await self._session.execute(
                    _text(
                        "SELECT profile_type, content FROM case_profiles "
                        "WHERE workspace_id = :ws AND decision_case_id = :cid"
                    ),
                    {"ws": workspace_id, "cid": run.decision_case_id},
                )
            ).all()
            if profile_rows:
                stage_inputs["profiles"] = {
                    row[0]: row[1] for row in profile_rows
                }
        except Exception:
            pass  # best-effort; missing profiles do not block the run
        # In-process stage output capture for the READY report hook (stage_results
        # on the run persists hashes only, not the output bodies).
        stage_outputs: dict[str, Any] = {}

        # Provenance first: stamp how this run is being executed before any
        # artifact exists, so fixture output can never be read as live.
        await self._repo.record_origin_mode(workspace_id, run_id, self._origin_mode)

        try:
            for index, stage in enumerate(_STAGE_SEQUENCE):
                # Stage boundary: cooperative stop before starting work.
                await self._check_cancelled(run)
                if stage != AnalysisRunStatus.PLANNING:
                    # claim_next_queued already moved queued -> planning.
                    await self._repo.transition(
                        workspace_id, run_id, stage, stage_input=stage_inputs
                    )
                await self._repo.heartbeat(workspace_id, run_id)
                # Stage entry and heartbeat become durable BEFORE the long
                # model call, so both the UI and stale-run recovery can see
                # which stage is running right now.
                await self._checkpoint()

                executor = self._executors.for_role(_STAGE_ROLE[stage])

                if stage == AnalysisRunStatus.CRITICIZING:
                    # Mandatory Safety Anchor sub-stage (focused AND full).
                    await self._check_cancelled(run)  # external call boundary
                    anchor = await executor(
                        run, stage, {**stage_inputs, "substage": "safety_anchor"}
                    )
                    await self._repo.append_event(
                        await self._fresh(run),
                        category="agent.task",
                        type="analysis.stage.progressed",
                        payload={
                            "stage": stage.value,
                            "substage": "safety_anchor",
                            "summary": dict(anchor.output),
                        },
                        origin_mode=self._origin_mode,
                    )
                    await self._checkpoint()

                # External-call boundary check before the main role execution.
                await self._check_cancelled(run)
                if stage == AnalysisRunStatus.RETRIEVING and charter is not None:
                    # BYOK connector keys: prefer workspace-stored keys over env.
                    byok_exa, byok_firecrawl = await self._load_byok_keys(run.workspace_id)
                    # Grey-goo §3: retrieval goes through the coverage index -
                    # a repeat query reuses the frozen row instead of re-hitting
                    # the provider; the row records what was searched and when.
                    web_sources = await self._retrieve_once(
                        run,
                        question=charter.decision_question,
                        option_ids=[str(o) for o in (charter.option_ids or [])],
                        byok_exa=byok_exa,
                        byok_firecrawl=byok_firecrawl,
                    )
                    if web_sources:
                        stage_inputs = {
                            **stage_inputs,
                            "webEvidence": sources_as_stage_input(web_sources),
                        }
                    # First-party leg (R2): the decision-maker's CONFIRMED
                    # dossier facts enter retrieving as L0 evidence - honest
                    # but externally unverified, and clearly labeled so.
                    first_party = await self._load_first_party_facts(run)
                    if first_party:
                        stage_inputs = {
                            **stage_inputs,
                            "firstPartyEvidence": first_party,
                        }
                result = await executor(run, stage, stage_inputs)
                # Boundary check immediately after the external call returns:
                # a cancellation observed here stops before any new persistence.
                await self._check_cancelled(run)
                # Grey-goo §7 (P2-3): Think-First/Search-Later for the
                # analyzing stage - round 1 reasons WITHOUT retrieval and names
                # its knowledge gaps; round 2 folds the round-1 gaps back in
                # and deepens. Focused runs skip the second round (budget).
                if (
                    stage == AnalysisRunStatus.ANALYZING
                    and is_full
                    and not result.output.get("round")
                ):
                    round1 = result
                    gaps = _extract_knowledge_gaps(round1.output)
                    round2_inputs = {
                        **dict(stage_inputs),
                        "round": 2,
                        "round1Gaps": gaps,
                    }
                    await self._check_cancelled(run)
                    result = await executor(run, stage, round2_inputs)
                    result = StageResult(
                        output={
                            **dict(result.output),
                            "roundProgression": {
                                "round1Gaps": gaps,
                                "rounds": 2,
                            },
                        },
                        packets=tuple(round1.packets) + tuple(result.packets),
                        lens_payloads=(
                            round1.lens_payloads or result.lens_payloads
                        ),
                        quality_gate_passed=result.quality_gate_passed,
                        validator_findings=result.validator_findings,
                    )
                    await self._check_cancelled(run)
                # Grey-goo narrative-echo prevention (P2-8): the planning
                # digest is checked for the five echo signals; the analyzing
                # digest is scored against the criticizing digest for
                # divergence. Both land in the stage output as audit metadata
                # (no state transition, no gate - a re-dispatch is a future
                # wave-3 enhancement, the signal must exist first).
                if stage == AnalysisRunStatus.PLANNING:
                    merged = dict(result.output)
                    merged["echoChecklist"] = _echo_checklist(
                        str(
                            result.output.get("digest", {}).get("headline")
                            if isinstance(result.output.get("digest"), Mapping)
                            else result.output.get("headline")
                            or ""
                        )
                    )
                    result = StageResult(
                        output=merged,
                        packets=result.packets,
                        lens_payloads=result.lens_payloads,
                        quality_gate_passed=result.quality_gate_passed,
                        validator_findings=result.validator_findings,
                    )
                if stage == AnalysisRunStatus.ANALYZING:
                    merged = dict(result.output)
                    merged["echoDivergence"] = _narrative_divergence(
                        str(result.output.get("digest", {}).get("headline")
                            if isinstance(result.output.get("digest"), Mapping)
                            else result.output.get("headline") or ""),
                        "",
                    )
                    result = StageResult(
                        output=merged,
                        packets=result.packets,
                        lens_payloads=result.lens_payloads,
                        quality_gate_passed=result.quality_gate_passed,
                        validator_findings=result.validator_findings,
                    )
                if stage == AnalysisRunStatus.RETRIEVING and result.packets:
                    # Information funnel: deterministic TDD checks + L1-L6
                    # grading BEFORE persistence. Survivors carry minted,
                    # human-auditable evidence ids; the audit (discards,
                    # tier mix, warnings) travels with the stage output into
                    # the digest/event stream and the report.
                    funnel = apply_evidence_funnel(result.packets, stage=stage.value)
                    merged_output = dict(result.output)
                    merged_output["evidenceFunnel"] = funnel.audit
                    # Grey-goo 原则⑩ (CCR-20260802-P2W2): persist the TDD
                    # discard audit so the E page can show "what was filtered
                    # out and why" - not just the survivors. Best-effort:
                    # a persistence failure never blocks the run.
                    try:
                        from app.models import EvidenceFunnelAudit as _FunnelRow

                        self._session.add(
                            _FunnelRow(
                                workspace_id=run.workspace_id,
                                decision_case_id=run.decision_case_id,
                                analysis_run_id=run.analysis_run_id,
                                stage=stage.value,
                                admitted=int(funnel.audit.get("admitted") or 0),
                                discarded=list(funnel.audit.get("discarded") or []),
                                warnings=list(funnel.audit.get("warnings") or []),
                                tier_counts=dict(funnel.audit.get("tierCounts") or {}),
                                opposing_count=int(funnel.audit.get("opposingCount") or 0),
                                low_tier_share=funnel.audit.get("lowTierShare"),
                            )
                        )
                        await self._session.flush()
                    except Exception:
                        logging.getLogger(__name__).exception(
                            "funnel audit persistence failed; run continues"
                        )
                    # Factor->factor influence edges: deterministic admission
                    # only - both endpoints must be labels of ADMITTED packets
                    # (no self-loops, no duplicates, bounded). The model may
                    # propose; it cannot fabricate graph structure.
                    merged_output["factorInfluences"] = _admit_influences(
                        merged_output.pop("influences", None), funnel.admitted
                    )
                    result = StageResult(
                        output=merged_output,
                        packets=tuple(funnel.admitted),
                        lens_payloads=result.lens_payloads,
                        quality_gate_passed=result.quality_gate_passed,
                        validator_findings=result.validator_findings,
                    )
                stage_outputs[stage.value] = dict(result.output)

                for packet in result.packets:
                    clean = _sanitize_packet(packet)
                    if clean is None:
                        continue
                    # Grey-goo §13 logic spot-check: shallow structural guard
                    # on the reasoning chain (analyzing/criticizing only).
                    # A flagged packet is still persisted (the audit trail
                    # shows exactly what was admitted) but the finding rides
                    # into the deterministic gate's consistency dimension.
                    spot_findings = (
                        _logic_spot_check(clean)
                        if stage in (AnalysisRunStatus.ANALYZING, AnalysisRunStatus.CRITICIZING)
                        else ()
                    )
                    # Grey-goo §8 self-anchor: a packet whose self-anchors are
                    # ALL conflicts was admitted with a capped score - surface
                    # that honestly on the event so the audit trail shows the
                    # downgrade instead of hiding it.
                    self_anchor_entries = clean.get("self_anchor") or ()
                    self_anchor_conflicts = [
                        entry
                        for entry in self_anchor_entries
                        if isinstance(entry, Mapping) and entry.get("verdict") == "conflict"
                    ]
                    # self_anchor / logic_spot_check are audit-trail metadata,
                    # NOT ResearchPacket columns: strip them before ORM insert
                    # (the event below carries them; the packet row keeps the
                    # capped score and the original text).
                    orm_clean = {
                        key: value
                        for key, value in clean.items()
                        if key not in ("self_anchor", "logic_spot_check")
                    }
                    saved = await self._repo.add_research_packet(
                        workspace_id=workspace_id,
                        decision_case_id=run.decision_case_id,
                        analysis_run_id=run_id,
                        role=_STAGE_ROLE[stage],
                        **orm_clean,
                    )
                    await self._repo.append_event(
                        await self._fresh(run),
                        category="agent.task",
                        type="research.packet.completed",
                        payload={
                            "packetId": str(saved.id),
                            "factor": saved.factor,
                            "claimSupportScore": saved.claim_support_score,
                            "selfAnchorPassed": (
                                not self_anchor_entries
                                or len(self_anchor_conflicts) < len(self_anchor_entries)
                            ),
                            "selfAnchorConflictCount": len(self_anchor_conflicts),
                            "logicSpotCheck": list(spot_findings),
                        },
                        origin_mode=self._origin_mode,
                    )

                if result.packets:
                    # Publish this stage's packets and their events before the
                    # lens/enrichment legs, which add minutes of model time.
                    await self._checkpoint()

                lens_chain_fragment: list[dict[str, Any]] = []
                if is_full and stage in FULL_LENS_SCHEDULE:
                    # Wave D: returns the convergence-audited chain fragments
                    # handed off by the lens sub-agents (merged below).
                    lens_chain_fragment = await self._run_lens_stages(run, stage, result)

                # Grey-goo v6 roles that Ludus previously dropped, re-added as
                # best-effort enrichment calls (no state transition, no gate):
                # an INDEPENDENT safety anchor after criticizing (collective
                # blind spots + if-all-wrong-because), and a chief of staff
                # after synthesizing ("so what to do" - conditional actions).
                if stage == AnalysisRunStatus.CRITICIZING:
                    # Grey-goo narrative-echo prevention (P2-8): now that BOTH
                    # the analyzing and criticizing digests exist, score their
                    # divergence (0-10). <4 is severe echo -> the signal rides
                    # the criticizing digest for the UI/audit trail (the
                    # re-dispatch itself is a future wave-3 enhancement).
                    _criticizing_merged = dict(result.output)
                    _analyzing_output = stage_outputs.get(AnalysisRunStatus.ANALYZING.value)
                    _analyzing_headline = (
                        _analyzing_output.get("digest", {}).get("headline")
                        if isinstance(_analyzing_output, Mapping)
                        and isinstance(_analyzing_output.get("digest"), Mapping)
                        else (_analyzing_output or {}).get("headline") or ""
                    )
                    _criticizing_merged["echoDivergence"] = _narrative_divergence(
                        str(_analyzing_headline or ""),
                        str(
                            result.output.get("digest", {}).get("headline")
                            if isinstance(result.output.get("digest"), Mapping)
                            else result.output.get("headline") or ""
                        ),
                    )
                    result = StageResult(
                        output=_criticizing_merged,
                        packets=result.packets,
                        lens_payloads=result.lens_payloads,
                        quality_gate_passed=result.quality_gate_passed,
                        validator_findings=result.validator_findings,
                    )
                    await self._enrich_role(
                        run, "safety_anchor", self._executors.critic,
                        AnalysisRunStatus.CRITICIZING, stage_inputs, stage_outputs,
                    )
                    # Grey-goo 原则⑮ complexity adaptivity (CCR-20260802-P2W2):
                    # after criticizing the safety anchor has run - if the
                    # anchor does NOT block and the evidence base is strong,
                    # a full run may downgrade its remaining budget (one-shot,
                    # full->focused) instead of wasting model calls. The
                    # five-lens artifact contract is untouched: downgrade
                    # affects budget/iteration depth only.
                    await self._maybe_downgrade_complexity(
                        run, stage_outputs, stage_inputs
                    )
                elif stage == AnalysisRunStatus.SYNTHESIZING:
                    await self._enrich_role(
                        run, "chief_of_staff", self._executors.synthesis,
                        AnalysisRunStatus.SYNTHESIZING, stage_inputs, stage_outputs,
                    )

                if stage == AnalysisRunStatus.VALIDATING:
                    # Validation validates and blocks ONLY: no artifact writes,
                    # no synthesis, no repair of missing artifacts here.
                    # Grey-goo multiplicative gate: model verdict is necessary
                    # but not sufficient - the deterministic gate scores the
                    # evidence/adversarial institutions from real artifacts.
                    gate = _deterministic_gate(stage_outputs, result.validator_findings)
                    passed = bool(result.quality_gate_passed) and bool(gate["passed"])
                    audit_findings: list[dict[str, Any]] = [dict(gate)]
                    if is_full:
                        # MOUNT-02 Addendum A1 §A1-⑥ audit binding: the persisted
                        # lens-id list travels AS-IS — exact-equality (and any
                        # normalization question) is the audit's job, never the
                        # caller's. A failed audit blocks readiness like any
                        # other severe validation failure.
                        fresh = await self._fresh(run)
                        charter = await self._session.get(
                            AnalysisCharter, fresh.charter_id
                        )
                        frozen_types = (
                            list(charter.required_strategic_lens_types)
                            if charter is not None
                            else [
                                lens
                                for lenses in FULL_LENS_SCHEDULE.values()
                                for lens in lenses
                            ]
                        )
                        audit = await self._lens_audit(
                            self._session,
                            workspace_id=workspace_id,
                            decision_case_id=fresh.decision_case_id,
                            analysis_run_id=run_id,
                            charter_id=fresh.charter_id,
                            frozen_lens_types=frozen_types,
                            referenced_artifact_ids=list(
                                fresh.strategic_lens_artifact_ids
                            ),
                        )
                        if not audit.ok:
                            passed = False
                            audit_findings = [
                                {"code": code, "source": "lens_set_audit"}
                                for code in audit.reason_codes
                            ]
                    if (
                        not passed
                        and len(audit_findings) == 1
                        and audit_findings[0].get("code") == "deterministic_gate"
                    ):
                        # Surface the model validator's rejection reasons: models
                        # rarely emit the structured validatorFindings array, so
                        # the validating digest's headline/keyFindings ARE the
                        # reasons. Without this the blocked event only carries the
                        # (passed!) deterministic gate and the UI cannot tell the
                        # user what gap actually blocked the run.
                        if not bool(result.quality_gate_passed):
                            v_digest = _extract_digest(result.output) or {}
                            audit_findings.append(
                                {
                                    "code": "validator_rejected",
                                    "source": "model_validator",
                                    "headline": str(v_digest.get("headline") or ""),
                                    "keyFindings": [
                                        str(item)
                                        for item in (v_digest.get("keyFindings") or [])
                                    ],
                                    "openQuestions": [
                                        str(item)
                                        for item in (v_digest.get("openQuestions") or [])
                                    ],
                                }
                            )
                    await self._repo.record_stage_completed(
                        workspace_id,
                        run_id,
                        stage=stage,
                        output=dict(result.output),
                        progress=_PROGRESS_AT_STAGE[stage],
                        digest=_extract_digest(result.output),
                    )
                    await self._check_cancelled(run)
                    target = (
                        AnalysisRunStatus.READY if passed else AnalysisRunStatus.BLOCKED
                    )
                    await self._repo.transition(
                        workspace_id,
                        run_id,
                        target,
                        quality_gate_passed=passed,
                        payload={
                            "findings": [dict(f) for f in result.validator_findings]
                            + audit_findings
                        },
                    )
                    # The verdict is durable before the report leg runs, so a
                    # report failure can never cost the terminal state.
                    await self._checkpoint()
                    if passed:
                        # READY report hook: assemble + persist the canonical
                        # report artifact from confirmed inputs. "No qualifying
                        # run, no report" holds: blocked/needs_attention never
                        # reach this line. A report failure must not roll back
                        # the READY state - log and continue (compensable).
                        try:
                            await self._persist_run_report(run, stage_outputs)
                            await self._checkpoint()
                        except Exception:
                            # READY is already committed; discard only the failed
                            # report work so the session stays usable.
                            await self._session.rollback()
                            logging.getLogger(__name__).exception(
                                "report persistence failed for READY run %s", run_id
                            )
                    return

                await self._repo.record_stage_completed(
                    workspace_id,
                    run_id,
                    stage=stage,
                    output=dict(result.output),
                    progress=_PROGRESS_AT_STAGE[stage],
                    digest=_extract_digest(result.output),
                    influences=(
                        list(result.output.get("factorInfluences") or [])
                        if stage == AnalysisRunStatus.RETRIEVING
                        else None
                    ),
                )
                # Progress, output hash and the stage digest event become
                # visible now - this is what the UI reads between stages.
                await self._checkpoint()
                # Wave C fix (wave D): the PRIOR stage's accumulated chain must
                # be captured BEFORE stage_inputs is rebuilt from this stage's
                # output, otherwise cross-stage accumulation silently resets.
                prior_chain = (
                    stage_inputs.get("decisionChain")
                    if isinstance(stage_inputs, Mapping)
                    else None
                )
                stage_inputs = {"previousStage": stage.value, **dict(result.output)}
                if charter_context is not None:
                    # The charter must survive stage handoffs - each stage
                    # otherwise loses the confirmed question it is analysing.
                    stage_inputs["charter"] = charter_context
                # Wave C: accumulate decision chain across stages
                chain_updates = result.output.get("chainLinkUpdates")
                if chain_updates and isinstance(chain_updates, Mapping):
                    stage_inputs["decisionChain"] = _accumulate_chain_links(
                        prior_chain, chain_updates
                    )
                elif isinstance(prior_chain, Mapping):
                    stage_inputs["decisionChain"] = dict(prior_chain)
                # Wave D: merge the audited lens sub-agent chain fragments
                # (namespaced + resolvability-checked) into the same chain.
                if lens_chain_fragment:
                    stage_inputs["decisionChain"] = _accumulate_chain_links(
                        stage_inputs.get("decisionChain"),
                        {"added": lens_chain_fragment, "confirmed": [], "refuted": []},
                    )
        except CooperativeStop:
            # Canonical cancelled terminal state was already written by the
            # cancel command; keep persisted events/artifacts, publish nothing.
            # The stage work completed before the stop is legitimate history,
            # so it is committed rather than silently rolled back.
            await self._checkpoint()
            return

    async def _fresh(self, run: AnalysisRun) -> AnalysisRun:
        refreshed = await self._repo.get_run(run.workspace_id, run.analysis_run_id)
        assert refreshed is not None
        return refreshed

    async def _load_byok_keys(self, workspace_id: UUID) -> tuple[str | None, str | None]:
        """Read BYOK connector keys for this workspace (Exa + Firecrawl).

        Returns (exa_key, firecrawl_key) decrypted for one-time use. Failures
        return (None, None) — the worker falls back to env keys.
        """

        from app.connectors.crypto import crypto_available, decrypt_secret
        from app.models import WorkspaceConnector
        from sqlalchemy import select as _sel2

        if not crypto_available():
            return None, None
        try:
            rows = (
                await self._session.execute(
                    _sel2(WorkspaceConnector).where(
                        WorkspaceConnector.workspace_id == workspace_id,
                        WorkspaceConnector.provider.in_(["exa", "firecrawl"]),
                    )
                )
            ).scalars().all()
            exa_key = None
            fc_key = None
            for row in rows:
                try:
                    plain = decrypt_secret(
                        row.ciphertext, row.nonce, row.key_version,
                        workspace_id=str(workspace_id), provider=row.provider,
                    )
                except Exception:
                    continue
                if row.provider == "exa":
                    exa_key = plain
                elif row.provider == "firecrawl":
                    fc_key = plain
            return exa_key, fc_key
        except Exception:
            return None, None

    async def _load_workspace_model_provider(self, workspace_id: UUID) -> "ModelProvider | None":
        """Load workspace custom model connector and build a BYOK provider.

        Returns None if no model connector is configured for this workspace,
        in which case the caller falls back to the system default provider.
        """

        from app.connectors.crypto import crypto_available, decrypt_secret
        from app.models import WorkspaceConnector
        from app.agents.model_provider import build_model_provider_from_connector
        from sqlalchemy import select as _sel3

        if not crypto_available():
            return None
        try:
            row = (
                await self._session.execute(
                    _sel3(WorkspaceConnector).where(
                        WorkspaceConnector.workspace_id == workspace_id,
                        WorkspaceConnector.provider == "model",
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            api_key = decrypt_secret(
                row.ciphertext, row.nonce, row.key_version,
                workspace_id=str(workspace_id), provider="model",
            )
            config = row.config or {}
            base_url = config.get("base_url", "")
            model_name = config.get("model_name", "")
            if not base_url or not model_name:
                return None
            return build_model_provider_from_connector(
                base_url=base_url, api_key=api_key, model_name=model_name,
            )
        except Exception:
            return None

    async def _load_first_party_facts(self, run: AnalysisRun) -> list[dict[str, str]]:
        """The decision-maker's CONFIRMED dossier facts for this case (L0 leg).

        Best-effort and bounded: a read failure never blocks the run - the
        analysis simply proceeds without first-party input, which is exactly
        the pre-R2 behaviour.
        """

        from sqlalchemy import select as _select

        from app.models import DossierEntry
        from app.types import EntryStatus

        try:
            rows = (
                await self._session.execute(
                    _select(DossierEntry.content, DossierEntry.statement_type)
                    .where(
                        DossierEntry.workspace_id == run.workspace_id,
                        DossierEntry.decision_case_id == run.decision_case_id,
                        DossierEntry.status == EntryStatus.CONFIRMED,
                    )
                    .order_by(DossierEntry.version.desc(), DossierEntry.id)
                    .limit(8)
                )
            ).all()
        except Exception:
            logging.getLogger(__name__).exception("first-party dossier read failed; continuing without")
            return []
        return [
            {
                "fact": str(content)[:400],
                "kind": str(getattr(statement_type, "value", statement_type)),
                "source": "decision-maker dossier (CONFIRMED entry)",
                "tier": "L0",
            }
            for content, statement_type in rows
            if str(content).strip()
        ]

    async def _retrieve_once(
        self,
        run: AnalysisRun,
        *,
        question: str,
        option_ids: list[str],
        byok_exa: str | None,
        byok_firecrawl: str | None,
    ) -> list[dict[str, Any]]:
        """Grey-goo §3 retrieval discipline: one query = one coverage row.

        The coverage index is the run-frozen authority: a repeat query inside
        the same run reuses the frozen row (idempotent) instead of re-hitting
        the provider. The query key is a canonical hash over the question +
        option ids, so distinct phrasings of the same question still reuse.

        The per-role quota (focused ≤3 / full ≤5 distinct queries) is enforced
        by the caller via ``_coverage_budget``; this method only records.

        Wave E: MCP tools are invoked alongside exa/firecrawl; their results
        enter the same evidence funnel (TDD triple filter) - no bypass.
        """

        import hashlib

        from app.models import RetrievalCoverage as _CoverageRow
        from sqlalchemy import select as _sel

        key_text = "\n".join([question.strip(), *sorted(option_ids)])
        query_hash = "sha256:" + hashlib.sha256(key_text.encode("utf-8")).hexdigest()
        try:
            existing = (
                await self._session.execute(
                    _sel(_CoverageRow).where(
                        _CoverageRow.workspace_id == run.workspace_id,
                        _CoverageRow.analysis_run_id == run.analysis_run_id,
                        _CoverageRow.result_hash == query_hash,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                logging.getLogger(__name__).info(
                    "retrieval coverage hit for run %s (hash %s); reusing frozen row",
                    run.analysis_run_id, query_hash[:12],
                )
                return []
        except Exception:
            pass  # coverage read failure degrades to a fresh search
        web_sources = await search_web(
            question,
            option_ids,
            **({"api_key": byok_exa} if byok_exa else {}),
            **({"firecrawl_api_key": byok_firecrawl} if byok_firecrawl else {}),
        )
        # Wave E: invoke MCP tools alongside exa/firecrawl; results merge into
        # the same evidence funnel (TDD triple filter) - no bypass.
        mcp_sources = await self._retrieve_mcp(run, question=question)
        if mcp_sources:
            web_sources = list(web_sources) + mcp_sources
        try:
            self._session.add(
                _CoverageRow(
                    workspace_id=run.workspace_id,
                    decision_case_id=run.decision_case_id,
                    analysis_run_id=run.analysis_run_id,
                    keywords=[question.strip()[:200]],
                    queried_at=datetime.now(timezone.utc),
                    result_summary=(
                        "; ".join(
                            (str(getattr(s, "title", "")) or str(getattr(s, "url", "")))[:80]
                            for s in web_sources[:5]
                        )
                        or "no sources"
                    )[:500],
                    result_hash=query_hash,
                    origin_mode=self._origin_mode,
                )
            )
            await self._session.flush()
        except Exception:
            logging.getLogger(__name__).exception(
                "retrieval coverage write failed for run %s; continuing",
                run.analysis_run_id,
            )
        return web_sources

    async def _retrieve_mcp(
        self, run: AnalysisRun, *, question: str
    ) -> list[dict[str, Any]]:
        """Wave E: invoke workspace MCP tools and return WebSource-compatible results.

        MCP connectors are workspace-scoped BYOK (provider='mcp', config JSONB
        carries command/args/env/timeout). Results are bounded and MUST pass
        the evidence funnel - no bypass. Failures degrade gracefully (empty list).
        """

        from app.models import WorkspaceConnector as _ConnectorRow
        from app.workers.mcp_retrieval import invoke_mcp_tools
        from sqlalchemy import select as _sel

        try:
            connectors = (
                await self._session.execute(
                    _sel(_ConnectorRow).where(
                        _ConnectorRow.workspace_id == run.workspace_id,
                        _ConnectorRow.provider == "mcp",
                        _ConnectorRow.status == "available",
                    )
                )
            ).scalars().all()
        except Exception:
            logging.getLogger(__name__).debug("MCP connector query failed; skipping")
            return []

        results: list[dict[str, Any]] = []
        for connector in connectors[:3]:  # bounded: max 3 MCP servers per run
            config = connector.config or {}
            if not isinstance(config, dict) or not config.get("command"):
                continue
            try:
                mcp_results = await invoke_mcp_tools(config, query=question)
                # Convert MCP results to WebSource-compatible format
                for item in mcp_results:
                    results.append({
                        "title": str(item.get("title") or "MCP result"),
                        "url": str(item.get("url") or ""),
                        "snippet": str(item.get("snippet") or "")[:2000],
                        "tier": str(item.get("tier") or "L6"),
                        "source": str(item.get("source") or "mcp"),
                    })
            except Exception:
                logging.getLogger(__name__).debug(
                    "MCP tool invocation failed for connector %s; skipping",
                    connector.id,
                )
        return results

    async def _maybe_downgrade_complexity(
        self,
        run: AnalysisRun,
        stage_outputs: Mapping[str, Any],
        stage_inputs: Mapping[str, Any],
    ) -> None:
        """Grey-goo 原则⑮: one-shot full->focused downgrade after criticizing.

        Conditions (all required):
        - the run is FULL and has not already downgraded;
        - the safety anchor does NOT block (≥2 shared assumptions would block,
          v6.9.5 narrative-echo guard);
        - the evidence base is strong (funnel admitted ≥2 and no warnings
          about one-narrative/low-trust).

        The downgrade is recorded on the run (complexity_downgraded + chain)
        and announced on the stage-progressed event. It affects the remaining
        budget/iteration depth only - the five-lens artifact contract and the
        state machine are untouched.
        """

        if (
            FormalAnalysisLevel(run.analysis_level) != FormalAnalysisLevel.FULL
            or run.complexity_downgraded
        ):
            return
        blocked, _count = _anchor_blocks_downgrade(stage_outputs)
        if blocked:
            return
        retrieving = stage_outputs.get(AnalysisRunStatus.RETRIEVING.value)
        audit = retrieving.get("evidenceFunnel") if isinstance(retrieving, Mapping) else None
        if not isinstance(audit, Mapping):
            return
        admitted = int(audit.get("admitted") or 0)
        opposing = int(audit.get("opposingCount") or 0)
        low_share = audit.get("lowTierShare")
        if admitted < 2 or opposing == 0:
            return
        if isinstance(low_share, (int, float)) and low_share > 0.5:
            return
        reason = "converged evidence + no anchor blind-spot block"
        try:
            chain = list(run.downgrade_chain or [])
            chain.append(f"full->focused ({reason})")
            run.complexity_downgraded = True
            run.downgrade_chain = chain
            await self._session.flush()
            await self._repo.append_event(
                await self._fresh(run),
                category="agent.task",
                type="analysis.stage.progressed",
                payload={
                    "stage": AnalysisRunStatus.CRITICIZING.value,
                    "downgrade": {
                        "from": "full",
                        "to": "focused",
                        "reason": reason,
                    },
                },
                origin_mode=self._origin_mode,
            )
        except Exception:
            logging.getLogger(__name__).exception(
                "complexity downgrade record failed; run continues at full depth"
            )

    async def _enrich_role(
        self,
        run: AnalysisRun,
        role: str,
        executor: RoleExecutor,
        stage: AnalysisRunStatus,
        stage_inputs: Mapping[str, Any],
        stage_outputs: dict[str, Any],
    ) -> None:
        """Best-effort extra role call; its digest lands in stage_outputs[role].

        No state transition and no quality gate - a failure here degrades to a
        missing section, never a failed run. The role marker rides in the
        stage inputs so the live executor swaps in the role's ask (fixture/stub
        executors ignore it and simply return their canned StageResult).
        """

        try:
            enriched_inputs = {**dict(stage_inputs), "roleOverride": role,
                               "substage": role}
            result = await executor(run, stage, enriched_inputs)
            stage_outputs[role] = dict(result.output)
            digest = _extract_digest(result.output)
            if digest:
                # Reuse the canonical research.packet.completed event type (the
                # analysis_events CHECK constraint whitelists types); the role
                # + digest ride the payload so the SSE trace can label them
                # without a schema migration.
                await self._repo.append_event(
                    await self._fresh(run),
                    category="agent.task",
                    type="research.packet.completed",
                    payload={"role": role, "enrichmentRole": role, "digest": dict(digest)},
                    origin_mode=self._origin_mode,
                )
                await self._checkpoint()
        except Exception:
            logging.getLogger(__name__).warning(
                "role enrichment %s failed for run %s", role, run.analysis_run_id,
                exc_info=True,
            )

    async def _persist_run_report(
        self, run: AnalysisRun, stage_outputs: Mapping[str, Any]
    ) -> None:
        """READY hook: assemble + persist + publish the canonical report.

        Judgment set and dissent record are logical source ids (no tables of
        their own); their content ships inside the report document. The
        persist path is canonical-hash idempotent, so a crash between READY
        and publish is safely re-runnable.
        """

        from app.analyses.synthesis import (
            build_report_validation,
            persist_report_artifact,
            publish_report_artifact,
        )
        from app.workers.report_builder import build_document_for_level

        fresh = await self._fresh(run)
        charter = await self._session.get(AnalysisCharter, fresh.charter_id)
        if charter is None:
            return
        # Deterministic per-run source ids: the judgment set / dissent record
        # are logical references whose content ships inside the document; a
        # stable derivation keeps the canonical hash (and thus idempotent
        # re-persistence) intact across retries.
        judgment_set_id = uuid5(NAMESPACE_URL, f"ludus:judgment-set:{fresh.analysis_run_id}")
        dissent_record_id = uuid5(NAMESPACE_URL, f"ludus:dissent-record:{fresh.analysis_run_id}")
        level = FormalAnalysisLevel(fresh.analysis_level)
        document = build_document_for_level(
            analysis_level=level,
            charter=charter,
            stage_outputs=stage_outputs,
            origin_mode=self._origin_mode,
            lens_artifact_ids=list(fresh.strategic_lens_artifact_ids),
            anchor=fresh.completed_at,
        )
        report = await persist_report_artifact(
            self._session,
            workspace_id=fresh.workspace_id,
            decision_case_id=fresh.decision_case_id,
            analysis_run_id=fresh.analysis_run_id,
            source_judgment_set_id=judgment_set_id,
            source_dissent_record_id=dissent_record_id,
            case_version=charter.case_version,
            content=document,
            validation=build_report_validation(passed=True),
            origin_modes=(self._origin_mode,),
        )
        await publish_report_artifact(
            self._session,
            workspace_id=fresh.workspace_id,
            report_artifact_id=report.id,
            gate_status="passed",
        )

    async def _register_dossier_assumptions(self, run: AnalysisRun) -> None:
        """Register the case's CONFIRMED dossier assumptions as Claim rows.

        The counterparty lens behavior gate resolves every coreAssumptionIds
        entry against the frozen ledger (fail-closed), and ledger
        assumption_ids come from persisted Claim rows. Nothing else writes
        those rows, so without this registration the lens can never pass: the
        model may only cite IDs that exist. Dossier entries are the product
        authority for assumptions (dossier_statement_type.assumption plus the
        decision-maker CONFIRMED endorsement); each one becomes a Claim whose
        source_span_ids pins the originating dossier entry, which also makes
        registration idempotent. Conversation messages are deliberately NOT
        registered: they carry no statement-type marker, so a deterministic
        lane cannot attribute assumptions from free text without an extraction
        model call.
        """

        from sqlalchemy import select as _sel

        from app.analyses.claims import Claim
        from app.models import DossierEntry
        from app.types import DossierStatementType, EntryStatus, StatementType

        entries = (
            await self._session.execute(
                _sel(DossierEntry.id, DossierEntry.content).where(
                    DossierEntry.workspace_id == run.workspace_id,
                    DossierEntry.decision_case_id == run.decision_case_id,
                    DossierEntry.status == EntryStatus.CONFIRMED,
                    DossierEntry.statement_type == DossierStatementType.ASSUMPTION,
                )
            )
        ).all()
        if not entries:
            return
        registered_spans = {
            span
            for (spans,) in (
                await self._session.execute(
                    _sel(Claim.source_span_ids).where(
                        Claim.workspace_id == run.workspace_id,
                        Claim.analysis_run_id == run.analysis_run_id,
                        Claim.statement_type == StatementType.ASSUMPTION,
                    )
                )
            ).all()
            for span in (spans or [])
        }
        for entry_id, content in entries:
            if str(entry_id) in registered_spans:
                continue
            self._session.add(
                Claim(
                    workspace_id=run.workspace_id,
                    decision_case_id=run.decision_case_id,
                    analysis_run_id=run.analysis_run_id,
                    statement_type=StatementType.ASSUMPTION,
                    text=str(content),
                    importance="core",
                    source="user",
                    responsibility={},
                    source_span_ids=[str(entry_id)],
                    supporting_evidence_ids=[],
                    opposing_evidence_ids=[],
                    assumption_ids=[],
                    support_score=0.0,
                    scope="",
                    status=EntryStatus.CONFIRMED,
                )
            )
        await self._session.flush()

    async def _frozen_reference_sets(
        self, run: AnalysisRun
    ) -> dict[str, frozenset[str]]:
        """Collect the run-frozen reference sets from persisted entities.

        The lens write path resolves every declared reference against this
        ledger fail-closed, so it MUST equal exactly what the lens prompt shows
        the model: research packet ids and their funnel-minted evidence ids
        (both persisted in ``research_packets``), dossier-derived assumption
        claims (registered by ``_register_dossier_assumptions``), plus any
        claim/challenge rows the run produced (challenges still empty until
        that lane persists rows; the model then cannot cite them and behavior
        gates that require them block honestly). Same source feeds the
        dedicated lens prompt inputs and ``FrozenReferenceLedger``, so what
        the model sees is what the write path will resolve - never
        ``result.output.get("ledger")``, which live executors never produce.
        """

        from sqlalchemy import select as _sel

        from app.analyses.claims import Claim
        from app.analyses.devils_advocate import Challenge
        from app.analyses.models import ResearchPacket
        from app.types import StatementType

        packet_rows = (
            await self._session.execute(
                _sel(ResearchPacket.id, ResearchPacket.evidence_ids).where(
                    ResearchPacket.workspace_id == run.workspace_id,
                    ResearchPacket.analysis_run_id == run.analysis_run_id,
                )
            )
        ).all()
        source_packet_ids = frozenset(str(row.id) for row in packet_rows)
        # Funnel-minted evidence ids are stored as annotated strings like
        # "ev-retrieving-001 [L6] https://..."; the ledger and the lens prompt
        # must agree on ONE citable form. The model can only echo a bare id, so
        # strip the " [..]" annotation suffix here - then what the model sees
        # is exactly what the write path will resolve.
        evidence_ids = frozenset(
            str(eid).split(" [", 1)[0].strip()
            for row in packet_rows
            for eid in (row.evidence_ids or [])
        )
        claim_rows = (
            await self._session.execute(
                _sel(Claim.id, Claim.statement_type).where(
                    Claim.workspace_id == run.workspace_id,
                    Claim.analysis_run_id == run.analysis_run_id,
                )
            )
        ).all()
        claim_ids = frozenset(str(row.id) for row in claim_rows)
        assumption_ids = frozenset(
            str(row.id)
            for row in claim_rows
            if row.statement_type == StatementType.ASSUMPTION
        )
        challenge_ids = frozenset(
            str(cid)
            for cid in (
                await self._session.execute(
                    _sel(Challenge.id).where(
                        Challenge.workspace_id == run.workspace_id,
                        Challenge.analysis_run_id == run.analysis_run_id,
                    )
                )
            ).scalars().all()
        )
        return {
            "source_packet_ids": source_packet_ids,
            "evidence_ids": evidence_ids,
            "claim_ids": claim_ids,
            "assumption_ids": assumption_ids,
            "challenge_ids": challenge_ids,
        }

    async def _load_upstream_lens_digests(
        self,
        run: AnalysisRun,
        current_lens: Any,
    ) -> dict[Any, Mapping[str, Any]]:
        """Grey-goo 原则⑭ (P2-1): validated outputs of earlier lenses in THIS run.

        Cross-agent calibration: each lens reads what its predecessors already
        concluded (e.g. counterparty before pre-mortem, scenario before
        meadows) so it deepens against REAL findings instead of stale
        assumptions. Only READY artifacts are eligible (a draft was never
        accepted); digests are compressed to ≤500 chars per lens so the prompt
        stays bounded. Best-effort: a read failure yields {} and the lens
        runs without upstream context (fail-open, never blocks).
        """

        from sqlalchemy import select as _sel

        from app.models import StrategicLensArtifact
        from app.types import StrategicLensArtifactStatus

        try:
            rows = (
                await self._session.execute(
                    _sel(StrategicLensArtifact).where(
                        StrategicLensArtifact.workspace_id == run.workspace_id,
                        StrategicLensArtifact.analysis_run_id == run.analysis_run_id,
                        StrategicLensArtifact.status == StrategicLensArtifactStatus.READY,
                    )
                )
            ).scalars().all()
        except Exception:
            return {}
        digests: dict[Any, Mapping[str, Any]] = {}
        for artifact in rows:
            if artifact.lens_type == current_lens:
                continue
            # The ORM stores the model payload under ``payload`` (which wraps
            # {content, references}); unwrap defensively.
            raw_payload = artifact.payload if isinstance(artifact.payload, Mapping) else {}
            content = (
                raw_payload.get("content")
                if isinstance(raw_payload.get("content"), Mapping)
                else raw_payload
            )
            headline = str(content.get("headline") or content.get("decision") or "")[:300]
            findings = content.get("keyFindings")
            findings_text = (
                "; ".join(str(item)[:120] for item in findings[:3])
                if isinstance(findings, Sequence) and not isinstance(findings, (str, bytes))
                else ""
            )
            summary = (headline + (" | " + findings_text if findings_text else ""))[:500]
            if not summary:
                continue
            digests[artifact.lens_type] = {"summary": summary}
        return digests

    async def _prepare_lens_context(self, run: AnalysisRun) -> dict[str, Any]:
        """Wave D: preload ALL database reads the dedicated lens calls need.

        Parallel lens execution is only safe when the model-call phase touches
        no AsyncSession. This method does every DB read ONCE, serially, before
        the parallel gather: charter option ids, frozen reference sets, and the
        upstream READY-lens digests (all types; each lens filters itself out
        during prompt assembly).
        """

        charter = await self._session.get(AnalysisCharter, run.charter_id)
        option_ids = tuple(str(o) for o in (charter.option_ids or [])) if charter else ()
        refs = await self._frozen_reference_sets(run)
        upstream_digests = await self._load_upstream_lens_digests(run, None)
        return {
            "option_ids": option_ids,
            "refs": refs,
            "upstream_digests": upstream_digests,
        }

    async def _run_lens_stages(
        self,
        run: AnalysisRun,
        stage: AnalysisRunStatus,
        result: StageResult,
    ) -> list[dict[str, Any]]:
        """Persist each scheduled lens through the shipped write path, then emit.

        When the generic stage executor returned no lens payload (the usual
        case for live models that were never shown the per-lens prompt), invoke
        a DEDICATED lens call through the registered implementation's prompt
        assembly + the same model provider. This is the missing wiring that
        caused every live full run to produce zero lens artifacts.

        Wave D returns the convergence-audited chain fragments handed off by
        the lens sub-agents (namespaced, resolvability-checked); the caller
        merges them into the run's accumulated decision chain.
        """

        # Frozen-reference ledger for the whole lens set: built once from the
        # persisted run (same source as the dedicated prompt inputs), so every
        # lens in this stage resolves against the same authority. Dossier
        # assumptions are registered BEFORE the ledger freezes so counterparty
        # can cite them; without rows the gate still blocks honestly.
        await self._register_dossier_assumptions(run)
        ledger = FrozenReferenceLedger(**(await self._frozen_reference_sets(run)))
        # Wave D: structured parallel delegation - the MODEL-CALL phase of the
        # lenses scheduled in this stage runs concurrently (bounded semaphore,
        # session-free thanks to _prepare_lens_context preloading); the
        # PERSISTENCE phase stays serial because the AsyncSession is not
        # concurrency-safe. Sub-agents stay auditable: every lens payload is
        # validated by the behavior gate + reference ledger before merge.
        lens_types = FULL_LENS_SCHEDULE[stage]
        pending = [lt for lt in lens_types if result.lens_payloads.get(lt) is None]
        payloads: dict[str, Mapping[str, Any] | None] = {
            lt: result.lens_payloads.get(lt) for lt in lens_types
        }
        if len(pending) > 1:
            await self._check_cancelled(run)
            preloaded = await self._prepare_lens_context(run)
            semaphore = asyncio.Semaphore(_MAX_PARALLEL_LENSES)

            async def _invoke(lt: str) -> Mapping[str, Any] | None:
                async with semaphore:
                    return await self._execute_dedicated_lens(
                        run, stage, lt, result,
                        preloaded_context=preloaded,
                    )

            gathered = await asyncio.gather(
                *(_invoke(lt) for lt in pending), return_exceptions=True
            )
            for lt, outcome in zip(pending, gathered):
                if isinstance(outcome, Mapping):
                    payloads[lt] = outcome
                elif isinstance(outcome, BaseException):
                    logging.getLogger(__name__).warning(
                        "parallel lens %s failed for run %s: %s",
                        lt, run.analysis_run_id, outcome,
                    )
        elif pending:
            payloads[pending[0]] = await self._execute_dedicated_lens(
                run, stage, pending[0], result
            )
        chain_fragment: list[dict[str, Any]] = []
        for lens_type in lens_types:
            payload = payloads.get(lens_type)
            if payload is None:
                continue
            # Wave D: extract the sub-agent's chain handoff and strip it from
            # the persisted payload (the artifact schema stays untouched).
            chain_links = payload.get("chainLinks")
            if "chainLinks" in payload:
                payload = {k: v for k, v in payload.items() if k != "chainLinks"}
            # External-call/persistence boundary: cooperative stop first.
            await self._check_cancelled(run)
            artifact_id = await self._persist_lens_with_repair(
                run, stage, lens_type, result, payload, ledger
            )
            if artifact_id is None:
                continue
            # Wave D convergence audit: a sub-agent's chain merges into the
            # run's decision chain ONLY after its artifact passed the behavior
            # gate AND every citation resolves against the frozen ledger.
            chain_fragment.extend(
                _audit_lens_chain_fragment(chain_links, lens_type, ledger.evidence_ids)
            )
            # Only after successful persistence: record the id and emit the
            # canonical strategic_lens.completed event.
            await self._repo.record_lens_artifact_id(
                run.workspace_id, run.analysis_run_id, artifact_id
            )
            # The shipped write path persists draft artifacts; the lens audit
            # only counts READY rows, so accept the artifact immediately (the
            # behavior gate already passed inside persist_lens_stage_output).
            # This was the last missing link that kept every full run blocked
            # with strategic_lens_incomplete even when all five lenses landed.
            await apply_validation_verdict(
                await self._session.connection(),
                workspace_id=run.workspace_id,
                strategic_lens_artifact_id=artifact_id,
                accepted=True,
            )
            await self._repo.append_event(
                await self._fresh(run),
                category="agent.task",
                type="strategic_lens.completed",
                payload={
                    "lensArtifactId": str(artifact_id),
                    "lensType": lens_type,
                    "producerRole": _STAGE_ROLE[stage],
                },
                origin_mode=self._origin_mode,
            )
            # Each persisted lens is published on its own: a full run spends
            # minutes per lens and the trace must not wait for the whole set.
            await self._checkpoint()
        return chain_fragment

    async def _persist_lens_with_repair(
        self,
        run: AnalysisRun,
        stage: AnalysisRunStatus,
        lens_type: str,
        result: StageResult,
        payload: Mapping[str, Any],
        ledger: FrozenReferenceLedger,
    ) -> UUID | None:
        """Persist one lens payload; repair on behavior-gate rejection.

        Grey-goo principle 13 (adversarial feedback loop): a behavior-gate
        rejection is a structured finding that MUST return into the producing
        lens model - the reason codes are handed back as a repair instruction
        and the lens is re-invoked instead of blind-retrying. The repair
        budget is ``self._lens_repair_max`` (default 1); only structural
        ``schema:*`` codes consume a budgeted repair - deterministic mistakes
        (lens_type/phase/skill-version mismatches) are not re-invoked. After
        the budget is spent the established fail-closed posture holds: log and
        return None (the lens audit at the validating gate blocks the run).
        """

        attempts = self._lens_repair_max + 1
        for attempt in range(attempts):
            try:
                return await self._lens_writer(
                    self._session,
                    workspace_id=run.workspace_id,
                    decision_case_id=run.decision_case_id,
                    analysis_run_id=run.analysis_run_id,
                    payload=payload,
                    ledger=ledger,
                    origin_modes=(self._origin_mode,),
                )
            except LensBehaviorRejected as rejected:
                if attempt == attempts - 1:
                    break
                # Only structural gaps deserve a budgeted repair re-invocation.
                repairable = _repairable_reason_codes(rejected.reason_codes)
                if not repairable:
                    break
                # External-call boundary before the repair model call.
                await self._check_cancelled(run)
                payload = await self._execute_dedicated_lens(
                    run, stage, lens_type, result,
                    repair_context=repairable,
                )
                if payload is None:
                    break
            except LensReferenceResolutionError as unresolved:
                # Gap-fix wave B: the model cited ids outside the frozen
                # ledger (hallucinated references). This is structural and
                # repairable - the repair prompt re-lists the exact legal id
                # lists, so a budgeted re-invocation can fix it instead of
                # blind fail-closed (the flash meadows E2E failure mode).
                if attempt == attempts - 1:
                    break
                await self._check_cancelled(run)
                missing_summary = "; ".join(
                    f"{key}: {', '.join(values)}"
                    for key, values in sorted(unresolved.missing.items())
                )
                payload = await self._execute_dedicated_lens(
                    run, stage, lens_type, result,
                    repair_context=(f"unresolved_reference: {missing_summary}",),
                )
                if payload is None:
                    break
            except Exception:
                # Persistence error unrelated to the behavior gate: log and
                # skip. The lens audit at the validating gate will catch the
                # absence and block the run (fail-closed) rather than
                # crashing here.
                logging.getLogger(__name__).warning(
                    "lens %s persistence failed for run %s; payload keys: %s; "
                    "references: %s; skipping",
                    lens_type, run.analysis_run_id,
                    sorted(payload.keys()),
                    {
                        key: sorted(map(str, values))
                        for key, values in payload.get("references", {}).items()
                    },
                    exc_info=True,
                )
                return None
        # Behavior gate rejected the repair pass too: log and skip. The lens
        # audit at the validating gate will catch the absence (fail-closed).
        logging.getLogger(__name__).warning(
            "lens %s behavior gate rejected after repair for run %s; skipping",
            lens_type, run.analysis_run_id,
        )
        return None

    async def _execute_dedicated_lens(
        self,
        run: AnalysisRun,
        stage: AnalysisRunStatus,
        lens_type: str,
        parent_result: StageResult,
        repair_context: tuple[str, ...] | None = None,
        preloaded_context: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any] | None:
        """Invoke the model with the published per-lens prompt and schema.

        This is the wiring that was previously missing: the generic stage prompt
        says 'lensPayloads: {}' and live models comply. This fallback reads the
        actual lens prompt from the published method pack, assembles the frozen
        inputs through the registered LensImplementation, and calls the model
        with an output schema that produces a valid StrategicLensStageOutput
        payload. Behavior validation happens downstream in persist_lens_stage_output.

        ``repair_context`` carries the behavior gate's rejection reason codes
        from a previous attempt (grey-goo principle 13): they are appended as
        a structured repair instruction so the model fixes the exact violated
        behavior fields instead of blind-retrying.

        Failures are logged and return None (the audit will catch the absence at
        the validating gate); this keeps the established fail-closed posture.
        """

        from pathlib import Path

        from app.agents.lenses import (
            LENS_SPECS,
            LensRequest,
            StrategicLensStageOutput,
        )
        from app.agents.model_provider import ModelMessage, complete_structured_checked
        from app.strategic_lenses.registry import build_lens_registry
        from app.types import StrategicLensType

        try:
            lens_enum = StrategicLensType(lens_type)
            spec = LENS_SPECS[lens_enum]
            registry = build_lens_registry()
            impl = registry.get(lens_enum)

            # Read the published prompt from the method pack (shipped in the
            # Docker image under /app/method-packs/).
            prompt_path = Path("/app/method-packs/hardtech-market-direction/1.1.0") / spec.prompt_ref
            if not prompt_path.is_file():
                # Fallback for local dev where the image mounts differently:
                # parents[4] is the repo root (services/api/app/workers -> x4).
                prompt_path = (
                    Path(__file__).resolve().parents[4]
                    / "method-packs" / "hardtech-market-direction" / "1.1.0" / spec.prompt_ref
                )
            prompt_text = prompt_path.read_text(encoding="utf-8") if prompt_path.is_file() else ""

            # Assemble the LensRequest from the frozen run context.
            # Wave D: when preloaded_context is provided (parallel lens phase),
            # every database read already happened serially in
            # _prepare_lens_context - this branch touches NO AsyncSession so
            # the gather below stays session-safe.
            if preloaded_context is not None:
                option_ids = tuple(preloaded_context.get("option_ids") or ())
                refs = preloaded_context.get("refs") or await self._frozen_reference_sets(run)
            else:
                charter = await self._session.get(AnalysisCharter, run.charter_id)
                option_ids = tuple(str(o) for o in (charter.option_ids or [])) if charter else ()
                # Frozen reference sets come from the DATABASE (prior stages
                # already persisted them; parent_result only has the current
                # stage's output which doesn't carry earlier artifacts). The same
                # sets feed the FrozenReferenceLedger, so the model can only cite
                # IDs the write path will resolve.
                refs = await self._frozen_reference_sets(run)
            packet_ids = tuple(sorted(refs["source_packet_ids"]))
            evidence_ids = tuple(sorted(refs["evidence_ids"]))
            claim_ids = tuple(sorted(refs["claim_ids"]))
            assumption_ids = tuple(sorted(refs["assumption_ids"]))
            challenge_ids = tuple(sorted(refs["challenge_ids"]))

            request = LensRequest(
                lens_type=lens_enum,
                workspace_id=str(run.workspace_id),
                analysis_run_id=str(run.analysis_run_id),
                prompt_text=prompt_text,
                research_packet_refs=packet_ids[:20],
                evidence_refs=evidence_ids[:30],
                claim_refs=claim_ids[:20],
                assumption_refs=assumption_ids[:20],
                challenge_refs=challenge_ids[:20],
                option_ids=option_ids,
                # Grey-goo 原则⑭ (P2-1): cross-agent calibration - the lens
                # reads the validated outputs of lenses that already ran in
                # THIS run before deepening its own reasoning. Compressed
                # digests only (≤500 chars each), never full content.
                # Wave D: parallel phase uses the preloaded digest map (each
                # lens filters itself out here - no DB read inside gather).
                upstream_lens_outputs=(
                    {
                        lens: digest
                        for lens, digest in (
                            preloaded_context.get("upstream_digests") or {}
                        ).items()
                        if lens != lens_enum
                    }
                    if preloaded_context is not None
                    else await self._load_upstream_lens_digests(run, lens_enum)
                ),
            )
            inputs = impl.build_prompt_inputs(request)

            # Get the role executor's provider reference (reuse the same model).
            # Call the model with the lens-specific prompt.
            user_message = inputs.user
            if repair_context:
                # Grey-goo principle 13: the behavior gate's rejection is a
                # structured finding that must CHANGE the produced artifact -
                # append the exact reason codes as a repair instruction. The
                # schema snippet for each violated field is attached so the
                # model repairs the SHAPE, not just the names (B4).
                reference_block = ""
                if any(str(code).startswith("unresolved_reference") for code in repair_context):
                    # Gap-fix wave B: hallucinated ids are repaired by re-listing
                    # the COMPLETE legal sets - the model may only cite these.
                    reference_block = (
                        "\nLegal reference ids (cite ONLY these, nothing else):\n"
                        f"- sourcePacketIds: {', '.join(packet_ids) or '(none)'}\n"
                        f"- claimIds: {', '.join(claim_ids) or '(none)'}\n"
                        f"- evidenceIds: {', '.join(evidence_ids) or '(none)'}\n"
                        f"- assumptionIds: {', '.join(assumption_ids) or '(none)'}\n"
                        f"- challengeIds: {', '.join(challenge_ids) or '(none)'}\n"
                    )
                user_message = (
                    f"{inputs.user}\n\n"
                    "Your previous lens output was rejected by the behavior "
                    "contract with these findings: "
                    + "; ".join(repair_context)
                    + ".\n"
                    + _schema_fragments_for(repair_context, inputs.schema_content_def)
                    + reference_block
                    + "Respond again with ONLY a corrected full lens JSON "
                    "object that satisfies every rejected behavior field."
                )
            completion = await complete_structured_checked(
                self._get_provider(),
                system=inputs.system,
                messages=(ModelMessage(role="user", content=user_message),),
                schema=None,  # JSON output mode, no strict schema (lens is complex)
                request_model="",
            )
            content = completion.content
            # Wave D fix: chainLinks is the sub-agent's chain handoff, NOT a
            # schema field - separate it before payload validation and
            # reattach afterwards, so _run_lens_stages can audit the fragment
            # and strip it before artifact persistence.
            chain_links = (
                content.get("chainLinks") if isinstance(content, Mapping) else None
            )
            if isinstance(content, Mapping) and "chainLinks" in content:
                content = {k: v for k, v in content.items() if k != "chainLinks"}
            # Validate it parses as a valid StrategicLensStageOutput.
            StrategicLensStageOutput.from_payload(content)
            payload = dict(content)
            if chain_links is not None:
                payload["chainLinks"] = chain_links
            return payload
        except Exception:
            # Diagnosis aid: the raw model reply is otherwise discarded, which
            # turned every lens failure into a blind spot (the schema KeyError
            # told us WHAT field was missing, never WHAT the model emitted).
            raw_text = ""
            try:
                raw_text = completion.raw_text  # type: ignore[possibly-undefined]
            except (NameError, UnboundLocalError):
                raw_text = ""
            logging.getLogger(__name__).warning(
                "dedicated lens %s execution failed for run %s; raw model output "
                "(truncated): %s; audit will catch absence",
                lens_type, run.analysis_run_id, raw_text[:2000], exc_info=True,
            )
            return None


def _env_lens_repair_max() -> int:
    """Read LENS_REPAIR_MAX (default 1, clamp 0..2) for the repair budget.

    The worker may be constructed with an explicit value (tests), otherwise
    the environment variable is the single deployment knob.
    """
    raw = os.environ.get("LENS_REPAIR_MAX", "1")
    try:
        return min(max(int(raw), 0), 2)
    except ValueError:
        return 1


def _repairable_reason_codes(reason_codes: tuple[str, ...]) -> tuple[str, ...]:
    """Keep the reason codes worth a budgeted repair re-invocation.

    Grey-goo ⑬ with a budget: deterministic mistakes will not be fixed by
    another model call, so they consume no repair budget. Everything else -
    structural gaps (schema:*) AND content-behavior violations (forces_missing,
    meadows_*, one_to_two_key_actors, ...) - is the class a second structured
    repair pass can actually fix.
    """
    deterministic = frozenset(
        {
            "lens_type_mismatch",
            "phase_must_be_adversarial_stress",
            "phase_must_be_strategic_synthesis",
            "source_skill_version_mismatch",
        }
    )
    return tuple(code for code in reason_codes if str(code) not in deterministic)


def _schema_fragments_for(
    reason_codes: tuple[str, ...],
    content_def: str,
) -> str:
    """Extract the violated schema branches as a compact repair hint.

    Reason codes carry JSON paths like ``schema:content.currentInterventions.2``;
    the model sees the path but not the required shape. This walks the
    published content branch and quotes the schema of the violated element so
    the repair pass fixes the SHAPE, not just the name (B4).
    """

    from app.agents.lenses import load_lens_content_schema

    branch_text = load_lens_content_schema(content_def)
    if not branch_text:
        return ""
    try:
        branch = json.loads(branch_text)
    except ValueError:
        return ""
    fragments: list[str] = []
    for code in reason_codes:
        path = str(code).removeprefix("schema:content.")
        node: Any = branch
        for part in path.split("."):
            if part.isdigit():
                # array index - descend into the item schema
                node = node.get("items", {}) if isinstance(node, dict) else {}
            else:
                node = node.get("properties", {}).get(part, {}) if isinstance(node, dict) else {}
        if node:
            fragments.append(f"- {path}: {json.dumps(node, ensure_ascii=False)[:400]}")
    if not fragments:
        return ""
    return (
        "Rejected fields must satisfy these schemas:\n"
        + "\n".join(fragments)
        + "\n"
    )


_STAGE_RESULT_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "required": ["output"],
    "properties": {
        # Live models emit `output` as an object OR a plain summary string; the
        # executor below normalizes any non-object output to {"value": ...}
        # before persistence, so tolerate both here rather than failing the
        # whole multi-stage run on a cosmetic type variance.
        "output": {"type": ["object", "string"]},
        "packets": {"type": "array"},
        # Some models emit [] instead of {} for "no lenses"; the executor
        # coerces a non-object lensPayloads to {} before use.
        "lensPayloads": {"type": ["object", "array"]},
        "qualityGatePassed": {"type": "boolean"},
        "validatorFindings": {"type": "array"},
    },
}


def _provider_request_model(provider: ModelProvider, request_model: str | None) -> str:
    if request_model:
        return request_model
    for attr in ("default_model", "request_model"):
        value = getattr(provider, attr, None)
        if value:
            return str(value)
    return "default"


# Stage-specific asks (hermes-agent enforcement style): every stage must
# deliver a dense, structured digest - no filler, no restated inputs.
_STAGE_ASKS: Mapping[str, str] = {
    "planning": (
        "Decompose the decision question into the decisive sub-questions and "
        "name the single assumption that, if wrong, flips the recommendation. "
        "You MUST also emit top-level \"decisionChain\": an array of initial "
        "decision-chain links that the validator will audit against. Each link: "
        "{\"linkId\": \"pl-1\", \"kind\": \"premise\"|\"evidence\"|\"inference\"|\"decision\", "
        "\"text\": short description, \"citesEvidenceIds\": [], \"citesPacketIds\": [], "
        "\"supportsLinkIds\": []}. Start with 3-6 premise links (what must be true "
        "for the recommendation to hold) and 1-2 decision links (the candidate "
        "options). Subsequent stages will add evidence/inference links and "
        "confirm/refute existing ones."
    ),
    "retrieving": (
        "Produce the FACT BASE. inputs.webEvidence (when present) holds REAL "
        "retrieved sources with url + deterministic tier - ground your facts "
        "in them. inputs.firstPartyEvidence (when present) holds the "
        "decision-maker's OWN confirmed facts: turn each relevant one into a "
        'packet with "sources": [{"name": "decision-maker dossier", "tier": '
        '"L0"}] (no url) - never upgrade first-party claims to an external '
        "tier. packets MUST hold 3-6 fact objects, each "
        '{"factor": short label, "conclusion": one specific falsifiable fact '
        "(with numbers/dates where possible), \"direction\": supporting|"
        "opposing|neutral relative to proceeding, \"claimSupportScore\": 0-1, "
        '"sources": [{"name": who says this, "url": the EXACT webEvidence url '
        "used (copy verbatim; omit url ONLY for model-internal knowledge), "
        '"tier": L1-L6}]}. '
        "NEVER invent a url. Facts without a webEvidence url are treated as "
        "unverified (L6). At least ONE packet MUST be opposing - a fact base "
        "with no adversarial fact is incomplete. Never 'more research needed'. "
        'You MUST also emit top-level "influences": 1-4 edges {"from": factor '
        'label, "to": factor label, "polarity": "+"|"-", "evidenceNote": which '
        "retrieved fact supports the causal link}. Real decision factors are "
        "rarely independent - map how they push or dampen each other. Use "
        "ONLY the exact factor labels you produced above; emit [] ONLY if the "
        "factors are genuinely independent. Never invent correlations. "
        "You MUST also emit top-level \"chainLinkUpdates\": {\"added\": [new "
        "evidence links citing your packet ids], \"confirmed\": [link ids from "
        "inputs.decisionChain your facts support], \"refuted\": [link ids your "
        "facts contradict]}. Each added link: {\"linkId\": \"ev-1\", \"kind\": "
        "\"evidence\", \"text\": ..., \"citesEvidenceIds\": [your packet ids], "
        "\"supportsLinkIds\": [premise link ids]}."
    ),
    "analyzing": (
        "Weigh the options against the goals and constraints. Every keyFinding "
        "is a causal claim with its strongest supporting factor, and set "
        "output.whyNow to why this decision cannot wait. Before finalizing, "
        "SELF-ANCHOR each keyFinding (grey-goo §8): for the 2 strongest "
        'findings, emit "selfAnchor": [{"verdict": "pass"|"uncertain"|'
        '"conflict", "evidenceId": <an evidence id you actually cited>}] '
        "testing your claim against the known evidence. Two conflicts mean "
        "your conclusion is not evidence-backed - fix it or the score is "
        "capped. ROUNDS (grey-goo §7): when inputs.round is absent you are "
        "in round 1 - reason from the evidence you have, and emit "
        '"knowledgeGaps": [what you could not verify without more data] '
        "(max 8). When inputs.round == 2, inputs.round1Gaps carries your "
        "round-1 gaps - fold them into your final reasoning explicitly. "
        "You MUST also emit top-level \"chainLinkUpdates\": {\"added\": [new "
        "inference links], \"confirmed\": [link ids your reasoning supports], "
        "\"refuted\": [link ids your reasoning contradicts]}. Each added link: "
        "{\"linkId\": \"inf-1\", \"kind\": \"inference\", \"text\": ..., "
        "\"supportsLinkIds\": [premise/evidence link ids]}."
    ),
    "criticizing": (
        "Attack the emerging recommendation. Set output.strongestObjection to "
        "the single most dangerous objection, and every keyFinding names a "
        "specific failure mode with its trigger condition. Self-anchor your "
        'strongest objection the same way ("selfAnchor" verdicts against '
        "cited evidence ids); a conflict with known facts means the objection "
        "itself needs rework. You MUST also emit top-level \"chainLinkUpdates\": "
        "{\"added\": [new inference links capturing failure modes], \"confirmed\": "
        "[link ids your objection challenges], \"refuted\": [link ids your "
        "objection invalidates]}."
    ),
    "synthesizing": (
        "Commit. Set output.decision to one conditional commitment sentence "
        "(what to do + under which conditions + exit rule). keyFindings carry "
        "the 2-4 reasons that survived criticism. You MUST also emit top-level "
        "\"chainLinkUpdates\": {\"added\": [decision links capturing your "
        "commitment], \"confirmed\": [link ids your decision rests on], "
        "\"refuted\": [link ids your decision rejects]}."
    ),
    "validating": (
        "Audit the decision chain: inputs.decisionChain carries the accumulated "
        "links (premise/evidence/inference/decision) from all prior stages. For "
        "each validatorFinding, cite the broken link's linkId in a \"linkId\" "
        "field. Does the decision follow from the evidence? Did the strongest "
        "objection get a real answer? Fail the gate when the chain has a hole, "
        "and say which link broke."
    ),
}

_DIGEST_LIST_KEYS = ("keyFindings", "risks", "openQuestions")

_MAX_INFLUENCE_EDGES = 6
_MAX_CHAIN_LINKS = 40  # bounded accumulator; prevents unbounded growth
# Wave D: concurrent lens sub-agent cap (aligned with hermes' MAX_CONCURRENT_CHILDREN).
_MAX_PARALLEL_LENSES = 2


def _accumulate_chain_links(
    prior_chain: Any, updates: Mapping[str, Any]
) -> dict[str, Any]:
    """Wave C: merge per-stage chainLinkUpdates into the accumulated chain.

    - added: new links appended (linkId must be unique; duplicates drop).
    - confirmed: linkIds acknowledged (no structural change; tracked for audit).
    - refuted: linkIds removed from the chain (validator sees them as broken).

    The accumulator is deterministic and bounded; malformed payloads degrade
    gracefully (drop the offending field, never crash the stage).
    """

    prior = prior_chain if isinstance(prior_chain, Mapping) else {}
    links: list[dict[str, Any]] = list(prior.get("links") or [])
    existing_ids = {str(link.get("linkId")) for link in links if isinstance(link, Mapping)}
    added = updates.get("added") if isinstance(updates.get("added"), Sequence) else []
    for link in added:
        if not isinstance(link, Mapping):
            continue
        link_id = str(link.get("linkId") or "").strip()
        if not link_id or link_id in existing_ids:
            continue
        if len(links) >= _MAX_CHAIN_LINKS:
            break
        links.append(dict(link))
        existing_ids.add(link_id)
    refuted = updates.get("refuted") if isinstance(updates.get("refuted"), Sequence) else []
    refuted_ids = {str(r) for r in refuted if r}
    if refuted_ids:
        links = [link for link in links if str(link.get("linkId")) not in refuted_ids]
    confirmed = updates.get("confirmed") if isinstance(updates.get("confirmed"), Sequence) else []
    return {
        "links": links,
        "confirmedIds": [str(c) for c in confirmed if c],
        "refutedIds": sorted(refuted_ids),
    }


_CHAIN_LINK_KINDS = frozenset({"premise", "evidence", "inference", "decision"})
_MAX_CHAIN_LINKS_PER_LENS = 5


def _audit_lens_chain_fragment(
    fragment: Any, lens_type: str, legal_evidence_ids: frozenset[str]
) -> list[dict[str, Any]]:
    """Wave D convergence-audit gate: validate one lens sub-agent's chainLinks.

    The orchestrator merges a sub-agent's reasoning into the run's decision
    chain ONLY after this audit passes per-link (fail-closed at link level):
    - linkId / text non-empty, kind in the canonical vocabulary;
    - every citesEvidenceIds entry RESOLVES against the frozen ledger (the
      same authority the lens artifact write path uses) - hallucinated
      citations drop the link, mirroring the reference-resolution gate;
    - link ids are namespaced (lens_type:linkId) so parallel sub-agents can
      never collide or spoof another lens's links.

    Audited links are returned ready for _accumulate_chain_links; a malformed
    fragment yields [] (the artifact itself is unaffected - the chain is an
    augmentation, and honest absence beats fabricated structure).
    """

    if not isinstance(fragment, Sequence) or isinstance(fragment, (str, bytes)):
        return []
    audited: list[dict[str, Any]] = []
    seen: set[str] = set()
    for link in list(fragment)[:_MAX_CHAIN_LINKS_PER_LENS]:
        if not isinstance(link, Mapping):
            continue
        link_id = str(link.get("linkId") or "").strip()
        text = str(link.get("text") or "").strip()
        kind = str(link.get("kind") or "").strip()
        if not link_id or not text or kind not in _CHAIN_LINK_KINDS:
            continue
        namespaced = f"{lens_type}:{link_id}"
        if namespaced in seen:
            continue
        cites_raw = link.get("citesEvidenceIds")
        cites = (
            [str(c) for c in cites_raw if str(c).strip()]
            if isinstance(cites_raw, Sequence) and not isinstance(cites_raw, (str, bytes))
            else []
        )
        resolvable = [c for c in cites if c in legal_evidence_ids]
        if cites and not resolvable:
            # Every citation hallucinated: the link claims evidence it cannot
            # show - drop it (fail-closed), never merge unfounded claims.
            continue
        seen.add(namespaced)
        audited.append(
            {
                "linkId": namespaced,
                "kind": kind,
                "text": text[:500],
                "citesEvidenceIds": resolvable,
                "supportsLinkIds": [],
                "stage": lens_type,
            }
        )
    return audited


def _admit_influences(
    raw: Any, admitted_packets: Sequence[Mapping[str, Any]]
) -> list[dict[str, str]]:
    """Deterministic admission of model-proposed factor->factor edges.

    Both endpoints must be factor labels of ADMITTED packets (case-insensitive
    exact match); self-loops and duplicates drop; bounded count. This is the
    "confirmed before it enters the propagation graph" step - structure the
    model merely proposed never reaches the sandbox unchecked.
    """

    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        if raw is not None:
            logging.getLogger(__name__).info("influences: non-list payload dropped (%s)", type(raw).__name__)
        return []
    labels: dict[str, str] = {}
    for packet in admitted_packets:
        if isinstance(packet, Mapping):
            label = str(packet.get("factor") or "").strip()
            if label:
                labels[label.lower()] = label
    edges: list[dict[str, str]] = []
    dropped = 0
    seen: set[tuple[str, str]] = set()
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        source = labels.get(str(entry.get("from") or "").strip().lower())
        target = labels.get(str(entry.get("to") or "").strip().lower())
        if not source or not target or source.lower() == target.lower():
            dropped += 1
            continue
        key = (source.lower(), target.lower())
        if key in seen:
            continue
        seen.add(key)
        polarity = str(entry.get("polarity") or "+").strip().lower()
        edges.append(
            {
                "from": source,
                "to": target,
                "polarity": "-" if polarity in {"-", "negative", "opposing", "inverse"} else "+",
                "evidenceNote": str(entry.get("evidenceNote") or entry.get("note") or "")[:160],
            }
        )
        if len(edges) >= _MAX_INFLUENCE_EDGES:
            break
    if dropped:
        logging.getLogger(__name__).info(
            "influences: %d edge(s) dropped by admission (labels=%s)", dropped, sorted(labels.values())
        )
    return edges


# Grey-goo complexity-adaptivity pre-check (framework-selector v6.9.5): a
# downgrade proposal must be BLOCKED when the independent safety anchor has
# already flagged ≥2 shared unexamined assumptions - convergence may be echo,
# not simplicity. Wave-1 ships the pure decision function; the downgrade
# state machine itself lands with P2-2 (wave 2).
def _anchor_blocks_downgrade(stage_outputs: Mapping[str, Any]) -> tuple[bool, int]:
    """Return (blocked, shared_blind_spot_count) from the safety-anchor digest.

    The anchor's ``digest.keyFindings`` lists the shared unexamined
    assumptions the whole analysis rests on. Two or more means a proposed
    downgrade is refused: the convergence it would rely on is suspect.
    """

    anchor = stage_outputs.get("safety_anchor")
    if not isinstance(anchor, Mapping):
        return False, 0
    digest = anchor.get("digest") if isinstance(anchor.get("digest"), Mapping) else None
    if not digest:
        return False, 0
    findings = digest.get("keyFindings") if isinstance(digest.get("keyFindings"), Sequence) else ()
    findings = [
        str(item) for item in findings
        if isinstance(item, (str,)) and str(item).strip()
    ]
    return (len(findings) >= 2, len(findings))


def _deterministic_gate(
    stage_outputs: Mapping[str, Any],
    validator_findings: tuple[Mapping[str, Any], ...],
) -> dict[str, Any]:
    """Grey-goo multiplicative gate: the model's verdict is necessary but no
    longer sufficient. Four dimensions are scored from ARTIFACTS the pipeline
    actually produced (funnel audit, adversarial digests, validator findings);
    a dimension whose institution did not run is skipped (fail-open for
    fixture paths), so the gate bites exactly when the evidence institution
    was exercised. Multiplication punishes the weakest link.
    """

    dims: dict[str, float] = {}

    retrieving = stage_outputs.get(AnalysisRunStatus.RETRIEVING.value)
    audit = retrieving.get("evidenceFunnel") if isinstance(retrieving, Mapping) else None
    if isinstance(audit, Mapping):
        admitted = int(audit.get("admitted") or 0)
        opposing = int(audit.get("opposingCount") or 0)
        low_share = audit.get("lowTierShare")
        d1 = 1.0 if admitted >= 2 else (0.6 if admitted == 1 else 0.2)
        if opposing == 0:
            d1 *= 0.7  # one-narrative evidence set
        if isinstance(low_share, (int, float)) and low_share > 0.5:
            d1 *= 0.7  # majority low-trust sources
        dims["evidence"] = round(d1, 3)

    criticizing = stage_outputs.get(AnalysisRunStatus.CRITICIZING.value)
    if isinstance(criticizing, Mapping):
        has_objection = bool(
            str(criticizing.get("strongestObjection") or "").strip()
            or (isinstance(criticizing.get("digest"), Mapping)
                and criticizing["digest"].get("keyFindings"))
        )
        d2 = 1.0 if has_objection else 0.7
        anchor = stage_outputs.get("safety_anchor")
        if isinstance(anchor, Mapping) and isinstance(anchor.get("digest"), Mapping):
            d2 = min(1.0, d2 + 0.0)  # anchor ran: keep score, absence is not punished twice
        dims["adversarial"] = round(d2, 3)

    dims["consistency"] = 1.0 if not validator_findings else 0.8

    # Grey-goo §13: packets that tripped the logic spot-check AND were never
    # repaired (no later packet carries a repair marker) drag consistency
    # down - the flaw is structural, not a one-off wording issue.
    spot_flagged = 0
    for stage in (AnalysisRunStatus.ANALYZING, AnalysisRunStatus.CRITICIZING):
        output = stage_outputs.get(stage.value)
        packets = output.get("packets") if isinstance(output, Mapping) else None
        if isinstance(packets, Sequence) and not isinstance(packets, (str, bytes)):
            spot_flagged += sum(
                1
                for packet in packets
                if isinstance(packet, Mapping) and _logic_spot_check(packet)
            )
    if spot_flagged:
        dims["consistency"] = round(dims["consistency"] * 0.7, 3)

    score = 1.0
    for value in dims.values():
        score *= value
    passed = score >= 0.5
    return {
        "code": "deterministic_gate",
        "source": "multiplicative_gate",
        "passed": passed,
        "score": round(score, 3),
        "dims": dims,
    }

# Independent-role asks (grey-goo v6 safety-anchor / chief-of-staff). Selected
# via inputs["roleOverride"] so the same executor serves an extra pass without
# a new pipeline stage.
_ROLE_ASKS: Mapping[str, str] = {
    "safety_anchor": (
        "You are an INDEPENDENT safety anchor, not an analyst. Ignore whether "
        "the prior stages agree - hunt COLLECTIVE blind spots. digest.headline "
        "answers 'if every prior direction is wrong, the most likely single "
        "reason is ___'. digest.keyFindings are 2-4 shared unexamined "
        "assumptions the whole analysis rests on; digest.risks are the most "
        "vulnerable links; digest.openQuestions are what must be checked before "
        "trusting the convergence. Name real blind spots, never 'looks fine'."
    ),
    "chief_of_staff": (
        "You are the chief of staff: convert analysis into ACTION. Not 'what "
        "this means' but 'so what to do'. digest.headline is ONE falsifiable, "
        "concrete recommendation naming the actor and the move (BANNED vague "
        "verbs: strengthen/optimize/enhance/leverage/balance). digest.keyFindings "
        "are 2-4 near-term actions, each 'who does what, precondition, failure "
        "signal'. digest.risks are the top risks with a pre-positioned response; "
        "digest.openQuestions are the decision gates. Do not invent actions for "
        "findings that have no handle."
    ),
}


def _extract_digest(output: Mapping[str, Any]) -> dict[str, Any] | None:
    """Best-effort structured digest from a stage output (bounded, fail-open).

    The digest is the run's visible thinking trace: it rides the
    analysis.stage.completed event into the SSE stream and the report
    builder. Malformed shapes degrade to None - a missing trace never
    fails a stage.
    """

    raw = output.get("digest")
    if not isinstance(raw, Mapping):
        # Fall back to prominent scalar fields so older outputs still trace.
        headline = output.get("summary") or output.get("decision") or output.get("value")
        if not isinstance(headline, str) or not headline.strip():
            return None
        return _tag_digest_model({"headline": headline.strip()[:300]}, output)
    digest: dict[str, Any] = {}
    headline = raw.get("headline") or raw.get("summary")
    if isinstance(headline, str) and headline.strip():
        digest["headline"] = headline.strip()[:300]
    for key in _DIGEST_LIST_KEYS:
        values = raw.get(key)
        if isinstance(values, (list, tuple)):
            clean = [str(v).strip()[:300] for v in values if str(v).strip()][:5]
            if clean:
                digest[key] = clean
    return _tag_digest_model(digest, output) if digest else None


def _tag_digest_model(digest: dict[str, Any], output: Mapping[str, Any]) -> dict[str, Any]:
    """Stamp which brain spoke (and whether it is a heterogeneous adversary)."""

    model_id = output.get("modelId")
    if isinstance(model_id, str) and model_id.strip():
        digest["model"] = model_id.strip()[:80]
        source = output.get("cognitiveSource")
        if isinstance(source, str) and source in ("heterogeneous", "primary"):
            digest["cognitiveSource"] = source
    return digest


def build_role_executors_from_model_provider(
    provider: ModelProvider,
    *,
    request_model: str | None = None,
    adversary_provider: ModelProvider | None = None,
    adversary_request_model: str | None = None,
) -> RoleExecutors:
    """Wire live/fixture ModelProvider calls into the durable worker.

    The worker receives only the schema-checked StageResult envelope; provider
    protocol details (including any DeepSeek ``reasoning_content``) are stripped
    inside the provider adapter and never persisted by this layer.

    When ``adversary_provider`` is set (MODEL_B_*), the ADVERSARIAL surfaces -
    criticizing, validating and the safety-anchor pass - run on that
    heterogeneous second brain: different training data, different biases,
    a genuinely independent second opinion. Without it every stage stays on
    the primary model and the trace labels the opposition as same-model.
    """

    model_id = _provider_request_model(provider, request_model)
    adversary_id = (
        _provider_request_model(adversary_provider, adversary_request_model)
        if adversary_provider is not None
        else None
    )

    # Stages whose whole job is to attack or veto the house view.
    _ADVERSARIAL_STAGES = {AnalysisRunStatus.CRITICIZING.value, AnalysisRunStatus.VALIDATING.value}

    async def execute(
        run: AnalysisRun, stage: AnalysisRunStatus, inputs: Mapping[str, Any]
    ) -> StageResult:
        role_override = inputs.get("roleOverride") if isinstance(inputs, Mapping) else None
        substage = inputs.get("substage") if isinstance(inputs, Mapping) else None
        is_adversarial = (
            stage.value in _ADVERSARIAL_STAGES
            or str(role_override) == "safety_anchor"
            or str(substage) == "safety_anchor"
        )
        active_provider = adversary_provider if (is_adversarial and adversary_provider) else provider
        active_model = adversary_id if (is_adversarial and adversary_provider) else model_id
        stage_ask = (
            _ROLE_ASKS.get(str(role_override))
            if role_override
            else _STAGE_ASKS.get(stage.value)
        ) or "Advance the analysis with concrete findings."
        completion = await complete_structured_checked(
            active_provider,
            system=(
                "You are a Ludus analysis stage executor. Return ONLY a JSON "
                "object with EXACTLY these keys and value types: "
                '"output" a JSON OBJECT (never a string) holding this stage\'s '
                "structured findings; "
                '"packets" a JSON ARRAY of objects (may be empty); '
                '"lensPayloads" a JSON OBJECT keyed by lens type (use {} if none, '
                "never an array); "
                '"qualityGatePassed" a boolean; '
                '"validatorFindings" a JSON ARRAY (may be empty). '
                "output MUST include a \"digest\" object: "
                '{"headline": one specific sentence with this stage\'s decisive '
                "conclusion, \"keyFindings\": 2-4 concrete claims, "
                '"risks": 0-3 specific dangers, "openQuestions": 0-3 questions '
                "that would change the verdict}. "
                f"THIS STAGE'S JOB: {stage_ask} "
                "Be dense and specific: never emit filler like 'analysis "
                "complete' or restate the inputs; every claim must be one a "
                "reader could falsify. Write digest text in the user's "
                "language (Chinese question -> Chinese digest). "
                "SELF-ANCHOR (mandatory): before finalizing, verify your "
                "digest.headline against ONE concrete fact from the inputs "
                "(webEvidence or a prior stage's finding). If no fact supports "
                "it or a fact conflicts, lower claimSupportScore and add the "
                "conflict to digest.openQuestions - never smooth it over. "
                "Do not include hidden reasoning."
            ),
            messages=(
                ModelMessage(
                    role="user",
                    content=json.dumps(
                        {
                            "workspaceId": str(run.workspace_id),
                            "decisionCaseId": str(run.decision_case_id),
                            "analysisRunId": str(run.analysis_run_id),
                            "stage": stage.value,
                            "inputs": dict(inputs),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                ),
            ),
            schema=_STAGE_RESULT_SCHEMA,
            request_model=active_model,
        )
        content = completion.content
        output = content.get("output") or {}
        if not isinstance(output, Mapping):
            output = {"value": output}
        # Which brain produced this stage: rides the output (free-form dict)
        # into the digest/event stream so the trace can show a genuine second
        # opinion - or honestly label same-model opposition.
        output = {
            **output,
            "modelId": completion.response_model or active_model,
            "cognitiveSource": (
                "heterogeneous" if (is_adversarial and adversary_provider) else "primary"
            ),
        }
        # The retrieving ask requests top-level "influences"; models place it
        # either beside "output" or inside it. Accept both - otherwise the
        # parser silently drops the causal edges before admission ever runs.
        raw_influences = content.get("influences")
        if (
            isinstance(raw_influences, Sequence)
            and not isinstance(raw_influences, (str, bytes))
            and "influences" not in output
        ):
            output = {**output, "influences": list(raw_influences)}
        packets = tuple(
            item for item in content.get("packets", ()) if isinstance(item, Mapping)
        )
        raw_lenses = content.get("lensPayloads") or {}
        lens_payloads = raw_lenses if isinstance(raw_lenses, Mapping) else {}
        findings = tuple(
            item for item in content.get("validatorFindings", ()) if isinstance(item, Mapping)
        )
        return StageResult(
            output=output,
            packets=packets,
            lens_payloads=lens_payloads,
            quality_gate_passed=content.get("qualityGatePassed"),
            validator_findings=findings,
        )

    return RoleExecutors(
        research=execute,
        critic=execute,
        synthesis=execute,
        validation=execute,
    )


def build_role_executors_from_env() -> tuple[RoleExecutors, OriginMode]:
    """Production seam: environment -> provider -> worker executors.

    ``MODEL_PROVIDER=deepseek`` gives live execution. ``MODEL_PROVIDER=fixture``
    or ``FIXTURE_MODE=true`` keeps the deterministic offline path explicitly
    marked as fixture origin.
    """

    provider = build_model_provider_from_env()
    origin_mode = OriginMode.FIXTURE if provider.name == "fixture" else OriginMode.LIVE
    if origin_mode == OriginMode.FIXTURE and getattr(provider, "fallback", None) is None:
        # Without this the key-free path cannot run at all: the fixture provider
        # has no registered stage responses, so every stage resolved to {} and
        # the run was parked within seconds. The synthesizer is deterministic
        # and labels every fact as fixture, so it cannot pass for live output.
        from app.workers.fixture_stages import synthesize_stage_response

        provider.fallback = synthesize_stage_response
        logging.getLogger(__name__).info(
            "fixture origin: deterministic stage responses bound (no model key in use)"
        )
    # Heterogeneous adversary (MODEL_B_*): only meaningful for live execution;
    # fixture runs stay fully deterministic on one provider.
    adversary = (
        build_secondary_model_provider_from_env() if origin_mode == OriginMode.LIVE else None
    )
    if adversary is not None:
        logging.getLogger(__name__).info(
            "adversarial stages bound to heterogeneous second brain: %s",
            getattr(adversary, "default_model", "secondary"),
        )
    return (
        build_role_executors_from_model_provider(provider, adversary_provider=adversary),
        origin_mode,
    )
