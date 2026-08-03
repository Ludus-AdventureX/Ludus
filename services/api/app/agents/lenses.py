"""Strategic-lens contract seam.

This module is the stable interface the five lens specialists (lane conversations
7-11) implement against. It mirrors the *immutable published* contract from
``method-packs/hardtech-market-direction/1.1.0`` - it does not redefine or mutate
it:

* the untrusted model stage output shape (``strategic-lens-output`` schema);
* the split between model-writable fields and server-owned identity/provenance;
* the canonical five-lens set, order, owning worker, phase and trigger;
* the per-lens behavior contract each specialist must enforce.

Each specialist provides one :class:`LensImplementation` (prompt input assembly +
behavior validation) for a single ``lensType`` in ``strategic_lenses/lenses/`` on
their own branch. The Ways Coordinator owns this seam, the registry and the shared
persistence/report wiring; specialists never touch shared schema/migration/API.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from app.types import FULL_REQUIRED_STRATEGIC_LENSES, StrategicLensType

from .errors import ServerOwnedFieldError, UnknownLensType

# --- Version pins mirrored from the published pack (immutable) --------------------
METHOD_ID = "hardtech-market-direction"
METHOD_VERSION = "1.1.0"
LENS_OUTPUT_SCHEMA_ID = (
    "urn:ludus:method:hardtech-market-direction:strategic-lens-output:1.1.0"
)
# The schema pins ``sourceSkillVersion`` to this const.
SOURCE_SKILL_VERSION = "1.0.0"

# Model-writable top-level fields vs server-owned fields (manifest
# ``lens_artifact_contract``). A specialist that emits any server-owned field fails
# closed - the server injects identity, provenance, status, hash and timestamps.
ALLOWED_TOP_LEVEL_FIELDS: frozenset[str] = frozenset(
    {"lensType", "sourceSkillVersion", "phase", "references", "researchRequests", "content"}
)
FORBIDDEN_SERVER_OWNED_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "artifactId",
        "workspaceId",
        "decisionCaseId",
        "analysisRunId",
        "charterId",
        "charterVersion",
        "caseVersion",
        "caseSnapshotHash",
        "methodId",
        "methodVersion",
        "methodContentHash",
        "schemaVersion",
        "producerRole",
        "status",
        "originModes",
        "contentHash",
        "createdAt",
    }
)
REFERENCE_KEYS: tuple[str, ...] = (
    "sourcePacketIds",
    "claimIds",
    "evidenceIds",
    "assumptionIds",
    "challengeIds",
)


# Full content examples for the three lenses whose behavior gates demand nested
# fields the JSON-schema text alone does not pin down. Live models emit the
# top-level skeleton but omit array-element fields (e.g. porter forces), so the
# contract now carries a complete, gate-passing content shape. The ``ev-sample-*``
# ids are placeholders the model MUST replace with ids from the frozen lists.
_PORTER_CONTENT_EXAMPLE: dict[str, Any] = {
    "marketAnalyses": [
        {
            "optionId": "opt_a",
            "industryBoundary": {
                "coreValue": "示例：该市场为购买方创造的核心价值",
                "upstream": ["示例：上游供应商类别"],
                "downstream": ["示例：下游渠道与客户"],
                "adjacentMarkets": ["示例：相邻市场"],
                "crossIndustrySubstitutes": ["示例：跨行业替代品"],
                "boundaryRisk": "示例：边界过宽或过窄的错判风险",
            },
            "forces": [
                {
                    "forceId": "rivalry",
                    "threatScore": 3,
                    "keyIndicators": ["示例：集中度"],
                    "evidenceIds": ["ev-sample-1", "ev-sample-2"],
                    "reasoning": "示例：该力的推理链",
                    "directionOfChange": "stable",
                },
                {
                    "forceId": "new_entrants",
                    "threatScore": 4,
                    "keyIndicators": ["示例：进入壁垒"],
                    "evidenceIds": ["ev-sample-3", "ev-sample-4"],
                    "reasoning": "示例：该力的推理链",
                    "directionOfChange": "strengthening",
                },
                {
                    "forceId": "substitutes",
                    "threatScore": 2,
                    "keyIndicators": ["示例：替代性价比"],
                    "evidenceIds": ["ev-sample-5", "ev-sample-6"],
                    "reasoning": "示例：该力的推理链",
                    "directionOfChange": "stable",
                },
                {
                    "forceId": "supplier_power",
                    "threatScore": 3,
                    "keyIndicators": ["示例：供应商集中度"],
                    "evidenceIds": ["ev-sample-7", "ev-sample-8"],
                    "reasoning": "示例：该力的推理链",
                    "directionOfChange": "stable",
                },
                {
                    "forceId": "buyer_power",
                    "threatScore": 3,
                    "keyIndicators": ["示例：买家集中度"],
                    "evidenceIds": ["ev-sample-9", "ev-sample-10"],
                    "reasoning": "示例：该力的推理链",
                    "directionOfChange": "stable",
                },
            ],
            "averageThreatScore": 3.0,
            "changingTrend": "示例：正在变化的技术/政策/需求趋势",
            "regulatoryAssessment": "示例：监管评估",
            "complementors": ["示例：互补者"],
        },
        {
            "optionId": "opt_b",
            "industryBoundary": {
                "coreValue": "示例：该市场为购买方创造的核心价值",
                "upstream": ["示例：上游供应商类别"],
                "downstream": ["示例：下游渠道与客户"],
                "adjacentMarkets": ["示例：相邻市场"],
                "crossIndustrySubstitutes": ["示例：跨行业替代品"],
                "boundaryRisk": "示例：边界错判风险",
            },
            "forces": [
                {
                    "forceId": "rivalry",
                    "threatScore": 3,
                    "keyIndicators": ["示例：集中度"],
                    "evidenceIds": ["ev-sample-1", "ev-sample-2"],
                    "reasoning": "示例：该力的推理链",
                    "directionOfChange": "stable",
                },
                {
                    "forceId": "new_entrants",
                    "threatScore": 3,
                    "keyIndicators": ["示例：进入壁垒"],
                    "evidenceIds": ["ev-sample-3", "ev-sample-4"],
                    "reasoning": "示例：该力的推理链",
                    "directionOfChange": "stable",
                },
                {
                    "forceId": "substitutes",
                    "threatScore": 2,
                    "keyIndicators": ["示例：替代性价比"],
                    "evidenceIds": ["ev-sample-5", "ev-sample-6"],
                    "reasoning": "示例：该力的推理链",
                    "directionOfChange": "weakening",
                },
                {
                    "forceId": "supplier_power",
                    "threatScore": 4,
                    "keyIndicators": ["示例：供应商集中度"],
                    "evidenceIds": ["ev-sample-7", "ev-sample-8"],
                    "reasoning": "示例：该力的推理链",
                    "directionOfChange": "strengthening",
                },
                {
                    "forceId": "buyer_power",
                    "threatScore": 3,
                    "keyIndicators": ["示例：买家集中度"],
                    "evidenceIds": ["ev-sample-9", "ev-sample-10"],
                    "reasoning": "示例：该力的推理链",
                    "directionOfChange": "stable",
                },
            ],
            "averageThreatScore": 3.0,
            "changingTrend": "示例：正在变化的技术/政策/需求趋势",
            "regulatoryAssessment": "示例：监管评估",
            "complementors": ["示例：互补者"],
        },
    ],
    "crossMarketComparison": "示例：跨市场对比与力量差异",
    "strategicImplications": [
        {
            "optionId": "opt_a",
            "strategy": "differentiation",
            "logic": "示例：与力量证据形成逻辑链的战略启示",
            "conditions": ["示例：成立的先决条件"],
        }
    ],
    "scoreIsNotDecisionFormula": True,
}


_SCENARIO_CONTENT_EXAMPLE: dict[str, Any] = {
    "focusQuestion": "示例：聚焦的决策问题",
    "timeHorizon": "示例：24 个月",
    "predeterminedElements": ["示例：预定要素"],
    "keyUncertainties": [
        {
            "uncertaintyId": "unc-1",
            "factor": "示例：不确定因素一",
            "impact": "high",
            "uncertainty": "high",
            "evidenceIds": ["ev-sample-1"],
        },
        {
            "uncertaintyId": "unc-2",
            "factor": "示例：不确定因素二",
            "impact": "high",
            "uncertainty": "high",
            "evidenceIds": ["ev-sample-2"],
        },
    ],
    "axes": [
        {
            "axisId": "axis-1",
            "uncertaintyId": "unc-1",
            "lowState": "示例：低态描述",
            "highState": "示例：高态描述",
            "selectionRationale": "示例：为何选该轴",
        },
        {
            "axisId": "axis-2",
            "uncertaintyId": "unc-2",
            "lowState": "示例：低态描述",
            "highState": "示例：高态描述",
            "selectionRationale": "示例：为何选该轴",
        },
    ],
    "scenarios": [
        {
            "scenarioId": "scen-1",
            "name": "示例：基线情景",
            "kind": "baseline",
            "axisStates": ["示例：轴1低态", "示例：轴2低态"],
            "coreLogic": "示例：核心逻辑",
            "timeline": [
                {"period": "示例：2026H2", "turningPoint": "示例：转折点"},
                {"period": "示例：2027H1", "turningPoint": "示例：转折点"},
            ],
            "stakeholderStates": [
                {"stakeholder": "示例：利益相关者A", "state": "示例：状态"},
                {"stakeholder": "示例：利益相关者B", "state": "示例：状态"},
                {"stakeholder": "示例：利益相关者C", "state": "示例：状态"},
            ],
            "earlySignals": [
                {
                    "signalId": "sig-1",
                    "type": "qualitative",
                    "observable": "示例：可观测信号",
                    "thresholdOrPattern": "示例：阈值或模式",
                    "cadence": "示例：观察频率",
                },
                {
                    "signalId": "sig-2",
                    "type": "quantitative",
                    "observable": "示例：可观测信号",
                    "thresholdOrPattern": "示例：阈值或模式",
                    "cadence": "示例：观察频率",
                },
                {
                    "signalId": "sig-3",
                    "type": "structural",
                    "observable": "示例：可观测信号",
                    "thresholdOrPattern": "示例：阈值或模式",
                    "cadence": "示例：观察频率",
                },
            ],
        },
        {
            "scenarioId": "scen-2",
            "name": "示例：结构断裂一",
            "kind": "structural_break",
            "axisStates": ["示例：轴1高态", "示例：轴2低态"],
            "coreLogic": "示例：核心逻辑",
            "timeline": [
                {"period": "示例：2026H2", "turningPoint": "示例：转折点"},
                {"period": "示例：2027H1", "turningPoint": "示例：转折点"},
            ],
            "stakeholderStates": [
                {"stakeholder": "示例：利益相关者A", "state": "示例：状态"},
                {"stakeholder": "示例：利益相关者B", "state": "示例：状态"},
                {"stakeholder": "示例：利益相关者C", "state": "示例：状态"},
            ],
            "earlySignals": [
                {
                    "signalId": "sig-4",
                    "type": "qualitative",
                    "observable": "示例：可观测信号",
                    "thresholdOrPattern": "示例：阈值或模式",
                    "cadence": "示例：观察频率",
                },
                {
                    "signalId": "sig-5",
                    "type": "quantitative",
                    "observable": "示例：可观测信号",
                    "thresholdOrPattern": "示例：阈值或模式",
                    "cadence": "示例：观察频率",
                },
                {
                    "signalId": "sig-6",
                    "type": "structural",
                    "observable": "示例：可观测信号",
                    "thresholdOrPattern": "示例：阈值或模式",
                    "cadence": "示例：观察频率",
                },
            ],
        },
        {
            "scenarioId": "scen-3",
            "name": "示例：结构断裂二",
            "kind": "structural_break",
            "axisStates": ["示例：轴1低态", "示例：轴2高态"],
            "coreLogic": "示例：核心逻辑",
            "timeline": [
                {"period": "示例：2026H2", "turningPoint": "示例：转折点"},
                {"period": "示例：2027H1", "turningPoint": "示例：转折点"},
            ],
            "stakeholderStates": [
                {"stakeholder": "示例：利益相关者A", "state": "示例：状态"},
                {"stakeholder": "示例：利益相关者B", "state": "示例：状态"},
                {"stakeholder": "示例：利益相关者C", "state": "示例：状态"},
            ],
            "earlySignals": [
                {
                    "signalId": "sig-7",
                    "type": "qualitative",
                    "observable": "示例：可观测信号",
                    "thresholdOrPattern": "示例：阈值或模式",
                    "cadence": "示例：观察频率",
                },
                {
                    "signalId": "sig-8",
                    "type": "quantitative",
                    "observable": "示例：可观测信号",
                    "thresholdOrPattern": "示例：阈值或模式",
                    "cadence": "示例：观察频率",
                },
                {
                    "signalId": "sig-9",
                    "type": "structural",
                    "observable": "示例：可观测信号",
                    "thresholdOrPattern": "示例：阈值或模式",
                    "cadence": "示例：观察频率",
                },
            ],
        },
    ],
    "strategyTests": [
        {
            "scenarioId": "scen-1",
            "optionId": "opt_a",
            "performance": "robust",
            "failureReason": "示例：失败原因（robust 可为空描述）",
            "requiredAdjustment": "示例：所需调整",
            "triggerSignalIds": ["sig-1"],
        },
        {
            "scenarioId": "scen-1",
            "optionId": "opt_b",
            "performance": "viable_with_adjustment",
            "failureReason": "示例：失败原因",
            "requiredAdjustment": "示例：所需调整",
            "triggerSignalIds": ["sig-2"],
        },
        {
            "scenarioId": "scen-2",
            "optionId": "opt_a",
            "performance": "killed",
            "failureReason": "示例：被杀死的理由",
            "requiredAdjustment": "示例：所需调整",
            "triggerSignalIds": ["sig-4"],
        },
        {
            "scenarioId": "scen-2",
            "optionId": "opt_b",
            "performance": "high_risk",
            "failureReason": "示例：失败原因",
            "requiredAdjustment": "示例：所需调整",
            "triggerSignalIds": ["sig-5"],
        },
        {
            "scenarioId": "scen-3",
            "optionId": "opt_a",
            "performance": "viable_with_adjustment",
            "failureReason": "示例：失败原因",
            "requiredAdjustment": "示例：所需调整",
            "triggerSignalIds": ["sig-7"],
        },
        {
            "scenarioId": "scen-3",
            "optionId": "opt_b",
            "performance": "robust",
            "failureReason": "示例：失败原因（robust 可为空描述）",
            "requiredAdjustment": "示例：所需调整",
            "triggerSignalIds": ["sig-8"],
        },
    ],
    "strategyKilledInAtLeastOneScenario": True,
    "monitoringActions": ["示例：立即开始的监控动作"],
    "irreducibleUnknowns": ["示例：不可约未知项"],
}


_COUNTERPARTY_CONTENT_EXAMPLE: dict[str, Any] = {
    "maxResponseDepth": 1,
    "counterparties": [
        {
            "counterpartyId": "cp-1",
            "identity": "示例：对手方身份",
            "coreInterest": "示例：核心利益",
            "responseTools": ["示例：可动用的响应工具"],
            "constraints": ["示例：约束条件"],
        }
    ],
    "ourActions": [
        {
            "actionId": "act-1",
            "actionType": "active",
            "description": "示例：主动行动描述",
            "observability": "high",
            "irreversibility": "medium",
            "coreAssumptionIds": ["asm-sample-1"],
        },
        {
            "actionId": "act-2",
            "actionType": "no_action",
            "description": "示例：按兵不动基线",
            "observability": "low",
            "irreversibility": "low",
            "coreAssumptionIds": ["asm-sample-2"],
        },
    ],
    "responseMatrix": [
        {
            "counterpartyId": "cp-1",
            "actionId": "act-1",
            "optimalResponse": "示例：最有利于对手的响应",
            "worstResponseForUs": "示例：对我们最不利的响应",
            "mostLikelyResponse": "示例：最可能发生的响应",
            "responseWindow": "示例：响应窗口",
            "optimalLikelyGap": "示例：最优与最可能的差距",
            "ourCounterResponse": "示例：我们的反制",
            "fallbackCost": "示例：备用方案的代价",
            "strategyInvalidated": False,
        },
        {
            "counterpartyId": "cp-1",
            "actionId": "act-2",
            "optimalResponse": "示例：对手方反应",
            "worstResponseForUs": "示例：对手方最不利反应",
            "mostLikelyResponse": "示例：对手方最可能反应",
            "responseWindow": "示例：响应窗口",
            "optimalLikelyGap": "示例：差距",
            "ourCounterResponse": "示例：反制",
            "fallbackCost": "示例：代价",
            "strategyInvalidated": False,
        },
    ],
    "publicationTest": {
        "responseChangesIfPublished": True,
        "newInformationRevealed": "示例：公布后将暴露的新信息",
        "informationAsymmetryVulnerability": "medium",
        "mitigation": "示例：缓解措施",
    },
    "downsideAsymmetry": [
        {
            "actionId": "act-1",
            "worstCase": "示例：最坏情形",
            "downsideFloor": "bounded",
            "exitPath": "示例：退出路径",
            "exitCost": "示例：退出成本",
        },
        {
            "actionId": "act-2",
            "worstCase": "示例：最坏情形",
            "downsideFloor": "unknown",
            "exitPath": "示例：退出路径",
            "exitCost": "示例：退出成本",
        },
    ],
    "reflexivityWarning": "示例：反身性警示",
}


_MEADOWS_CONTENT_EXAMPLE: dict[str, Any] = {
    "systemMap": {
        "boundary": "示例：系统边界",
        "statedGoal": "示例：宣称目标",
        "actualGoal": "示例：实际目标",
        "stocks": ["示例：存量"],
        "flows": ["示例：流量"],
        "reinforcingLoops": ["示例：增强回路"],
        "balancingLoops": ["示例：平衡回路"],
        "delays": ["示例：延迟"],
        "actors": ["示例：行动者"],
        "rulesAndIncentives": ["示例：规则与激励"],
    },
    "levelsCovered": [1, 2, 5, 10],
    "currentInterventions": [
        {
            "interventionId": "int-1",
            "level": 1,
            "levelName": "transcend_paradigms",
            "strengthBand": "high",
            "target": "示例：干预目标",
            "action": "示例：干预动作",
            "feasibility": "medium",
            "expectedEffect": "示例：预期效果",
            "failureSignal": "示例：失败信号",
        },
        {
            "interventionId": "int-2",
            "level": 5,
            "levelName": "rules",
            "strengthBand": "medium",
            "target": "示例：干预目标",
            "action": "示例：干预动作",
            "feasibility": "high",
            "expectedEffect": "示例：预期效果",
            "failureSignal": "示例：失败信号",
        },
        {
            "interventionId": "int-3",
            "level": 10,
            "levelName": "stock_flow_structure",
            "strengthBand": "low",
            "target": "示例：干预目标",
            "action": "示例：干预动作",
            "feasibility": "medium",
            "expectedEffect": "示例：预期效果",
            "failureSignal": "示例：失败信号",
        },
    ],
    "highLeverageGaps": [
        {
            "interventionId": "int-4",
            "level": 2,
            "levelName": "paradigm",
            "strengthBand": "high",
            "target": "示例：干预目标",
            "action": "示例：干预动作",
            "feasibility": "low",
            "expectedEffect": "示例：预期效果",
            "failureSignal": "示例：失败信号",
            "whyAvoided": "示例：为何被回避",
            "disruptionRisk": "示例：破坏性风险",
        }
    ],
    "runawayPositiveLoops": [
        {
            "loop": "示例：增强回路描述",
            "runawaySignal": "示例：失控信号",
            "brake": "示例：刹车机制",
        }
    ],
    "interventionSequence": [
        {
            "order": 1,
            "interventionId": "int-2",
            "purpose": "trust_building",
            "precondition": "示例：前置条件",
            "failureSignal": "示例：失败信号",
        },
        {
            "order": 2,
            "interventionId": "int-4",
            "purpose": "system_change",
            "precondition": "示例：前置条件",
            "failureSignal": "示例：失败信号",
        },
    ],
    "riskTradeoffs": ["示例：风险权衡"],
}


def load_lens_content_schema(content_def: str) -> str:
    """Return one lens content-branch schema definition as JSON text.

    The published prompts reference the schema only by URN, so live models
    cannot see the file and free-style the ``content`` object; every behavior
    gate then rejects the shape. The output contract carries the branch
    definition verbatim (from the shipped method-pack ``$defs``) so the model
    can emit a schema-shaped content the gate accepts. Empty string when the
    pack is not installed (fixture/test-only runs never need it).
    """

    candidates: list[Path] = [
        Path(
            "/app/method-packs/hardtech-market-direction/1.1.0/schemas/"
            "strategic-lens-output.schema.json"
        )
    ]
    # Local dev fallback: walk up from this file to the repository root. Do not
    # hard-code a parent index - the container tree (/app/app/agents/...) is
    # shallower than the checkout tree (services/api/app/agents/...).
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidates.append(
            parent
            / "method-packs"
            / "hardtech-market-direction"
            / "1.1.0"
            / "schemas"
            / "strategic-lens-output.schema.json"
        )
    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ""
        branch = data.get("$defs", {}).get(content_def)
        return json.dumps(branch, ensure_ascii=False) if branch is not None else ""
    return ""


_CONTENT_EXAMPLES: dict[str, dict[str, Any]] = {
    "porterContent": _PORTER_CONTENT_EXAMPLE,
    "scenarioPlanningContent": _SCENARIO_CONTENT_EXAMPLE,
    "meadowsContent": _MEADOWS_CONTENT_EXAMPLE,
    "counterpartyContent": _COUNTERPARTY_CONTENT_EXAMPLE,
}


def lens_content_example(content_def: str) -> str:
    """Return the gate-passing content example for a lens as JSON text.

    Empty string when no example is shipped for that content branch (the
    counterparty/pre_mortem lenses already pass with the schema text alone).
    """
    example = _CONTENT_EXAMPLES.get(content_def)
    return json.dumps(example, ensure_ascii=False) if example is not None else ""


# Per-lens behavior checklist: the SAME deterministic checks the behavior gate
# runs after the call, written as a model-executable self-audit list. Front-
# loading these constraints (grey-goo style "skill" handoff) makes the model
# self-check before emitting instead of discovering violations only when the
# gate rejects. Keep every line a hard requirement - the gate will enforce it.
_BEHAVIOR_CHECKLISTS: dict[str, tuple[str, ...]] = {
    "counterpartyContent": (
        "counterparties: exactly 1-2, each with counterpartyId/identity/coreInterest/responseTools/constraints",
        "ourActions: exactly 2-3, with EXACTLY ONE actionType='no_action' and the rest 'active'",
        "each ourAction needs actionId/description/observability/irreversibility/coreAssumptionIds",
        "coreAssumptionIds must cite ids from references.assumptionIds only",
        "responseMatrix: one row per (counterpartyId x actionId) pair, every row complete, no extra pairs",
        "each matrix row: optimalResponse/worstResponseForUs/mostLikelyResponse/responseWindow/optimalLikelyGap/ourCounterResponse/fallbackCost/strategyInvalidated",
        "publicationTest: responseChangesIfPublished boolean + newInformationRevealed + informationAsymmetryVulnerability(one of none/low/medium/high/critical) + mitigation",
        "downsideAsymmetry: one entry PER actionId with worstCase/downsideFloor(bounded|unbounded|unknown)/exitPath/exitCost",
        "reflexivityWarning: non-empty; maxResponseDepth MUST be 1",
    ),
    "meadowsContent": (
        "systemMap: boundary/statedGoal/actualGoal/stocks/flows/reinforcingLoops/balancingLoops/delays/actors/rulesAndIncentives all non-empty",
        "levelsCovered: integers 1-12, unique, EXACTLY the distinct levels used across currentInterventions and highLeverageGaps",
        "currentInterventions: each with interventionId/level/levelName/strengthBand/target/action/feasibility/expectedEffect/failureSignal",
        "level/levelName/strengthBand triplets must match the canonical map (1=transcend_paradigms/high ... 12=parameters/low)",
        "highLeverageGaps: each with interventionId/level(1-4)/levelName/strengthBand=high/target/action/feasibility/expectedEffect/failureSignal/whyAvoided/disruptionRisk",
        "runawayPositiveLoops: each with loop/runawaySignal/brake",
        "interventionSequence: at least 2 entries, each with order/interventionId/purpose(one of trust_building/information_gain/system_change/risk_control)/precondition/failureSignal",
        "riskTradeoffs: non-empty array; interventionId must reference an existing currentInterventions or highLeverageGaps id",
    ),
}


def lens_behavior_checklist(content_def: str) -> str:
    """Return the behavior-gate constraints as a self-audit checklist.

    Grey-goo principle: the producing agent must know its acceptance criteria
    BEFORE it writes (like a skill handoff), not only after the gate rejects.
    Empty string when no checklist is shipped for that content branch.
    """

    items = _BEHAVIOR_CHECKLISTS.get(content_def)
    if not items:
        return ""
    return (
        "\n## Behavior contract - self-audit BEFORE you emit (MANDATORY)\n"
        "Your output will be deterministically rejected unless EVERY line holds. "
        "Verify your content object against each line, then emit:\n"
        + "\n".join(f"- [ ] {item}" for item in items)
    )


def lens_output_contract(
    *,
    lens_type: str,
    phase: str,
    source_skill_version: str,
    content_def: str,
    content_schema: str = "",
    content_example: str = "",
    behavior_checklist: str = "",
) -> str:
    """The shared output contract every lens user message must carry.

    Live models only emit fields they are explicitly told about; the five lens
    prompts previously diverged (some never mentioned ``references``), so full
    runs lost every lens to ``KeyError: 'references'`` before the behavior gate
    ever ran. One canonical contract text keeps all lanes aligned with the
    ``strategic-lens-output`` schema the server parses against. Example shape
    is plain JSON text (no fences), mirroring what the model must return.
    """

    top_fields = sorted(ALLOWED_TOP_LEVEL_FIELDS)
    content_line = f"- content: an object matching the {content_def} schema branch"
    if content_schema:
        content_line += ":\n" + content_schema
    example_line = "Example shape:\n" + json.dumps(
        {
            "lensType": lens_type,
            "sourceSkillVersion": source_skill_version,
            "phase": phase,
            "references": {key: [] for key in REFERENCE_KEYS},
            "researchRequests": [],
            "content": {},
        },
        ensure_ascii=False,
    )
    if content_example:
        example_line += (
            "\nExample content (follow this structure EXACTLY - every field shown "
            "is required; the ev-sample-* ids and all 示例： values are placeholders "
            "you MUST replace with real analysis content and ids from the frozen "
            "lists above):\n"
            + content_example
        )
    example_line += (
        "\nConsistency and language rules:\n"
        "- averageThreatScore MUST be the arithmetic mean of the five threatScore "
        "values (porter).\n"
        "- levelsCovered MUST contain exactly the distinct level values used by "
        "currentInterventions and highLeverageGaps (meadows).\n"
        "- EVERY highLeverageGaps element MUST include whyAvoided and "
        "disruptionRisk; every currentInterventions element MUST include every "
        "field shown (meadows).\n"
        "- highLeverageGaps level/levelName/strengthBand must match exactly: "
        "level 1=transcend_paradigms, 2=paradigm, 3=goals, 4=self_organization, "
        "strengthBand always high (meadows).\n"
        "- NEVER write the literal words 成功概率, 概率, probability, 成功率, 胜率, "
        "or chance of success anywhere in content - even in a negation like "
        "'not a success probability' (porter rejects any occurrence).\n"
    )
    return (
        "## Output contract (MANDATORY)\n"
        "Return exactly one JSON object with top-level fields "
        + json.dumps(top_fields, ensure_ascii=False)
        + ". You MUST include every one of these fields, including references.\n"
        + f'- lensType: "{lens_type}"\n'
        + f'- sourceSkillVersion: "{source_skill_version}"\n'
        + f'- phase: "{phase}"\n'
        + "- references: an object with exactly the keys "
        + json.dumps(list(REFERENCE_KEYS), ensure_ascii=False)
        + ", each an array of IDs cited from the frozen lists above; "
        + "use [] where none apply\n"
        + "- researchRequests: an array of request objects ([] if none)\n"
        + content_line
        + "\n"
        + "Never emit server-owned fields "
        + json.dumps(sorted(FORBIDDEN_SERVER_OWNED_FIELDS), ensure_ascii=False)
        + ", markdown fences, hidden reasoning, or success probabilities.\n"
        + example_line
        + behavior_checklist
        + (
            "\n## Decision-chain handoff (Wave D, MANDATORY)\n"
            "You are a specialist sub-agent: the orchestrator merges your "
            "reasoning into the run's decision chain ONLY if you hand it over "
            "as structured links. Emit top-level \"chainLinks\": an array of "
            "2-5 links your lens established, each {\"linkId\": short-unique-id, "
            "\"kind\": \"premise\"|\"evidence\"|\"inference\"|\"decision\", \"text\": "
            "one falsifiable sentence, \"citesEvidenceIds\": [evidence ids from "
            "the frozen lists you actually cited], \"supportsLinkIds\": []}. "
            "Every cited evidence id must come from the frozen reference lists "
            "above - the orchestrator audits resolvability before merging.\n"
        )
    )


@dataclass(frozen=True, slots=True)
class LensSpec:
    """Static, published contract facts for one lens."""

    lens_type: StrategicLensType
    phase: str
    owner_worker: str
    trigger: str
    prompt_ref: str
    content_def: str
    behavior_contract: str
    behavior_assertions: tuple[str, ...]
    required_focused: bool
    required_full: bool
    output_schema_id: str = LENS_OUTPUT_SCHEMA_ID
    source_skill_version: str = SOURCE_SKILL_VERSION


# Canonical five-lens registry. Behavior assertions are the exact acceptance bullets
# from 18-detailed-development-plan Task 10 and the manifest behavior contracts.
LENS_SPECS: dict[StrategicLensType, LensSpec] = {
    StrategicLensType.PORTER_FIVE_FORCES: LensSpec(
        lens_type=StrategicLensType.PORTER_FIVE_FORCES,
        phase="research_interpretation",
        owner_worker="research",
        trigger="after_research_packets_pass_information_gate",
        prompt_ref="prompts/lenses/porter-five-forces.md",
        content_def="porterContent",
        behavior_contract=(
            "per_market_boundary_then_five_forces_with_two_evidence_items_per_force_"
            "and_regulatory_complementor_correction"
        ),
        behavior_assertions=(
            "at_least_two_markets",
            "each_market_has_exactly_five_forces",
            "each_force_has_at_least_two_resolvable_evidence",
            "industry_boundary_change_trend_regulatory_and_complementors_present",
            "scoreIsNotDecisionFormula_is_true_and_score_does_not_decide",
        ),
        required_focused=False,
        required_full=True,
    ),
    StrategicLensType.PRE_MORTEM: LensSpec(
        lens_type=StrategicLensType.PRE_MORTEM,
        phase="adversarial_stress",
        owner_worker="critic",
        trigger="after_counterparty_matrix_for_current_preference_or_strongest_candidate",
        prompt_ref="prompts/lenses/pre-mortem.md",
        content_def="preMortemContent",
        behavior_contract=(
            "failure_is_assumed_complete_with_three_perspectives_five_causes_top_three_"
            "prevention_contingency_detection_and_verdict"
        ),
        behavior_assertions=(
            "exactly_three_perspectives_internal_external_systemic_hindsight",
            "at_least_five_failure_causes",
            "exactly_three_top_risks_with_unique_complete_cause_refs",
            "each_top_risk_has_prevention_contingency_detection_indicator",
            "explicit_verdict_and_rationale",
        ),
        required_focused=False,
        required_full=True,
    ),
    StrategicLensType.COUNTERPARTY_RESPONSE_MATRIX: LensSpec(
        lens_type=StrategicLensType.COUNTERPARTY_RESPONSE_MATRIX,
        phase="adversarial_stress",
        owner_worker="critic",
        trigger="after_safety_anchor_and_before_adversarial_review",
        prompt_ref="prompts/lenses/counterparty-response-matrix.md",
        content_def="counterpartyContent",
        behavior_contract=(
            "one_layer_only_with_no_action_baseline_optimal_worst_likely_responses_"
            "publication_test_and_reflexivity"
        ),
        behavior_assertions=(
            "one_to_two_key_actors",
            "two_to_three_actions_with_exactly_one_no_action",
            "response_depth_is_one_layer",
            "matrix_covers_optimal_worst_likely_window_gap_counterresponse",
            "publication_test_and_per_action_downside_asymmetry_and_reflexivity",
        ),
        required_focused=False,
        required_full=True,
    ),
    StrategicLensType.SCENARIO_PLANNING: LensSpec(
        lens_type=StrategicLensType.SCENARIO_PLANNING,
        phase="strategic_synthesis",
        owner_worker="synthesis",
        trigger="after_critic_packet_before_final_recommendation",
        prompt_ref="prompts/lenses/scenario-planning.md",
        content_def="scenarioPlanningContent",
        behavior_contract=(
            "three_or_four_structurally_distinct_scenarios_with_baseline_two_breaks_"
            "signals_and_at_least_one_killed_strategy"
        ),
        behavior_assertions=(
            "predetermined_elements_and_at_least_two_key_uncertainties",
            "exactly_two_axes",
            "three_to_four_scenarios_exactly_one_baseline_at_least_two_structural_breaks",
            "each_scenario_has_timeline_three_stakeholder_states_and_three_to_five_signals",
            "each_strategy_tested_and_at_least_one_result_is_killed",
        ),
        required_focused=False,
        required_full=True,
    ),
    StrategicLensType.MEADOWS_LEVERAGE_POINTS: LensSpec(
        lens_type=StrategicLensType.MEADOWS_LEVERAGE_POINTS,
        phase="strategic_synthesis",
        owner_worker="synthesis",
        trigger="after_scenario_planning_before_final_action_path",
        prompt_ref="prompts/lenses/meadows-leverage-points.md",
        content_def="meadowsContent",
        behavior_contract=(
            "system_map_three_or_more_levels_high_leverage_gap_runaway_reinforcing_loop_"
            "risk_and_intervention_sequence"
        ),
        behavior_assertions=(
            "system_map_covers_boundary_goals_stocks_flows_loops_delays_actors_rules",
            "covers_at_least_three_leverage_levels",
            "at_least_one_ignored_high_leverage_gap_level_one_to_four",
            "at_least_one_runaway_reinforcing_loop",
            "non_empty_intervention_sequence_and_risk_tradeoffs",
        ),
        required_focused=False,
        required_full=True,
    ),
}


def lens_spec(lens_type: StrategicLensType) -> LensSpec:
    try:
        return LENS_SPECS[lens_type]
    except KeyError as exc:
        raise UnknownLensType(f"unknown lens type: {lens_type!r}") from exc


@dataclass(frozen=True, slots=True)
class LensRequest:
    """Stable input handed to a lens implementation.

    ``run_context`` pins tenant/run/method; the ref tuples resolve against the
    frozen run only. ``upstream_lens_outputs`` carries the validated content of
    lenses this lens depends on (e.g. counterparty before pre-mortem, scenario
    before meadows), never another workspace or another run.
    """

    lens_type: StrategicLensType
    workspace_id: str
    analysis_run_id: str
    prompt_text: str
    research_packet_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    claim_refs: tuple[str, ...] = ()
    assumption_refs: tuple[str, ...] = ()
    challenge_refs: tuple[str, ...] = ()
    option_ids: tuple[str, ...] = ()
    upstream_lens_outputs: Mapping[StrategicLensType, Mapping[str, Any]] = field(
        default_factory=dict
    )


@dataclass(frozen=True, slots=True)
class LensPromptInputs:
    """What a lens implementation assembles for the model call."""

    system: str
    user: str
    schema_content_def: str


@dataclass(frozen=True, slots=True)
class StrategicLensStageOutput:
    """The untrusted model stage output (model-writable fields only).

    Server-owned identity/provenance fields are injected later; :func:`from_payload`
    rejects any attempt by the model to set them.
    """

    lens_type: StrategicLensType
    source_skill_version: str
    phase: str
    references: Mapping[str, Sequence[str]]
    research_requests: Sequence[Mapping[str, Any]]
    content: Mapping[str, Any]

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "StrategicLensStageOutput":
        assert_no_server_owned_fields(payload)
        extra = set(payload) - ALLOWED_TOP_LEVEL_FIELDS
        if extra:
            raise ServerOwnedFieldError(tuple(sorted(extra)))
        return cls(
            lens_type=StrategicLensType(payload["lensType"]),
            source_skill_version=str(payload["sourceSkillVersion"]),
            phase=str(payload["phase"]),
            references=dict(payload["references"]),
            research_requests=list(payload["researchRequests"]),
            content=dict(payload["content"]),
        )


@dataclass(frozen=True, slots=True)
class LensBehaviorReport:
    """Result of a lens behavior check. ``ok=False`` fails the run closed."""

    lens_type: StrategicLensType
    ok: bool
    reason_codes: tuple[str, ...] = ()
    findings: tuple[str, ...] = ()


def assert_no_server_owned_fields(payload: Mapping[str, Any]) -> None:
    """Reject model output that tries to set any server-owned field."""

    present = FORBIDDEN_SERVER_OWNED_FIELDS & set(payload)
    if present:
        raise ServerOwnedFieldError(tuple(sorted(present)))


@runtime_checkable
class LensImplementation(Protocol):
    """The seam each lens specialist implements for exactly one lens type."""

    lens_type: StrategicLensType

    def build_prompt_inputs(self, request: LensRequest) -> LensPromptInputs: ...

    def validate_behavior(
        self, output: StrategicLensStageOutput
    ) -> LensBehaviorReport: ...


class LensRegistry:
    """Registry of the five lens implementations, guarding the exact set."""

    def __init__(self) -> None:
        self._impls: dict[StrategicLensType, LensImplementation] = {}

    def register(self, impl: LensImplementation) -> None:
        lens_type = impl.lens_type
        if lens_type not in LENS_SPECS:
            raise UnknownLensType(f"unknown lens type: {lens_type!r}")
        if lens_type in self._impls:
            raise ValueError(f"lens already registered: {lens_type}")
        self._impls[lens_type] = impl

    def get(self, lens_type: StrategicLensType) -> LensImplementation:
        try:
            return self._impls[lens_type]
        except KeyError as exc:
            raise UnknownLensType(f"no implementation for lens: {lens_type!r}") from exc

    def registered(self) -> frozenset[StrategicLensType]:
        return frozenset(self._impls)

    def require_full_set(self) -> None:
        """Fail closed unless all five canonical lenses are registered."""

        missing = set(FULL_REQUIRED_STRATEGIC_LENSES) - set(self._impls)
        if missing:
            raise UnknownLensType(
                f"missing lens implementations for full delivery: {sorted(missing)}"
            )
