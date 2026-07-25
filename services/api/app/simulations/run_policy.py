"""Minimal-contract run policy for the SIM-02A run route (CCR-20260724-SIM-02A §7/§9).

Three concerns live here so the route handler stays thin:

- per (workspace, user) POST rate limiting — frozen default 10 runs / 5 minutes,
  reusing the shipped fail-closed sliding-window pattern and the migrated
  ``login_rate_buckets`` store under a dedicated ``simrun`` digest dimension (a
  dedicated table is a later, non-blocking migration; keys never collide because
  the dimension prefix enters the SHA-256 digest);
- synchronous execution budget — ``maxSteps ≤ 64`` is schema-enforced, the graph
  size guard (≤ 500 nodes / 2000 edges) is checked after load and BEFORE any
  engine work, failing closed with 422 ``SIMULATION_BUDGET_EXCEEDED``;
- terminal status ruling (§7): formal non-converged runs persist and answer 409,
  everything else answers 201.

Rate limiting and idempotency stay independent: a 429 never consumes an
Idempotency-Key, and replays still pass the limiter.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.security.envelope import ApiFailure
from app.security.rate_limits import login_rate_buckets
from app.types import SimulationConvergenceStatus, SimulationMode

from .errors import StrategyOverrideError
from .idempotency import RESPONSE_KIND_NON_CONVERGED, RESPONSE_KIND_SUCCESS
from .repository import SimulationInputRepository

# Frozen §9 defaults; module-level so tests and settings wiring can tune them.
RUN_RATE_WINDOW_MINUTES = 5
RUN_RATE_MAX_ATTEMPTS = 10
MAX_GRAPH_NODES = 500
MAX_GRAPH_EDGES = 2000


def budget_exceeded(dimension: str) -> ApiFailure:
    """422 with only the offending budget dimension (§8); no sizes are echoed."""

    return ApiFailure(
        "SIMULATION_BUDGET_EXCEEDED",
        "The simulation exceeds the synchronous execution budget.",
        http_status=422,
        details={"budget": dimension},
    )


def _run_rate_limited(retry_after_seconds: int) -> ApiFailure:
    return ApiFailure(
        "REQUEST_RATE_LIMITED",
        "Too many simulation runs. Retry later.",
        http_status=429,
        retryable=True,
        details={"retryAfterSeconds": retry_after_seconds},
    )


def run_rate_key(workspace_id: UUID, user_id: UUID) -> str:
    """SHA-256 digest of the (workspace, user) dimension; raw ids never enter the store."""

    return hashlib.sha256(f"simrun:{workspace_id}:{user_id}".encode()).hexdigest()


class SimulationRunRateLimiter:
    """Sliding-window limiter over minute slices; storage failure fails CLOSED."""

    @property
    def _window(self) -> timedelta:
        return timedelta(minutes=RUN_RATE_WINDOW_MINUTES)

    async def check_run_attempt(
        self, db: AsyncSession, *, workspace_id: UUID, user_id: UUID
    ) -> None:
        """Meter one POST attempt; raise REQUEST_RATE_LIMITED when over limit."""

        now = datetime.now(timezone.utc)
        bucket_key = run_rate_key(workspace_id, user_id)
        retry_after = max(int(self._window.total_seconds()), 60)
        try:
            upsert = (
                pg_insert(login_rate_buckets)
                .values(
                    bucket_key=bucket_key,
                    slice_start=now.replace(second=0, microsecond=0),
                    attempts=1,
                )
                .on_conflict_do_update(
                    index_elements=["bucket_key", "slice_start"],
                    set_={"attempts": login_rate_buckets.c.attempts + 1},
                )
            )
            await db.execute(upsert)
            total = await db.scalar(
                select(func.coalesce(func.sum(login_rate_buckets.c.attempts), 0)).where(
                    login_rate_buckets.c.bucket_key == bucket_key,
                    login_rate_buckets.c.slice_start > now - self._window,
                )
            )
            await db.commit()
        except ApiFailure:
            raise
        except Exception:
            # An unmetered run path must not exist.
            try:
                await db.rollback()
            except Exception:
                pass
            raise _run_rate_limited(retry_after) from None

        if int(total or 0) > RUN_RATE_MAX_ATTEMPTS:
            raise _run_rate_limited(retry_after)


def enforce_formal_overrides(
    mode: SimulationMode, node_overrides: dict[str, float]
) -> None:
    """§5.7: formal replay authority lives in frozen StrategyVersions only."""

    if mode == SimulationMode.FORMAL and node_overrides:
        raise StrategyOverrideError(
            "run-level nodeOverrides must be empty on a formal run"
        )


async def enforce_graph_budget(
    repository: SimulationInputRepository, workspace_id: UUID, graph_version_id: UUID
) -> None:
    """Graph size guard, checked after load and before any engine work (§9)."""

    nodes = await repository.count_graph_nodes(workspace_id, graph_version_id)
    if nodes > MAX_GRAPH_NODES:
        raise budget_exceeded("graphNodes")
    edges = await repository.count_graph_edges(workspace_id, graph_version_id)
    if edges > MAX_GRAPH_EDGES:
        raise budget_exceeded("graphEdges")


def terminal_run_status(
    mode: SimulationMode, convergence_status: SimulationConvergenceStatus
) -> tuple[int, str]:
    """§7 ruling: (http_status, response_kind) for one freshly persisted run."""

    if (
        mode == SimulationMode.FORMAL
        and convergence_status != SimulationConvergenceStatus.CONVERGED
    ):
        return 409, RESPONSE_KIND_NON_CONVERGED
    return 201, RESPONSE_KIND_SUCCESS


def simulation_not_converged(
    simulation_run_id: UUID, convergence_status: SimulationConvergenceStatus
) -> ApiFailure:
    """409 for a persisted-but-non-converged formal run; details stay tenant-safe."""

    return ApiFailure(
        "SIMULATION_NOT_CONVERGED",
        "The formal simulation run did not converge. The run was persisted for audit.",
        http_status=409,
        details={
            "simulationRunId": str(simulation_run_id),
            "convergenceStatus": convergence_status.value,
        },
    )
