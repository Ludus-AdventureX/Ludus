"""add canonical simulation graph contract

Revision ID: a3f8c2d47e19
Revises: d7e2a91c5b48
Create Date: 2026-07-24

CCR-20260724-SIM-01 (accepted with corrections B-1..B-8): eight graph
aggregate tables plus four composite FKs on the pre-existing simulation_runs
frozen-reference columns. The FKs are added with an orphan preflight, then
ADD CONSTRAINT ... NOT VALID, then VALIDATE CONSTRAINT, so the migration
never assumes simulation_runs is empty. Six new PG enums are created;
ConstraintComparison deliberately has no PG enum (JSONB rules only).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'a3f8c2d47e19'
down_revision: Union[str, Sequence[str], None] = 'd7e2a91c5b48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# origin_mode predates this revision and is shared; never recreate it.
ORIGIN_MODE = postgresql.ENUM('live', 'cached', 'fixture', name='origin_mode', create_type=False)

_SIMULATION_RUN_FKS: tuple[tuple[str, str, str, str], ...] = (
    # (constraint name, local column, target table, target id column)
    ('fk_simulation_runs_workspace_graph_version', 'graph_version_id', 'graph_versions', 'id'),
    ('fk_simulation_runs_workspace_strategy_version', 'strategy_version_id', 'strategy_versions', 'id'),
    ('fk_simulation_runs_workspace_scenario_version', 'scenario_version_id', 'scenario_versions', 'id'),
    ('fk_simulation_runs_workspace_score_definition', 'score_definition_id', 'score_definitions', 'id'),
)


def _uuid(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _jsonb(name: str, default: str) -> sa.Column:
    return sa.Column(
        name, postgresql.JSONB(astext_type=sa.Text()),
        server_default=sa.text(f"'{default}'::jsonb"), nullable=False,
    )


def _origin_modes() -> sa.Column:
    return sa.Column(
        'origin_modes', postgresql.ARRAY(ORIGIN_MODE),
        server_default=sa.text("'{}'::origin_mode[]"), nullable=False,
    )


def _created_at() -> sa.Column:
    return sa.Column(
        'created_at', sa.DateTime(timezone=True),
        server_default=sa.text('now()'), nullable=False,
    )


def upgrade() -> None:
    """Create the graph aggregate and wire simulation_runs frozen references."""
    op.create_table(
        'causal_graphs',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        _uuid('workspace_id'),
        _uuid('decision_case_id'),
        _uuid('report_artifact_id'),
        _uuid('current_graph_version_id', nullable=True),
        sa.Column('title', sa.String(length=240), nullable=False),
        _origin_modes(),
        _created_at(),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_causal_graphs')),
        sa.UniqueConstraint('workspace_id', 'id', name='uq_causal_graphs_workspace_id'),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_causal_graphs_workspace_id_workspaces'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id'],
            ['decision_cases.workspace_id', 'decision_cases.decision_case_id'],
            name='fk_causal_graphs_workspace_case', ondelete='CASCADE',
        ),
    )
    op.create_index(
        'ix_causal_graphs_workspace_case', 'causal_graphs', ['workspace_id', 'decision_case_id']
    )

    op.create_table(
        'graph_versions',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        _uuid('workspace_id'),
        _uuid('graph_id'),
        _uuid('decision_case_id'),
        sa.Column('case_version', sa.Integer(), nullable=False),
        _uuid('source_report_artifact_id'),
        sa.Column('version', sa.Integer(), nullable=False),
        _uuid('branch_id', nullable=True),
        _uuid('parent_version_id', nullable=True),
        _uuid('source_graph_version_id', nullable=True),
        sa.Column(
            'status',
            sa.Enum('draft', 'confirmed', 'archived', name='graph_version_status'),
            server_default='draft', nullable=False,
        ),
        _jsonb('provenance', '[]'),
        _origin_modes(),
        sa.Column('title', sa.String(length=240), nullable=False),
        sa.Column('content_hash', sa.String(length=256), nullable=False),
        _uuid('created_by'),
        _created_at(),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_graph_versions')),
        sa.UniqueConstraint('workspace_id', 'id', name='uq_graph_versions_workspace_id'),
        sa.UniqueConstraint(
            'workspace_id', 'graph_id', 'version',
            name='uq_graph_versions_workspace_graph_version',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_graph_versions_workspace_id_workspaces'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'graph_id'],
            ['causal_graphs.workspace_id', 'causal_graphs.id'],
            name='fk_graph_versions_workspace_graph', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id'],
            ['decision_cases.workspace_id', 'decision_cases.decision_case_id'],
            name='fk_graph_versions_workspace_case', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'parent_version_id'],
            ['graph_versions.workspace_id', 'graph_versions.id'],
            name='fk_graph_versions_workspace_parent', ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'source_graph_version_id'],
            ['graph_versions.workspace_id', 'graph_versions.id'],
            name='fk_graph_versions_workspace_source', ondelete='RESTRICT',
        ),
        sa.CheckConstraint('version > 0', name=op.f('ck_graph_versions_graph_version_positive')),
        sa.CheckConstraint(
            'case_version > 0', name=op.f('ck_graph_versions_graph_case_version_positive')
        ),
        sa.CheckConstraint(
            "status <> 'confirmed' OR confirmed_at IS NOT NULL",
            name=op.f('ck_graph_versions_confirmed_requires_timestamp'),
        ),
    )
    # No confirmed partial unique index by design (B-correction): multiple
    # confirmed versions per graph are the normal history model.
    op.create_index(
        'ix_graph_versions_workspace_graph_status',
        'graph_versions', ['workspace_id', 'graph_id', 'status'],
    )

    op.create_table(
        'graph_nodes',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        _uuid('workspace_id'),
        _uuid('graph_version_id'),
        sa.Column('label', sa.String(length=240), nullable=False),
        sa.Column('node_type', sa.String(length=16), nullable=False),
        sa.Column('baseline_value', sa.Float(), nullable=False),
        sa.Column('current_value', sa.Float(), nullable=False),
        sa.Column('min_value', sa.Float(), nullable=False),
        sa.Column('max_value', sa.Float(), nullable=False),
        sa.Column('unit', sa.String(length=80), nullable=True),
        sa.Column('normalization', sa.String(length=20), nullable=False),
        sa.Column('sensitivity_step', sa.Float(), nullable=True),
        sa.Column(
            'controllability',
            sa.Enum(
                'controllable', 'partially_controllable', 'uncontrollable',
                name='factor_controllability',
            ),
            nullable=False,
        ),
        sa.Column(
            'authorship',
            sa.Enum('generated', 'user_added', 'user_modified', name='factor_authorship'),
            nullable=False,
        ),
        sa.Column(
            'evidence_status',
            sa.Enum(
                'supported', 'conditional', 'assumed', 'unknown', name='factor_evidence_status'
            ),
            nullable=False,
        ),
        sa.Column('evidence_quality_score', sa.Float(), nullable=False),
        _jsonb('evidence_ids', '[]'),
        _jsonb('assumption_ids', '[]'),
        sa.Column('rationale', sa.Text(), nullable=False),
        sa.Column('review_status', sa.String(length=16), nullable=False),
        sa.Column('editable', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_graph_nodes')),
        sa.UniqueConstraint(
            'workspace_id', 'graph_version_id', 'id',
            name='uq_graph_nodes_workspace_version_id',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_graph_nodes_workspace_id_workspaces'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'graph_version_id'],
            ['graph_versions.workspace_id', 'graph_versions.id'],
            name='fk_graph_nodes_workspace_version', ondelete='CASCADE',
        ),
        sa.CheckConstraint(
            "node_type IN ('decision', 'lever', 'constraint', 'external', 'unknown', "
            "'intermediate', 'outcome', 'indicator')",
            name=op.f('ck_graph_nodes_node_type_valid'),
        ),
        sa.CheckConstraint('min_value < max_value', name=op.f('ck_graph_nodes_node_bounds_ordered')),
        sa.CheckConstraint(
            'baseline_value >= min_value AND baseline_value <= max_value',
            name=op.f('ck_graph_nodes_node_baseline_in_bounds'),
        ),
        sa.CheckConstraint(
            'current_value >= min_value AND current_value <= max_value',
            name=op.f('ck_graph_nodes_node_current_in_bounds'),
        ),
        sa.CheckConstraint(
            'sensitivity_step IS NULL OR sensitivity_step > 0',
            name=op.f('ck_graph_nodes_node_sensitivity_step_positive'),
        ),
        sa.CheckConstraint(
            'evidence_quality_score >= 0 AND evidence_quality_score <= 1',
            name=op.f('ck_graph_nodes_node_evidence_quality_range'),
        ),
        sa.CheckConstraint(
            "normalization IN ('linear', 'inverse_linear')",
            name=op.f('ck_graph_nodes_node_normalization_valid'),
        ),
        sa.CheckConstraint(
            "review_status IN ('draft', 'confirmed', 'rejected')",
            name=op.f('ck_graph_nodes_node_status_valid'),
        ),
    )
    op.create_index(
        'ix_graph_nodes_workspace_version', 'graph_nodes', ['workspace_id', 'graph_version_id']
    )

    op.create_table(
        'graph_edges',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        _uuid('workspace_id'),
        _uuid('graph_version_id'),
        _uuid('source_node_id'),
        _uuid('target_node_id'),
        sa.Column(
            'polarity',
            sa.Enum('positive', 'negative', name='edge_polarity'),
            nullable=False,
        ),
        sa.Column('strength', sa.Float(), nullable=False),
        sa.Column('delay_steps', sa.Integer(), nullable=False),
        sa.Column(
            'authorship',
            sa.Enum('generated', 'user_added', 'user_modified', name='factor_authorship'),
            nullable=False,
        ),
        sa.Column(
            'evidence_status',
            sa.Enum(
                'supported', 'conditional', 'assumed', 'unknown', name='factor_evidence_status'
            ),
            nullable=False,
        ),
        sa.Column('relationship_quality_score', sa.Float(), nullable=False),
        sa.Column('rationale', sa.Text(), nullable=False),
        _jsonb('claim_ids', '[]'),
        _jsonb('evidence_ids', '[]'),
        _jsonb('assumption_ids', '[]'),
        sa.Column('review_status', sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_graph_edges')),
        sa.UniqueConstraint(
            'workspace_id', 'graph_version_id', 'id',
            name='uq_graph_edges_workspace_version_id',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_graph_edges_workspace_id_workspaces'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'graph_version_id'],
            ['graph_versions.workspace_id', 'graph_versions.id'],
            name='fk_graph_edges_workspace_version', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'graph_version_id', 'source_node_id'],
            ['graph_nodes.workspace_id', 'graph_nodes.graph_version_id', 'graph_nodes.id'],
            name='fk_graph_edges_same_version_source', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'graph_version_id', 'target_node_id'],
            ['graph_nodes.workspace_id', 'graph_nodes.graph_version_id', 'graph_nodes.id'],
            name='fk_graph_edges_same_version_target', ondelete='CASCADE',
        ),
        sa.CheckConstraint(
            'strength >= 0 AND strength <= 1', name=op.f('ck_graph_edges_edge_strength_range')
        ),
        sa.CheckConstraint(
            'delay_steps >= 0', name=op.f('ck_graph_edges_edge_delay_steps_non_negative')
        ),
        sa.CheckConstraint(
            'relationship_quality_score >= 0 AND relationship_quality_score <= 1',
            name=op.f('ck_graph_edges_edge_relationship_quality_range'),
        ),
        sa.CheckConstraint(
            "review_status IN ('draft', 'confirmed', 'rejected', 'conditional')",
            name=op.f('ck_graph_edges_edge_status_valid'),
        ),
        sa.CheckConstraint(
            'source_node_id <> target_node_id',
            name=op.f('ck_graph_edges_no_self_loop'),
        ),
    )
    op.create_index(
        'ix_graph_edges_workspace_version', 'graph_edges', ['workspace_id', 'graph_version_id']
    )

    op.create_table(
        'strategy_versions',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        _uuid('workspace_id'),
        _uuid('graph_id'),
        _uuid('decision_case_id'),
        sa.Column('version', sa.Integer(), nullable=False),
        _uuid('option_id'),
        _jsonb('node_overrides', '{}'),
        _jsonb('enabled_edge_ids', '[]'),
        _created_at(),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_strategy_versions')),
        sa.UniqueConstraint('workspace_id', 'id', name='uq_strategy_versions_workspace_id'),
        sa.UniqueConstraint(
            'workspace_id', 'graph_id', 'option_id', 'version',
            name='uq_strategy_versions_workspace_graph_option_version',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_strategy_versions_workspace_id_workspaces'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'graph_id'],
            ['causal_graphs.workspace_id', 'causal_graphs.id'],
            name='fk_strategy_versions_workspace_graph', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id'],
            ['decision_cases.workspace_id', 'decision_cases.decision_case_id'],
            name='fk_strategy_versions_workspace_case', ondelete='CASCADE',
        ),
        sa.CheckConstraint('version > 0', name=op.f('ck_strategy_versions_strategy_version_positive')),
    )
    op.create_index(
        'ix_strategy_versions_workspace_graph', 'strategy_versions', ['workspace_id', 'graph_id']
    )

    op.create_table(
        'scenario_versions',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        _uuid('workspace_id'),
        _uuid('graph_id'),
        _uuid('decision_case_id'),
        _uuid('source_lens_artifact_id'),
        sa.Column('source_strategic_scenario_id', sa.String(length=240), nullable=False),
        _uuid('scenario_id'),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=240), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('default_edge_multiplier', sa.Float(), nullable=False),
        _jsonb('edge_multipliers', '{}'),
        _jsonb('node_shifts', '{}'),
        sa.Column('strategy_survives', sa.Boolean(), nullable=False),
        _jsonb('early_warning_signals', '[]'),
        sa.Column('damping', sa.Float(), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_scenario_versions')),
        sa.UniqueConstraint('workspace_id', 'id', name='uq_scenario_versions_workspace_id'),
        sa.UniqueConstraint(
            'workspace_id', 'scenario_id', 'version',
            name='uq_scenario_versions_workspace_scenario_version',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_scenario_versions_workspace_id_workspaces'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'graph_id'],
            ['causal_graphs.workspace_id', 'causal_graphs.id'],
            name='fk_scenario_versions_workspace_graph', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id'],
            ['decision_cases.workspace_id', 'decision_cases.decision_case_id'],
            name='fk_scenario_versions_workspace_case', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'source_lens_artifact_id'],
            [
                'strategic_lens_artifacts.workspace_id',
                'strategic_lens_artifacts.strategic_lens_artifact_id',
            ],
            name='fk_scenario_versions_workspace_source_lens', ondelete='RESTRICT',
        ),
        sa.CheckConstraint('version > 0', name=op.f('ck_scenario_versions_scenario_version_positive')),
        sa.CheckConstraint(
            'default_edge_multiplier >= 0',
            name=op.f('ck_scenario_versions_scenario_default_multiplier_non_negative'),
        ),
        sa.CheckConstraint(
            'damping > 0 AND damping <= 1', name=op.f('ck_scenario_versions_scenario_damping_range')
        ),
    )
    op.create_index(
        'ix_scenario_versions_workspace_graph', 'scenario_versions', ['workspace_id', 'graph_id']
    )

    op.create_table(
        'score_definitions',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        _uuid('workspace_id'),
        _uuid('graph_id'),
        _uuid('decision_case_id'),
        sa.Column('version', sa.String(length=80), nullable=False),
        _jsonb('option_outcome_mappings', '[]'),
        _jsonb('risk_weights', '[]'),
        _jsonb('constraint_rules', '[]'),
        sa.Column('content_hash', sa.String(length=256), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_score_definitions')),
        sa.UniqueConstraint('workspace_id', 'id', name='uq_score_definitions_workspace_id'),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_score_definitions_workspace_id_workspaces'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'graph_id'],
            ['causal_graphs.workspace_id', 'causal_graphs.id'],
            name='fk_score_definitions_workspace_graph', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id'],
            ['decision_cases.workspace_id', 'decision_cases.decision_case_id'],
            name='fk_score_definitions_workspace_case', ondelete='CASCADE',
        ),
        sa.CheckConstraint(
            "content_hash <> ''",
            name=op.f('ck_score_definitions_score_definition_content_hash_not_empty'),
        ),
    )
    op.create_index(
        'ix_score_definitions_workspace_graph', 'score_definitions', ['workspace_id', 'graph_id']
    )

    op.create_table(
        'graph_branches',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        _uuid('workspace_id'),
        _uuid('graph_id'),
        sa.Column('name', sa.String(length=160), nullable=False),
        _uuid('base_graph_version_id'),
        _uuid('head_graph_version_id'),
        sa.Column(
            'status',
            sa.Enum('active', 'archived', name='graph_branch_status'),
            server_default='active', nullable=False,
        ),
        _created_at(),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_graph_branches')),
        sa.UniqueConstraint('workspace_id', 'id', name='uq_graph_branches_workspace_id'),
        sa.UniqueConstraint(
            'workspace_id', 'graph_id', 'name', name='uq_graph_branches_workspace_graph_name'
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_graph_branches_workspace_id_workspaces'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'graph_id'],
            ['causal_graphs.workspace_id', 'causal_graphs.id'],
            name='fk_graph_branches_workspace_graph', ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'base_graph_version_id'],
            ['graph_versions.workspace_id', 'graph_versions.id'],
            name='fk_graph_branches_workspace_base_version', ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'head_graph_version_id'],
            ['graph_versions.workspace_id', 'graph_versions.id'],
            name='fk_graph_branches_workspace_head_version', ondelete='RESTRICT',
        ),
        sa.CheckConstraint("name <> ''", name=op.f('ck_graph_branches_branch_name_not_empty')),
    )
    op.create_index(
        'ix_graph_branches_workspace_graph', 'graph_branches', ['workspace_id', 'graph_id']
    )

    # --- simulation_runs frozen-reference FKs: preflight -> NOT VALID -> VALIDATE.
    bind = op.get_bind()
    for constraint, column, target_table, target_column in _SIMULATION_RUN_FKS:
        orphans = bind.execute(
            sa.text(
                f"SELECT COUNT(*) FROM simulation_runs sr "
                f"WHERE NOT EXISTS ("
                f"  SELECT 1 FROM {target_table} t "
                f"  WHERE t.workspace_id = sr.workspace_id AND t.{target_column} = sr.{column}"
                f")"
            )
        ).scalar_one()
        if orphans:
            raise RuntimeError(
                f"simulation_runs has {orphans} orphan row(s) for {column}; "
                f"backfill or archive them before adding {constraint}"
            )
        op.execute(
            f"ALTER TABLE simulation_runs "
            f"ADD CONSTRAINT {constraint} "
            f"FOREIGN KEY (workspace_id, {column}) "
            f"REFERENCES {target_table} (workspace_id, {target_column}) "
            f"ON DELETE RESTRICT NOT VALID"
        )
        op.execute(f"ALTER TABLE simulation_runs VALIDATE CONSTRAINT {constraint}")


def downgrade() -> None:
    """Drop the graph aggregate; simulation_runs columns remain (pre-existing)."""
    for constraint, _column, _target_table, _target_column in reversed(_SIMULATION_RUN_FKS):
        op.drop_constraint(constraint, 'simulation_runs', type_='foreignkey')
    op.drop_index('ix_graph_branches_workspace_graph', table_name='graph_branches')
    op.drop_table('graph_branches')
    op.drop_index('ix_score_definitions_workspace_graph', table_name='score_definitions')
    op.drop_table('score_definitions')
    op.drop_index('ix_scenario_versions_workspace_graph', table_name='scenario_versions')
    op.drop_table('scenario_versions')
    op.drop_index('ix_strategy_versions_workspace_graph', table_name='strategy_versions')
    op.drop_table('strategy_versions')
    op.drop_index('ix_graph_edges_workspace_version', table_name='graph_edges')
    op.drop_table('graph_edges')
    op.drop_index('ix_graph_nodes_workspace_version', table_name='graph_nodes')
    op.drop_table('graph_nodes')
    op.drop_index('ix_graph_versions_workspace_graph_status', table_name='graph_versions')
    op.drop_table('graph_versions')
    op.drop_index('ix_causal_graphs_workspace_case', table_name='causal_graphs')
    op.drop_table('causal_graphs')
    # origin_mode is shared and predates this revision; drop only the six new enums.
    for enum_name in (
        'graph_branch_status',
        'edge_polarity',
        'factor_evidence_status',
        'factor_authorship',
        'factor_controllability',
        'graph_version_status',
    ):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
