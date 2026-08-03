"""Meadows leverage-points lens tests (lens-lane owned, no DB required).

Covers the meadows branch schema mirror, the manifest behavior contract
``system_map_three_or_more_levels_high_leverage_gap_runaway_reinforcing_loop_risk_and_intervention_sequence``,
the spherical-robot eval assertions, and a cross-check of the valid fixture
against the published method-pack JSON schema.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from app.strategic_lenses.lenses.meadows_leverage_points import (
    MeadowsLensValidationError,
    check_meadows_behavior,
    sandbox_consumption,
    validate_meadows_stage_output,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
PUBLISHED_LENS_SCHEMA = (
    REPO_ROOT
    / "method-packs"
    / "hardtech-market-direction"
    / "1.1.0"
    / "schemas"
    / "strategic-lens-output.schema.json"
)


def spherical_robot_meadows_payload() -> dict[str, Any]:
    """A valid meadows stage output for the P0 spherical-robot golden case."""

    return {
        "lensType": "meadows_leverage_points",
        "sourceSkillVersion": "1.0.0",
        "phase": "strategic_synthesis",
        "references": {
            "sourcePacketIds": ["SP-research-1"],
            "claimIds": ["CL-rescue-first"],
            "evidenceIds": ["EV-rescue-tender-2026Q2", "EV-cash-runway-model"],
            "assumptionIds": ["AS-household-presale-conversion"],
            "challengeIds": ["CH-critic-2"],
        },
        "researchRequests": [
            {
                "requestId": "RR-procurement-cycle",
                "question": "省级应急管理采购从中标到回款的实际周期分布是多少？",
                "evidenceNeed": "procurement",
                "priority": "high",
                "affectedClaimIds": ["CL-rescue-first"],
            }
        ],
        "content": {
            "systemMap": {
                "boundary": "球形机器人初创公司未来 18 个月的市场进入系统：研发资源分配、目标市场选择与现金流。",
                "statedGoal": "同时探索救援与家庭服务两个市场，保持技术领先。",
                "actualGoal": "按资源流向推断，实际目标是维持研发团队规模并延长现金跑道，市场验证被持续推迟。",
                "stocks": ["现金储备", "可部署工程师时数", "救援场景验证数据", "家庭场景品牌认知"],
                "flows": ["月度研发支出", "试点项目回款", "演示与投标带来的线索流入"],
                "reinforcingLoops": [
                    "R1：救援试点成功 -> 采购方背书 -> 更多试点邀请 -> 更多验证数据",
                    "R2：家庭市场营销投入 -> 曝光 -> 预售 -> 更多营销预算",
                ],
                "balancingLoops": ["B1：研发支出上升 -> 跑道缩短 -> 招聘冻结 -> 交付速度下降"],
                "delays": ["救援采购 9-18 个月的回款延迟", "家庭市场从预售到量产约 12 个月的交付延迟"],
                "actors": ["创始团队", "应急管理采购方", "家庭渠道分销商", "种子投资人"],
                "rulesAndIncentives": ["政府采购必须先通过资质认证", "投资人以下一轮估值叙事为核心激励"],
            },
            "levelsCovered": [3, 5, 6, 12],
            "currentInterventions": [
                {
                    "interventionId": "MI-12-price",
                    "level": 12,
                    "levelName": "parameters",
                    "strengthBand": "low",
                    "target": "家庭版预售定价",
                    "action": "把家庭版预售价下调 15% 以刺激转化",
                    "feasibility": "high",
                    "expectedEffect": "预售转化率短期提升，但不改变双市场资源争夺结构",
                    "failureSignal": "降价 4 周后预售转化率提升不足 3 个百分点",
                },
                {
                    "interventionId": "MI-6-dashboard",
                    "level": 6,
                    "levelName": "information_flows",
                    "strengthBand": "medium",
                    "target": "救援试点数据的可见性",
                    "action": "建立救援试点关键指标的月度仪表盘并同步给采购方与投资人",
                    "feasibility": "high",
                    "expectedEffect": "让资源分配讨论基于同一份救援验证数据，削弱叙事偏好",
                    "failureSignal": "仪表盘上线 6 周内没有采购方主动询价或复购意向",
                },
                {
                    "interventionId": "MI-5-gate",
                    "level": 5,
                    "levelName": "rules",
                    "strengthBand": "medium",
                    "target": "内部资源分配规则",
                    "action": "设立救援优先规则：救援线索 48 小时内必须获得工程响应",
                    "feasibility": "medium",
                    "expectedEffect": "把稀缺工程师时数从家庭线自动倾斜回救援验证",
                    "failureSignal": "规则生效后救援线索平均响应时间仍超过 5 个工作日",
                },
            ],
            "highLeverageGaps": [
                {
                    "interventionId": "MI-3-goal",
                    "level": 3,
                    "levelName": "goals",
                    "strengthBand": "high",
                    "target": "公司目标定义",
                    "action": "把目标从“双市场并行”改为“18 个月内拿下救援市场标杆客户”",
                    "feasibility": "medium",
                    "expectedEffect": "资源冲突在目标层一次性消解，R2 回路失去预算来源",
                    "failureSignal": "目标切换 8 周后救援标杆客户谈判仍无实质进展",
                    "whyAvoided": "创始团队对放弃家庭市场有沉没成本与情感阻力，投资人偏好双市场叙事",
                    "disruptionRisk": "目标收窄可能触发家庭线工程师流失与渠道伙伴解约",
                }
            ],
            "runawayPositiveLoops": [
                {
                    "loop": "R2：家庭市场营销投入 -> 曝光 -> 预售 -> 更多营销预算，在现金约束下持续挤占救援验证资源",
                    "runawaySignal": "月度营销支出连续两个月环比增长超过 20% 且救援试点数据停滞",
                    "brake": "触发后冻结营销预算增量并回拨给救援试点，直至 R1 数据恢复增长",
                }
            ],
            "interventionSequence": [
                {
                    "order": 1,
                    "interventionId": "MI-6-dashboard",
                    "purpose": "information_gain",
                    "precondition": "至少存在一个进行中的救援试点且指标可按月采集",
                    "failureSignal": "仪表盘上线 6 周内无采购方主动询问",
                },
                {
                    "order": 2,
                    "interventionId": "MI-5-gate",
                    "purpose": "trust_building",
                    "precondition": "仪表盘已运行一个完整月度周期并被创始团队采纳为例会输入",
                    "failureSignal": "救援线索响应规则连续两周被例外审批绕过",
                },
                {
                    "order": 3,
                    "interventionId": "MI-3-goal",
                    "purpose": "system_change",
                    "precondition": "仪表盘显示救援线索转化率连续两个月高于家庭预售转化率",
                    "failureSignal": "目标切换 8 周后救援标杆客户谈判无实质进展",
                },
            ],
            "riskTradeoffs": [
                "高杠杆目标收窄可逆性差：裁撤家庭线后重启成本高",
                "低杠杆降价见效快但可能拉低品牌定位并压缩毛利",
                "救援采购回款延迟使目标切换后的前 6 个月现金流风险上升",
            ],
        },
    }


def test_spherical_robot_payload_passes_schema_and_behavior() -> None:
    output = validate_meadows_stage_output(spherical_robot_meadows_payload())
    assert output.lens_type == "meadows_leverage_points"
    assert output.phase == "strategic_synthesis"
    assert check_meadows_behavior(output) == ()
    # spherical-robot eval: interventions_cover_at_least_three_levels
    levels = {item.level for item in output.content.current_interventions}
    levels |= {item.level for item in output.content.high_leverage_gaps}
    assert len(levels) >= 3
    # spherical-robot eval: level_one_to_four_gap_with_resistance_and_disruption_risk
    gap = output.content.high_leverage_gaps[0]
    assert gap.level in {1, 2, 3, 4} and gap.why_avoided and gap.disruption_risk
    # spherical-robot eval: runaway_reinforcing_loop_with_signal_and_brake
    loop = output.content.runaway_positive_loops[0]
    assert loop.runaway_signal and loop.brake
    # spherical-robot eval: intervention_sequence_with_preconditions_and_failure_signals
    assert all(step.precondition and step.failure_signal for step in output.content.intervention_sequence)


def test_valid_payload_also_passes_published_method_pack_schema() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(PUBLISHED_LENS_SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    errors = list(validator.iter_errors(spherical_robot_meadows_payload()))
    assert errors == [], [error.message for error in errors]


def test_round_trip_serialization_stays_on_wire_contract() -> None:
    payload = spherical_robot_meadows_payload()
    output = validate_meadows_stage_output(payload)
    assert output.model_dump(by_alias=True, mode="json") == payload


def test_server_identity_fields_are_rejected_before_parsing() -> None:
    payload = spherical_robot_meadows_payload()
    payload["workspaceId"] = "ws-1"
    payload["contentHash"] = "sha256:abc"
    with pytest.raises(MeadowsLensValidationError) as excinfo:
        validate_meadows_stage_output(payload)
    codes = {violation.code for violation in excinfo.value.violations}
    assert codes == {
        "server_identity_self_reported:contentHash",
        "server_identity_self_reported:workspaceId",
    }


def test_wrong_lens_type_and_phase_are_schema_violations() -> None:
    payload = spherical_robot_meadows_payload()
    payload["lensType"] = "scenario_planning"
    payload["phase"] = "adversarial_stress"
    with pytest.raises(MeadowsLensValidationError) as excinfo:
        validate_meadows_stage_output(payload)
    codes = {violation.code for violation in excinfo.value.violations}
    assert "schema:lensType" in codes
    assert "schema:phase" in codes


def test_missing_system_map_section_is_rejected() -> None:
    payload = spherical_robot_meadows_payload()
    del payload["content"]["systemMap"]["balancingLoops"]
    with pytest.raises(MeadowsLensValidationError) as excinfo:
        validate_meadows_stage_output(payload)
    assert any(
        violation.code.startswith("schema:content.systemMap.balancingLoops")
        for violation in excinfo.value.violations
    )


def test_level_name_or_band_mismatch_is_rejected() -> None:
    payload = spherical_robot_meadows_payload()
    payload["content"]["currentInterventions"][0]["levelName"] = "goals"
    with pytest.raises(MeadowsLensValidationError):
        validate_meadows_stage_output(payload)
    payload = spherical_robot_meadows_payload()
    payload["content"]["currentInterventions"][1]["strengthBand"] = "high"
    with pytest.raises(MeadowsLensValidationError):
        validate_meadows_stage_output(payload)


def test_levels_covered_must_match_declared_interventions() -> None:
    payload = spherical_robot_meadows_payload()
    payload["content"]["levelsCovered"] = [3, 5, 6, 9]
    with pytest.raises(MeadowsLensValidationError) as excinfo:
        validate_meadows_stage_output(payload)
    codes = {violation.code for violation in excinfo.value.violations}
    assert "levels_covered_mismatch" in codes


def test_fewer_than_three_distinct_levels_is_rejected() -> None:
    payload = spherical_robot_meadows_payload()
    # Collapse the low/medium interventions onto one level so only {3, 6} remain.
    for item in payload["content"]["currentInterventions"]:
        item["level"] = 6
        item["levelName"] = "information_flows"
        item["strengthBand"] = "medium"
    payload["content"]["currentInterventions"][1]["interventionId"] = "MI-6-b"
    payload["content"]["currentInterventions"][2]["interventionId"] = "MI-6-c"
    payload["content"]["levelsCovered"] = [3, 6, 12]
    with pytest.raises(MeadowsLensValidationError) as excinfo:
        validate_meadows_stage_output(payload)
    codes = {violation.code for violation in excinfo.value.violations}
    assert "interventions_cover_fewer_than_three_levels" in codes
    assert "levels_covered_mismatch" in codes


def test_duplicate_intervention_ids_are_rejected() -> None:
    payload = spherical_robot_meadows_payload()
    payload["content"]["highLeverageGaps"][0]["interventionId"] = "MI-6-dashboard"
    with pytest.raises(MeadowsLensValidationError) as excinfo:
        validate_meadows_stage_output(payload)
    codes = {violation.code for violation in excinfo.value.violations}
    assert "duplicate_intervention_id" in codes


def test_sequence_must_reference_declared_interventions() -> None:
    payload = spherical_robot_meadows_payload()
    payload["content"]["interventionSequence"][2]["interventionId"] = "MI-unknown"
    with pytest.raises(MeadowsLensValidationError) as excinfo:
        validate_meadows_stage_output(payload)
    codes = {violation.code for violation in excinfo.value.violations}
    assert "sequence_references_unknown_intervention" in codes


def test_sequence_orders_must_be_dense_and_ascending() -> None:
    payload = spherical_robot_meadows_payload()
    payload["content"]["interventionSequence"][1]["order"] = 5
    with pytest.raises(MeadowsLensValidationError) as excinfo:
        validate_meadows_stage_output(payload)
    codes = {violation.code for violation in excinfo.value.violations}
    assert "sequence_orders_not_dense_ascending" in codes


def test_transcend_paradigms_must_be_paired_with_a_mechanism() -> None:
    payload = spherical_robot_meadows_payload()
    gap = copy.deepcopy(payload["content"]["highLeverageGaps"][0])
    gap.update(
        {
            "interventionId": "MI-1-transcend",
            "level": 1,
            "levelName": "transcend_paradigms",
            "action": "把“选市场”重构为“为救援体系提供可靠性能力”的身份假设实验",
            "whyAvoided": "范式层动作难以向投资人解释，团队担心失焦",
            "disruptionRisk": "身份重构失败会同时动摇两个市场的既有叙事",
        }
    )
    payload["content"]["highLeverageGaps"].append(gap)
    payload["content"]["levelsCovered"] = [1, 3, 5, 6, 12]
    payload["content"]["interventionSequence"] = [
        {
            "order": 1,
            "interventionId": "MI-1-transcend",
            "purpose": "system_change",
            "precondition": "创始团队完成一次完整的范式假设盘点",
            "failureSignal": "盘点后 4 周内没有产生任何可执行动作",
        },
        {
            "order": 2,
            "interventionId": "MI-1-transcend",
            "purpose": "risk_control",
            "precondition": "第一轮范式实验结束并留存记录",
            "failureSignal": "实验记录无法回答任何一个采购方问题",
        },
    ]
    with pytest.raises(MeadowsLensValidationError) as excinfo:
        validate_meadows_stage_output(payload)
    codes = {violation.code for violation in excinfo.value.violations}
    assert "transcend_paradigms_unpaired" in codes


def test_empty_evidence_and_assumption_references_are_rejected() -> None:
    payload = spherical_robot_meadows_payload()
    payload["references"]["evidenceIds"] = []
    payload["references"]["assumptionIds"] = []
    with pytest.raises(MeadowsLensValidationError) as excinfo:
        validate_meadows_stage_output(payload)
    codes = {violation.code for violation in excinfo.value.violations}
    assert "unanchored_evidence_and_assumptions" in codes


def test_sandbox_consumption_exposes_levers_and_ordered_sequence() -> None:
    output = validate_meadows_stage_output(spherical_robot_meadows_payload())
    consumption = sandbox_consumption(output)
    kinds = {(item.intervention_id, item.kind) for item in consumption.lever_candidates}
    assert ("MI-3-goal", "high_leverage_gap") in kinds
    assert ("MI-6-dashboard", "current") in kinds
    assert len(consumption.lever_candidates) == 4
    assert [step.order for step in consumption.intervention_sequence] == [1, 2, 3]
    assert consumption.intervention_sequence[-1].intervention_id == "MI-3-goal"
    assert consumption.intervention_sequence[-1].purpose == "system_change"

def test_shipped_content_example_passes_meadows_gate() -> None:
    """B3: the prompt-carried meadows example must itself satisfy the gate.

    Guards against a gate-passing example that the gate itself rejects (the
    regression class behind the flash run 979c98f7 meadows failure). The
    example is loaded from the shared seam so a broken example fails here
    instead of in a live full run.
    """
    from app.agents.lenses import lens_content_example

    example = json.loads(lens_content_example("meadowsContent"))
    payload = spherical_robot_meadows_payload()
    payload["content"] = example
    output = validate_meadows_stage_output(payload)
    violations = check_meadows_behavior(output)
    assert not violations, [v.message for v in violations]
