# Ludus / decision-lab 项目开发约束

本文件适用于 `decision-lab` 仓库中的全部代码、配置、测试、脚本、数据、文档和交付物。它把已确认的产品计划转换为开发时必须执行的约束，供人类开发者和 AI 开发代理共同遵守。

## 1. 规则级别与事实来源

- **MUST / MUST NOT**：发布阻断规则，不满足时任务不得标记完成。
- **SHOULD / SHOULD NOT**：默认规则；偏离时必须在变更说明中记录具体理由和影响。
- **MAY**：在产品、架构、安全和已选择的交付档位内可自行选择的实现方式；72 小时只对应 Hackathon Prototype，完整 MVP 使用 108/144 小时或重新估算。
- 权威计划位于 `docs/product-plan/README.md`、活动领域文档 `01` 至 `24`、`26`、合同修复完工审计 `28`、accepted CCR 和 `agent-work-manifest.yaml`。`25/27` 是 superseded 历史审计。本文件是执行索引，不替代领域规格。
- 开始开发前必须先阅读计划 `README.md`、`17-product-design-v2.md`、`18-detailed-development-plan.md`、`19-mcp-data-sources-and-launch-constraints.md`、`20-conversation-led-method-routing.md`、`21-existing-asset-reuse-and-conversion.md`、`22-contract-generation-and-security-plan.md`、`23-multi-agent-capacity-execution-plan.md`、`24-frontend-visual-theme.md`、`26-decision-os-invariants-and-agent-engine-contract.md`、`28-contract-repair-completion-audit-20260721.md`、`docs/contract-changes/CCR-20260721-003.md`、`docs/contract-changes/CCR-20260722-004.md`、`agent-work-manifest.yaml`，以及本次变更对应的领域文档。
- 计划文档之间出现冲突时，必须把它视为文档缺陷，停止受影响实现，先统一所有相关合同；不得按文件编号、修改日期或个人理解自行选一个版本。
- 新的产品或架构决定必须先同步到所有受影响的计划文档，再修改代码、schema、API、事件或 UI。禁止通过实现默默改变已锁定合同。字段、状态、API、事件或错误码变化还必须创建并获批 CCR，再重新生成 OpenAPI/TypeScript 合同。
- 用户最新的明确决定可以改变计划，但必须完成上述文档同步后才成为新的开发依据。
- no_automatic_decided_transition、decision_record_append_only、report_requires_qualifying_run 和 responsibility_semantics_enforced_in_code 是发布阻断规则。

## 2. 产品身份、边界与金路径

- 展示品牌 MUST 使用 **Ludus**，中文定位为“企业战略决策沙盒”，标准标语为“Ludus — 预见未来，保障您的事业。”
- 仓库、目录、包和产品自身的代码/配置标识 MUST 使用 `decision-lab`；需要 snake_case 的数据库标识使用 `decision_lab`。环境变量按领域使用计划中已定义的 `MODEL_*`、`EXA_*` 等名称。不得把展示品牌和技术标识混为一个命名空间。
- Ludus 帮助决策人暴露假设、因果路径、风险、可控杠杆和建议翻转条件；它不替用户做决定，也不宣称精确预测未来。
- P0 首个用户是硬科技初创团队中承担最终责任的决策人。P0 不以多人审批、投票或实时协作为主流程。
- P0 唯一预置案例和端到端验收案例是：资金与研发资源有限的球形机器人项目，应优先进入救援市场还是家庭服务市场。
- 登录后的第一屏 MUST 是可工作的日常问答，不得先展示营销落地页、模板选择页或模板卡片墙。
- 用户只选择 `quick`、`focused`、`full` 三档分析深度；系统负责选择和解释方法包，不把方法论选择责任转嫁给用户。
- P0 必须跑通：日常问答 -> 候选档案确认 -> Charter 确认 -> 正式分析 -> 证据与质量门 -> 条件化报告 -> 因果沙盘 -> 分支/比较/非破坏性回滚 -> 最终决定 -> 结构化 Review 保存与读取。
- P0 不实现真实支付、积分账本、社区市场、方法编辑器、任意方法组合、自动生成方法包、跨行业正式深度分析、DecisionEpisode 历史检索投影、自动训练、跨租户学习、SSO、复杂 RBAC、多人实时协作、项目管理、自动外部监控、完全私有部署或任意 MCP 执行。

## 3. 已锁定技术栈

除非先修改权威计划，否则 P0 MUST 使用以下主栈：

- Node.js 22、pnpm、Next.js 15、React 19、TypeScript、Tailwind CSS。
- TanStack Query 管理服务端状态，Lucide 提供图标，`@xyflow/react` 实现因果沙盘，Zod 用于前端边界校验。
- Python 3.12、uv、FastAPI、Pydantic 2、SQLAlchemy 2、Alembic、httpx、OpenAI SDK、PyYAML。不得使用系统默认的其他 Python 版本创建环境或锁文件。
- PostgreSQL 16 作为正式业务、租户、事件和任务数据源。
- 独立 Python Worker 通过 `SELECT ... FOR UPDATE SKIP LOCKED` 领取 `AnalysisRun`。
- SSE 提供分析进度，事件 ID 单调递增并支持 `Last-Event-ID` 恢复。
- OpenAI-compatible `ModelProvider` 和 deterministic fixture provider；默认 `MODEL_PROVIDER=deepseek`、`MODEL_BASE_URL=https://api.deepseek.com`、`MODEL_NAME=deepseek-v4-pro`，Key 与覆盖值由环境注入。
- Exa 默认搜索、Firecrawl 默认抓取、Tavily 搜索备用，全部置于可替换 Provider Adapter 后。
- `StructuredReport` 先渲染 HTML，再由 Playwright 从同一表示生成 PDF。
- pytest/pytest-asyncio、Vitest/Testing Library、Playwright 组成测试栈。
- Docker Compose 是可重复的本地交付路径；线上托管平台保持可替换。

P0 MUST NOT 引入以下平行主路径：

- Prisma、Node Worker 或 SQLite 主业务持久化。
- Redis、Celery、Temporal、通用向量数据库或第二套任务状态机。
- 远程 MCP 协议运行时、任意 MCP URL、stdio/npx、自定义 OAuth、写工具或通用高权限工具集。
- 绑定某一家模型、检索或托管平台的业务实现。

SQLite 只 MAY 用于隔离单元测试或明确标识的离线 fixture，不得成为正式迁移起点或第二套业务合同。

## 4. 目标仓库与模块边界

仓库 SHOULD 保持以下顶层结构：

