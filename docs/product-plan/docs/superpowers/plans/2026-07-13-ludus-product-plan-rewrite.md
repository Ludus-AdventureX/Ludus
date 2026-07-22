# Ludus Product Plan Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 README 与 01-20 重构为一套以 Ludus 为展示品牌、支持 AI 辅助 72 小时完整功能 Demo、并明确复用三个本地参考资产的单一可实施合同。

**Architecture:** README 与 17 负责产品总合同，06 负责 canonical data schema，10 负责 canonical API/event contract，18 负责实施顺序；其余文档只扩展各自领域，不重复发明平行字段或状态。重构按产品语义、运行时合同、用户体验和交付验收四层推进，最后使用自动扫描和人工交叉检查验证一致性。

**Tech Stack:** Markdown、Mermaid、TypeScript/Python schema 示例、PowerShell、ripgrep；参考资产为 `探讨`、Hermes Agent 和 Open WebUI 0.10.2。

---

## 执行约束

- 目标目录不是 Git 仓库，不执行提交，也不擅自初始化 Git。
- 所有文件使用 UTF-8，保留现有中文内容和仍然有效的用户决策。
- 产品展示名写作 `Ludus`；内部仓库、包名和配置标识使用 `decision-lab`。
- deterministic fixture 只作为明确标识的最坏情况降级。
- 参考资产以“提炼、适配、测试”为原则，不 fork Open WebUI，也不直接嵌入 Hermes 的 CLI 单体循环。
- 每份文档修改后立即执行局部术语和合同检查，全部完成后再运行全局扫描。

### Task 1: 建立总合同与文档优先级

**Files:**
- Modify: `README.md`
- Modify: `17-product-design-v2.md`

- [ ] **Step 1: 将 README 品牌合同改为 Ludus**

写明展示品牌、中文定位、品牌主张解释和 `decision-lab` 技术标识；删除旧名称禁令。

- [ ] **Step 2: 重写 72 小时可行性结论**

写明 AI 持续辅助的生产力假设、真实实现清单、live-first 路径和 fixture-worst-case 路径。

- [ ] **Step 3: 将 17 升级为 Ludus 产品总设计**

统一可信度、正式 Worker、既有资产适配、分支回滚、用户权力边界和 P0/P1 范围。

- [ ] **Step 4: 验证总合同**

Run:

```powershell
rg -n --encoding utf-8 "Decision Lab|旧名称不得|Ludus|decision-lab|fixture|72 小时" README.md 17-product-design-v2.md
```

Expected: 产品正文使用 Ludus；Decision Lab 只允许出现在历史说明或技术目录语境；fixture 明确为最坏降级。

### Task 2: 重写产品愿景

**Files:**
- Modify: `01-product-vision.md`

- [ ] **Step 1: 更新定位与价值主张**

把“预见未来”解释为提前暴露假设、影响路径、翻转条件和验证优先级。

- [ ] **Step 2: 修正可信度承诺**

将“防范幻觉”限定为阻止无依据内容进入正式输出；将“每一步推理”改为用户可见产物可追溯。

- [ ] **Step 3: 更新成功指标**

除结构完整性外，增加证据支持准确性、因果边可解释性、降级标识和翻转条件可复现。

- [ ] **Step 4: 验证愿景文案**

Run: `rg -n --encoding utf-8 "精确预测|消除幻觉|内部思维|成功概率|翻转条件" 01-product-vision.md`

Expected: 没有绝对化可信度承诺；限制和真实能力同时可见。

### Task 3: 重写 PRD 与用户流程

**Files:**
- Modify: `02-prd-and-user-flows.md`

- [ ] **Step 1: 固化三模式与跨模式对象**

明确日常问答、正式分析和沙盘分别读写 CandidateRevision、冻结快照和 GraphBranch。

- [ ] **Step 2: 增加 live/cached/fixture 流程**

正常路径优先真实模型与真实数据源；最坏路径由用户明确切换 fixture，且后续 UI 持续显示来源状态。

- [ ] **Step 3: 增加分支、比较和回滚用户流程**

