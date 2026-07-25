"""add evidence ledger and information quality gateway tables

Revision ID: e7f3a2c9d5b1
Revises: b2c7e9d4a1f6
Create Date: 2026-07-25

Task 8 (case_api_data) forward revision on top of b2c7e9d4a1f6 (untouched):

* ``retrieval_tasks`` / ``raw_artifacts`` / ``quality_assessments`` /
  ``evidence_items`` / ``evidence_relations`` per 06-data-model.md, all
  workspace-scoped with the composite case/run FK discipline used across the
  codebase (tenant-scoped SELECT + uniform CASE_NOT_FOUND stays enforceable
  at the database layer).
* One new PG enum ``evidence_verdict`` sourced from the canonical
  ``app.types.EvidenceVerdict`` plus ``retrieval_task_status`` built from the
  canonical 06-data-model literal set (status-like columns must be enums per
  the decision-os invariants suite); the shared ``origin_mode`` enum is
  reused, never recreated (CCR-20260724-Ways-01 precedent).
* Canonical literal sets without an ``app.types`` enum (stable tool names,
  raw artifact kinds, source grades, freshness statuses, relation kinds)
  persist as CHECK-constrained strings following the SIM-02A
  ``response_kind`` precedent; no parallel Python enums are invented.
* RawArtifact/QualityAssessment rows are immutable by construction (no
  update surface); ``storage_provider`` is locked to ``filesystem`` and
  ``storage_path`` must stay a workspace-scoped relative pointer.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'e7f3a2c9d5b1'
down_revision: Union[str, Sequence[str], None] = 'b2c7e9d4a1f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ORIGIN_MODE = postgresql.ENUM(
    'live', 'cached', 'fixture', name='origin_mode', create_type=False
)
# Column references never auto-create the type; upgrade()/downgrade() manage
# the enum's lifecycle exactly once.
_EVIDENCE_VERDICT = postgresql.ENUM(
    'accepted', 'conditional', 'lead_only', 'rejected',
    name='evidence_verdict', create_type=False,
)
_RETRIEVAL_TASK_STATUS = postgresql.ENUM(
    'queued', 'running', 'completed', 'failed', 'cancelled',
    name='retrieval_task_status', create_type=False,
)


def upgrade() -> None:
    """Create the five evidence ledger tables and their two new enums."""
    op.execute(
        "CREATE TYPE evidence_verdict AS ENUM "
        "('accepted', 'conditional', 'lead_only', 'rejected')"
    )
    op.execute(
        "CREATE TYPE retrieval_task_status AS ENUM "
        "('queued', 'running', 'completed', 'failed', 'cancelled')"
    )

    op.create_table(
        'retrieval_tasks',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('decision_case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('analysis_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('stable_tool_name', sa.String(length=40), nullable=False),
        sa.Column('query_summary', sa.Text(), nullable=False),
        sa.Column('input_hash', sa.String(length=256), nullable=False),
        sa.Column(
            'status', _RETRIEVAL_TASK_STATUS,
            server_default='queued', nullable=False,
        ),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_retrieval_tasks')),
        sa.UniqueConstraint('workspace_id', 'id', name='uq_retrieval_tasks_workspace_id'),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_retrieval_tasks_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id'],
            ['decision_cases.workspace_id', 'decision_cases.decision_case_id'],
            name='fk_retrieval_tasks_workspace_case', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id', 'analysis_run_id'],
            [
                'analysis_runs.workspace_id',
                'analysis_runs.decision_case_id',
                'analysis_runs.analysis_run_id',
            ],
            name='fk_retrieval_tasks_workspace_case_run', ondelete='CASCADE',
        ),
        sa.CheckConstraint(
            "stable_tool_name IN ('search_web', 'fetch_url', 'crawl_site', "
            "'extract_document', 'get_source_status')",
            name=op.f('ck_retrieval_tasks_stable_tool_name_canonical'),
        ),
        sa.CheckConstraint(
            "input_hash <> ''", name=op.f('ck_retrieval_tasks_input_hash_not_empty')
        ),
        sa.CheckConstraint(
            'completed_at IS NULL OR completed_at >= created_at',
            name=op.f('ck_retrieval_tasks_completed_after_created'),
        ),
    )
    op.create_index(
        'ix_retrieval_tasks_workspace_run_status',
        'retrieval_tasks',
        ['workspace_id', 'analysis_run_id', 'status'],
    )

    op.create_table(
        'raw_artifacts',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('decision_case_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('analysis_run_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('retrieval_task_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('connector_call_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('kind', sa.String(length=30), nullable=False),
        sa.Column('original_name', sa.String(length=400), nullable=True),
        sa.Column('media_type', sa.String(length=160), nullable=False),
        sa.Column('byte_size', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column(
            'storage_provider', sa.String(length=30),
            server_default='filesystem', nullable=False,
        ),
        sa.Column('storage_path', sa.Text(), nullable=False),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('origin_mode', _ORIGIN_MODE, nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_raw_artifacts')),
        sa.UniqueConstraint('workspace_id', 'id', name='uq_raw_artifacts_workspace_id'),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_raw_artifacts_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id'],
            ['decision_cases.workspace_id', 'decision_cases.decision_case_id'],
            name='fk_raw_artifacts_workspace_case', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id', 'analysis_run_id'],
            [
                'analysis_runs.workspace_id',
                'analysis_runs.decision_case_id',
                'analysis_runs.analysis_run_id',
            ],
            name='fk_raw_artifacts_workspace_case_run', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'retrieval_task_id'],
            ['retrieval_tasks.workspace_id', 'retrieval_tasks.id'],
            name='fk_raw_artifacts_workspace_retrieval_task', ondelete='RESTRICT',
        ),
        sa.CheckConstraint(
            "kind IN ('web_page', 'provider_result', 'uploaded_file')",
            name=op.f('ck_raw_artifacts_kind_canonical'),
        ),
        sa.CheckConstraint(
            'byte_size >= 0', name=op.f('ck_raw_artifacts_byte_size_non_negative')
        ),
        sa.CheckConstraint(
            "sha256 ~ '^[0-9a-f]{64}$'", name=op.f('ck_raw_artifacts_sha256_hex')
        ),
        sa.CheckConstraint(
            "storage_provider = 'filesystem'",
            name=op.f('ck_raw_artifacts_storage_provider_locked'),
        ),
        sa.CheckConstraint(
            "storage_path <> ''", name=op.f('ck_raw_artifacts_storage_path_not_empty')
        ),
        sa.CheckConstraint(
            "storage_path NOT LIKE '/%' AND storage_path NOT LIKE '%..%' "
            "AND storage_path NOT LIKE '%:%'",
            name=op.f('ck_raw_artifacts_storage_path_workspace_relative'),
        ),
        sa.CheckConstraint(
            'analysis_run_id IS NULL OR decision_case_id IS NOT NULL',
            name=op.f('ck_raw_artifacts_run_requires_case'),
        ),
    )
    op.create_index(
        'ix_raw_artifacts_workspace_run', 'raw_artifacts',
        ['workspace_id', 'analysis_run_id'],
    )
    op.create_index(
        'ix_raw_artifacts_workspace_sha256', 'raw_artifacts',
        ['workspace_id', 'sha256'],
    )

    op.create_table(
        'quality_assessments',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('decision_case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('analysis_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('raw_artifact_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('authenticity', sa.Float(), nullable=False),
        sa.Column('source_quality', sa.Float(), nullable=False),
        sa.Column('relevance', sa.Float(), nullable=False),
        sa.Column('freshness', sa.Float(), nullable=False),
        sa.Column('applicability', sa.Float(), nullable=False),
        sa.Column('independence', sa.Float(), nullable=False),
        sa.Column('extraction_reliability', sa.Float(), nullable=False),
        sa.Column(
            'bias_flags', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'completeness_warnings', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'conflict_group_ids', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column('verdict', _EVIDENCE_VERDICT, nullable=False),
        sa.Column(
            'reason_codes', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'assessed_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_quality_assessments')),
        sa.UniqueConstraint(
            'workspace_id', 'id', name='uq_quality_assessments_workspace_id'
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_quality_assessments_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id'],
            ['decision_cases.workspace_id', 'decision_cases.decision_case_id'],
            name='fk_quality_assessments_workspace_case', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id', 'analysis_run_id'],
            [
                'analysis_runs.workspace_id',
                'analysis_runs.decision_case_id',
                'analysis_runs.analysis_run_id',
            ],
            name='fk_quality_assessments_workspace_case_run', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'raw_artifact_id'],
            ['raw_artifacts.workspace_id', 'raw_artifacts.id'],
            name='fk_quality_assessments_workspace_raw_artifact', ondelete='RESTRICT',
        ),
        sa.CheckConstraint(
            'authenticity >= 0 AND authenticity <= 1',
            name=op.f('ck_quality_assessments_authenticity_range'),
        ),
        sa.CheckConstraint(
            'source_quality >= 0 AND source_quality <= 1',
            name=op.f('ck_quality_assessments_source_quality_range'),
        ),
        sa.CheckConstraint(
            'relevance >= 0 AND relevance <= 1',
            name=op.f('ck_quality_assessments_relevance_range'),
        ),
        sa.CheckConstraint(
            'freshness >= 0 AND freshness <= 1',
            name=op.f('ck_quality_assessments_freshness_range'),
        ),
        sa.CheckConstraint(
            'applicability >= 0 AND applicability <= 1',
            name=op.f('ck_quality_assessments_applicability_range'),
        ),
        sa.CheckConstraint(
            'independence >= 0 AND independence <= 1',
            name=op.f('ck_quality_assessments_independence_range'),
        ),
        sa.CheckConstraint(
            'extraction_reliability >= 0 AND extraction_reliability <= 1',
            name=op.f('ck_quality_assessments_extraction_reliability_range'),
        ),
    )
    op.create_index(
        'ix_quality_assessments_workspace_run', 'quality_assessments',
        ['workspace_id', 'analysis_run_id'],
    )

    op.create_table(
        'evidence_items',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('decision_case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('analysis_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('file_path', sa.Text(), nullable=True),
        sa.Column('source_domain', sa.String(length=255), nullable=True),
        sa.Column('source_grade', sa.String(length=20), nullable=False),
        sa.Column('snippet', sa.Text(), nullable=False),
        sa.Column('source_record_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            'source_span_ids', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'supports_claim_ids', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'contradicts_claim_ids', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('retrieved_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            'freshness_status', sa.String(length=10),
            server_default='unknown', nullable=False,
        ),
        sa.Column('relevance', sa.Float(), nullable=False),
        sa.Column('bias', sa.Text(), nullable=True),
        sa.Column('conflict_group_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            'independent_source_group_id', postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column('verdict', _EVIDENCE_VERDICT, nullable=False),
        sa.Column(
            'verdict_reason_codes', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            'applicability_limits', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column('origin_mode', _ORIGIN_MODE, nullable=False),
        sa.Column('raw_artifact_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('quality_assessment_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_evidence_items')),
        sa.UniqueConstraint('workspace_id', 'id', name='uq_evidence_items_workspace_id'),
        sa.UniqueConstraint(
            'workspace_id', 'decision_case_id', 'id',
            name='uq_evidence_items_workspace_case_id',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_evidence_items_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id'],
            ['decision_cases.workspace_id', 'decision_cases.decision_case_id'],
            name='fk_evidence_items_workspace_case', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id', 'analysis_run_id'],
            [
                'analysis_runs.workspace_id',
                'analysis_runs.decision_case_id',
                'analysis_runs.analysis_run_id',
            ],
            name='fk_evidence_items_workspace_case_run', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id', 'source_record_id'],
            [
                'source_records.workspace_id',
                'source_records.decision_case_id',
                'source_records.id',
            ],
            name='fk_evidence_items_workspace_case_source', ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'raw_artifact_id'],
            ['raw_artifacts.workspace_id', 'raw_artifacts.id'],
            name='fk_evidence_items_workspace_raw_artifact', ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'quality_assessment_id'],
            ['quality_assessments.workspace_id', 'quality_assessments.id'],
            name='fk_evidence_items_workspace_quality_assessment', ondelete='RESTRICT',
        ),
        sa.CheckConstraint(
            "source_grade IN ('L1_primary', 'L2_reputable', 'L3_industry', "
            "'L4_general', 'L5_opinion', 'L6_unverified')",
            name=op.f('ck_evidence_items_source_grade_canonical'),
        ),
        sa.CheckConstraint(
            "freshness_status IN ('fresh', 'aging', 'stale', 'unknown')",
            name=op.f('ck_evidence_items_freshness_status_canonical'),
        ),
        sa.CheckConstraint(
            'relevance >= 0 AND relevance <= 1',
            name=op.f('ck_evidence_items_relevance_range'),
        ),
        sa.CheckConstraint("title <> ''", name=op.f('ck_evidence_items_title_not_empty')),
        sa.CheckConstraint(
            "snippet <> ''", name=op.f('ck_evidence_items_snippet_not_empty')
        ),
        sa.CheckConstraint(
            "verdict <> 'conditional' OR applicability_limits <> '[]'::jsonb",
            name=op.f('ck_evidence_items_conditional_requires_limits'),
        ),
    )
    op.create_index(
        'ix_evidence_items_workspace_run', 'evidence_items',
        ['workspace_id', 'analysis_run_id'],
    )
    op.create_index(
        'ix_evidence_items_workspace_run_group', 'evidence_items',
        ['workspace_id', 'analysis_run_id', 'independent_source_group_id'],
    )
    op.create_index(
        'ix_evidence_items_workspace_run_conflict', 'evidence_items',
        ['workspace_id', 'analysis_run_id', 'conflict_group_id'],
    )

    op.create_table(
        'evidence_relations',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('decision_case_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('from_evidence_item_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('to_evidence_item_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('kind', sa.String(length=30), nullable=False),
        sa.Column('group_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('rationale', sa.Text(), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_evidence_relations')),
        sa.UniqueConstraint(
            'workspace_id', 'id', name='uq_evidence_relations_workspace_id'
        ),
        sa.UniqueConstraint(
            'workspace_id', 'from_evidence_item_id', 'to_evidence_item_id', 'kind',
            name='uq_evidence_relations_workspace_pair_kind',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_evidence_relations_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id'],
            ['decision_cases.workspace_id', 'decision_cases.decision_case_id'],
            name='fk_evidence_relations_workspace_case', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id', 'from_evidence_item_id'],
            [
                'evidence_items.workspace_id',
                'evidence_items.decision_case_id',
                'evidence_items.id',
            ],
            name='fk_evidence_relations_workspace_case_from', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id', 'to_evidence_item_id'],
            [
                'evidence_items.workspace_id',
                'evidence_items.decision_case_id',
                'evidence_items.id',
            ],
            name='fk_evidence_relations_workspace_case_to', ondelete='CASCADE',
        ),
        sa.CheckConstraint(
            "kind IN ('same_source_group', 'conflicts_with', 'corroborates')",
            name=op.f('ck_evidence_relations_kind_canonical'),
        ),
        sa.CheckConstraint(
            'from_evidence_item_id <> to_evidence_item_id',
            name=op.f('ck_evidence_relations_no_self_relation'),
        ),
    )
    op.create_index(
        'ix_evidence_relations_workspace_group', 'evidence_relations',
        ['workspace_id', 'group_id'],
    )


def downgrade() -> None:
    """Drop the five evidence tables and the two Task 8 enums only."""
    op.drop_index('ix_evidence_relations_workspace_group', table_name='evidence_relations')
    op.drop_table('evidence_relations')
    op.drop_index('ix_evidence_items_workspace_run_conflict', table_name='evidence_items')
    op.drop_index('ix_evidence_items_workspace_run_group', table_name='evidence_items')
    op.drop_index('ix_evidence_items_workspace_run', table_name='evidence_items')
    op.drop_table('evidence_items')
    op.drop_index(
        'ix_quality_assessments_workspace_run', table_name='quality_assessments'
    )
    op.drop_table('quality_assessments')
    op.drop_index('ix_raw_artifacts_workspace_sha256', table_name='raw_artifacts')
    op.drop_index('ix_raw_artifacts_workspace_run', table_name='raw_artifacts')
    op.drop_table('raw_artifacts')
    op.drop_index(
        'ix_retrieval_tasks_workspace_run_status', table_name='retrieval_tasks'
    )
    op.drop_table('retrieval_tasks')
    op.execute('DROP TYPE retrieval_task_status')
    op.execute('DROP TYPE evidence_verdict')