```text
decision-lab/
├── apps/web/                 # Next.js Web
├── services/api/             # FastAPI、领域服务、Worker 与迁移
├── ways/                     # 可审阅、唯一可编辑的方法源
├── method-packs/             # 安装生成、已发布且不可变的运行时方法包
├── fixtures/spherical-robot/ # 演示输入、外部 fixture 与期望结果
├── scripts/                  # seed、verify、运维脚本
├── e2e/                      # Playwright 金路径
├── compose.yaml
└── AGENTS.md
```

- FastAPI route MUST 保持薄：输入输出由 Pydantic 校验，业务规则进入 service，持久化进入 repository。
- 领域代码只能依赖稳定能力接口，不能直接依赖 Exa、Firecrawl、Tavily 或具体模型 SDK。
- 前端 API 层必须使用 canonical schema；不得为页面临时创造与后端平行的状态枚举或字段含义。
- 复杂 JSON、YAML、HTML 和模型输出 MUST 使用 schema 或结构化解析器，禁止用字符串切片或松散正则解析正式结构化数据。
- 参考资产按 `21-existing-asset-reuse-and-conversion.md` 的逐文件判定复用，不使用笼统的“全部重写”或“全部复制”。Hermes 是 MIT：标为 `Extract & adapt` 的纯函数/小模块 MAY 在保留版权许可、记录来源和补齐 Ludus 测试后抽取适配；状态化或同步胶水必须重写为 async、Workspace-scoped 实现。Open WebUI 0.10.2 因文件级提交许可来源未建立，P0 只 `Reimplement from verified behavior`，不得复制其源码、品牌受限界面或依赖树。不得嵌入 Hermes 的单体循环、CLI、Gateway、通用工具全集，也不得以临时 Markdown/目录作为生产唯一状态。
- `ways/hardtech-market-direction/1.1.0` 是 P0 唯一方法源，当前 `release_candidate` 不可直接执行。安装器必须校验并计算内容哈希，生成 `method-packs/hardtech-market-direction/1.1.0` 的不可变 `published` 副本；Router/Worker 只读取 `method-packs`，不得运行时回读 `ways` 或 `探讨`，也不得手改已发布包。
- `探讨/config.yaml`、`SOUL.md`、研究 Skill、模板和灰测记录只可按 21 号转换账本导入；`探讨/.env` 与 `探讨/auth.json` MUST NOT 被读取、复制、打包、记录、提交或写入 fixture。
- API、Worker 与 Renderer MUST 使用同一 Docker shared volume 上的 filesystem `ArtifactStore`。稳定接口只暴露 `put/open/stat`，路径位于 `workspaces/{workspaceId}/...`；数据库只保存相对路径、媒体类型、大小和 SHA-256，读取必须经 FastAPI 重新校验 Workspace 所有权，禁止宿主机路径和 volume 静态直链。
- 新依赖必须解决 P0 的明确问题，并先检查现有依赖或标准库是否已经提供能力。不得为活动后设想增加抽象或基础设施。

## 5. 租户、领域模型与版本合同

- `Workspace` 是租户、安全和数据所有权边界；`DecisionSubject` 是长期记忆边界；`DecisionCase` 是一次正式决策的聚合根和版本边界。三者 MUST NOT 合并。Domain、Pydantic、OpenAPI、TypeScript 和 URL 对 Case/AnalysisRun 只使用 `decisionCaseId`、`analysisRunId`；数据库列使用 `decision_case_id`、`analysis_run_id`。
- P0 持久化角色可继续使用 `owner | member`，但服务端 MUST 投影 `contribute | review | sign | manage_connectors` capability；`sign` 只能授予人类用户，不能授予 Worker/Agent。JWT 的 session ID MUST 映射可撤销 `UserSession`；每个敏感请求同时校验活动 session、WorkspaceMembership 与 capability，不能只信任 JWT 声明。P0 不增加复杂权限矩阵，产品主流程仍按单一决策人设计。
- `DecisionMakerProfile` 的个人偏好与 `DecisionSubjectDossier` 的项目事实 MUST 分离，某一主体的结论不得污染其他主体。
- `DecisionSubjectDossier` 保存长期事实、约束、证据、假设和历史决定；`DecisionCase` 保存本次问题、目标、选项和 Case-local 条目，并引用冻结的档案快照。
- 日常对话只生成 `CandidateRevision`。消息、Case 字段和上传材料先规范化为 `pre_run` SourceRecord/SourceSpan；未确认的候选不得进入正式档案、`MethodRouter`、Charter 或 Run。创建 Run 时必须冻结为新的 `run_frozen` Source/Span，保留来源 ID/hash；pre-run 不得携带 AnalysisRun，human input/case snapshot 不得伪造 RawArtifact。
- 分析、报告和沙盘输出只生成候选更新；未获用户采纳前不得静默写回 Case 或长期档案。
- AI 生成内容默认是草稿。确认、修订、否决、过期、正式状态变化、质量门、图版本和最终决定都 MUST 产生 append-only 事件。
- 当前投影 MAY 更新，历史事件、确认快照、输入哈希、方法版本、图版本和产物来源 MUST NOT 覆盖。
- 所有业务实体、repository 查询、文件、连接器、事件、Run、报告、沙盘和导出 MUST 显式按 `workspace_id` 限定。
- 跨 Workspace 访问统一返回 `404`，不得通过 `403`、计数、时序、错误消息或 SSE 泄露资源是否存在。
- schema 变更 MUST 使用 Alembic。不得手工修改共享数据库，不得重写已经应用的 migration。
- 更新版本化对象必须提交 `baseVersion`；冲突返回结构化 `VERSION_CONFLICT`，不得以最后写入覆盖。

核心状态 MUST 严格使用以下枚举，禁止互相借用：

```text
DecisionCase:    draft | scoped | ready | running | review | pending_signoff |
                 decided | monitoring
CaseOperational: ok | blocked | needs_attention | cancelled | reopened | archived
AnalysisCharter: draft | awaiting_confirmation | confirmed | superseded
AnalysisRun:     queued | planning | retrieving | analyzing | criticizing |
                 synthesizing | validating | ready | blocked |
                 needs_attention | cancelled
```

