from __future__ import annotations

from sqlalchemy import Enum, UniqueConstraint

from app.db import Base
import app.models  # noqa: F401
from app.types import (
    AnalysisRunStatus,
    AnalysisStatus,
    CaseOperationalStatus,
    DecisionLifecycleStage,
    DecisionStatus,
    NodeType,
)


def test_repaired_enum_symbols_share_one_canonical_value_set() -> None:
    assert AnalysisStatus is AnalysisRunStatus
    assert DecisionStatus is DecisionLifecycleStage
    assert [item.value for item in AnalysisRunStatus] == [
        "queued",
        "planning",
        "retrieving",
        "analyzing",
        "criticizing",
        "synthesizing",
        "validating",
        "ready",
        "blocked",
        "needs_attention",
        "cancelled",
    ]
    assert [item.value for item in NodeType] == [
        "decision",
        "lever",
        "constraint",
        "external",
        "unknown",
        "intermediate",
        "outcome",
        "indicator",
    ]


def test_case_lifecycle_and_operational_status_are_separate() -> None:
    lifecycle = {item.value for item in DecisionLifecycleStage}
    operational = {item.value for item in CaseOperationalStatus}

    assert lifecycle == {
        "draft",
        "scoped",
        "ready",
        "running",
        "review",
        "pending_signoff",
        "decided",
        "monitoring",
    }
    assert operational == {
        "ok",
        "blocked",
        "needs_attention",
        "cancelled",
        "reopened",
        "archived",
    }
    assert lifecycle.isdisjoint({"blocked", "cancelled", "reopened", "archived"})


def test_decision_case_uses_canonical_database_identifier() -> None:
    columns = Base.metadata.tables["decision_cases"].c
    assert "decision_case_id" in columns
    assert "case_id" not in columns


def test_membership_session_and_candidate_contracts_are_single_source() -> None:
    membership = Base.metadata.tables["workspace_memberships"].c
    session = Base.metadata.tables["user_sessions"].c

    assert {"workspace_id", "user_id", "role", "capabilities", "status"} <= set(membership.keys())
    assert {"id", "user_id", "token_version", "expires_at", "revoked_at"} <= set(session.keys())
    assert "candidate_revisions" in Base.metadata.tables
    assert "candidate_updates" not in Base.metadata.tables
    assert "memory_candidates" not in Base.metadata.tables


def test_tenant_unique_constraints_include_workspace() -> None:
    global_tables = {"users", "workspaces", "user_sessions"}
    for table_name, table in Base.metadata.tables.items():
        if table_name in global_tables:
            continue
        for constraint in table.constraints:
            if isinstance(constraint, UniqueConstraint):
                assert "workspace_id" in {column.name for column in constraint.columns}


def test_database_status_columns_use_enums() -> None:
    status_like_names = {"status", "operational_status", "role", "scope", "formality", "actor"}
    for table in Base.metadata.tables.values():
        for column in table.c:
            if column.name in status_like_names:
                assert isinstance(column.type, Enum), f"{table.name}.{column.name}"
