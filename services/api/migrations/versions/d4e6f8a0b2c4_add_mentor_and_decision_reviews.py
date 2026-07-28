"""add mentor reviews (R3 incubator lane)

Revision ID: d4e6f8a0b2c4
Revises: b3c5d7e9f1a2
Create Date: 2026-07-28

mentor_reviews: structured mentor feedback per decision case (score 1-5,
blind spots, suggested next step). decision_reviews already exists since
c8d4e6f0a1b2 - R3 adds only its missing POST surface, no schema change.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd4e6f8a0b2c4'
down_revision: Union[str, Sequence[str], None] = 'b3c5d7e9f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'mentor_reviews',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('decision_case_id', sa.UUID(), nullable=False),
        sa.Column('author_user_id', sa.UUID(), nullable=False),
        sa.Column('quality_score', sa.Integer(), nullable=False),
        sa.Column('blind_spots', sa.Text(), nullable=False),
        sa.Column('next_step', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['author_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('quality_score >= 1 AND quality_score <= 5', name='ck_mentor_reviews_score_range'),
    )
    op.create_index('ix_mentor_reviews_workspace_case', 'mentor_reviews',
                    ['workspace_id', 'decision_case_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_mentor_reviews_workspace_case', table_name='mentor_reviews')
    op.drop_table('mentor_reviews')