- Case 状态只表达决策生命周期；Run 子状态不能冒充 Case 阶段，但领域服务可以依据已验证的 Run 事件执行 `ready→running` 与 `running→review` 投影。异常状态只进入 `CaseOperationalStatus` 或 Run。
- 已确认 Charter 不可修改。范围、深度、方法、材料或预算变化必须创建替代 draft。
- 替代 draft 未确认时，旧 confirmed Charter 继续有效；只有新 Charter 确认后，旧 Charter 才变为 `superseded` 并记录事件。
- 同一 Case 可以保留多次历史 Run，但 P0 同时最多一个活动正式 Run；数据库必须用约束或等价的原子机制保证。
- 运行中输入 MUST 先生成 append-only `RunInterventionClassification`。只有不改变问题、目标、选项、偏好权重、硬约束定义、材料/连接器范围、预算、方法或分析深度，并且属于来源冲突裁决、既有硬约束确认或已授权 Provider 恢复时，才能追加 `RunResolution` 并恢复到 `lastResumableStage`。
- 任何冻结字段变化都是 amendment：创建 replacement Charter，确认后创建 new Run，旧 Run 进入 `cancelled` 并用 supersession 字段关联；禁止原地修改 confirmed Charter 或使用无类型的通用恢复接口。`blocked` 和 `cancelled` 是终态，`queued` 不是恢复目标。
- `GraphVersion` 使用 `draft | confirmed | archived`，保存后不可变；`ScenarioVersion` 同样按版本不可变。正式 `SimulationRun` 必须精确引用 confirmed `graphVersionId`、`strategyVersionId`、`scenarioVersionId`、`scoreDefinitionId` 和 `engineVersion`。
- `SignoffRequest` 必须内嵌不可变 `SignoffPayload`，其 payloadHash 覆盖 Case/Run/Report/Judgment/Dissent/Graph/Simulation、system option/abstain、人的选择、决定文本、条件、阈值、退出条件、行动项、领先指标、Unknown 和复盘日期；sign body 只接受声明、payloadHash 与一次 nonce。`DecisionRecord` 是授权人类签署瞬间的不可变副本，插入后 MUST NOT UPDATE/DELETE；修订只能创建新记录并填写 `supersedesDecisionRecordId`。
- `Review` MUST 使用 `06-data-model.md` 的 canonical 结构，分别保存建议采纳、执行偏差、决策过程质量、结果质量、外部变化、现实结果、原假设状态、教训和下一轮改变；不得退化为 `outcome + notes`。
- Review 的 `sourceCaseVersion/sourceAnalysisRunId/sourceCausalGraphVersionId/sourceSimulationRunId` 必须由服务端从 `DecisionRecord` 冻结，客户端不得自报；Review 不覆盖原决定，也不得把 SimulationRun 当作现实结果。
- 三条发布红线：Agent/系统不得自动进入 `decided`；历史 DecisionRecord 只能追加修订；没有同 Workspace/Case 的 qualifying Run 就不能创建或发布 Report。
- `pending_signoff → decided` 只能由授权人类通过独立 sign command 执行。Agent 工具表、MCP catalog、fixture 和管理员任务 MUST NOT 暴露 `sign_decision`、`transition_to_decided` 或等价能力。
- `ReportArtifact.analysisRunId` 必须是非空 FK；ready 报告要求 Run ready、九验证 V1-V9 无 blocker、V9 publication authority pass。客户端和 Agent 没有通用 Create Report 工具。
- Human / Analysis / Unknown 必须使用 `ResponsibilityStamp`、不同 actor/权限和可测试 schema。Unknown 不得被低置信度分数吞并。

## 6. 三档分析与方法路由授权

分析等级是服务端授权合同，不只是 UI 文案：

| 等级 | 必需合同 | 允许输出 | 明确禁止 |
|---|---|---|---|
| `quick` | 仅使用已确认档案；会话范围 | `QuickAnalysisResult`、结构化判断、反方、未知项、下一步 | `MethodRouter`、Charter、正式 Run、正式报告、PDF、正式沙盘 |
| `focused` | `exact` 方法匹配；confirmed Charter；`formalAnalysisAllowed=true` | `FocusedResearchResult`、执行简报、结构化建议、证据账本、反方、剩余未知、六维质量画像 | `StructuredReport`、PDF、`simulations/from-report` |
| `full` | `exact` 方法匹配；confirmed Charter；`formalAnalysisAllowed=true`；质量门通过 | 完整 `StructuredReport`、HTML、PDF、正式沙盘 | 未通过质量门时发布正式产物 |

- P0 唯一正式方法包是 `hardtech-market-direction@1.1.0`。Router MUST NOT 返回未发布或不存在的 ID/版本，也不能让模型自评分把 `partial` 提升为 `exact`。
- 方法包的源文件只在 `ways/hardtech-market-direction/1.1.0` 修改；发布后同 ID/版本内容哈希不一致必须拒绝加载。Prompt、schema、质量门、预算、工具权限、eval 或来源清单变化必须提升 SemVer 后重新安装。
- `MethodRouter` 只处理 `focused/full`，输入只能来自当前 Workspace 内已确认的 Case/Dossier 快照，并携带 Case 版本、快照哈希和请求深度。
- 路由顺序 MUST 是 manifest 适用/排除规则筛选，再由模型在候选集合内生成结构化解释。
- 路由输出 MUST 包含 `exact | partial | unsupported`、方法 ID/版本/内容哈希、routerVersion、理由、适用边界、缺失输入、替代方法和 `formalAnalysisAllowed`。
- `partial` 必须展示可执行缺口，补充并确认数据后重新路由；不得启动正式分析。
- `unsupported` 仍允许聊天和明确标为“非正式方法输出”的 quick；focused/full、正式报告、PDF 和沙盘 MUST 在 API 与 UI 双重阻断。
- `focused/full` 都必须绑定 confirmed Charter、持久化 AnalysisRun 和研究/批判/综合/校验四类 Worker；两档只在预算、研究方向数和输出 schema 上不同。
- full Run 必须独立持久化并校验五个 `StrategicLensArtifact`：Research 产出 `porter_five_forces`，Critic 产出 `pre_mortem` 与 `counterparty_response_matrix`，Synthesis 产出 `scenario_planning` 与 `meadows_leverage_points`，Validation 检查逐项行为与下游消费。缺失任一项不得进入 `ready`、生成 PDF 或创建正式沙盘；五项不得扩张为五个新 Worker。
- Charter 必须冻结问题、期限、主体与档案快照、目标、硬约束、选项、允许/禁止材料、未知项、深度、方法 ID/版本/哈希、连接器、时间/模型/检索预算和授权结果。
- 质量门通过后 Run 直接进入 `ready` 并生成对应等级的产物，不新增发布前二次确认；产物对 Case/Dossier 的写回仍必须由用户验收为候选更新。
- 方法包 manifest 至少包含 ID、语义化版本、适用/排除条件、Cynefin gate、必需输入、Worker、工具权限、预算、Judgment/Dissent/DeepAnalysis 输出 schema、九 Validator Contract、质量门、沙盘映射、eval 和来源技能清单。`DeepAnalysisRequest/Result` 必须与 `06/26` 精确一致；Result 只返回持久化对象 ID/hash，不返回第二套内嵌 DTO。
- 产品级 `21-existing-asset-reuse-and-conversion.md` 与包内 `ways/hardtech-market-direction/1.1.0/CAPABILITY-MAP.md` MUST 对 `探讨/skills/research` 的 31 个 Skill 保持相同名称集合、状态与固定计数：直接编译 13、其他合同吸收 7、延期 8、仅参考 1、禁用 2。缺失、重复或漂移时不得安装 method-pack。
- Loader 遇到路径穿越、重复 ID/版本、frontmatter 缺失、未知 Worker/工具、schema 不兼容或未发布包时 MUST 阻止启动。运行期间不得热重载方法包；升级必须产生新版本且不改写历史 Run。

