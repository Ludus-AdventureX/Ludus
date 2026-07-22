# 15. 开源项目参考

## 授权记录原则

用户已确认三个本地资产具备二次开发授权，但发布前仍必须在 `docs/asset-authorizations/` 保存非敏感授权摘要：授权主体、资产、允许行为、品牌处理、分发范围、有效期、审批引用和责任人。摘要未落盘前继续执行 21 号文档的最保守许可策略。

## 使用原则

本地资产的逐文件判定、许可证/NOTICE、Ludus 目标文件和验收统一见 `21-existing-asset-reuse-and-conversion.md`。本章只保留来源索引和外部项目参考，不维护第二份转换账本。

Ludus 首先核验本地 Hermes 的工程机制：registry、Skill frontmatter 解析和 MCP schema/错误清洗中的纯函数按 MIT **Extract & adapt**，受限委派和 context compression 等状态化机制按验证行为重写。`run_agent.py`、`hermes_state.py`、CLI/Gateway 和通用 MCP runtime 不直接采用。外部开源项目只作为成熟机制参考，P0 不为追求架构完整性引入重依赖。

**待验证：** 外部链接按项目官方公开仓库列出，但这些项目未在本地拉取源码逐行审查；具体 API、版本兼容性和许可证必须在开发落地前核验。

本地三个参考资产已经存在并完成针对性源码检查，采用优先级高于外部项目：

| 本地资产 | 直接提炼/适配 | 重写适配 | 不采用 |
|---|---|---|---|
| `探讨` | **Extract & adapt**：v6.12.x 方法阶段、RAG task/schema、来源分级和质量闭环 | 已沉淀为 `ways/hardtech-market-direction/1.1.0`；31 个研究 Skill 按文档 21 逐项处置 | 临时 Markdown 状态、全部 Skill 动态加载、`.env`、`auth.json`、整体复制 `config.yaml` |
| Hermes Agent | **Extract & adapt**：registry、Skill frontmatter 解析、schema/错误清洗纯函数；**Reimplement from verified behavior**：受限委派、context compression | 保留 MIT/精确来源后适配为原生 async Worker、Workspace 权限、Postgres 状态、Ludus 角色和预算 | CLI、Gateway、SQLite、同步单体循环、通用高权限工具、任意 MCP runtime |
| Open WebUI 0.10.2 | **Reimplement from verified behavior**：status/task/tool/citation/confirmation/event 语义 | Next.js/React、SSE 历史重放、Ludus 信息架构 | fork、源码/UI/CSS/品牌复制、Svelte 运行时、MCP client 和完整依赖树 |

## 本地来源许可证与 NOTICE

| 来源 | 本地依据 | P0 法律边界 | 发布记录 |
|---|---|---|---|
| `探讨` | 未发现根 `LICENSE` | 只在产品方确认拥有的范围内转换；第三方引用不自动获得再发布许可 | 方法来源写入 `ways/.../SOURCES.md` |
| Hermes Agent | `LICENSE`，MIT，Copyright 2025 Nous Research | 允许抽取边界清楚的纯函数；必须保留 MIT 文本、版权和精确函数来源，状态化胶水仍行为重写 | `THIRD_PARTY_NOTICES.md` 记录版本、路径、函数和 MIT |
| Open WebUI 0.10.2 | `LICENSE`、`LICENSE_NOTICE`、`LICENSE_HISTORY` | 多许可证且含品牌限制；未完成逐文件提交 provenance 前禁止复制代码和界面 | `THIRD_PARTY_NOTICES.md` 记录三个许可文件；源码复制需单独法律复核 |

DeepSeek V4 Pro 是 P0 默认基座模型，不是本章要复刻或内嵌的开源工程。接入只走 DeepSeek 官方 API，默认 `MODEL_BASE_URL=https://api.deepseek.com`、`MODEL_NAME=deepseek-v4-pro`，并封装在 OpenAI-compatible `ModelProvider` 后。四类运行时角色可以共用该模型，但上下文和产物必须隔离；官方 `reasoning_content` 只保留在单次工具调用链内存中，不进入 Ludus 的持久审计链。

