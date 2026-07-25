"""Offline tests for the A2A prototype surface (no network, no DB, no keys).

Covers the plan's three acceptance areas:

1. full pipeline happy path on fixture providers — five gate-passing lenses,
   risk-disclosure section always present;
2. behavior-gate failure path — degraded lens disclosed, pipeline survives;
3. protocol surface — mount-time gating on/off, agent-card completeness, and
   a JSON-RPC ``message/send`` round trip through the official SDK stack.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.a2a.config import get_a2a_settings
from app.a2a.mount import mount_a2a
from app.a2a.panda_client import DataRequest, FixturePandaClient
from app.a2a.pipeline import LENS_EXECUTION_ORDER, FiveLensPipeline
from app.agents.lenses import LENS_SPECS
from app.agents.model_provider import ModelMessage, ProviderProbe, StructuredCompletion

FIXTURES = Path(__file__).resolve().parent / "fixtures"

PLANNER_CONTENT: dict[str, Any] = {
    "decisionQuestion": "未来 24 个月应当增持还是回避 CATL？",
    "horizon": "24 months",
    "optionIds": ["option-overweight", "option-avoid"],
    "subjects": [{"symbol": "300750.SZ", "name": "CATL"}],
    "dataRequests": [{"kind": "quote", "subject": "300750.SZ", "params": {}}],
}

REPORT_CONTENT: dict[str, Any] = {
    "summary": "五个透镜均通过行为门控，竞争壁垒依旧但对手盘反应加剧。",
    "recommendation": "倾向 option-overweight，前提是季度毛利率不跌破预警线。",
    "keyRisks": ["价格战超预期", "海外政策收紧", "技术路线切换"],
}


def _lens_payload(lens_value: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{lens_value}.json").read_text("utf-8"))


class StubProvider:
    """Deterministic ModelProvider routing on request_model / content_def."""

    name = "stub"
    supports_structured_output = True

    def __init__(self, overrides: dict[str, Mapping[str, Any]] | None = None) -> None:
        self.overrides = overrides or {}
        self.calls: list[str] = []

    async def complete_structured(
        self,
        *,
        system: str,
        messages: Sequence[ModelMessage],
        schema: Mapping[str, Any] | None,
        tools: Sequence[Mapping[str, Any]] | None,
        request_model: str,
    ) -> StructuredCompletion:
        content = self._route(request_model, messages[-1].content if messages else "")
        return StructuredCompletion(
            content=content,
            raw_text=json.dumps(content, ensure_ascii=False),
            request_model=request_model,
            response_model="stub",
            finish_reason="stop",
        )

    def _route(self, request_model: str, user_text: str) -> Mapping[str, Any]:
        if request_model == "a2a-planner":
            self.calls.append("planner")
            return self.overrides.get("planner", PLANNER_CONTENT)
        if request_model == "a2a-report":
            self.calls.append("report")
            return self.overrides.get("report", REPORT_CONTENT)
        for spec in LENS_SPECS.values():
            if spec.content_def in user_text:
                self.calls.append(spec.lens_type.value)
                if spec.lens_type.value in self.overrides:
                    return self.overrides[spec.lens_type.value]
                return _lens_payload(spec.lens_type.value)
        raise AssertionError(f"unroutable stub call: {request_model}")

    async def probe(self) -> ProviderProbe:
        return ProviderProbe(provider=self.name, ok=True, supports_structured_output=True)


def _panda_fixture() -> FixturePandaClient:
    client = FixturePandaClient()
    client.register(
        "quote",
        "300750.SZ",
        [{"date": "2026-07-24", "close": 251.3, "pct_chg": -1.2}],
    )
    return client


def _pipeline(provider: StubProvider) -> FiveLensPipeline:
    return FiveLensPipeline(
        settings=get_a2a_settings(),
        provider=provider,
        panda_client=_panda_fixture(),
    )


async def test_pipeline_happy_path_all_five_lenses_pass() -> None:
    provider = StubProvider()
    result = await _pipeline(provider).run("分析宁德时代未来两年的竞争格局与下行风险")

    assert [o.lens_type for o in result.lens_outcomes] == list(LENS_EXECUTION_ORDER)
    assert all(o.status == "ok" for o in result.lens_outcomes)
    # evidence flowed from the fixture data client into the run
    assert result.evidence and result.evidence[0].origin == "fixture"
    # mandatory compliance sections in the report
    assert "风险提示与免责声明" in result.report_markdown
    assert "不构成任何投资建议" in result.report_markdown
    assert "执行摘要" in result.report_markdown
    # planner ran first, report ran last
    assert provider.calls[0] == "planner" and provider.calls[-1] == "report"


async def test_pipeline_degrades_failed_lens_and_continues() -> None:
    broken_porter = _lens_payload("porter_five_forces")
    broken_porter["content"]["marketAnalyses"] = broken_porter["content"]["marketAnalyses"][:1]
    provider = StubProvider(overrides={"porter_five_forces": broken_porter})

    result = await _pipeline(provider).run("分析宁德时代未来两年的竞争格局与下行风险")

    by_lens = {o.lens_type.value: o for o in result.lens_outcomes}
    porter = by_lens["porter_five_forces"]
    assert porter.status == "degraded"
    assert porter.findings  # gate findings surfaced, not swallowed
    assert porter.attempts == 2  # one findings-guided retry happened
    # the other four lenses still completed
    others = [o for o in result.lens_outcomes if o.lens_type.value != "porter_five_forces"]
    assert all(o.status == "ok" for o in others)
    # degradation is disclosed in the report
    assert "degraded" in result.report_markdown


def test_mount_disabled_leaves_app_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("A2A_ENABLED", raising=False)
    app = FastAPI()
    baseline = len(app.routes)
    assert mount_a2a(app) is False
    assert len(app.routes) == baseline


def _enabled_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setenv("A2A_ENABLED", "true")
    monkeypatch.setenv("A2A_PUBLIC_URL", "https://agent.example.test")
    app = FastAPI()
    assert mount_a2a(app) is True
    return app


async def test_agent_card_served_and_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _enabled_app(monkeypatch)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/.well-known/agent-card.json")
    assert response.status_code == 200
    card = response.json()
    assert card["name"] == "Ludus Five-Lens Research Agent"
    assert card["url"] == "https://agent.example.test/a2a"
    assert card["capabilities"]["streaming"] is True
    skill_names = {skill["name"] for skill in card["skills"]}
    assert {"five_lens_research", "market_data_analysis", "risk_premortem"} <= skill_names


async def test_message_send_round_trip_returns_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JSON-RPC message/send through the official SDK stack with stub agents."""

    from a2a.server.apps import A2AStarletteApplication
    from a2a.server.request_handlers import DefaultRequestHandler
    from a2a.server.tasks import InMemoryTaskStore

    from app.a2a.agent_card import build_agent_card
    from app.a2a.executor import FiveLensAgentExecutor

    monkeypatch.setenv("A2A_PUBLIC_URL", "https://agent.example.test")
    app = A2AStarletteApplication(
        agent_card=build_agent_card(get_a2a_settings()),
        http_handler=DefaultRequestHandler(
            agent_executor=FiveLensAgentExecutor(
                provider_factory=StubProvider,
                panda_client_factory=_panda_fixture,
            ),
            task_store=InMemoryTaskStore(),
        ),
    ).build(agent_card_url="/.well-known/agent-card.json", rpc_url="/a2a")

    request_body = {
        "jsonrpc": "2.0",
        "id": "req-1",
        "method": "message/send",
        "params": {
            "message": {
                "kind": "message",
                "role": "user",
                "messageId": uuid4().hex,
                "parts": [
                    {"kind": "text", "text": "分析宁德时代未来两年的竞争格局与下行风险"}
                ],
            }
        },
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        timeout=30.0,
    ) as client:
        response = await client.post("/a2a", json=request_body)

    assert response.status_code == 200
    body = response.json()
    assert "error" not in body, body
    task = body["result"]
    assert task["status"]["state"] == "completed"
    artifacts = task.get("artifacts") or []
    assert artifacts, "the research report artifact must be attached"
    report_text = artifacts[0]["parts"][0]["text"]
    assert "风险提示与免责声明" in report_text
    assert "五 Lens 投研分析报告" in report_text


