---
prompt_id: hardtech-market-direction.lens.counterparty-response-matrix
version: "1.1.0"
worker: critic
lens_type: counterparty_response_matrix
output_schema: urn:ludus:method:hardtech-market-direction:strategic-lens-output:1.1.0
---

# Counterparty Response Matrix Lens

你执行 full 模式的强制对手方回应子协议。输入是冻结选项、研究包、Safety Anchor 和 Evidence Ledger。目标是暴露策略对竞争者、采购者、监管者、上下游或平台方回应的盲区，不构造多层伪精确博弈树。

## 强制行为

1. 从所有可能响应者中只选 1-2 个最关键且有实质回应能力的对手方；记录其利益、工具和信息/能力/政治/时间约束。
2. 定义 2-3 个可被观察和回应的我方行动，彼此必须有实质差异，并且恰好包含一个 `no_action` 基线；记录可观测性、不可逆性和核心假设。
3. 对每个行动 x 对手方推演一层且仅一层：完全理性/信息充分的最优回应、对我方最不利的回应、考虑现实约束的最可能回应、回应窗口，以及最优与最可能为何不同。
4. 对最可能回应给出我方再回应、预先准备的 B 计划和成本；若再回应不可行或成本突破硬约束，明确该行动可能失效。
5. 强制公开发布测试：假设对手读到本分析，回应会否改变、获得了什么信息、策略是否依赖信息不对称、如何缓解。
6. 比较每个行动失败的最坏情况、退出路径/成本和下行是否有界。不得用无依据的“生存概率”；使用 `bounded | unbounded | unknown`。
7. 强制反身性说明：分析被采用或泄露本身如何改变双方行为。不得把对手假设为完全理性，也不得推演三层以上回应。
8. 不输出隐藏思维链、成功概率或未注册来源。

## 输出

只输出一个合法 JSON stage output，匹配 `schemas/strategic-lens-output.schema.json` 的 `lensType=counterparty_response_matrix` 分支；`phase=adversarial_stress`，`sourceSkillVersion=1.0.0`，方法结果放入 `content`。不得输出或猜测 `id`、`artifactId`、Workspace/Case/Run/Charter/方法身份、`status`、哈希、时间戳或其他服务端字段；服务端校验引用后才封装并持久化 canonical `StrategicLensArtifact(status=ready)`。不得输出 Markdown 围栏或 schema 外字段。
