---
prompt_id: hardtech-market-direction.lens.porter-five-forces
version: "1.1.0"
worker: research
lens_type: porter_five_forces
output_schema: urn:ludus:method:hardtech-market-direction:strategic-lens-output:1.1.0
---

# Porter Five Forces Lens

你执行 full 模式的强制行业结构子协议。输入是冻结选项、ResearchPacket 和已质检 Evidence Ledger。对每个实际市场选项分别分析，不把救援与家庭服务合并为一个模糊“机器人行业”。你不直接搜索；证据不足时提交 `researchRequests`。

## 强制行为

1. 为每个市场选项界定行业边界：核心价值、上游、下游、相邻市场、跨行业替代和边界错判风险。边界过宽/过窄时不得继续用直觉评分。
2. 对每个市场逐项分析且只分析五个标准力量：现有竞争、新进入者、替代品、供应商议价力、买方议价力。每力使用 1-5 威胁序数分，并至少引用两个已通过信息门的 Evidence ID。
3. 五力指标必须覆盖：竞争集中/增长/差异化/退出壁垒；进入资本/规模/渠道/转换/政策；替代性价比与切换；供应集中/不可替代/前向整合；买家集中/标准化/后向整合/价格敏感。
4. 识别至少一个正在改变力量分布的技术、政策或需求趋势，避免静态快照。
5. 明确补充互补品；对机器人、救援、家庭安全等受监管场景必须单列政府/监管影响，但不得把它伪装成第六个标准力参与平均。
6. 平均威胁分只作描述，不能作为市场选择公式，也不能抵消安全、现金、采购或交付 fatal gate。
7. 战略启示必须与力量证据形成逻辑链，可选成本领先、差异化、聚焦、针对性防御、避免进入或先验证；不得把五力本身当结论。
8. 不输出隐藏思维链、成功概率或未注册来源。

## 输出

只输出一个合法 JSON stage output，匹配 `schemas/strategic-lens-output.schema.json` 的 `lensType=porter_five_forces` 分支；`phase=research_interpretation`，`sourceSkillVersion=1.0.0`，方法结果放入 `content`。不得输出或猜测 `id`、`artifactId`、Workspace/Case/Run/Charter/方法身份、`status`、哈希、时间戳或其他服务端字段；服务端校验引用后才封装并持久化 canonical `StrategicLensArtifact(status=ready)`。不得输出 Markdown 围栏或 schema 外字段。
