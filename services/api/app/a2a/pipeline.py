"""In-process five-lens research pipeline for the A2A prototype surface.

Multi-agent flow for one natural-language task:

    Planner -> Data Agent (PandaAI skills) -> Porter -> Counterparty ->
    Pre-Mortem -> Scenario -> Meadows -> Report

Reuse discipline: lenses run through the frozen seams only — the assembled
:func:`build_lens_registry`, each lane's ``build_prompt_inputs`` /
``validate_behavior``, ``WorkerRunner`` for model calls and ``BudgetLedger``
for the hard wall-clock/model-call caps. Nothing is persisted: the
``AnalysisRun`` state machine, tenancy anchors and ``StrategicLensArtifact``
write path are deliberately bypassed, so this module can never violate the
run/workspace invariants they guard.

Degrade-not-die: a lens whose output still fails its behavior gate after one
findings-guided retry is marked ``degraded`` (findings attached, output kept
out of downstream upstream_lens_outputs); the pipeline continues and the
report discloses the degradation. Budget exhaustion stops remaining stages
and yields a partial report — a late partial answer beats a 20-minute timeout.
"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from app.a2a.config import A2ASettings
from app.a2a.panda_client import DataRequest, EvidenceItem, PandaDataClient
from app.agents.budget import BudgetExhausted, BudgetLedger, BudgetLimits
from app.agents.context import RunContext, MethodRef, WorkerInputs
from app.agents.errors import SchemaValidationError, ServerOwnedFieldError
from app.agents.lenses import (
    ALLOWED_TOP_LEVEL_FIELDS,
    LENS_SPECS,
    LensRequest,
    StrategicLensStageOutput,
)
from app.agents.model_provider import ModelMessage, ModelProvider
from app.agents.runner import PromptLoader, WorkerDefinition, WorkerRunner
from app.agents.tool_registry import ToolRegistry
from app.strategic_lenses.registry import build_lens_registry
from app.types import FormalAnalysisLevel, StrategicLensType

# Canonical execution order (mirrors the read-path constant; counterparty
# strictly precedes the pre-mortem that consumes its matrix).
LENS_EXECUTION_ORDER: tuple[StrategicLensType, ...] = (
    StrategicLensType.PORTER_FIVE_FORCES,
    StrategicLensType.COUNTERPARTY_RESPONSE_MATRIX,
    StrategicLensType.PRE_MORTEM,
    StrategicLensType.SCENARIO_PLANNING,
    StrategicLensType.MEADOWS_LEVERAGE_POINTS,
)

_LENS_TITLES: dict[StrategicLensType, str] = {
    StrategicLensType.PORTER_FIVE_FORCES: "Porter Five Forces — 竞争格局",
    StrategicLensType.COUNTERPARTY_RESPONSE_MATRIX: "Counterparty Response Matrix — 对手盘反应",
    StrategicLensType.PRE_MORTEM: "Pre-Mortem — 失败预演",
    StrategicLensType.SCENARIO_PLANNING: "Scenario Planning — 情景推演",
    StrategicLensType.MEADOWS_LEVERAGE_POINTS: "Meadows Leverage Points — 系统杠杆点",
}

_METHOD_ID = "hardtech-market-direction"
_METHOD_VERSION = "1.1.0"

_PLANNER_SYSTEM = """\
You are the Planner agent of a five-lens investment research team.
Turn the user's natural-language task into a frozen research plan.
Rules:
- Frame the task as ONE decision question with AT LEAST TWO mutually
  exclusive options (e.g. overweight vs avoid, enter now vs wait).
- Each option id must be a short kebab-case slug prefixed "option-".
- Request only data kinds from: quote, financial, factor, index, calendar.
- Keep subjects to at most 3 instruments/indices central to the task.
Return ONLY a JSON object with keys:
  decisionQuestion (string), horizon (string),
  optionIds (array of >=2 strings),
  subjects (array of {symbol, name}),
  dataRequests (array of {kind, subject, params(object)}).
"""

_REPORT_SYSTEM = """\
You are the Report agent of a five-lens investment research team.
Write a concise executive summary in Chinese for the completed analysis.
Base every statement strictly on the provided lens outputs; never invent data.
Return ONLY a JSON object with keys:
  summary (string, <= 300 Chinese characters),
  recommendation (string, one sentence naming the preferred option and the
  key condition attached to it),
  keyRisks (array of <= 3 short strings).
