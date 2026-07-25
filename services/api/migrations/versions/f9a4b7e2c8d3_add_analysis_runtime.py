"""add analysis runtime tables and active-run constraint

Revision ID: f9a4b7e2c8d3
Revises: e7f3a2c9d5b1
Create Date: 2026-07-25

Task 9 (case_api_data) forward revision on top of e7f3a2c9d5b1 (untouched):

* ``analysis_charters`` / ``analysis_events`` / ``research_packets`` /
  ``run_intervention_classifications`` / ``run_resolutions`` per
  06-data-model.md, workspace-scoped with the composite case/run FK
  discipline;
* the canonical partial unique index "at most one ACTIVE formal Run per
  (workspace, case)" on the PRE-EXISTING ``analysis_runs`` table (06 数据库
  索引 section);
* one new PG enum ``analysis_charter_status``; ``formal_analysis_level`` /
  ``analysis_run_status`` / ``origin_mode`` enums are reused, never
  recreated. Event category/type, packet role, classification result and
  resolution kind literal sets persist as CHECK-constrained strings
  (SIM-02A ``response_kind`` precedent).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'f9a4b7e2c8d3'
down_revision: Union[str, Sequence[str], None] = 'e7f3a2c9d5b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CHARTER_STATUS = postgresql.ENUM(
    'draft', 'awaiting_confirmation', 'confirmed', 'superseded',
    name='analysis_charter_status', create_type=False,
)
_FORMAL_LEVEL = postgresql.ENUM(
    'focused', 'full', name='formal_analysis_level', create_type=False,
)
_RUN_STATUS = postgresql.ENUM(
    'queued', 'planning', 'retrieving', 'analyzing', 'criticizing',
    'synthesizing', 'validating', 'ready', 'blocked', 'needs_attention',
    'cancelled', name='analysis_run_status', create_type=False,
)
_ORIGIN_MODE = postgresql.ENUM(
    'live', 'cached', 'fixture', name='origin_mode', create_type=False,
)
_PACKET_ROLE = postgresql.ENUM(
    'research', 'critic', 'synthesis', 'validation',
    name='research_packet_role', create_type=False,
)

_EVENT_CATEGORIES = (
    "'agent.status', 'agent.task', 'tool.call', 'citation.added', "
    "'user.confirmation.required'"
)
_EVENT_TYPES = (
    "'analysis.stage.started', 'analysis.stage.progressed', "
    "'analysis.stage.completed', 'analysis.needs_attention', "
    "'analysis.resumed', 'analysis.amendment_required', 'analysis.cancelled', "
    "'analysis.blocked', 'analysis.ready', 'research.packet.completed', "
    "'retrieval.completed', 'quality.warning', 'strategic_lens.completed', "
    "'tool.call.started', 'tool.call.completed', 'tool.call.failed', "
    "'fallback.cached_evidence', 'fallback.fixture.loaded', 'citation.added', "
    "'user.confirmation.required'"
)


def upgrade() -> None:
    """Create the analysis runtime tables and the active-run partial index."""
    op.execute(
        "CREATE TYPE analysis_charter_status AS ENUM "
        "('draft', 'awaiting_confirmation', 'confirmed', 'superseded')"
    )
    op.execute(
        "CREATE TYPE research_packet_role AS ENUM "
        "('research', 'critic', 'synthesis', 'validation')"
    )

    op.create_table(
        'analysis_charters',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('decision_subject_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('decision_case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('case_version', sa.Integer(), nullable=False),
        sa.Column('case_snapshot_hash', sa.String(length=256), nullable=False),
        sa.Column('status', _CHARTER_STATUS, server_default='draft', nullable=False),
        sa.Column('analysis_level', _FORMAL_LEVEL, nullable=False),
        sa.Column('decision_question', sa.Text(), nullable=False),
        sa.Column('deadline', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'goals', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'constraints', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'option_ids', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column('current_inclination', sa.Text(), nullable=True),
        sa.Column(
            'possible_biases', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'unknown_item_ids', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'allowed_material_ids', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'excluded_material_ids', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column('dossier_snapshot_version', sa.Integer(), nullable=False),
        sa.Column('dossier_snapshot_hash', sa.String(length=256), nullable=False),
        sa.Column(
            'decision_maker_profile_id', postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column('decision_maker_profile_version', sa.Integer(), nullable=True),
        sa.Column('preference_snapshot_hash', sa.String(length=256), nullable=True),
        sa.Column(
            'preference_weights', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        sa.Column(
            'analysis_directions', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'required_strategic_lens_types', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'method_recommendation_id', postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column('method_id', sa.String(length=160), nullable=True),
        sa.Column('method_version', sa.String(length=64), nullable=True),
        sa.Column('method_content_hash', sa.String(length=256), nullable=True),
        sa.Column(
            'method_reasons', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'applicability_limits', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'alternative_methods', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'missing_inputs', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'formal_analysis_allowed', sa.Boolean(),
            server_default='false', nullable=False,
        ),
        sa.Column(
            'blocking_reasons', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'allowed_connector_ids', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'estimated_duration_minutes', sa.Integer(),
            server_default='0', nullable=False,
        ),
        sa.Column(
            'budget', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        sa.Column('replaces_charter_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            'superseded_by_charter_id', postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_analysis_charters')),
        sa.UniqueConstraint(
            'workspace_id', 'id', name='uq_analysis_charters_workspace_id'
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_analysis_charters_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id'],
            ['decision_cases.workspace_id', 'decision_cases.decision_case_id'],
            name='fk_analysis_charters_workspace_case', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'replaces_charter_id'],
            ['analysis_charters.workspace_id', 'analysis_charters.id'],
            name='fk_analysis_charters_workspace_replaces', ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'superseded_by_charter_id'],
            ['analysis_charters.workspace_id', 'analysis_charters.id'],
            name='fk_analysis_charters_workspace_superseded_by', ondelete='RESTRICT',
        ),
        sa.CheckConstraint(
            'version > 0', name=op.f('ck_analysis_charters_version_positive')
        ),
        sa.CheckConstraint(
            'case_version > 0', name=op.f('ck_analysis_charters_case_version_positive')
        ),
        sa.CheckConstraint(
            'dossier_snapshot_version > 0',
            name=op.f('ck_analysis_charters_dossier_snapshot_version_positive'),
        ),
        sa.CheckConstraint(
            "status <> 'confirmed' OR confirmed_at IS NOT NULL",
            name=op.f('ck_analysis_charters_confirmed_requires_timestamp'),
        ),
        sa.CheckConstraint(
            "status <> 'superseded' OR superseded_by_charter_id IS NOT NULL",
            name=op.f('ck_analysis_charters_superseded_requires_successor'),
        ),
        sa.CheckConstraint(
            "(analysis_level = 'focused' "
            "AND required_strategic_lens_types = '[]'::jsonb) "
            "OR (analysis_level = 'full' "
            "AND jsonb_array_length(required_strategic_lens_types) = 5)",
            name=op.f('ck_analysis_charters_lens_set_matches_level'),
        ),
    )
    op.create_index(
        'ix_analysis_charters_workspace_case_status',
        'analysis_charters',
        ['workspace_id', 'decision_case_id', 'status', 'created_at'],
    )

    op.create_table(
        'analysis_events',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('decision_case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('analysis_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('sequence', sa.BigInteger(), nullable=False),
        sa.Column('category', sa.String(length=40), nullable=False),
        sa.Column('type', sa.String(length=60), nullable=False),
        sa.Column('origin_mode', _ORIGIN_MODE, nullable=False),
        sa.Column(
            'source_origin_modes', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'payload', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_analysis_events')),
        sa.UniqueConstraint(
            'workspace_id', 'id', name='uq_analysis_events_workspace_id'
        ),
        sa.UniqueConstraint(
            'workspace_id', 'analysis_run_id', 'sequence',
            name='uq_analysis_events_workspace_run_sequence',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_analysis_events_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id'],
            ['decision_cases.workspace_id', 'decision_cases.decision_case_id'],
            name='fk_analysis_events_workspace_case', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id', 'analysis_run_id'],
            [
                'analysis_runs.workspace_id',
                'analysis_runs.decision_case_id',
                'analysis_runs.analysis_run_id',
            ],
            name='fk_analysis_events_workspace_case_run', ondelete='CASCADE',
        ),
        sa.CheckConstraint(
            'sequence > 0', name=op.f('ck_analysis_events_sequence_positive')
        ),
        sa.CheckConstraint(
            f'category IN ({_EVENT_CATEGORIES})',
            name=op.f('ck_analysis_events_category_canonical'),
        ),
        sa.CheckConstraint(
            f'type IN ({_EVENT_TYPES})',
            name=op.f('ck_analysis_events_type_canonical'),
        ),
    )
    op.create_index(
        'ix_analysis_events_workspace_run_sequence',
        'analysis_events',
        ['workspace_id', 'analysis_run_id', 'sequence'],
    )

    op.create_table(
        'research_packets',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('decision_case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('analysis_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', _PACKET_ROLE, nullable=False),
        sa.Column('factor', sa.String(length=400), nullable=True),
        sa.Column('framework_used', sa.String(length=400), nullable=True),
        sa.Column('conclusion', sa.Text(), nullable=False),
        sa.Column('direction', sa.String(length=200), nullable=True),
        sa.Column('claim_support_score', sa.Float(), nullable=False),
        sa.Column(
            'evidence_ids', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'discarded_claims', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'remaining_gaps', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column('disclaimer', sa.Text(), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_research_packets')),
        sa.UniqueConstraint(
            'workspace_id', 'id', name='uq_research_packets_workspace_id'
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_research_packets_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id'],
            ['decision_cases.workspace_id', 'decision_cases.decision_case_id'],
            name='fk_research_packets_workspace_case', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id', 'analysis_run_id'],
            [
                'analysis_runs.workspace_id',
                'analysis_runs.decision_case_id',
                'analysis_runs.analysis_run_id',
            ],
            name='fk_research_packets_workspace_case_run', ondelete='CASCADE',
        ),
        sa.CheckConstraint(
            'claim_support_score >= 0 AND claim_support_score <= 1',
            name=op.f('ck_research_packets_claim_support_score_range'),
        ),
        sa.CheckConstraint(
            "conclusion <> ''", name=op.f('ck_research_packets_conclusion_not_empty')
        ),
    )
    op.create_index(
        'ix_research_packets_workspace_run_role',
        'research_packets',
        ['workspace_id', 'analysis_run_id', 'role'],
    )

    op.create_table(
        'run_intervention_classifications',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('decision_case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('analysis_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('result', sa.String(length=20), nullable=False),
        sa.Column(
            'changed_frozen_fields', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'reason_codes', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            'id', name=op.f('pk_run_intervention_classifications')
        ),
        sa.UniqueConstraint(
            'workspace_id', 'id',
            name='uq_run_intervention_classifications_workspace_id',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_run_intervention_classifications_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id'],
            ['decision_cases.workspace_id', 'decision_cases.decision_case_id'],
            name='fk_run_intervention_classifications_workspace_case',
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id', 'analysis_run_id'],
            [
                'analysis_runs.workspace_id',
                'analysis_runs.decision_case_id',
                'analysis_runs.analysis_run_id',
            ],
            name='fk_run_intervention_classifications_workspace_case_run',
            ondelete='CASCADE',
        ),
        sa.CheckConstraint(
            "result IN ('resolution', 'amendment')",
            name=op.f('ck_run_intervention_classifications_result_canonical'),
        ),
        sa.CheckConstraint(
            "(result = 'resolution' AND changed_frozen_fields = '[]'::jsonb) "
            "OR (result = 'amendment' AND changed_frozen_fields <> '[]'::jsonb)",
            name=op.f(
                'ck_run_intervention_classifications_result_matches_changed_fields'
            ),
        ),
    )
    op.create_index(
        'ix_run_intervention_classifications_workspace_run',
        'run_intervention_classifications',
        ['workspace_id', 'analysis_run_id', 'created_at'],
    )

    op.create_table(
        'run_resolutions',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('decision_case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('analysis_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('classification_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            'payload', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        sa.Column('resume_stage', _RUN_STATUS, nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_run_resolutions')),
        sa.UniqueConstraint(
            'workspace_id', 'id', name='uq_run_resolutions_workspace_id'
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_run_resolutions_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id'],
            ['decision_cases.workspace_id', 'decision_cases.decision_case_id'],
            name='fk_run_resolutions_workspace_case', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id', 'analysis_run_id'],
            [
                'analysis_runs.workspace_id',
                'analysis_runs.decision_case_id',
                'analysis_runs.analysis_run_id',
            ],
            name='fk_run_resolutions_workspace_case_run', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'classification_id'],
            [
                'run_intervention_classifications.workspace_id',
                'run_intervention_classifications.id',
            ],
            name='fk_run_resolutions_workspace_classification', ondelete='RESTRICT',
        ),
        sa.CheckConstraint(
            "payload ->> 'kind' IN ('source_conflict', "
            "'hard_constraint_confirmation', 'provider_recovery')",
            name=op.f('ck_run_resolutions_payload_kind_canonical'),
        ),
        sa.CheckConstraint(
            "resume_stage IN ('planning', 'retrieving', 'analyzing', "
            "'criticizing', 'synthesizing', 'validating')",
            name=op.f('ck_run_resolutions_resume_stage_resumable'),
        ),
    )
    op.create_index(
        'ix_run_resolutions_workspace_run',
        'run_resolutions',
        ['workspace_id', 'analysis_run_id', 'created_at'],
    )

    # Canonical: at most one ACTIVE formal Run per (workspace, case).
    op.create_index(
        'uq_analysis_runs_one_active_per_case',
        'analysis_runs',
        ['workspace_id', 'decision_case_id'],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('queued', 'planning', 'retrieving', 'analyzing', "
            "'criticizing', 'synthesizing', 'validating', 'needs_attention')"
        ),
    )


def downgrade() -> None:
    """Drop the analysis runtime tables, the partial index, and the enum."""
    op.drop_index('uq_analysis_runs_one_active_per_case', table_name='analysis_runs')
    op.drop_index('ix_run_resolutions_workspace_run', table_name='run_resolutions')
    op.drop_table('run_resolutions')
    op.drop_index(
        'ix_run_intervention_classifications_workspace_run',
        table_name='run_intervention_classifications',
    )
    op.drop_table('run_intervention_classifications')
    op.drop_index(
        'ix_research_packets_workspace_run_role', table_name='research_packets'
    )
    op.drop_table('research_packets')
    op.drop_index(
        'ix_analysis_events_workspace_run_sequence', table_name='analysis_events'
    )
    op.drop_table('analysis_events')
    op.drop_index(
        'ix_analysis_charters_workspace_case_status', table_name='analysis_charters'
    )
    op.drop_table('analysis_charters')
    op.execute('DROP TYPE research_packet_role')
    op.execute('DROP TYPE analysis_charter_status')
