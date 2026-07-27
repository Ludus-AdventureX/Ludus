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
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

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
                    return

                await self._repo.record_stage_completed(
                    workspace_id,
                    run_id,
                    stage=stage,
                    output=dict(result.output),
                    progress=_PROGRESS_AT_STAGE[stage],
                )
                stage_inputs = {"previousStage": stage.value, **dict(result.output)}
        except CooperativeStop:
            # Canonical cancelled terminal state was already written by the
            # cancel command; keep persisted events/artifacts, publish nothing.
            return

    async def _fresh(self, run: AnalysisRun) -> AnalysisRun:
        refreshed = await self._repo.get_run(run.workspace_id, run.analysis_run_id)
        assert refreshed is not None
        return refreshed

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
                "Example: {\"output\":{\"summary\":\"...\",\"keyFindings\":[]},"
                '"packets":[],"lensPayloads":{},"qualityGatePassed":true,'
                '"validatorFindings":[]}. '
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
