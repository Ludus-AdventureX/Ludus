# 19. MCP 数据源与发布约束

## 文档状态

本文记录截至 2026-07-21（星期二）重新核对的数据获取、模型适配、部署形态和交付约束，并与 CCR-20260721-003 同步。72 小时只适用于 Hackathon Prototype Slice；完整 MVP 使用 108/144 小时档或重新估算。出现冲突时必须停止相关实现并修正文档，不能按日期自行选择合同。

## 已确认决策

- P0 数据获取采用 Exa 搜索、Firecrawl 抓取、Tavily 备用的直接 HTTP API Provider Adapter 组合，不把单一供应商或远程 MCP 协议当作不可替换基础设施。
- 用户可以从审核目录添加 Exa、Firecrawl 或 Tavily，并使用自己的 API Key；P0 不接受任意 MCP 地址、stdio/npx 进程、自定义 OAuth 或写操作。
- P0 首个基座锁定为 DeepSeek 官方 API 的 DeepSeek V4 Pro，默认 `MODEL_PROVIDER=deepseek`、`MODEL_BASE_URL=https://api.deepseek.com`、`MODEL_NAME=deepseek-v4-pro`；这些值仍可由环境覆盖，业务代码只依赖 OpenAI-compatible `ModelProvider`。
- 正常金路径必须优先运行真实模型、Exa、Firecrawl 和必要时的 Tavily。只有在审核过的 provider fallback 与可用缓存仍不能让金路径完成时，才允许用户显式切换 deterministic fixture；它是最坏情况降级，不是默认 Demo 路径，也不要求所有外部服务同时失效。
- 最终部署平台暂不锁定，但交付形态必须是浏览器可访问的 Web 应用，并保留 Docker Compose 本地演示路径。
- 72 小时只承诺 Hackathon Prototype Slice；第 60 小时冻结 Prototype 功能，第 60-72 小时只做验收、阻断修复、部署和展示准备。完整 MVP 不沿用该期限。

## 官方服务、MCP 参考与额度

以下信息于 2026-07-21 从官方定价页、官方文档和官方仓库重新核对。额度、credit 价格和 model availability 都会变化；开发接入、现场演示和上线前必须重新读取官方页面并执行 provider probe，产品界面不得承诺永久免费额度或固定请求数。

| 服务 | P0 职责 | 当前官方计量语义 | 官方 MCP（仅作 P1 评估资料） | P0 状态 |
|---|---|---|---|---|
| Exa | 默认网页搜索、语义发现、论文和公司资料检索 | 按 credits/具体 endpoint 与结果计费；免费 credit 价值可能变化，禁止换算成固定“每月请求数”合同 | `https://mcp.exa.ai/mcp` / 官方 exa-mcp-server | 内置直接 HTTP API，默认搜索 |
| Firecrawl | 指定 URL 抓取、正文清洗、文档解析、有限站点爬取 | 按 plan/credits 计量；官方远程 MCP 配置要求 Firecrawl API key/Authorization，不存在“免 Key P0 依赖” | `https://mcp.firecrawl.dev/v2/mcp` | 内置直接 HTTP API，默认抓取 |
| Tavily | 搜索、提取、Map、Crawl 的备用路径 | 官方 free plan 当前说明每月 1,000 API credits；上线前重新核对 | `https://mcp.tavily.com/mcp` | 内置，默认关闭 |

官方依据：

- Firecrawl 定价：<https://www.firecrawl.dev/pricing>
- Firecrawl MCP：<https://docs.firecrawl.dev/mcp-server>
- Exa 定价：<https://exa.ai/pricing>
- Exa MCP：<https://github.com/exa-labs/exa-mcp-server>
- Tavily 定价：<https://www.tavily.com/pricing>
- Tavily MCP：<https://docs.tavily.com/documentation/mcp>

这些 URL 只用于人类核对；P0 runtime 不动态抓定价页，也不根据文档中的额度自动放宽预算。

## P0 检索路由

Agent 只调用 Ludus 的稳定工具名，不接触供应商专有工具名：

```text
search_web
fetch_url
crawl_site
extract_document
get_source_status
```

这些工具由 P0 的直接 HTTP API Provider Adapter 实现。接口保持 MCP-compatible 的只读能力语义，但不连接或执行官方远程 MCP 服务。

实现不从零设计 MCP 基础行为：参考 Hermes `tools/mcp_tool.py` 的 input schema 规范化、工具名前缀、server/tool 命名空间、超时、错误清洗、连接生命周期和动态工具刷新；参考 Open WebUI `backend/open_webui/utils/mcp/client.py` 的 Streamable HTTP 会话与清理。P0 只提炼这些机制到审核连接器，不开放任意服务器执行。

默认路由：

```text
search_web
→ Exa
→ 失败、无 Key 或额度耗尽时切换 Tavily

fetch_url
→ Firecrawl
→ 失败时使用基础 HTTP 抓取或缓存 RawArtifact

crawl_site
→ Firecrawl
→ 默认关闭，只允许用户确认的域名、页数和深度

extract_document
→ 本地解析优先
→ Firecrawl 作为增强路径
```

