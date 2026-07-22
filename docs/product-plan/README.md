# Ludus 产品与工程蓝图

> **Repository canonical path (2026-07-22):** `docs/product-plan`. When this plan was vendored from the sibling workspace into the Private Git repository, only repository-relative paths and cross-directory links were normalized; product, data, API, agent, security, and acceptance contracts were not changed.

**Ludus — 预见未来，保障您的事业。**

Ludus 是面向实际决策人的企业战略决策沙盒。这里的“预见未来”不是预测一个确定结果，而是提前暴露关键假设、因果路径、风险、可控杠杆和建议翻转条件。系统不替代人做决定，而是把决策过程沉淀为一个可追溯、可质疑、可调整、可推演、可回滚、可复盘的版本化 `DecisionCase`。

本目录同时定义 72 小时 Hackathon Prototype Slice 与完整 MVP 的可执行产品、技术和工程合同；72 小时不再等同于完整 MVP。方案参考三个本地资产：`探讨` 的深度研究与质量体系、`hermes-agent-hermes-hermes-a8a19433` 的 Agent 运行时机制，以及 `open-webui-0.10.2` 的认证、聊天、文件、引用和连接器产品模式。

`17-product-design-v2.md` 至 `26-decision-os-invariants-and-agent-engine-contract.md` 记录了截至 2026-07-21 确认的产品总设计、实施、数据源、方法路由、资产转换、合同安全、容量调度、Look V7 前端视觉/交互与决策操作系统工程不变量。本目录已经按这些合同回写其他领域文档；任何文档出现冲突都视为缺陷，不能依靠“以后面的文档为准”继续开发。

## 统一规范

本目录所有文档统一遵守以下规范，不再保留并行名称、并行演示案例或并行主技术栈：

- 产品展示名统一为 **Ludus**，中文定位为“企业战略决策沙盒”；仓库、目录、包名和配置标识继续使用 `decision-lab`。展示品牌与技术标识是两个稳定命名空间。
- P0 唯一预置案例为“资金与研发资源有限的球形机器人项目，应该优先进入救援市场，还是家庭服务市场？”。其他案例只能作为自由输入示例，不参与 P0 完成线和金路径验收。
- P0 唯一主技术栈为 Next.js 15/React 19/TypeScript 前端、FastAPI/Python Worker、Postgres 16/SQLAlchemy 2、数据库任务队列、SSE、`@xyflow/react` 和 Playwright PDF。
- 正式产品数据模型与异步执行统一采用 Postgres 16、SQLAlchemy 2 和 Python Worker；单元测试或显式离线演示可以使用隔离 fixture，但不得形成第二套业务持久化契约。
- 正常金路径优先使用真实模型与 Exa/Firecrawl/Tavily；只有审核 fallback 与可用缓存仍不能完成金路径时，才由用户显式启用 deterministic fixture，并持续标记为 `fixture`，不得冒充实时结果。
- P0 默认 `MODEL_PROVIDER=deepseek`、`MODEL_BASE_URL=https://api.deepseek.com`、`MODEL_NAME=deepseek-v4-pro`，产品显示名为 DeepSeek V4 Pro；三者仍可由环境覆盖。每次真实调用保存 provider、请求 model id 与 API 返回版本/模型标识，不把供应商绑定写进业务领域层。
- P0 合同生成固定为 `06/10` 语义合同 -> FastAPI/Pydantic -> OpenAPI snapshot -> `openapi-typescript` 生成类型 -> `openapi-fetch` Web client；生成物只读，Web 不得手写平行 API DTO。
- Cookie mutation 必须通过 CSRF 校验；所有服务端远程 URL 请求必须通过 SSRF 校验；登录、高成本分析、上传和连接器必须有明确限流、大小与安全响应头。
- 多智能体执行以 `agent-work-manifest.yaml` 为机器可调度清单，以 `23-multi-agent-capacity-execution-plan.md` 选择 3/4/6 槽位档；QA 只提交缺陷 handoff，源码修复返回唯一 owner。
- `ways/hardtech-market-direction/1.1.0` 是首版方法论唯一源资产；通过校验和安装后生成 `method-packs/hardtech-market-direction/1.1.0` 运行时产物。开发只修改 `ways`，Router 只消费已发布、哈希一致的 `method-packs`，不得双向手工维护。
- 01-16 提供分领域规格，17 提供产品总设计，18 提供实施顺序，19 提供数据源与发布硬约束，20 提供对话入口和方法路由契约，21 提供现有资产的转换、许可、归属和验收账本，22 提供合同生成与 Web 安全实施方案，23 提供 3/4/6 Agent 容量档，24 提供 Look V7，25/27 是历史开工审计，26 锁定决策操作系统工程不变量，28 记录合同修复完工；`agent-work-manifest.yaml` 是机器调度索引。任何新增决策必须同步检查所有受影响文档，不允许保留平行合同。
- 自定义影响因素是 P0 正式合同：只在完整模型按需出现，先生成候选并由用户审阅，再写入 revision 工作副本；即时结果是不可用于正式决定的 `ExperimentPreview`，正式运行仍要求 immutable confirmed `GraphVersion`。
- Human / Analysis / Unknown 是代码级责任类型，不是配色标签；人类确认与签署、系统分析产物、未知项/假设必须使用不同 actor、权限和 schema。
- Case 决策生命周期固定为 `draft → scoped → ready → running → review → pending_signoff → decided → monitoring`；系统和 Agent 永远不能自动执行 `pending_signoff → decided`。
- 历史 DecisionRecord append-only，修订只能创建 superseding record；没有 qualifying Run 就没有 Report，未通过发布门不得导出、建图或进入签署。
- 正式 Agent Engine 输入为 Case Charter + 冻结材料快照 + 分析深度，输出 Judgment Set + Dissent Record + Draft Recommendation；不是聊天 `messages[]` 循环。
- Domain/API/URL 对 Case 和 AnalysisRun 只使用 `decisionCaseId`、`analysisRunId`；Source 使用 `pre_run | run_frozen`，DeepAnalysis 只返回持久化 ID/hash。
- UserSession 必须可撤销；WorkspaceMembership 投影 `contribute/review/sign/manage_connectors` capability；只有活动人类 signer 可签署完整 `SignoffPayload`。
- Look V7 主工作区固定为问题 `workspace`、证据 `analysis`、判断 `report`、推演 `sandbox`、决定 `decision`；Review 是 dialog/drawer，Project Drawer 负责 Case，公开主题十项且默认 `ink`。

