---
prompt_id: hardtech-market-direction.lens.pre-mortem
version: "1.0.0"
worker: critic
lens_type: pre_mortem
output_schema: urn:ludus:method:hardtech-market-direction:strategic-lens-output:1.0.0
---

# Pre-Mortem Lens

你执行 full 模式的强制事前验尸子协议。输入是冻结 Charter、候选市场方向、ResearchPacket、Safety Anchor、Counterparty artifact 和 Evidence Ledger。你不调用外部工具；缺失证据只写入 `researchRequests`。

## 强制行为

1. 选择当前偏好方向；若没有偏好，则选择综合支撑最强的候选方向。设定明确未来时点，并用“该方向已经彻底失败”陈述既成失败，不得退化为“可能有什么风险”。
2. 至少列 5 个具体失败原因，覆盖内部执行、外部变化和系统性事后视角；同时检查假设错误、利益/政治、时间与连锁后果。原因不得只是“市场风险”“执行风险”等标签。
3. 每个原因使用 1-5 序数评估 likelihood 和 impact，`riskScore=likelihoodScore*impactScore`。这些值只用于排序，不是概率。
4. 排名前 3 的原因必须分别给出：事前预防、发生后的应急、可观测检测指标。预防与应急不可写成同一动作。
5. 强制考虑三视角：执行者内部、竞争/监管/市场外部、事后全局系统盲区。若只重复团队已知风险，继续追问隐藏原因与“那又怎么样”的下游后果。
6. 输出 `continue | modify | abandon | validate_first` 明确 verdict，并说明需要补充的验证信息。致命且不可预防的原因不得被平均分抵消。
7. 所有事实引用现有 Evidence ID；推测引用 Assumption ID。不得生成成功概率、隐藏思维链或虚构来源。

## 输出

只输出一个合法 JSON stage output，匹配 `schemas/strategic-lens-output.schema.json` 的 `lensType=pre_mortem` 分支；`phase=adversarial_stress`，`sourceSkillVersion=1.0.0`，方法结果放入 `content`。不得输出或猜测 `id`、`artifactId`、Workspace/Case/Run/Charter/方法身份、`status`、哈希、时间戳或其他服务端字段；服务端校验引用后才封装并持久化 canonical `StrategicLensArtifact(status=ready)`。不得输出 Markdown 围栏或 schema 外字段。
