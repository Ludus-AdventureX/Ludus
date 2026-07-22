# Hardtech Market Direction 1.0.0

本方法用于资源受限的硬科技团队，在两个或更多高切换成本市场/场景之间作出可复盘的优先级选择。它首先检查需求、付费与采购、技术成熟度、交付、安全责任、现金窗口和供应链是否构成不可补偿的硬门；只有通过硬门的选项才进入战略比较。

本目录是 `hardtech-market-direction@1.0.0` 的定稿源版本。`release_candidate` 表示内容已经完成方法评审、等待安装器校验和内容哈希发布；它不表示运行时可直接读取 `ways`。

阅读入口：本文说明方法主合同；`CAPABILITY-MAP.md` 记录 `探讨/skills/research` 全部 31 个 Skill 的处置、目标位置与运行边界；`SOURCES.md` 记录实际编译来源和版本审计；`evals/README.md` 说明行为评测规格。

## 方法命题与不变量

本方法不以“找到最大市场”为目标，而以“在当前资源、期限和责任边界下，找到最值得优先验证且失败有界的市场路径”为目标。所有 Worker、lens、质量门和 eval 必须服从以下不变量：

1. **决策视角先于框架**：事实不会因创始人、投资人、客户或监管者的视角而改变；成功标准、风险承担和策略判断会改变。Charter 必须冻结最终决策人、目标和硬约束。
2. **致命短板不可补偿**：需求、采购、交付、安全、现金或供应链的 `fatal_fail` 不能被 TAM、增长率、品牌价值或平均分救回。
3. **规模会改变策略性质**：团队人数、现金窗口、融资阶段、采购周期和交付能力变化时，必须重新计算可行路径；不得把种子期结论线性外推到天使期，也不得把资金增加自动解释为应同时扩张多条产品线。
4. **证据状态必须约束使用方式**：`conditional` 证据只能支撑带条件判断，`lead_only/rejected` 不能支撑核心结论；时间、样本、地域、口径或分母错配必须降级或阻断，不得只在附注中免责后继续当作可靠事实使用。
5. **反方必须改变产物**：Safety Anchor、Counterparty、Pre-mortem 和魔鬼审查的重要发现必须改变建议、条件、阈值、退出标准、质量画像或沙盘；只增加“风险提示”附录不算消费。
6. **决策质量与结果质量分离**：建议必须保存当时证据、脆弱假设、领先指标、复盘日期和翻转条件，使后续 Review 能区分坏结果、坏执行、外部冲击和坏决策过程。

## 适用问题

- 决策主体是机器人、设备、深科技或具有显著研发和交付约束的产品。
- 需要在至少两个市场方向、细分场景或产品市场路径之间选择。
- 错选会造成明显的研发分叉、认证/量产投入、渠道锁定、现金消耗或机会成本。
- 已确认决策期限、目标、硬约束、选项、允许材料和关键未知项。

本方法不替代工程安全认证、法律意见、财务审计或临床/监管审批；不用于单一选项可行性证明、纯营销定位、短期投放优化、证券投资或没有研发/交付约束的通用市场研究。

## 执行顺序

1. **诊断与路由**：完成 5W1H、需求真实性、采购、TRL/交付、安全责任、现金、供应链、竞争替代和可逆性问题。路由必须先按 manifest 做确定性筛选。
2. **冻结 Charter**：冻结 Case/Dossier 快照、期限、目标、硬约束、选项、材料、未知项、深度、预算、方法版本和哈希。
3. **Research**：按因素检索；外部材料先进入信息质检，再以 Evidence ID 写入研究包。先检查已有证据，再补关键缺口。
4. **Full 战略 lens**：Research 产出 Porter stage output；Critic 产出 Counterparty 与 Pre-mortem；Synthesis 产出 Scenario 与 Meadows。五个 lens 在 full 中全部强制执行，focused 不执行。
5. **Critic**：强制执行 Safety Anchor 与魔鬼审查，找共享盲区、伪收敛、最强反方、失败模式、利益相关方阻力和致命缺陷，并消费 Counterparty/Pre-mortem 发现。
6. **Synthesis**：先做每个选项的不可补偿业务硬门，再比较需求强度、采购可达性、技术/交付、单位经济、现金匹配、供应链、竞争替代和可逆性。建议必须带条件、阈值、退出条件、领先指标与复盘日期，并消费全部五项 lens。
7. **Validation**：检查证据、引用、冲突、因果、反方响应、建议条件、五项 lens 行为合同和沙盘依据。重要问题必须触发修复、降级或阻断。
8. **Full 沙盘种子**：仅 full 且质量门通过后生成至少 8 个节点、10 条边的草稿图；图是可解释的干预模型，不是预测器。

