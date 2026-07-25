"""Task 8 owner tests: RawArtifact-first ingestion over the provider router."""

from __future__ import annotations

import httpx
from sqlalchemy import func, select

from app.connectors.providers.base import ProviderFailure
from app.connectors.providers.exa import ExaSearchProvider
from app.connectors.providers.firecrawl import FirecrawlFetchProvider
from app.connectors.providers.fixture import FixtureProvider
from app.connectors.providers.router import ProviderRouter
from app.connectors.providers.tavily import TavilySearchProvider
from app.evidence.ingest import (
    FetchIngestResult,
    RetrievalIngestService,
    SearchIngestResult,
)
from app.evidence.models import RawArtifact, RetrievalTask
from app.types import ConnectorStatus

FAKE_KEY = "task08-test-only-key-000000"
QUERY = "search and rescue ground robot procurement cycle"


def _fixture_router() -> ProviderRouter:
    fixture = FixtureProvider()
    return ProviderRouter(search_providers=(fixture,), fetch_provider=fixture)


def _degraded_router() -> ProviderRouter:
    def deny(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "redacted"})

    def factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(deny))

    return ProviderRouter(
        search_providers=(
            ExaSearchProvider(client_factory=factory, api_key=FAKE_KEY),
            TavilySearchProvider(client_factory=factory, api_key=FAKE_KEY),
        ),
        fetch_provider=FirecrawlFetchProvider(client_factory=factory, api_key=FAKE_KEY),
    )


async def test_search_writes_immutable_raw_artifacts_before_returning_refs(
    session, world, artifact_store
) -> None:
    service = RetrievalIngestService(
        session, router=_fixture_router(), store=artifact_store
    )
    result = await service.search_and_record(
        workspace_id=world.workspace_id,
        decision_case_id=world.case_id,
        analysis_run_id=world.analysis_run_id,
        query=QUERY,
    )
    assert isinstance(result, SearchIngestResult)
    assert len(result.references) == 2
    for ref in result.references:
        row = await session.scalar(
            select(RawArtifact).where(
                RawArtifact.workspace_id == world.workspace_id,
                RawArtifact.id == ref.raw_artifact_id,
            )
        )
        assert row is not None, "reference returned without a persisted RawArtifact"
        assert row.kind == "provider_result"
        assert row.origin_mode.value == "fixture"
        assert row.sha256 == ref.sha256
        # Body lives behind the pointer, never inside the reference.
        body = artifact_store.read(
            workspace_id=world.workspace_id, storage_path=row.storage_path
        )
        assert body, "artifact body must be readable through the store"
    task = await session.scalar(
        select(RetrievalTask).where(RetrievalTask.id == result.retrieval_task_id)
    )
    assert task is not None
    assert task.status == "completed"
    assert task.stable_tool_name == "search_web"


async def test_fetch_writes_web_page_artifact_with_content_hash(
    session, world, artifact_store
) -> None:
    service = RetrievalIngestService(
        session, router=_fixture_router(), store=artifact_store
    )
    search = await service.search_and_record(
        workspace_id=world.workspace_id,
        decision_case_id=world.case_id,
        analysis_run_id=world.analysis_run_id,
        query=QUERY,
    )
    assert isinstance(search, SearchIngestResult)
    url = search.references[0].url
    fetched = await service.fetch_and_record(
        workspace_id=world.workspace_id,
        decision_case_id=world.case_id,
        analysis_run_id=world.analysis_run_id,
        url=url,
    )
    assert isinstance(fetched, FetchIngestResult)
    row = await session.scalar(
        select(RawArtifact).where(RawArtifact.id == fetched.reference.raw_artifact_id)
    )
    assert row is not None
    assert row.kind == "web_page"
    body = artifact_store.read(
        workspace_id=world.workspace_id, storage_path=row.storage_path
    )
    import hashlib

    assert hashlib.sha256(body).hexdigest() == row.sha256


async def test_degraded_search_records_failed_task_and_returns_structured_state(
    session, world, artifact_store
) -> None:
    service = RetrievalIngestService(
        session, router=_degraded_router(), store=artifact_store
    )
    outcome = await service.search_and_record(
        workspace_id=world.workspace_id,
        decision_case_id=world.case_id,
        analysis_run_id=world.analysis_run_id,
        query=QUERY,
    )
    assert isinstance(outcome, ProviderFailure)
    assert outcome.status == ConnectorStatus.RATE_LIMITED
    assert outcome.fallback_chain == ("exa", "tavily")
    assert FAKE_KEY not in repr(outcome)
    # The failed attempt is recorded, but no artifact row was fabricated.
    task_count = await session.scalar(
        select(func.count()).select_from(RetrievalTask).where(
            RetrievalTask.workspace_id == world.workspace_id,
            RetrievalTask.status == "failed",
        )
    )
    assert task_count == 1
    artifact_count = await session.scalar(
        select(func.count()).select_from(RawArtifact).where(
            RawArtifact.workspace_id == world.workspace_id
        )
    )
    assert artifact_count == 0


async def test_artifact_store_rejects_foreign_workspace_pointer(
    session, world, foreign_world, artifact_store
) -> None:
    service = RetrievalIngestService(
        session, router=_fixture_router(), store=artifact_store
    )
    result = await service.search_and_record(
        workspace_id=world.workspace_id,
        decision_case_id=world.case_id,
        analysis_run_id=world.analysis_run_id,
        query=QUERY,
    )
    assert isinstance(result, SearchIngestResult)
    row = await session.scalar(
        select(RawArtifact).where(
            RawArtifact.id == result.references[0].raw_artifact_id
        )
    )
    assert row is not None
    import pytest

    with pytest.raises(ValueError):
        artifact_store.read(
            workspace_id=foreign_world.workspace_id, storage_path=row.storage_path
        )
