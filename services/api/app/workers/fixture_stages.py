"""Deterministic stage responses for the key-free (FIXTURE_MODE) analysis path.

Why this module exists: ``FixtureModelProvider`` only ever answered from an
explicitly registered ``responses`` map, and the worker registers nothing, so
every stage of a ``FIXTURE_MODE=true`` run resolved to ``{}`` and raised
``EmptyModelContentError``. The run was parked ``needs_attention`` within
seconds. That was recorded once as "fixture-mode deep analysis parks by
design", but it is not by design: ``compose.prototype.yaml`` advertises the
worker as deterministic and key-free, and AGENTS.md section 8 requires the
fixture path to be runnable without a key. This module makes that true.

Two invariants:

- **Deterministic.** No clock, no randomness, no network. The same stage always
  produces the same object, so a fixture run is replayable byte for byte.
- **Never impersonating live analysis.** Every headline and fact is prefixed
  ``[fixture]`` and every source is graded ``L6`` with the name stating it is a
  fixture, not a retrieved source. A reader (and the evidence funnel) can see
  that this run rests on no external evidence: the funnel's low-trust warning
  and the gate's evidence penalty both fire on purpose.

Scope: the ``focused`` pipeline reaches ``ready``. A ``full`` run additionally
requires five discriminative lens artifacts; those are not synthesized here, so
a fixture ``full`` run blocks at the lens audit - an honest verdict, not a
crash.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from app.agents.model_provider import ModelMessage

_TAG = "[fixture]"

# Three facts: two supporting/neutral and one OPPOSING. The funnel discards a
# fact whose conclusion is thin or filler, and warns when nothing opposes, so a
# fixture fact base that cannot survive its own funnel would be pointless.
_PACKETS: tuple[Mapping[str, Any], ...] = (
    {
        "factor": f"{_TAG} 目标市场规模",
        "framework_used": "fixture-deterministic",
        "conclusion": (
            f"{_TAG} 确定性占位事实：救援市场采购集中在少数机构客户，单笔金额高但决策周期长，"
            "本次运行没有任何外部检索作为支撑。"
        ),
        "direction": "supporting",
        "claim_support_score": 0.5,
        "sources": [{"name": f"{_TAG} 确定性占位来源（非检索结果）", "tier": "L6"}],
        "disclaimer": "fixture 占位内容，不可作为真实市场判断。",
    },
    {
        "factor": f"{_TAG} 交付与服务成本",
        "framework_used": "fixture-deterministic",
        "conclusion": (
            f"{_TAG} 确定性占位事实：家庭服务场景的单机毛利更低，且售后与服务网络投入前置，"
            "在资源受限时会挤压研发预算。"
        ),
        "direction": "neutral",
        "claim_support_score": 0.5,
        "sources": [{"name": f"{_TAG} 确定性占位来源（非检索结果）", "tier": "L6"}],
        "disclaimer": "fixture 占位内容，不可作为真实成本判断。",
    },
    {
        "factor": f"{_TAG} 认证与合规门槛",
        "framework_used": "fixture-deterministic",
        "conclusion": (
            f"{_TAG} 确定性占位反方事实：救援场景的认证与可靠性门槛显著更高，"
            "会推迟首次收入，这一条与优先进入救援市场的方向相反。"
        ),
        "direction": "opposing",
        "claim_support_score": 0.5,
        "sources": [{"name": f"{_TAG} 确定性占位来源（非检索结果）", "tier": "L6"}],
        "disclaimer": "fixture 占位内容，不可作为真实合规判断。",
    },
)

# Endpoints must be labels of admitted packets or admission drops them.
_INFLUENCES: tuple[Mapping[str, str], ...] = (
    {
        "from": f"{_TAG} 认证与合规门槛",
        "to": f"{_TAG} 目标市场规模",
        "polarity": "-",
        "evidenceNote": f"{_TAG} 占位因果说明：认证周期推迟可触达的规模。",
    },
    {
        "from": f"{_TAG} 交付与服务成本",
        "to": f"{_TAG} 目标市场规模",
        "polarity": "-",
        "evidenceNote": f"{_TAG} 占位因果说明：服务成本挤压可投入的扩张。",
    },
)


def _digest(
    headline: str,
    key_findings: Sequence[str],
    risks: Sequence[str] = (),
    open_questions: Sequence[str] = (),
) -> dict[str, Any]:
    digest: dict[str, Any] = {
        "headline": f"{_TAG} {headline}",
        "keyFindings": [f"{_TAG} {item}" for item in key_findings],
    }
    if risks:
        digest["risks"] = [f"{_TAG} {item}" for item in risks]
    if open_questions:
        digest["openQuestions"] = [f"{_TAG} {item}" for item in open_questions]
    return digest


def _planning() -> dict[str, Any]:
    return {
        "output": {
            "decisiveSubQuestions": [
                f"{_TAG} 哪一个市场的首次收入时间更早？",
                f"{_TAG} 哪一个市场的失败可以低成本退出？",
            ],
            "flipAssumption": f"{_TAG} 假设认证周期可控；若不成立，优先顺序反转。",
            "digest": _digest(
                "确定性占位规划：先比首次收入时间与退出成本，再比市场规模。",
                [
                    "两个市场的决定性差异是认证周期而非需求总量。",
                    "资源受限下，退出成本比理论天花板更关键。",
                ],
                risks=["占位内容不含真实市场数据，不能替代一次真实分析。"],
                open_questions=["认证周期的真实区间需要外部来源验证。"],
            ),
        },
        "packets": [],
        "lensPayloads": {},
        "qualityGatePassed": True,
        "validatorFindings": [],
    }


def _retrieving() -> dict[str, Any]:
    return {
        "output": {
            "factBaseNote": f"{_TAG} 本次运行没有外部检索；以下是确定性占位事实。",
            "influences": [dict(edge) for edge in _INFLUENCES],
            "digest": _digest(
                "确定性占位事实基座：三条事实，其中一条与主方向相反。",
                [
                    "救援市场客单价高但决策周期长。",
                    "家庭服务毛利更低且服务网络投入前置。",
                    "救援场景认证门槛更高，会推迟首次收入。",
                ],
                risks=["全部来源为 L6 占位，不构成可用证据。"],
            ),
        },
        "packets": [dict(packet) for packet in _PACKETS],
        "lensPayloads": {},
        "qualityGatePassed": True,
        "validatorFindings": [],
    }


def _analyzing() -> dict[str, Any]:
    return {
        "output": {
            "whyNow": f"{_TAG} 占位理由：研发预算只够押注一个市场，拖延本身即是选择。",
            "digest": _digest(
                "确定性占位分析：认证周期是把资源优势转化为收入的瓶颈。",
                [
                    "认证周期越长，现金跑道被消耗得越快。",
                    "服务网络投入决定家庭服务路径的可回撤性。",
                ],
                risks=["占位结论无证据支撑，仅用于验证管线。"],
                open_questions=["真实认证周期与现金跑道的比值是多少？"],
            ),
        },
        "packets": [],
        "lensPayloads": {},
        "qualityGatePassed": True,
        "validatorFindings": [],
    }


def _criticizing() -> dict[str, Any]:
    return {
        "output": {
            "strongestObjection": (
                f"{_TAG} 占位最强反对：若认证周期超出预算跑道，优先救援市场会在拿到"
                "第一笔收入前耗尽现金。"
            ),
            "digest": _digest(
                "确定性占位质疑：失败模式是现金耗尽先于认证通过。",
                [
                    "失败触发条件：认证周期超过现金跑道的一半。",
                    "失败触发条件：机构客户采购延期一个财年。",
                ],
                risks=["占位质疑不替代真实的魔鬼审查。"],
                open_questions=["认证进度可否设置可观测的中途检查点？"],
            ),
        },
        "packets": [],
        "lensPayloads": {},
        "qualityGatePassed": True,
        "validatorFindings": [],
    }


def _synthesizing() -> dict[str, Any]:
    return {
        "output": {
            "decision": (
                f"{_TAG} 占位条件化承诺：在认证周期可在现金跑道一半内完成的条件下先做"
                "救援市场；若中途检查点未通过，则转向家庭服务并保留已完成的可靠性投入。"
            ),
            "digest": _digest(
                "确定性占位综合：带退出规则的条件化承诺，而非无条件命令。",
                [
                    "成立条件：认证中途检查点按期通过。",
                    "退出规则：检查点未过即切换路径。",
                ],
                risks=["占位建议不可用于真实决定。"],
                open_questions=["中途检查点的具体判据由谁签署？"],
            ),
        },
        "packets": [],
        "lensPayloads": {},
        "qualityGatePassed": True,
        "validatorFindings": [],
    }


def _validating() -> dict[str, Any]:
    return {
        "output": {
            "chainAudit": (
                f"{_TAG} 占位校验：结论确实带条件与退出规则，最强反对被条件化吸收；"
                "证据全部为 L6 占位，因此确定性质量门会按弱证据评分。"
            ),
            "digest": _digest(
                "确定性占位校验：链路结构完整，证据强度按占位来源诚实降级。",
                [
                    "结论可由占位事实推出，未出现无支撑跃迁。",
                    "最强反对得到了条件化回应而非忽略。",
                ],
                risks=["证据强度不足是占位模式的固有属性。"],
            ),
        },
        "packets": [],
        "lensPayloads": {},
        "qualityGatePassed": True,
        "validatorFindings": [],
    }


def _safety_anchor() -> dict[str, Any]:
    return {
        "output": {
            "digest": _digest(
                "确定性占位安全锚：若所有方向都错，最可能的原因是把认证周期当作可控变量。",
                [
                    "共同未检验假设：认证机构的排期可以被影响。",
                    "共同未检验假设：两个市场的需求互不影响。",
                ],
                risks=["占位盲区清单不替代真实的独立复核。"],
                open_questions=["认证排期是否真的存在可谈判空间？"],
            )
        },
        "packets": [],
        "lensPayloads": {},
        "qualityGatePassed": True,
        "validatorFindings": [],
    }


def _chief_of_staff() -> dict[str, Any]:
    return {
        "output": {
            "digest": _digest(
                "确定性占位行动建议：由负责人在两周内取得认证机构的书面排期区间。",
                [
                    "负责人取得书面排期区间；前置条件是已提交申请；失败信号是无书面回复。",
                    "财务给出现金跑道下限；前置条件是本月账目关闭；失败信号是口径反复变化。",
                ],
                risks=["占位行动项无真实上下文，执行前须替换为真实分析结果。"],
                open_questions=["若排期无法书面确认，是否直接切换路径？"],
            )
        },
        "packets": [],
        "lensPayloads": {},
        "qualityGatePassed": True,
        "validatorFindings": [],
    }


_BY_STAGE = {
    "planning": _planning,
    "retrieving": _retrieving,
    "analyzing": _analyzing,
    "criticizing": _criticizing,
    "synthesizing": _synthesizing,
    "validating": _validating,
}

_BY_ROLE = {
    "safety_anchor": _safety_anchor,
    "chief_of_staff": _chief_of_staff,
}


def synthesize_stage_response(
    messages: Sequence[ModelMessage],
) -> Mapping[str, Any]:
    """Deterministic stage payload derived from the worker's own request body.

    The worker sends one user message holding a JSON envelope with ``stage`` and
    ``inputs`` (which carry ``roleOverride``/``substage`` for the independent
    enrichment passes). An unparsable or unknown request degrades to a minimal
    but VALID envelope rather than an empty object, so the key-free path never
    fails structurally.
    """

    stage = ""
    role = ""
    if messages:
        try:
            envelope = json.loads(messages[-1].content)
        except (TypeError, ValueError, json.JSONDecodeError):
            envelope = {}
        if isinstance(envelope, Mapping):
            stage = str(envelope.get("stage") or "")
            inputs = envelope.get("inputs")
            if isinstance(inputs, Mapping):
                role = str(inputs.get("roleOverride") or inputs.get("substage") or "")

    builder = _BY_ROLE.get(role) or _BY_STAGE.get(stage)
    if builder is not None:
        return builder()
    return {
        "output": {
            "digest": _digest(
                f"确定性占位输出（未识别的阶段 {stage or '未提供'}）。",
                ["占位内容，仅用于在无 Key 情况下验证管线结构。"],
            )
        },
        "packets": [],
        "lensPayloads": {},
        "qualityGatePassed": True,
        "validatorFindings": [],
    }
