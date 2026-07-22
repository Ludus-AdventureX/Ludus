# Ludus 72 小时完整功能 Demo 文档重构设计

## 1. 文档目的

本设计用于统一 `decision-lab-product-plan` 中 README 与 01-20 的产品、工程和交付合同。重构后的文档必须支持在 AI 持续辅助架构、编码、测试、联调和修复的前提下，于 72 小时内交付一个真实可运行的完整功能 Demo。

本设计只定义文档如何重构，不代表产品代码已经实现。

## 2. 品牌与技术标识

- 产品展示名统一为 **Ludus**。
- 中文定位统一为“企业战略决策沙盒”。
- 品牌主张保留“预见未来，保障您的事业”，但正文必须解释为提前识别假设、影响路径、风险和推荐翻转条件，不得暗示精确预测未来。
- 仓库、目录、包名、数据库前缀、环境变量命名和内部配置标识继续使用 `decision-lab`。
- 原有“展示名只能使用 Decision Lab、旧名称不得出现”的合同全部删除或替换。

## 3. 产品真实性边界

### 3.1 可以承诺

- 用户可从日常对话形成候选档案，并在确认后生成正式版本。
- 正式分析绑定不可变的档案快照、方法版本、输入范围、数据源和预算。
- 用户可追溯每条用户可见命题、证据、假设、判断、方法版本、状态变化、因果边和最终建议。
- 正式报告通过信息质量门、反方审查和分析质量门。
- 用户可在因果沙盘中干预变量、修改关系、创建实验分支、运行情景、查看敏感性和推荐翻转条件。
- 用户可保存最终决定、成立条件、退出条件、领先指标和复盘日期。

### 3.2 不可以承诺

- 不展示或声称保存模型不可验证的内部思维链。
- 不声称消除大模型幻觉，只声称降低无依据内容进入正式输出的风险。
- 不把任何综合分数包装为真实成功概率、统计置信区间或未来预测概率。
- 不声称因果边天然为事实；自动生成边必须保留来源、状态和适用限制。
- 不以预置 fixture 冒充实时模型、实时搜索或真实外部证据。

## 4. 72 小时完成定义

### 4.1 生产力假设

72 小时评估基于以下协作方式：

- 用户负责产品取舍、关键业务口径、外部账号与最终验收。
- AI 辅助开发持续承担代码生成、重构、迁移、测试、联调、错误定位、文档同步和发布检查。
- 开发以连续可验证的垂直切片推进，不按传统人工团队的串行工时估算。
- 所有关键合同在开发前冻结；非阻断设计问题由既定默认值解决，不重复等待会议决策。

### 4.2 必须真实实现的功能

- 浏览器可访问的 Web 应用、API、Worker 和 PostgreSQL 数据路径。
- 简单认证与 Workspace 隔离。
- 日常问答、候选提取、确认/否决和版本化档案。
- `quick`、`focused`、`full` 三档入口，以及唯一正式方法包 `hardtech-market-direction@1.1.0`。
- Analysis Charter、AnalysisRun 状态机、持久事件、SSE 进度和恢复。
- Exa 搜索、Firecrawl 抓取和 Tavily 备用的真实 Provider Adapter。
- RawArtifact、Evidence Ledger、信息质量门、Research/Critic/Synthesis/Validation。
- 同源结构化报告、HTML 和 PDF。
- 可编辑因果图、Strategy、Scenario、变量干预、传播、评分、敏感性和翻转条件。
- 最小实验分支、图版本、版本比较和非破坏性回滚。
- 最终决定记录和复盘字段。
- 单元、集成和 Playwright 金路径测试。

### 4.3 deterministic fixture 的位置

- fixture 是模型、搜索、抓取或网络全部不可用时的最坏情况降级。
- 正常启动和验收优先使用真实模型与真实数据源。
- 降级必须由用户显式触发或由系统明确告知后切换。
- UI、事件、报告和导出物必须持续显示 `live`、`cached` 或 `fixture` 来源状态。
- fixture 只替代不稳定的外部输入，不替代数据库、状态机、质量门、报告渲染、沙盘计算、版本和保存流程。

### 4.4 退出 72 小时范围

- 真实计费和模拟积分账本。
- 社区贡献、方法市场和跨租户学习。
- DecisionEpisode 历史检索投影。
- 完整通知与自动监控系统。
- 企业级 SSO、复杂 RBAC、审批和多人实时协作。
- 通用方法编辑器和跨行业正式方法库。

## 5. 既有资产适配合同

Ludus 不从零设计方法论、Agent 基础机制或通用聊天交互。三个本地参考资产分别承担不同来源角色，但不直接作为一个整体 fork。

### 5.1 `探讨`：首个方法包的内容来源