核心原则：**不锁死入口，锁死正式分析的执行契约。**

## 7. Agent、证据与质量门

- 正式执行 Worker 只有研究、批判、综合、校验四类职责。Validation Worker 内由一个编排器执行 V1-V9 九个隔离 Validator Contract；它们不是九个常驻服务，也不通过多数投票决定发布。Safety Anchor 和魔鬼审查是 Critic 的强制子步骤；参谋长式建议结构由 Synthesis 产出。
- full 的执行顺序 MUST 是 Research/Porter -> Critic/Safety Anchor -> Counterparty Matrix -> Pre-Mortem -> adversarial review -> Synthesis/Scenario + Meadows -> Validation。Counterparty 必须先于依赖其结果的 Pre-Mortem；五个 lens 仍不是五个新 Worker。
- 五个战略透镜必须执行方法包中的独立 Prompt 与判别式 JSON Schema，产物包含方法/Prompt/schema 版本和 claim/evidence/assumption 引用。`StructuredReport` 通过 `lensArtifactIds` 引用被 Validation 接受的不可变产物；不得把框架名写入通用 Prompt 就宣称能力已实现。
- 模型只能返回不含身份的 `StrategicLensOutput`；`id/workspaceId/decisionCaseId/analysisRunId/charterId/方法快照/producerRole/status/originModes/contentHash/createdAt` 全部由服务端从冻结上下文注入。服务端解析引用、通过 schema 与行为校验后才可写入 Postgres `StrategicLensArtifact(status=ready)`；模型自报这些字段必须拒绝。
- Research/Critic/Synthesis/Validation MAY 共用 DeepSeek V4 Pro 基座，但 MUST 分别使用独立 Prompt、上下文、阶段产物、预算、事件和 tool trace；产品和文档不得声称它们是四个独立基础模型。
- 委派工具权限只能是父任务权限的子集。并发、深度、迭代、时间和调用预算必须有硬上限；父任务只接收结构化摘要与 tool trace。
- Worker 阶段必须幂等或有重复领取保护，持久化 heartbeat、attempt、阶段输入/输出哈希和事件；中断后应恢复，不能恢复时进入 `needs_attention` 或结构化终态。
- 外部证据 MUST 经过：`RetrievalTask -> Provider Adapter -> RawArtifact -> Evidence Normalizer -> Information Quality Gate -> Evidence Ledger`。
- 外部网页、文件和模型内容一律视为不可信输入，不能覆盖系统、产品、安全、工具权限或 Workspace 约束。
- 证据结论只使用 `accepted | conditional | lead_only | rejected`。核心判断至少需要一条 `accepted` 或带条件的 `conditional` 证据；`lead_only/rejected` 只能用于线索或解释拒绝原因。
- 信息质检必须区分真实性、来源等级、相关性、时效性、适用范围、独立性、偏见、完整性、冲突和提取可靠性。
- 分析质量门必须检查主要判断支撑、相关/因果混淆、反向证据、来源冲突、关键假设、伪收敛、反方响应、条件化建议和沙盘边依据。
- Critic 或质量门的重要发现必须改变正文、条件、质量状态、因果边或进入 escalation；不得只生成无人消费的附录。
- 未通过质量门时只能交付草稿、阻断原因、缺口和验证动作。质量门有权阻断正式报告、PDF 和正式沙盘。
- 用户可见建议必须带成立条件、阈值、退出条件、领先指标和复盘日期，不得写成无条件命令。
- 不展示、记录或声称访问模型隐藏思维链。只保存用户可见命题、证据、假设、判断、方法版本、工具摘要、状态、因果边、模拟输入和建议。
- 正式 Agent Engine 输入 MUST 是 confirmed Case Charter + 冻结 Case/Dossier/Material Snapshot + analysis depth + method/budget/tool envelope；输出 MUST 是结构化 JudgmentSet + DissentRecord + DraftRecommendation + ValidatorResults。不得用 chat `messages[]` 作为正式分析主合同。
- 不把模型自评分、质量门分数或沙盘结果包装为“结论正确概率”或“成功概率”。分别展示证据可用性、命题支撑、假设稳定性、因果关系可信度、战略稳健性和流程质量。

## 8. 模型、连接器与来源模式

