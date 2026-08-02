"""harden workspace_connectors.status to canonical connector_status enum

Revision ID: a4b5c6d7e8f9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-02

Decision-OS invariant repair: AGENTS section 8 defines the canonical
connector status set via ``app.types.ConnectorStatus`` (the only authoritative
definition) and the decision-OS invariants suite requires status-like columns
to be PG enums. The BYOK lane originally persisted ``status`` as a plain
String(32); this migration converts the column to the enum without touching
row values (every legacy value is a member of the canonical set).
"""

from alembic import op
import sqlalchemy as sa

revision = "a4b5c6d7e8f9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None

_CONNECTOR_STATUS = sa.Enum(
    "available",
    "missing_credentials",
    "invalid_credentials",
    "rate_limited",
    "quota_exhausted",
    "provider_error",
    "disabled",
    name="connector_status",
)


def upgrade() -> None:
    _CONNECTOR_STATUS.create(op.get_bind(), checkfirst=False)
    # The column carries a server_default; it must be dropped before the type
    # cast, then re-applied against the enum (same canonical default value).
    op.execute(
        "ALTER TABLE workspace_connectors ALTER COLUMN status DROP DEFAULT"
    )
    op.execute(
        "ALTER TABLE workspace_connectors "
        "ALTER COLUMN status TYPE connector_status "
        "USING status::connector_status"
    )
    op.execute(
        "ALTER TABLE workspace_connectors "
        "ALTER COLUMN status SET DEFAULT 'available'::connector_status"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE workspace_connectors ALTER COLUMN status DROP DEFAULT"
    )
    op.execute(
        "ALTER TABLE workspace_connectors "
        "ALTER COLUMN status TYPE VARCHAR(32) "
        "USING status::text"
    )
    op.execute(
        "ALTER TABLE workspace_connectors "
        "ALTER COLUMN status SET DEFAULT 'available'"
    )
    _CONNECTOR_STATUS.drop(op.get_bind(), checkfirst=False)
