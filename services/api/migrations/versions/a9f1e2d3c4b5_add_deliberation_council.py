"""add deliberation council

Revision ID: a9f1e2d3c4b5
Revises: 2b2d34dacee0
Create Date: 2026-08-04

CCR-20260804-DELIB-01: the eight deliberation tables (run, factor, round,
message, proposal, nomination, outcome, event), column/constraint exact with
app/models.py. Invariants enforced at the database level:

- subjective factors require statement + human author + assumed/unknown
  status (never supported/conditional);
- nominations carry no factor reference before confirmation (no
  auto-activation);
- one outcome per run; per-run monotonic event sequence for Last-Event-ID
  replay;
- max_rounds budget capped at 5.

origin_mode and factor_evidence_status already exist; never recreate them.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'a9f1e2d3c4b5'
down_revision: Union[str, Sequence[str], None] = '2b2d34dacee0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ORIGIN_MODE = postgresql.ENUM('live', 'cached', 'fixture', name='origin_mode', create_type=False)
FACTOR_EVIDENCE_STATUS = postgresql.ENUM(
    'supported', 'conditional', 'assumed', 'unknown',
    name='factor_evidence_status', create_type=False,
)


def upgrade() -> None:
    """Create the deliberation council tables and their enums."""
    op.create_table(
        'deliberation_runs',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('decision_case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            'status',
            sa.Enum(
                'preparing', 'running', 'awaiting_user', 'complete', 'cancelled',
                name='deliberation_run_status',
            ),
            server_default='preparing',
            nullable=False,
        ),
        sa.Column('current_round_seq', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('max_rounds', sa.Integer(), server_default=sa.text('3'), nullable=False),
        sa.Column('factor_snapshot_hash', sa.String(length=256), nullable=False),
        sa.Column(
            'origin_modes', postgresql.ARRAY(ORIGIN_MODE),
            server_default=sa.text("'{}'::origin_mode[]"), nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_deliberation_runs')),
        sa.UniqueConstraint(
            'workspace_id', 'id',
            name='uq_deliberation_runs_workspace_id',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_deliberation_runs_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id'],
            ['decision_cases.workspace_id', 'decision_cases.decision_case_id'],
            name='fk_deliberation_runs_workspace_case',
            ondelete='CASCADE',
        ),
        sa.CheckConstraint(
            'max_rounds >= 1 AND max_rounds <= 5',
            name='ck_deliberation_runs_max_rounds_budget',
        ),
    )
    op.create_index(
        'ix_deliberation_runs_workspace_case', 'deliberation_runs',
        ['workspace_id', 'decision_case_id'],
    )

    op.create_table(
        'deliberation_factors',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('deliberation_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            'provenance',
            sa.Enum('objective', 'subjective', name='deliberation_factor_provenance'),
            nullable=False,
        ),
        sa.Column('label', sa.String(length=240), nullable=False),
        sa.Column('strength', sa.Float(), nullable=False),
        sa.Column('source_factor_id', sa.String(length=240), nullable=True),
        sa.Column('statement', sa.Text(), nullable=True),
        sa.Column('author_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('dossier_assumption_id', sa.String(length=240), nullable=True),
        sa.Column('evidence_status', FACTOR_EVIDENCE_STATUS, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_deliberation_factors')),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_deliberation_factors_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'deliberation_run_id'],
            ['deliberation_runs.workspace_id', 'deliberation_runs.id'],
            name='fk_deliberation_factors_run',
            ondelete='CASCADE',
        ),
        sa.CheckConstraint(
            "provenance <> 'objective' OR source_factor_id IS NOT NULL",
            name='ck_deliberation_factors_objective_requires_source',
        ),
        sa.CheckConstraint(
            "provenance <> 'subjective' OR (statement IS NOT NULL AND author_user_id IS NOT NULL AND evidence_status IS NOT NULL)",
            name='ck_deliberation_factors_subjective_requires_human_stamp',
        ),
        sa.CheckConstraint(
            'strength >= 0 AND strength <= 1',
            name='ck_deliberation_factors_strength_range',
        ),
    )
    op.create_index(
        'ix_deliberation_factors_workspace_run', 'deliberation_factors',
        ['workspace_id', 'deliberation_run_id'],
    )

    op.create_table(
        'deliberation_rounds',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('deliberation_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column(
            'kind',
            sa.Enum('opening', 'challenge', 'verdict', name='deliberation_round_kind'),
            nullable=False,
        ),
        sa.Column(
            'status',
            sa.Enum('active', 'complete', name='deliberation_round_status'),
            server_default='active',
            nullable=False,
        ),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_deliberation_rounds')),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_deliberation_rounds_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'deliberation_run_id'],
            ['deliberation_runs.workspace_id', 'deliberation_runs.id'],
            name='fk_deliberation_rounds_run',
            ondelete='CASCADE',
        ),
        sa.UniqueConstraint(
            'workspace_id', 'deliberation_run_id', 'seq',
            name='uq_deliberation_rounds_run_seq',
        ),
    )

    op.create_table(
        'deliberation_messages',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('deliberation_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('round_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            'speaker',
            sa.Enum('witness', 'moderator', 'user', name='deliberation_speaker'),
            nullable=False,
        ),
        sa.Column('speaker_factor_id', sa.String(length=240), nullable=True),
        sa.Column(
            'kind',
            sa.Enum(
                'statement', 'challenge', 'rebuttal', 'proposal',
                'intervention', 'nomination', 'verdict_summary',
                name='deliberation_message_kind',
            ),
            nullable=False,
        ),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('structured_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            'stamp_actor',
            sa.Enum('human', 'analysis', 'unknown', name='responsibility_actor'),
            nullable=False,
        ),
        sa.Column('stamp_note', sa.Text(), nullable=True),
        sa.Column('origin_mode', ORIGIN_MODE, server_default='fixture', nullable=False),
        sa.Column(
            'source_origin_modes', postgresql.ARRAY(ORIGIN_MODE),
            server_default=sa.text("'{}'::origin_mode[]"), nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_deliberation_messages')),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_deliberation_messages_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'deliberation_run_id'],
            ['deliberation_runs.workspace_id', 'deliberation_runs.id'],
            name='fk_deliberation_messages_run',
            ondelete='CASCADE',
        ),
        sa.CheckConstraint(
            "speaker <> 'witness' OR speaker_factor_id IS NOT NULL",
            name='ck_deliberation_messages_witness_requires_factor',
        ),
    )
    op.create_index(
        'ix_deliberation_messages_workspace_run', 'deliberation_messages',
        ['workspace_id', 'deliberation_run_id'],
    )

    op.create_table(
        'deliberation_proposals',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('deliberation_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('proposer_factor_id', sa.String(length=240), nullable=False),
        sa.Column(
            'kind',
            sa.Enum('factor_strength', 'edge_validity', 'new_factor', name='deliberation_proposal_kind'),
            nullable=False,
        ),
        sa.Column(
            'before', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        sa.Column(
            'after', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        sa.Column(
            'status',
            sa.Enum('pending', 'accepted', 'rejected', name='deliberation_proposal_status'),
            server_default='pending',
            nullable=False,
        ),
        sa.Column('engine_preview', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_deliberation_proposals')),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_deliberation_proposals_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'deliberation_run_id'],
            ['deliberation_runs.workspace_id', 'deliberation_runs.id'],
            name='fk_deliberation_proposals_run',
            ondelete='CASCADE',
        ),
        sa.CheckConstraint(
            "status <> 'accepted' OR decided_at IS NOT NULL",
            name='ck_deliberation_proposals_decided_requires_timestamp',
        ),
    )
    op.create_index(
        'ix_deliberation_proposals_workspace_run', 'deliberation_proposals',
        ['workspace_id', 'deliberation_run_id'],
    )

    op.create_table(
        'deliberation_nominations',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('deliberation_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('rationale', sa.Text(), nullable=False),
        sa.Column('target_description', sa.Text(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('pending', 'confirmed', 'rejected', name='deliberation_nomination_status'),
            server_default='pending',
            nullable=False,
        ),
        sa.Column('confirmed_factor_id', sa.String(length=240), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_deliberation_nominations')),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_deliberation_nominations_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'deliberation_run_id'],
            ['deliberation_runs.workspace_id', 'deliberation_runs.id'],
            name='fk_deliberation_nominations_run',
            ondelete='CASCADE',
        ),
        sa.CheckConstraint(
            "status <> 'confirmed' OR confirmed_factor_id IS NOT NULL",
            name='ck_deliberation_nominations_confirmed_requires_factor',
        ),
        sa.CheckConstraint(
            "status = 'confirmed' OR confirmed_factor_id IS NULL",
            name='ck_deliberation_nominations_no_factor_before_confirmation',
        ),
    )
    op.create_index(
        'ix_deliberation_nominations_workspace_run', 'deliberation_nominations',
        ['workspace_id', 'deliberation_run_id'],
    )

    op.create_table(
        'deliberation_outcomes',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('deliberation_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            'condition_projections', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'flip_conditions', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'dissent_log', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'assumption_ledger', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column('disclaimer', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_deliberation_outcomes')),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_deliberation_outcomes_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'deliberation_run_id'],
            ['deliberation_runs.workspace_id', 'deliberation_runs.id'],
            name='fk_deliberation_outcomes_run',
            ondelete='CASCADE',
        ),
        sa.UniqueConstraint(
            'workspace_id', 'deliberation_run_id',
            name='uq_deliberation_outcomes_one_per_run',
        ),
    )

    op.create_table(
        'deliberation_events',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('decision_case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('deliberation_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column(
            'category',
            sa.Enum(
                'deliberation.round', 'deliberation.message', 'deliberation.proposal',
                'deliberation.nomination', 'deliberation.outcome',
                name='deliberation_event_category',
            ),
            nullable=False,
        ),
        sa.Column('type', sa.String(length=120), nullable=False),
        sa.Column('origin_mode', ORIGIN_MODE, server_default='fixture', nullable=False),
        sa.Column(
            'source_origin_modes', postgresql.ARRAY(ORIGIN_MODE),
            server_default=sa.text("'{}'::origin_mode[]"), nullable=False,
        ),
        sa.Column(
            'payload', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_deliberation_events')),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_deliberation_events_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'deliberation_run_id'],
            ['deliberation_runs.workspace_id', 'deliberation_runs.id'],
            name='fk_deliberation_events_run',
            ondelete='CASCADE',
        ),
        sa.UniqueConstraint(
            'workspace_id', 'deliberation_run_id', 'sequence',
            name='uq_deliberation_events_run_sequence',
        ),
    )
    op.create_index(
        'ix_deliberation_events_workspace_run', 'deliberation_events',
        ['workspace_id', 'deliberation_run_id'],
    )


def downgrade() -> None:
    """Drop the deliberation tables and their enums (shared enums survive)."""
    for table in (
        'deliberation_events',
        'deliberation_outcomes',
        'deliberation_nominations',
        'deliberation_proposals',
        'deliberation_messages',
        'deliberation_rounds',
        'deliberation_factors',
        'deliberation_runs',
    ):
        op.drop_table(table)
    for enum_name in (
        'deliberation_event_category',
        'deliberation_nomination_status',
        'deliberation_proposal_status',
        'deliberation_proposal_kind',
        'deliberation_message_kind',
        'responsibility_actor',
        'deliberation_round_status',
        'deliberation_round_kind',
        'deliberation_speaker',
        'deliberation_factor_provenance',
        'deliberation_run_status',
    ):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