定义从历史图版本创建分支、比较变化、非破坏性回滚和候选采纳。

- [ ] **Step 4: 验证流程闭环**

Run: `rg -n --encoding utf-8 "CandidateRevision|GraphBranch|live|cached|fixture|比较|回滚" 02-prd-and-user-flows.md`

Expected: 六组术语均存在并形成端到端路径。

### Task 4: 重写现有资产评估

**Files:**
- Modify: `03-existing-assets-assessment.md`

- [ ] **Step 1: 补全 `探讨` 的方法论资产映射**

记录 framework-selector v6.12.7、RAG pool、analysis/safety/synthesis/chief/devils/quality gate 和脚本产物。

- [ ] **Step 2: 补全 Hermes 代码级采用矩阵**

列出 registry、model_tools、delegate、MoA、MCP、Skill、session/context 的来源文件、可适配机制和不采用部分。

- [ ] **Step 3: 补全 Open WebUI 交互采用矩阵**

列出 Chat event handler、statusHistory、TaskList、ToolCallDisplay、Citations、后端 events 和 MCP client。

- [ ] **Step 4: 重算 72 小时节省项**

区分可直接提炼的方法内容、可适配运行时模式、可参考 UI 模式和仍需新建的 Ludus 领域模型/沙盘。

- [ ] **Step 5: 验证本地路径**

Run:

```powershell
rg -n --encoding utf-8 "framework-selector|pool_manager|tools/registry.py|delegate_tool.py|mcp_tool.py|Chat.svelte|ToolCallDisplay|Citations" 03-existing-assets-assessment.md
```

Expected: 每类资产都有真实本地文件依据和 Ludus 落点。

### Task 5: 修正决策方法论与可信度模型

**Files:**
- Modify: `04-decision-methodology.md`

- [ ] **Step 1: 保留类型分离、论证、反方、冲突和复盘协议**

将 `探讨` 的成熟方法规则编译为首个方法包，而不是重新发明等价流程。

- [ ] **Step 2: 删除任意加权总置信公式**

改为证据可用性、命题支撑、假设稳定性、因果可信、稳健性和流程质量六类状态。

- [ ] **Step 3: 定义乘法门控边界**

乘法值只判断正式交付资格；任一阻断维度失败即不发布，不解释为正确概率。

- [ ] **Step 4: 验证可信度表述**

Run: `rg -n --encoding utf-8 "confidence =|正确概率|交付资格|最脆弱环节|命题支撑" 04-decision-methodology.md`

Expected: 不存在旧加权公式；存在多维等级和交付门控说明。

### Task 6: 统一系统架构与复用边界

**Files:**
- Modify: `05-system-architecture.md`

- [ ] **Step 1: 更新总体架构图**

加入 Method/Skill Loader、Agent Runtime、Connector/MCP Adapter、Trace Projection、Graph Versioning 和 fixture provider。

- [ ] **Step 2: 明确 Next.js/FastAPI 边界**

Next.js 只负责 Web UI、SSR/打印页面和浏览器状态；FastAPI 负责业务 API、租户、Agent、连接器、报告和沙盘。

- [ ] **Step 3: 写入三个参考资产的适配位置**

Hermes 机制进入运行时，Open WebUI 模式进入 Web 事件与组件，`探讨` 进入方法包编译。

- [ ] **Step 4: 验证架构模块**

Run: `rg -n --encoding utf-8 "Method/Skill|Agent Runtime|MCP|Trace|Graph Version|Open WebUI|Hermes|探讨" 05-system-architecture.md`

Expected: 架构图和模块边界覆盖全部采用关系。

### Task 7: 重建 canonical data schema

**Files:**
- Modify: `06-data-model.md`

- [ ] **Step 1: 统一租户、版本和候选类型**

为所有业务对象补齐 Workspace 作用域；定义 ConversationRevision、CandidateRevision、DossierVersion 和 CaseVersion。

- [ ] **Step 2: 补全 AnalysisCharter 与 StructuredReport**

Charter 包含目标、约束、选项、材料和预算；StructuredReport 包含 `sections`、`simulationSeeds`、方法版本和质量门。

