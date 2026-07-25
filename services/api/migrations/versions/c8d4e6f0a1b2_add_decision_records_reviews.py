"""add decision records, reviews and lifecycle events

Revision ID: c8d4e6f0a1b2
Revises: a7c3e9f1b5d8
Create Date: 2026-07-25

Release integration closure for signoff + append-only DecisionRecord + Review.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'c8d4e6f0a1b2'
down_revision: Union[str, Sequence[str], None] = 'a7c3e9f1b5d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ORIGIN_MODE = postgresql.ENUM('live', 'cached', 'fixture', name='origin_mode', create_type=False)
_DECISION_STAGE = postgresql.ENUM(
    'draft', 'scoped', 'ready', 'running', 'review', 'pending_signoff', 'decided', 'monitoring',
    name='decision_lifecycle_stage', create_type=False,
)
_DOMAIN_EVENT_ACTOR = postgresql.ENUM('user', 'system', 'worker', name='domain_event_actor', create_type=False)

_APPEND_ONLY_FUNCTION = """
CREATE FUNCTION forbid_decision_append_only_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION '% is append-only', TG_TABLE_NAME USING ERRCODE = 'check_violation';
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.create_table(
        'decision_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('decision_case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('case_version', sa.Integer(), nullable=False),
        sa.Column('record_kind', sa.String(length=16), nullable=False),
        sa.Column('supersedes_decision_record_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('signoff_request_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('payload_hash', sa.String(length=256), nullable=False),
        sa.Column('source_analysis_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_report_artifact_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_judgment_set_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_dissent_record_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_causal_graph_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('source_causal_graph_version_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('source_simulation_run_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('origin_modes', postgresql.ARRAY(_ORIGIN_MODE), server_default=sa.text("'{}'::origin_mode[]"), nullable=False),
        sa.Column('system_recommendation', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('selected_option_id', sa.String(length=200), nullable=False),
        sa.Column('decision_text', sa.Text(), nullable=False),
        sa.Column('conditions', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('thresholds', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('exit_criteria', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('action_items', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('leading_indicators', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('accepted_unknown_ids', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('review_date', sa.String(length=32), nullable=False),
        sa.Column('signed_by_user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('signed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('signature_statement', sa.Text(), nullable=False),
        sa.Column('signature_hash', sa.String(length=256), nullable=False),
        sa.Column('record_hash', sa.String(length=256), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_decision_records')),
        sa.UniqueConstraint('workspace_id', 'id', name='uq_decision_records_workspace_id'),
        sa.UniqueConstraint('workspace_id', 'decision_case_id', 'id', name='uq_decision_records_workspace_case_id'),
        sa.UniqueConstraint('workspace_id', 'signoff_request_id', name='uq_decision_records_workspace_signoff_request'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_decision_records_workspace_id_workspaces'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id', 'decision_case_id'], ['decision_cases.workspace_id', 'decision_cases.decision_case_id'], name='fk_decision_records_workspace_case', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id', 'decision_case_id', 'signoff_request_id'], ['signoff_requests.workspace_id', 'signoff_requests.decision_case_id', 'signoff_requests.id'], name='fk_decision_records_workspace_signoff_request', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['workspace_id', 'decision_case_id', 'supersedes_decision_record_id'], ['decision_records.workspace_id', 'decision_records.decision_case_id', 'decision_records.id'], name='fk_decision_records_workspace_supersedes', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['signed_by_user_id'], ['users.id'], name=op.f('fk_decision_records_signed_by_user_id_users'), ondelete='RESTRICT'),
        sa.CheckConstraint('case_version > 0', name='decision_record_case_version_positive'),
        sa.CheckConstraint("record_kind IN ('original', 'revision')", name='decision_record_kind_valid'),
        sa.CheckConstraint("(record_kind = 'original' AND supersedes_decision_record_id IS NULL) OR (record_kind = 'revision' AND supersedes_decision_record_id IS NOT NULL)", name='decision_record_revision_supersedes'),
        sa.CheckConstraint("payload_hash <> ''", name='decision_record_payload_hash_not_empty'),
        sa.CheckConstraint("signature_hash <> ''", name='decision_record_signature_hash_not_empty'),
        sa.CheckConstraint("record_hash <> ''", name='decision_record_record_hash_not_empty'),
    )
    op.create_index('ix_decision_records_workspace_case_created', 'decision_records', ['workspace_id', 'decision_case_id', 'created_at'])

    op.create_table(
        'decision_reviews',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('decision_case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('decision_record_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_case_version', sa.Integer(), nullable=False),
        sa.Column('source_analysis_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_causal_graph_version_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('source_simulation_run_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('review_date', sa.String(length=32), nullable=False),
        sa.Column('outcome', sa.String(length=24), nullable=False),
        sa.Column('recommendation_adoption', sa.String(length=24), nullable=False),
        sa.Column('execution_assessment', sa.String(length=32), nullable=False),
        sa.Column('decision_process_assessment', sa.String(length=16), nullable=False),
        sa.Column('outcome_quality', sa.String(length=24), nullable=False),
        sa.Column('observed_indicator_values', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('threshold_breaches', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('external_changes', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('actual_outcomes', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('assumption_results', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('lessons', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('next_decision_changes', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('next_review_date', sa.String(length=32), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_decision_reviews')),
        sa.UniqueConstraint('workspace_id', 'id', name='uq_decision_reviews_workspace_id'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_decision_reviews_workspace_id_workspaces'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id', 'decision_case_id'], ['decision_cases.workspace_id', 'decision_cases.decision_case_id'], name='fk_decision_reviews_workspace_case', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id', 'decision_case_id', 'decision_record_id'], ['decision_records.workspace_id', 'decision_records.decision_case_id', 'decision_records.id'], name='fk_decision_reviews_workspace_decision_record', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_decision_reviews_created_by_users'), ondelete='RESTRICT'),
        sa.CheckConstraint('source_case_version > 0', name='decision_review_case_version_positive'),
        sa.CheckConstraint("outcome IN ('on_track', 'adjust', 'reverse', 'close')", name='decision_review_outcome_valid'),
        sa.CheckConstraint("recommendation_adoption IN ('adopted', 'partially_adopted', 'not_adopted')", name='decision_review_recommendation_adoption_valid'),
        sa.CheckConstraint("execution_assessment IN ('as_planned', 'minor_deviation', 'major_deviation', 'not_executed')", name='decision_review_execution_assessment_valid'),
        sa.CheckConstraint("decision_process_assessment IN ('sound', 'mixed', 'flawed')", name='decision_review_process_assessment_valid'),
        sa.CheckConstraint("outcome_quality IN ('positive', 'mixed', 'negative', 'not_yet_observable')", name='decision_review_outcome_quality_valid'),
    )
    op.create_index('ix_decision_reviews_workspace_decision_created', 'decision_reviews', ['workspace_id', 'decision_record_id', 'created_at'])

    op.create_table(
        'decision_lifecycle_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('decision_case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('from_stage', _DECISION_STAGE, nullable=False),
        sa.Column('to_stage', _DECISION_STAGE, nullable=False),
        sa.Column('actor_type', _DOMAIN_EVENT_ACTOR, nullable=False),
        sa.Column('actor_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('command_type', sa.String(length=80), nullable=False),
        sa.Column('command_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('payload_hash', sa.String(length=256), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_decision_lifecycle_events')),
        sa.UniqueConstraint('workspace_id', 'id', name='uq_decision_lifecycle_events_workspace_id'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], name=op.f('fk_decision_lifecycle_events_workspace_id_workspaces'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id', 'decision_case_id'], ['decision_cases.workspace_id', 'decision_cases.decision_case_id'], name='fk_decision_lifecycle_events_workspace_case', ondelete='CASCADE'),
        sa.CheckConstraint("payload_hash <> ''", name='decision_lifecycle_event_payload_hash_not_empty'),
    )
    op.create_index('ix_decision_lifecycle_events_workspace_case_created', 'decision_lifecycle_events', ['workspace_id', 'decision_case_id', 'created_at'])

    op.execute(_APPEND_ONLY_FUNCTION)
    op.execute("CREATE TRIGGER decision_records_append_only BEFORE UPDATE OR DELETE ON decision_records FOR EACH ROW EXECUTE FUNCTION forbid_decision_append_only_mutation()")
    op.execute("CREATE TRIGGER decision_lifecycle_events_append_only BEFORE UPDATE OR DELETE ON decision_lifecycle_events FOR EACH ROW EXECUTE FUNCTION forbid_decision_append_only_mutation()")


def downgrade() -> None:
    op.execute('DROP TRIGGER IF EXISTS decision_lifecycle_events_append_only ON decision_lifecycle_events')
    op.execute('DROP TRIGGER IF EXISTS decision_records_append_only ON decision_records')
    op.execute('DROP FUNCTION IF EXISTS forbid_decision_append_only_mutation()')
    op.drop_index('ix_decision_lifecycle_events_workspace_case_created', table_name='decision_lifecycle_events')
    op.drop_table('decision_lifecycle_events')
    op.drop_index('ix_decision_reviews_workspace_decision_created', table_name='decision_reviews')
    op.drop_table('decision_reviews')
    op.drop_index('ix_decision_records_workspace_case_created', table_name='decision_records')
    op.drop_table('decision_records')
