"""add decision maker profiles and idempotency records

Revision ID: b2c7e9d4a1f6
Revises: a3f8c2d47e19
Create Date: 2026-07-25

CCR-20260724-SIM-02A prerequisites P1 + P3 in one forward revision on top of
a3f8c2d47e19 (which stays untouched):

* P1: immutable, append-only ``decision_maker_profiles`` with business identity
  UNIQUE(workspace_id, profile_id, version), plus the tenant-scoped frozen
  profile reference FK on the pre-existing ``simulation_runs`` columns. The FK
  follows the SIM-01 frozen-reference discipline exactly: orphan preflight
  (never assumes the table is empty; unresolvable references fail closed with
  RuntimeError), then ADD CONSTRAINT ... NOT VALID, then VALIDATE CONSTRAINT,
  then a pg_constraint.convalidated = true assertion.
* P3: generic ``idempotency_records`` persistence schema only; no replay/
  conflict runtime flow, no header handling, no route wiring in this slice.
  ``response_kind`` is an enum-checked string by contract (no PG enum).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'b2c7e9d4a1f6'
down_revision: Union[str, Sequence[str], None] = 'a3f8c2d47e19'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PROFILE_FK = 'fk_simulation_runs_workspace_profile_version'


def upgrade() -> None:
    """Create profile + idempotency tables, then wire the runs profile FK."""
    op.create_table(
        'decision_maker_profiles',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('profile_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('decision_case_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('display_name', sa.String(length=160), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column(
            'preference_weights', postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        sa.Column('risk_tolerance', sa.Float(), nullable=False),
        sa.Column('content_hash', sa.String(length=256), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_decision_maker_profiles')),
        sa.UniqueConstraint(
            'workspace_id', 'id', name='uq_decision_maker_profiles_workspace_id'
        ),
        sa.UniqueConstraint(
            'workspace_id', 'profile_id', 'version',
            name='uq_decision_maker_profiles_workspace_profile_version',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_decision_maker_profiles_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id', 'decision_case_id'],
            ['decision_cases.workspace_id', 'decision_cases.decision_case_id'],
            name='fk_decision_maker_profiles_workspace_case', ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'],
            name=op.f('fk_decision_maker_profiles_user_id_users'), ondelete='RESTRICT',
        ),
        sa.CheckConstraint(
            'version > 0',
            name=op.f('ck_decision_maker_profiles_profile_version_positive'),
        ),
        sa.CheckConstraint(
            'risk_tolerance >= 0 AND risk_tolerance <= 1',
            name=op.f('ck_decision_maker_profiles_profile_risk_tolerance_range'),
        ),
        sa.CheckConstraint(
            "display_name <> ''",
            name=op.f('ck_decision_maker_profiles_profile_display_name_not_empty'),
        ),
        sa.CheckConstraint(
            "content_hash <> ''",
            name=op.f('ck_decision_maker_profiles_profile_content_hash_not_empty'),
        ),
    )
    op.create_index(
        'ix_decision_maker_profiles_workspace_case',
        'decision_maker_profiles',
        ['workspace_id', 'decision_case_id'],
    )

    op.create_table(
        'idempotency_records',
        sa.Column(
            'id', postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'), nullable=False,
        ),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('route_key', sa.String(length=120), nullable=False),
        sa.Column('idempotency_key', sa.String(length=200), nullable=False),
        sa.Column('normalized_request_hash', sa.String(length=256), nullable=False),
        sa.Column('resource_type', sa.String(length=80), nullable=False),
        sa.Column('resource_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('http_status', sa.Integer(), nullable=False),
        sa.Column('response_kind', sa.String(length=40), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_idempotency_records')),
        sa.UniqueConstraint(
            'workspace_id', 'route_key', 'idempotency_key',
            name='uq_idempotency_records_workspace_route_key',
        ),
        sa.ForeignKeyConstraint(
            ['workspace_id'], ['workspaces.id'],
            name=op.f('fk_idempotency_records_workspace_id_workspaces'),
            ondelete='CASCADE',
        ),
        sa.CheckConstraint(
            "route_key <> ''",
            name=op.f('ck_idempotency_records_idempotency_route_key_not_empty'),
        ),
        sa.CheckConstraint(
            'char_length(idempotency_key) BETWEEN 1 AND 200',
            name=op.f('ck_idempotency_records_idempotency_key_length'),
        ),
        sa.CheckConstraint(
            "normalized_request_hash <> ''",
            name=op.f('ck_idempotency_records_idempotency_request_hash_not_empty'),
        ),
        sa.CheckConstraint(
            "resource_type <> ''",
            name=op.f('ck_idempotency_records_idempotency_resource_type_not_empty'),
        ),
        sa.CheckConstraint(
            'http_status >= 100 AND http_status <= 599',
            name=op.f('ck_idempotency_records_idempotency_http_status_range'),
        ),
        sa.CheckConstraint(
            "response_kind IN ('success', 'non_converged')",
            name=op.f('ck_idempotency_records_idempotency_response_kind_enum'),
        ),
        sa.CheckConstraint(
            'expires_at > created_at',
            name=op.f('ck_idempotency_records_idempotency_expiry_after_creation'),
        ),
    )
    op.create_index(
        'ix_idempotency_records_workspace_expires',
        'idempotency_records',
        ['workspace_id', 'expires_at'],
    )

    # --- simulation_runs frozen profile FK: preflight -> NOT VALID -> VALIDATE.
    bind = op.get_bind()
    orphans = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM simulation_runs sr "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM decision_maker_profiles p "
            "  WHERE p.workspace_id = sr.workspace_id "
            "    AND p.profile_id = sr.decision_maker_profile_id "
            "    AND p.version = sr.decision_maker_profile_version"
            ")"
        )
    ).scalar_one()
    if orphans:
        raise RuntimeError(
            f"simulation_runs has {orphans} row(s) whose decision_maker_profile "
            f"reference cannot be resolved against decision_maker_profiles; "
            f"backfill frozen profile rows or archive those runs before adding "
            f"{_PROFILE_FK}"
        )
    op.execute(
        f"ALTER TABLE simulation_runs "
        f"ADD CONSTRAINT {_PROFILE_FK} "
        f"FOREIGN KEY (workspace_id, decision_maker_profile_id, "
        f"decision_maker_profile_version) "
        f"REFERENCES decision_maker_profiles (workspace_id, profile_id, version) "
        f"ON DELETE RESTRICT NOT VALID"
    )
    op.execute(f"ALTER TABLE simulation_runs VALIDATE CONSTRAINT {_PROFILE_FK}")
    validated = bind.execute(
        sa.text(
            "SELECT convalidated FROM pg_constraint WHERE conname = :name"
        ),
        {"name": _PROFILE_FK},
    ).scalar_one()
    if validated is not True:
        raise RuntimeError(
            f"{_PROFILE_FK} exists but pg_constraint.convalidated is not true"
        )


def downgrade() -> None:
    """Drop the profile FK and both tables; simulation_runs columns pre-exist."""
    op.drop_constraint(_PROFILE_FK, 'simulation_runs', type_='foreignkey')
    op.drop_index(
        'ix_idempotency_records_workspace_expires', table_name='idempotency_records'
    )
    op.drop_table('idempotency_records')
    op.drop_index(
        'ix_decision_maker_profiles_workspace_case',
        table_name='decision_maker_profiles',
    )
    op.drop_table('decision_maker_profiles')
