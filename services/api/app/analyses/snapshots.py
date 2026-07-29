"""Server-authoritative case/dossier snapshot freezing (traceability).

The charter is supposed to freeze WHAT was analysed: a case version, a dossier
version, and a content hash of each, so a report can later be proven to rest on
exactly that input. Until now those four fields were simply whatever the client
sent, and the shipped web client sent `sha256:` + 32 random bytes for each. The
audit chain therefore existed in shape only: two runs over genuinely different
case content produced unrelated hashes that proved nothing, and two runs over
identical content never matched.

This module computes them from the database instead:

- ``case_version`` is the case's own ``current_version``;
- ``case_snapshot_hash`` is a SHA-256 over the canonical JSON of the case fields
  that define the question being decided;
- ``dossier_snapshot_version`` is the highest version among the CONFIRMED dossier
  entries in scope, so it moves when the confirmed record moves;
- ``dossier_snapshot_hash`` is a SHA-256 over the canonical JSON of those entries.

Determinism rules that make the hash worth having:

- only CONFIRMED entries participate - candidates and rejected entries must not
  change what a frozen charter claims to have analysed;
- both subject-scoped and this-case-scoped entries participate, because the
  analysis genuinely reads both;
- entries are ordered by id (a stable, storage-independent key), and the JSON is
  emitted with sorted keys and no whitespace, so the same content always hashes
  identically regardless of row order or dict ordering.

The client may still send these fields (older callers do); the values are
ignored. Server-side freezing is the only way the hash can mean anything.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DecisionCase, DossierEntry
from app.types import EntryStatus


@dataclass(frozen=True, slots=True)
class FrozenCaseSnapshot:
    """What the charter freezes, computed from the database."""

    case_version: int
    case_snapshot_hash: str
    dossier_snapshot_version: int
    dossier_snapshot_hash: str
    decision_question: str
    entry_count: int


class CaseSnapshotUnavailable(RuntimeError):
    """The case does not exist in this workspace, so nothing can be frozen."""


def _digest(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


async def freeze_case_snapshot(
    db: AsyncSession, *, workspace_id: UUID, decision_case_id: UUID
) -> FrozenCaseSnapshot:
    """Freeze the authoritative case + confirmed-dossier snapshot for a charter."""

    case = await db.scalar(
        select(DecisionCase).where(
            DecisionCase.workspace_id == workspace_id,
            DecisionCase.decision_case_id == decision_case_id,
        )
    )
    if case is None:
        raise CaseSnapshotUnavailable("decision case not found in this workspace")

    case_payload = {
        "decisionCaseId": str(case.decision_case_id),
        "decisionSubjectId": str(case.decision_subject_id),
        "currentVersion": int(case.current_version),
        "title": case.title,
        "decisionQuestion": case.decision_question,
        "inferredDecisionType": _enum_value(case.inferred_decision_type),
        "status": _enum_value(case.status),
        "operationalStatus": _enum_value(case.operational_status),
        "summary": dict(case.summary or {}),
        "fiveWOneH": dict(case.five_w_one_h or {}),
    }

    rows = (
        await db.scalars(
            select(DossierEntry)
            .where(
                DossierEntry.workspace_id == workspace_id,
                DossierEntry.decision_subject_id == case.decision_subject_id,
                DossierEntry.status == EntryStatus.CONFIRMED,
                # Subject-wide facts plus this case's own confirmed entries; a
                # sibling case's entries must never enter this snapshot.
                # NOT `in_([case_id, None])`: SQL `col IN (x, NULL)` never
                # matches a NULL row, which silently dropped every subject-wide
                # fact from the snapshot.
                or_(
                    DossierEntry.decision_case_id == decision_case_id,
                    DossierEntry.decision_case_id.is_(None),
                ),
            )
            .order_by(DossierEntry.id)
        )
    ).all()

    entries = [
        {
            "id": str(entry.id),
            "version": int(entry.version),
            "scope": _enum_value(entry.scope),
            "statementType": _enum_value(entry.statement_type),
            "content": entry.content,
            "sourceType": _enum_value(entry.source_type),
            "sourceRef": entry.source_ref,
        }
        for entry in rows
    ]

    return FrozenCaseSnapshot(
        case_version=int(case.current_version),
        case_snapshot_hash=_digest(case_payload),
        # No confirmed entry yet is an honest version 1 of an empty dossier: the
        # hash below still distinguishes it from any populated dossier.
        dossier_snapshot_version=max((entry["version"] for entry in entries), default=1),
        dossier_snapshot_hash=_digest(entries),
        decision_question=case.decision_question,
        entry_count=len(entries),
    )
