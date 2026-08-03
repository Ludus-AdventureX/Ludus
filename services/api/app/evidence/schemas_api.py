"""Wire DTOs for the unmounted evidence provenance/conflict query layer.

Strict camelCase ``CanonicalModel`` views (SIM-02A ``schemas_api`` precedent).
The canonical SourceRecord/SourceSpan wire unions stay in
``app/evidence/schemas.py`` (contract repair lane) and are not redefined
here. These endpoints are not in 10-api-and-events.md yet: the router is
deliberately NOT mounted and the exact public paths await a CCR (recorded in
the Task 8 handoff), so none of these shapes reach the generated contracts.
"""

from __future__ import annotations

from datetime import datetime

from app.contracts.schemas import CanonicalModel, Identifier, NonEmptyText
from app.types import EvidenceVerdict, OriginMode


class QualityDimensionsView(CanonicalModel):
    authenticity: float
    source_quality: float
    relevance: float
    freshness: float
    applicability: float
    independence: float
    extraction_reliability: float
    bias_flags: list[str]
    completeness_warnings: list[str]
    conflict_group_ids: list[str]
    verdict: EvidenceVerdict
    reason_codes: list[str]
    assessed_at: datetime


class EvidenceItemView(CanonicalModel):
    id: Identifier
    workspace_id: Identifier
    decision_case_id: Identifier
    analysis_run_id: Identifier
    title: NonEmptyText
    url: str | None = None
    file_path: str | None = None
    source_domain: str | None = None
    source_grade: NonEmptyText
    snippet: NonEmptyText
    source_record_id: Identifier
    source_span_ids: list[str]
    supports_claim_ids: list[str]
    contradicts_claim_ids: list[str]
    published_at: datetime | None = None
    retrieved_at: datetime
    freshness_status: NonEmptyText
    relevance: float
    bias: str | None = None
    conflict_group_id: str | None = None
    independent_source_group_id: str | None = None
    verdict: EvidenceVerdict
    verdict_reason_codes: list[str]
    applicability_limits: list[str]
    origin_mode: OriginMode
    raw_artifact_id: Identifier
    quality_assessment_id: Identifier


class RawArtifactView(CanonicalModel):
    """RawArtifact metadata; storage pointer style, no absolute path, no body."""

    id: Identifier
    kind: NonEmptyText
    media_type: NonEmptyText
    byte_size: int
    sha256: NonEmptyText
    source_url: str | None = None
    origin_mode: OriginMode
    created_at: datetime


class SourceSpanView(CanonicalModel):
    id: Identifier
    locator: dict[str, object]
    quote: NonEmptyText
    quote_hash: NonEmptyText


class SourceRecordView(CanonicalModel):
    id: Identifier
    kind: NonEmptyText
    source_scope: NonEmptyText
    canonical_uri: NonEmptyText
    title: NonEmptyText
    content_hash: NonEmptyText
    source_version: NonEmptyText
    origin_mode: OriginMode
    raw_artifact_id: str | None = None
    spans: list[SourceSpanView]


class EvidenceProvenanceView(CanonicalModel):
    """Full traceability chain slice for one evidence item."""

    evidence_item_id: Identifier
    raw_artifact: RawArtifactView
    source_record: SourceRecordView
    quality: QualityDimensionsView


class EvidenceDirectionView(CanonicalModel):
    """Supporting/opposing projection of one evidence item."""

    evidence_item_id: Identifier
    supports_claim_ids: list[str]
    contradicts_claim_ids: list[str]
    verdict: EvidenceVerdict


class SameSourceGroupView(CanonicalModel):
    independent_source_group_id: str | None = None
    member_evidence_item_ids: list[str]
    independent_source_count_contribution: int


class ConflictRelationView(CanonicalModel):
    id: Identifier
    from_evidence_item_id: Identifier
    to_evidence_item_id: Identifier
    group_id: str | None = None
    rationale: str | None = None


class PacketEvidenceView(CanonicalModel):
    """Read-model projection of one funnel-admitted research packet.

    The E page's evidence list used to be empty whenever the Task 11 ingest
    chain (RetrievalTask→RawArtifact→QualityAssessment→SourceRecord→
    EvidenceItem) had not run: the analysis worker persists admitted packets
    but never that chain. This projection makes the honest evidence set (the
    packets that actually fed the run) visible without fabricating ingest
    rows - ids carry the funnel-minted tier annotation verbatim.
    """

    packet_id: Identifier
    factor: str | None = None
    direction: str | None = None
    conclusion: NonEmptyText
    claim_support_score: float
    evidence_ids: list[str]
    role: NonEmptyText


class RunEvidenceListView(CanonicalModel):
    analysis_run_id: Identifier
    items: list[EvidenceItemView]
    # Additive: packet projection rides alongside the ingest-chain items so the
    # E page shows the run's real evidence set even before ingest rows exist.
    packet_evidence: list[PacketEvidenceView] = []


class ConflictListView(CanonicalModel):
    analysis_run_id: Identifier
    conflicts: list[ConflictRelationView]