## 产品结论

P0 聚焦一个窄场景：资金与研发资源有限的球形机器人项目，判断优先进入救援市场还是家庭服务市场。这个场景同时需要技术与需求澄清、证据收集、假设分离、选项比较、报告输出和因果推演，能够在 72 小时 Prototype 中展示最窄但真实的价值闭环；完整 MVP 的全部宽度按 108/144 小时或重新估算。

Ludus 的差异化不是“会聊天”或“会写报告”，而是以 Human（人类承诺）、Analysis（系统分析）和 Unknown（已知未知）三类责任语义驱动真实状态机与可追溯记录：

- `DecisionSubjectDossier` 保存主体长期记忆；`DecisionCase` 保存一次正式决策的问题、目标、选项和版本边界。
- 分析、报告和沙盘引用冻结的 Case/档案快照。它们产生的结论只形成候选档案更新，用户确认后才写回。
- 每条关键结论必须区分事实、证据、假设、判断、偏好和未知项。
- 系统展示可审计的命题、来源、冲突、假设、反方审查、因果边和条件化建议，不展示模型不可验证的内部思维过程。
- “可追溯”指每条用户可见命题、证据、方法版本、工具调用摘要、状态变化、因果边和建议均可回到来源，不宣称保存模型的每一步隐藏推理。
- 可信度按证据可用性、命题支撑、假设稳定性、因果关系可信度、战略稳健性和流程质量分别表达；质量门分数只决定交付资格，不是结论正确概率。
- 建议必须带条件、阈值、退出条件、领先指标和复盘日期。

## 核心领域模型

```text
User / UserSession
└── Workspace / WorkspaceMembership
    └── DecisionSubject
        ├── DecisionSubjectDossier
        └── DecisionCase
        ├── MethodRecommendation
        ├── AnalysisCharter
        ├── RunManifest / SourceRecord / SourceSpan
        ├── AnalysisRun
        ├── JudgmentSet / DissentRecord / DraftRecommendation
        ├── StrategicLensArtifact / ValidatorResult
        ├── ReportArtifact / SignoffRequest
        ├── CausalGraph / GraphBranch / SimulationRun
        ├── immutable DecisionRecord
        └── Review / DecisionLifecycleEvent
```