成本受控的默认流程是先用 Exa 找到 10–20 个候选来源，去重和初筛后只用 Firecrawl 抓取 3–8 个高价值页面。具体调用数由 Charter budget、实时 provider quota 与本地 Postgres-backed 限流共同约束；禁止依赖免费额度假设或无上限全站爬取。

## 连接器与 BYOK

P0 的“用户添加信息来源”定义为从审核目录添加 HTTP API 连接器，而不是执行 MCP 服务或任意第三方代码。

用户可配置：

- 服务类型：Exa、Firecrawl 或 Tavily。
- 显示名称、启用状态和 Workspace 范围。
- 自有 API Key；凭证只在服务端加密保存。
- 允许的只读工具、域名范围、单次结果数和预算。

所有 Provider endpoint 和检索结果 URL 必须通过 `22-contract-generation-and-security-plan.md` 的 SSRF-safe client：首次解析和每次重定向均校验协议、DNS/IP、端口、私网/metadata 地址、墙钟和响应大小。用户不能提交任意抓取 URL。

P0 禁止：

- 任意远程 MCP URL。
- 本地 stdio、npx 或其他子进程。
- 写工具、浏览器任意操作和外部副作用。
- 在 URL 查询参数、前端状态、事件负载或日志中保存 API Key。
- 跨 Workspace 共享连接器凭证。

P0 密钥存储按 `22-contract-generation-and-security-plan.md` 锁定 AES-256-GCM：每条 credential 使用随机 96-bit nonce，AAD 覆盖 Workspace/Connector/Provider/credential schema version，数据库保存 ciphertext/tag/nonce/masterKeyVersion/掩码。主密钥轮换采用版本化双读与批量 re-encryption；任何响应、SSE、日志、fixture、报告和异常只允许掩码。企业级外部 KMS 和审批流可在活动后实现，但算法、AAD、版本与轮换合同不能延后。

官方或任意 Streamable HTTP MCP、动态 OAuth、用户自定义工具和私有数据连接器在活动后实现。目标接口可提前建模，但不得成为 P0 金路径依赖。

## 证据进入系统的边界

```text
RetrievalTask
→ Connector Registry
→ HTTP API Provider Adapter
→ Immutable RawArtifact
→ Evidence Normalizer
→ Information Quality Gate
→ Evidence Ledger
```

每次调用记录 Workspace、用户、连接器、工具、查询、时间、耗用额度、结果哈希、错误类型和降级状态。外部正文一律标记为 `UNTRUSTED_EVIDENCE`；MCP 只负责获取，不负责判定可信度。

RawArtifact、EvidenceItem 和 connector call 使用单值 `originMode`；AnalysisEvent 使用直接 `originMode` 加 `sourceOriginModes[]`，聚合事件按 `fixture > cached > live` 显示最保守状态；ReportArtifact 与 ExportArtifact 使用去重后的 `originModes[]`：

- `live`：本次运行真实调用获得。
- `cached`：读取此前真实获取且保留内容哈希的材料。
- `fixture`：live/provider fallback/cached 仍不能完成金路径，且用户明确同意后加载的确定性输入。

fixture 只替代外部输入，不替代 Postgres、AnalysisRun、质量门、报告渲染、沙盘算法、图版本和决定保存。

## 可用性与降级

连接器必须实现启动检查和运行时状态：

- `available`
- `missing_credentials`
- `invalid_credentials`
- `rate_limited`
- `quota_exhausted`
- `provider_error`
- `disabled`

Exa 不可用时切换 Tavily；Firecrawl 不可用时使用基础抓取、已有 RawArtifact 或显式缓存证据。所有降级必须写事件并在 UI 标注，预置内容不得冒充实时检索。

## DeepSeek V4 Pro 模型适配

以下官方信息于 2026-07-21 从 <https://api-docs.deepseek.com/> 重新核验：OpenAI-compatible Base URL 为 `https://api.deepseek.com`，P0 默认 model id 为 `deepseek-v4-pro`；`deepseek-chat` 与 `deepseek-reasoner` 将于 2026-07-24 弃用，不得作为新默认值。环境和配置至少提供：

```text
MODEL_PROVIDER=deepseek
MODEL_BASE_URL
MODEL_NAME
MODEL_API_KEY
MODEL_SUPPORTS_STRUCTURED_OUTPUT
MODEL_TIMEOUT_SECONDS
```

DeepSeek V4 Pro 的 thinking 默认启用。官方 JSON Output 可能偶发返回空 `content`，因此 Provider 必须同时做空内容检测和 canonical schema 校验，最多执行一次修复重试；仍失败时进入结构化错误/阻断或由用户显式启用 fixture，禁止解析自由文本兜底。strict tool calls 可用于 thinking 与 non-thinking 调用。