- [ ] **Step 3: 补全 Strategy/Scenario/ScoreDefinition**

定义 OptionOutcomeMapping、RiskWeight、ConstraintRule、StrategyVersion 和 ScenarioVersion。

- [ ] **Step 4: 补全 GraphBranch 与 SimulationRun 引用**

图版本记录父版本、分支、来源报告和 provenance；运行固定引用图、策略、情景和引擎版本。

- [ ] **Step 5: 执行字段一致性扫描**

Run:

```powershell
rg -n --encoding utf-8 "interface (AnalysisCharter|StructuredReport|GraphBranch|StrategyVersion|ScenarioVersion|ScoreDefinition|SimulationRun)|workspaceId|simulationSeeds|engineVersion" 06-data-model.md
```

Expected: canonical 类型全部存在，后续文档不需要自行补字段。

### Task 8: 重写 Agent 工作流

**Files:**
- Modify: `07-agent-workflow.md`

- [ ] **Step 1: 固定正式角色与 Safety Anchor 位置**

正式 Worker 为 Research、Critic、Synthesis、Validation；Safety Anchor 是 Critic 的强制子阶段。

- [ ] **Step 2: 映射 Hermes 运行时机制**

采用工具注册、工具权限交集、子任务隔离、并发/深度/迭代预算、tool trace、进度 callback 和中断。

- [ ] **Step 3: 定义 Web 可见事件**

每个 Agent/任务只展示角色、目标、状态、工具摘要、产物和错误，不展示内部思维链。

- [ ] **Step 4: 验证角色与事件**

Run: `rg -n --encoding utf-8 "Research|Critic|Synthesis|Validation|Safety Anchor|tool trace|progress|内部思维" 07-agent-workflow.md`

Expected: 角色命名唯一，Web 展示边界明确。

### Task 9: 对齐深度研究流水线

**Files:**
- Modify: `08-deep-research-pipeline.md`

- [ ] **Step 1: 将 `探讨` 产物映射为方法包阶段**

使用真实技能版本和产物路径说明输入如何转换为数据库对象。

- [ ] **Step 2: 统一 StructuredReport 示例**

示例必须与 06 的字段、枚举和引用完全一致。

- [ ] **Step 3: 写入真实 Provider 与 fixture 降级**

真实检索失败后按状态切换 cached/fixture，不将缓存伪装为 live。

- [ ] **Step 4: 验证报告合同**

Run: `rg -n --encoding utf-8 "simulationSeeds|sections|qualityGate|live|cached|fixture|methodVersion" 08-deep-research-pipeline.md`

Expected: 报告示例可直接通过 06 的 schema。

### Task 10: 修复沙盘算法合同

**Files:**
- Modify: `09-simulation-engine.md`

- [ ] **Step 1: 修复归一化 delta**

伪代码使用 `normalize(node, node.baseline)`，禁止归一化状态减业务单位。

- [ ] **Step 2: 引入显式评分定义**

选项评分只读取 ScoreDefinition、目标映射、风险权重和约束规则。

- [ ] **Step 3: 加入收敛、饱和和错误处理**

定义最大步数、epsilon、非收敛、NaN、Infinity 和裁剪警告。

- [ ] **Step 4: 加入版本和分支语义**

相同 graph/strategy/scenario/engine 版本必须产生相同结果；回滚创建新版本。

- [ ] **Step 5: 验证公式**

Run: `rg -n --encoding utf-8 "normalizedBaseline|ScoreDefinition|epsilon|non_convergent|engineVersion|branch" 09-simulation-engine.md`

Expected: 原始量纲错误表达不再存在。

### Task 11: 补全 API 与事件合同

**Files:**
- Modify: `10-api-and-events.md`

- [ ] **Step 1: 增加候选审阅 API**

定义 list/confirm/reject/bulk-review，候选操作不直接提升 CaseVersion。

- [ ] **Step 2: 增加图版本 API**

定义 branch、working-copy、compare、rollback、simulation run 和 candidate adoption。

- [ ] **Step 3: 统一事件信封**

