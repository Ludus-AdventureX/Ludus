from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.db import get_database_url
from app.models import Base
from app.security.rate_limits import rate_limit_metadata

# Task 8 evidence ledger tables live in app/evidence/models.py (case_api_data
# write scope) but register on the shared Base; import them so autogenerate/
# check see the full metadata and do not propose dropping them.
import app.evidence.models  # noqa: F401  (registers evidence ledger tables)

# Task 9 analysis runtime tables (app/analyses/models.py) register the same way,
# including the active-run partial unique index attached to analysis_runs.
import app.analyses.models  # noqa: F401  (registers analysis runtime tables)

# Task 4/5 companion table (dossier_version_snapshots) registers the same way;
# without this import `alembic check` on the merged chain reports a spurious
# remove_table drift (QA finding F1, codex/qa-task-04-05-backend-r1).
import app.dossiers.models  # noqa: F401  (registers dossier_version_snapshots)

# Task 10 analysis output tables register the same way: claims/claim_evidence
# (app/analyses/claims.py), challenges (app/analyses/devils_advocate.py),
# quality_gate_results (app/analyses/quality_gate.py) and report/export
# artifacts (app/reports/models.py).
import app.analyses.claims  # noqa: F401  (registers claims + claim_evidence)
import app.analyses.devils_advocate  # noqa: F401  (registers challenges)
import app.analyses.quality_gate  # noqa: F401  (registers quality_gate_results)
import app.reports.models  # noqa: F401  (registers report/export artifacts)

config = context.config
# The login throttle table lives on a deliberate module-local MetaData
# (see app/security/rate_limits.py); include it so autogenerate/check do not
# propose dropping it.
target_metadata = [Base.metadata, rate_limit_metadata]


def run_migrations_offline() -> None:
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_database_url()
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
