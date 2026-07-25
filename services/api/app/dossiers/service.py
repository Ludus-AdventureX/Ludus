"""Dossier command objects and the transactional confirmation service (Task 4).

Persistence targets are the FROZEN canonical tables in ``app/models.py``
(Task 19A migration): ``dossier_entries``, ``dossier_versions``,
``candidate_revisions``, ``case_versions`` and ``domain_events``. This lane
adds only the immutable ``DossierVersionSnapshot`` companion row.

Command semantics (18-plan Task 4 Step 2, consumed verbatim):

- ``ProposeEntry`` creates only a ``CandidateRevision`` plus a candidate audit
  event; ``RejectEntry`` only closes the candidate and writes an audit event.
  Neither may produce a formal Dossier/Case version.
- ``ConfirmEntry`` validates ``base_dossier_version`` (and the optional
  ``base_case_version``) and then, in the *same transaction*, writes the formal
  entry, the new Dossier/Case versions and the confirmation event.
- ``ExpireEntry`` / ``ReclassifyEntry`` on a *confirmed* entry are explicit
  formal edits and also produce a new version; applied to a *candidate* they
  only update the candidate.

Snapshots (Step 3): each ``DossierVersion`` + companion snapshot row freezes
entry ids, entry versions, profile version, subject version, the creation
reason and a content hash. Later entry edits never mutate existing rows.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CandidateRevision,
    CaseVersion,
    DecisionCase,
    DecisionSubject,
    DomainEvent,
    DossierEntry,
    DossierVersion,
)
from app.types import (
    CandidateRevisionStatus,
    CandidateSourceType,
    DomainEventActor,
    DossierScope,
    DossierSourceType,
    DossierStatementType,
    EntryStatus,
)

from .models import DossierVersionSnapshot
from .repository import DossierRepository


class DossierError(Exception):
    """Base class; carries a stable machine-readable ``code``."""

    code = "dossier_error"


class DossierNotFoundError(DossierError):
    """Subject/case/candidate/entry invisible in this workspace (uniform 404)."""

    code = "dossier_scope_not_found"


class DossierVersionConflictError(DossierError):
    """The command's base version no longer matches the current head (409)."""

    code = "dossier_version_conflict"

    def __init__(self, message: str, *, expected: int, actual: int) -> None:
        super().__init__(message)
        self.expected = expected
        self.actual = actual


class CandidateNotReviewableError(DossierError):
    """The candidate has already been reviewed (accepted/rejected)."""

    code = "candidate_not_reviewable"


# ---------------------------------------------------------------------------
# Command objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProposeEntry:
    workspace_id: UUID
    decision_subject_id: UUID
    proposals: list[dict[str, Any]]
    source_type: CandidateSourceType
    source_id: UUID
    base_dossier_version: int
    decision_case_id: UUID | None = None
    base_case_version: int | None = None
    actor: DomainEventActor = DomainEventActor.USER


@dataclass(frozen=True)
class ConfirmEntry:
    workspace_id: UUID
    candidate_revision_id: UUID
    base_dossier_version: int
    base_case_version: int | None = None
    # Optional per-proposal overrides applied at confirm time, keyed by the
    # proposal index (e.g. the reviewer corrected the statement type).
    statement_type_overrides: dict[int, DossierStatementType] = field(default_factory=dict)
    created_by: str = "user"
    actor: DomainEventActor = DomainEventActor.USER


@dataclass(frozen=True)
class RejectEntry:
    workspace_id: UUID
    candidate_revision_id: UUID
    reason: str | None = None
    actor: DomainEventActor = DomainEventActor.USER


@dataclass(frozen=True)
class ExpireEntry:
    """Target may be a confirmed entry (formal edit) or a candidate (soft)."""

    workspace_id: UUID
    target_id: UUID
    reason: str = "expired by user"
    created_by: str = "user"
    actor: DomainEventActor = DomainEventActor.USER


@dataclass(frozen=True)
class ReclassifyEntry:
    workspace_id: UUID
    target_id: UUID
    new_statement_type: DossierStatementType
    reason: str = "reclassified by user"
    created_by: str = "user"
    actor: DomainEventActor = DomainEventActor.USER


