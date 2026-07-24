"""add login rate buckets for postgres backed login throttling

Revision ID: c4a1f0b2d9e7
Revises: f850d361ee42
Create Date: 2026-07-24

Column-exact with the Core Table declared in
``app/security/rate_limits.py`` (module-local metadata, P2-001 / doc 22):
login is intentionally fail-closed (429) until this table exists, so this
migration is a release prerequisite for exposing the login endpoint.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c4a1f0b2d9e7'
down_revision: Union[str, Sequence[str], None] = 'f850d361ee42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the sliding-window login throttle store."""
    op.create_table(
        'login_rate_buckets',
        # SHA-256 hex digest of the normalized dimension value ("ip:.." / "account:..").
        sa.Column('bucket_key', sa.String(length=64), nullable=False),
        # Minute-aligned slice start; the sliding window sums recent slices.
        sa.Column('slice_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('bucket_key', 'slice_start', name=op.f('pk_login_rate_buckets')),
    )


def downgrade() -> None:
    """Drop the login throttle store (login becomes fail-closed again)."""
    op.drop_table('login_rate_buckets')
