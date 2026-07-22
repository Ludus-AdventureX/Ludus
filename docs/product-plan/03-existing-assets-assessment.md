# 03. 现有资产评估

本评估只引用已检查到的本地文件和目录。目标是说明现有资产如何支撑 Ludus 的 Alpha，而不是复制现有系统。

逐文件复用判定、许可证/NOTICE、目标文件、适配点、验收以及 `探讨/skills/research` 全部 31 个 Skill 的处置账本，以 `21-existing-asset-reuse-and-conversion.md` 为唯一明细。本文只保留能力评估，不再充当不完整的复用清单。

## 工作区现状

工作区根目录 `E:\Temp\xiayu\Documents\adventure-x` 已是 Git 仓库根目录，但当前主要资产目录仍处于未跟踪状态；`decision-lab` 尚未初始化为独立 Git 仓库，`探讨` 与 Hermes 也不是独立仓库。因此，进入计时开发前必须先提交权威计划与 ways 基线，再按 Gate 0 在 `decision-lab` 建立独立仓库、分支和 worktree；在此之前同时使用根仓库状态、文件路径和最终目录范围校验保护现有改动。

## `探讨` 的结构与代表性成果

`探讨` 是一个以研究技能、模板和工具为主的分析资产目录。表面扫描显示其中包含大量 Markdown、Python、LaTeX、HTML、PDF 和 JSON 文件，核心目录包括：

- `探讨/skills/research/`：研究与战略分析技能。
- `探讨/templates/`：二十类交付物模板。
- `探讨/tools/`：研究和生成相关工具。
- `探讨/lessons/`、`探讨/memories/`：历史经验和记忆资产。

以下是已编译进首个 ways 或直接支撑其设计的代表性研究技能，不是全量 Skill 清单：

- `探讨/skills/research/framework-selector/SKILL.md`
- `探讨/skills/research/document-type-selector/SKILL.md`
- `探讨/skills/research/full-mode-composer/SKILL.md`
- `探讨/skills/research/v6-rag-pool/SKILL.md`
- `探讨/skills/research/v6-analysis-agent/SKILL.md`
- `探讨/skills/research/v6-safety-anchor/SKILL.md`
- `探讨/skills/research/v6-strategy-synthesis/SKILL.md`
- `探讨/skills/research/v6-chief-of-staff/SKILL.md`
- `探讨/skills/research/v6-devils-advocate/SKILL.md`
- `探讨/skills/research/v6-pipeline-coordinator/SKILL.md`
- `探讨/skills/research/analysis-quality-gate/SKILL.md`
- `探讨/skills/research/deliverable-standards/SKILL.md`
- `探讨/skills/research/pre-mortem/SKILL.md`
- `探讨/skills/research/scenario-planning/SKILL.md`
- `探讨/skills/research/porter-five-forces/SKILL.md`
- `探讨/skills/research/counterparty-response-matrix/SKILL.md`
- `探讨/skills/research/meadows-leverage-points/SKILL.md`

`探讨/skills/research` 实际包含 31 个 `SKILL.md`。其余框架分别被 quick/Review/沙盘等 canonical 合同吸收、延后到下一方法包、仅作参考或明确禁用；不得因为未出现在上述代表列表中就默认加载。完整逐项原因和验收见文档 21。

`探讨/SOUL.md` 的智力诚实、证据优先、反方和不确定性表达可转换为版本化 system policy 与方法 Prompt，但个人身份、单一用户偏好、飞书和人格表演不得进入产品。`探讨/config.yaml` 只允许白名单提取非秘密配置结构并转换为 typed settings/provider adapter；不得整体复制。`探讨/.env`、`探讨/auth.json` 属于禁止检查和复用的秘密资产，必须从安装、fixture、镜像和日志中排除。

模板层面，`探讨/templates/01_research_report/template.html`、`探讨/templates/01_research_report/template.tex` 和 `探讨/templates/01_research_report/template.pdf` 表明目录中已经有 HTML、LaTeX 和 PDF 交付物的模板资产。

