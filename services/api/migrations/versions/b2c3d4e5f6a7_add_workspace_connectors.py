"""add workspace_connectors table (BYOK)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_connectors",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary, nullable=False),
        sa.Column("nonce", sa.LargeBinary, nullable=False),
        sa.Column("key_version", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("mask", sa.String(24), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'available'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"],
            name="fk_workspace_connectors_workspace", ondelete="CASCADE",
        ),
        sa.UniqueConstraint("workspace_id", "id", name="uq_workspace_connectors_workspace_id"),
        sa.UniqueConstraint(
            "workspace_id", "provider",
            name="uq_workspace_connectors_workspace_provider",
        ),
        sa.CheckConstraint(
            "provider IN ('exa', 'firecrawl', 'tavily')",
            name="ck_workspace_connectors_workspace_connector_provider_in_catalog",
        ),
    )
    op.create_index(
        "ix_workspace_connectors_workspace", "workspace_connectors", ["workspace_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_workspace_connectors_workspace")
    op.drop_table("workspace_connectors")
