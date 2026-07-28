"""Analysis runtime repository (Task 9): durable state machine operations.

All mutations run against the caller's transaction/session:

- every transition locks the run row (``FOR UPDATE``), consults the pure
  state machine, appends the canonical ``analysis_events`` row (per-run
  strictly increasing ``sequence``) and records stage input/output hashes in
  ``stage_results`` — no status ever changes silently;
- queue claims use ``FOR UPDATE SKIP LOCKED`` so concurrent workers never
  double-claim; heartbeats are plain timestamp bumps on the claimed row;
- cancellation writes the canonical terminal state atomically and is
  idempotent; the worker observes it cooperatively at stage and external-call
  boundaries and stops without publishing anything new;
- ``blocked`` (quality-gate terminal) is never reopened by resolution or
  cancel; redo requires a new Run;
- charter confirmation freezes fields; any frozen-field change is classified
  as an amendment and can only lead to a replacement draft + new Run.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalysisRun, IdempotencyRecord
from app.types import AnalysisRunStatus, FormalAnalysisLevel, OriginMode

from .models import (
    ACTIVE_RUN_STATUSES,
    AnalysisCharter,
    AnalysisEvent,
    ResearchPacket,
    RunInterventionClassification,
    RunResolution,
)
from .state_machine import (
    EXECUTING_STAGES,
    RunStateMachine,
    diff_frozen_fields,
    normalize_lens_set,
    validate_charter_transition,
)

DEFAULT_HEARTBEAT_TIMEOUT = timedelta(seconds=120)

# CCR-20260725-ANALYSIS-01 §2.1/§2.2 (consumed read-only from
# codex/ccr-guest-analysis-contracts @ d6675693fd2b7709d9ed4756489e633c49c869ee):
# the resolutions endpoint carries a mandatory Idempotency-Key header; same
# key + same normalized body replays the original success, same key +
# different body answers IDEMPOTENCY_CONFLICT 409. Storage reuses the generic
# idempotency_records table (SIM-02A §4 schema, already migrated — no new
# migration in this fast-fix); 48h retention per that table's contract.
RESOLUTIONS_ROUTE_KEY = "analyses.resolutions"
_IDEMPOTENCY_RETENTION = timedelta(hours=48)


class AnalysisRuntimeError(RuntimeError):
    code: str = "analysis_runtime_error"


class RunNotFound(AnalysisRuntimeError):
    code = "not_found"


class CharterNotFound(AnalysisRuntimeError):
    code = "not_found"


class CharterImmutable(AnalysisRuntimeError):
    code = "CHARTER_IMMUTABLE"


class CharterNotConfirmed(AnalysisRuntimeError):
    code = "CHARTER_NOT_CONFIRMED"


class RunAlreadyActive(AnalysisRuntimeError):
    code = "ANALYSIS_RUN_ALREADY_ACTIVE"

    def __init__(self, existing_analysis_run_id: UUID) -> None:
        super().__init__("another formal run is already active for this case")
        self.existing_analysis_run_id = existing_analysis_run_id


class RunNotResumable(AnalysisRuntimeError):
    code = "ANALYSIS_RUN_NOT_RESUMABLE"


class RunNotCancellable(AnalysisRuntimeError):
    code = "ANALYSIS_RUN_NOT_CANCELLABLE"


class RunAmendmentRequired(AnalysisRuntimeError):
    code = "RUN_AMENDMENT_REQUIRED"

    def __init__(self, changed_frozen_fields: list[str], classification_id: UUID) -> None:
        super().__init__("intervention changes charter frozen fields")
        self.changed_frozen_fields = changed_frozen_fields
        self.classification_id = classification_id


class RunResolutionInvalid(AnalysisRuntimeError):
    code = "RUN_RESOLUTION_INVALID"


class IdempotencyConflict(AnalysisRuntimeError):
    code = "IDEMPOTENCY_CONFLICT"


_RESOLUTION_KINDS = frozenset(
    {"source_conflict", "hard_constraint_confirmation", "provider_recovery"}
)
_EVENT_TYPE_FOR_TERMINAL = {
    AnalysisRunStatus.READY: ("agent.status", "analysis.ready"),
    AnalysisRunStatus.BLOCKED: ("agent.status", "analysis.blocked"),
    AnalysisRunStatus.CANCELLED: ("agent.status", "analysis.cancelled"),
    AnalysisRunStatus.NEEDS_ATTENTION: ("agent.status", "analysis.needs_attention"),
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def stage_io_hash(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalized_request_hash(body: Any) -> str:
    """Canonical hash of a request body for idempotency comparison (§2.2).

    Key-order and whitespace insensitive: two bodies that decode to the same
    JSON document always hash identically.
    """

    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TransitionRecord:
    analysis_run_id: UUID
    from_status: AnalysisRunStatus
    to_status: AnalysisRunStatus
    event_id: UUID
    sequence: int


class AnalysisRuntimeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._machine = RunStateMachine()

    # --- charter lifecycle ----------------------------------------------------

    async def get_charter(self, workspace_id: UUID, charter_id: UUID) -> AnalysisCharter | None:
        return await self._session.scalar(
            select(AnalysisCharter).where(
                AnalysisCharter.workspace_id == workspace_id,
                AnalysisCharter.id == charter_id,
            )
        )

    async def _require_charter(self, workspace_id: UUID, charter_id: UUID) -> AnalysisCharter:
        charter = await self.get_charter(workspace_id, charter_id)
        if charter is None:
            raise CharterNotFound("charter not found")
        return charter

    async def create_charter_draft(self, **values: Any) -> AnalysisCharter:
        """Create a draft charter; the lens set is normalized fail-closed."""

        level = values["analysis_level"]
        level_value = level.value if isinstance(level, FormalAnalysisLevel) else str(level)
        values["required_strategic_lens_types"] = normalize_lens_set(
            level_value, list(values.get("required_strategic_lens_types", []))
        )
        charter = AnalysisCharter(id=values.pop("id", uuid4()), **values)
        self._session.add(charter)
        await self._session.flush()
        return charter

    async def update_draft_charter(
        self, workspace_id: UUID, charter_id: UUID, **changes: Any
    ) -> AnalysisCharter:
        charter = await self._require_charter(workspace_id, charter_id)
        if charter.status != "draft":
            raise CharterImmutable(
                f"charter status {charter.status!r} does not accept edits"
            )
        if "required_strategic_lens_types" in changes or "analysis_level" in changes:
            level = changes.get("analysis_level", charter.analysis_level)
            level_value = (
                level.value if isinstance(level, FormalAnalysisLevel) else str(level)
            )
            changes["required_strategic_lens_types"] = normalize_lens_set(
                level_value,
                list(
                    changes.get(
                        "required_strategic_lens_types",
                        charter.required_strategic_lens_types,
                    )
                ),
            )
        for key, value in changes.items():
            setattr(charter, key, value)
        charter.version = charter.version + 1
        await self._session.flush()
        return charter

    async def submit_charter(self, workspace_id: UUID, charter_id: UUID) -> AnalysisCharter:
        charter = await self._require_charter(workspace_id, charter_id)
        validate_charter_transition(charter.status, "awaiting_confirmation")
        charter.status = "awaiting_confirmation"
        await self._session.flush()
        return charter

    async def confirm_charter(self, workspace_id: UUID, charter_id: UUID) -> AnalysisCharter:
        """Freeze the charter. If it replaces an older confirmed charter, the
        replaced charter is atomically marked superseded and its active run
        cancelled with ``charter_replaced`` (canonical replacement flow)."""

        charter = await self._require_charter(workspace_id, charter_id)
        validate_charter_transition(charter.status, "confirmed")
        # Re-validate the frozen lens-set invariant at the freeze boundary.
        charter.required_strategic_lens_types = normalize_lens_set(
            charter.analysis_level.value
            if isinstance(charter.analysis_level, FormalAnalysisLevel)
            else str(charter.analysis_level),
            list(charter.required_strategic_lens_types),
        )
        charter.status = "confirmed"
        charter.confirmed_at = utc_now()
        await self._session.flush()

        if charter.replaces_charter_id is not None:
            replaced = await self._require_charter(workspace_id, charter.replaces_charter_id)
            if replaced.status == "confirmed":
                validate_charter_transition(replaced.status, "superseded")
                replaced.status = "superseded"
                replaced.superseded_by_charter_id = charter.id
                await self._session.flush()
                await self._cancel_runs_for_replaced_charter(
                    workspace_id, replaced.id, superseding_charter=charter
                )
        return charter

    async def create_replacement_draft(
        self,
        workspace_id: UUID,
        charter_id: UUID,
        *,
        changes: dict[str, Any],
    ) -> AnalysisCharter:
        """Amendment path: clone the confirmed charter into a new draft."""

        original = await self._require_charter(workspace_id, charter_id)
        if original.status != "confirmed":
            raise CharterNotConfirmed(
                "only a confirmed charter can receive a replacement draft"
            )
        clone_fields = {
            "workspace_id": original.workspace_id,
            "decision_subject_id": original.decision_subject_id,
            "decision_case_id": original.decision_case_id,
            "case_version": original.case_version,
            "case_snapshot_hash": original.case_snapshot_hash,
            "analysis_level": original.analysis_level,
            "decision_question": original.decision_question,
            "goals": list(original.goals),
            "constraints": list(original.constraints),
            "option_ids": list(original.option_ids),
            "preference_weights": dict(original.preference_weights),
            "required_strategic_lens_types": list(original.required_strategic_lens_types),
            "dossier_snapshot_version": original.dossier_snapshot_version,
            "dossier_snapshot_hash": original.dossier_snapshot_hash,
            "method_id": original.method_id,
            "method_version": original.method_version,
            "method_content_hash": original.method_content_hash,
            "formal_analysis_allowed": original.formal_analysis_allowed,
            "allowed_connector_ids": list(original.allowed_connector_ids),
            "budget": dict(original.budget),
        }
        clone_fields.update(changes)
        clone_fields["replaces_charter_id"] = original.id
        return await self.create_charter_draft(**clone_fields)

    async def _cancel_runs_for_replaced_charter(
        self,
        workspace_id: UUID,
        replaced_charter_id: UUID,
        *,
        superseding_charter: AnalysisCharter,
    ) -> None:
        runs = (
            await self._session.scalars(
                select(AnalysisRun)
                .where(
                    AnalysisRun.workspace_id == workspace_id,
                    AnalysisRun.charter_id == replaced_charter_id,
                    AnalysisRun.status.in_(list(ACTIVE_RUN_STATUSES)),
                )
                .with_for_update()
            )
        ).all()
        for run in runs:
            await self._apply_transition(
                run,
                AnalysisRunStatus.CANCELLED,
                payload={"reason": "charter_replaced"},
                cancellation_reason="charter_replaced",
            )

    # --- run creation -----------------------------------------------------------

    async def create_queued_run(
        self,
        *,
        workspace_id: UUID,
        charter_id: UUID,
        idempotency_key: str,
        run_manifest_hash: str,
        cynefin_gate_result_id: UUID,
        supersedes_analysis_run_id: UUID | None = None,
    ) -> tuple[AnalysisRun, bool]:
        """Create a queued Run from a confirmed, formal-allowed charter.

        Returns ``(run, created)``. The same idempotency key returns the
        existing run (idempotent replay); a *different* second active run for
        the same case raises :class:`RunAlreadyActive` (backed by the partial
        unique index at the database layer).
        """

        charter = await self._require_charter(workspace_id, charter_id)
        if charter.status != "confirmed" or not charter.formal_analysis_allowed:
            raise CharterNotConfirmed(
                "runs require a confirmed charter with formalAnalysisAllowed"
            )

        replay = await self._session.scalar(
            select(AnalysisRun).where(
                AnalysisRun.workspace_id == workspace_id,
                AnalysisRun.idempotency_key == idempotency_key,
            )
        )
        if replay is not None:
            return replay, False

        active = await self._session.scalar(
            select(AnalysisRun.analysis_run_id).where(
                AnalysisRun.workspace_id == workspace_id,
                AnalysisRun.decision_case_id == charter.decision_case_id,
                AnalysisRun.status.in_(list(ACTIVE_RUN_STATUSES)),
            )
        )
        if active is not None:
            raise RunAlreadyActive(active)

        run = AnalysisRun(
            analysis_run_id=uuid4(),
            workspace_id=workspace_id,
            decision_case_id=charter.decision_case_id,
            charter_id=charter.id,
            charter_version=charter.version,
            run_manifest_id=uuid4(),
            run_manifest_hash=run_manifest_hash,
            cynefin_gate_result_id=cynefin_gate_result_id,
            analysis_level=charter.analysis_level,
            case_version=charter.case_version,
            case_snapshot_hash=charter.case_snapshot_hash,
            dossier_snapshot_version=charter.dossier_snapshot_version,
            dossier_snapshot_hash=charter.dossier_snapshot_hash,
            method_id=charter.method_id or "",
            method_version=charter.method_version or "",
            method_content_hash=charter.method_content_hash or "",
            idempotency_key=idempotency_key,
            supersedes_analysis_run_id=supersedes_analysis_run_id,
        )
        self._session.add(run)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            # Loser of a concurrent race on the partial unique index.
            if "uq_analysis_runs_one_active_per_case" in str(exc):
                raise RunAlreadyActive(uuid4()) from exc
            raise
        return run, True

    # --- events -----------------------------------------------------------------

    async def _next_sequence(self, analysis_run_id: UUID) -> int:
        current = await self._session.scalar(
            select(func.coalesce(func.max(AnalysisEvent.sequence), 0)).where(
                AnalysisEvent.analysis_run_id == analysis_run_id
            )
        )
        return int(current or 0) + 1

    async def append_event(
        self,
        run: AnalysisRun,
        *,
        category: str,
        type: str,
        payload: dict[str, Any],
        origin_mode: OriginMode = OriginMode.FIXTURE,
        source_origin_modes: list[str] | None = None,
    ) -> AnalysisEvent:
        event = AnalysisEvent(
            id=uuid4(),
            workspace_id=run.workspace_id,
            decision_case_id=run.decision_case_id,
            analysis_run_id=run.analysis_run_id,
            sequence=await self._next_sequence(run.analysis_run_id),
            category=category,
            type=type,
            origin_mode=origin_mode,
            source_origin_modes=source_origin_modes or [origin_mode.value],
            payload=payload,
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def list_events_after(
        self, workspace_id: UUID, analysis_run_id: UUID, after_sequence: int = 0
    ) -> list[AnalysisEvent]:
        result = await self._session.scalars(
            select(AnalysisEvent)
            .where(
                AnalysisEvent.workspace_id == workspace_id,
                AnalysisEvent.analysis_run_id == analysis_run_id,
                AnalysisEvent.sequence > after_sequence,
            )
            .order_by(AnalysisEvent.sequence)
        )
        return list(result)

    # --- transitions --------------------------------------------------------------

    async def get_run(self, workspace_id: UUID, analysis_run_id: UUID) -> AnalysisRun | None:
        return await self._session.scalar(
            select(AnalysisRun).where(
                AnalysisRun.workspace_id == workspace_id,
                AnalysisRun.analysis_run_id == analysis_run_id,
            )
        )

    async def _lock_run(self, workspace_id: UUID, analysis_run_id: UUID) -> AnalysisRun:
        run = await self._session.scalar(
            select(AnalysisRun)
            .where(
                AnalysisRun.workspace_id == workspace_id,
                AnalysisRun.analysis_run_id == analysis_run_id,
            )
            .with_for_update()
        )
        if run is None:
            raise RunNotFound("analysis run not found")
        return run

    async def _apply_transition(
        self,
        run: AnalysisRun,
        target: AnalysisRunStatus,
        *,
        payload: dict[str, Any] | None = None,
        quality_gate_passed: bool = False,
        stage_input: Any = None,
        stage_output: Any = None,
        cancellation_reason: str | None = None,
        origin_mode: OriginMode = OriginMode.FIXTURE,
    ) -> TransitionRecord:
        current = AnalysisRunStatus(run.status)
        self._machine.validate_transition(
            current,
            target,
            quality_gate_passed=quality_gate_passed,
            last_resumable_stage=(
                AnalysisRunStatus(run.last_resumable_stage)
                if run.last_resumable_stage
                else None
            ),
        )
        now = utc_now()
        run.status = target
        if target in EXECUTING_STAGES:
            # Stage entry: record the stage input hash immediately; the output
            # hash lands when the stage completes (record_stage_output).
            results = dict(run.stage_results)
            entry = dict(results.get(target.value, {}))
            entry["inputHash"] = stage_io_hash(
                stage_input if stage_input is not None else {"stage": target.value}
            )
            results[target.value] = entry
            run.stage_results = results
            if run.started_at is None:
                run.started_at = now
            run.heartbeat_at = now
        if current in EXECUTING_STAGES and stage_output is not None:
            results = dict(run.stage_results)
            entry = dict(results.get(current.value, {}))
            entry["outputHash"] = stage_io_hash(stage_output)
            results[current.value] = entry
            run.stage_results = results
        if target == AnalysisRunStatus.NEEDS_ATTENTION:
            run.last_resumable_stage = current
        if current == AnalysisRunStatus.NEEDS_ATTENTION and target in EXECUTING_STAGES:
            run.last_resumable_stage = None
            run.heartbeat_at = now
        if target == AnalysisRunStatus.CANCELLED:
            run.cancellation_reason = cancellation_reason or "user_cancelled"
            run.cancelled_at = now
        if target in (AnalysisRunStatus.READY, AnalysisRunStatus.BLOCKED):
            run.completed_at = now
            run.progress = 1.0 if target == AnalysisRunStatus.READY else run.progress
        await self._session.flush()

        if target in _EVENT_TYPE_FOR_TERMINAL:
            category, event_type = _EVENT_TYPE_FOR_TERMINAL[target]
        elif current == AnalysisRunStatus.NEEDS_ATTENTION:
            category, event_type = "agent.status", "analysis.resumed"
        else:
            category, event_type = "agent.status", "analysis.stage.started"
        event = await self.append_event(
            run,
            category=category,
            type=event_type,
            payload={
                "from": current.value,
                "status": target.value,
                **(payload or {}),
            },
            origin_mode=origin_mode,
        )
        return TransitionRecord(
            analysis_run_id=run.analysis_run_id,
            from_status=current,
            to_status=target,
            event_id=event.id,
            sequence=event.sequence,
        )

    async def transition(
        self,
        workspace_id: UUID,
        analysis_run_id: UUID,
        target: AnalysisRunStatus,
        **kwargs: Any,
    ) -> TransitionRecord:
        run = await self._lock_run(workspace_id, analysis_run_id)
        return await self._apply_transition(run, target, **kwargs)

    async def record_stage_completed(
        self,
        workspace_id: UUID,
        analysis_run_id: UUID,
        *,
        stage: AnalysisRunStatus,
        output: Any,
        progress: float,
        digest: Mapping[str, Any] | None = None,
        influences: list[Mapping[str, Any]] | None = None,
    ) -> None:
        run = await self._lock_run(workspace_id, analysis_run_id)
        results = dict(run.stage_results)
        entry = dict(results.get(stage.value, {}))
        entry["outputHash"] = stage_io_hash(output)
        results[stage.value] = entry
        run.stage_results = results
        run.progress = max(0.0, min(1.0, progress))
        await self._session.flush()
        # The digest rides the persisted event so the thinking trace is both
        # streamed (SSE) and replayable (Last-Event-ID) without a new table.
        payload: dict[str, Any] = {"stage": stage.value, "outputHash": entry["outputHash"]}
        if digest:
            payload["digest"] = dict(digest)
        if influences:
            # Factor->factor edges ride the persisted event (whitelisted type)
            # so the sandbox can rebuild the propagation graph without a new
            # table - append-only and replayable like the digest.
            payload["influences"] = [dict(edge) for edge in influences]
        await self.append_event(
            run,
            category="agent.status",
            type="analysis.stage.completed",
            payload=payload,
        )

    # --- queue / worker --------------------------------------------------------

    async def claim_next_queued(
        self, *, workspace_id: UUID | None = None
    ) -> AnalysisRun | None:
        """Claim one queued run with FOR UPDATE SKIP LOCKED; None when empty.

        The production worker claims globally; a workspace filter is available
        for tenant-scoped deployments and deterministic tests.
        """

        query = (
            select(AnalysisRun)
            .where(AnalysisRun.status == AnalysisRunStatus.QUEUED)
            .order_by(AnalysisRun.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if workspace_id is not None:
            query = query.where(AnalysisRun.workspace_id == workspace_id)
        run = await self._session.scalar(query)
        if run is None:
            return None
        await self._apply_transition(run, AnalysisRunStatus.PLANNING)
        return run

    async def heartbeat(self, workspace_id: UUID, analysis_run_id: UUID) -> None:
        await self._session.execute(
            update(AnalysisRun)
            .where(
                AnalysisRun.workspace_id == workspace_id,
                AnalysisRun.analysis_run_id == analysis_run_id,
                AnalysisRun.status.in_(list(EXECUTING_STAGES)),
            )
            .values(heartbeat_at=utc_now())
        )

    async def cancellation_requested(
        self, workspace_id: UUID, analysis_run_id: UUID
    ) -> bool:
        """Persisted cooperative-stop check for stage/external-call boundaries."""

        status = await self._session.scalar(
            select(AnalysisRun.status).where(
                AnalysisRun.workspace_id == workspace_id,
                AnalysisRun.analysis_run_id == analysis_run_id,
            )
        )
        return status is not None and AnalysisRunStatus(status) == AnalysisRunStatus.CANCELLED

    async def cancel(
        self,
        workspace_id: UUID,
        analysis_run_id: UUID,
        *,
        reason: str = "user_cancelled",
    ) -> AnalysisRun:
        """Idempotent cancel; canonical terminal state written atomically."""

        run = await self._lock_run(workspace_id, analysis_run_id)
        current = AnalysisRunStatus(run.status)
        if current == AnalysisRunStatus.CANCELLED:
            return run  # idempotent: same terminal state, no new records
        if current in (AnalysisRunStatus.READY, AnalysisRunStatus.BLOCKED):
            raise RunNotCancellable(
                f"run status {current.value!r} is not a cancellable active task"
            )
        await self._apply_transition(
            run,
            AnalysisRunStatus.CANCELLED,
            payload={"reason": reason},
            cancellation_reason=reason,
        )
        return run

    async def recover_stale_runs(
        self, *, timeout: timedelta = DEFAULT_HEARTBEAT_TIMEOUT
    ) -> list[UUID]:
        """Move active executing runs with an expired heartbeat to needs_attention."""

        cutoff = utc_now() - timeout
        rows = (
            await self._session.scalars(
                select(AnalysisRun)
                .where(
                    AnalysisRun.status.in_(list(EXECUTING_STAGES)),
                    AnalysisRun.heartbeat_at.is_not(None),
                    AnalysisRun.heartbeat_at < cutoff,
                )
                .with_for_update(skip_locked=True)
            )
        ).all()
        recovered: list[UUID] = []
        for run in rows:
            await self._apply_transition(
                run,
                AnalysisRunStatus.NEEDS_ATTENTION,
                payload={"reason": "heartbeat_expired"},
            )
            recovered.append(run.analysis_run_id)
        return recovered

    # --- resolution idempotency (CCR-20260725-ANALYSIS-01 §2.2) ------------------

    async def check_resolution_idempotency(
        self, workspace_id: UUID, idempotency_key: str, request_hash: str
    ) -> IdempotencyRecord | None:
        """Return the stored record on an exact replay, None when the key is new.

        Same key + different normalized body hash raises
        :class:`IdempotencyConflict` (wire: IDEMPOTENCY_CONFLICT 409).
        """

        record = await self._session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.workspace_id == workspace_id,
                IdempotencyRecord.route_key == RESOLUTIONS_ROUTE_KEY,
                IdempotencyRecord.idempotency_key == idempotency_key,
            )
        )
        if record is None:
            return None
        if record.normalized_request_hash != request_hash:
            raise IdempotencyConflict(
                "same Idempotency-Key was already used with a different body"
            )
        return record

    async def record_resolution_idempotency(
        self,
        workspace_id: UUID,
        *,
        idempotency_key: str,
        request_hash: str,
        resolution_id: UUID,
        http_status: int = 200,
    ) -> IdempotencyRecord:
        now = utc_now()
        record = IdempotencyRecord(
            id=uuid4(),
            workspace_id=workspace_id,
            route_key=RESOLUTIONS_ROUTE_KEY,
            idempotency_key=idempotency_key,
            normalized_request_hash=request_hash,
            resource_type="run_resolution",
            resource_id=resolution_id,
            http_status=http_status,
            response_kind="success",
            created_at=now,
            expires_at=now + _IDEMPOTENCY_RETENTION,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def load_resolution_replay(
        self, workspace_id: UUID, resolution_id: UUID
    ) -> tuple[RunResolution, RunInterventionClassification, AnalysisEvent | None] | None:
        """Rebuild the pieces of the original success body for an idempotent replay."""

        resolution = await self._session.scalar(
            select(RunResolution).where(
                RunResolution.workspace_id == workspace_id,
                RunResolution.id == resolution_id,
            )
        )
        if resolution is None:
            return None
        classification = await self._session.scalar(
            select(RunInterventionClassification).where(
                RunInterventionClassification.workspace_id == workspace_id,
                RunInterventionClassification.id == resolution.classification_id,
            )
        )
        if classification is None:
            return None
        events = await self.list_events_after(
            workspace_id, resolution.analysis_run_id, 0
        )
        resumed_event = next(
            (
                event
                for event in events
                if event.type == "analysis.resumed"
                and event.payload.get("resolutionId") == str(resolution.id)
            ),
            None,
        )
        return resolution, classification, resumed_event

    # --- interventions: resolution vs amendment ---------------------------------

    async def classify_and_resolve(
        self,
        workspace_id: UUID,
        analysis_run_id: UUID,
        *,
        payload: dict[str, Any],
        created_by: UUID,
        proposed_charter_changes: dict[str, Any] | None = None,
    ) -> tuple[RunInterventionClassification, RunResolution, TransitionRecord]:
        """Canonical intervention flow: classification first, then resolution.

        A lens-set (or any frozen-field) change is an amendment: the
        classification is persisted with ``result=amendment`` and
        :class:`RunAmendmentRequired` is raised — never a RunResolution.
        """

        run = await self._lock_run(workspace_id, analysis_run_id)
        current = AnalysisRunStatus(run.status)
        if current != AnalysisRunStatus.NEEDS_ATTENTION:
            raise RunNotResumable(
                f"run status {current.value!r} is not needs_attention"
            )
        if run.last_resumable_stage is None:
            raise RunNotResumable("run has no persisted lastResumableStage")

        charter = await self._require_charter(workspace_id, run.charter_id)
        changed: list[str] = []
        if proposed_charter_changes:
            frozen_now = {
                "decision_question": charter.decision_question,
                "goals": charter.goals,
                "options": charter.option_ids,
                "preference_weights": charter.preference_weights,
                "hard_constraints": charter.constraints,
                "material_scope": charter.allowed_material_ids,
                "connector_scope": charter.allowed_connector_ids,
                "budget": charter.budget,
                "method": [charter.method_id, charter.method_version],
                "analysis_level": (
                    charter.analysis_level.value
                    if isinstance(charter.analysis_level, FormalAnalysisLevel)
                    else str(charter.analysis_level)
                ),
                "strategic_lens_set": charter.required_strategic_lens_types,
            }
            changed = diff_frozen_fields(frozen_now, proposed_charter_changes)

        classification = RunInterventionClassification(
            id=uuid4(),
            workspace_id=workspace_id,
            decision_case_id=run.decision_case_id,
            analysis_run_id=run.analysis_run_id,
            result="amendment" if changed else "resolution",
            changed_frozen_fields=changed,
            reason_codes=[],
            created_by=created_by,
        )
        self._session.add(classification)
        await self._session.flush()

        if changed:
            await self.append_event(
                run,
                category="agent.status",
                type="analysis.amendment_required",
                payload={"changedFrozenFields": changed},
            )
            raise RunAmendmentRequired(changed, classification.id)

        kind = payload.get("kind")
        if kind not in _RESOLUTION_KINDS:
            raise RunResolutionInvalid(f"resolution kind {kind!r} is not allowed")
        if kind == "provider_recovery":
            connector_id = payload.get("connectorId")
            if connector_id is not None and str(connector_id) not in [
                str(cid) for cid in charter.allowed_connector_ids
            ]:
                raise RunResolutionInvalid(
                    "provider_recovery may only switch to a charter-allowed connector"
                )

        resume_stage = AnalysisRunStatus(run.last_resumable_stage)
        resolution = RunResolution(
            id=uuid4(),
            workspace_id=workspace_id,
            decision_case_id=run.decision_case_id,
            analysis_run_id=run.analysis_run_id,
            classification_id=classification.id,
            payload=payload,
            resume_stage=resume_stage,
            created_by=created_by,
        )
        self._session.add(resolution)
        await self._session.flush()

        record = await self._apply_transition(
            run,
            resume_stage,
            payload={"resolutionId": str(resolution.id), "resumedFrom": resume_stage.value},
        )
        return classification, resolution, record

    # --- packets & lens artifact ids ---------------------------------------------

    async def add_research_packet(self, **values: Any) -> ResearchPacket:
        packet = ResearchPacket(id=values.pop("id", uuid4()), **values)
        self._session.add(packet)
        await self._session.flush()
        return packet

    async def record_lens_artifact_id(
        self, workspace_id: UUID, analysis_run_id: UUID, artifact_id: UUID
    ) -> None:
        run = await self._lock_run(workspace_id, analysis_run_id)
        ids = list(run.strategic_lens_artifact_ids)
        if str(artifact_id) not in ids:
            ids.append(str(artifact_id))
            run.strategic_lens_artifact_ids = ids
            await self._session.flush()