采用 Open WebUI 可借鉴的 message/status/task/citation/confirmation 分类，但保存 Ludus 领域事件并通过 SSE 重放。

- [ ] **Step 4: 增加 live/cached/fixture 状态**

连接器调用、证据、报告和降级事件使用一致枚举。

- [ ] **Step 5: 验证 API 覆盖**

Run: `rg -n --encoding utf-8 "candidates|bulk-review|branches|compare|rollback|Last-Event-ID|live|cached|fixture" 10-api-and-events.md`

Expected: 每项能力至少有一个 API 或事件合同。

### Task 12: 补全前端呈现规格

**Files:**
- Modify: `11-frontend-spec.md`

- [ ] **Step 1: 吸收 Open WebUI 的交互模式**

定义 message-scoped status history、Agent/Task 列表、工具调用折叠、引用抽屉、确认弹层、取消和恢复。

- [ ] **Step 2: 定义 Ludus 多 Agent 展示**

阶段行展示 Agent 角色、目标、任务状态、已用工具、产物数量和错误；不显示内部思维。

- [ ] **Step 3: 增加跨模式溯源和路径高亮**

报告命题、证据、因果边和未知项支持双向定位；节点干预后显示一至三阶正负影响路径。

- [ ] **Step 4: 增加分支时间线与回滚 UI**

定义工作副本、undo/redo、保存版本、创建分支、比较和非破坏性回滚。

- [ ] **Step 5: 验证前端规格**

Run: `rg -n --encoding utf-8 "statusHistory|Agent|Task|工具调用|引用|undo|redo|分支|比较|回滚|影响路径" 11-frontend-spec.md`

Expected: 用户可见的 Agent、工具、证据和版本交互全部有定义。

### Task 13: 重算 72 小时执行计划

**Files:**
- Modify: `12-72-hour-execution-plan.md`

- [ ] **Step 1: 改写生产力假设**

以用户决策加 AI 持续开发为执行单元，不沿用传统 2/3 人线性估算。

- [ ] **Step 2: 按垂直切片重排时间**

0-12h 基础与 fixture 金路径；12-30h 对话/档案/方法/Run；30-48h 研究/报告；48-60h 沙盘/版本；60-72h E2E/部署/宣传。

- [ ] **Step 3: 记录资产复用节省**

方法论、Agent 机制和 Web 交互分别注明来自三个本地参考资产。

- [ ] **Step 4: 删除非 P0 任务**

移除积分、社区、历史检索投影和完整提醒系统。

- [ ] **Step 5: 验证时间盒**

Run: `rg -n --encoding utf-8 "0-12h|12-30h|30-48h|48-60h|60-72h|积分|DecisionEpisode|fixture" 12-72-hour-execution-plan.md`

Expected: 五个时间段存在；非 P0 项只出现在排除范围。

### Task 14: 加强测试与验收

**Files:**
- Modify: `13-testing-and-acceptance.md`

- [ ] **Step 1: 增加内容支持度验收**

检查证据是否真正支持命题，而不是只验证引用 ID 存在。

- [ ] **Step 2: 增加 Agent/工具/MCP 测试映射**

参考 Hermes 的 registry、delegate、MCP 和 Skill 测试类型，覆盖权限、深度、预算、动态工具和错误清洗。

- [ ] **Step 3: 增加前端事件与恢复验收**

覆盖 status、task、tool call、citation、confirmation、取消、重连和历史重放。

- [ ] **Step 4: 增加沙盘版本测试**

覆盖确定性、归一化、分支、比较、回滚和翻转条件复现。

- [ ] **Step 5: 验证验收覆盖**

Run: `rg -n --encoding utf-8 "支持命题|registry|delegate|MCP|Skill|citation|confirmation|分支|回滚|确定性" 13-testing-and-acceptance.md`

Expected: 四类新增风险均有明确测试。

### Task 15: 更新演示剧本

**Files:**
- Modify: `14-demo-script.md`

- [ ] **Step 1: 使用 Ludus 品牌和真实能力话术**

保留品牌主张但避免精确预测、消除幻觉和内部思维链承诺。

