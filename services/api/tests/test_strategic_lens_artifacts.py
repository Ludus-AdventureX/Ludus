"""QA negative regressions for StrategicLensArtifact persistence (CCR-20260724-Ways-01).

Every constraint asserted here is exercised against the real PostgreSQL
schema (rollback-only connection over the migrated database), not only the
Pydantic/model layer. Skips cleanly on trees without the CCR execution.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import insert, select
from sqlalchemy.exc import DBAPIError, IntegrityError, StatementError
from sqlalchemy.ext.asyncio import AsyncConnection

pytest.importorskip("app.models", reason="canonical models unavailable")

from app.models import Base, StrategicLensArtifact  # noqa: E402
from app.types import (  # noqa: E402
    ConnectorStatus,
    LensProducerRole,
    StrategicLensArtifactStatus,
    StrategicLensType,
)

from tests.test_models import (  # noqa: E402
    seed_analysis_run,
    seed_case,
    seed_subject_pair,
    seed_user_and_workspaces,
)


def _artifact_values(workspace_id, case_id, run_id, **overrides) -> dict:
    values = {
        "strategic_lens_artifact_id": uuid4(),
        "workspace_id": workspace_id,
        "decision_case_id": case_id,
        "analysis_run_id": run_id,
        "charter_id": uuid4(),
        "lens_type": StrategicLensType.PORTER_FIVE_FORCES,
        "producer_role": LensProducerRole.RESEARCH,
        "status": StrategicLensArtifactStatus.DRAFT,
        "method_id": "hardtech-market-direction",
        "method_version": "1.1.0",
        "method_content_hash": "sha256:method",
        "prompt_version": "1.0.0",
        "schema_version": "1.1.0",
        "origin_modes": ["fixture"],
        "content_hash": f"sha256:lens-{uuid4().hex[:12]}",
        "payload": {"summary": "qa"},
        "claim_refs": [],
        "evidence_refs": [],
        "assumption_refs": [],
    }
    values.update(overrides)
    return values


async def _insert(connection: AsyncConnection, values: dict) -> None:
    await connection.execute(insert(StrategicLensArtifact).values(**values))


async def _expect_rejected(connection: AsyncConnection, values: dict) -> None:
    savepoint = await connection.begin_nested()
    # StatementError covers enum-layer rejections (SQLAlchemy validates enum
    # members before the statement reaches PostgreSQL); Integrity/DBAPIError
    # cover the real database constraints.
    with pytest.raises((IntegrityError, DBAPIError, StatementError)):
        await _insert(connection, values)
    await savepoint.rollback()


@pytest.fixture
async def lens_stack(db_connection: AsyncConnection):
    """Two workspaces; workspace A carries subject/case/run for lens rows."""

    _, ws_a, ws_b = await seed_user_and_workspaces(db_connection)
    subject_a, subject_b = await seed_subject_pair(db_connection, ws_a)
    case_a = await seed_case(db_connection, ws_a, subject_a)
    case_b = await seed_case(db_connection, ws_a, subject_b)
    run_a = await seed_analysis_run(db_connection, ws_a, case_a)
    run_b = await seed_analysis_run(db_connection, ws_a, case_b)
    return db_connection, ws_a, ws_b, case_a, case_b, run_a, run_b


async def test_wrong_workspace_binding_is_rejected(lens_stack) -> None:
    connection, ws_a, ws_b, case_a, _, run_a, _ = lens_stack
    await _expect_rejected(
        connection, _artifact_values(ws_b, case_a, run_a)
    )


async def test_wrong_case_binding_is_rejected(lens_stack) -> None:
    connection, ws_a, _, case_a, case_b, run_a, _ = lens_stack
    # run_a belongs to case_a; binding it to case_b must fail the composite FK
    await _expect_rejected(
        connection, _artifact_values(ws_a, case_b, run_a)
    )
    # a fabricated case id fails the workspace+case FK as well
    await _expect_rejected(
        connection, _artifact_values(ws_a, uuid4(), run_a)
    )


async def test_wrong_analysis_run_binding_is_rejected(lens_stack) -> None:
    connection, ws_a, _, case_a, _, _, run_b = lens_stack
    # run_b belongs to case_b: composite (workspace, case, run) FK must reject
    await _expect_rejected(
        connection, _artifact_values(ws_a, case_a, run_b)
    )
    await _expect_rejected(
        connection, _artifact_values(ws_a, case_a, uuid4())
    )


async def test_ready_without_validation_acceptance_is_rejected(lens_stack) -> None:
    connection, ws_a, _, case_a, _, run_a, _ = lens_stack
    await _expect_rejected(
        connection,
        _artifact_values(
            ws_a,
            case_a,
            run_a,
            status=StrategicLensArtifactStatus.READY,
            validation_accepted_at=None,
        ),
    )
    # positive twin: ready + witness timestamp is accepted
    await _insert(
        connection,
        _artifact_values(
            ws_a,
            case_a,
            run_a,
            status=StrategicLensArtifactStatus.READY,
            validation_accepted_at=datetime.now(timezone.utc),
        ),
    )


async def test_second_ready_per_run_and_lens_is_rejected(lens_stack) -> None:
    connection, ws_a, _, case_a, _, run_a, _ = lens_stack
    accepted = dict(
        status=StrategicLensArtifactStatus.READY,
        validation_accepted_at=datetime.now(timezone.utc),
    )
    await _insert(connection, _artifact_values(ws_a, case_a, run_a, **accepted))
    await _expect_rejected(
        connection, _artifact_values(ws_a, case_a, run_a, **accepted)
    )


async def test_draft_and_rejected_history_is_allowed(lens_stack) -> None:
    connection, ws_a, _, case_a, _, run_a, _ = lens_stack
    for status in (
        StrategicLensArtifactStatus.DRAFT,
        StrategicLensArtifactStatus.DRAFT,
        StrategicLensArtifactStatus.REJECTED,
        StrategicLensArtifactStatus.REJECTED,
    ):
        await _insert(
            connection, _artifact_values(ws_a, case_a, run_a, status=status)
        )
    count = (
        await connection.execute(
            select(StrategicLensArtifact.strategic_lens_artifact_id).where(
                StrategicLensArtifact.analysis_run_id == run_a
            )
        )
    ).scalars().all()
    assert len(count) == 4, "audit history for draft/rejected must be retained"


async def test_empty_content_hash_is_rejected(lens_stack) -> None:
    connection, ws_a, _, case_a, _, run_a, _ = lens_stack
    await _expect_rejected(
        connection, _artifact_values(ws_a, case_a, run_a, content_hash="")
    )


async def test_illegal_origin_mode_is_rejected(lens_stack) -> None:
    connection, ws_a, _, case_a, _, run_a, _ = lens_stack
    await _expect_rejected(
        connection,
        _artifact_values(ws_a, case_a, run_a, origin_modes=["hallucinated"]),
    )


def test_connector_status_is_the_exact_seven_value_set() -> None:
    assert {member.value for member in ConnectorStatus} == {
        "available",
        "missing_credentials",
        "invalid_credentials",
        "rate_limited",
        "quota_exhausted",
        "provider_error",
        "disabled",
    }, "any missing/extra/renamed connector status must fail this test"


def test_strategic_lens_artifact_status_is_exact() -> None:
    assert {member.value for member in StrategicLensArtifactStatus} == {
        "draft",
        "ready",
        "rejected",
    }


def test_lens_type_column_reuses_canonical_strategic_lens_type() -> None:
    column = Base.metadata.tables["strategic_lens_artifacts"].c.lens_type
    assert column.type.name == "strategic_lens_type"
    assert set(column.type.enums) == {member.value for member in StrategicLensType}


def test_no_parallel_connector_status_definition_exists() -> None:
    """Source-scan guard: ConnectorStatus is defined exactly once in app/."""

    from pathlib import Path

    app_root = Path(__file__).resolve().parents[1] / "app"
    definitions = []
    for path in app_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "class ConnectorStatus" in text:
            definitions.append(str(path.relative_to(app_root)))
    assert definitions == ["types.py"], (
        f"parallel ConnectorStatus definitions found: {definitions}"
    )