## 本地 Hermes 机制

| 机制 | 本地依据 | 判定 | Ludus 应用 |
|---|---|---|---|
| Agent 主循环 | `hermes-agent-hermes-hermes-a8a19433/run_agent.py` | Do not use | 不复制单体循环；由 `AnalysisRun` state machine 与独立 Worker 实现 |
| 工具注册 | `hermes-agent-hermes-hermes-a8a19433/tools/registry.py` | Extract & adapt | 带 MIT 署名抽取注册/定义/availability cache，适配 Pydantic/async/Workspace-scoped `agents/tool_registry.py` |
| 工具发现 | `hermes-agent-hermes-hermes-a8a19433/model_tools.py` | Reference only | 只参考可用性过滤；不复制同步 bridge 或全局工具表 |
| 状态持久化 | `hermes-agent-hermes-hermes-a8a19433/hermes_state.py` | Do not use | SQLite 不进入正式路径；Postgres 保存消息、事件和 Run |
| 上下文压缩 | `hermes-agent-hermes-hermes-a8a19433/agent/context_compressor.py` | Reimplement from verified behavior | 领域化 `CaseSummary`，保护冻结字段且不保存隐藏推理 |
| 子任务边界 | `hermes-agent-hermes-hermes-a8a19433/tools/delegate_tool.py` | Reimplement from verified behavior | 四类 Worker，权限取交集，限制并发、深度和预算 |
| MCP 生命周期 | `hermes-agent-hermes-hermes-a8a19433/tools/mcp_tool.py` | Extract & adapt（纯 schema/清洗函数）/ Reference only（runtime） | 复用 schema 规范化与错误清洗；P0 只做直接 HTTP Provider Adapter，不运行 MCP runtime |
| Skill 发现 | `hermes-agent-hermes-hermes-a8a19433/agent/skill_utils.py`、`agent/skill_commands.py` | Extract & adapt（纯解析函数） | 带 MIT 署名抽取 YAML/frontmatter/条件解析，适配固定根、SemVer、内容哈希和发布状态 |
| 并行视角聚合 | `hermes-agent-hermes-hermes-a8a19433/tools/mixture_of_agents_tool.py` | Reference only | 只借鉴失败隔离；不暴露 MoA 工具或模型投票 |

## Open WebUI 交互机制

| 本地文件 | 判定 | 已验证机制 | Ludus 落点 |
|---|---|---|---|
| `open-webui-0.10.2/src/lib/components/chat/Chat.svelte` | Reimplement from verified behavior | message-scoped event、`statusHistory`、取消、确认和重连 | React 工作台与 canonical AnalysisRun 投影 |
| `open-webui-0.10.2/src/lib/components/common/ToolCallDisplay.svelte` | Reimplement from verified behavior | 工具运行/完成/错误与折叠详情 | `ToolCallDisplay.tsx` 安全摘要 |
| `open-webui-0.10.2/src/lib/components/chat/Messages/Citations.svelte` | Reimplement from verified behavior | 引用归并、编号和来源详情 | Evidence Drawer 与 Claim/Evidence 溯源 |
| `open-webui-0.10.2/src/lib/components/chat/Messages/ResponseMessage/TaskList.svelte` | Reimplement from verified behavior | 后台任务状态与折叠 | canonical Agent/检索任务列表 |
| `open-webui-0.10.2/backend/open_webui/events.py` | Reimplement from verified behavior | 类型化 event envelope 和 sink 错误隔离 | append-only Ludus 事件与 SSE replay |
| `open-webui-0.10.2/backend/open_webui/utils/mcp/client.py` | Reference only（P1） | AsyncExitStack、initialize timeout、幂等 disconnect 等 MCP 生命周期 | 无 P0 runtime；P1 仅按行为自行实现 |

