# Changelog

## 1.1.0 - 2026-07-19

- Added deterministic Cynefin gate before formal execution.
- Added SourceSpan provenance, structured JudgmentSet, DissentRecord and DraftRecommendation contracts.
- Added DeepAnalysisResult and exact V1-V9 Validator Aggregate contracts.
- Repaired DeepAnalysisResult to the CCR-20260721-003 ID/hash-only envelope; canonical Judgment/Dissent/Recommendation objects are no longer embedded.
- Repaired Recommendation and DraftRecommendation to the option/abstain discriminated union; fatal paths no longer require a fake option ID.
- Aligned active diagnostic/quality-gate metadata and all prompt/schema references on method version 1.1.0; retained source Skill versions and document schema versions as independent historical metadata.
- Formalized RunManifest freeze and non-chat Agent Engine I/O.
- Clarified that the method package only emits analysis responsibility artifacts; human signoff and immutable DecisionRecord remain platform-owned.


## 1.0.0 - 2026-07-13

- 首次编译 `hardtech-market-direction` 方法包。
- 将 v6.12.7 研究体系收敛为 Ludus 的 Research、Critic、Synthesis、Validation 四类正式 Worker。
- 将 Safety Anchor 与魔鬼审查并入 Critic 强制子步骤，将参谋长式行动建议并入 Synthesis。
- 固化 quick/focused/full 授权边界、信息质检、正式分析门、full 交付资格和沙盘映射。
- 新增球形机器人 exact 路由、关键假设、反方、证据质量、8/10 沙盘与采购周期翻转 eval。
- 移除旧技能的聊天平台、临时文件落盘、LaTeX/PPTX 编译和任意多 Agent 编排协议。
- 补齐条件 schema 的局部类型与属性声明，确保 Draft 2020-12 strict mode 安装校验通过。
- 新增 full 强制 Porter、Counterparty、Pre-mortem、Scenario、Meadows 五项战略 lens 及逐项 `LQ-*` 行为门；focused 明确不创建 lens 产物。
- 新增严格判别的 `StrategicLensOutput` stage schema。模型只输出 `lensType/references/content` 等方法结果，服务端验证引用后注入冻结身份、provenance、哈希与 `ready` 状态并持久化 immutable canonical `StrategicLensArtifact`。
- 将 `StructuredReport` 的 lens 合同收敛为恰好五个唯一 `lensArtifactIds`，并阻断缺失、重复、跨 Run/Charter/方法快照、未 ready 或未被报告/沙盘实质消费的 artifact。
- 移除正式报告和沙盘中硬编码的 optimistic/base/pessimistic 三档；改由 `scenario_planning` 的 3-4 个结构化业务情景生成 `scenarioCandidates`，要求一个 baseline、至少两个 structural break、至少一个策略被推翻，并经用户审阅后创建 ScenarioVersion。
- full 预算预留五类 lens 各至多两次调用：`max_lens_calls=10`、`max_lens_attempts_per_type=2`；首次全部通过时仍只使用五次。

### 定稿补充 - 2026-07-14

- 固化六条方法不变量：决策视角、不可补偿硬门、规模改变性质、证据标注与使用一致、反方必须改变产物、决策质量与结果质量分离。
- 将 BrainCo 时间错配教训编译为 `AG-15` 时间/样本/口径对齐和 `AG-16` 证据标注-使用一致性阻断门。
- 将 BCI 三线平台的资源阶段翻转编译为 `AG-17` 资源规模反事实，并要求 Research/Critic/Synthesis 显式处理规模敏感性。
- 新增 `AG-18` 复盘可判别性，要求领先指标、退出条件和复盘日期支持后续区分决策、执行、外部冲击与结果。
- 新增去标识化 BCI seed/angel 双轨 parity eval，以及 partial/unsupported 负向路由 eval；首版 eval 从 1 个扩展为 5 个。
- 修复 `simulation-seeds` 与 `strategic-lens-output` 中 `contains` 子 schema 缺少显式对象类型的问题，使全部 Draft 2020-12 schema 可在 Ajv strict 模式编译。
- `ways` 仍保持 `release_candidate/unpublished`；只有后续安装器校验、规范化、计算哈希并生成 `method-packs` 后才能成为运行时 `published` 包。
- 新增 `CAPABILITY-MAP.md`，对 `探讨/skills/research` 全部 31 个 Skill 给出版本、处置状态、沉淀目标、运行边界、验收方式和后续方法包候选；明确“知识沉淀”不等于“全部运行时加载”。
- manifest 新增 documentation 引用，安装前可以确定性检查 README、来源审计、能力地图、变更日志和 eval 指南均存在。
