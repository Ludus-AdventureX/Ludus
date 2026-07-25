from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.model_provider import FixtureModelProvider
from app.main import app
from app.workers.analysis_worker import build_role_executors_from_model_provider
from app.types import AnalysisRunStatus


def test_release_resource_routes_are_published_in_openapi() -> None:
    paths = set(app.openapi()["paths"])
    expected = {
        "/api/workspaces/{workspaceId}/subjects",
        "/api/workspaces/{workspaceId}/subjects/{subjectId}",
        "/api/workspaces/{workspaceId}/cases",
        "/api/workspaces/{workspaceId}/cases/{decisionCaseId}",
        "/api/workspaces/{workspaceId}/cases/{decisionCaseId}/messages",
        "/api/workspaces/{workspaceId}/conversations/{conversationId}/quick-analyses",
        "/api/workspaces/{workspaceId}/cases/{decisionCaseId}/analysis-charters",
        "/api/workspaces/{workspaceId}/analysis-charters/{charterId}/runs",
        "/api/workspaces/{workspaceId}/cases/{decisionCaseId}/reports",
        "/api/workspaces/{workspaceId}/cases/{decisionCaseId}/reports/{reportId}",
        "/api/workspaces/{workspaceId}/cases/{decisionCaseId}/reports/{reportId}/exports",
        "/api/workspaces/{workspaceId}/exports/{exportArtifactId}",
        "/api/workspaces/{workspaceId}/cases/{decisionCaseId}/signoff-requests",
        "/api/workspaces/{workspaceId}/signoff-requests/{signoffRequestId}/sign",
        "/api/workspaces/{workspaceId}/cases/{decisionCaseId}/decisions",
        "/api/workspaces/{workspaceId}/decisions/{decisionId}",
        "/api/workspaces/{workspaceId}/decisions/{decisionId}/reviews",
    }
    assert expected <= paths


def test_decision_record_append_only_migration_is_present() -> None:
    migration = Path(
        "services/api/migrations/versions/c8d4e6f0a1b2_add_decision_records_reviews.py"
    ).read_text(encoding="utf-8")
    assert "decision_records_append_only" in migration
    assert "BEFORE UPDATE OR DELETE ON decision_records" in migration
    assert "decision_lifecycle_events_append_only" in migration


@pytest.mark.asyncio
async def test_worker_live_provider_executor_seam_uses_stage_result_schema() -> None:
    provider = FixtureModelProvider()
    marker = (
        '{"analysisRunId":"00000000-0000-0000-0000-000000000001",'
        '"decisionCaseId":"00000000-0000-0000-0000-000000000002",'
        '"inputs":{"analysisRunId":"00000000-0000-0000-0000-000000000001"},'
        '"stage":"validating",'
        '"workspaceId":"00000000-0000-0000-0000-000000000003"}'
    )
    provider.register(
        marker,
        {
            "output": {"validated": True},
            "qualityGatePassed": True,
            "validatorFindings": [{"code": "ok"}],
        },
    )
    executors = build_role_executors_from_model_provider(provider)

    class Run:
        workspace_id = "00000000-0000-0000-0000-000000000003"
        decision_case_id = "00000000-0000-0000-0000-000000000002"
        analysis_run_id = "00000000-0000-0000-0000-000000000001"

    result = await executors.validation(
        Run(),
        AnalysisRunStatus.VALIDATING,
        {"analysisRunId": "00000000-0000-0000-0000-000000000001"},
    )
    assert result.output == {"validated": True}
    assert result.quality_gate_passed is True
    assert result.validator_findings == ({"code": "ok"},)
