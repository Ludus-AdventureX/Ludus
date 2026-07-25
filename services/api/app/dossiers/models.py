"""Supplementary dossier table owned by this lane (Task 4).

The canonical dossier tables (``dossier_entries``, ``dossier_versions``,
``candidate_revisions``, ``case_versions``) are frozen in ``app/models.py``
(Task 19A migration ``6b246c283d7a``) and are REUSED, not redefined, here.

This module adds only the immutable snapshot *detail* row required by the
Task 4 charter: per included entry the frozen entry id, entry version,
statement type, scope and content hash, plus the decision-maker profile
version and subject version pinned at snapshot time. Later entry edits never
touch these rows.

Migration discipline: the Alembic revision for this table is deferred until
Task 10's ``0004`` migration lands; tests materialise it from this metadata.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import created_at_column, json_list_column, uuid_primary_key, workspace_column


class DossierVersionSnapshot(Base):
    """Immutable per-version snapshot detail (write-once companion row)."""

    __tablename__ = "dossier_version_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "dossier_version_id",
            name="uq_dossier_version_snapshots_version",
        ),
    )

    id: Mapped[UUID] = uuid_primary_key()
    workspace_id: Mapped[UUID] = workspace_column()
    dossier_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("dossier_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    # [{entryId, entryVersion, statementType, scope, contentHash}, ...]
    entries: Mapped[list[dict[str, Any]]] = json_list_column()
    decision_maker_profile_version: Mapped[int | None] = mapped_column(Integer)
    subject_version: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = created_at_column()