- `Workspace` 是租户和安全边界；`DecisionSubject` 是长期记忆边界；`DecisionCase` 是一次正式决策的聚合根。
- `AnalysisCharter` 只服务 `focused/full`，是不可变的正式分析契约；`AnalysisRun` 是执行该契约的一次持久化运行。
- `quick` 留在对话中，保存为 `QuickAnalysisResult`，不创建 Charter 或正式 Run。
- Case 生命周期为 `draft → scoped → ready → running → review → pending_signoff → decided → monitoring`；异常状态进入 operational status。系统不能自动从 pending_signoff 进入 decided，同一 Case 可保留多次历史 Run，P0 同时最多存在一个活动正式 Run。

## 开工与交付档位结论

截至 2026-07-21，CCR-20260721-003 已把 Source、ID、DeepAnalysis、session/capability、SignoffPayload、abstain、Simulation、Look V7 与 manifest 调度合同收敛为单一基线；逐项关闭证据与验证结果见 `28-contract-repair-completion-audit-20260721.md`。

- **Hackathon Prototype：可以进入开发。** 先做 Task 1/1W 的不计时离线 bootstrap；`gate-0` 通过后，6 Agent/72 小时档才开始计时。
- **完整 MVP：可以进入实施，但不能承诺 72 小时完成。** 使用 4 Agent/108 小时、3 Agent/144 小时或重新估算。
- **live 集成/正式计时：仍受环境 Gate 0 约束。** 2026-07-14 的本机状态仅是历史快照，不代表 2026-07-21 当前环境；必须重新运行 Python/uv、Docker/Postgres、浏览器、合同 drift、Look hash、Ways、secret/safety 配置与真实 provider probe。验证不得读取或输出本机 Key。
- **发布：尚未开始。** 当前只有规划、方法源与合同修复；应用代码、migration、Docker/live provider、完整 E2E 和生产部署仍需实现与验证。

72 小时 Prototype 不可降级的主链路：创建/选择 Case → 日常问答与材料 → pre-run Source → confirmed Charter → frozen Source + AnalysisRun → V1–V9/no-run-no-report → 条件化报告与 option/abstain → 最小可重放 sandbox → 完整 SignoffPayload → 授权人类签署 append-only DecisionRecord。Look V7 五工作区必须存在，但完整五透镜专用 UI、PDF、完整图编辑/分支/比较/回滚、BYOK UI、完整 Review 和十主题全部精修可作为 stretch 或进入完整 MVP。

共同边界：

- Workspace/UserSession/Membership/capability、来源追溯、状态机、质量门、origin mode 和人类签署不能用 fixture 绕过；
- fixture/cached/live 必须真实标记，`expected/` 只用于验证；
- Research/Critic/Synthesis/Validation 是四个编排职责，可以共用 provider 基座但隔离上下文、Prompt、产物、预算和事件；
- 系统可 abstain，永远不能替人进入 `decided`；
- 投资项目批量筛选、多方法包、复杂协作、计费和生产 SaaS 加固不进入当前 Prototype。

## 文档导航

