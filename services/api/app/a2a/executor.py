"""A2A AgentExecutor bridging the protocol to the five-lens pipeline.

One incoming task -> one pipeline run. Stage transitions surface as A2A
``working`` status updates (the judge-visible "explainable process"), the
final report lands as a text artifact, and every failure path resolves the
task instead of hanging the client.
"""

from __future__ import annotations

import logging

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, TaskState, TextPart
from a2a.utils import new_agent_text_message, new_task

from app.a2a.config import get_a2a_settings
from app.a2a.panda_client import (
    FixturePandaClient,
    HttpPandaClient,
    PandaDataClient,
    SdkPandaClient,
)
from app.a2a.pipeline import FiveLensPipeline
from app.agents.model_provider import ModelProvider

logger = logging.getLogger(__name__)

_STAGE_LABELS = {
    "planner": "Planner",
    "data": "Data Agent",
    "lens": "Lens",
    "report": "Report Agent",
}


def _build_panda_client() -> PandaDataClient:
    settings = get_a2a_settings()
    # Official access path first: panda_data SDK credentials. REST base URL is
    # a fallback should the track ever expose one.
    if settings.panda_username and settings.panda_password:
        return SdkPandaClient(settings)
    if settings.panda_base_url:
        return HttpPandaClient(settings)
    # No data access configured: run with an empty fixture client so the
    # pipeline degrades openly ("no market data fetched") instead of crashing.
    return FixturePandaClient()


class FiveLensAgentExecutor(AgentExecutor):
    """Stateless executor; per-task pipeline instances, no shared mutable state."""

    def __init__(
        self,
        *,
        provider_factory=None,
        panda_client_factory=None,
    ) -> None:
        # Factories keep live-binding construction lazy (env read per task)
        # and let tests inject fixture providers without monkeypatching.
        if provider_factory is None:
            from app.a2a.deepseek_provider import build_model_provider

            provider_factory = build_model_provider
        self._provider_factory = provider_factory
        self._panda_client_factory = panda_client_factory or _build_panda_client

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_text = (context.get_user_input() or "").strip()
        task = context.current_task
        if task is None:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)

        if not task_text:
            await updater.reject(
                new_agent_text_message(
                    "请提供一个自然语言投研任务，例如：分析某只股票的竞争格局与下行风险。",
                    task.context_id,
                    task.id,
                )
            )
            return

        async def progress(stage: str, detail: str) -> None:
            label = _STAGE_LABELS.get(stage, stage)
            await updater.update_status(
                TaskState.working,
                new_agent_text_message(f"[{label}] {detail}", task.context_id, task.id),
            )

        try:
            provider: ModelProvider = self._provider_factory()
            pipeline = FiveLensPipeline(
                settings=get_a2a_settings(),
                provider=provider,
                panda_client=self._panda_client_factory(),
            )
            await updater.start_work()
            result = await pipeline.run(task_text, progress)
        except Exception:
            logger.exception("a2a pipeline failed for task %s", task.id)
            await updater.failed(
                new_agent_text_message(
                    "分析流水线执行失败，请稍后重试或联系参赛团队。",
                    task.context_id,
                    task.id,
                )
            )
            return

        await updater.add_artifact(
            [Part(root=TextPart(text=result.report_markdown))],
            name="five-lens-research-report.md",
        )
        ok = sum(1 for o in result.lens_outcomes if o.status == "ok")
        await updater.complete(
            new_agent_text_message(
                f"分析完成：{ok}/5 个 Lens 通过行为门控，总耗时 "
                f"{result.elapsed_seconds:.0f} 秒。完整报告见任务产物。",
                task.context_id,
                task.id,
            )
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task
        if task is not None:
            updater = TaskUpdater(event_queue, task.id, task.context_id)
            await updater.cancel()