`reasoning_content` 只允许作为 Provider 单次工具调用链中的内存瞬态协议字段，不持久化、不展示、不进入事件、日志、报告或审计。运行审计只保存 provider、请求 model id、API 返回版本/模型标识、用量、延迟和结构化结果状态。

Research/Critic/Synthesis/Validation 是 Ludus 编排的四类角色，可以共用同一 DeepSeek 模型；必须隔离上下文、Prompt、产物、预算、事件和 tool trace，不宣传为四个独立基础模型。开发、单元测试、E2E 和离线演示仍保留 deterministic fixture provider，但 live 验收优先运行真实 DeepSeek。

## 启动 preflight

preflight 还必须验证 OpenAPI/TypeScript drift clean、`deepseek-v4-pro` 的文本/structured output/thinking/tool-call 能力、CSRF secret、连接器 master key 长度、SSRF 安全配置与当前 3/4/6 Agent 容量档。

Gate 0 必须检查 `uv`、Python 3.12、Docker daemon、Postgres 16、`ways/hardtech-market-direction/1.1.0` 校验/安装，以及 `fixtures/spherical-robot/{seed,external,expected}` 边界，并用配置的 Key 对 DeepSeek 默认 model id 做最小 probe。Playwright Chromium 在依赖安装后、首个 6 小时集成门前检查。仅检查环境变量存在不算通过；probe 结果必须记录 provider、请求 model id 和 API 返回版本/模型标识。缺少 Key 时可继续不计时的离线实现；若以 fixture 参加黑客松，必须明确标记为 fixture Prototype，不能宣称 live Gate 通过。完整 MVP 的 live 验收仍要求配置模型和至少一个真实来源 provider probe。

## Web 展示与部署

交付物必须通过浏览器展示，桌面端 1440x900 是现场主视口，390x844 是移动端验收视口。部署平台未定，因此：

- Web、API、Worker 和 Postgres 使用容器化配置。
- `WEB_ORIGIN`、API Origin、Cookie Secure、CORS 和 SSE 代理缓冲通过环境配置切换。
- 保留单机 Docker Compose 演示和断网 fixture 路径。
- 不为某一托管平台引入不可移植的业务依赖。

## 72 小时 Prototype 与完整 MVP

72 小时时间盒使用 `12-72-hour-execution-plan.md` 的六条泳道、至少 6 个持续槽位、独立 worktree、Contract Lead 唯一合同合并权和每 6 小时集成门。它只承诺 Hackathon Prototype Slice：一条球形机器人金路径、真实 Postgres/Run/Source/validator/Signoff/Decision，外部模型/检索允许显式 fixture 降级。

| 时间 | Prototype 完成线 |
|---|---|
| 0–12h | 仓库、合同、auth/session、Workspace、Look V7 shell |
| 12–30h | Case/Source freeze、Charter、AnalysisRun 和 SSE |
| 30–48h | V1–V9、StructuredReport、最小确定性 SimulationRun |
| 48–60h | SignoffPayload、human sign、append-only DecisionRecord |
| 60–72h | E2E、安全、部署、现场彩排和恢复资产 |

60 小时后禁止增加非阻断功能。PDF、完整 lens 专用 UI、完整图编辑/分支、BYOK UI、完整 Review 和额外主题精修是 Prototype stretch；不得删除 SourceSpan、no-run-no-report、来源模式、abstain、human signoff、append-only Decision 或单一合同链。

完整 MVP 切换到 4 Agent/108 小时、3 Agent/144 小时或重新估算，并恢复 `23-multi-agent-capacity-execution-plan.md` 定义的完整 UI、PDF、文件、BYOK、图版本和 Review 范围。

## 宣传与展示交付物

Hackathon Prototype 结束前必须具备：

- 可运行的 Web App 和可重复启动命令。
- 5 分钟现场演示脚本。
- 60-90 秒宣传录屏。
- 至少 6 张无调试信息、无敏感数据的关键界面截图。
- 一页产品说明：问题、用户、差异、金路径和限制。
- 一张系统架构图和一张决策闭环图。
- 完整演示录屏和断网备用方案。
- 演示账号、预置数据、预生成 HTML/PDF 和恢复检查表。

## 完成定义

本文相关工作只有在以下断言同时为真时完成：

- Exa 搜索与 Firecrawl 抓取通过统一只读工具进入 RawArtifact 和 Evidence Ledger。
- 用户能从审核目录添加至少一种 BYOK 信息源，且密钥不出现在前端响应和日志中。
- 连接器无 Key、Key 失效、限流和额度耗尽均有可读状态和显式降级。
- 未配置真实模型时，fixture provider 仍能跑通离线金路径，但不满足 72 小时 Gate 0/live 验收。
- 配置真实服务时，验收优先运行 live 路径；fixture 路径必须显式标记且只替代外部输入。
- Web 金路径、断网路径、5 分钟演示和宣传资产在 72 小时 Prototype 内共同交付；该结论不等于完整 MVP。