## 已沉淀的第一版方法论

`探讨` 的首轮沉淀已经完成，不再是 72 小时内临场提炼的待办。可审阅源位于 `decision-lab/ways/hardtech-market-direction/1.1.0`，当前状态为 `release_candidate/unpublished`，包含 manifest、43 个诊断问题、29 项质量检查、Research/Critic/Synthesis/Validation Prompt、五个战略透镜 Prompt、9 个已通过 Draft 2020-12 严格编译的 JSON Schema、5 个 eval 规格、来源版本审计、changelog 和 `CAPABILITY-MAP.md`。能力地图逐项记录 `探讨/skills/research` 全部 31 个 Skill 的版本、处置状态、沉淀目标、运行边界与后续方法包候选，固定计数为直接编译 13、其他合同吸收 7、延后 8、参考 1、禁用 2。5 个 eval 分别覆盖球形机器人 exact/full、同一脑机接口平台案例在种子期与天使期资源约束下的尺度敏感性、信息缺失导致的 partial/full 阻断，以及不适用营销优化问题的 unsupported/focused 阻断；其中脑机接口双案例是去标识化的 parity 规格，不代表 legacy/Ludus 双轨运行已经完成。质量门新增 `AG-15` 至 `AG-18`，分别阻断时间/样本/分母错配、证据裁决与使用方式不一致、缺少资源尺度反事实，以及无法区分决策质量与结果质量的产物。

这两个目录有明确的单向关系：

- `探讨/` 是历史研究资产与来源依据，不是运行时输入。
- `ways/hardtech-market-direction/1.1.0` 是唯一可编辑、可评审的方法源。
- `method-packs/hardtech-market-direction/1.1.0` 是安装器校验、规范化并计算内容哈希后生成的不可变运行时副本。
- Router 只读取状态为 `published` 且哈希复算一致的 `method-packs`；`release_candidate` 不得进入正式分析。
- 发布后的同 ID/版本不得原地修改；Prompt、schema、质量门、预算、工具权限或来源变化必须提升 SemVer 并重新安装。

因此后续实现任务是“校验、安装、执行和评测第一版方法包”，不是再次从 `探讨` 编译一套平行方法论。

## `探讨` 模式二已经完成什么

从 `探讨/skills/research/framework-selector/SKILL.md` 和相关 v6 技能文件可以看出，模式二已具备一套完整深度研究流程的设计：

- 决策/研究任务会落到临时项目目录，并维护 `meta.yaml`、事实卡、RAG 资料、Agent 结论、综合材料、质量门和输出文件。
- 研究过程包含框架选择、方向确认、事实卡、RAG 池、分析 Agent、安全锚点、战略综合、反方审查、质量门和报告生成。
- 典型产物路径包括 `fact_card/fact_card.md`、`rag/_search_index.json`、`agents/Agent-*/factor_conclusion.json`、`agents/Safety-Anchor/blind_spot_report.json`、`agents/Devils-Advocate/internal_memo.json`、`synthesis/strategy_synthesis.md`、`output/executive_summary.tex`、`output/paper.tex` 和 `output/paper.pdf`。
- `探讨/skills/research/full-mode-composer/SKILL.md` 定义了简报和详细报告的生成前置条件，要求检查事实卡、方向、至少一个因子结论和综合文件，缺失时不得直接生成完整报告。
- `探讨/skills/research/deliverable-standards/SKILL.md` 提供交付物标准，强调金字塔原则、行动标题、SCR、MECE、数据优先和可信度标注。

`framework-selector` 当前版本已明确记录多 Agent、RAG 池、Coordinator、失败恢复、战略综合、参谋长、魔鬼审查反馈弧和三阶段质检；`v6-rag-pool/scripts/pool_manager.py` 已提供优先级、并发、重试、L1-L6 分级、相关性过滤、去重和 `infra_failure` 检测。因此 Ludus 的首个方法包不是从空白 Prompt 开始，而是把已经沉淀和灰测过的协议编译成可版本化 manifest、schema、Prompt、quality gates 和 eval fixtures。

