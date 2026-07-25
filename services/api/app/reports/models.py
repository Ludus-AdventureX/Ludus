"""Report and export artifacts (Task 10 Step 6-8, ways_agent_pipeline scope).

Canonical shapes: 06-data-model.md ``ReportArtifact`` / ``ExportArtifact``
plus the discriminant rule below the interfaces: ``focused`` implies
``type == "brief"`` with a ``FocusedResearchResult`` body and NO lens/PDF/
simulation artifacts; ``full`` implies ``type == "detailed"`` with a
``StructuredReport`` body and is the only level allowed to create HTML/PDF
``ExportArtifact`` rows. The server enforces this — never the frontend.

Immutability: a ``ready`` report row can never be UPDATEd or DELETEd. The
enforcement is double-layered — a database trigger (this batch's migration)
plus the repository-level rejection in ``app.analyses.synthesis``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final, Sequence
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import (
    ORIGIN_MODE_ENUM,
    created_at_column,
    enum_type,
    json_object_column,
    uuid_primary_key,
    workspace_column,
)
from app.types import FormalAnalysisLevel, OriginMode

# --- canonical literal sets (06-data-model.md) --------------------------------
# Status columns are PG enums with no parallel Python StrEnum (Task 9
# packet-role precedent): the decision-os invariants suite requires it.
REPORT_TYPES: Final[tuple[str, ...]] = ("brief", "detailed")
REPORT_STATUSES: Final[tuple[str, ...]] = ("draft", "ready")
EXPORT_TYPES: Final[tuple[str, ...]] = ("html", "pdf")
EXPORT_STATUSES: Final[tuple[str, ...]] = ("pending", "ready", "failed")
EXPORT_MEDIA_TYPES: Final[tuple[str, ...]] = ("text/html", "application/pdf")
EXPORT_STORAGE_PROVIDERS: Final[tuple[str, ...]] = ("filesystem",)

REPORT_ARTIFACT_STATUS_ENUM = SAEnum(
    *REPORT_STATUSES, name="report_artifact_status", native_enum=True
)
EXPORT_ARTIFACT_STATUS_ENUM = SAEnum(
    *EXPORT_STATUSES, name="export_artifact_status", native_enum=True
)


def _check_in(column: str, values: Sequence[str]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


class ReportArtifact(Base):
    """Formal analysis output container, one per qualifying Run."""

    __tablename__ = "report_artifacts"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_report_artifacts_workspace_id"),
        # One report per Run: the idempotency anchor (same content hash
        # replays the original row; a different hash is a conflict).
        UniqueConstraint(
            "workspace_id",
            "analysis_run_id",
            name="uq_report_artifacts_workspace_run",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id"],
            ["decision_cases.workspace_id", "decision_cases.decision_case_id"],
            name="fk_report_artifacts_workspace_case",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "analysis_run_id"],
            [
                "analysis_runs.workspace_id",
                "analysis_runs.decision_case_id",
                "analysis_runs.analysis_run_id",
            ],
            name="fk_report_artifacts_workspace_case_run",
            ondelete="CASCADE",
        ),
        CheckConstraint(_check_in("type", REPORT_TYPES), name="report_type_valid"),
        # 06 discriminant: focused -> brief; full -> detailed. Enforced in
        # the database so no service bug can cross the level/type pairing.
        CheckConstraint(
            "(analysis_level = 'focused' AND type = 'brief') "
            "OR (analysis_level = 'full' AND type = 'detailed')",
            name="report_level_type_discriminant",
        ),
        CheckConstraint("case_version > 0", name="report_case_version_positive"),
        CheckConstraint("content_hash <> ''", name="report_content_hash_not_empty"),
        # publishedAt is only writable together with ready status.
        CheckConstraint(
            "status = 'ready' OR published_at IS NULL",
            name="report_published_requires_ready",
        ),
        Index("ix_report_artifacts_workspace_case", "workspace_id", "decision_case_id"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    analysis_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_judgment_set_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_dissent_record_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    case_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    analysis_level: Mapped[FormalAnalysisLevel] = mapped_column(
        enum_type(FormalAnalysisLevel, "formal_analysis_level"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        REPORT_ARTIFACT_STATUS_ENUM, nullable=False, default="draft", server_default="draft"
    )
    # FocusedResearchResult | StructuredReport as one canonical JSON document.
    structured_content: Mapped[dict[str, Any]] = json_object_column()
    content_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    origin_modes: Mapped[list[OriginMode]] = mapped_column(
        ARRAY(ORIGIN_MODE_ENUM),
        nullable=False,
        default=list,
    )
    # ReportValidation witness (passed/errors/warnings/checkedAt).
    validation: Mapped[dict[str, Any]] = json_object_column()
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()


class ExportArtifact(Base):
    """HTML/PDF rendering of one ready full report."""

    __tablename__ = "export_artifacts"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_export_artifacts_workspace_id"),
        ForeignKeyConstraint(
            ["workspace_id", "report_artifact_id"],
            ["report_artifacts.workspace_id", "report_artifacts.id"],
            name="fk_export_artifacts_workspace_report",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "analysis_run_id"],
            [
                "analysis_runs.workspace_id",
                "analysis_runs.decision_case_id",
                "analysis_runs.analysis_run_id",
            ],
            name="fk_export_artifacts_workspace_case_run",
            ondelete="CASCADE",
        ),
        CheckConstraint(_check_in("type", EXPORT_TYPES), name="export_type_valid"),
        CheckConstraint(
            _check_in("media_type", EXPORT_MEDIA_TYPES), name="export_media_type_valid"
        ),
        CheckConstraint(
            _check_in("storage_provider", EXPORT_STORAGE_PROVIDERS),
            name="export_storage_provider_valid",
        ),
        CheckConstraint(
            "(type = 'html' AND media_type = 'text/html') "
            "OR (type = 'pdf' AND media_type = 'application/pdf')",
            name="export_type_media_pairing",
        ),
        CheckConstraint("case_version > 0", name="export_case_version_positive"),
        Index("ix_export_artifacts_workspace_report", "workspace_id", "report_artifact_id"),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    report_artifact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    analysis_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    decision_case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    case_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    type: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(
        EXPORT_ARTIFACT_STATUS_ENUM, nullable=False, default="pending", server_default="pending"
    )
    storage_provider: Mapped[str] = mapped_column(
        String(32), nullable=False, default="filesystem", server_default="filesystem"
    )
    storage_path: Mapped[str | None] = mapped_column(String(1024))
    sha256: Mapped[str | None] = mapped_column(String(64))
    byte_size: Mapped[int | None] = mapped_column(BigInteger)
    media_type: Mapped[str] = mapped_column(String(64), nullable=False)
    renderer_version: Mapped[str] = mapped_column(String(64), nullable=False)
    origin_modes: Mapped[list[OriginMode]] = mapped_column(
        ARRAY(ORIGIN_MODE_ENUM),
        nullable=False,
        default=list,
    )
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = created_at_column()
