"""add strategic lens artifacts

Revision ID: d7e2a91c5b48
Revises: c4a1f0b2d9e7
Create Date: 2026-07-24

CCR-20260724-Ways-01: canonical StrategicLensArtifact table, column/constraint
exact with app/models.py. Identity, method snapshot, originModes, contentHash,
and createdAt are server-injected; `ready` requires Validation acceptance
(witnessed by validation_accepted_at); one ready artifact per lens per run.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'd7e2a91c5b48'
down_revision: Union[str, Sequence[str], None] = 'c4a1f0b2d9e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# origin_mode already exists in the database (19A foundations); never recreate it.
ORIGIN_MODE = postgresql.ENUM('live', 'cached', 'fixture', name='origin_mode', create_type=False)


def upgrade() -> None:
    """Create strategic_lens_artifacts and its lens enums."""
    op.create_table(
        'strategic_lens_artifacts',
        sa.Column(
            'strategic_lens_artifact_id',
            postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'),
            nullable=False,
        ),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('decision_case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('analysis_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('charter_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            'lens_type',
            sa.Enum(
                'porter_five_forces',
                'pre_mortem',
                'counterparty_response_matrix',
                'scenario_planning',
                'meadows_leverage_points',
                name='strategic_lens_type',
            ),
            nullable=False,
        ),
        sa.Column(
            'producer_role',
            sa.Enum('research', 'critic', 'synthesis', name='lens_producer_role'),
            nullable=False,
        ),
        sa.Column(
            'status',
            sa.Enum('draft', 'ready', 'rejected', name='strategic_lens_artifact_status'),
            server_default='draft',
            nullable=False,
        ),
        sa.Column('method_id', sa.String(length=160), nullable=False),
        sa.Column('method_version', sa.String(length=64), nullable=False),
        sa.Column('method_content_hash', sa.String(length=256), nullable=False),
        sa.Column('prompt_version', sa.String(length=64), nullable=False),
        sa.Column('schema_version', sa.String(length=64), nullable=False),
        sa.Column(
            'origin_modes',
            postgresql.ARRAY(ORIGIN_MODE),
            server_default=sa.text("'{}'::origin_mode[]"),
            nullable=False,
        ),
        sa.Column('content_hash', sa.String(length=256), nullable=False),
        sa.Column(
            'payload', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        sa.Column(
            'claim_refs', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'evidence_refs', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'assumption_refs', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column('validation_accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.PrimaryKeyConstraint('strategic_lens_artifact_id', name=op.f('pk_strategic_lens_artifacts')),
        sa.UniqueConstraint(
            'workspace_id', 'strategic_lens_artifact_id',
            name='uq_strategic_lens_artifacts_workspace_id',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_strategic_lens_artifacts_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id'],
            ['decision_cases.workspace_id', 'decision_cases.decision_case_id'],
            name='fk_strategic_lens_artifacts_workspace_case',
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id', 'analysis_run_id'],
            [
                'analysis_runs.workspace_id',
                'analysis_runs.decision_case_id',
                'analysis_runs.analysis_run_id',
            ],
            name='fk_strategic_lens_artifacts_workspace_case_run',
            ondelete='CASCADE',
        ),
        sa.CheckConstraint(
            "status <> 'ready' OR validation_accepted_at IS NOT NULL",
            name=op.f('ck_strategic_lens_artifacts_ready_requires_validation_acceptance'),
        ),
        sa.CheckConstraint(
            "content_hash <> ''",
            name=op.f('ck_strategic_lens_artifacts_content_hash_not_empty'),
        ),
    )
    op.create_index(
        'uq_strategic_lens_artifacts_ready_per_run_lens',
        'strategic_lens_artifacts',
        ['workspace_id', 'analysis_run_id', 'lens_type'],
        unique=True,
        postgresql_where=sa.text("status = 'ready'"),
    )
    op.create_index(
        'ix_strategic_lens_artifacts_workspace_run',
        'strategic_lens_artifacts',
        ['workspace_id', 'analysis_run_id'],
    )


def downgrade() -> None:
    """Drop strategic_lens_artifacts and the lens-specific enums."""
    op.drop_index('ix_strategic_lens_artifacts_workspace_run', table_name='strategic_lens_artifacts')
    op.drop_index(
        'uq_strategic_lens_artifacts_ready_per_run_lens',
        table_name='strategic_lens_artifacts',
    )
    op.drop_table('strategic_lens_artifacts')
    # origin_mode is shared and predates this revision; drop only lens enums.
    sa.Enum(name='strategic_lens_artifact_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='lens_producer_role').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='strategic_lens_type').drop(op.get_bind(), checkfirst=True)