- [ ] **Step 2: 展示多 Agent 与工具状态**

演示任务列表、工具摘要、引用、质量门和实时/缓存状态。

- [ ] **Step 3: 展示分支与回滚**

在 5 分钟剧本中创建压力情景分支、比较推荐并回到基准版本。

- [ ] **Step 4: 将 fixture 定义为最坏情况**

只有真实外部服务失败时使用，且全程显示 fixture 标识。

- [ ] **Step 5: 验证演示话术**

Run: `rg -n --encoding utf-8 "Ludus|Agent|工具|分支|比较|回滚|fixture|精确预测" 14-demo-script.md`

Expected: 演示包含真实运行优先和清晰降级边界。

### Task 16: 更新开源与本地参考边界

**Files:**
- Modify: `15-open-source-references.md`

- [ ] **Step 1: 将三个本地资产放在采用矩阵首位**

逐文件说明直接适配、重写适配、仅参考和不采用。

- [ ] **Step 2: 记录 Hermes MCP 与 Skill 能力**

说明 P0 只复用安全的 schema/lifecycle/loader 模式，不开放任意服务器执行。

- [ ] **Step 3: 记录 Open WebUI 许可和交互边界**

不 fork、不复制品牌界面，只参考事件与组件行为。

- [ ] **Step 4: 验证采用矩阵**

Run: `rg -n --encoding utf-8 "直接适配|重写适配|仅参考|不采用|mcp_tool.py|skill_utils.py|Chat.svelte" 15-open-source-references.md`

Expected: 采用边界可直接指导 18 的文件任务。

### Task 17: 调整黑客松后路线图

**Files:**
- Modify: `16-post-hackathon-roadmap.md`

- [ ] **Step 1: 将基础可信度评估前移到 P0**

P0 已包含最小内容支持度与沙盘边人工验收；后续扩展为统计校准和真实复盘评估。

- [ ] **Step 2: 保留后续产品化任务**

复杂权限、通用 MCP、方法市场、历史检索、通知和校准继续放在后续。

- [ ] **Step 3: 验证路线图边界**

Run: `rg -n --encoding utf-8 "P0|2 周|6 周|3 个月|校准|方法市场|历史检索|通知" 16-post-hackathon-roadmap.md`

Expected: 可信度基础验收不再全部推迟，产品化能力仍有清晰阶段。

### Task 18: 重写详细开发计划

**Files:**
- Modify: `18-detailed-development-plan.md`

- [ ] **Step 1: 替换总目标、品牌和生产力模型**

使用 Ludus 展示名，明确 AI 持续辅助与现有资产适配。

- [ ] **Step 2: 重排为垂直切片任务**

每个切片同时包含 schema、服务、UI、测试和可运行验收，避免前后端长时间分离。

- [ ] **Step 3: 写入具体参考文件**

每个 Agent、工具、MCP、Skill、会话事件、工具展示和引用任务列出对应 Hermes/Open WebUI/`探讨` 文件。

- [ ] **Step 4: 修复 canonical schema 与算法任务**

所有代码示例引用 06 的字段，沙盘测试覆盖 normalized baseline、ScoreDefinition、版本和回滚。

- [ ] **Step 5: 删除模拟积分和 DecisionEpisode P0 任务**

将它们移入路线图，不占用 72 小时。

- [ ] **Step 6: 验证详细计划**

Run:

```powershell
rg -n --encoding utf-8 "Ludus|tools/registry.py|delegate_tool.py|mcp_tool.py|skill_utils.py|Chat.svelte|Citations.svelte|normalizedBaseline|ScoreDefinition|GraphBranch|credit_ledger|DecisionEpisode" 18-detailed-development-plan.md
```

Expected: 参考来源和核心修复存在；移出项只在排除或后续范围出现。

### Task 19: 更新数据源、MCP 与发布约束

**Files:**
- Modify: `19-mcp-data-sources-and-launch-constraints.md`

- [ ] **Step 1: 固化 live-first 路由**

Exa/Firecrawl/Tavily 优先真实调用，cached/fixture 只在失败时显式切换。

