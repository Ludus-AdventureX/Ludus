"""add workspace invites (multi-guest collaboration lane)

Revision ID: b3c5d7e9f1a2
Revises: c8d4e6f0a1b2
Create Date: 2026-07-28

workspace_invites: hashed invite tokens (plaintext never stored) with bounded
uses, TTL and revocation. The membership uniqueness the redeem path relies on
(uq_workspace_memberships_workspace_user) already exists since 0001.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'b3c5d7e9f1a2'
down_revision: Union[str, Sequence[str], None] = 'c8d4e6f0a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'workspace_invites',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('created_by_user_id', sa.UUID(), nullable=False),
        sa.Column('token_hash', sa.String(length=128), nullable=False),
        sa.Column(
            'granted_capabilities',
            postgresql.ARRAY(
                postgresql.ENUM(
                    'contribute', 'review', 'sign', 'manage_connectors',
                    name='workspace_capability', create_type=False,
                )
            ),
            server_default=sa.text("'{}'::workspace_capability[]"),
            nullable=False,
        ),
        sa.Column('max_uses', sa.Integer(), nullable=False),
        sa.Column('used_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash', name='uq_workspace_invites_token_hash'),
    )
    op.create_index(
        'ix_workspace_invites_workspace', 'workspace_invites',
        ['workspace_id', 'revoked_at'], unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_workspace_invites_workspace', table_name='workspace_invites')
    op.drop_table('workspace_invites')
