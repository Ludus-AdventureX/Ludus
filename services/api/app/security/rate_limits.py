"""P2-001: Postgres-backed login rate limiting (doc 22 security contract).

Contract points implemented here:

- dual sliding window per client IP and per normalized account, evaluated
  before any credential work;
- counters live in PostgreSQL via atomic ``INSERT .. ON CONFLICT`` increments
  (no read-then-write races, no single-process memory state), so Web/API
  workers and restarts share one consistent view;
- over-limit requests fail with ``REQUEST_RATE_LIMITED`` (429) carrying only a
  safe ``retryAfterSeconds``;
- infrastructure failure fails CLOSED: if the throttle store cannot be read
  or written, the login attempt is rejected rather than admitted unmetered;
- expired slices are cleaned opportunistically; cleanup failure never widens
  the limit.

Privacy: bucket keys are SHA-256 digests of the normalized dimension value
("ip:<addr>" / "account:<email>"); raw IPs and emails never enter the store.

Schema ownership: the ``login_rate_buckets`` table is declared on a
module-local ``MetaData`` (deliberately not ``app.db.Base.metadata``) because
canonical models and Alembic migrations belong to the Contract Lead. The
accompanying CONTRACT_CHANGE_REQUEST carries the exact migration draft; until
it lands, ``ensure_login_rate_schema`` lets tests and local environments
create the table explicitly.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    delete,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.auth.config import AuthSettings, get_auth_settings
from app.security.envelope import ApiFailure

# Module-local metadata: see the module docstring for why this is not Base.
rate_limit_metadata = MetaData()

login_rate_buckets = Table(
    "login_rate_buckets",
    rate_limit_metadata,
    # SHA-256 hex digest of the normalized dimension value.
    Column("bucket_key", String(64), primary_key=True),
    # Minute-aligned slice start; the sliding window sums recent slices.
    Column("slice_start", DateTime(timezone=True), primary_key=True),
    Column("attempts", BigInteger, nullable=False),
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _digest(dimension: str, value: str) -> str:
    return hashlib.sha256(f"{dimension}:{value}".encode()).hexdigest()


def login_ip_key(client_ip: str) -> str:
    return _digest("ip", client_ip.strip().lower())


def login_account_key(email: str) -> str:
    return _digest("account", email.strip().lower())


def _rate_limited(retry_after_seconds: int) -> ApiFailure:
    return ApiFailure(
        "REQUEST_RATE_LIMITED",
        "Too many login attempts. Retry later.",
        http_status=429,
        retryable=True,
        details={"retryAfterSeconds": retry_after_seconds},
    )


@dataclass(frozen=True)
class LoginRateDecision:
    allowed: bool
    retry_after_seconds: int


class LoginRateLimiter:
    """Sliding-window limiter over minute slices with atomic upserts."""

    def __init__(self, settings: AuthSettings | None = None) -> None:
        self._settings = settings or get_auth_settings()

    @property
    def _window(self) -> timedelta:
        return timedelta(minutes=self._settings.login_rate_window_minutes)

    @staticmethod
    def _slice_start(now: datetime) -> datetime:
        return now.replace(second=0, microsecond=0)

    async def _record_and_count(self, db: AsyncSession, bucket_key: str) -> int:
        """Atomically count this attempt and return the in-window total."""

        now = _utc_now()
        upsert = (
            pg_insert(login_rate_buckets)
            .values(bucket_key=bucket_key, slice_start=self._slice_start(now), attempts=1)
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
        return int(total or 0)

    async def check_login_attempt(
        self, db: AsyncSession, *, client_ip: str, email: str
    ) -> None:
        """Meter one login attempt; raise REQUEST_RATE_LIMITED when over limit.

        Any storage failure is converted to the same 429 (fail-closed): an
        unmetered login path must not exist.
        """

        retry_after = max(int(self._window.total_seconds()), 60)
        try:
            ip_total = await self._record_and_count(db, login_ip_key(client_ip))
            account_total = await self._record_and_count(db, login_account_key(email))
            await db.commit()
        except ApiFailure:
            raise
        except Exception:
            await _safe_rollback(db)
            raise _rate_limited(retry_after) from None

        if (
            ip_total > self._settings.login_rate_ip_max_attempts
            or account_total > self._settings.login_rate_account_max_attempts
        ):
            raise _rate_limited(retry_after)

    async def reset_account(self, db: AsyncSession, email: str) -> None:
        """Clear the account dimension after a successful login.

        The IP dimension intentionally keeps counting: one address rotating
        across many accounts must not launder its budget via one success.
        """

        try:
            await db.execute(
                delete(login_rate_buckets).where(
                    login_rate_buckets.c.bucket_key == login_account_key(email)
                )
            )
        except Exception:
            await _safe_rollback(db)

    async def cleanup_expired(self, db: AsyncSession) -> None:
        """Best-effort removal of slices older than the window."""

        try:
            await db.execute(
                delete(login_rate_buckets).where(
                    login_rate_buckets.c.slice_start <= _utc_now() - self._window
                )
            )
            await db.commit()
        except Exception:
            # Cleanup failure must never widen or bypass the limit.
            await _safe_rollback(db)


async def _safe_rollback(db: AsyncSession) -> None:
    try:
        await db.rollback()
    except Exception:
        pass


async def ensure_login_rate_schema(engine: AsyncEngine) -> None:
    """Create the throttle table explicitly (tests / pre-migration local envs).

    Canonical environments receive the same DDL through the Contract Lead's
    Alembic migration; this helper never touches other tables.
    """

    async with engine.begin() as connection:
        await connection.run_sync(rate_limit_metadata.create_all)
