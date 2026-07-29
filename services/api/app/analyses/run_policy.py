"""Cost policy for the deep-analysis run route (alpha gate).

A formal run is the most expensive action in the product: one focused run makes
~8 model calls plus bounded web retrieval and takes minutes. Until now the route
had NO metering at all, while the far cheaper pure-computation simulation run
route did (``app/simulations/run_policy.py``). AGENTS.md section 11 requires
Postgres-backed per-user/per-workspace limits and size budgets for "login, high
cost Run, connectors and uploads" — this closes the high-cost-Run half, which is
a precondition for exposing the app to anyone outside the machine that runs it.

Two independent dimensions, both fail-closed:

- per (workspace, user) burst: 5 runs / 60 minutes — one person cannot queue a
  wall of runs;
- per workspace rolling day: 20 runs / 24 hours — one tenant (including a guest
  workspace) cannot drain the model/retrieval budget of the whole deployment.

Storage reuses the migrated ``login_rate_buckets`` sliding-window table under
dedicated digest dimensions, exactly as the simulation limiter does: the
dimension prefix enters the SHA-256 digest, so keys can never collide and no
raw workspace/user id is written to the limiter store. A dedicated table is a
later, non-blocking migration.

Rate limiting stays independent of idempotency: a 429 never consumes an
Idempotency-Key, and a replay of an accepted key still passes the limiter.
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

# Frozen alpha defaults; module-level so tests and later settings wiring can
# tune them without touching the route.
RUN_BURST_WINDOW_MINUTES = 60
RUN_BURST_MAX_ATTEMPTS = 5
RUN_DAILY_WINDOW_MINUTES = 24 * 60
RUN_DAILY_MAX_ATTEMPTS = 20


def _rate_limited(retry_after_seconds: int, dimension: str) -> ApiFailure:
    """429 naming only the exhausted dimension; no counts or ids are echoed."""

    return ApiFailure(
        "REQUEST_RATE_LIMITED",
        "Too many analysis runs. Retry later.",
        http_status=429,
        retryable=True,
        details={"retryAfterSeconds": retry_after_seconds, "limit": dimension},
    )


def run_burst_key(workspace_id: UUID, user_id: UUID) -> str:
    """SHA-256 digest of the (workspace, user) dimension; raw ids never stored."""

    return hashlib.sha256(f"analysisrun:{workspace_id}:{user_id}".encode()).hexdigest()


def run_daily_key(workspace_id: UUID) -> str:
    """SHA-256 digest of the per-workspace rolling-day dimension."""

    return hashlib.sha256(f"analysisrunday:{workspace_id}".encode()).hexdigest()


class AnalysisRunRateLimiter:
    """Sliding-window limiter over minute slices; storage failure fails CLOSED."""

    async def _record_and_count(
        self, db: AsyncSession, bucket_key: str, window: timedelta, now: datetime
    ) -> int:
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
                login_rate_buckets.c.slice_start > now - window,
            )
        )
        return int(total or 0)

    async def check_run_attempt(
        self, db: AsyncSession, *, workspace_id: UUID, user_id: UUID
    ) -> None:
        """Meter one run-creation attempt; raise REQUEST_RATE_LIMITED when over.

        Both dimensions are recorded before either verdict so a caller cannot
        spend only the cheaper budget, and the commit is the limiter's own: the
        attempt must be counted even when the request that follows fails.
        """

        now = datetime.now(timezone.utc)
        burst_window = timedelta(minutes=RUN_BURST_WINDOW_MINUTES)
        daily_window = timedelta(minutes=RUN_DAILY_WINDOW_MINUTES)
        try:
            burst_total = await self._record_and_count(
                db, run_burst_key(workspace_id, user_id), burst_window, now
            )
            daily_total = await self._record_and_count(
                db, run_daily_key(workspace_id), daily_window, now
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
            raise _rate_limited(
                max(int(burst_window.total_seconds()), 60), "workspaceUserBurst"
            ) from None

        if burst_total > RUN_BURST_MAX_ATTEMPTS:
            raise _rate_limited(
                max(int(burst_window.total_seconds()), 60), "workspaceUserBurst"
            )
        if daily_total > RUN_DAILY_MAX_ATTEMPTS:
            raise _rate_limited(
                max(int(daily_window.total_seconds()), 60), "workspaceDaily"
            )
