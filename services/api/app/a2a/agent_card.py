"""Agent Card for the PandaAI track submission (A2A discovery document).

Served at ``/.well-known/agent-card.json`` by the mounted a2a-sdk app. Skill
names here are the public contract quoted in the submission docs; keep them
in sync with ``docs/a2a-submission/README.md``.
"""

from __future__ import annotations

from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from app.a2a.config import A2ASettings

_DESCRIPTION = (
    "Ludus Five-Lens Research Agent — a multi-agent investment research team. "
    "A Planner agent frames the decision, a Data agent pulls PandaAI market/"
    "fundamental/factor data, then five strategy lenses run in canonical order "
    "(Porter Five Forces, Counterparty Response Matrix, Pre-Mortem, Scenario "
    "Planning, Meadows Leverage Points), each behavior-gated, and a Report "
    "agent assembles an evidence-referenced research report with mandatory "
    "risk disclosures. Educational research output only; not investment advice."
)


def build_agent_card(settings: A2ASettings) -> AgentCard:
    return AgentCard(
        name=settings.agent_name,
        description=_DESCRIPTION,
        url=f"{settings.public_url}/a2a",
        version=settings.agent_version,
        protocol_version="0.3.0",
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[
            AgentSkill(
                id="five_lens_research",
                name="five_lens_research",
                description=(
                    "Run the full five-lens multi-agent research workflow on a "
                    "natural-language investment question and return a "
                    "structured Chinese research report."
                ),
                tags=["research", "multi-agent", "strategy"],
                examples=[
                    "分析宁德时代未来两年的竞争格局与下行风险，判断应该增持还是回避",
                    "对中证新能源指数做 12 个月的情景推演，并给出监控信号",
                ],
            ),
            AgentSkill(
                id="market_data_analysis",
                name="market_data_analysis",
                description=(
                    "Fetch quotes, fundamentals, factors, index and trading-"
                    "calendar data through PandaAI data skills and ground every "
                    "lens conclusion in referenced evidence items."
                ),
                tags=["data", "market", "pandaai"],
                examples=["用最近一年的行情与财务数据评估贵州茅台的竞争壁垒变化"],
            ),
            AgentSkill(
                id="risk_premortem",
                name="risk_premortem",
                description=(
                    "Adversarial Pre-Mortem stress test: assume the preferred "
                    "position failed, enumerate failure causes from three "
                    "perspectives and return top risks with prevention, "
                    "contingency and detection indicators."
                ),
                tags=["risk", "premortem", "critic"],
                examples=["对重仓白酒板块的组合做一次失败预演，找出前三大风险"],
            ),
        ],
    )