- 模型业务代码只能依赖 `ModelProvider`。至少通过环境配置 `MODEL_PROVIDER`、`MODEL_BASE_URL`、`MODEL_NAME`、`MODEL_API_KEY`、`MODEL_SUPPORTS_STRUCTURED_OUTPUT` 和 `MODEL_TIMEOUT_SECONDS`；默认值锁定 DeepSeek 官方 API 的 `deepseek-v4-pro`，但业务合同不得绑定供应商私有字段。
- DeepSeek thinking mode 的 `reasoning_content` 只允许存在于同一次 Provider 工具调用链的内存态 transient envelope；按官方协议回传工具结果时可以原样带回。它 MUST NOT 进入数据库、日志、`AnalysisEvent`、tool trace、上下文压缩、报告、fixture 或 UI；没有 tool call、调用结束或 Run 中断时立即丢弃。
- strict tool calls 和 JSON Output 都必须经过服务端 schema 校验。空 `content` 是结构失败，最多执行一次 schema 修复重试；不得读取或解析 `reasoning_content` 作为业务输出。
- Agent 只能看到稳定、只读的 `search_web`、`fetch_url`、`crawl_site`、`extract_document`、`get_source_status`，不能看到供应商专有接口或凭证。
- 默认检索路由：Exa 搜索失败/无 Key/限流/额度耗尽时切换 Tavily；Firecrawl 抓取失败时使用基础 HTTP 抓取、已有 RawArtifact 或缓存正文。
- 先搜索并去重，再抓取少量高价值页面。禁止无界抓取、默认全站爬取或跳过用户确认的域名/页数/深度预算。
- 用户只可从审核目录添加 Exa、Firecrawl 或 Tavily 的 Workspace-scoped BYOK 只读连接器。
- BYOK 必须使用 `CONNECTOR_MASTER_KEY` 在服务端加密；数据库只保存密文、nonce、key version 和掩码。响应、SSE、事件、日志、fixture、报告和异常不得出现完整 Key。
- 每次连接器调用记录 Workspace、用户、连接器、稳定工具名、查询摘要、时间、额度、结果哈希、错误和降级状态，不保存不必要的敏感正文。
- 连接器状态严格使用 `available | missing_credentials | invalid_credentials | rate_limited | quota_exhausted | provider_error | disabled`。
- 正常金路径优先使用真实模型和真实数据源。只有已审核 provider fallback 与可用缓存仍不能完成金路径时，才允许用户显式启用 deterministic fixture；不得静默切换或把 fixture 冒充实时结果。
- 缺少 Key 不得阻止应用、测试和核心链路开发；系统必须可启动，并能在明确提示和用户确认后运行 fixture 路径。
- fixture 只替代外部模型/搜索/抓取响应，不替代 Postgres、Run 状态机、质量门、报告渲染、沙盘算法、版本和决定保存。运行时代码禁止读取 `fixtures/**/expected/` 作为产品输出。
- `RawArtifact`、`EvidenceItem`、connector call 使用单值 `originMode`；`AnalysisEvent` 同时保存直接 `originMode` 与 `sourceOriginModes[]`；Run、报告、导出、图、模拟和决定使用去重的 `originModes[]`。
- 来源聚合按 `fixture > cached > live` 显示最保守状态，同时保留全部来源明细。UI 中的 `live/cached/fixture` 标识不得隐藏。

## 9. API、事件、报告与恢复

- API 必须使用统一成功/错误信封和稳定错误码；用户消息可操作且不泄露内部数据、资源存在性或密钥。
- 正式授权在 API、service 和 Worker 边界重复校验；不能依赖禁用按钮保证安全。
- SSE 的 `event:` 使用固定 category：`agent.status`、`agent.task`、`tool.call`、`citation.added`、`user.confirmation.required`；`data:` 是完整 `AnalysisEvent` 信封。
- 事件必须持久化并按 Run/消息作用域隔离。重连从 `Last-Event-ID` 对应的 sequence 继续，不重复、不倒退、不串到其他 Case。
- `focused` ready 只能生成 focused 合同产物；请求 PDF 或 `simulations/from-report` 必须返回明确的不允许错误。
- `full` 只有在 ready 且质量门通过后才能生成 `StructuredReport`、PDF 和正式沙盘。
- HTML 与 PDF 必须来自同一个 `StructuredReport`。PDF 失败时 HTML 保持可用，PDF `ExportArtifact` 标记 `failed` 并保存安全错误码，不得用预生成 PDF 冒充本次导出。
- 报告引用的每个 `evidenceId` 必须存在；来源等级缺失、核心判断无可用证据或未解释的来源冲突都阻止正式发布。
- `needs_attention` Run 只能通过 canonical 三类 `RunResolution` 恢复；改变冻结输入必须返回 `RUN_AMENDMENT_REQUIRED`。Run cancel 必须幂等，queued/执行阶段/needs_attention 可取消，ready/blocked/cancelled 不可取消或恢复。

## 10. 因果沙盘合同

- 沙盘是可干预、可解释的因果决策模型，不是预测器；页面必须明确说明“不代表精确预测”。
- 节点类型固定为 `decision | lever | constraint | external | unknown | intermediate | outcome | indicator`。
- 每条边必须保存方向、强度、延迟、关系存在可信度、来源和确认状态。关系可信度与影响强度不得合并。
- Strategy 是主动行动，Scenario 是外部因素/未知项假设，Simulation 是某情景下运行某战略；三者不得混为同一对象。
- `ScenarioVersion` 只保存外部/未知变量初始值、边强度乘数和来源 Scenario Planning frame；`riskTolerance` 属于冻结 Profile/Charter/Strategy/ScoreDefinition，MUST NOT 进入 ScenarioVersion。
- 推演引擎必须是确定性纯函数。相同 graph、strategy、scenario、score definition/profile 版本、riskTolerance、engineVersion、epsilon、maxSteps 必须产生相同 inputHash 和结果。
- 业务单位进入引擎前先转换为 normalized baseline；禁止用归一化状态直接减原始月份、金额或其他业务单位。
- `ScoreDefinition` 必须显式关联选项、结果、目标、风险和约束，不得从节点标签猜测评分含义。
- 传播 effect 精确使用 `delta * polarity * strength * edgeMultiplier * damping`；`relationshipQualityScore` 只影响解释质量、warning 和发布门，不进入数值 effect。`nodeShifts` 是归一化 delta；稳定性充分条件、epsilon/maxSteps 和敏感性步长必须按 `09` 实现。非收敛、饱和、无效数值和硬约束触发必须有结构化状态，不得参与正式推荐、signoff 或决定。
- 编辑先进入工作副本并支持 undo/redo；保存产生不可变 graph version。
- 用户添加影响因素只允许在完整模型按需触发：自然语言先生成 `FactorCandidate` 和候选关系，用户逐项确认、修改或否决后才写入带 `revision` 乐观锁的 `GraphWorkingCopy`；该入口禁止创建 `decision` 节点。
- 新因素必须保存 `authorship`、`controllability` 和 `evidenceStatus`。无可追溯证据时只能是 `assumed | unknown`，禁止冒充 supported 事实。
- 工作副本修改可以生成确定性 `ExperimentPreview`；预览必须绑定精确 revision，并持续标记 experimental。预览不是 `SimulationRun`，MUST NOT 用于 PDF、Decision、正式推荐或审计导出。
- 工作副本再次变化后旧预览必须 stale；正式运行仍要求保存 immutable GraphVersion、完成 confirmed 门并由用户主动运行。
- `from-report` 只能创建 draft `GraphVersion`。用户必须 bulk review 每个自动节点和每条自动边，确认、修改或否决后才可创建新的 confirmed `GraphVersion`；原 draft 和被否决对象保留审计历史。
- draft 图只允许 `experimental` 推演，并且结果不得进入 PDF、正式推荐或最终决定的系统建议；`formal` 推演只接受 confirmed `GraphVersion` 和不可变 `ScenarioVersion`。
- 用户可从任意历史版本创建命名分支、比较两个版本，并通过“从历史版本创建新的当前版本”完成非破坏性回滚；任何操作都不得删除历史。
- 正式 SimulationRun 必须固定引用 graph、strategy、scenario、ScoreDefinition ID/version、DecisionMakerProfile ID/version、实际 riskTolerance、engineVersion、epsilon、maxSteps 和 inputHash。
- 球形机器人 fixture 至少验证 8 个节点、10 条边、三个情景、敏感性排序，以及采购周期变化触发可解释的推荐翻转。

