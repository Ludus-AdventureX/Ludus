"""add P2 wave-2 schema: retrieval coverage, funnel audits, complexity downgrade

Revision ID: 2b2d34dacee0
Revises: a4b5c6d7e8f9
Create Date: 2026-08-02 23:49:43.311240

CCR-20260802-P2W2: three additive schema changes (no rewrite of applied
revisions):
1. AnalysisRun gains complexity_downgraded bool + downgrade_chain jsonb
   (internal state only; the five-lens artifact contract is untouched);
2. retrieval_coverage — per-run frozen search index (grey-goo §3);
3. evidence_funnel_audits — persisted TDD discard records (grey-goo 原则⑩).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID


revision: str = "2b2d34dacee0"
down_revision: Union[str, Sequence[str], None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "analysis_runs",
        sa.Column(
            "complexity_downgraded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "analysis_runs",
        sa.Column(
            "downgrade_chain",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    op.create_table(
        "retrieval_coverage",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("decision_case_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("analysis_run_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("keywords", JSONB, nullable=False),
        sa.Column("queried_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_summary", sa.Text(), nullable=False),
        sa.Column("result_hash", sa.String(256), nullable=False),
        sa.Column("frozen", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "origin_mode",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'live'"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "analysis_run_id"],
            [
                "analysis_runs.workspace_id",
                "analysis_runs.decision_case_id",
                "analysis_runs.analysis_run_id",
            ],
            name="fk_retrieval_coverage_workspace_case_run",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "analysis_run_id",
            "result_hash",
            name="uq_retrieval_coverage_run_hash",
        ),
        sa.Index("ix_retrieval_coverage_workspace_run", "workspace_id", "analysis_run_id"),
    )

    op.create_table(
        "evidence_funnel_audits",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("decision_case_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("analysis_run_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("admitted", sa.Integer(), nullable=False),
        sa.Column("discarded", JSONB, nullable=False),
        sa.Column("warnings", JSONB, nullable=False),
        sa.Column("tier_counts", JSONB, nullable=False),
        sa.Column("opposing_count", sa.Integer(), nullable=False),
        sa.Column("low_tier_share", sa.Numeric(6, 3), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "decision_case_id", "analysis_run_id"],
            [
                "analysis_runs.workspace_id",
                "analysis_runs.decision_case_id",
                "analysis_runs.analysis_run_id",
            ],
            name="fk_evidence_funnel_audits_workspace_case_run",
            ondelete="CASCADE",
        ),
        sa.Index("ix_evidence_funnel_audits_workspace_run", "workspace_id", "analysis_run_id"),
    )


def downgrade() -> None:
    op.drop_table("evidence_funnel_audits")
    op.drop_table("retrieval_coverage")
    op.drop_column("analysis_runs", "downgrade_chain")
    op.drop_column("analysis_runs", "complexity_downgraded")