- `skills/research/framework-selector/SKILL.md` 提供模式路由、方向确认、复杂度门控、失败恢复和两段式交付协议。
- `v6-rag-pool` 及 `scripts/pool_manager.py` 提供检索任务、优先级、并发、重试、L1-L6 来源分级、相关性过滤和基础设施降级机制。
- `v6-analysis-agent`、`v6-safety-anchor`、`v6-strategy-synthesis`、`v6-chief-of-staff`、`v6-devils-advocate` 和 `analysis-quality-gate` 提供首个正式方法包的阶段、结构化产物和质量规则。
- 这些资产编译为 `hardtech-market-direction@1.1.0` 的 manifest、Prompt、schema、quality gates 和 eval fixtures；生产运行时不把临时 Markdown 目录作为唯一状态。
- 方法内容迁移必须记录原技能路径、版本和内容哈希，便于追溯后续升级。

### 5.2 Hermes Agent：运行时机制来源

- 参考 `tools/registry.py` 的单一注册表，统一保存工具名称、schema、handler、toolset、可用性检查和环境要求。
- 参考 `model_tools.py` 的工具发现、可用工具过滤、统一 dispatch 和动态 MCP 注册流程，但 Ludus 使用原生 async FastAPI/Worker，不复制同步桥接和 CLI 全局状态。
- 参考 `tools/delegate_tool.py` 的隔离上下文、父级工具权限取交集、并发/深度/迭代限制、结构化摘要、tool trace 和进度回调。
- 参考 `tools/mixture_of_agents_tool.py` 的并行参考输出与聚合思路，但正式分析按方法包角色和证据合同编排，不把通用模型投票当作置信概率。
- 参考 `tools/mcp_tool.py` 的工具 schema 转换、名称前缀、连接生命周期、动态工具刷新、错误清洗、超时和安全环境过滤。P0 仍只允许审核目录中的只读连接器，不开放任意 MCP URL、stdio/npx 或写工具。
- 参考 `agent/skill_utils.py`、`agent/skill_commands.py` 和 Skills 工具的 frontmatter、发现、装载与按需注入机制，建立版本化 Method/Skill Loader。
- 参考 `gateway/session.py`、上下文压缩、状态回调和中断机制；正式 Ludus 状态改存 PostgreSQL，并绑定 Workspace、Case 和 AnalysisRun。

### 5.3 Open WebUI：Web 交互机制来源

- 参考 `src/lib/components/chat/Chat.svelte` 的 message-scoped event handler、`statusHistory`、任务 ID、取消、确认输入、来源/引用事件和断线后任务协调。
- 参考 `ToolCallDisplay.svelte` 的工具调用折叠状态、运行/完成/错误反馈和结果查看模式。
- 参考 `Citations.svelte` 的引用列表与来源详情交互，映射为 Ludus 的 Evidence Drawer 和命题溯源。
- 参考 `ResponseMessage/TaskList.svelte` 的后台任务可见性，映射为多 Agent 阶段、子任务和检索任务列表。
- 参考后端事件定义、Socket 路由和 MCP client 的事件封装、工具状态和连接生命周期，但 Ludus 的正式 AnalysisRun 仍以持久化事件加 SSE/Last-Event-ID 为主。
- 不 fork Open WebUI，不复制品牌受限界面或其完整依赖；只重新实现与 Ludus 信息架构相符的交互模式。

### 5.4 复用验收

- 每个采用机制在文档中列出本地来源文件和 Ludus 落点。
- 直接适配的代码必须单独审查许可证、依赖和隐藏全局状态。
- 参考资产的 CLI、消息网关、通用工具全集、任意代码执行和通用聊天产品结构不进入 Ludus P0。
- 72 小时估算按“提炼、适配、测试”计算，不再按从零发明相同机制计算。

## 6. 可信度与多 Agent 合同

Ludus 使用多 Agent 分工和质量门，而不是把多个模型自评分简单平均。

用户可见可信度分为：

- 证据可用性。
- 命题支撑状态。
- 反对证据与冲突状态。
- 假设稳定性。
- 因果关系存在可信度。
- 影响强度。
- 战略跨情景稳健性。
- 分析流程质量。

质量门可以使用乘法门控决定是否允许生成正式报告，但乘法结果只表示交付资格，不表示结论正确概率。界面默认展示“等级、原因、最脆弱环节”，数值细节放入展开区域。

正式 Worker 固定为 Research、Critic、Synthesis、Validation。Safety Anchor 作为 Critic 阶段的强制检查子步骤，不新增角色命名冲突。Worker 输出必须是结构化产物，并记录模型、Prompt 版本、输入/输出哈希和引用关系。

## 7. 统一数据合同

`06-data-model.md` 作为类型和字段的唯一规范，其他文档只引用，不重复发明平行结构。

必须修复：

- 所有正式业务对象包含 `workspaceId` 和必要的聚合引用。
- AnalysisCharter 包含目标、约束、选项、未知项、允许/禁止材料、方法信息和预算。
- StructuredReport 正式包含 `sections`、`simulationSeeds`、方法版本和质量门结果。
- CandidateRevision、DossierVersion、CaseVersion 和 ConversationRevision 分离。
- Strategy、Scenario 和 SimulationRun 分离建模。
- 增加 OptionOutcomeMapping、RiskWeight、ConstraintRule 和 ScoreDefinition。
- CausalGraph 增加 parentVersionId、branchId、sourceGraphVersionId 和 provenance。
- 每次 SimulationRun 固定引用 graphVersion、strategyVersion、scenarioVersion 和 engineVersion。

