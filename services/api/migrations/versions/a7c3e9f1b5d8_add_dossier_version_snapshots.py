"""add dossier version snapshots companion table

Revision ID: a7c3e9f1b5d8
Revises: b6e8f3a1d7c2
Create Date: 2026-07-25

Task 4/5 deferred revision, released now that the A1 lane (Task 10) reported
its migration rev-id ``b6e8f3a1d7c2`` (add_analysis_outputs, chained after
``f9a4b7e2c8d3``). Per the charter's ordering this lane's revision lands LAST:
``down_revision`` points at the Task 10 revision, whose file ships on the A1
branch — this file is therefore only applicable after the integration merge
brings both branches together (declared in the handoff; the in-worktree QA-7
test pins exactly this dangling-parent state).

Single table, generated from ``app/dossiers/models.py`` metadata verbatim:

* ``dossier_version_snapshots`` — immutable per-version snapshot detail
  (write-once companion row to the frozen canonical ``dossier_versions``);
  per included entry ``{entryId, entryVersion, statementType, scope,
  contentHash}`` plus the decision-maker profile version and subject version
  pinned at snapshot time. No new enums; no frozen table is touched.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'a7c3e9f1b5d8'
down_revision: Union[str, Sequence[str], None] = 'b6e8f3a1d7c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the write-once snapshot companion table."""
    op.create_table(
        'dossier_version_snapshots',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            'dossier_version_id', postgresql.UUID(as_uuid=True), nullable=False,
        ),
        sa.Column(
            'entries', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column('decision_maker_profile_version', sa.Integer(), nullable=True),
        sa.Column('subject_version', sa.Integer(), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_dossier_version_snapshots')),
        sa.UniqueConstraint(
            'workspace_id', 'dossier_version_id',
            name='uq_dossier_version_snapshots_version',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_dossier_version_snapshots_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['dossier_version_id'], ['dossier_versions.id'],
            name=op.f(
                'fk_dossier_version_snapshots_dossier_version_id_dossier_versions'
            ),
            ondelete='CASCADE',
        ),
    )


def downgrade() -> None:
    """Drop the companion table (frozen canonical tables untouched)."""
    op.drop_table('dossier_version_snapshots')