| 文件 | 作用 |
|---|---|
| [01-product-vision.md](01-product-vision.md) | 产品定位、目标用户、价值主张、成功指标 |
| [02-prd-and-user-flows.md](02-prd-and-user-flows.md) | PRD、用户故事、三种模式流程、验收标准 |
| [03-existing-assets-assessment.md](03-existing-assets-assessment.md) | 基于 `探讨` 和 Hermes 的真实资产评估 |
| [04-decision-methodology.md](04-decision-methodology.md) | 5W1H、事实假设分离、论证树、反方审查、复盘协议 |
| [05-system-architecture.md](05-system-architecture.md) | 总体架构、模块边界、关键时序和技术选择 |
| [06-data-model.md](06-data-model.md) | 主体档案、`DecisionCase`、Charter、Run、证据、报告、因果图和版本模型 |
| [07-agent-workflow.md](07-agent-workflow.md) | Agent 状态机、工具调用、人工确认和失败恢复 |
| [08-deep-research-pipeline.md](08-deep-research-pipeline.md) | 现有模式二接入、结构化输入输出、HTML/PDF 生成 |
| [09-simulation-engine.md](09-simulation-engine.md) | 因果图、影响传播、三情景和敏感性分析算法 |
| [10-api-and-events.md](10-api-and-events.md) | 核心 API、事件模型、错误码和示例负载 |
| [11-frontend-spec.md](11-frontend-spec.md) | 信息架构、五个 canonical 主工作区、渐进披露、组件和响应式要求 |
| [12-72-hour-execution-plan.md](12-72-hour-execution-plan.md) | 72 小时 Hackathon Prototype Slice、Gate 0、时间表、依赖与删减边界 |
| [13-testing-and-acceptance.md](13-testing-and-acceptance.md) | 单元、集成、端到端、报告质量和沙盘验收 |
| [14-demo-script.md](14-demo-script.md) | 5 分钟演示剧本、预置案例、自由输入和降级方案 |
| [15-open-source-references.md](15-open-source-references.md) | 可参考开源项目、机制、应用模块和采用深度 |
| [16-post-hackathon-roadmap.md](16-post-hackathon-roadmap.md) | Alpha 到真实试用产品的 2 周、6 周、3 个月路线 |
| [17-product-design-v2.md](17-product-design-v2.md) | 已确认的最新产品设计、权力边界、三模式、质检、学习与 P0 |
| [18-detailed-development-plan.md](18-detailed-development-plan.md) | Prototype/完整 MVP backlog、Task 1W/14W/18A ownership 与详细开发测试计划 |
| [19-mcp-data-sources-and-launch-constraints.md](19-mcp-data-sources-and-launch-constraints.md) | Exa/Firecrawl/Tavily、BYOK、DeepSeek V4 Pro、Web 展示、72 小时与宣传约束 |
| [20-conversation-led-method-routing.md](20-conversation-led-method-routing.md) | 自由对话入口、方法路由、分析深度、Analysis Charter 和非匹配边界 |
| [21-existing-asset-reuse-and-conversion.md](21-existing-asset-reuse-and-conversion.md) | `探讨`、Hermes、Open WebUI 的逐文件复用判定、转换映射、许可与验收 |
| [22-contract-generation-and-security-plan.md](22-contract-generation-and-security-plan.md) | OpenAPI/TypeScript 单向合同链、CCR、CSRF、SSRF、限流与上传安全 |
| [23-multi-agent-capacity-execution-plan.md](23-multi-agent-capacity-execution-plan.md) | 3/4/6 Agent 槽位、阶段、冻结点、handoff 与自动降档 |
| [24-frontend-visual-theme.md](24-frontend-visual-theme.md) | Look V7 五工作区、十主题、默认 `ink`、semantic token 与静态原型转换合同 |
| [25-demo-development-readiness-audit.md](25-demo-development-readiness-audit.md) | 2026-07-16 历史开工审计，已被 28 号完工审计取代 |
| [26-decision-os-invariants-and-agent-engine-contract.md](26-decision-os-invariants-and-agent-engine-contract.md) | Human/Analysis/Unknown、可追溯链、真实生命周期、三条工程红线、Agent Engine 与九验证合同 |
| [27-mvp-and-hackathon-readiness-audit-20260721.md](27-mvp-and-hackathon-readiness-audit-20260721.md) | 合同修复前审计与问题清单，已 superseded |
| [28-contract-repair-completion-audit-20260721.md](28-contract-repair-completion-audit-20260721.md) | 12 项 blocker 关闭证据、验证结果与最终开工结论 |
| [docs/audits/strategy-analyst-recommendation-audit-20260719.md](docs/audits/strategy-analyst-recommendation-audit-20260719.md) | 专业战略分析师建议的逐项审计、资产吸收结论与分期可行性 |
| [docs/contract-changes/CCR-20260721-003.md](docs/contract-changes/CCR-20260721-003.md) | Source/ID/DeepAnalysis/权限/Signoff/abstain/Simulation/Look V7/manifest 的 accepted 合同修复 |
| [docs/contract-changes/CCR-20260719-002.md](docs/contract-changes/CCR-20260719-002.md) | 决策操作系统工程不变量与签署流程的 accepted canonical 变更 |
| [docs/contract-changes/CCR-20260716-001.md](docs/contract-changes/CCR-20260716-001.md) | 自定义影响因素与即时实验预览的 accepted canonical 合同变更 |
| [agent-work-manifest.yaml](agent-work-manifest.yaml) | Task 1–19 及 1W/14W/18A/19A–D 子切片的 owner、依赖、write scope、Gate 0 与调度规则 |
| [templates/contract-change-request.md](templates/contract-change-request.md) | canonical 合同变更申请模板 |
| [templates/agent-handoff.md](templates/agent-handoff.md) | Agent/QA 跨 owner 交接模板 |
| [templates/asset-authorization-summary.yaml](templates/asset-authorization-summary.yaml) | 非敏感二次开发授权摘要模板 |

