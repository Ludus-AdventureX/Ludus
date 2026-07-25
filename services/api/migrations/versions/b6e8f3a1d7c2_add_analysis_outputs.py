"""add analysis output tables and ready-row immutability triggers

Revision ID: b6e8f3a1d7c2
Revises: f9a4b7e2c8d3
Create Date: 2026-07-25

Task 10 forward revision on top of f9a4b7e2c8d3 (untouched):

* ``claims`` / ``claim_evidence`` / ``challenges`` / ``quality_gate_results`` /
  ``report_artifacts`` / ``export_artifacts`` per 06-data-model.md, all
  workspace-scoped with the composite case/run FK discipline;
* ``strategic_lens_artifacts`` ALREADY EXISTS (d7e2a91c5b48) and is NOT
  recreated — this revision only attaches the ready-row immutability trigger
  to it (18-plan Task 10 Step 8 "数据库权限/trigger 阻止 ready 行更新删除");
* one shared trigger function forbids UPDATE/DELETE on ``ready`` rows of
  ``strategic_lens_artifacts`` and ``report_artifacts``; FK cascade deletes
  (workspace/case/run purge) stay legal via ``pg_trigger_depth()``, and an
  explicit maintenance purge requires ``SET LOCAL ludus.allow_ready_artifact_purge``
  (the repository layer is the second rejection layer of the same rule);
* new PG enums ``statement_type`` / ``generated_content_status`` /
  ``quality_gate_status`` / ``report_artifact_status`` /
  ``export_artifact_status`` (status columns per the decision-os invariant);
  ``entry_status`` / ``evidence_verdict`` / ``formal_analysis_level`` /
  ``origin_mode`` enums are reused, never recreated. Non-status literal sets
  (importance/source/direction/category/severity/type/media) persist as
  CHECK-constrained strings (SIM-02A precedent).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'b6e8f3a1d7c2'
down_revision: Union[str, Sequence[str], None] = 'f9a4b7e2c8d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATEMENT_TYPE = postgresql.ENUM(
    'fact', 'evidence', 'assumption', 'judgment', 'preference', 'unknown',
    name='statement_type', create_type=False,
)
_ENTRY_STATUS = postgresql.ENUM(
    'candidate', 'confirmed', 'rejected', 'expired', 'conflicted',
    name='entry_status', create_type=False,
)
_EVIDENCE_VERDICT = postgresql.ENUM(
    'accepted', 'conditional', 'lead_only', 'rejected',
    name='evidence_verdict', create_type=False,
)
_FORMAL_LEVEL = postgresql.ENUM(
    'focused', 'full', name='formal_analysis_level', create_type=False,
)
_ORIGIN_MODE = postgresql.ENUM(
    'live', 'cached', 'fixture', name='origin_mode', create_type=False,
)
_GENERATED_CONTENT_STATUS = postgresql.ENUM(
    'draft', 'confirmed', 'rejected',
    name='generated_content_status', create_type=False,
)
_QUALITY_GATE_STATUS = postgresql.ENUM(
    'passed', 'blocked', name='quality_gate_status', create_type=False,
)
_REPORT_ARTIFACT_STATUS = postgresql.ENUM(
    'draft', 'ready', name='report_artifact_status', create_type=False,
)
_EXPORT_ARTIFACT_STATUS = postgresql.ENUM(
    'pending', 'ready', 'failed', name='export_artifact_status', create_type=False,
)

_CHECK_STATUSES = "'passed', 'warning', 'severe_failure'"

# One shared guard for both immutable-artifact tables: a row whose OLD status
# is 'ready' can never be UPDATEd, and never directly DELETEd. FK cascade
# deletes (pg_trigger_depth() > 1: workspace/case/run purge) stay legal, and
# an explicit maintenance purge may opt in per transaction with
# SET LOCAL ludus.allow_ready_artifact_purge = 'on'.
_READY_GUARD_FUNCTION = """
CREATE FUNCTION forbid_ready_artifact_mutation() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.status = 'ready' AND pg_trigger_depth() = 1
           AND current_setting('ludus.allow_ready_artifact_purge', true)
               IS DISTINCT FROM 'on' THEN
            RAISE EXCEPTION 'ready % rows are immutable', TG_TABLE_NAME
                USING ERRCODE = 'raise_exception';
        END IF;
        RETURN OLD;
    END IF;
    IF OLD.status = 'ready' THEN
        RAISE EXCEPTION 'ready % rows are immutable', TG_TABLE_NAME
            USING ERRCODE = 'raise_exception';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    """Create the analysis output tables and the ready-row guards."""
    op.execute(
        "CREATE TYPE statement_type AS ENUM "
        "('fact', 'evidence', 'assumption', 'judgment', 'preference', 'unknown')"
    )
    op.execute(
        "CREATE TYPE generated_content_status AS ENUM "
        "('draft', 'confirmed', 'rejected')"
    )
    op.execute("CREATE TYPE quality_gate_status AS ENUM ('passed', 'blocked')")
    op.execute("CREATE TYPE report_artifact_status AS ENUM ('draft', 'ready')")
    op.execute(
        "CREATE TYPE export_artifact_status AS ENUM ('pending', 'ready', 'failed')"
    )

    op.create_table(
        'claims',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('decision_case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('analysis_run_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('statement_type', _STATEMENT_TYPE, nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('importance', sa.String(length=16), nullable=False),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column(
            'responsibility', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        sa.Column(
            'source_span_ids', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'supporting_evidence_ids', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'opposing_evidence_ids', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'assumption_ids', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column('support_score', sa.Float(), nullable=False),
        sa.Column('scope', sa.Text(), nullable=False),
        sa.Column('status', _ENTRY_STATUS, server_default='candidate', nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_claims')),
        sa.UniqueConstraint('workspace_id', 'id', name='uq_claims_workspace_id'),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_claims_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id'],
            ['decision_cases.workspace_id', 'decision_cases.decision_case_id'],
            name='fk_claims_workspace_case', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id', 'analysis_run_id'],
            [
                'analysis_runs.workspace_id',
                'analysis_runs.decision_case_id',
                'analysis_runs.analysis_run_id',
            ],
            name='fk_claims_workspace_case_run', ondelete='CASCADE',
        ),
        sa.CheckConstraint(
            "importance IN ('core', 'supporting')",
            name=op.f('ck_claims_claim_importance_valid'),
        ),
        sa.CheckConstraint(
            "source IN ('user', 'ai', 'tool', 'imported')",
            name=op.f('ck_claims_claim_source_valid'),
        ),
        sa.CheckConstraint(
            'support_score >= 0 AND support_score <= 1',
            name=op.f('ck_claims_claim_support_score_range'),
        ),
    )
    op.create_index('ix_claims_workspace_run', 'claims', ['workspace_id', 'analysis_run_id'])

    op.create_table(
        'claim_evidence',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('claim_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('evidence_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('direction', sa.String(length=16), nullable=False),
        sa.Column('support_strength', sa.Float(), nullable=False),
        sa.Column('rationale', sa.Text(), nullable=False),
        sa.Column('verdict', _EVIDENCE_VERDICT, nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_claim_evidence')),
        sa.UniqueConstraint('workspace_id', 'id', name='uq_claim_evidence_workspace_id'),
        sa.UniqueConstraint(
            'workspace_id', 'claim_id', 'evidence_id', 'direction',
            name='uq_claim_evidence_workspace_link',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_claim_evidence_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'claim_id'],
            ['claims.workspace_id', 'claims.id'],
            name='fk_claim_evidence_workspace_claim', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'evidence_id'],
            ['evidence_items.workspace_id', 'evidence_items.id'],
            name='fk_claim_evidence_workspace_evidence', ondelete='CASCADE',
        ),
        sa.CheckConstraint(
            "direction IN ('supporting', 'opposing')",
            name=op.f('ck_claim_evidence_claim_evidence_direction_valid'),
        ),
        sa.CheckConstraint(
            'support_strength >= 0 AND support_strength <= 1',
            name=op.f('ck_claim_evidence_claim_evidence_strength_range'),
        ),
    )
    op.create_index(
        'ix_claim_evidence_workspace_claim', 'claim_evidence', ['workspace_id', 'claim_id']
    )

    op.create_table(
        'challenges',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('decision_case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('analysis_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('category', sa.String(length=32), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('severity', sa.String(length=16), nullable=False),
        sa.Column(
            'affected_option_ids', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'evidence_ids', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column('mitigation', sa.Text(), nullable=True),
        sa.Column(
            'status', _GENERATED_CONTENT_STATUS, server_default='draft', nullable=False
        ),
        sa.Column('disposition', sa.String(length=32), nullable=True),
        sa.Column('disposition_reason', sa.Text(), server_default='', nullable=False),
        sa.Column(
            'resulting_change', postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_challenges')),
        sa.UniqueConstraint('workspace_id', 'id', name='uq_challenges_workspace_id'),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_challenges_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id'],
            ['decision_cases.workspace_id', 'decision_cases.decision_case_id'],
            name='fk_challenges_workspace_case', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id', 'analysis_run_id'],
            [
                'analysis_runs.workspace_id',
                'analysis_runs.decision_case_id',
                'analysis_runs.analysis_run_id',
            ],
            name='fk_challenges_workspace_case_run', ondelete='CASCADE',
        ),
        sa.CheckConstraint(
            "category IN ('core_assumption', 'counterargument', 'failure_pattern', "
            "'stakeholder_resistance', 'bias', 'fatal_flaw', 'blind_spot')",
            name=op.f('ck_challenges_challenge_category_valid'),
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name=op.f('ck_challenges_challenge_severity_valid'),
        ),
        sa.CheckConstraint(
            "disposition IS NULL OR disposition IN "
            "('accepted_change', 'rejected_with_reason', 'escalated')",
            name=op.f('ck_challenges_challenge_disposition_valid'),
        ),
        sa.CheckConstraint(
            "disposition <> 'rejected_with_reason' OR disposition_reason <> ''",
            name=op.f('ck_challenges_challenge_rejection_requires_reason'),
        ),
        sa.CheckConstraint(
            "status <> 'confirmed' OR severity IN ('low', 'medium') "
            'OR disposition IS NOT NULL',
            name=op.f('ck_challenges_challenge_important_confirmed_requires_disposition'),
        ),
    )
    op.create_index(
        'ix_challenges_workspace_run', 'challenges', ['workspace_id', 'analysis_run_id']
    )

    op.create_table(
        'quality_gate_results',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('decision_case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('analysis_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', _QUALITY_GATE_STATUS, nullable=False),
        sa.Column('evidence_sufficiency_score', sa.Float(), nullable=False),
        sa.Column('evidence_sufficiency_status', sa.String(length=16), nullable=False),
        sa.Column('adversarial_pressure_score', sa.Float(), nullable=False),
        sa.Column('adversarial_pressure_status', sa.String(length=16), nullable=False),
        sa.Column('logic_consistency_score', sa.Float(), nullable=False),
        sa.Column('logic_consistency_status', sa.String(length=16), nullable=False),
        sa.Column('synthesis_deviation_score', sa.Float(), nullable=False),
        sa.Column('synthesis_deviation_status', sa.String(length=16), nullable=False),
        sa.Column('multiplicative_value', sa.Float(), nullable=False),
        sa.Column('deliverable', sa.Boolean(), nullable=False),
        sa.Column(
            'reason_codes', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'quality_profile', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        sa.Column(
            'checked_at', sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_quality_gate_results')),
        sa.UniqueConstraint(
            'workspace_id', 'id', name='uq_quality_gate_results_workspace_id'
        ),
        sa.UniqueConstraint(
            'workspace_id', 'analysis_run_id',
            name='uq_quality_gate_results_workspace_run',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_quality_gate_results_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id'],
            ['decision_cases.workspace_id', 'decision_cases.decision_case_id'],
            name='fk_quality_gate_results_workspace_case', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id', 'analysis_run_id'],
            [
                'analysis_runs.workspace_id',
                'analysis_runs.decision_case_id',
                'analysis_runs.analysis_run_id',
            ],
            name='fk_quality_gate_results_workspace_case_run', ondelete='CASCADE',
        ),
        sa.CheckConstraint(
            f'evidence_sufficiency_status IN ({_CHECK_STATUSES})',
            name=op.f('ck_quality_gate_results_gate_evidence_status_valid'),
        ),
        sa.CheckConstraint(
            f'adversarial_pressure_status IN ({_CHECK_STATUSES})',
            name=op.f('ck_quality_gate_results_gate_adversarial_status_valid'),
        ),
        sa.CheckConstraint(
            f'logic_consistency_status IN ({_CHECK_STATUSES})',
            name=op.f('ck_quality_gate_results_gate_logic_status_valid'),
        ),
        sa.CheckConstraint(
            f'synthesis_deviation_status IN ({_CHECK_STATUSES})',
            name=op.f('ck_quality_gate_results_gate_synthesis_status_valid'),
        ),
        sa.CheckConstraint(
            'evidence_sufficiency_score >= 0 AND evidence_sufficiency_score <= 1 AND '
            'adversarial_pressure_score >= 0 AND adversarial_pressure_score <= 1 AND '
            'logic_consistency_score >= 0 AND logic_consistency_score <= 1 AND '
            'synthesis_deviation_score >= 0 AND synthesis_deviation_score <= 1 AND '
            'multiplicative_value >= 0 AND multiplicative_value <= 1',
            name=op.f('ck_quality_gate_results_gate_scores_in_unit_interval'),
        ),
        sa.CheckConstraint(
            "(status = 'passed') = deliverable",
            name=op.f('ck_quality_gate_results_gate_blocked_never_deliverable'),
        ),
    )
    op.create_index(
        'ix_quality_gate_results_workspace_case',
        'quality_gate_results',
        ['workspace_id', 'decision_case_id'],
    )

    op.create_table(
        'report_artifacts',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('analysis_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_judgment_set_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_dissent_record_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('decision_case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('case_version', sa.BigInteger(), nullable=False),
        sa.Column('analysis_level', _FORMAL_LEVEL, nullable=False),
        sa.Column('type', sa.String(length=16), nullable=False),
        sa.Column('status', _REPORT_ARTIFACT_STATUS, server_default='draft', nullable=False),
        sa.Column(
            'structured_content', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        sa.Column('content_hash', sa.String(length=256), nullable=False),
        sa.Column('origin_modes', postgresql.ARRAY(_ORIGIN_MODE), nullable=False),
        sa.Column(
            'validation', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_report_artifacts')),
        sa.UniqueConstraint('workspace_id', 'id', name='uq_report_artifacts_workspace_id'),
        sa.UniqueConstraint(
            'workspace_id', 'analysis_run_id', name='uq_report_artifacts_workspace_run'
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_report_artifacts_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id'],
            ['decision_cases.workspace_id', 'decision_cases.decision_case_id'],
            name='fk_report_artifacts_workspace_case', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id', 'analysis_run_id'],
            [
                'analysis_runs.workspace_id',
                'analysis_runs.decision_case_id',
                'analysis_runs.analysis_run_id',
            ],
            name='fk_report_artifacts_workspace_case_run', ondelete='CASCADE',
        ),
        sa.CheckConstraint(
            "type IN ('brief', 'detailed')",
            name=op.f('ck_report_artifacts_report_type_valid'),
        ),
        sa.CheckConstraint(
            "(analysis_level = 'focused' AND type = 'brief') "
            "OR (analysis_level = 'full' AND type = 'detailed')",
            name=op.f('ck_report_artifacts_report_level_type_discriminant'),
        ),
        sa.CheckConstraint(
            'case_version > 0',
            name=op.f('ck_report_artifacts_report_case_version_positive'),
        ),
        sa.CheckConstraint(
            "content_hash <> ''",
            name=op.f('ck_report_artifacts_report_content_hash_not_empty'),
        ),
        sa.CheckConstraint(
            "status = 'ready' OR published_at IS NULL",
            name=op.f('ck_report_artifacts_report_published_requires_ready'),
        ),
    )
    op.create_index(
        'ix_report_artifacts_workspace_case',
        'report_artifacts',
        ['workspace_id', 'decision_case_id'],
    )

    op.create_table(
        'export_artifacts',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('report_artifact_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('analysis_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('decision_case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('case_version', sa.BigInteger(), nullable=False),
        sa.Column('type', sa.String(length=8), nullable=False),
        sa.Column(
            'status', _EXPORT_ARTIFACT_STATUS, server_default='pending', nullable=False
        ),
        sa.Column(
            'storage_provider', sa.String(length=32),
            server_default='filesystem', nullable=False,
        ),
        sa.Column('storage_path', sa.String(length=1024), nullable=True),
        sa.Column('sha256', sa.String(length=64), nullable=True),
        sa.Column('byte_size', sa.BigInteger(), nullable=True),
        sa.Column('media_type', sa.String(length=64), nullable=False),
        sa.Column('renderer_version', sa.String(length=64), nullable=False),
        sa.Column('origin_modes', postgresql.ARRAY(_ORIGIN_MODE), nullable=False),
        sa.Column('error_code', sa.String(length=64), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_export_artifacts')),
        sa.UniqueConstraint('workspace_id', 'id', name='uq_export_artifacts_workspace_id'),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_export_artifacts_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'report_artifact_id'],
            ['report_artifacts.workspace_id', 'report_artifacts.id'],
            name='fk_export_artifacts_workspace_report', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id', 'analysis_run_id'],
            [
                'analysis_runs.workspace_id',
                'analysis_runs.decision_case_id',
                'analysis_runs.analysis_run_id',
            ],
            name='fk_export_artifacts_workspace_case_run', ondelete='CASCADE',
        ),
        sa.CheckConstraint(
            "type IN ('html', 'pdf')",
            name=op.f('ck_export_artifacts_export_type_valid'),
        ),
        sa.CheckConstraint(
            "media_type IN ('text/html', 'application/pdf')",
            name=op.f('ck_export_artifacts_export_media_type_valid'),
        ),
        sa.CheckConstraint(
            "storage_provider IN ('filesystem')",
            name=op.f('ck_export_artifacts_export_storage_provider_valid'),
        ),
        sa.CheckConstraint(
            "(type = 'html' AND media_type = 'text/html') "
            "OR (type = 'pdf' AND media_type = 'application/pdf')",
            name=op.f('ck_export_artifacts_export_type_media_pairing'),
        ),
        sa.CheckConstraint(
            'case_version > 0',
            name=op.f('ck_export_artifacts_export_case_version_positive'),
        ),
    )
    op.create_index(
        'ix_export_artifacts_workspace_report',
        'export_artifacts',
        ['workspace_id', 'report_artifact_id'],
    )

    # Ready-row immutability, database layer (repository is the second layer).
    # strategic_lens_artifacts pre-exists (d7e2a91c5b48) — trigger only, no
    # table recreation.
    op.execute(_READY_GUARD_FUNCTION)
    op.execute(
        'CREATE TRIGGER trg_strategic_lens_artifacts_ready_immutable '
        'BEFORE UPDATE OR DELETE ON strategic_lens_artifacts '
        'FOR EACH ROW EXECUTE FUNCTION forbid_ready_artifact_mutation()'
    )
    op.execute(
        'CREATE TRIGGER trg_report_artifacts_ready_immutable '
        'BEFORE UPDATE OR DELETE ON report_artifacts '
        'FOR EACH ROW EXECUTE FUNCTION forbid_ready_artifact_mutation()'
    )


def downgrade() -> None:
    """Drop the analysis output tables, triggers, and the statement enum."""
    op.execute(
        'DROP TRIGGER trg_report_artifacts_ready_immutable ON report_artifacts'
    )
    op.execute(
        'DROP TRIGGER trg_strategic_lens_artifacts_ready_immutable '
        'ON strategic_lens_artifacts'
    )
    op.execute('DROP FUNCTION forbid_ready_artifact_mutation()')
    op.drop_index('ix_export_artifacts_workspace_report', table_name='export_artifacts')
    op.drop_table('export_artifacts')
    op.drop_index('ix_report_artifacts_workspace_case', table_name='report_artifacts')
    op.drop_table('report_artifacts')
    op.drop_index(
        'ix_quality_gate_results_workspace_case', table_name='quality_gate_results'
    )
    op.drop_table('quality_gate_results')
    op.drop_index('ix_challenges_workspace_run', table_name='challenges')
    op.drop_table('challenges')
    op.drop_index('ix_claim_evidence_workspace_claim', table_name='claim_evidence')
    op.drop_table('claim_evidence')
    op.drop_index('ix_claims_workspace_run', table_name='claims')
    op.drop_table('claims')
    op.execute('DROP TYPE export_artifact_status')
    op.execute('DROP TYPE report_artifact_status')
    op.execute('DROP TYPE quality_gate_status')
    op.execute('DROP TYPE generated_content_status')
    op.execute('DROP TYPE statement_type')