这些资产说明：Ludus 的“深度决策报告模式”不需要从零设计分析链路。Alpha 应吸收其结构化产物和质量门，但用 Web 产品需要的 `DecisionCase`、`AnalysisCharter`、`AnalysisRun` 和报告对象重组。

## 输入材料和最终输出

模式二的输入材料可以抽象为：

- 原始决策问题。
- 用户目标和约束。
- 事实卡和补充事实。
- RAG 检索任务和来源结果。
- 分析因子和框架选择。
- 反方审查与安全锚点。

模式二的最终输出可以映射为：

| 现有产物 | Ludus 对象 |
|---|---|
| `fact_card/fact_card.md` | `DossierEntry`、`EvidenceItem`、`CaseSummary` 与冻结快照 |
| `rag/_search_index.json` | `EvidenceItem` 与来源索引 |
| `agents/Agent-*/factor_conclusion.json` | `ResearchPacket`、`Judgment`、`Assumption` |
| `agents/Safety-Anchor/blind_spot_report.json` | `Challenge`、`UnknownItem`、`RiskItem` |
| `agents/Devils-Advocate/internal_memo.json` | `CounterArgument`、`VulnerableAssumption` |
| `synthesis/strategy_synthesis.md` | `ReportArtifact.structuredContent`、`Recommendation` |
| `output/executive_summary.tex` | `BriefArtifact` |
| `output/paper.tex`、`output/paper.pdf` | `ReportArtifact` 与 `ExportArtifact` |

## 简报、详细报告、PDF、HTML 的生成方式

`探讨/skills/research/full-mode-composer/SKILL.md` 显示模式二偏向 LaTeX 生成：先写 `output/executive_summary.tex`，再生成 `output/paper.tex` 和 PDF。`探讨/templates/01_research_report/template.html` 又说明 HTML 模板资产已经存在。

Ludus P0 的落地策略：

- 保留“简报与详细报告来自同一个结构化报告对象”的原则。
- 不把 LaTeX 编译作为黑客松 P0 的硬依赖，优先用 HTML 模板加 Playwright 打印 PDF。
- 若现场环境已有 Tectonic 或 LaTeX 运行时，可把 `template.tex` 作为 P1 或演示增强。
- 报告生成前仍保留模式二的完整性检查：事实、证据、至少一个因子结论、综合建议、反方审查和引用列表缺一不可。

## 提示词、脚本、模型调用、搜索和引用链路

`探讨/skills/research/v6-rag-pool/SKILL.md` 给出共享 RAG 池设计：请求包含 `query_id`、提交 Agent、优先级、查询、关键词、最大来源数和时间戳；响应包含标题、摘要、URL、来源域、来源等级、偏向、相关度和检索时间。

这对 Ludus 的影响：

- `EvidenceItem` 必须保留 `sourceGrade`、`retrievedAt`、`relevance`、`bias` 和 `claimIds`。
- 研究任务不应让每个 Agent 随意搜索，而应通过统一工具或任务队列提交检索请求。
- 生成报告时，引用链路应从报告段落回到 `EvidenceItem`，而不是只在末尾列链接。

`探讨/skills/research/v6-analysis-agent/SKILL.md` 的因子结论结构提供了 Alpha 的研究包格式：`factor`、`framework_used`、`conclusion`、`confidence`、`direction`、`key_evidence`、`tdd_discards`、`remaining_gaps` 和 `disclaimer`。

## Hermes 的结构与可采纳机制

Hermes 是一个 Python Agent 系统，包含 CLI、Gateway、工具注册、会话状态、上下文压缩和子任务委派。与 Ludus 相关的本地文件包括：