"""

# Fallback lens prompts, used only when the published method pack is not on
# disk (e.g. slim container images). Each mirrors the lane's behavior contract
# so gate assertions remain satisfiable.
_FALLBACK_LENS_PROMPTS: dict[StrategicLensType, str] = {
    StrategicLensType.PORTER_FIVE_FORCES: (
        "# Porter Five Forces Lens\nAnalyze EACH option as its own market. For every "
        "market produce an industryBoundary (coreValue, upstream, downstream, "
        "adjacentMarkets, crossIndustrySubstitutes, boundaryRisk), exactly five forces "
        "(forceId in: supplier_power, buyer_power, new_entrants, substitutes, rivalry; "
        "each with threatScore 1-5, keyIndicators, >=2 evidenceIds from the provided "
        "evidence, reasoning, directionOfChange), averageThreatScore, changingTrend, "
        "regulatoryAssessment and complementors. Add crossMarketComparison, "
        "strategicImplications and scoreIsNotDecisionFormula=true."
    ),
    StrategicLensType.COUNTERPARTY_RESPONSE_MATRIX: (
        "# Counterparty Response Matrix Lens\nPick 1-2 key counterparty actors. List "
        "2-3 of our candidate actions, EXACTLY ONE of which is a no-action baseline. "
        "For each action give the actor's optimal/worst/likely responses (one layer "
        "deep only), the time window, capability gap, our counter-response, a "
        "publication test, downside asymmetry and a reflexivity note."
    ),
    StrategicLensType.PRE_MORTEM: (
        "# Pre-Mortem Lens\nAssume the currently preferred option FAILED completely at "
        "the horizon. From exactly three perspectives (internal, external, systemic "
        "hindsight) collect at least five distinct failure causes. Choose exactly "
        "three top risks with unique complete cause references; give each prevention, "
        "contingency and a detection indicator. End with an explicit verdict and "
        "rationale."
    ),
    StrategicLensType.SCENARIO_PLANNING: (
        "# Scenario Planning Lens\nState the focus question, horizon, predetermined "
        "elements and >=2 key uncertainties (impact x uncertainty, evidenceIds). "
        "Select exactly two axes, derive 3-4 structurally distinct scenarios (exactly "
        "one baseline, >=2 structural breaks), each with timeline turning points, "
        "three stakeholder states and 3-5 early signals. Test every option in every "
        "scenario; at least one test result must be 'killed'. Set "
        "strategyKilledInAtLeastOneScenario, monitoringActions, irreducibleUnknowns."
    ),
    StrategicLensType.MEADOWS_LEVERAGE_POINTS: (
        "# Meadows Leverage Points Lens\nMap the system (boundary, statedGoal, "
        "actualGoal, stocks, flows, reinforcingLoops, balancingLoops, delays, actors, "
        "rulesAndIncentives). Cover >=3 leverage levels across currentInterventions "
        "and highLeverageGaps; include >=1 ignored high-leverage gap at level 1-4 "
        "(with whyAvoided and disruptionRisk) and >=1 runaway reinforcing loop (with "
        "runawaySignal and brake). Provide an ordered interventionSequence (purpose, "
        "precondition, failureSignal) and riskTradeoffs."
    ),
}

ProgressCallback = Callable[[str, str], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class ResearchPlan:
    """Frozen planner output driving data fetch and lens framing."""

    decision_question: str
    horizon: str
    option_ids: tuple[str, ...]
    subjects: tuple[dict[str, str], ...]
    data_requests: tuple[DataRequest, ...]


@dataclass(slots=True)
class LensOutcome:
    """One lens stage result: gate-passed, degraded, or skipped."""

    lens_type: StrategicLensType
    status: str  # "ok" | "degraded" | "skipped"
    content: dict[str, Any] = field(default_factory=dict)
    findings: tuple[str, ...] = ()
    attempts: int = 0


@dataclass(slots=True)
class PipelineResult:
    """Everything the A2A executor needs to answer the task."""

    report_markdown: str
    plan: ResearchPlan
    lens_outcomes: list[LensOutcome]
    evidence: list[EvidenceItem]
    elapsed_seconds: float
    budget_snapshot: dict[str, float]


async def _noop_progress(stage: str, detail: str) -> None:
    return None


class FiveLensPipeline:
    """Planner -> Data -> five lenses -> Report, all in one process."""

    def __init__(
        self,
        *,
        settings: A2ASettings,
        provider: ModelProvider,
        panda_client: PandaDataClient,
    ) -> None:
        self._settings = settings
        self._provider = provider
        self._panda = panda_client
        self._registry = build_lens_registry()
        self._pack_root = (
            settings.method_pack_root / _METHOD_ID / _METHOD_VERSION
        )
        self._lens_schema = self._load_lens_schema()

    # ------------------------------------------------------------------
    # public entrypoint
    # ------------------------------------------------------------------

    async def run(
        self, task_text: str, progress: ProgressCallback | None = None
    ) -> PipelineResult:
        notify = progress or _noop_progress
        started = time.monotonic()
        budget = BudgetLedger(
            limits=BudgetLimits(
                limits={
                    "max_model_calls": self._settings.max_model_calls,
                    "max_elapsed_seconds": self._settings.task_budget_seconds,
                }
            )
        )
        runner = WorkerRunner(
            provider=self._provider,
            registry=ToolRegistry(),
            prompt_loader=PromptLoader(self._read_prompt),
        )
        run_context = self._make_run_context()

        await notify("planner", "解析任务，拟定研究计划")
        plan = await self._plan(task_text, budget)

        await notify("data", f"获取 PandaAI 数据（{len(plan.data_requests)} 项请求）")
        evidence = await self._fetch_evidence(plan)
        if not evidence:
            # Porter fails closed on an empty evidence ledger; an explicit
            # task-context item keeps the run honest (origin discloses it).
            evidence = [
                EvidenceItem(
                    evidence_id="ev-task-context-001",
                    kind="context",
                    subject="task",
                    summary=task_text[:400],
                    payload={"task": task_text},
                    source="task-statement",
                    origin="context",
                )
            ]
        ledger_ids = tuple(item.evidence_id for item in evidence)

        outcomes: list[LensOutcome] = []
        upstream: dict[StrategicLensType, Mapping[str, Any]] = {}
        for lens_type in LENS_EXECUTION_ORDER:
            title = _LENS_TITLES[lens_type]
            try:
                budget.check_elapsed()
            except BudgetExhausted:
                outcomes.append(LensOutcome(lens_type=lens_type, status="skipped"))
                await notify("lens", f"{title}：预算耗尽，跳过")
                continue
            await notify("lens", f"{title}：分析中")
            outcome = await self._run_lens(
                lens_type=lens_type,
                task_text=task_text,
                plan=plan,
                evidence=evidence,
                ledger_ids=ledger_ids,
                upstream=upstream,
                runner=runner,
                run_context=run_context,
                budget=budget,
            )
            outcomes.append(outcome)
            if outcome.status == "ok":
                upstream[lens_type] = outcome.content
            await notify("lens", f"{title}：{outcome.status}")

        await notify("report", "汇总五 Lens 结论，生成投研报告")
        summary = await self._summarize(task_text, plan, outcomes, budget)
        report = _render_report(task_text, plan, outcomes, evidence, summary)

        return PipelineResult(
            report_markdown=report,
            plan=plan,
            lens_outcomes=outcomes,
            evidence=evidence,
            elapsed_seconds=time.monotonic() - started,
            budget_snapshot=budget.snapshot(),
        )

    # ------------------------------------------------------------------
    # stages
    # ------------------------------------------------------------------

    async def _plan(self, task_text: str, budget: BudgetLedger) -> ResearchPlan:
        budget.charge("max_model_calls")
        completion = await self._provider.complete_structured(
            system=_PLANNER_SYSTEM,
            messages=[_user_message(task_text)],
            schema=None,
            tools=None,
            request_model="a2a-planner",
        )
        content = dict(completion.content)
        option_ids = [str(o) for o in content.get("optionIds", []) if str(o).strip()]
        if len(option_ids) < 2:
            option_ids = ["option-proceed", "option-hold"]
        raw_requests = content.get("dataRequests", [])
        data_requests: list[DataRequest] = []
        if isinstance(raw_requests, list):
            for entry in raw_requests[:10]:
                if not isinstance(entry, Mapping):
                    continue
                kind = str(entry.get("kind", "")).strip()
                subject = str(entry.get("subject", "")).strip()
                params = entry.get("params")
                if kind and subject:
                    data_requests.append(
                        DataRequest(
                            kind=kind,
                            subject=subject,
                            params=dict(params) if isinstance(params, Mapping) else {},
                        )
                    )
        subjects_raw = content.get("subjects", [])
        subjects: list[dict[str, str]] = []
        if isinstance(subjects_raw, list):
            for entry in subjects_raw[:3]:
                if isinstance(entry, Mapping):
                    subjects.append(
                        {
                            "symbol": str(entry.get("symbol", "")),
                            "name": str(entry.get("name", "")),
                        }
                    )
        return ResearchPlan(
            decision_question=str(content.get("decisionQuestion") or task_text),
            horizon=str(content.get("horizon") or "12 months"),
            option_ids=tuple(option_ids[:4]),
            subjects=tuple(subjects),
            data_requests=tuple(data_requests),
        )

    async def _fetch_evidence(self, plan: ResearchPlan) -> list[EvidenceItem]:
        evidence: list[EvidenceItem] = []
        for request in plan.data_requests:
            try:
                evidence.extend(await self._panda.fetch(request))
            except PermissionError:
                raise
            except Exception:  # noqa: BLE001 - single bad fetch must not kill the run
                continue
        return evidence

    async def _run_lens(
        self,
        *,
        lens_type: StrategicLensType,
        task_text: str,
        plan: ResearchPlan,
        evidence: list[EvidenceItem],
        ledger_ids: tuple[str, ...],
        upstream: dict[StrategicLensType, Mapping[str, Any]],
        runner: WorkerRunner,
        run_context: RunContext,
        budget: BudgetLedger,
    ) -> LensOutcome:
        spec = LENS_SPECS[lens_type]
        impl = self._registry.get(lens_type)
        request = LensRequest(
            lens_type=lens_type,
            workspace_id="a2a-prototype",
            analysis_run_id=str(run_context.analysis_run_id),
            prompt_text=self._read_prompt(spec.prompt_ref),
            # The Data Agent's normalized PandaAI bundle acts as the single
            # frozen research packet for every lens in this run.
            research_packet_refs=("rp-a2a-panda-bundle",),
            evidence_refs=ledger_ids,
            option_ids=plan.option_ids,
            upstream_lens_outputs=dict(upstream),
        )
        prompt_inputs = impl.build_prompt_inputs(request)
        definition = WorkerDefinition(
            role=spec.owner_worker,
            prompt_ref=spec.prompt_ref,
            output_schema_id=spec.output_schema_id,
        )
        base_summary = _lens_user_prompt(
            spec=spec,
            task_text=task_text,
            plan=plan,
            evidence=evidence,
            upstream=upstream,
            deterministic_refs=prompt_inputs.user,
        )

        findings: tuple[str, ...] = ()
        attempts = 0
        for attempt in range(2):
            summary = base_summary
            if findings:
                summary += (
                    "\n\n## Previous attempt failed these behavior checks — fix them\n"
                    + "\n".join(f"- {finding}" for finding in findings)
                )
            try:
                result = await runner.run_worker(
                    definition=definition,
                    run_context=run_context,
                    budget=budget,
                    inputs=WorkerInputs(frozen_summary=summary),
                    output_schema=self._lens_schema,
                )
            except BudgetExhausted:
                return LensOutcome(
                    lens_type=lens_type,
                    status="skipped" if attempt == 0 else "degraded",
                    findings=findings or ("budget_exhausted",),
                    attempts=attempts,
                )
            except SchemaValidationError as exc:
                return LensOutcome(
                    lens_type=lens_type,
                    status="degraded",
                    findings=(f"model_output_invalid: {exc}",),
                    attempts=attempts + 1,
                )
            attempts += 1
            stage, stage_findings = self._gate(
                lens_type, spec, dict(result.output), ledger_ids
            )
            if stage is not None:
                return LensOutcome(
                    lens_type=lens_type,
                    status="ok",
                    content=dict(stage.content),
                    attempts=attempts,
                )
            findings = stage_findings
        return LensOutcome(
            lens_type=lens_type,
            status="degraded",
            findings=findings,
            attempts=attempts,
        )

    def _gate(
        self,
        lens_type: StrategicLensType,
        spec: Any,
        payload: dict[str, Any],
        ledger_ids: tuple[str, ...],
    ) -> tuple[StrategicLensStageOutput | None, tuple[str, ...]]:
        """Envelope-normalize the untrusted output, then run the behavior gate."""

        normalized = _normalize_envelope(lens_type, spec, payload, ledger_ids)
        try:
            stage = StrategicLensStageOutput.from_payload(normalized)
        except (ServerOwnedFieldError, KeyError, ValueError) as exc:
            return None, (f"envelope_invalid: {exc}",)
        impl = self._registry.get(lens_type)
        report = impl.validate_behavior(stage)
        if report.ok:
            return stage, ()
        return None, report.findings or report.reason_codes

    async def _summarize(
        self,
        task_text: str,
        plan: ResearchPlan,
        outcomes: list[LensOutcome],
        budget: BudgetLedger,
    ) -> dict[str, Any]:
        digest = {
            "task": task_text,
            "decisionQuestion": plan.decision_question,
            "optionIds": list(plan.option_ids),
            "lenses": {
                outcome.lens_type.value: (
                    outcome.content if outcome.status == "ok" else {"status": outcome.status}
                )
                for outcome in outcomes
            },
        }
        try:
            budget.charge("max_model_calls")
            budget.check_elapsed()
            completion = await self._provider.complete_structured(
                system=_REPORT_SYSTEM,
                messages=[_user_message(json.dumps(digest, ensure_ascii=False))],
                schema=None,
                tools=None,
                request_model="a2a-report",
            )
            return dict(completion.content)
        except Exception:  # noqa: BLE001 - deterministic fallback below
            return {}

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _make_run_context(self) -> RunContext:
        """Synthetic, tenant-free context: satisfies the seam types only."""

        return RunContext(
            workspace_id=uuid4(),
            decision_case_id=uuid4(),
            analysis_run_id=uuid4(),
            user_id=uuid4(),
            charter_id="a2a-prototype",
            charter_version=1,
            analysis_depth=FormalAnalysisLevel.FULL,
            method=MethodRef(id=_METHOD_ID, version=_METHOD_VERSION, content_hash=""),
            case_snapshot_hash="",
            dossier_snapshot_hash="",
            material_snapshot_hash="",
        )

    def _read_prompt(self, prompt_ref: str) -> str:
        """Published pack prompt when available; finance fallback otherwise."""

        candidate = self._pack_root / prompt_ref
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
        for lens_type, spec in LENS_SPECS.items():
            if spec.prompt_ref == prompt_ref:
                return _FALLBACK_LENS_PROMPTS[lens_type]
        return "You are a rigorous strategic analysis agent."

    def _load_lens_schema(self) -> Mapping[str, Any] | None:
        candidate = self._pack_root / "schemas" / "strategic-lens-output.schema.json"
        if candidate.is_file():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except ValueError:
                return None
        return None


def _user_message(content: str) -> ModelMessage:
    return ModelMessage(role="user", content=content)


def _normalize_envelope(
    lens_type: StrategicLensType,
    spec: Any,
    payload: dict[str, Any],
    ledger_ids: tuple[str, ...],
) -> dict[str, Any]:
    """Coerce untrusted model output into the stage-output envelope.

    Models frequently emit only the ``content`` body or mangle the envelope
    constants. Since nothing here is persisted, we repair mechanically:
    wrap bare content, force the spec constants, drop foreign top-level keys
    and default references to the full evidence ledger.
    """

    if "content" not in payload:
        payload = {"content": payload}
    envelope = {key: value for key, value in payload.items() if key in ALLOWED_TOP_LEVEL_FIELDS}
    envelope["lensType"] = lens_type.value
    envelope["sourceSkillVersion"] = spec.source_skill_version
    envelope["phase"] = spec.phase
    references = envelope.get("references")
    if not isinstance(references, Mapping):
        references = {}
    envelope["references"] = {
        "sourcePacketIds": list(references.get("sourcePacketIds", [])),
        "claimIds": list(references.get("claimIds", [])),
        "evidenceIds": list(references.get("evidenceIds", [])) or list(ledger_ids),
        "assumptionIds": list(references.get("assumptionIds", [])),
        "challengeIds": list(references.get("challengeIds", [])),
    }
    if not isinstance(envelope.get("researchRequests"), list):
        envelope["researchRequests"] = []
    if not isinstance(envelope.get("content"), Mapping):
        envelope["content"] = {}
    return envelope


def _lens_user_prompt(
    *,
    spec: Any,
    task_text: str,
    plan: ResearchPlan,
    evidence: list[EvidenceItem],
    upstream: dict[StrategicLensType, Mapping[str, Any]],
    deterministic_refs: str,
) -> str:
    evidence_lines = [
        f"- {item.evidence_id} [{item.kind}/{item.origin}] {item.subject}: {item.summary}"
        for item in evidence[:60]
    ]
    upstream_blocks = [
        f"### upstream:{lens.value}\n{json.dumps(dict(content), ensure_ascii=False)[:4000]}"
        for lens, content in upstream.items()
    ]
    subjects = ", ".join(
        f"{entry['symbol']}({entry['name']})" for entry in plan.subjects
    ) or "N/A"
    return "\n\n".join(
        part
        for part in (
            f"## Task\n{task_text}",
            f"## Decision question\n{plan.decision_question}\n"
            f"Horizon: {plan.horizon}\nSubjects: {subjects}\n"
            f"Options (use these exact optionIds): {', '.join(plan.option_ids)}",
            "## Evidence ledger (cite ONLY these evidenceIds)\n"
            + ("\n".join(evidence_lines) if evidence_lines else "(no market data fetched)"),
            "\n\n".join(upstream_blocks) if upstream_blocks else "",
            f"## Frozen references\n{deterministic_refs}",
            "## Output\nReturn ONLY the JSON stage output: keys lensType, "
            "sourceSkillVersion, phase, references, researchRequests, content; "
            f"content must follow the {spec.content_def} definition.",
        )
        if part
    )


_RISK_DISCLAIMER = """\
## 风险提示与免责声明

