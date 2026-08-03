"""Evidence provenance & conflict query routes (Task 8; relative, UNMOUNTED).

Router mounting belongs to the integration layer (Run API lane precedent);
``app.main`` is untouched and these paths are absent from the generated
contracts until a CCR lands them in 10-api-and-events.md. Every route:

- resolves tenancy through ``require_workspace_context`` (uniform 404 for
  foreign/missing workspaces);
- answers cross-workspace access, foreign rows, and nonexistent ids with the
  same CASE_NOT_FOUND 404 so nothing about existence leaks;
- returns only material inside the caller's workspace.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import SourceRecord, SourceSpan
from app.security.envelope import ApiFailure
from app.tenancy.context import WorkspaceContext, require_workspace_context

from .models import EvidenceItem, QualityAssessment, RawArtifact
from .repository import EvidenceReadRepository
from .schemas_api import (
    ConflictListView,
    ConflictRelationView,
    EvidenceDirectionView,
    EvidenceItemView,
    EvidenceProvenanceView,
    PacketEvidenceView,
    QualityDimensionsView,
    RawArtifactView,
    RunEvidenceListView,
    SameSourceGroupView,
    SourceRecordView,
    SourceSpanView,
)

router = APIRouter(prefix="/api/workspaces/{workspaceId}")


def case_not_found() -> ApiFailure:
    """Uniform 404: missing, foreign, and cross-tenant reads are identical."""

    return ApiFailure(
        "CASE_NOT_FOUND",
        "Case material not found.",
        http_status=404,
    )


def _envelope(data: object) -> dict[str, object]:
    return {"ok": True, "data": data}


def _item_view(item: EvidenceItem) -> EvidenceItemView:
    return EvidenceItemView(
        id=str(item.id),
        workspace_id=str(item.workspace_id),
        decision_case_id=str(item.decision_case_id),
        analysis_run_id=str(item.analysis_run_id),
        title=item.title,
        url=item.url,
        file_path=item.file_path,
        source_domain=item.source_domain,
        source_grade=item.source_grade,
        snippet=item.snippet,
        source_record_id=str(item.source_record_id),
        source_span_ids=list(item.source_span_ids),
        supports_claim_ids=list(item.supports_claim_ids),
        contradicts_claim_ids=list(item.contradicts_claim_ids),
        published_at=item.published_at,
        retrieved_at=item.retrieved_at,
        freshness_status=item.freshness_status,
        relevance=item.relevance,
        bias=item.bias,
        conflict_group_id=str(item.conflict_group_id) if item.conflict_group_id else None,
        independent_source_group_id=(
            str(item.independent_source_group_id)
            if item.independent_source_group_id
            else None
        ),
        verdict=item.verdict,
        verdict_reason_codes=list(item.verdict_reason_codes),
        applicability_limits=list(item.applicability_limits),
        origin_mode=item.origin_mode,
        raw_artifact_id=str(item.raw_artifact_id),
        quality_assessment_id=str(item.quality_assessment_id),
    )


def _quality_view(assessment: QualityAssessment) -> QualityDimensionsView:
    return QualityDimensionsView(
        authenticity=assessment.authenticity,
        source_quality=assessment.source_quality,
        relevance=assessment.relevance,
        freshness=assessment.freshness,
        applicability=assessment.applicability,
        independence=assessment.independence,
        extraction_reliability=assessment.extraction_reliability,
        bias_flags=list(assessment.bias_flags),
        completeness_warnings=list(assessment.completeness_warnings),
        conflict_group_ids=list(assessment.conflict_group_ids),
        verdict=assessment.verdict,
        reason_codes=list(assessment.reason_codes),
        assessed_at=assessment.assessed_at,
    )


def _raw_artifact_view(artifact: RawArtifact) -> RawArtifactView:
    return RawArtifactView(
        id=str(artifact.id),
        kind=artifact.kind,
        media_type=artifact.media_type,
        byte_size=artifact.byte_size,
        sha256=artifact.sha256,
        source_url=artifact.source_url,
        origin_mode=artifact.origin_mode,
        created_at=artifact.created_at,
    )


def _source_record_view(
    record: SourceRecord, spans: list[SourceSpan]
) -> SourceRecordView:
    return SourceRecordView(
        id=str(record.id),
        kind=record.kind.value,
        source_scope=record.source_scope.value,
        canonical_uri=record.canonical_uri,
        title=record.title,
        content_hash=record.content_hash,
        source_version=record.source_version,
        origin_mode=record.origin_mode,
        raw_artifact_id=str(record.raw_artifact_id) if record.raw_artifact_id else None,
        spans=[
            SourceSpanView(
                id=str(span.id),
                locator=dict(span.locator),
                quote=span.quote,
                quote_hash=span.quote_hash,
            )
            for span in spans
        ],
    )


async def _require_item(
    repo: EvidenceReadRepository, workspace_id: UUID, evidence_item_id: UUID
) -> EvidenceItem:
    item = await repo.get_evidence_item(workspace_id, evidence_item_id)
    if item is None:
        raise case_not_found()
    return item


@router.get("/evidence/{evidenceItemId}")
async def get_evidence_detail(
    evidence_item_id: UUID = Path(alias="evidenceItemId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    repo = EvidenceReadRepository(db)
    item = await _require_item(repo, context.workspace_id, evidence_item_id)
    return _envelope(_item_view(item).model_dump(by_alias=True))


@router.get("/evidence/{evidenceItemId}/quality")
async def get_evidence_quality(
    evidence_item_id: UUID = Path(alias="evidenceItemId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    repo = EvidenceReadRepository(db)
    item = await _require_item(repo, context.workspace_id, evidence_item_id)
    assessment = await repo.get_quality_assessment(
        context.workspace_id, item.quality_assessment_id
    )
    if assessment is None:
        raise case_not_found()
    return _envelope(_quality_view(assessment).model_dump(by_alias=True))


@router.get("/evidence/{evidenceItemId}/provenance")
async def get_evidence_provenance(
    evidence_item_id: UUID = Path(alias="evidenceItemId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    repo = EvidenceReadRepository(db)
    item = await _require_item(repo, context.workspace_id, evidence_item_id)
    artifact = await repo.get_raw_artifact(context.workspace_id, item.raw_artifact_id)
    record = await repo.get_source_record(context.workspace_id, item.source_record_id)
    assessment = await repo.get_quality_assessment(
        context.workspace_id, item.quality_assessment_id
    )
    if artifact is None or record is None or assessment is None:
        raise case_not_found()
    spans = await repo.list_source_spans(context.workspace_id, record.id)
    view = EvidenceProvenanceView(
        evidence_item_id=str(item.id),
        raw_artifact=_raw_artifact_view(artifact),
        source_record=_source_record_view(record, spans),
        quality=_quality_view(assessment),
    )
    return _envelope(view.model_dump(by_alias=True))


@router.get("/evidence/{evidenceItemId}/direction")
async def get_evidence_direction(
    evidence_item_id: UUID = Path(alias="evidenceItemId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    repo = EvidenceReadRepository(db)
    item = await _require_item(repo, context.workspace_id, evidence_item_id)
    view = EvidenceDirectionView(
        evidence_item_id=str(item.id),
        supports_claim_ids=list(item.supports_claim_ids),
        contradicts_claim_ids=list(item.contradicts_claim_ids),
        verdict=item.verdict,
    )
    return _envelope(view.model_dump(by_alias=True))


@router.get("/evidence/{evidenceItemId}/same-source-group")
async def get_same_source_group(
    evidence_item_id: UUID = Path(alias="evidenceItemId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    repo = EvidenceReadRepository(db)
    item = await _require_item(repo, context.workspace_id, evidence_item_id)
    members = await repo.list_same_source_group(context.workspace_id, item)
    view = SameSourceGroupView(
        independent_source_group_id=(
            str(item.independent_source_group_id)
            if item.independent_source_group_id
            else None
        ),
        member_evidence_item_ids=[str(member.id) for member in members],
        independent_source_count_contribution=1,
    )
    return _envelope(view.model_dump(by_alias=True))


@router.get("/analyses/{analysisRunId}/evidence")
async def list_run_evidence(
    analysis_run_id: UUID = Path(alias="analysisRunId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    repo = EvidenceReadRepository(db)
    if not await repo.run_exists(context.workspace_id, analysis_run_id):
        raise case_not_found()
    items = await repo.list_run_evidence(context.workspace_id, analysis_run_id)
    # Grey-goo 原则⑩ read-model projection: the run's real evidence set is
    # the funnel-admitted research packets (persisted by the worker). Project
    # them so the E page is honest even before the ingest chain exists.
    from sqlalchemy import select as _select

    from app.analyses.models import ResearchPacket as _PacketRow

    packet_rows = (
        await db.execute(
            _select(_PacketRow)
            .where(
                _PacketRow.workspace_id == context.workspace_id,
                _PacketRow.analysis_run_id == analysis_run_id,
            )
            .order_by(_PacketRow.created_at, _PacketRow.id)
        )
    ).scalars().all()
    view = RunEvidenceListView(
        analysis_run_id=str(analysis_run_id),
        items=[_item_view(item) for item in items],
        packet_evidence=[
            PacketEvidenceView(
                packet_id=str(row.id),
                factor=row.factor,
                direction=row.direction,
                conclusion=row.conclusion,
                claim_support_score=float(row.claim_support_score),
                evidence_ids=list(row.evidence_ids or []),
                role=str(row.role),
            )
            for row in packet_rows
        ],
    )
    # Grey-goo 原则⑩ (CCR-20260802-P2W2): the persisted TDD funnel audit
    # (discards with factor/reason/check, warnings, tier mix) rides the same
    # response so the E page can show "what was filtered out and why".
    # Latest stage wins; absent audit -> None (honest empty, never fabricated).
    data = view.model_dump(by_alias=True)
    funnel_audit = await _latest_funnel_audit(db, context.workspace_id, analysis_run_id)
    if funnel_audit is not None:
        data["funnelAudit"] = funnel_audit
    return _envelope(data)


async def _latest_funnel_audit(
    db: AsyncSession, workspace_id: UUID, analysis_run_id: UUID
) -> dict[str, object] | None:
    """The most recent persisted funnel audit for this run (principle ⑩)."""

    from sqlalchemy import select

    from app.models import EvidenceFunnelAudit

    row = (
        await db.execute(
            select(EvidenceFunnelAudit)
            .where(
                EvidenceFunnelAudit.workspace_id == workspace_id,
                EvidenceFunnelAudit.analysis_run_id == analysis_run_id,
            )
            .order_by(EvidenceFunnelAudit.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return {
        "stage": row.stage,
        "admitted": row.admitted,
        "discarded": list(row.discarded),
        "warnings": list(row.warnings),
        "tierCounts": dict(row.tier_counts),
        "opposingCount": row.opposing_count,
        "lowTierShare": float(row.low_tier_share) if row.low_tier_share is not None else None,
    }


@router.get("/analyses/{analysisRunId}/evidence-conflicts")
async def list_run_conflicts(
    analysis_run_id: UUID = Path(alias="analysisRunId"),
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    repo = EvidenceReadRepository(db)
    if not await repo.run_exists(context.workspace_id, analysis_run_id):
        raise case_not_found()
    relations = await repo.list_conflict_relations(context.workspace_id, analysis_run_id)
    view = ConflictListView(
        analysis_run_id=str(analysis_run_id),
        conflicts=[
            ConflictRelationView(
                id=str(relation.id),
                from_evidence_item_id=str(relation.from_evidence_item_id),
                to_evidence_item_id=str(relation.to_evidence_item_id),
                group_id=str(relation.group_id) if relation.group_id else None,
                rationale=relation.rationale,
            )
            for relation in relations
        ],
    )
    return _envelope(view.model_dump(by_alias=True))