## 本地资产依据

关键本地依据来自以下已确认存在的路径：

- `探讨/skills/research/framework-selector/SKILL.md`
- `探讨/skills/research/full-mode-composer/SKILL.md`
- `探讨/skills/research/v6-rag-pool/SKILL.md`
- `探讨/skills/research/v6-analysis-agent/SKILL.md`
- `探讨/skills/research/v6-safety-anchor/SKILL.md`
- `探讨/skills/research/v6-strategy-synthesis/SKILL.md`
- `探讨/skills/research/v6-devils-advocate/SKILL.md`
- `探讨/skills/research/v6-pipeline-coordinator/SKILL.md`
- `探讨/skills/research/deliverable-standards/SKILL.md`
- `探讨/skills/research/document-type-selector/SKILL.md`
- `探讨/skills/research/pre-mortem/SKILL.md`
- `探讨/skills/research/scenario-planning/SKILL.md`
- `探讨/skills/research/porter-five-forces/SKILL.md`
- `探讨/skills/research/counterparty-response-matrix/SKILL.md`
- `探讨/skills/research/meadows-leverage-points/SKILL.md`
- `探讨/config.yaml`
- `探讨/SOUL.md`
- `探讨/templates/01_research_report/template.html`
- `探讨/templates/01_research_report/template.tex`
- `hermes-agent-hermes-hermes-a8a19433/run_agent.py`
- `hermes-agent-hermes-hermes-a8a19433/model_tools.py`
- `hermes-agent-hermes-hermes-a8a19433/tools/registry.py`
- `hermes-agent-hermes-hermes-a8a19433/hermes_state.py`
- `hermes-agent-hermes-hermes-a8a19433/agent/context_compressor.py`
- `hermes-agent-hermes-hermes-a8a19433/agent/skill_utils.py`
- `hermes-agent-hermes-hermes-a8a19433/tools/delegate_tool.py`
- `hermes-agent-hermes-hermes-a8a19433/tools/mcp_tool.py`
- `hermes-agent-hermes-hermes-a8a19433/tools/mixture_of_agents_tool.py`
- `hermes-agent-hermes-hermes-a8a19433/gateway/session.py`
- `open-webui-0.10.2/backend/open_webui/models/auths.py`
- `open-webui-0.10.2/backend/open_webui/models/chats.py`
- `open-webui-0.10.2/backend/open_webui/models/files.py`
- `open-webui-0.10.2/backend/open_webui/routers/auths.py`
- `open-webui-0.10.2/src/lib/components/chat/Chat.svelte`
- `open-webui-0.10.2/src/lib/components/chat/Messages/Citations.svelte`
- `open-webui-0.10.2/src/lib/components/common/ToolCallDisplay.svelte`
- `open-webui-0.10.2/src/lib/components/chat/Messages/ResponseMessage/TaskList.svelte`
- `open-webui-0.10.2/backend/open_webui/events.py`

`探讨/.env` 和 `探讨/auth.json` 只属于原运行环境的秘密与认证状态，不是方法资产。任何审计、安装、fixture、镜像、日志和提交都必须显式排除它们；开发者不得为“转换完整性”读取或复制其内容。

## Alpha 完成线

开发按可运行垂直切片推进：先跑通 fixture 驱动但使用真实数据库/状态机的闭环，再接入真实模型和数据源，随后完成报告、沙盘、分支回滚和最终验收。P0 完成线不是“功能很多”，而是每个核心环节均有真实实现，外部服务失败时才明确降级。



