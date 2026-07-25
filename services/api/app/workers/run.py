"""Production analysis-worker entrypoint: ``python -m app.workers.run``.

Polls the durable DB queue (``claim_next_queued`` = FOR UPDATE SKIP LOCKED)
and fully processes one run per iteration through :class:`AnalysisWorker`.
Model execution comes from the environment seam only
(``MODEL_PROVIDER=deepseek`` live, or ``FIXTURE_MODE=true`` deterministic
fixture origin) — nothing vendor-specific is hard-coded here.

Transaction ownership: the repository layer never commits; this runner owns
the session and commits once after ``run_once`` returns. On an unexpected
executor/persistence failure the claimed transaction is rolled back (the run
returns to ``queued``); the runner then re-claims the queue head in a FRESH
session (queued -> planning, the canonical claim transition) and parks it
``planning -> needs_attention`` so a poison run cannot wedge the queue head
forever; operators resume it through the shipped resolution/resume API.
Cancellation is already handled inside the worker (CooperativeStop) and
needs nothing here.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from uuid import UUID

from app.db import async_session_factory
from app.types import AnalysisRunStatus
from app.workers.analysis_worker import AnalysisWorker, build_role_executors_from_env

log = logging.getLogger("app.workers.run")


def _poll_interval() -> float:
    return float(os.getenv("WORKER_POLL_INTERVAL_SECONDS", "2.0"))


async def _park_queue_head() -> None:
    """Best-effort poison-run parking in a fresh session (fresh transaction).

    After the failed transaction rolled back, the failing run is back at the
    queue head (claim takes the oldest queued run). Re-claim it with the
    canonical locked transition (queued -> planning) and park it
    planning -> needs_attention; both edges are legal in the state machine.
    Single-worker deployment: the re-claimed head is the run that just failed.
    """

    from app.analyses.repository import AnalysisRuntimeRepository

    try:
        async with async_session_factory() as session:
            repo = AnalysisRuntimeRepository(session)
            run = await repo.claim_next_queued()
            if run is None:
                return
            await repo.transition(
                run.workspace_id,
                run.analysis_run_id,
                AnalysisRunStatus.NEEDS_ATTENTION,
                payload={"reason": "worker_execution_error"},
            )
            await session.commit()
            log.warning(
                "run %s parked needs_attention after worker failure",
                run.analysis_run_id,
            )
    except Exception:
        log.exception("could not park the failed run; it stays queued")


async def main() -> None:
    logging.basicConfig(
        level=os.getenv("WORKER_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    executors, origin_mode = build_role_executors_from_env()
    log.info(
        "analysis worker starting (origin_mode=%s, poll=%.1fs)",
        origin_mode.value,
        _poll_interval(),
    )

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # pragma: no cover - Windows dev shells
            signal.signal(sig, lambda *_: stop.set())

    while not stop.is_set():
        claimed: UUID | None = None
        try:
            async with async_session_factory() as session:
                worker = AnalysisWorker(
                    session, executors=executors, origin_mode=origin_mode
                )
                claimed = await worker.run_once()
                if claimed is not None:
                    await session.commit()
        except Exception:
            log.exception("worker iteration failed; rolled back, parking the queue head")
            await _park_queue_head()
        else:
            if claimed is not None:
                log.info("processed analysis run %s", claimed)
                continue  # drain the queue without sleeping
        try:
            await asyncio.wait_for(stop.wait(), timeout=_poll_interval())
        except (TimeoutError, asyncio.TimeoutError):
            pass

    log.info("analysis worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
