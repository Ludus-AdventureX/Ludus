# 示例任务与预期输出

> 提交清单要求：至少 3 个示例任务，且已完成测试。以下任务均通过 A2A `message/send`
> 以纯文本提交；"预期输出"为报告结构与内容形态的演示样例（实际数值以运行时
> PandaAI 数据与模型推理为准），**所有内容均为技术演示，不构成投资建议**。

## 调用方式（以示例 1 为例）

```bash
curl -X POST https://<你的域名>/a2a -H "Content-Type: application/json" -d '{
  "jsonrpc": "2.0", "id": "demo-1", "method": "message/send",
  "params": {"message": {"kind": "message", "role": "user", "messageId": "m-demo-1",
    "parts": [{"kind": "text", "text": "分析宁德时代（300750.SZ）未来两年的竞争格局与下行风险，判断应该增持还是回避。"}]}}}'
```

---

## 示例 1：个股竞争格局与下行风险

**输入**

> 分析宁德时代（300750.SZ）未来两年的竞争格局与下行风险，判断应该增持还是回避。

**预期过程（TaskStatusUpdate 流）**

```
[Planner]    解析任务，拟定研究计划
[Data Agent] 获取 PandaAI 数据（3 项请求：quote/factor/financial × 300750.SZ）
[Lens] Porter Five Forces — 竞争格局：分析中 → ok
[Lens] Counterparty Response Matrix — 对手盘反应：分析中 → ok
[Lens] Pre-Mortem — 失败预演：分析中 → ok
[Lens] Scenario Planning — 情景推演：分析中 → ok
[Lens] Meadows Leverage Points — 系统杠杆点：分析中 → ok
[Report Agent] 汇总五 Lens 结论，生成投研报告
```

**预期输出（artifact 报告节选）**

````markdown
# 五 Lens 投研分析报告

**任务**：分析宁德时代（300750.SZ）未来两年的竞争格局与下行风险，判断应该增持还是回避。
**决策问题**：未来 24 个月内，相对基准应当增持还是回避宁德时代？
**时间窗**：24 months
**候选选项**：option-overweight、option-avoid

## 执行摘要
五个透镜全部通过行为门控。竞争格局侧（Porter）显示动力电池主业进入壁垒仍高但
买方议价力上升；对手盘侧（Counterparty）提示二线厂商对降价动作存在跟进能力；
失败预演（Pre-Mortem）识别出的前三大风险集中在价格战、海外政策与技术路线切换；
情景推演中"激烈价格战 × 海外受阻"情景下增持策略被判 killed；系统分析（Meadows）
认为产能纪律是当前最高杠杆干预点。

**倾向性结论**：倾向 option-overweight，前提条件是季度毛利率与海外出货占比
两项检测指标不触发 Pre-Mortem 预警线；任一触发则转为 option-avoid 复审。

**关键风险**：
- 行业价格战强度超出当前证据所示区间
- 海外市场准入政策收紧
- 固态电池等技术路线切换快于预期

## Porter Five Forces — 竞争格局
```json
{
  "content": {
    "marketAnalyses": [
      {
        "optionId": "option-overweight",
        "industryBoundary": {"coreValue": "动力+储能电池平台", "boundaryRisk": "过宽的'新能源'框定会掩盖储能与动力买方结构差异", ...},
        "forces": [
          {"forceId": "rivalry", "threatScore": 4, "evidenceIds": ["ev-panda-quote-0003", "ev-panda-factor-0007"], "reasoning": "...", "directionOfChange": "increasing"},
          {"forceId": "buyer_power", "threatScore": 4, ...},
          {"forceId": "supplier_power", "threatScore": 2, ...},
          {"forceId": "new_entrants", "threatScore": 2, ...},
          {"forceId": "substitutes", "threatScore": 3, ...}
        ],
        "regulatoryAssessment": "海外补贴与本地化率规则单独评估，不并入五力平均",
        ...
      },
      { "optionId": "option-avoid", ... }
    ],
    "scoreIsNotDecisionFormula": true
  }
}
```

## Pre-Mortem — 失败预演
```json
{
  "content": {
    "perspectives": ["internal", "external", "systemic_hindsight"],
    "failureCauses": [ /* ≥5 条，含 causeId 与视角归属 */ ],
    "topRisks": [
      {"risk": "价格战失控压垮单位盈利", "prevention": "...", "contingency": "...", "detectionIndicator": "季度毛利率连续两季低于预警线"},
      {"risk": "海外政策使高毛利市场收缩", "prevention": "...", "contingency": "...", "detectionIndicator": "海外出货占比环比连降两季"},
      {"risk": "技术路线切换导致现有产能贬值", "prevention": "...", "contingency": "...", "detectionIndicator": "竞品固态电池装车公告频次"}
    ],
    "verdict": "conditional_go",
    "rationale": "失败路径可检测、可对冲，但依赖两项前置监控指标"
  }
}
```

