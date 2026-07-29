"""Production analysis-worker entrypoint: ``python -m app.workers.run``.

Polls the durable DB queue (``claim_next_queued`` = FOR UPDATE SKIP LOCKED)
and fully processes one run per iteration through :class:`AnalysisWorker`.
Model execution comes from the environment seam only
(``MODEL_PROVIDER=deepseek`` live, or ``FIXTURE_MODE=true`` deterministic
fixture origin) — nothing vendor-specific is hard-coded here.

Transaction ownership: the repository layer never commits, but the WORKER now
commits at every stage boundary (``AnalysisWorker._checkpoint``). A run used to
advance inside one long transaction, which made its status, progress, heartbeat
and events invisible until it finished — a run five minutes and six model calls
deep still read ``queued / progress 0`` through the API. This runner therefore
owns the session but no longer owns the run's visibility; its final commit is
just a no-op backstop for anything written after the last boundary.

On an unexpected executor/persistence failure the current (partial) stage rolls
back and the runner parks EXACTLY the run it claimed, in place, from whatever
executing stage it reached — every ``executing -> needs_attention`` edge is
legal. Operators resume it through the shipped resolution/resume API.
Cancellation is already handled inside the worker (CooperativeStop) and needs
nothing here.
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


async def _park_run(workspace_id: UUID, analysis_run_id: UUID) -> None:
    """Park EXACTLY the failed run, in place, in a fresh session.

    Stage boundaries commit, so after the failed stage rolls back the run is
    still sitting in an executing stage (not back in ``queued``) and can be
    parked directly. The previous strategy re-claimed the queue head, which was
    only correct because the whole run lived in one transaction and therefore
    rolled back to ``queued``; with more than one queued run it could park an
    innocent run instead of the poison one.

    A run that reached a terminal state concurrently (e.g. cancelled) is left
    alone: the transition guard rejects it and that is the correct outcome.
    """

    from app.analyses.repository import AnalysisRuntimeRepository

    try:
        async with async_session_factory() as session:
            repo = AnalysisRuntimeRepository(session)
            await repo.transition(
                workspace_id,
                analysis_run_id,
                AnalysisRunStatus.NEEDS_ATTENTION,
                payload={"reason": "worker_execution_error"},
            )
            await session.commit()
            log.warning(
                "run %s parked needs_attention after worker failure",
                analysis_run_id,
            )
    except Exception:
        log.exception(
            "could not park run %s; it stays in its current stage", analysis_run_id
        )


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
        worker: AnalysisWorker | None = None
        try:
            async with async_session_factory() as session:
                worker = AnalysisWorker(
                    session, executors=executors, origin_mode=origin_mode
                )
                claimed = await worker.run_once()
                if claimed is not None:
                    await session.commit()
        except Exception:
            log.exception("worker iteration failed; parking the claimed run")
            target = worker.claimed if worker is not None else None
            if target is None:
                log.error("failure before any claim; nothing to park")
            else:
                await _park_run(*target)
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