- `hermes-agent-hermes-hermes-a8a19433/run_agent.py`
- `hermes-agent-hermes-hermes-a8a19433/model_tools.py`
- `hermes-agent-hermes-hermes-a8a19433/tools/registry.py`
- `hermes-agent-hermes-hermes-a8a19433/hermes_state.py`
- `hermes-agent-hermes-hermes-a8a19433/agent/context_compressor.py`
- `hermes-agent-hermes-hermes-a8a19433/agent/skill_utils.py`
- `hermes-agent-hermes-hermes-a8a19433/agent/skill_commands.py`
- `hermes-agent-hermes-hermes-a8a19433/tools/delegate_tool.py`
- `hermes-agent-hermes-hermes-a8a19433/tools/mcp_tool.py`
- `hermes-agent-hermes-hermes-a8a19433/tools/mixture_of_agents_tool.py`
- `hermes-agent-hermes-hermes-a8a19433/gateway/session.py`

从 `hermes-agent-hermes-hermes-a8a19433/AGENTS.md` 可确认：

- `run_agent.py` 的 `AIAgent` 是核心对话循环。
- `model_tools.py` 负责工具发现、工具定义解析和函数调用分发。
- `tools/registry.py` 是中央工具注册表，工具文件在导入时注册 schema、handler 和可用性检查。
- `hermes_state.py` 使用 SQLite 保存会话和消息，并带 FTS5 搜索。
- `agent/context_compressor.py` 负责自动上下文压缩。
- `tools/delegate_tool.py` 提供子 Agent 委派，限制并发、深度和可用工具。
- `tools/mcp_tool.py` 支持 stdio 与 Streamable HTTP、schema 转换、命名空间、动态 tools/list_changed、超时、错误清洗和连接生命周期。
- `agent/skill_utils.py` 与 Skill 工具实现 frontmatter、目录发现、按需查看和注入。
- `tools/mixture_of_agents_tool.py` 实现并行参考响应与聚合，但其模型自输出不能直接作为正确概率。
- `gateway/session.py` 支持消息平台会话持久化。

## Hermes 思路如何进入 Ludus

Ludus 不需要复刻 Hermes 的 CLI 或多平台消息网关，但需要吸收以下机制：

| Hermes 文件依据 | Ludus 中的设计落点 |
|---|---|
| `run_agent.py` | Web Worker 中的任务循环、迭代预算、工具调用、错误恢复和状态回调 |
| `model_tools.py` | 决策工具注册与可用性过滤，例如搜索、报告渲染、PDF 导出、沙盘生成 |
| `tools/registry.py` | `ToolRegistry` 模式，所有工具返回结构化 JSON，失败时返回可机器处理错误 |
| `hermes_state.py` | 借鉴持久会话思想；Ludus 的领域事件、消息和 AnalysisRun 统一写入 Postgres，SQLite 不承担正式产品状态 |
| `agent/context_compressor.py` | 对长对话生成 `CaseSummary`，保护关键事实、最近上下文和工具调用一致性 |
| `tools/delegate_tool.py` | 少量受限 Worker：Research、Critic、Synthesis、Validation，父任务只接收结构化摘要 |
| `tools/mcp_tool.py` | 借鉴 schema 转换、工具名前缀、超时、错误清洗、动态刷新和连接生命周期；P0 不开放任意 MCP URL/stdio/npx |
| `agent/skill_utils.py` / `agent/skill_commands.py` | Method/Skill Loader 的 frontmatter、发现、版本元数据和按需加载 |
| `tools/mixture_of_agents_tool.py` | 借鉴并行视角与聚合结构；正式结论仍由方法包角色、证据和质量门约束 |
| `gateway/session.py` | 会话模型、事件流和前端进度更新，P0 使用 SSE |

## Open WebUI 的 Web 交互与可采纳机制

Open WebUI 0.10.2 已实现通用聊天产品中的长任务和工具交互。Ludus 不 fork 其代码库，也不复制品牌界面，而是重新实现以下经过验证的交互模式：

