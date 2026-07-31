"""add case_profiles table

Revision ID: a1b2c3d4e5f6
Revises: d4e6f8a0b2c4
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB

revision = "a1b2c3d4e5f6"
down_revision = "d4e6f8a0b2c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_profiles",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("decision_case_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("profile_type", sa.String(32), nullable=False),
        sa.Column("content", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"],
            name="fk_case_profiles_workspace", ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "workspace_id", "decision_case_id", "profile_type",
            name="uq_case_profiles_workspace_case_type",
        ),
    )
    op.create_index(
        "ix_case_profiles_workspace_case",
        "case_profiles",
        ["workspace_id", "decision_case_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_case_profiles_workspace_case")
    op.drop_table("case_profiles")