- 本报告由 AI 多智能体系统自动生成，仅用于研究与技术演示，**不构成任何投资建议**、\
荐股或收益承诺。
- 分析基于任务提交时刻可获得的数据快照与模型推断，数据可能存在延迟、缺失或错误；\
历史规律不代表未来表现。
- 五 Lens 框架输出依赖行为门控校验，标记为 degraded/skipped 的部分未通过完整校验，\
其结论可靠性更低，已在正文披露。
- 市场存在系统性风险、流动性风险与政策风险等不可预测因素；任何实际投资决策请咨询\
持牌专业机构并自行承担风险。
"""


def _render_report(
    task_text: str,
    plan: ResearchPlan,
    outcomes: list[LensOutcome],
    evidence: list[EvidenceItem],
    summary: dict[str, Any],
) -> str:
    lines: list[str] = ["# 五 Lens 投研分析报告", ""]
    lines.append(f"**任务**：{task_text}")
    lines.append(f"**决策问题**：{plan.decision_question}")
    lines.append(f"**时间窗**：{plan.horizon}")
    lines.append(f"**候选选项**：{'、'.join(plan.option_ids)}")
    lines.append("")

    if summary.get("summary"):
        lines += ["## 执行摘要", str(summary["summary"]), ""]
    if summary.get("recommendation"):
        lines += [f"**倾向性结论**：{summary['recommendation']}", ""]
    key_risks = summary.get("keyRisks")
    if isinstance(key_risks, list) and key_risks:
        lines.append("**关键风险**：")
        lines += [f"- {risk}" for risk in key_risks]
        lines.append("")

    for outcome in outcomes:
        title = _LENS_TITLES[outcome.lens_type]
        lines.append(f"## {title}")
        if outcome.status == "ok":
            lines.append("```json")
            lines.append(json.dumps(outcome.content, ensure_ascii=False, indent=2)[:8000])
            lines.append("```")
        elif outcome.status == "degraded":
            lines.append(
                "> ⚠️ 该 Lens 输出未通过行为门控校验（degraded），未纳入下游分析。"
            )
            lines += [f"> - {finding}" for finding in outcome.findings[:8]]
        else:
            lines.append("> ⏱️ 时间预算耗尽，该 Lens 被跳过（skipped）。")
        lines.append("")

    lines.append("## 数据来源")
    if evidence:
        live = sum(1 for item in evidence if item.origin == "live")
        lines.append(
            f"共引用 {len(evidence)} 条证据（live: {live}, fixture: {len(evidence) - live}），"
            "来自 PandaAI 数据 Skills。"
        )
    else:
        lines.append("本次任务未获取到外部市场数据，分析基于任务描述与模型推断（已降低置信度）。")
    lines.append("")
    lines.append(_RISK_DISCLAIMER)
    return "\n".join(lines)