- [ ] **Step 2: 写明 Hermes MCP 参考边界**

可适配 schema conversion、namespacing、timeout、error sanitize 和 lifecycle；P0 不接受任意 URL、stdio/npx 和写工具。

- [ ] **Step 3: 完善密钥边界**

定义服务端 master key、密文存储、掩码响应、日志清洗和删除行为；不在 P0 承诺企业级轮换。

- [ ] **Step 4: 验证连接器合同**

Run: `rg -n --encoding utf-8 "live|cached|fixture|schema|namespace|timeout|sanitize|master key|stdio|npx" 19-mcp-data-sources-and-launch-constraints.md`

Expected: 正常、降级和禁止能力都有明确状态。

### Task 20: 对齐对话驱动方法路由

**Files:**
- Modify: `20-conversation-led-method-routing.md`

- [ ] **Step 1: 说明 Method/Skill Loader 来源**

采用 Hermes Skill frontmatter/发现/按需注入模式，方法包仍由 Ludus 版本化发布目录控制。

- [ ] **Step 2: 对齐 `探讨` 的模式语义**

将原 A/B/C 方法能力映射到 quick/focused/full，但用户界面只展示 Ludus 三档名称。

- [ ] **Step 3: 保持正式分析阻断**

唯一正式方法包不匹配时只允许聊天和明确非正式 quick。

- [ ] **Step 4: 验证路由合同**

Run: `rg -n --encoding utf-8 "Skill Loader|frontmatter|quick|focused|full|hardtech-market-direction|unsupported" 20-conversation-led-method-routing.md`

Expected: 方法来源、用户入口和正式授权边界一致。

### Task 21: 执行全目录一致性审查

**Files:**
- Verify: `README.md`
- Verify: `01-product-vision.md` through `20-conversation-led-method-routing.md`

- [ ] **Step 1: 扫描旧品牌与绝对化承诺**

Run:

```powershell
rg -n --encoding utf-8 "产品展示名统一为 \*\*Decision Lab|旧名称不得|消除幻觉|每一个推理步骤|精确预测未来|成功概率" . -g '*.md'
```

Expected: 无匹配；历史说明必须改为不触发上述产品承诺。

- [ ] **Step 2: 扫描 canonical 合同覆盖**

Run:

```powershell
rg -l --encoding utf-8 "simulationSeeds|GraphBranch|ScoreDefinition|live|cached|fixture|Ludus" README.md 0*.md 1*.md 20-conversation-led-method-routing.md
```

Expected: 相关领域文档均覆盖其负责的 canonical 术语。

- [ ] **Step 3: 扫描状态枚举漂移**

Run: `rg -n --encoding utf-8 "queued|planning|retrieving|analyzing|criticizing|synthesizing|validating|ready|blocked|needs_attention|cancelled" *.md`

Expected: AnalysisRun 状态集合没有额外平行状态。

- [ ] **Step 4: 扫描占位符和无效引用**

Run: `rg -n --encoding utf-8 "[T]BD|[T]ODO|以后[补]充|待[定]义|待[实]现" . -g '*.md'`

Expected: 无未解释占位符；外部服务的“待配置”必须是明确运行状态而非缺失设计。

- [ ] **Step 5: 验证全部本地参考路径存在**

Run:

```powershell
$paths = rg -o --no-filename --encoding utf-8 "(?:探讨|hermes-agent-hermes-hermes-a8a19433|open-webui-0\.10\.2)/[^` )]+" . -g '*.md' | Sort-Object -Unique
$missing = $paths | Where-Object { -not (Test-Path -LiteralPath (Join-Path 'E:\Temp\xiayu\Documents\adventure-x' ($_ -replace '/', '\'))) }
if ($missing) { $missing; exit 1 }
```

Expected: exit code 0 and no missing paths.

- [ ] **Step 6: 人工交叉审查**

逐项核对 README/17 总合同、06 schema、09 算法、10 API、11 UI、13 验收和 18 实施计划，确认同一能力的字段、状态、版本和 P0 边界一致。