## 8. 沙盘计算合同

- 所有传播计算使用归一化值，`delta = normalizedCurrent - normalizedBaseline`。
- 业务单位只在引擎入口归一化，在输出边界反归一化。
- Strategy 只改变 decision/lever；Scenario 只改变 external/unknown；Constraint 修改必须标记为实验性覆盖。
- 正式运行只使用 confirmed/conditional 边；包含 draft 边的运行标记为 experimental。
- 引擎限制步数，检测非收敛、NaN、无穷值和裁剪饱和。
- 选项评分必须由显式目标映射、风险权重和约束规则驱动，不允许从节点名称隐式猜测。
- 敏感性分析输出分数变化、排序变化、首个翻转阈值和最脆弱边。
- 相同输入、版本和引擎版本必须得到相同输出。

## 9. 分支、版本与回滚合同

P0 实现最小但真实的版本能力：

- 编辑发生在工作副本，运行前可 undo/redo。
- 保存工作副本创建新的不可变 graph version。
- 用户可以从任意历史 graph version 创建实验分支。
- 比较视图展示节点、边、参数、结果和推荐变化。
- 回滚不删除历史，而是从目标历史版本创建新的当前版本。
- 采纳沙盘结论只生成候选档案更新，仍需用户确认。

## 10. API 合同修复

`10-api-and-events.md` 必须补充：

- 候选列表、确认、否决和批量审阅 API。
- CaseVersion 与候选修订分离。
- 图版本、分支创建、比较、回滚和工作副本保存 API。
- SimulationRun 显式绑定全部输入版本。
- 跨 Workspace 的 API、SSE、报告、文件和连接器统一返回 404。
- 创建 Run、报告、PDF、图版本和决定记录使用幂等键。
- 所有外部输入状态在 API 中返回 `live/cached/fixture`。

## 11. 用户体验合同

### 11.1 核心界面

- 日常问答与档案确认工作台。
- 分析任务书、进度、证据、质量门和报告界面。
- 全尺寸因果沙盘。
- 最终决定和复盘抽屉。

### 11.2 跨模式溯源

- 点击报告命题可查看支持、反对证据和假设。
- 点击沙盘边可定位产生它的命题和证据。
- 点击未知项可返回日常问答或创建检索任务。
- 调整节点后高亮一至三阶正负影响路径。
- 公共状态条展示证据、因果链、战略稳健性、质量门和版本状态。

### 11.3 沙盘交互

- 图画布支持稳定布局、缩放、拖拽、选择和筛选。
- 右侧检查器编辑节点、边、依据、强度、可信度和适用限制。
- 顶部使用 Strategy/Scenario 分段控件。
- 底部展示选项评分、敏感因素、翻转条件、约束和模型完整性。
- 分支时间线支持创建、比较、回滚和命名。
- 所有状态使用文字、图标和形状共同表达，不只依赖颜色。

## 12. 测试与验收合同

- 单元测试覆盖 schema、状态机、质量门、归一化、传播、延迟、循环、评分、约束、敏感性和回滚。
- 集成测试覆盖数据库迁移、Workspace 隔离、Run 领取、SSE 重连、报告/PDF、连接器降级和幂等。
- E2E 覆盖 live 优先的金路径和显式 fixture 最坏路径。
- 内容验收检查引用是否真正支持命题，而不只检查 evidence ID 存在。
- 方法包至少包含预置案例、边界案例、输入不足案例和不支持案例。
- 沙盘 fixture 必须通过独立验证脚本复现推荐翻转，不能把期望结果硬编码在 UI。

## 13. 文档回写策略

- README：品牌、总合同、72 小时结论和文档导航。
- 01-04：产品定位、PRD、资产边界、方法论和可信度表述。
- 05-10：架构、canonical schema、Agent、研究流水线、沙盘和 API。
- 11：完整用户呈现、跨页溯源、分支与回滚交互。
- 12-14：AI 辅助生产力模型、72 小时执行、验收和演示。
- 15-16：依赖采用边界和真实试用路线图。
- 17：升级为 Ludus 产品总设计，不保留与 README 冲突的品牌合同。
- 18：删除非 P0 范围，按真实垂直切片重新排任务和时间。
- 19：明确 live-first、fixture-worst-case、密钥和发布约束。
- 20：保留对话驱动路由并统一正式输出边界。

## 14. 文档完成标准

- 全目录产品展示名统一为 Ludus，技术标识统一为 `decision-lab`。
- 不再出现“任意文档可自行选择合同”的空间。
- 数据字段、状态枚举、API 路径和事件名称可交叉对应。
- `simulationSeeds`、分支、版本、回滚和评分结构在数据、API、UI、测试与实施计划中全部出现。
- P0、P1 和活动后范围没有相互冲突。
- live、cached、fixture 的含义在所有相关文档一致。
- 不存在未决占位符、旧品牌禁令、伪概率或精确预测承诺。
- 72 小时完成线明确区分“真实实现”和“外部服务降级”。
