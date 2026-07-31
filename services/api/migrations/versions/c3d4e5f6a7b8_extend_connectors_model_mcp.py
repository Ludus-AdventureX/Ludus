"""extend workspace_connectors: widen provider constraint + add config JSONB

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Drop old provider CHECK constraint
    op.drop_constraint(
        "ck_workspace_connectors_workspace_connector_provider_in_catalog",
        "workspace_connectors",
        type_="check",
    )
    # 2. Add new wider CHECK to include 'model' and 'mcp'
    op.create_check_constraint(
        "ck_workspace_connectors_provider_in_catalog",
        "workspace_connectors",
        "provider IN ('exa', 'firecrawl', 'tavily', 'model', 'mcp')",
    )
    # 3. Add config JSONB column (nullable, for model/mcp extra fields)
    op.add_column(
        "workspace_connectors",
        sa.Column("config", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workspace_connectors", "config")
    op.drop_constraint(
        "ck_workspace_connectors_provider_in_catalog",
        "workspace_connectors",
        type_="check",
    )
    op.create_check_constraint(
        "ck_workspace_connectors_workspace_connector_provider_in_catalog",
        "workspace_connectors",
        "provider IN ('exa', 'firecrawl', 'tavily')",
    )