## 11. 前端与交互约束

- 登录后进入 Look V7 五个主工作区：问题 `workspace`、证据 `analysis`、判断 `report`、推演 `sandbox`、决定 `decision`。Review 是 dialog/drawer，Case 选择是 Project Drawer，无 Case 使用 `empty`；不得恢复四页 IA、独立 Review 主页面或模板墙。
- 界面应安静、工作导向、适合重复分析；不得使用营销式大标题、装饰性渐变/光球、嵌套卡片或模板卡片墙。
- 视觉主题 MUST 遵守 `24-frontend-visual-theme.md` 的 Look V7 合同：公开 ID 精确为 `ink/ledger/vermilion/red/orange/yellow/green/cyan/blue/purple`，默认 `ink`。Human/Analysis/Unknown、成功/警告/阻断和来源模式使用集中 semantic token，不能随主题交换责任语义；Paper/Night Desk 仅是 surface 角色，不是平行主题。
- 组件 MUST 消费集中 CSS 语义 token，不得在 JSX 中散布主题十六进制颜色或复制 Claude 的品牌图标、精确色值、文案和组件结构。
- 分析深度使用分段控件；熟悉操作使用 Lucide 图标；图标按钮必须有 `aria-label` 和必要 tooltip。
- 方法名称、版本、理由、边界和缺失输入放在 Charter 可展开详情中；用户不需要先理解方法论。
- `focused` 的详细报告、PDF 和沙盘控件必须隐藏；`unsupported` 必须保留聊天/quick，并明确禁用正式能力。
- 报告页展示执行简报、证据、引用、冲突、反方、六维质量和来源模式；点击引用进入 Evidence Drawer，不展示隐藏思维链。
- 沙盘默认先展示最多三个脆弱条件的压力测试；完整因果图按需展开，提供节点/边检查、变量控制、情景、评分、敏感性、分支时间线、比较和回滚。
- “添加影响因素”不得常驻默认首屏或把所有候选组件铺满画布；输入、因素审阅、关系审阅和预览按单一任务逐层展开，关闭后恢复留白。
- 所有核心组件必须覆盖 loading、empty、error、partial、unsupported、blocked、needs_attention、recovery 和 provider fallback 状态。
- 使用 TanStack Query 管理 API 数据，Case 缓存键包含版本；SSE 只增量更新事件和进度，Run 终态后重新拉取正式对象。HTTP 与 SSE 类型必须从 `packages/contracts` 生成物导入，禁止手写平行 API DTO；生成物禁止手工修改。
- 桌面现场主视口为 1440x900，移动验收视口为 390x844；同时验证 768-1199px 的抽屉式详情布局。小屏沙盘可只读概览，编辑转为表单。
- 文本不得溢出按钮、标签、面板或卡片；固定格式控件、画布、工具栏和图节点必须有稳定响应式尺寸。
- Cookie mutation MUST 通过 Origin/Referer 与 double-submit CSRF token；所有服务器端 URL 请求 MUST 使用 SSRF-safe client，pin 已批准 IP，同时保留原始 Host/TLS SNI/hostname certificate validation，并在每次重定向后重新解析与复核。登录、高成本 Run、连接器和上传 MUST 使用 Postgres-backed 用户/Workspace 限流与大小预算。
- 颜色不能是状态的唯一表达。键盘至少可完成创建案例、澄清、切换报告、运行推演和保存决定。

## 12. 安全、隐私与文件

- 禁止提交 API Key、JWT secret、Cookie、个人数据、生产连接串或真实客户材料；`.env.example` 只放占位符。BYOK 必须使用 AES-256-GCM（32-byte key、随机 96-bit nonce、AAD、master-key version）并支持轮换/重加密；不得自制可逆编码。
- P0 只承载公开、脱敏或专门用于演示的材料；不得鼓励上传源代码、未申请专利的核心细节、密钥、客户个人信息、原始合同或核心工艺参数。
- Workspace 数据默认私有且默认不用于训练。社区贡献与模型训练属于两个独立的活动后授权，P0 不得把演示数据自动用于任一用途。
- 上传必须校验文件类型、大小、文件名、存储路径和 Workspace 所有权，并防止路径穿越与未授权下载。PDF 使用 magic/MIME；TXT/Markdown 使用编码与内容策略，不能错误依赖 magic bytes。
- 上传原件、RawArtifact 和 HTML/PDF 导出必须通过共享 `ArtifactStore`；禁止 API、Worker、Renderer 各写本地私有目录，禁止数据库正文存储或绕过鉴权暴露 shared volume。
- 托管入口使用 HTTPS；Cookie Secure、CORS、Web/API Origin 和 SSE 代理缓冲必须可由环境配置。
- 连接器只读；抓取内容和上传文档不得触发外部写操作、浏览器任意操作或第三方副作用。
- 日志、错误、截图、测试产物和演示资产必须脱敏。任何完整连接器 Key 出现在响应、SSE、事件或日志中都是发布阻断。
- 提供管理员删除 demo Workspace 的运维命令；P0 不承诺面向真实客户的完整数据保留、导出和删除体系。

## 13. 编码与变更纪律

