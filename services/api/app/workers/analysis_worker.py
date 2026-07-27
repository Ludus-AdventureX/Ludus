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

import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid5, NAMESPACE_URL

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.model_provider import (
    ModelMessage,
    ModelProvider,
    build_model_provider_from_env,
    complete_structured_checked,
)

# Shipped lens write path: imported (never copied). The default lens writer
# below delegates to these exact callables.
from app.strategic_lenses.repository import (
    apply_validation_verdict,
    persist_lens_stage_output,
)
from app.analyses.models import AnalysisCharter
from app.analyses.quality_gate import audit_full_run_lens_set
from app.analyses.repository import AnalysisRuntimeRepository
from app.models import AnalysisRun
from app.types import AnalysisRunStatus, FormalAnalysisLevel, OriginMode
from app.workers.evidence_funnel import apply_evidence_funnel

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
}


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

    @property
    def repository(self) -> AnalysisRuntimeRepository:
        return self._repo

    async def run_once(self, *, workspace_id: UUID | None = None) -> UUID | None:
        """Claim and fully process one queued run; None when the queue is empty."""

        run = await self._repo.claim_next_queued(workspace_id=workspace_id)
        if run is None:
            return None
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
        # In-process stage output capture for the READY report hook (stage_results
        # on the run persists hashes only, not the output bodies).
        stage_outputs: dict[str, Any] = {}

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

                # External-call boundary check before the main role execution.
                await self._check_cancelled(run)
                result = await executor(run, stage, stage_inputs)
                # Boundary check immediately after the external call returns:
                # a cancellation observed here stops before any new persistence.
                await self._check_cancelled(run)
                if stage == AnalysisRunStatus.RETRIEVING and result.packets:
                    # Information funnel: deterministic TDD checks + L1-L6
                    # grading BEFORE persistence. Survivors carry minted,
                    # human-auditable evidence ids; the audit (discards,
                    # tier mix, warnings) travels with the stage output into
                    # the digest/event stream and the report.
                    funnel = apply_evidence_funnel(result.packets, stage=stage.value)
                    merged_output = dict(result.output)
                    merged_output["evidenceFunnel"] = funnel.audit
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
                    saved = await self._repo.add_research_packet(
                        workspace_id=workspace_id,
                        decision_case_id=run.decision_case_id,
                        analysis_run_id=run_id,
                        role=_STAGE_ROLE[stage],
                        **clean,
                    )
                    await self._repo.append_event(
                        await self._fresh(run),
                        category="agent.task",
                        type="research.packet.completed",
                        payload={
                            "packetId": str(saved.id),
                            "factor": saved.factor,
                            "claimSupportScore": saved.claim_support_score,
                        },
                        origin_mode=self._origin_mode,
                    )

                if is_full and stage in FULL_LENS_SCHEDULE:
                    await self._run_lens_stages(run, stage, result)

                # Grey-goo v6 roles that Ludus previously dropped, re-added as
                # best-effort enrichment calls (no state transition, no gate):
                # an INDEPENDENT safety anchor after criticizing (collective
                # blind spots + if-all-wrong-because), and a chief of staff
                # after synthesizing ("so what to do" - conditional actions).
                if stage == AnalysisRunStatus.CRITICIZING:
                    await self._enrich_role(
                        run, "safety_anchor", self._executors.critic,
                        AnalysisRunStatus.CRITICIZING, stage_inputs, stage_outputs,
                    )
                elif stage == AnalysisRunStatus.SYNTHESIZING:
                    await self._enrich_role(
                        run, "chief_of_staff", self._executors.synthesis,
                        AnalysisRunStatus.SYNTHESIZING, stage_inputs, stage_outputs,
                    )

                if stage == AnalysisRunStatus.VALIDATING:
                    # Validation validates and blocks ONLY: no artifact writes,
                    # no synthesis, no repair of missing artifacts here.
                    passed = bool(result.quality_gate_passed)
                    audit_findings: list[dict[str, Any]] = []
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
                    if passed:
                        # READY report hook: assemble + persist the canonical
                        # report artifact from confirmed inputs. "No qualifying
                        # run, no report" holds: blocked/needs_attention never
                        # reach this line. A report failure must not roll back
                        # the READY state - log and continue (compensable).
                        try:
                            await self._persist_run_report(run, stage_outputs)
                        except Exception:
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
                )
                stage_inputs = {"previousStage": stage.value, **dict(result.output)}
                if charter_context is not None:
                    # The charter must survive stage handoffs - each stage
                    # otherwise loses the confirmed question it is analysing.
                    stage_inputs["charter"] = charter_context
        except CooperativeStop:
            # Canonical cancelled terminal state was already written by the
            # cancel command; keep persisted events/artifacts, publish nothing.
            return

    async def _fresh(self, run: AnalysisRun) -> AnalysisRun:
        refreshed = await self._repo.get_run(run.workspace_id, run.analysis_run_id)
        assert refreshed is not None
        return refreshed

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

    async def _run_lens_stages(
        self,
        run: AnalysisRun,
        stage: AnalysisRunStatus,
        result: StageResult,
    ) -> None:
        """Persist each scheduled lens through the shipped write path, then emit."""

        for lens_type in FULL_LENS_SCHEDULE[stage]:
            payload = result.lens_payloads.get(lens_type)
            if payload is None:
                continue
            # External-call/persistence boundary: cooperative stop first.
            await self._check_cancelled(run)
            artifact_id = await self._lens_writer(
                self._session,
                workspace_id=run.workspace_id,
                decision_case_id=run.decision_case_id,
                analysis_run_id=run.analysis_run_id,
                payload=payload,
                ledger=result.output.get("ledger"),
                origin_modes=(self._origin_mode,),
            )
            # Only after successful persistence: record the id and emit the
            # canonical strategic_lens.completed event.
            await self._repo.record_lens_artifact_id(
                run.workspace_id, run.analysis_run_id, artifact_id
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
        "name the single assumption that, if wrong, flips the recommendation."
    ),
    "retrieving": (
        "Produce the FACT BASE. packets MUST hold 3-6 fact objects, each "
        '{"factor": short label, "conclusion": one specific falsifiable fact '
        "(with numbers/dates where possible), \"direction\": supporting|"
        "opposing|neutral relative to proceeding, \"claimSupportScore\": 0-1, "
        '"sources": [{"name": who says this, "tier": L1-L6}]}. '
        "Tier ladder: L1 primary/official filings, L2 regulator or audited "
        "data, L3 reputable research, L4 quality press, L5 secondary "
        "commentary, L6 unsourced/your own inference. At least ONE packet "
        "MUST be opposing - a fact base with no adversarial fact is "
        "incomplete. Never 'more research needed'."
    ),
    "analyzing": (
        "Weigh the options against the goals and constraints. Every keyFinding "
        "is a causal claim with its strongest supporting factor, and set "
        "output.whyNow to why this decision cannot wait."
    ),
    "criticizing": (
        "Attack the emerging recommendation. Set output.strongestObjection to "
        "the single most dangerous objection, and every keyFinding names a "
        "specific failure mode with its trigger condition."
    ),
    "synthesizing": (
        "Commit. Set output.decision to one conditional commitment sentence "
        "(what to do + under which conditions + exit rule). keyFindings carry "
        "the 2-4 reasons that survived criticism."
    ),
    "validating": (
        "Audit the chain: does the decision follow from the evidence, and did "
        "the strongest objection get a real answer? Fail the gate when the "
        "chain has a hole, and say which link broke in validatorFindings."
    ),
}