| Open WebUI 文件依据 | Ludus 中的设计落点 |
|---|---|
| `src/lib/components/chat/Chat.svelte` | message-scoped 事件处理、`statusHistory`、任务 ID、取消、确认输入、来源/引用事件和断线协调 |
| `src/lib/components/common/ToolCallDisplay.svelte` | Agent 工具调用的运行/完成/错误状态、折叠详情和结果查看 |
| `src/lib/components/chat/Messages/Citations.svelte` | Evidence Drawer、来源列表和命题引用跳转 |
| `src/lib/components/chat/Messages/ResponseMessage/TaskList.svelte` | AnalysisRun 阶段、子任务和检索任务的可见列表 |
| `backend/open_webui/events.py` | 类型化事件定义和安全元数据思想 |
| `backend/open_webui/utils/mcp/client.py` | Streamable HTTP MCP 连接、工具 schema、调用与资源读取的参考实现 |

Ludus 的差异在于：聊天消息不是正式决策状态源；Agent 事件必须投影到 `AnalysisRun`；证据必须经过信息质量门；正式任务使用持久化事件和 SSE/`Last-Event-ID`，而不是只依赖浏览器 Socket 会话。

## Hackathon Prototype 与完整 MVP 仍需实现的产品能力

第一版方法源已经就绪，但参考资产不是可运行应用。72 小时只实现 `12-72-hour-execution-plan.md` 冻结的 Hackathon Prototype Slice：

- `DecisionCase`、Workspace/UserSession/Membership/capability 与版本机制；
- pre-run/run-frozen `SourceRecord/SourceSpan`、AnalysisCharter、AnalysisRun、事件、V1–V9 与 no-run-no-report；
- 从研究产物到最小结构化报告、system option/abstain、SignoffPayload 和 append-only DecisionRecord；
- 可重放、可解释且 fail-closed 的最小 SimulationRun；
- Look V7 五工作区：问题 `workspace`、证据 `analysis`、判断 `report`、推演 `sandbox`、决定 `decision`，以及 Project Drawer、empty view 和 Review dialog；
- `fixtures/spherical-robot/seed|external|expected` 三段式预置案例；运行时只可加载 `seed` 和用户明确启用的 `external`，`expected` 只供验证脚本比较。

完整 HTML/PDF、五透镜专用 UI、完整图审阅/分支/比较/回滚、BYOK UI、完整 Review 和十主题全部精修属于完整 MVP 或 Prototype stretch，不能据参考资产存在就压回 72 小时承诺。

## 复用强度边界

`探讨` 属于强内容资产复用，首版 `ways` 已落盘；Hermes 属于小型纯函数抽取与运行机制重写；Open WebUI 属于交互行为和测试范式重写。Next.js、FastAPI 领域服务、Postgres 模型、Worker、SSE、因果引擎和大部分 React UI 仍是 Ludus 原生实现。执行计划不得把“参考了成熟资产”解释为“已有应用只需换壳”。

## 关键判断

`探讨` 已经沉淀了首个方法论和多 Agent 研究协议，并已形成 `ways/hardtech-market-direction/1.1.0` 第一版源包；Hermes 已经实现了 Agent 循环、工具注册、受限委派、MCP、Skill、状态与中断；Open WebUI 已经验证了 Web 端长任务、工具、引用和确认交互。Ludus Alpha 的工作量应按“安装、适配、领域重组和验证”估算，而不是按从零搭建三个同类基础系统估算。真正需要新建的是 Ludus 的领域模型、正式质量合同、可追溯投影、因果沙盘和跨模式闭环。

这里的“复用”有三种不同含义：`探讨` 的自有方法内容经来源审计后 **Extract & adapt** 到 ways；Hermes 的 MIT 纯解析/注册/schema 清洗函数带署名 **Extract & adapt**，状态化运行机制按已核验行为 **Reimplement**；Open WebUI 统一按已核验行为 **Reimplement**。P0 不 fork、不整体复制，也不把全部 Skill 塞入一次 full Run。法律与工程边界以文档 21 为准。