- 优先实现可运行、可验证的 P0 垂直切片；每个切片 SHOULD 同时交付 schema、API、UI、fixture 和测试，避免长期只有局部代码没有端到端结果。
- 对行为变更先写或同步更新能失败的测试，再做最小实现；不得把未运行的测试当作验证。QA/Release 只拥有测试、trace、截图和 handoff；发现产品缺陷必须交回 `agent-work-manifest.yaml` 的原 owner，禁止跨 owner 直接修改产品源码。
- 使用明确类型、描述性命名、小而聚焦的函数和早返回。稳定领域边界禁止使用 TypeScript `any` 或无 schema 的 Python `dict`。
- 注释只解释非显然原因、边界或权衡，不复述代码。
- 保持改动聚焦；不得顺手重构无关模块、替换已锁定依赖、格式化整个仓库或覆盖他人修改。
- 不得把 mock、fixture、禁用按钮、通用 Prompt 或预生成产物描述成已完成的生产能力。
- 新增/修改 schema、API、事件或环境变量时，必须在同一变更中更新 migration、类型、fixture、测试、`.env.example` 和受影响文档。
- Git 提交应小而连贯，不混合无关格式化、依赖升级、生成产物和业务行为；禁止提交缓存、虚拟环境、依赖目录、测试 trace、本地数据库或未批准的大二进制。
- 自 Task 6 已完成本地集成起，所有后续新开发 MUST 以最新本地 `main` 为基线创建新的任务分支（默认使用 `codex/<task-name>`）；MUST NOT 在 `codex/task-06-method-pack`、`codex/qa-task-06-method-pack`、`codex/integrate-task-06-method-pack` 或任何已完成的 Task 6 工作树/分支上继续修改或提交。新任务开始前必须确认本地 `main` 工作树干净、记录基线 commit，并先写入 `HEAD`。
- 保留已有用户修改；没有明确授权不得执行 destructive reset、checkout 或清理命令。

## 14. 测试与验证门

每个任务只运行与风险相称的验证，但完成声明必须基于本次变更后的新鲜输出。

- 后端领域/API：运行受影响 pytest，并运行相关 Workspace 隔离负面测试。
- 前端行为：运行受影响 Vitest/Testing Library 测试和 `pnpm --dir apps/web build`。
- 数据库：在干净 PostgreSQL 上执行 Alembic `upgrade head`，检查迁移内容与重复升级行为。
- Router：覆盖球形机器人 `exact`、缺输入 `partial`、非匹配 `unsupported` 和未知方法 ID/版本拒绝。
- Charter/Run：覆盖确认前置、不可变、替代 draft、确认后 supersede、单 Case 单活动 Run、focused/full 授权、三类 resolution、amendment 新 Run、精确阶段恢复，以及 blocked/cancelled 终态。
- 报告：覆盖证据质量门、focused 禁止 PDF/沙盘、full 正式产物、PDF 失败时 HTML 保底。
- Worker/SSE：覆盖重复领取、中断恢复、heartbeat、事件顺序和 `Last-Event-ID`。
- 安全：覆盖跨租户统一 404、CSRF、SSRF、登录与高成本任务限流、上传嗅探、安全响应头、连接器只读、任意 MCP 拒绝，并扫描响应和日志中的密钥。
- 沙盘：覆盖节点/边 bulk review、draft/confirmed GraphVersion、不可变 ScenarioVersion、experimental/formal 授权、正负边、延迟、裁剪、情景、硬约束、确定性、非收敛、分支、比较和非破坏性回滚；并覆盖 FactorCandidate、关系逐条审阅、缺证据默认状态、working-copy revision conflict、preview stale、preview 禁止正式引用和 fixture 图 `p95 <= 1s` 目标。
- Decision/Review：覆盖决定来源链、Review 保存/读取/刷新/跨 Workspace 404、服务端来源冻结，以及缺少建议采纳、执行、过程、结果、外部变化、假设验证、教训或下一轮改变时的校验失败。
- 文件：覆盖 API/Worker/Renderer shared volume 可见性、Workspace 路径规范化、跨租户 404、路径穿越拒绝、hash/metadata 一致性和静态直链不可用。
- 金路径/UI：用 Playwright 跑 1440x900、平板和 390x844，人工检查截图中的重叠、裁切、空白和来源标识。
- 测试默认不得调用付费或真实外部服务。live-provider 测试必须显式、可选，并在无 Key 时安全跳过。

常用命令以仓库实际脚本为准，初始合同为：

```powershell
docker compose up -d db
uv run --project services/api pytest -q
uv run --project services/api ruff check services/api
pnpm --dir apps/web test
pnpm --dir apps/web build
pnpm --dir apps/web exec playwright test
powershell -ExecutionPolicy Bypass -File scripts/generate_contracts.ps1 -Check
uv run --project services/api python scripts/verify_demo.py
pnpm --dir apps/web audit --prod
uv run --project services/api pip-audit
```

发布候选还必须验证 `docker compose build/up`、全新 migration、seed、live 优先金路径、显式 fixture 断网路径和恢复检查表。

## 15. Prototype/MVP 时间盒与范围控制

- 6 Agent 档的 72 小时 Hackathon Prototype 结论只在 Gate 0 通过后成立。Gate 0 MUST 验证 uv/Python 3.12、Docker daemon/Postgres、DeepSeek Key 与文本/structured output/thinking/tool-call 真实 probe、无冲突 canonical baseline、OpenAPI/TypeScript drift clean、Ways 源包与 31-Skill 双账本校验、fixture 三段边界、安全配置和浏览器环境；未通过前可做离线准备，但不得启动任何档位计时。
- Hackathon Prototype 使用 6 Agent/72 小时档：Contract Lead、Ways/Agent Pipeline、Case/API/Data、Web/UX、Simulation/Graph、QA/Release。完整 MVP 使用 4 Agent/108 小时、3 Agent/144 小时或重新估算；少于 6 个槽位时不得继续引用 72 小时 Prototype 估算，少于 3 个槽位或无法使用独立 worktree 时重新估期。
- 每条泳道 MUST 使用独立 `codex/<lane>-<slice>` 分支和 worktree，并遵守文件/模块 ownership。只有 Contract/Integration Lead 可以合并 canonical schema、API、事件与迁移；其他 Agent 不得自行发明平行 DTO、字段或状态。
- 从第 6 小时开始每 6 小时执行一次集成门：先合并合同、迁移和生成类型，再合并消费方；运行迁移、contract tests、fixture 路径扫描、跨租户/secret 检查和当前金路径 smoke。失败切片退回 owner，不能叠加新功能。
- `0-12h`：仓库、canonical schema、认证、Workspace、真实 Postgres/状态机下的 fixture 金路径。
- `12-30h`：日常问答、候选确认、方法包、Charter、AnalysisRun、SSE 和事件 UI。
- `30-48h`：真实或明确降级的来源、证据质量门、四类 Worker、V1–V9 和最小结构化报告；PDF 仅在不影响金路径时作为 stretch。
- `48-60h`：最小可重放 sandbox、SignoffPayload、人类签署和 append-only Decision；完整图编辑、分支、比较、回滚和完整 Review 是 stretch/完整 MVP。
- 第 60 小时功能冻结。`60-72h` 只允许验收、发布阻断修复、部署、彩排、截图、录屏和恢复资产；禁止增加非阻断功能。
- 第 36 小时分析链路未跑通则执行计划中的宽度删减：可删文件格式、BYOK 目录宽度、移动端编辑和非阻断展示，不得删三模式金路径、Workspace 隔离、正式授权、状态机、质量门或来源标识。
- 外部服务缺失不得阻止核心开发；内部 Worker、状态机、授权或质量门缺陷不得用 fixture 掩盖。
- 优先完成唯一球形机器人金路径，禁止以多个半成品案例换取表面功能数量。