@dataclass(frozen=True)
class SnapshotEntryRef:
    """One immutable entry reference inside a snapshot projection."""

    id: UUID
    version: int
    statement_type: str
    content_hash: str


@dataclass(frozen=True)
class DossierSnapshot:
    """Service-level projection of one immutable DossierVersion (+ companion)."""

    dossier_id: UUID
    version: int
    snapshot_hash: str
    reason: str
    entries: tuple[SnapshotEntryRef, ...]


def content_hash(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def _snapshot_hash(payload: Any) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


_SUBJECT_KEY = "decisionSubjectId"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class DossierService:
    """Transactional dossier commands. Flushes but never commits: the caller
    (route handler or test) owns the enclosing transaction so that a confirm
    writes the entry, both versions and the event atomically."""

    def __init__(self, session: AsyncSession, *, workspace_id: UUID | None = None) -> None:
        self._session = session
        self._repo = DossierRepository(session)
        # Optional default tenant context so test/service callers may omit the
        # workspace on the convenience surface; routes always pass it explicitly.
        self._workspace_id = workspace_id

    @property
    def repository(self) -> DossierRepository:
        return self._repo

    # -- version helpers ------------------------------------------------------

    async def current_dossier_version(self, workspace_id: UUID, subject_id: UUID) -> int:
        subject = await self._repo.get_subject(workspace_id, subject_id)
        if subject is None:
            raise DossierNotFoundError("subject not visible in this workspace")
        return await self._repo.current_dossier_version(workspace_id, subject.dossier_id)

    # -- 18-plan Step 1 test surface -----------------------------------------

    async def add_entry(
        self,
        subject_id: UUID,
        content: str,
        statement_type: str,
        status: str,
        *,
        scope: str = "subject",
        decision_case_id: UUID | None = None,
        workspace_id: UUID | None = None,
        source_type: DossierSourceType = DossierSourceType.USER,
        created_by: str = "user",
    ) -> DossierEntry | CandidateRevision:
        """Convenience entry point mirroring the 18-plan Step 1 fixture call.

        ``status="confirmed"`` writes a formal entry + new dossier version in
        one transaction; ``status="candidate"`` routes through ``propose`` and
        returns the ``CandidateRevision`` (candidates never touch
        ``dossier_entries``).
        """

        workspace_id = workspace_id or self._workspace_id
        if workspace_id is None:
            raise DossierError("add_entry requires a workspace context")
        subject = await self._repo.get_subject(workspace_id, subject_id)
        if subject is None:
            raise DossierNotFoundError("subject not visible in this workspace")

        if status == EntryStatus.CANDIDATE.value:
            case = None
            if decision_case_id is not None:
                case = await self._require_same_subject_case(
                    workspace_id, subject_id, decision_case_id
                )
            current = await self._repo.current_dossier_version(
                workspace_id, subject.dossier_id
            )
            return await self.propose(
                ProposeEntry(
                    workspace_id=workspace_id,
                    decision_subject_id=subject_id,
                    decision_case_id=decision_case_id,
                    proposals=[
                        {
                            "operation": "add",
                            "entry": {
                                "scope": scope,
                                "statementType": statement_type,
                                "content": content,
                                "sourceType": source_type.value,
                            },
                        }
                    ],
                    source_type=CandidateSourceType.CONVERSATION,
                    source_id=uuid4(),
                    base_dossier_version=current,
                    base_case_version=case.current_version if case is not None else None,
                )
            )

        if status != EntryStatus.CONFIRMED.value:
            raise DossierError(f"add_entry does not accept status {status!r}")

        if decision_case_id is not None:
            await self._require_same_subject_case(workspace_id, subject_id, decision_case_id)
        entry = DossierEntry(
            workspace_id=workspace_id,
            decision_subject_id=subject_id,
            decision_case_id=decision_case_id,
            scope=DossierScope(scope),
            statement_type=DossierStatementType(statement_type),
            content=content,
            status=EntryStatus.CONFIRMED,
            source_type=source_type,
            version=1,
        )
        self._session.add(entry)
        await self._session.flush()
        await self._write_dossier_version(
            subject,
            reason=f"direct confirmed entry ({statement_type})",
            created_by=created_by,
            decision_case_id=decision_case_id,
        )
        await self._audit(
            workspace_id,
            aggregate_type="dossier_entry",
            aggregate_id=entry.id,
            event_type="dossier.entry_confirmed",
            actor=DomainEventActor.USER,
            payload={"statementType": statement_type, "direct": True},
        )
        return entry

    # -- commands ------------------------------------------------------------

    async def propose(self, command: ProposeEntry) -> CandidateRevision:
        """Create only a CandidateRevision + candidate event. No versions."""

        subject = await self._repo.get_subject(
            command.workspace_id, command.decision_subject_id
        )
        if subject is None:
            raise DossierNotFoundError("subject not visible in this workspace")
        if command.decision_case_id is not None:
            await self._require_same_subject_case(
                command.workspace_id, command.decision_subject_id, command.decision_case_id
            )
        # The frozen candidate_revisions table has no subject column; pin the
        # subject inside each proposal so subject-only candidates stay
        # resolvable at confirm time.
        proposals: list[dict[str, Any]] = []
        for item in command.proposals:
            entry_payload = dict(item.get("entry", {}))
            entry_payload[_SUBJECT_KEY] = str(command.decision_subject_id)
            proposals.append({**item, "entry": entry_payload})
        candidate = CandidateRevision(
            workspace_id=command.workspace_id,
            decision_case_id=command.decision_case_id,
            source_type=command.source_type,
            source_id=command.source_id,
            base_dossier_version=command.base_dossier_version,
            base_case_version=command.base_case_version,
            proposals=proposals,
            status=CandidateRevisionStatus.PENDING,
        )
        self._session.add(candidate)
        await self._session.flush()
        await self._audit(
            command.workspace_id,
            aggregate_type="candidate_revision",
            aggregate_id=candidate.id,
            event_type="dossier.candidate_proposed",
            actor=command.actor,
            payload={
                "decisionSubjectId": str(command.decision_subject_id),
                "decisionCaseId": (
                    str(command.decision_case_id)
                    if command.decision_case_id is not None
                    else None
                ),
                "proposalCount": len(proposals),
                "baseDossierVersion": command.base_dossier_version,
                "baseCaseVersion": command.base_case_version,
            },
        )
        return candidate

    async def reject(self, command: RejectEntry) -> CandidateRevision:
        """Close the candidate and write the audit event. No versions."""

        candidate = await self._require_pending_candidate(
            command.workspace_id, command.candidate_revision_id
        )
        candidate.status = CandidateRevisionStatus.REJECTED
        candidate.reviewed_at = _utc_now()
        await self._session.flush()
        await self._audit(
            command.workspace_id,
            aggregate_type="candidate_revision",
            aggregate_id=candidate.id,
            event_type="dossier.candidate_rejected",
            actor=command.actor,
            payload={"reason": command.reason},
        )
        return candidate

    async def confirm(self, command: ConfirmEntry) -> dict[str, Any]:
        """Validate base versions then atomically write entries + versions + event."""

        candidate = await self._require_pending_candidate(
            command.workspace_id, command.candidate_revision_id
        )
        subject_id = await self._candidate_subject_id(command.workspace_id, candidate)
        subject = await self._repo.get_subject(
            command.workspace_id, subject_id, for_update=True
        )
        if subject is None:
            raise DossierNotFoundError("subject not visible in this workspace")
        current_version = await self._repo.current_dossier_version(
            command.workspace_id, subject.dossier_id
        )
        if command.base_dossier_version != current_version:
            raise DossierVersionConflictError(
                "base_dossier_version is stale",
                expected=current_version,
                actual=command.base_dossier_version,
            )
        case: DecisionCase | None = None
        if candidate.decision_case_id is not None:
            case = await self._repo.get_case(
                command.workspace_id, candidate.decision_case_id
            )
            if case is None:
                raise DossierNotFoundError("case not visible in this workspace")
            if (
                command.base_case_version is not None
                and command.base_case_version != case.current_version
            ):
                raise DossierVersionConflictError(
                    "base_case_version is stale",
                    expected=case.current_version,
                    actual=command.base_case_version,
                )

        confirmed_entries: list[DossierEntry] = []
        for index, proposal in enumerate(candidate.proposals):
            operation = proposal.get("operation", "add")
            payload = proposal.get("entry", {})
            statement_type = command.statement_type_overrides.get(
                index, DossierStatementType(payload["statementType"])
            )
            if operation == "add":
                scope_value = payload.get("scope", "subject")
                if candidate.decision_case_id is None:
                    # A case-scoped proposal cannot outlive a subject-only
                    # candidate; degrade to subject scope defensively.
                    scope_value = "subject"
                entry = DossierEntry(
                    workspace_id=command.workspace_id,
                    decision_subject_id=subject_id,
                    decision_case_id=(
                        candidate.decision_case_id if scope_value == "case" else None
                    ),
                    scope=DossierScope(scope_value),
                    statement_type=statement_type,
                    content=payload["content"],
                    status=EntryStatus.CONFIRMED,
                    source_type=DossierSourceType(
                        payload.get("sourceType", DossierSourceType.AI_CANDIDATE.value)
                    ),
                    source_ref=str(candidate.id),
                    version=1,
                )
                self._session.add(entry)
                confirmed_entries.append(entry)
            elif operation in ("update", "reclassify", "expire"):
                target = await self._repo.get_entry(
                    command.workspace_id, UUID(str(payload["entryId"]))
                )
                if target is None:
                    raise DossierNotFoundError("target entry not visible")
                if operation == "update":
                    target.content = payload["content"]
                elif operation == "reclassify":
                    target.statement_type = statement_type
                else:
                    target.status = EntryStatus.EXPIRED
                target.version += 1
                confirmed_entries.append(target)
            else:
                raise DossierError(f"unsupported proposal operation {operation!r}")
        await self._session.flush()

        dossier_version = await self._write_dossier_version(
            subject,
            reason=f"candidate {candidate.id} confirmed",
            created_by=command.created_by,
            decision_case_id=candidate.decision_case_id,
        )

        case_version: CaseVersion | None = None
        if case is not None:
            case_version = await self._write_case_version(
                case,
                dossier_version=dossier_version,
                reason=f"candidate {candidate.id} confirmed",
                created_by=command.created_by,
            )

        candidate.status = CandidateRevisionStatus.ACCEPTED
        candidate.reviewed_at = _utc_now()
        await self._session.flush()
        await self._audit(
            command.workspace_id,
            aggregate_type="candidate_revision",
            aggregate_id=candidate.id,
            event_type="dossier.candidate_confirmed",
            actor=command.actor,
            payload={
                "dossierVersion": dossier_version.version,
                "caseVersion": case_version.version if case_version is not None else None,
                "entryIds": [str(entry.id) for entry in confirmed_entries],
            },
        )
        return {
            "candidate": candidate,
            "entries": confirmed_entries,
            "dossier_version": dossier_version,
            "case_version": case_version,
        }

    async def expire(self, command: ExpireEntry) -> dict[str, Any]:
        """Formal edit on a confirmed entry; soft update on a candidate."""

        entry = await self._repo.get_entry(command.workspace_id, command.target_id)
        if entry is not None and entry.status == EntryStatus.CONFIRMED:
            entry.status = EntryStatus.EXPIRED
            entry.version += 1
            await self._session.flush()
            subject = await self._repo.get_subject(
                command.workspace_id, entry.decision_subject_id, for_update=True
            )
            assert subject is not None
            dossier_version = await self._write_dossier_version(
                subject,
                reason=command.reason,
                created_by=command.created_by,
                decision_case_id=entry.decision_case_id,
            )
            await self._audit(
                command.workspace_id,
                aggregate_type="dossier_entry",
                aggregate_id=entry.id,
                event_type="dossier.entry_expired",
                actor=command.actor,
                payload={"formal": True, "dossierVersion": dossier_version.version},
            )
            return {"formal": True, "entry": entry, "dossier_version": dossier_version}

        candidate = await self._require_pending_candidate(
            command.workspace_id, command.target_id
        )
        proposals = [dict(item) for item in candidate.proposals]
        for item in proposals:
            item["expired"] = True
        candidate.proposals = proposals
        candidate.status = CandidateRevisionStatus.REJECTED
        candidate.reviewed_at = _utc_now()
        await self._session.flush()
        await self._audit(
            command.workspace_id,
            aggregate_type="candidate_revision",
            aggregate_id=candidate.id,
            event_type="dossier.candidate_expired",
            actor=command.actor,
            payload={"formal": False},
        )
        return {"formal": False, "candidate": candidate, "dossier_version": None}

    async def reclassify(self, command: ReclassifyEntry) -> dict[str, Any]:
        """Formal edit on a confirmed entry; candidate-only update otherwise."""

        entry = await self._repo.get_entry(command.workspace_id, command.target_id)
        if entry is not None and entry.status == EntryStatus.CONFIRMED:
            entry.statement_type = command.new_statement_type
            entry.version += 1
            await self._session.flush()
            subject = await self._repo.get_subject(
                command.workspace_id, entry.decision_subject_id, for_update=True
            )
            assert subject is not None
            dossier_version = await self._write_dossier_version(
                subject,
                reason=command.reason,
                created_by=command.created_by,
                decision_case_id=entry.decision_case_id,
            )
            await self._audit(
                command.workspace_id,
                aggregate_type="dossier_entry",
                aggregate_id=entry.id,
                event_type="dossier.entry_reclassified",
                actor=command.actor,
                payload={
                    "formal": True,
                    "newStatementType": command.new_statement_type.value,
                    "dossierVersion": dossier_version.version,
                },
            )
            return {"formal": True, "entry": entry, "dossier_version": dossier_version}

        candidate = await self._require_pending_candidate(
            command.workspace_id, command.target_id
        )
        proposals = [dict(item) for item in candidate.proposals]
        for item in proposals:
            entry_payload = dict(item.get("entry", {}))
            entry_payload["statementType"] = command.new_statement_type.value
            item["entry"] = entry_payload
        candidate.proposals = proposals
        await self._session.flush()
        await self._audit(
            command.workspace_id,
            aggregate_type="candidate_revision",
            aggregate_id=candidate.id,
            event_type="dossier.candidate_reclassified",
            actor=command.actor,
            payload={"formal": False, "newStatementType": command.new_statement_type.value},
        )
        return {"formal": False, "candidate": candidate, "dossier_version": None}

    # -- snapshots -----------------------------------------------------------

    async def create_snapshot(
        self,
        decision_case_id: UUID,
        *,
        workspace_id: UUID | None = None,
        reason: str = "case snapshot",
        created_by: str = "user",
    ) -> DossierSnapshot:
        """Freeze the confirmed dossier view of one case into a new version."""

        workspace_id = workspace_id or self._workspace_id
        if workspace_id is None:
            raise DossierError("create_snapshot requires a workspace context")
        case = await self._repo.get_case(workspace_id, decision_case_id)
        if case is None:
            raise DossierNotFoundError("case not visible in this workspace")
        subject = await self._repo.get_subject(
            workspace_id, case.decision_subject_id, for_update=True
        )
        if subject is None:
            raise DossierNotFoundError("subject not visible in this workspace")
        version = await self._write_dossier_version(
            subject,
            reason=reason,
            created_by=created_by,
            decision_case_id=decision_case_id,
        )
        snapshot_row = await self._repo.get_version_snapshot(workspace_id, version.id)
        return self._snapshot_projection(version, snapshot_row)

    @staticmethod
    def _snapshot_projection(
        version: DossierVersion, snapshot_row: DossierVersionSnapshot | None
    ) -> DossierSnapshot:
        entries = snapshot_row.entries if snapshot_row is not None else []
        return DossierSnapshot(
            dossier_id=version.dossier_id,
            version=version.version,
            snapshot_hash=version.snapshot_hash,
            reason=version.reason,
            entries=tuple(
                SnapshotEntryRef(
                    id=UUID(item["entryId"]),
                    version=item["entryVersion"],
                    statement_type=item["statementType"],
                    content_hash=item["contentHash"],
                )
                for item in entries
            ),
        )

    # -- internals -----------------------------------------------------------

    async def _candidate_subject_id(
        self, workspace_id: UUID, candidate: CandidateRevision
    ) -> UUID:
        if candidate.decision_case_id is not None:
            case = await self._repo.get_case(workspace_id, candidate.decision_case_id)
            if case is None:
                raise DossierNotFoundError("case not visible in this workspace")
            return case.decision_subject_id
        for proposal in candidate.proposals:
            pinned = proposal.get("entry", {}).get(_SUBJECT_KEY)
            if pinned:
                return UUID(str(pinned))
        raise DossierNotFoundError("candidate has no resolvable subject")

    async def _require_same_subject_case(
        self, workspace_id: UUID, subject_id: UUID, decision_case_id: UUID
    ) -> DecisionCase:
        case = await self._repo.get_case(workspace_id, decision_case_id)
        if case is None or case.decision_subject_id != subject_id:
            raise DossierNotFoundError("case not visible for this subject")
        return case

    async def _require_pending_candidate(
        self, workspace_id: UUID, candidate_id: UUID
    ) -> CandidateRevision:
        candidate = await self._repo.get_candidate(workspace_id, candidate_id)
        if candidate is None:
            raise DossierNotFoundError("candidate not visible in this workspace")
        if candidate.status != CandidateRevisionStatus.PENDING:
            raise CandidateNotReviewableError(
                f"candidate is {candidate.status.value}, not pending"
            )
        return candidate

    async def _write_dossier_version(
        self,
        subject: DecisionSubject,
        *,
        reason: str,
        created_by: str,
        decision_case_id: UUID | None = None,
        profile_version: int | None = None,
        subject_version: int | None = None,
    ) -> DossierVersion:
        """Append the next immutable DossierVersion + snapshot companion row."""

        confirmed = await self._repo.list_confirmed_entries(
            subject.workspace_id,
            subject.id,
            decision_case_id=decision_case_id,
        )
        entries_payload = [
            {
                "entryId": str(entry.id),
                "entryVersion": entry.version,
                "statementType": entry.statement_type.value,
                "scope": entry.scope.value,
                "contentHash": content_hash(entry.content),
            }
            for entry in confirmed
        ]
        parent_version = await self._repo.current_dossier_version(
            subject.workspace_id, subject.dossier_id
        )
        next_version = parent_version + 1
        snapshot_hash = _snapshot_hash(
            {
                "dossierId": str(subject.dossier_id),
                "version": next_version,
                "entries": entries_payload,
                "profileVersion": profile_version,
                "subjectVersion": subject_version,
            }
        )
        version = DossierVersion(
            workspace_id=subject.workspace_id,
            dossier_id=subject.dossier_id,
            decision_subject_id=subject.id,
            version=next_version,
            parent_version=parent_version,
            entry_ids=[item["entryId"] for item in entries_payload],
            snapshot_hash=snapshot_hash,
            reason=reason,
            created_by=created_by,
        )
        self._session.add(version)
        await self._session.flush()
        self._session.add(
            DossierVersionSnapshot(
                workspace_id=subject.workspace_id,
                dossier_version_id=version.id,
                entries=entries_payload,
                decision_maker_profile_version=profile_version,
                subject_version=subject_version,
            )
        )
        await self._session.flush()
        return version

    async def _write_case_version(
        self,
        case: DecisionCase,
        *,
        dossier_version: DossierVersion,
        reason: str,
        created_by: str,
    ) -> CaseVersion:
        parent_version = case.current_version
        next_version = parent_version + 1
        snapshot = {
            "decisionCaseId": str(case.decision_case_id),
            "title": case.title,
            "decisionQuestion": case.decision_question,
            "status": case.status.value,
            "operationalStatus": case.operational_status.value,
            "version": next_version,
            "dossierVersion": dossier_version.version,
        }
        case_version = CaseVersion(
            workspace_id=case.workspace_id,
            decision_case_id=case.decision_case_id,
            version=next_version,
            parent_version=parent_version,
            dossier_version=dossier_version.version,
            dossier_snapshot_hash=dossier_version.snapshot_hash,
            snapshot=snapshot,
            snapshot_hash=_snapshot_hash(snapshot),
            reason=reason,
            created_by=created_by,
        )
        self._session.add(case_version)
        case.current_version = next_version
        await self._session.flush()
        return case_version

    async def _audit(
        self,
        workspace_id: UUID,
        *,
        aggregate_type: str,
        aggregate_id: UUID,
        event_type: str,
        actor: DomainEventActor,
        payload: dict[str, Any],
    ) -> DomainEvent:
        event = DomainEvent(
            workspace_id=workspace_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            actor=actor,
            payload=payload,
        )
        self._session.add(event)
        await self._session.flush()
        return event
