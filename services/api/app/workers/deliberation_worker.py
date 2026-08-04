"""Deliberation council worker step (CCR-20260804-DELIB-01).

The council orchestrator is a worker-side job kind reusing the durable queue
discipline (FOR UPDATE SKIP LOCKED claim, one step per iteration, commit at
the boundary so SSE sees progress). It runs inside the same analysis worker
process: when the analysis queue is idle, one actionable deliberation run is
claimed and advanced by at most one round.

Model execution comes from the same environment seam as analysis
(``FIXTURE_MODE=true`` -> deterministic fixture witnesses/moderator; otherwise
the locked ModelProvider with strict structured schemas).
"""

from __future__ import annotations

import logging
import os
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.model_provider import build_model_provider_from_env
from app.deliberation.orchestrator import DeliberationOrchestrator
from app.deliberation.repository import DeliberationRepository
from app.deliberation.service import load_case_basis
from app.types import OriginMode

log = logging.getLogger("app.workers.deliberation")


def _deliberation_origin_mode() -> OriginMode:
    return OriginMode.FIXTURE if os.getenv("FIXTURE_MODE", "false").lower() == "true" else OriginMode.LIVE


async def advance_one_deliberation(session: AsyncSession) -> UUID | None:
    """Claim one actionable deliberation run and advance it by one step.

    Returns the claimed run id (None when the queue is empty). Commits at the
    boundary so every persisted message/proposal/event is SSE-visible
    immediately; a failure rolls back only this step and leaves the run in its
    previous honest state.
    """

    repo = DeliberationRepository(session)
    run = await repo.claim_next_actionable()
    if run is None:
        return None

    workspace_id = run.workspace_id
    run_id = run.id
    decision_case_id = run.decision_case_id
    origin_mode = _deliberation_origin_mode()
    provider = None if origin_mode is OriginMode.FIXTURE else build_model_provider_from_env()

    packets, influences = await load_case_basis(session, workspace_id, decision_case_id)
    orchestrator = DeliberationOrchestrator(
        repo, provider=provider, origin_mode=origin_mode
    )
    new_status = await orchestrator.advance(
        workspace_id, run_id, packets=packets, influences=influences
    )
    await session.commit()
    log.info(
        "deliberation run %s advanced -> %s (origin_mode=%s)",
        run_id,
        new_status.value,
        origin_mode.value,
    )
    return run_id
