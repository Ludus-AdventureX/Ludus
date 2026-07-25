"""RawArtifact-first retrieval ingestion (Task 8).

Wraps the provider router with the immutability rule from
08-deep-research-pipeline.md: every provider result is persisted as an
immutable ``RawArtifact`` row (plus a filesystem body for fetched pages)
*before* any reference is returned, and no raw page body is ever handed back
directly — callers receive artifact IDs only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.providers.base import (
    FetchOutcome,
    FetchSuccess,
    ProviderFailure,
    SearchOutcome,
    SearchSuccess,
)
from app.connectors.providers.router import ProviderRouter

from .artifact_store import FilesystemArtifactStore
from .models import RawArtifact, RetrievalTask


@dataclass(frozen=True)
class RawArtifactRef:
    """Reference to one persisted artifact; never carries the body."""

    raw_artifact_id: UUID
    url: str
    title: str
    snippet: str
    sha256: str
    origin_mode: str
    published_at: datetime | None = None


@dataclass(frozen=True)
class SearchIngestResult:
    retrieval_task_id: UUID
    provider: str
    references: tuple[RawArtifactRef, ...]


@dataclass(frozen=True)
class FetchIngestResult:
    retrieval_task_id: UUID
    provider: str
    reference: RawArtifactRef


IngestOutcome = SearchIngestResult | FetchIngestResult | ProviderFailure


def _input_hash(tool: str, payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(f"{tool}:{canonical}".encode()).hexdigest()


class RetrievalIngestService:
    """Persist provider outcomes under one workspace/case/run anchor."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        router: ProviderRouter,
        store: FilesystemArtifactStore | None = None,
    ) -> None:
        self._session = session
        self._router = router
        self._store = store or FilesystemArtifactStore()

    async def _record_task(
        self,
        *,
        workspace_id: UUID,
        decision_case_id: UUID,
        analysis_run_id: UUID,
        tool: str,
        query_summary: str,
        payload: dict[str, object],
        status: str,
    ) -> RetrievalTask:
        now = datetime.now(timezone.utc)
        task = RetrievalTask(
            id=uuid4(),
            workspace_id=workspace_id,
            decision_case_id=decision_case_id,
            analysis_run_id=analysis_run_id,
            stable_tool_name=tool,
            query_summary=query_summary,
            input_hash=_input_hash(tool, payload),
            status=status,
            created_at=now,
            completed_at=now if status in ("completed", "failed") else None,
        )
        self._session.add(task)
        await self._session.flush()
        return task

    async def search_and_record(
        self,
        *,
        workspace_id: UUID,
        decision_case_id: UUID,
        analysis_run_id: UUID,
        query: str,
        limit: int = 10,
    ) -> IngestOutcome:
        outcome: SearchOutcome = await self._router.search_web(query, limit=limit)
        if isinstance(outcome, ProviderFailure):
            await self._record_task(
                workspace_id=workspace_id,
                decision_case_id=decision_case_id,
                analysis_run_id=analysis_run_id,
                tool="search_web",
                query_summary=query,
                payload={"query": query, "limit": limit},
                status="failed",
            )
            return outcome
        assert isinstance(outcome, SearchSuccess)
        task = await self._record_task(
            workspace_id=workspace_id,
            decision_case_id=decision_case_id,
            analysis_run_id=analysis_run_id,
            tool="search_web",
            query_summary=query,
            payload={"query": query, "limit": limit},
            status="completed",
        )
        references: list[RawArtifactRef] = []
        for hit in outcome.hits:
            # Provider results are persisted as metadata-only artifacts; the
            # canonical body arrives later via fetch_and_record.
            body = json.dumps(
                {
                    "url": hit.url,
                    "title": hit.title,
                    "snippet": hit.snippet,
                    "provider": outcome.provider,
                },
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
            stored = self._store.write(
                workspace_id=workspace_id, content=body, suffix=".json"
            )
            artifact = RawArtifact(
                id=uuid4(),
                workspace_id=workspace_id,
                decision_case_id=decision_case_id,
                analysis_run_id=analysis_run_id,
                retrieval_task_id=task.id,
                kind="provider_result",
                media_type="application/json",
                byte_size=stored.byte_size,
                sha256=stored.sha256,
                storage_path=stored.storage_path,
                source_url=hit.url,
                origin_mode=outcome.origin_mode,
            )
            self._session.add(artifact)
            await self._session.flush()
            references.append(
                RawArtifactRef(
                    raw_artifact_id=artifact.id,
                    url=hit.url,
                    title=hit.title,
                    snippet=hit.snippet,
                    sha256=stored.sha256,
                    origin_mode=outcome.origin_mode.value,
                    published_at=hit.published_at,
                )
            )
        return SearchIngestResult(
            retrieval_task_id=task.id,
            provider=outcome.provider,
            references=tuple(references),
        )

    async def fetch_and_record(
        self,
        *,
        workspace_id: UUID,
        decision_case_id: UUID,
        analysis_run_id: UUID,
        url: str,
    ) -> IngestOutcome:
        outcome: FetchOutcome = await self._router.fetch_url(url)
        if isinstance(outcome, ProviderFailure):
            await self._record_task(
                workspace_id=workspace_id,
                decision_case_id=decision_case_id,
                analysis_run_id=analysis_run_id,
                tool="fetch_url",
                query_summary=url,
                payload={"url": url},
                status="failed",
            )
            return outcome
        assert isinstance(outcome, FetchSuccess)
        task = await self._record_task(
            workspace_id=workspace_id,
            decision_case_id=decision_case_id,
            analysis_run_id=analysis_run_id,
            tool="fetch_url",
            query_summary=url,
            payload={"url": url},
            status="completed",
        )
        stored = self._store.write(
            workspace_id=workspace_id,
            content=outcome.content.encode("utf-8"),
            suffix=".md",
        )
        artifact = RawArtifact(
            id=uuid4(),
            workspace_id=workspace_id,
            decision_case_id=decision_case_id,
            analysis_run_id=analysis_run_id,
            retrieval_task_id=task.id,
            kind="web_page",
            media_type=outcome.media_type,
            byte_size=stored.byte_size,
            sha256=stored.sha256,
            storage_path=stored.storage_path,
            source_url=url,
            origin_mode=outcome.origin_mode,
        )
        self._session.add(artifact)
        await self._session.flush()
        return FetchIngestResult(
            retrieval_task_id=task.id,
            provider=outcome.provider,
            reference=RawArtifactRef(
                raw_artifact_id=artifact.id,
                url=url,
                title=url,
                snippet=outcome.content[:280],
                sha256=stored.sha256,
                origin_mode=outcome.origin_mode.value,
            ),
        )