（Counterparty / Scenario / Meadows 章节结构同理，略）

## 数据来源
共引用 27 条证据（live: 27, fixture: 0），来自 PandaAI 数据 Skills。

## 风险提示与免责声明
- 本报告由 AI 多智能体系统自动生成，仅用于研究与技术演示，**不构成任何投资建议**、
荐股或收益承诺。
- 分析基于任务提交时刻可获得的数据快照与模型推断，数据可能存在延迟、缺失或错误；
历史规律不代表未来表现。
- （下略，每份报告固定附加）
````

---

## 示例 2：指数情景推演

**输入**

> 对中证新能源指数（H30592）做未来 12 个月的情景推演，识别关键不确定性并给出可监控的早期信号。

**预期过程**：同示例 1，Data Agent 改为调用 `get_index_daily` + `get_trade_cal`；
Planner 将任务框定为 `option-add-exposure`（加配）与 `option-wait`（观望）两个互斥选项。

**预期输出（Scenario Lens 章节节选）**

```json
{
  "content": {
    "focusQuestion": "未来 12 个月是否应提高新能源指数敞口？",
    "keyUncertainties": [
      {"uncertaintyId": "unc-policy", "factor": "产业政策与补贴节奏", "impact": "high", "uncertainty": "high", "evidenceIds": ["ev-panda-index-0002"]},
      {"uncertaintyId": "unc-capacity", "factor": "行业产能出清速度", "impact": "high", "uncertainty": "high", "evidenceIds": ["ev-panda-index-0005"]}
    ],
    "axes": [ /* 恰好两条：政策松/紧 × 出清快/慢 */ ],
    "scenarios": [
      {"scenarioId": "sc-base", "kind": "baseline", "earlySignals": [ /* 3-5 个可监控信号 */ ], ...},
      {"scenarioId": "sc-squeeze", "kind": "structural_break", ...},
      {"scenarioId": "sc-boom", "kind": "structural_break", ...}
    ],
    "strategyTests": [
      {"scenarioId": "sc-squeeze", "optionId": "option-add-exposure", "performance": "killed",
       "failureReason": "出清迟滞叠加政策退坡，指数盈利与估值双杀", "triggerSignalIds": ["sig-sq-1", "sig-sq-2"]},
      ...
    ],
    "strategyKilledInAtLeastOneScenario": true,
    "monitoringActions": ["跟踪月度行业产能利用率数据", "跟踪政策文件发布节奏"]
  }
}
```

行为门控保证：恰好两条轴、3-4 个情景且恰一个 baseline、每个情景 3-5 个早期信号、
至少一个策略在某情景下被判 `killed`——这些是硬性校验，不满足即 degraded。

---

## 示例 3：持仓组合失败预演

**输入**

> 我重仓白酒板块（贵州茅台 600519.SH 为主），请做一次失败预演：假设 18 个月后这个持仓决策彻底失败了，最可能的原因是什么？给出前三大风险的预防、应急与检测指标。

**预期过程**：Planner 框定为 `option-keep-position`（维持重仓）与
`option-reduce`（减仓分散）；Data Agent 调用 `get_stock_daily` + `get_fina_reports`
（600519.SH）；Counterparty Lens 先输出渠道与竞品的反应矩阵，作为上游内容注入
Pre-Mortem。

**预期输出（最终 completed 消息 + 报告要点）**

```
completed: 分析完成：5/5 个 Lens 通过行为门控，总耗时 298 秒。完整报告见任务产物。
```

报告中 Pre-Mortem 章节将包含（行为门控强制）：

- 恰好三个视角：internal（持仓集中度与心理锚定）、external（消费习惯与渠道变革）、
  systemic hindsight（"事后看显而易见"的宏观信号）
- ≥5 个失败原因，每个可追溯至证据或明确标注为假设
- 恰好 3 个 top risks，每个含 prevention / contingency / detectionIndicator
  （如"批价连续 N 周低于阈值"这类可操作检测指标）
- 显式 verdict 与 rationale

---

## 降级行为示例（可解释性验收）

当某个 Lens 输出两次均未通过行为门控时，报告对应章节显示：

```
> ⚠️ 该 Lens 输出未通过行为门控校验（degraded），未纳入下游分析。
> - at_least_two_markets @ content.marketAnalyses: 市场分析少于两个候选选项
```

任务不中断，其余 Lens 正常完成，completed 消息如实报告 `4/5 个 Lens 通过行为门控`
——评审可据此验证"门控是真实的，不是提示词装饰"。

## 无数据兜底示例

PandaAI 凭证未配置或当日无可用数据时，报告"数据来源"章节显示：

```
本次任务未获取到外部市场数据，分析基于任务描述与模型推断（已降低置信度）。
```

Agent 不会伪造数据引用；证据条目的 `origin` 字段（live/fixture/context）在报告中
如实区分。