## 16. 完成定义

任务只有在所有适用断言都为真时才完成：

- 实现与已确认的产品、schema、API、事件、UI 和安全合同一致。
- 受影响测试、类型检查、lint 和 build 已用最新代码运行并通过；失败或跳过项已明确报告。
- Workspace 隔离、正式分析授权、Charter 不可变、来源模式、结构化 Review 和密钥脱敏没有退化。
- loading、empty、error、unsupported、blocked、needs_attention、fallback 和恢复状态按变更范围得到处理。
- fixture/cached/live 在数据、事件、报告和 UI 中保持真实标识，没有用预置输出冒充本次运行。
- 至少一种审核目录 BYOK 连接器可被添加、检查和安全使用，缺 Key、Key 失效、限流、额度耗尽和 provider error 均有可验证状态。
- 文档、migration、fixture 和示例与实现同步，没有重新引入旧品牌、旧案例、旧状态或平行技术栈。
- 变更可以在球形机器人金路径中展示，且不会把质量分数或沙盘输出声称为成功概率。
- 交接说明列出修改文件、实际验证命令及结果、失败/跳过检查和仍需外部输入的事项。

Hackathon Prototype 候选只有在不可降级主链路、Web App、5 分钟演示、60–90 秒宣传录屏、至少 6 张关键界面截图、一页产品说明、系统架构图、决策闭环图、完整备用录屏、演示账号/预置数据和恢复检查表全部就绪时才算完成。完整 MVP 还必须完成 108/144 小时 backlog 中的 PDF、完整图版本链、BYOK UI、完整 Review 和视觉验收，不能用 Prototype 资产代替。


## 17. 知识产权、许可与公开发布

- 截至 2026-07-22，本仓库 MUST 保持 Private，根目录 MUST NOT 添加 `LICENSE`；Ludus 自有内容按 `LICENSING.md` 和 `COPYRIGHT` 的 **All Rights Reserved** 状态管理。不得把当前仓库描述为已经采用 MIT、Apache-2.0、AGPL-3.0、BSL 1.1 或其他公开许可。
- 当前候选商业化结构是“核心私有 + 可选择性开放外围能力”。`ways/**` 自有方法、决策/评分/质量门、Agent 编排、因果模拟策略、系统 Prompt、eval corpus、golden fixtures、调优数据和可实质复现核心技术的资料默认 Proprietary；不得复制到公开仓库、公开包、公开镜像或公开演示资产。
- SDK、API client、插件接口和非核心示例只有在路径级 IP boundary audit 后 MAY 候选 Apache-2.0；经拆分的社区 Web/API shell MAY 候选 AGPL-3.0-only + 商业双许可；选定服务器模块 MAY 候选 BSL 1.1，但 BSL 必须称为 Source Available，不得称为 OSI Open Source。以上均不是当前已授予许可。
- 任何开发者或 Agent MUST NOT 擅自创建、替换或修改根 `LICENSE`、SPDX header、版权主体、CLA/DCO、公开包发布配置或仓库可见性。许可变更必须获得产品方对具体路径、版本与许可的书面批准，并同步 `LICENSING.md`、`COPYRIGHT`、`README.md`、本文件和发布物。
- 未经产品方确认，MUST NOT 把仓库改为 Public，也不得向任何公开 remote、registry 或镜像仓库推送核心内容。向当前受控 Private `origin` 首次 push 前仍必须确认远程可见性并完成当前树及 Git 历史的 secret/IP scan。
- 第三方材料不因进入私有仓库而变成 Ludus Proprietary。任何 Extract & adapt 必须保留上游版权/许可证并记录精确版本、commit、源路径、函数和修改；公开发布前必须完成 `THIRD_PARTY_NOTICES.md`、资产授权、专利/商业秘密、商标与贡献者权利链审计。
- 如果仓库公开边界、第三方许可、贡献者再许可权或可专利披露存在不确定性，任务状态 MUST 标为 blocked 并交由产品方/法律顾问决定；不得以实现便利替代法律决策。

## 18. HEAD/HISTORY、验证切片与本地环境

- `HEAD` 是当前工作的唯一活动记录；必须包含开始时间、状态、目标、范围、约束、已完成事项、验证结果、未验证事项和下一步。不得在其中记录密码、API Key、Token、Cookie、连接串或其他敏感值。
- 进入新的工作前，如果 `HEAD` 仍保存上一项非 idle 工作，MUST 先把其完整内容连同归档时间追加到 `HISTORY`，再写入新的 `HEAD`。`HISTORY` 是 append-only，不得重写、排序、压缩或删除已有记录。
- 当前工作结束时，MUST 先把 `HEAD` 状态更新为 `completed` 或经规则确认的 `blocked`，写明实际验证与剩余风险，再把完整记录追加到 `HISTORY`；随后把 `HEAD` 置为 `idle` 并记录最近归档时间/条目标识，防止重复归档。
- `E:\Temp\xiayu\Documents\adventure-x\decision-lab-G0` 只用于可丢弃的 Gate 0 切片验证。所有最终代码、配置、文档和验证脚本 MUST 落到 `E:\Temp\xiayu\Documents\adventure-x\decision-lab`；不得把验证切片当作交付仓库。
- 安装或升级系统/全局工具、安装项目依赖、创建 Python `.venv`/其他 runtime 环境、拉取容器镜像、启动持久容器或安装 Playwright 浏览器前，MUST 先征得产品方明确同意。只读版本探测、语法解析和使用已安装工具执行不产生新环境的检查 MAY 直接进行。
- 环境操作获批后，Python MUST 使用 3.12；默认 Python 3.14 不得用于项目环境。虚拟环境如需创建，只能位于仓库内的 `.venv` 并保持 Git ignored。
- Gate 0 未完全通过时，离线 bootstrap MAY 继续，但 `HEAD`、报告和提交信息 MUST 明确写为 offline preparation；不得输出 `PREFLIGHT_OK`、启动 3/4/6 Agent 容量计时或声称 live-provider/生产验收通过。
