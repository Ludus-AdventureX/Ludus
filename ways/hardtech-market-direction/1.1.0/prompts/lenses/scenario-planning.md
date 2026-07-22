---
prompt_id: hardtech-market-direction.lens.scenario-planning
version: "1.1.0"
worker: synthesis
lens_type: scenario_planning
output_schema: urn:ludus:method:hardtech-market-direction:strategic-lens-output:1.1.0
---

# Scenario Planning Lens

你执行 full 模式的强制情景规划子协议。输入是冻结 Charter、研究/批判产物、候选选项、Porter artifact 与当前策略基线。目标是准备多种合理未来，不是预测唯一未来或给情景分配概率。

## 强制行为

1. 明确聚焦决策、时间跨度和关键决策者。短于三年的案例仍以 Charter 决策/复盘窗口为最低跨度，并说明为何需要情景韧性测试。
2. 分开记录预决因素和关键不确定性；按影响与不确定性识别两个 `high impact x high uncertainty` 情景轴。
3. 构建 3-4 个内部自洽、结构假设不同的情景：恰好一个延续性基准情景，至少两个跳出现有思维的结构突变情景。禁止把同一逻辑写成乐观/悲观数值变体。
4. 每个情景必须包含核心逻辑、至少两个转折点、行业/政府/客户或竞争者等至少三个利益相关方状态，以及 3-5 个定性/定量/结构早期信号。
5. 把候选市场策略逐一放入情景运行；至少一个策略必须在至少一个情景中被判定 `killed`，否则继续寻找未覆盖的结构性假设。
6. 为高风险/失效策略写明调整、备选和触发信号；输出立即开始的监控动作和不可约未知项。情景需可在复盘日更新，不是一次性故事。
7. 所有事实引用 Evidence ID，推测引用 Assumption ID。不得写情景概率、成功概率、隐藏思维链或单一确定未来。

## 输出

只输出一个合法 JSON stage output，匹配 `schemas/strategic-lens-output.schema.json` 的 `lensType=scenario_planning` 分支；`phase=strategic_synthesis`，`sourceSkillVersion=1.0.0`，方法结果放入 `content`。不得输出或猜测 `id`、`artifactId`、Workspace/Case/Run/Charter/方法身份、`status`、哈希、时间戳或其他服务端字段；服务端校验引用后才封装并持久化 canonical `StrategicLensArtifact(status=ready)`。不得输出 Markdown 围栏或 schema 外字段。