## Agent 编排和持久化任务

| 项目 | 解决的问题 | 可借鉴机制 | 放入模块 | 72 小时采用深度 | 链接 |
|---|---|---|---|---|---|
| LangGraph | 有状态 Agent 图和可恢复执行 | 节点/边表达任务阶段，状态显式传递 | `Research Pipeline`、`Agent Workflow` | 不直接接入；借鉴状态图和 checkpoint 概念 | [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) |
| Temporal | 长时任务、重试、幂等和可靠工作流 | activity、workflow、retry policy、idempotency | `Analysis Orchestrator` | P0 不引入；把重试和恢复语义写入 `analysis_runs` | [temporalio/temporal](https://github.com/temporalio/temporal) |
| BullMQ | Node 队列和后台任务 | job、retry、backoff、progress | `Analysis Orchestrator` | P0 不引入；未来只有已采用 Redis 时才评估 | [taskforcesh/bullmq](https://github.com/taskforcesh/bullmq) |
| XState | 前端和后端状态机 | 明确状态、事件、guard、transition | `AnalysisRun` 状态机、前端长任务 UI | 可局部用状态机思想；不强制安装 | [statelyai/xstate](https://github.com/statelyai/xstate) |

## 深度研究与引用

| 项目 | 解决的问题 | 可借鉴机制 | 放入模块 | 72 小时采用深度 | 链接 |
|---|---|---|---|---|---|
| LlamaIndex | 文档索引、检索和引用节点 | node metadata、source attribution、retrieval pipeline | `Evidence Service`、`Research Worker` | P0 不建复杂索引；借鉴 metadata 和 citation 结构 | [run-llama/llama_index](https://github.com/run-llama/llama_index) |
| Haystack | RAG 管线和组件化检索 | pipeline component、retriever、ranker、generator | `Research Pipeline` | 不直接接入；借鉴检索管线分层 | [deepset-ai/haystack](https://github.com/deepset-ai/haystack) |
| Ragas | RAG 质量评估 | faithfulness、answer relevancy、context precision | `Report Validation` | P1 引入；P0 手写引用和质量门检查 | [explodinggradients/ragas](https://github.com/explodinggradients/ragas) |

## Web 数据与 MCP

免费额度于 2026-07-12 从官方页面核对，开发接入与演示前必须复核，不能写成永久产品承诺。

| 服务 | 主要能力 | 免费额度 | P0 用法 | 官方依据 |
|---|---|---|---|---|
| Exa | Web 搜索、语义发现、论文和公司资料 | 每月最多 20,000 次请求 | 默认 `search_web`，先找候选来源 | [定价](https://exa.ai/pricing) / [MCP](https://github.com/exa-labs/exa-mcp-server) |
| Firecrawl | Search、Scrape、Crawl、Map、文件解析 | 每月 1,000 credits；远程 MCP 有免 Key 限速模式 | 默认 `fetch_url`，只抓高价值页面 | [定价](https://www.firecrawl.dev/pricing) / [MCP](https://docs.firecrawl.dev/mcp-server) |
| Tavily | Search、Extract、Map、Crawl | 每月 1,000 API credits，无需信用卡 | Exa 失败或额度不足时备用 | [定价](https://www.tavily.com/pricing) / [MCP](https://docs.tavily.com/documentation/mcp) |

三者在 P0 通过直接 HTTP API Provider Adapter 接入，Agent 只看到 Ludus 的稳定只读工具。官方 MCP 链接只作为 P1 评估依据；P0 不运行远程 MCP 协议，用户添加来源仅支持审核目录和 BYOK，不接受任意 MCP 地址或第三方进程。

## 知识检索

| 项目 | 解决的问题 | 可借鉴机制 | 放入模块 | 72 小时采用深度 | 链接 |
|---|---|---|---|---|---|
| Qdrant | 向量检索和过滤 | payload filter、collection、向量相似度 | `Evidence Store` | P0 不引入；Postgres 足够，P1 用于历史案例检索 | [qdrant/qdrant](https://github.com/qdrant/qdrant) |
| Chroma | 本地向量数据库 | 本地集合、embedding 检索 | `Evidence Store` | P0 不引入；仅作为 P1 替代方案评估 | [chroma-core/chroma](https://github.com/chroma-core/chroma) |
| pgvector | Postgres 向量扩展 | SQL 内向量检索和 metadata join | `Evidence Store` | P0 不引入；P1 可在现有 Postgres 中增加历史决策检索 | [pgvector/pgvector](https://github.com/pgvector/pgvector) |

## 因果图和流程图编辑

| 项目 | 解决的问题 | 可借鉴机制 | 放入模块 | 72 小时采用深度 | 链接 |
|---|---|---|---|---|---|
| React Flow / xyflow | 浏览器节点和边编辑 | 节点拖拽、边连接、inspector、layout | `Simulation UI` | P0 直接采用，支撑沙盘画布 | [xyflow/xyflow](https://github.com/xyflow/xyflow) |
| Mermaid | 文档和报告中的图表 | 文本生成流程图、时序图、状态图 | 文档、报告附录 | P0 用于文档和可选报告图，不用于交互沙盘 | [mermaid-js/mermaid](https://github.com/mermaid-js/mermaid) |
| ELK.js | 自动图布局 | layered layout、节点布局计算 | `Simulation UI` | P1 引入；P0 先用简单布局或 React Flow 自动定位 | [kieler/elkjs](https://github.com/kieler/elkjs) |

## HTML/PDF 报告

| 项目 | 解决的问题 | 可借鉴机制 | 放入模块 | 72 小时采用深度 | 链接 |
|---|---|---|---|---|---|
| Playwright | 浏览器自动化和 PDF 导出 | headless Chromium、print CSS、截图 | `Report Renderer` | P0 直接采用 HTML -> PDF | [microsoft/playwright](https://github.com/microsoft/playwright) |
| md-to-pdf | Markdown 到 PDF | Markdown 渲染和 PDF 管线 | `Report Renderer` | 可作为备选；P0 优先 HTML 模板 | [simonhaenisch/md-to-pdf](https://github.com/simonhaenisch/md-to-pdf) |
| WeasyPrint | HTML/CSS 到 PDF | print CSS 和服务端 PDF | `Report Renderer` | Python 环境已稳定时可评估；P0 选 Playwright | [Kozea/WeasyPrint](https://github.com/Kozea/WeasyPrint) |

## 可观测性和评估

| 项目 | 解决的问题 | 可借鉴机制 | 放入模块 | 72 小时采用深度 | 链接 |
|---|---|---|---|---|---|
| OpenTelemetry JS | Trace、metric、log 标准 | trace id、span、exporter | `Observability` | P0 先用 `domain_events`/`analysis_events`；P1 接入 OTel | [open-telemetry/opentelemetry-js](https://github.com/open-telemetry/opentelemetry-js) |
| Langfuse | LLM 调用观测和评估 | prompt trace、generation、score | `LLM Observability` | P1 接入；P0 只记录任务事件和模型错误摘要 | [langfuse/langfuse](https://github.com/langfuse/langfuse) |
| Phoenix | LLM/RAG 可观测和评估 | tracing、retrieval eval、experiment | `Report Validation`、`RAG Eval` | P1 做报告和检索评估；P0 不引入 | [Arize-ai/phoenix](https://github.com/Arize-ai/phoenix) |

## 采用边界

P0 直接采用的外部依赖应限制为：Next.js/React/TypeScript、FastAPI/Pydantic/SQLAlchemy、Postgres、`@xyflow/react`、Playwright、DeepSeek 官方 API 的 OpenAI-compatible Adapter、Exa/Firecrawl/Tavily Provider Adapter 和基础 Web/Python 工具链。其余项目作为机制参考或 P1 评估对象，避免 72 小时内把架构复杂度变成开发风险。