_DIGEST_LIST_KEYS = ("keyFindings", "risks", "openQuestions")

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
        return {"headline": headline.strip()[:300]}
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
    return digest or None


def build_role_executors_from_model_provider(
    provider: ModelProvider,
    *,
    request_model: str | None = None,
) -> RoleExecutors:
    """Wire live/fixture ModelProvider calls into the durable worker.

    The worker receives only the schema-checked StageResult envelope; provider
    protocol details (including any DeepSeek ``reasoning_content``) are stripped
    inside the provider adapter and never persisted by this layer.
    """

    model_id = _provider_request_model(provider, request_model)

    async def execute(
        run: AnalysisRun, stage: AnalysisRunStatus, inputs: Mapping[str, Any]
    ) -> StageResult:
        role_override = inputs.get("roleOverride") if isinstance(inputs, Mapping) else None
        stage_ask = (
            _ROLE_ASKS.get(str(role_override))
            if role_override
            else _STAGE_ASKS.get(stage.value)
        ) or "Advance the analysis with concrete findings."
        completion = await complete_structured_checked(
            provider,
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
            request_model=model_id,
        )
        content = completion.content
        output = content.get("output") or {}
        if not isinstance(output, Mapping):
            output = {"value": output}
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
    return build_role_executors_from_model_provider(provider), origin_mode
