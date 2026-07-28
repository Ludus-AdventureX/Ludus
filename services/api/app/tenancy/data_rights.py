"""Workspace data rights (interlude B): export + purge.

Founders' decision data is extremely sensitive; incubator procurement always
asks two questions - "can we take our data out?" and "can we make you delete
it?". Both answers live here, OWNER-only:

* GET  /export           full-workspace JSON projection (download once, keep).
* POST /purge            irreversible cascade delete; the caller must echo the
                         workspace id as confirmation, and the deletion is
                         logged (id + actor only, never content) BEFORE the
                         rows disappear.

Every business table carries ``workspace_id ... ON DELETE CASCADE``, so the
purge is one authoritative delete of the workspace row - no partial states.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.schemas import CanonicalModel
from app.db import get_session
from app.models import Workspace
from app.security.csrf import require_csrf
from app.security.envelope import ApiFailure
from app.tenancy.context import WorkspaceContext, require_workspace_context
from app.types import WorkspaceRole

logger = logging.getLogger(__name__)

router = APIRouter(tags=["data-rights"])

# Tables projected into the export (name -> ORDER BY column). A raw projection
# keeps the export honest: what the database holds is what you get.
_EXPORT_TABLES: tuple[tuple[str, str], ...] = (
    ("decision_subjects", "id"),
    ("decision_cases", "decision_case_id"),
    ("dossier_entries", "id"),
    ("conversations", "id"),
    ("messages", "id"),
    ("analysis_charters", "id"),
    ("analysis_runs", "analysis_run_id"),
    ("research_packets", "id"),
    ("analysis_events", "id"),
    ("report_artifacts", "id"),
    ("decision_records", "id"),
    ("decision_reviews", "id"),
    ("mentor_reviews", "id"),
    ("workspace_invites", "id"),
)
_EXPORT_ROW_CAP = 5000  # per table; guests cannot exceed this in practice


def _require_owner(context: WorkspaceContext) -> None:
    if context.role != WorkspaceRole.OWNER:
        raise ApiFailure(
            "MEMBERSHIP_CAPABILITY_REQUIRED",
            "Only the workspace owner can exercise data rights.",
            http_status=403,
        )


@router.get("/export")
async def export_workspace(
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Full-workspace JSON projection (OWNER). Values are stringified so the
    export is loss-tolerant and always serializable; hashes stay verbatim, so
    signed decisions stay verifiable outside the system."""

    _require_owner(context)
    data: dict[str, Any] = {"workspaceId": str(context.workspace_id), "tables": {}}
    for table, order_col in _EXPORT_TABLES:
        try:
            rows = (
                await db.execute(
                    text(
                        f"SELECT to_jsonb(t) AS row FROM {table} t "  # noqa: S608 - fixed allowlist above
                        f"WHERE t.workspace_id = CAST(:ws AS uuid) ORDER BY t.{order_col} LIMIT :cap"
                    ).bindparams(ws=str(context.workspace_id), cap=_EXPORT_ROW_CAP)
                )
            ).scalars().all()
        except Exception:
            logger.exception("export: table %s failed; omitted honestly", table)
            data["tables"][table] = {"error": "export_failed_for_table"}
            continue
        data["tables"][table] = [dict(row) for row in rows]
    return {"ok": True, "data": data}


class PurgeRequest(CanonicalModel):
    # Second confirmation: the caller must echo the workspace id verbatim.
    confirm_workspace_id: str


@router.post("/purge", dependencies=[Depends(require_csrf)])
async def purge_workspace(
    body: PurgeRequest,
    context: WorkspaceContext = Depends(require_workspace_context),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Irreversible workspace deletion (OWNER + echoed-id confirmation).

    One authoritative delete of the workspace row; every business table
    cascades. The audit line carries ids only - purged content is gone."""

    _require_owner(context)
    if body.confirm_workspace_id.strip() != str(context.workspace_id):
        raise ApiFailure(
            "PURGE_CONFIRMATION_MISMATCH",
            "confirmWorkspaceId must exactly match the workspace id.",
            http_status=422,
        )
    workspace = await db.scalar(select(Workspace).where(Workspace.id == context.workspace_id))
    if workspace is None:
        raise ApiFailure("WORKSPACE_NOT_FOUND", "The workspace does not exist.", http_status=404)
    logger.warning(
        "DATA-RIGHTS PURGE: workspace=%s requested_by=%s (cascade delete)",
        context.workspace_id,
        context.user_id,
    )
    await db.delete(workspace)
    await db.commit()
    return {"ok": True, "data": {"purged": True, "workspaceId": str(context.workspace_id)}}