async def test_fixture_panda_client_marks_origin() -> None:
    client = _panda_fixture()
    items = await client.fetch(DataRequest(kind="quote", subject="300750.SZ"))
    assert items and all(item.origin == "fixture" for item in items)
    assert items[0].evidence_id.startswith("ev-fixture-quote-")


async def test_sdk_panda_client_normalizes_dataframe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SdkPandaClient routes kinds to panda_data getters and normalizes rows."""

    import pandas as pd

    import app.a2a.panda_client as panda_client_module
    from app.a2a.panda_client import SdkPandaClient

    calls: list[str] = []

    class FakePandaData:
        @staticmethod
        def init_token(username: str, password: str) -> None:
            calls.append(f"init:{username}")

        @staticmethod
        def get_stock_daily(**kwargs):
            calls.append("get_stock_daily")
            return pd.DataFrame(
                [
                    {"date": "20260720", "symbol": "300750.SZ", "close": 250.0},
                    {"date": "20260721", "symbol": "300750.SZ", "close": float("nan")},
                ]
            )

        @staticmethod
        def get_trade_cal(**kwargs):
            calls.append("get_trade_cal")
            return pd.DataFrame([{"nature_date": 20260721, "is_trade": 1}])

    import sys

    monkeypatch.setitem(sys.modules, "panda_data", FakePandaData())
    monkeypatch.setattr(SdkPandaClient, "_token_ready", False)
    monkeypatch.setenv("PANDAAI_USERNAME", "8613800000000")
    monkeypatch.setenv("PANDAAI_PASSWORD", "secret")
    client = SdkPandaClient(get_a2a_settings())

    quotes = await client.fetch(DataRequest(kind="quote", subject="300750.SZ"))
    assert calls[0] == "init:8613800000000" and "get_stock_daily" in calls
    assert len(quotes) == 2 and quotes[0].origin == "live"
    assert quotes[0].source == "pandaai-sdk:quote"
    assert quotes[1].payload["close"] is None  # NaN normalized to None

    calendar = await client.fetch(DataRequest(kind="calendar", subject="SH"))
    assert len(calendar) == 1 and calendar[0].kind == "calendar"
    # init_token ran exactly once across both fetches
    assert calls.count("init:8613800000000") == 1
    assert panda_client_module.SdkPandaClient._token_ready is True
