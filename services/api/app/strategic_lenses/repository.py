"""StrategicLensArtifact write path (Ways Persistence lane).

Wires the CCR-20260724-Ways-01 canonical model to the lens runtime without
redefining any schema or enum:

* tenancy first: every operation resolves the frozen ``AnalysisRun`` through
  the (workspace, case, run) triple and answers uniformly with "not found"
  when anything is foreign or missing;
* the untrusted model payload passes the seam guard (server-owned identity
  fields rejected) and the assembled registry's behavior gate before any row
  is written - behavior failures are never persisted as artifacts;
* claim/evidence/assumption references must resolve inside the worker-supplied
  frozen ledgers (fail-closed until the evidence owner lane lands DB ledgers);
* identity, method snapshot, producer role, schema version, origin modes,
  content hash and timestamps are injected server-side from the run row;
* writes are append-only: the only mutation ever allowed is the Validation
  verdict transition ``draft -> ready`` (with acceptance witness) or
  ``draft -> rejected``; content columns are never updated.

HTTP-level capability enforcement (``contribute``) belongs to the router lane;
this module is invoked by the server-side worker with an already-authorized,
frozen run context.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final
from uuid import UUID, uuid4

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.agents.lenses import (
    LENS_OUTPUT_SCHEMA_ID,
    LENS_SPECS,
    LensRegistry,
    StrategicLensStageOutput,
)
from app.models import AnalysisRun, StrategicLensArtifact
from app.strategic_lenses.registry import build_lens_registry
from app.types import (
    AnalysisRunStatus,
    LensProducerRole,
    OriginMode,
    StrategicLensArtifactStatus,
    StrategicLensType,
)

# The canonical column stores the short schema semver; the full URN is
# reconstructable from the method id/version pins.
_LENS_SCHEMA_VERSION: Final[str] = LENS_OUTPUT_SCHEMA_ID.rsplit(":", 1)[-1]

# Run stages during which a worker may persist lens stage outputs. Terminal and
# paused states never accept new artifacts.
_WRITABLE_RUN_STATUSES: Final[frozenset[AnalysisRunStatus]] = frozenset(
    {
        AnalysisRunStatus.PLANNING,
        AnalysisRunStatus.RETRIEVING,
        AnalysisRunStatus.ANALYZING,
        AnalysisRunStatus.CRITICIZING,
        AnalysisRunStatus.SYNTHESIZING,
        AnalysisRunStatus.VALIDATING,
    }
)

# Manifest owner_worker -> canonical producer role projection.
_PRODUCER_ROLE_BY_WORKER: Final[dict[str, LensProducerRole]] = {
    "research": LensProducerRole.RESEARCH,
    "critic": LensProducerRole.CRITIC,
    "synthesis": LensProducerRole.SYNTHESIS,
}

# Partial unique index guarding "at most one ready artifact per run+lens"
# (migration d7e2a91c5b48). Violations are mapped to LensArtifactConflict.
_READY_SLOT_CONSTRAINT: Final[str] = "uq_strategic_lens_artifacts_ready_per_run_lens"


class LensPersistenceError(RuntimeError):
    """Base class for lens write-path failures."""

    code: str = "lens_persistence_error"


class LensRunNotFound(LensPersistenceError):
    """Uniform not-found: missing run, foreign workspace or mismatched case."""

    code = "not_found"


class LensRunNotWritable(LensPersistenceError):
    """The run is not in an executing stage that accepts stage outputs."""

    code = "run_not_writable"


class LensReferenceResolutionError(LensPersistenceError):
    """Stage-output references do not resolve inside the frozen ledgers."""

    code = "reference_unresolved"

    def __init__(self, missing: Mapping[str, Sequence[str]]) -> None:
        detail = {key: sorted(values) for key, values in missing.items() if values}
        super().__init__(f"unresolved frozen references: {detail}")
        self.missing = detail


class LensBehaviorRejected(LensPersistenceError):
    """Behavior gate failed; the output is returned to its owner worker."""

    code = "lens_behavior_rejected"

    def __init__(self, lens_type: StrategicLensType, reason_codes: tuple[str, ...]) -> None:
        super().__init__(f"{lens_type.value} behavior gate rejected: {reason_codes}")
        self.lens_type = lens_type
        self.reason_codes = reason_codes


class LensArtifactConflict(LensPersistenceError):
    """A ready artifact already exists for this run+lens with different content."""

    code = "artifact_conflict"


class LensArtifactImmutable(LensPersistenceError):
    """Only draft artifacts may receive a Validation verdict; content never mutates."""

    code = "artifact_immutable"


@dataclass(frozen=True, slots=True)
class FrozenReferenceLedger:
    """Run-frozen reference sets supplied by the harness/worker.

    Until the evidence owner lane persists canonical ledgers, this is the only
    authority the write path resolves against - unknown references fail closed.
    """

    source_packet_ids: frozenset[str] = frozenset()
    claim_ids: frozenset[str] = frozenset()
    evidence_ids: frozenset[str] = frozenset()
    assumption_ids: frozenset[str] = frozenset()
    challenge_ids: frozenset[str] = frozenset()

    def missing_references(
        self, references: Mapping[str, Sequence[str]]
    ) -> dict[str, list[str]]:
        known = {
            "sourcePacketIds": self.source_packet_ids,
            "claimIds": self.claim_ids,
            "evidenceIds": self.evidence_ids,
            "assumptionIds": self.assumption_ids,
            "challengeIds": self.challenge_ids,
        }
        missing: dict[str, list[str]] = {}
        for key, ledger in known.items():
            declared = set(references.get(key, ()))
            unresolved = declared - ledger
            if unresolved:
                missing[key] = sorted(unresolved)
        return missing


@dataclass(frozen=True, slots=True)
class PersistedLensArtifact:
    """Write-path result: persisted identity only, never a parallel DTO."""

    strategic_lens_artifact_id: UUID
    lens_type: StrategicLensType
    status: StrategicLensArtifactStatus
    content_hash: str
    created: bool


@dataclass(frozen=True, slots=True)
class _FrozenRunContext:
    workspace_id: UUID
    decision_case_id: UUID
    analysis_run_id: UUID
    charter_id: UUID
    method_id: str
    method_version: str
    method_content_hash: str
    status: AnalysisRunStatus


def canonical_content_hash(payload: Mapping[str, Any]) -> str:
    """Deterministic sha256 over the normalized allowed-field payload."""

    normalized = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return "sha256:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _normalized_payload(stage: StrategicLensStageOutput) -> dict[str, Any]:
    return {
        "lensType": stage.lens_type.value,
        "sourceSkillVersion": stage.source_skill_version,
        "phase": stage.phase,
        "references": {key: list(value) for key, value in stage.references.items()},
        "researchRequests": [dict(item) for item in stage.research_requests],
        "content": dict(stage.content),
    }


def _deduped_origin_modes(origin_modes: Sequence[OriginMode]) -> list[OriginMode]:
    seen: list[OriginMode] = []
    for mode in origin_modes:
        if mode not in seen:
            seen.append(mode)
    return seen


async def _load_frozen_run(
    connection: AsyncConnection,
    *,
    workspace_id: UUID,
    decision_case_id: UUID,
    analysis_run_id: UUID,
) -> _FrozenRunContext:
    row = (
        await connection.execute(
            select(
                AnalysisRun.workspace_id,
                AnalysisRun.decision_case_id,
                AnalysisRun.analysis_run_id,
                AnalysisRun.charter_id,
                AnalysisRun.method_id,
                AnalysisRun.method_version,
                AnalysisRun.method_content_hash,
                AnalysisRun.status,
            ).where(
                AnalysisRun.workspace_id == workspace_id,
                AnalysisRun.decision_case_id == decision_case_id,
                AnalysisRun.analysis_run_id == analysis_run_id,
            )
        )
    ).one_or_none()
    if row is None:
        raise LensRunNotFound("analysis run not found")
    return _FrozenRunContext(
        workspace_id=row.workspace_id,
        decision_case_id=row.decision_case_id,
        analysis_run_id=row.analysis_run_id,
        charter_id=row.charter_id,
        method_id=row.method_id,
        method_version=row.method_version,
        method_content_hash=row.method_content_hash,
        status=AnalysisRunStatus(row.status),
    )


async def persist_lens_stage_output(
    connection: AsyncConnection,
    *,
    workspace_id: UUID,
    decision_case_id: UUID,
    analysis_run_id: UUID,
    payload: Mapping[str, Any],
    ledger: FrozenReferenceLedger,
    origin_modes: Sequence[OriginMode] = (OriginMode.LIVE,),
    registry: LensRegistry | None = None,
) -> PersistedLensArtifact:
    """Validate one untrusted stage output and persist it as a draft artifact.

    Raises seam errors (``ServerOwnedFieldError``/``UnknownLensType``) untouched,
    :class:`LensBehaviorRejected` when the behavior gate fails (nothing is
    written), :class:`LensReferenceResolutionError` for unresolved references,
    and :class:`LensArtifactConflict` when a ready artifact with different
    content already occupies this run+lens slot. Re-submitting identical content
    is idempotent and returns the existing row.
    """

    run = await _load_frozen_run(
        connection,
        workspace_id=workspace_id,
        decision_case_id=decision_case_id,
        analysis_run_id=analysis_run_id,
    )
    if run.status not in _WRITABLE_RUN_STATUSES:
        raise LensRunNotWritable(
            f"run status {run.status.value!r} does not accept lens stage outputs"
        )

    stage = StrategicLensStageOutput.from_payload(payload)

    lens_registry = registry if registry is not None else build_lens_registry()
    report = lens_registry.get(stage.lens_type).validate_behavior(stage)
    if not report.ok:
        raise LensBehaviorRejected(stage.lens_type, report.reason_codes)

    missing = ledger.missing_references(stage.references)
    if missing:
        raise LensReferenceResolutionError(missing)

    normalized = _normalized_payload(stage)
    content_hash = canonical_content_hash(normalized)

    existing_rows = (
        await connection.execute(
            select(
                StrategicLensArtifact.strategic_lens_artifact_id,
                StrategicLensArtifact.status,
                StrategicLensArtifact.content_hash,
            )
            .where(
                StrategicLensArtifact.workspace_id == workspace_id,
                StrategicLensArtifact.analysis_run_id == analysis_run_id,
                StrategicLensArtifact.lens_type == stage.lens_type,
            )
            .order_by(StrategicLensArtifact.created_at.desc())
        )
    ).all()
    for row in existing_rows:
        if row.content_hash == content_hash:
            return PersistedLensArtifact(
                strategic_lens_artifact_id=row.strategic_lens_artifact_id,
                lens_type=stage.lens_type,
                status=StrategicLensArtifactStatus(row.status),
                content_hash=content_hash,
                created=False,
            )
    for row in existing_rows:
        if StrategicLensArtifactStatus(row.status) is StrategicLensArtifactStatus.READY:
            raise LensArtifactConflict(
                f"a ready {stage.lens_type.value} artifact with different content "
                "already exists for this run"
            )

    spec = LENS_SPECS[stage.lens_type]
    artifact_id = uuid4()
    await connection.execute(
        insert(StrategicLensArtifact).values(
            strategic_lens_artifact_id=artifact_id,
            workspace_id=run.workspace_id,
            decision_case_id=run.decision_case_id,
            analysis_run_id=run.analysis_run_id,
            charter_id=run.charter_id,
            lens_type=stage.lens_type,
            producer_role=_PRODUCER_ROLE_BY_WORKER[spec.owner_worker],
            status=StrategicLensArtifactStatus.DRAFT,
            method_id=run.method_id,
            method_version=run.method_version,
            method_content_hash=run.method_content_hash,
            prompt_version=run.method_version,
            schema_version=_LENS_SCHEMA_VERSION,
            origin_modes=_deduped_origin_modes(origin_modes),
            content_hash=content_hash,
            payload=normalized,
            claim_refs=list(stage.references.get("claimIds", ())),
            evidence_refs=list(stage.references.get("evidenceIds", ())),
            assumption_refs=list(stage.references.get("assumptionIds", ())),
        )
    )
    return PersistedLensArtifact(
        strategic_lens_artifact_id=artifact_id,
        lens_type=stage.lens_type,
        status=StrategicLensArtifactStatus.DRAFT,
        content_hash=content_hash,
        created=True,
    )


async def apply_validation_verdict(
    connection: AsyncConnection,
    *,
    workspace_id: UUID,
    strategic_lens_artifact_id: UUID,
    accepted: bool,
    accepted_at: datetime | None = None,
) -> StrategicLensArtifactStatus:
    """Apply the Validation worker's verdict to a draft artifact.

    ``draft -> ready`` records the acceptance witness (DB check enforces it);
    ``draft -> rejected`` keeps the audit row. Any other transition, a foreign
    workspace, or an unknown artifact fails closed. Content is never mutated.

    Concurrency contract (QA-WAYS-PERSIST-001): the guarded UPDATE runs inside
    a savepoint so a losing racer never poisons the caller's transaction; a
    ready-slot partial-unique violation surfaces as :class:`LensArtifactConflict`
    and a zero-row guarded UPDATE re-reads and fails closed - raw database
    errors and silent no-op successes are both forbidden outcomes.
    """

    row = (
        await connection.execute(
            select(
                StrategicLensArtifact.strategic_lens_artifact_id,
                StrategicLensArtifact.status,
            ).where(
                StrategicLensArtifact.workspace_id == workspace_id,
                StrategicLensArtifact.strategic_lens_artifact_id
                == strategic_lens_artifact_id,
            )
        )
    ).one_or_none()
    if row is None:
        raise LensRunNotFound("strategic lens artifact not found")
    if StrategicLensArtifactStatus(row.status) is not StrategicLensArtifactStatus.DRAFT:
        raise LensArtifactImmutable(
            f"artifact status {row.status!r} is terminal and cannot change"
        )

    if accepted:
        new_status = StrategicLensArtifactStatus.READY
        witness = accepted_at if accepted_at is not None else datetime.now(UTC)
    else:
        new_status = StrategicLensArtifactStatus.REJECTED
        witness = None

    savepoint = await connection.begin_nested()
    try:
        result = await connection.execute(
            update(StrategicLensArtifact)
            .where(
                StrategicLensArtifact.workspace_id == workspace_id,
                StrategicLensArtifact.strategic_lens_artifact_id
                == strategic_lens_artifact_id,
                StrategicLensArtifact.status == StrategicLensArtifactStatus.DRAFT,
            )
            .values(status=new_status, validation_accepted_at=witness)
        )
    except IntegrityError as exc:
        await savepoint.rollback()
        if _READY_SLOT_CONSTRAINT in str(exc):
            raise LensArtifactConflict(
                "another artifact already holds the ready slot for this run and lens"
            ) from exc
        raise LensPersistenceError(
            "lens verdict update violated a database invariant"
        ) from exc
    if result.rowcount != 1:
        await savepoint.rollback()
        current = (
            await connection.execute(
                select(StrategicLensArtifact.status).where(
                    StrategicLensArtifact.workspace_id == workspace_id,
                    StrategicLensArtifact.strategic_lens_artifact_id
                    == strategic_lens_artifact_id,
                )
            )
        ).scalar_one_or_none()
        if current is None:
            raise LensRunNotFound("strategic lens artifact not found")
        raise LensArtifactImmutable(
            f"artifact status changed concurrently to {current!r}; verdict not applied"
        )
    await savepoint.commit()
    return new_status
