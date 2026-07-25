"""Tenant-scoped read repository for the evidence ledger (Task 8).

Every query filters on ``workspace_id`` first; a miss, a foreign-workspace
row, and a nonexistent id are indistinguishable to callers (``None`` /
empty), which the router folds into the uniform CASE_NOT_FOUND 404. No
update or delete surface exists: raw artifacts and assessments are immutable
and evidence corrections happen by writing new rows in later tasks.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AnalysisRun, SourceRecord, SourceSpan

from .models import EvidenceItem, EvidenceRelation, QualityAssessment, RawArtifact


class EvidenceReadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_evidence_item(
        self, workspace_id: UUID, evidence_item_id: UUID
    ) -> EvidenceItem | None:
        return await self._session.scalar(
            select(EvidenceItem).where(
                EvidenceItem.workspace_id == workspace_id,
                EvidenceItem.id == evidence_item_id,
            )
        )

    async def get_raw_artifact(
        self, workspace_id: UUID, raw_artifact_id: UUID
    ) -> RawArtifact | None:
        return await self._session.scalar(
            select(RawArtifact).where(
                RawArtifact.workspace_id == workspace_id,
                RawArtifact.id == raw_artifact_id,
            )
        )

    async def get_quality_assessment(
        self, workspace_id: UUID, quality_assessment_id: UUID
    ) -> QualityAssessment | None:
        return await self._session.scalar(
            select(QualityAssessment).where(
                QualityAssessment.workspace_id == workspace_id,
                QualityAssessment.id == quality_assessment_id,
            )
        )

    async def get_source_record(
        self, workspace_id: UUID, source_record_id: UUID
    ) -> SourceRecord | None:
        return await self._session.scalar(
            select(SourceRecord).where(
                SourceRecord.workspace_id == workspace_id,
                SourceRecord.id == source_record_id,
            )
        )

    async def list_source_spans(
        self, workspace_id: UUID, source_record_id: UUID
    ) -> list[SourceSpan]:
        result = await self._session.scalars(
            select(SourceSpan)
            .where(
                SourceSpan.workspace_id == workspace_id,
                SourceSpan.source_record_id == source_record_id,
            )
            .order_by(SourceSpan.created_at)
        )
        return list(result)

    async def run_exists(self, workspace_id: UUID, analysis_run_id: UUID) -> bool:
        run = await self._session.scalar(
            select(AnalysisRun.analysis_run_id).where(
                AnalysisRun.workspace_id == workspace_id,
                AnalysisRun.analysis_run_id == analysis_run_id,
            )
        )
        return run is not None

    async def list_run_evidence(
        self, workspace_id: UUID, analysis_run_id: UUID
    ) -> list[EvidenceItem]:
        result = await self._session.scalars(
            select(EvidenceItem)
            .where(
                EvidenceItem.workspace_id == workspace_id,
                EvidenceItem.analysis_run_id == analysis_run_id,
            )
            .order_by(EvidenceItem.created_at, EvidenceItem.id)
        )
        return list(result)

    async def list_same_source_group(
        self, workspace_id: UUID, item: EvidenceItem
    ) -> list[EvidenceItem]:
        if item.independent_source_group_id is None:
            return [item]
        result = await self._session.scalars(
            select(EvidenceItem)
            .where(
                EvidenceItem.workspace_id == workspace_id,
                EvidenceItem.analysis_run_id == item.analysis_run_id,
                EvidenceItem.independent_source_group_id
                == item.independent_source_group_id,
            )
            .order_by(EvidenceItem.created_at, EvidenceItem.id)
        )
        return list(result)

    async def list_conflict_relations(
        self, workspace_id: UUID, analysis_run_id: UUID
    ) -> list[EvidenceRelation]:
        result = await self._session.scalars(
            select(EvidenceRelation)
            .join(
                EvidenceItem,
                (EvidenceItem.workspace_id == EvidenceRelation.workspace_id)
                & (EvidenceItem.id == EvidenceRelation.from_evidence_item_id),
            )
            .where(
                EvidenceRelation.workspace_id == workspace_id,
                EvidenceRelation.kind == "conflicts_with",
                EvidenceItem.analysis_run_id == analysis_run_id,
            )
            .order_by(EvidenceRelation.created_at, EvidenceRelation.id)
        )
        return list(result)
