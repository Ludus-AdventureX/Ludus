"""Read-side helpers for the dossier domain (Task 4).

All persistence goes through the frozen canonical tables in ``app/models.py``
(Task 19A migration); this lane's only supplementary table is the immutable
``DossierVersionSnapshot`` companion row.

Every query here is workspace-scoped by construction: the workspace id is a
mandatory argument and is always part of the WHERE clause, never a post-filter.
Cross-tenant lookups therefore resolve to ``None`` and surface as uniform 404s.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CandidateRevision,
    CaseVersion,
    DecisionCase,
    DecisionSubject,
    DossierEntry,
    DossierVersion,
)
from app.types import EntryStatus

from .models import DossierVersionSnapshot


class DossierRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_subject(
        self, workspace_id: UUID, subject_id: UUID, *, for_update: bool = False
    ) -> DecisionSubject | None:
        statement = select(DecisionSubject).where(
            DecisionSubject.workspace_id == workspace_id,
            DecisionSubject.id == subject_id,
        )
        if for_update:
            # The subject row is the concurrency anchor for dossier version
            # bumps (there is no separate dossier-head table in the frozen
            # canonical schema).
            statement = statement.with_for_update()
        return await self._session.scalar(statement)

    async def get_case(self, workspace_id: UUID, decision_case_id: UUID) -> DecisionCase | None:
        return await self._session.scalar(
            select(DecisionCase).where(
                DecisionCase.workspace_id == workspace_id,
                DecisionCase.decision_case_id == decision_case_id,
            )
        )

    async def current_dossier_version(self, workspace_id: UUID, dossier_id: UUID) -> int:
        """Current version = latest persisted version row; an empty dossier is
        version 1 by canonical convention (06-data-model currentVersion)."""

        latest = await self._session.scalar(
            select(func.max(DossierVersion.version)).where(
                DossierVersion.workspace_id == workspace_id,
                DossierVersion.dossier_id == dossier_id,
            )
        )
        return latest or 1

    async def get_entry(self, workspace_id: UUID, entry_id: UUID) -> DossierEntry | None:
        return await self._session.scalar(
            select(DossierEntry).where(
                DossierEntry.workspace_id == workspace_id,
                DossierEntry.id == entry_id,
            )
        )

    async def get_candidate(
        self, workspace_id: UUID, candidate_id: UUID
    ) -> CandidateRevision | None:
        return await self._session.scalar(
            select(CandidateRevision).where(
                CandidateRevision.workspace_id == workspace_id,
                CandidateRevision.id == candidate_id,
            )
        )

    async def list_candidates(
        self, workspace_id: UUID, decision_case_id: UUID
    ) -> list[CandidateRevision]:
        result = await self._session.scalars(
            select(CandidateRevision)
            .where(
                CandidateRevision.workspace_id == workspace_id,
                CandidateRevision.decision_case_id == decision_case_id,
            )
            .order_by(CandidateRevision.id)
        )
        return list(result)

    async def list_confirmed_entries(
        self,
        workspace_id: UUID,
        subject_id: UUID,
        *,
        decision_case_id: UUID | None = None,
    ) -> list[DossierEntry]:
        """Confirmed entries visible to a case: subject-scoped plus that case's own.

        Candidates never appear here: candidates live in ``candidate_revisions``
        and are excluded from every snapshot by construction.
        """

        statement = (
            select(DossierEntry)
            .where(
                DossierEntry.workspace_id == workspace_id,
                DossierEntry.decision_subject_id == subject_id,
                DossierEntry.status == EntryStatus.CONFIRMED,
            )
            .order_by(DossierEntry.id)
        )
        entries = list(await self._session.scalars(statement))
        return [
            entry
            for entry in entries
            if entry.decision_case_id is None or entry.decision_case_id == decision_case_id
        ]

    async def list_dossier_versions(
        self, workspace_id: UUID, dossier_id: UUID
    ) -> list[DossierVersion]:
        result = await self._session.scalars(
            select(DossierVersion)
            .where(
                DossierVersion.workspace_id == workspace_id,
                DossierVersion.dossier_id == dossier_id,
            )
            .order_by(DossierVersion.version)
        )
        return list(result)

    async def get_dossier_version(
        self, workspace_id: UUID, dossier_id: UUID, version: int
    ) -> DossierVersion | None:
        return await self._session.scalar(
            select(DossierVersion).where(
                DossierVersion.workspace_id == workspace_id,
                DossierVersion.dossier_id == dossier_id,
                DossierVersion.version == version,
            )
        )

    async def get_version_snapshot(
        self, workspace_id: UUID, dossier_version_id: UUID
    ) -> DossierVersionSnapshot | None:
        return await self._session.scalar(
            select(DossierVersionSnapshot).where(
                DossierVersionSnapshot.workspace_id == workspace_id,
                DossierVersionSnapshot.dossier_version_id == dossier_version_id,
            )
        )

    async def get_case_version(
        self, workspace_id: UUID, decision_case_id: UUID, version: int
    ) -> CaseVersion | None:
        return await self._session.scalar(
            select(CaseVersion).where(
                CaseVersion.workspace_id == workspace_id,
                CaseVersion.decision_case_id == decision_case_id,
                CaseVersion.version == version,
            )
        )