## 正式建议的最低结构

正式建议不是单一选项名称。focused/full 至少交付：

- 当前优先选项与可保留的替代选项；若没有选项通过全部硬门，明确建议“先验证/继续研究”，不得强行二选一。
- 建议成立所依赖的条件、可观测阈值和证据状态。
- 每个脆弱假设的验证动作、责任人、最晚验证时间和方向翻转影响。
- 退出条件、方向切换成本和仍可保留的选择权。
- 领先指标、首个最小楔子、下一步行动和复盘日期。
- 六维质量画像及最脆弱维度，不给出项目成功率或结论正确概率。

## 三档边界

- `quick` 不执行本正式方法、不创建 Charter/Run，只使用已确认档案生成非正式结构化判断。
- `focused` 需要 `exact` 路由和 confirmed Charter，研究 1-2 个最关键方向，运行四类 Worker，产出 `FocusedResearchResult`；禁止 PDF、`StructuredReport` 和正式沙盘。
- `full` 需要 `exact` 路由和 confirmed Charter，覆盖四个研究轨道，运行四类 Worker；只有质量门通过后才能产出 `StructuredReport`、HTML/PDF 和正式沙盘。

## Strategic lens 持久化边界

- Lens 模型调用只返回严格匹配 `schemas/strategic-lens-output.schema.json` 的未信任 stage output：`lensType`、`sourceSkillVersion`、`phase`、`references`、`researchRequests` 和 `content`。模型不得自报 artifact、Workspace、Case、Run、Charter、方法身份、状态、哈希或时间戳。
- 服务端先验证 schema 与 `LQ-*` 行为合同，再对冻结 Run 解析全部引用；随后注入 canonical 身份/provenance、producer role、`status=ready` 与内容哈希，持久化不可变 `StrategicLensArtifact`。
- Full 必须为五种 canonical lensType 各持久化一项 `ready` artifact。`StructuredReport.lensArtifactIds` 只保存五个唯一服务端 ID，不内嵌 lens content；缺失、重复、跨 Workspace/Case/Run/Charter/方法快照或未消费重要发现都会阻断 ready、HTML/PDF 和正式沙盘。
- Focused 不生成 stage output，也不创建 `StrategicLensArtifact`。
- 正式沙盘情景来自 ready `scenario_planning` artifact 的 3-4 个结构化 frame：恰好一个 baseline、至少两个 structural break，且至少一个会推翻当前策略。optimistic/base/pessimistic 只可作为测试或 experimental 参数预设，不能满足 full 方法合同；用户审阅 frame 后才创建不可变 ScenarioVersion。

## 核心判定纪律

- 业务硬门使用布尔 AND：致命安全/交付/现金/采购缺口不能被大市场或高增长分数抵消。
- 分数只表达单维质量或比较权重，不表达“结论正确概率”或“项目成功概率”。
- 乘法指标仅用于 full 正式产物的交付资格，不能用于给市场方向估算成功率。
- 相关性不得冒充因果；模型生成的边保持 `draft`，必须携带证据、假设和关系质量。
- Critic 的高/关键严重度发现必须改变正文、条件、质量状态、因果边或触发 escalation，不能只留在附录。

本包共编译 17 个 source skill、10 个 Prompt 和 9 个 Draft 2020-12 schema。执行合同以 `manifest.yaml`、`diagnostic-questions.yaml`、`quality-gates.yaml`、`prompts/` 和 `schemas/` 为准。

所有 Prompt 都是模型厂商无关的 JSON/schema 合同：运行时可使用 DeepSeek 或其他 OpenAI-compatible Provider，但必须在服务端做 schema 校验，不能依赖某个模型的私有字段或隐藏思维过程。
