# 13. 测试与验收

## 测试目标

Alpha 测试不追求企业级覆盖率，而是保证端到端演示真实可用、关键数据可追溯、失败时能降级。测试围绕一条主链路：创建决策项目 -> 讨论归档 -> 冻结 Run -> 深度报告 -> 沙盘推演 -> 请求 Signoff -> 授权人类签署不可变决定。

## 测试分层

| 层级 | 范围 | P0 要求 |
|---|---|---|
| 单元测试 | 数据校验、传播算法、评分、质量门 | 覆盖核心纯函数 |
| 集成测试 | API、数据库、Run 状态、报告渲染 | 覆盖主接口和失败分支 |
| 端到端测试 | 浏览器链路、SSE、PDF、沙盘 | 覆盖预置案例完整演示 |
| 内容验收 | 报告质量、引用、反方、建议边界 | 人工和规则共同检查 |
| 降级验收 | 模型/搜索/PDF 失败 | 预置案例和缓存路径可用 |
| 连接器验收 | Exa/Firecrawl/Tavily、BYOK、密钥和额度状态 | 只读、隔离、可降级、无密钥泄露 |
| 方法路由验收 | 对话入口、匹配状态、Charter 冻结和非匹配边界 | 不强制模板，不冒充正式分析 |
| 战略透镜验收 | 五项独立 artifact、角色映射、行为 schema、读取 API 与报告引用 | full 强制且可审计，focused 不创建 |
| 迁移行为等价验收 | 至少两个获授权且去标识化的 `探讨` 成功实验、固定模型/资料条件、六维行为 rubric | 不比逐字文本、不以模型投票作概率，未完成前不得宣称复现原效果 |
| 模型适配验收 | DeepSeek probe、结构化输出、审计与瞬态字段 | 默认可替换、空内容可控、不保存隐藏推理 |
| 方法源验收 | ways 校验、安装、哈希和 runtime catalog | 唯一源资产、运行时不可漂移 |
| 展示验收 | Web、5 分钟现场演示和宣传资产 | 72 小时内可重复交付 |

## 单元测试

重点测试对象：

- `DecisionCase` schema 校验。
- `MethodRouter` 精确/部分/不支持匹配和方法目录约束。
- `AnalysisCharter` 确认后不可变、变更生成新 draft。
- full Charter 的 `requiredStrategicLensTypes` 恰为五项 canonical 集合，focused 为空；增删 lens 分类为 `strategic_lens_set` amendment。
- `EvidenceItem` 来源等级、过期状态和冲突分组。
- `SourceRecord/SourceSpan` 的 `pre_run | run_frozen` 判别联合；Run 前用户输入不伪造 RawArtifact，Run 创建时复制冻结来源 ID/hash。
- `SystemRecommendation` 的 `option | abstain` 精确联合；fatal unknown、质量门 blocker 或无合法路径时不得返回空 option。
- 报告质量门：引用、反方、条件、阈值、退出条件。
- 沙盘传播算法：正向边、负向边、延迟、裁剪、情景乘数；`relationshipQualityScore` 不进入 effect，稳定性充分条件、epsilon/maxSteps 和非收敛状态可复验。
- 敏感性分析排序；优先使用 `sensitivityStep`，默认步长为业务范围的 10%，相同冻结输入和 `inputHash` 重放结果完全一致。
- 选项评分与硬约束惩罚。
- StrategicLensArtifact 判别联合、同 Run/lens 幂等、不同哈希冲突、不可更新和 Workspace/Run 引用约束。
- DeepSeek JSON Output 空 `content`、schema 失败的一次修复重试和重试后阻断。
- `ways/hardtech-market-direction/1.1.0` 校验、确定性安装、哈希一致与相同版本冲突拒绝。

示例用例：

| 用例 | 输入 | 期望 |
|---|---|---|
| 负向边传播 | 外部风险因素上升，负向影响结果节点 | 目标结果下降 |
| 延迟边 | `delaySteps=1` | 第 1 轮不生效，第 2 轮生效 |
| 硬约束 | 工程投入超过上限 | 对应选项被显著降分 |
| 引用缺失 | 报告主要判断无证据且未标假设 | 质量门失败 |
| 冲突证据 | 同一 claim 有支持和反驳来源 | 报告要求冲突解释 |

## 合同与安全生成门

- OpenAPI 与 TypeScript regenerate 后仓库必须 clean；生成物手工修改或 Web 手写平行 DTO 均阻止合并。
- Cookie mutation 覆盖 `GET /api/auth/csrf`、正确 token、缺失 token、错误 token、跨 Origin 和 token 轮换。
- UserSession 覆盖登录创建、logout/revoke、过期、membership 移除和 capability 变化；撤销 session 或缺少 `sign` capability 后已有 JWT 也不能签署。
- SSRF 覆盖 loopback、RFC1918、IPv6、metadata、DNS 解析、approved IP pin、原始 Host/TLS SNI/证书校验、重定向后重新解析、非常规端口和响应大小。
- 登录、高成本分析、连接器和上传覆盖 Postgres-backed 用户/Workspace 限流，并验证多进程/重启后额度不会绕过。
- BYOK 覆盖 AES-256-GCM 32-byte key、随机 96-bit nonce、AAD、master-key version、轮换与篡改失败；测试只使用假密钥。
- 上传覆盖 PDF magic/MIME、TXT/Markdown 编码与内容策略、扩展名不一致、路径穿越、压缩后大小和 HTML/Markdown 转义。
- QA 的产品缺陷以 handoff 交给唯一 owner；验收提交不得跨 ownership 修改被测源码。

## 集成测试

### Auth、Session、Membership 与 capability

- `GET /api/auth/csrf` 返回可轮换 token；register/login 建立可撤销 `UserSession`，logout 原子撤销当前 session。
- 每个 Workspace-scoped 请求都从活动 session 解析 membership/capability，不信任客户端自报 role；跨 Workspace 统一 404。
- `owner` 默认能力与 `member` 显式能力投影一致；Worker/Agent 永远不能获得 `sign`。
- 已签发 JWT 在 session revoked/expired、membership removed 或 `sign` capability 被移除后立即失去签署能力。

### Case API

- 按 canonical contract 覆盖案例列表、创建、读取、状态/版本和跨 Workspace 404；测试不另造平行响应字段。
- `POST /api/workspaces/{workspaceId}/cases` 创建案例后返回 `decisionCaseId`、`version` 和澄清问题。
- `PATCH /api/workspaces/{workspaceId}/cases/{decisionCaseId}` 基于 `baseVersion` 更新，版本冲突时返回 `VERSION_CONFLICT`。
- `POST /api/workspaces/{workspaceId}/cases/{decisionCaseId}/messages` 写入消息并生成候选档案变更。
- PDF/TXT/Markdown 上传形成 Workspace-scoped RawArtifact，MIME/签名错误被拒绝，文件内容不直接成为正式事实。
- 候选确认或重分类后 `ArgumentTree` 的选项、支持/反对理由、假设和证据投影同步。

### AnalysisRun 系统

- Run 前消息、Case 字段和上传材料先成为 `pre_run` SourceRecord/SourceSpan；confirmed Charter 创建 Run 时在同一事务冻结为新的 `run_frozen` 来源并记录 `analysisRunId/frozenFrom*`，原记录保持可审计。
- confirmed Charter 创建 Run 后进入 `queued`，同一 Case 的第二个活动正式 Run 被拒绝或返回现有 Run。
- Worker 能 claim Run 并写入 `heartbeatAt`。
- Run 事件可通过 SSE 读取并支持 `Last-Event-ID`。
- 已授权 Provider 的可恢复故障进入 `needs_attention`；追加合法 `provider_recovery` `RunResolution` 后精确回到 `lastResumableStage`，不得统一回到 `queued`。
- 来源冲突裁决、既有硬约束确认和已授权 Provider 恢复三类 resolution 均需覆盖合法/非法 payload、幂等和审计事件。
- 预算、新材料/连接器、问题、目标、选项、偏好权重、硬约束定义、方法或深度变化必须分类为 amendment；原 Run 不恢复，replacement Charter 确认后创建 new Run 并关联取消旧 Run。
- 状态严格使用 `queued/planning/retrieving/analyzing/criticizing/synthesizing/validating/ready/blocked/needs_attention/cancelled`。
- 活动 Run 的 canonical cancel 动作幂等；Worker 在安全边界停止，刷新后仍为取消终态，既有事件可读且不生成正式报告/PDF/沙盘。
- `DeepAnalysisRequest` 精确使用 Workspace/Case/Run/Charter/hash/method/budget/tool/connector/idempotency 字段；`DeepAnalysisResult` 只返回已持久化 artifact ID/hash 与九验证结果，不内嵌第二套 Judgment/Dissent DTO。

### 方法路由

- 登录后直接进入日常问答，不显示强制模板选择页。
- 球形机器人案例稳定返回 `exact` 和 `hardtech-market-direction@1.1.0`。
- 方法源 eval 规格固定为 5 个：球形机器人 exact/full；同一去标识化脑机接口平台案例的 seed/full 与 angel/full 尺度敏感性配对；缺少决策合同字段的 partial/full；不适用营销优化问题的 unsupported/focused。配对规格只验证预期行为差异，不等于完成 legacy/Ludus 双轨 parity 运行。
- 缺少目标、期限或两个选项时返回 `partial` 和明确缺口，不创建正式 Run。
- SaaS 欧洲市场等非匹配案例返回 `unsupported`；聊天和快速分析可用，聚焦/完整研究禁用。
- Router 返回的方法 ID 和版本必须存在于已发布目录。
- 只有 `confirmed` 且 `formalAnalysisAllowed=true` 的 Charter 能创建正式 Run。
- 已确认 Charter 的 PATCH 返回 `CHARTER_IMMUTABLE`；修改创建替代 draft。旧 confirmed Charter 在替代 draft 未确认时仍有效，新 Charter 确认后才产生 `superseded` 事件。`blocked/cancelled` 不接受 resolution，重做只能创建新 Run。

方法源生成门必须解析全部 YAML/JSON，使用 Draft 2020-12 strict mode 编译 9 个 schema，确认 manifest documentation/Prompt/Schema/eval 引用文件与磁盘一致、eval 覆盖数为 5、17 个实际编译来源 Skill 版本与 frontmatter 一致、43 个诊断问题和 29 项质量检查 ID 唯一，并验证 `AG-15` 至 `AG-18` 存在。生成门还必须从 `CAPABILITY-MAP.md` 提取 31 个唯一 Skill，核对直接编译 13、其他合同吸收 7、延后 8、参考 1、禁用 2，且名称集合与 `探讨/skills/research/*/SKILL.md` 一致。任一失败都不得安装为 `published` 方法包。

### 报告渲染

- `focused` ready Run 只生成 `FocusedResearchResult`、执行简报和证据账本；PDF 与正式沙盘接口返回不允许。
- `full` ready Run 才生成完整 `StructuredReport` 并允许创建正式沙盘。
- 同一个 `StructuredReport` 可以生成 HTML 和 PDF。
- PDF Export 失败时 HTML Export 仍可访问，PDF `ExportArtifact.status` 标记为 `failed` 并保留错误码。
- 报告中的引用 ID 都能在 `EvidenceItem` 中找到。
- full HTML 预览、PDF 下载和失败重试均消费本次 ExportArtifact；不得用预生成文件冒充成功。
- `StructuredReport.lensArtifactIds` 恰好引用同 Workspace/Case/Run/Charter/方法快照的五个 ready artifact；缺失、重复、跨 Run、角色错误或不可解析时阻止 ready、HTML/PDF 和正式沙盘。
- `Recommendation.outcome` 覆盖 option 与 abstain；abstain 报告仍必须保留条件、风险、Unknown、修复动作和质量解释，不伪造 recommended option。

### Strategic Lens Artifact 与 API

- full Run 按固定映射持久化：Research=`porter_five_forces`；Critic=`pre_mortem` + `counterparty_response_matrix`；Synthesis=`scenario_planning` + `meadows_leverage_points`。Validation 不得补写缺失 artifact。
- `(workspaceId, analysisRunId, lensType)` 唯一；相同 contentHash 幂等返回已有 artifact，不同哈希冲突；artifact 无 PATCH/DELETE。
- `GET /api/workspaces/{workspaceId}/analyses/{analysisRunId}/strategic-lenses` 按 canonical 顺序返回 `StrategicLensArtifactSummary[]`，断言保留 ID/type/producer/status、引用计数、版本/hash/origin/createdAt 且序列化结果不存在 `content/researchRequests`；item 端点才返回完整 `StrategicLensArtifact` 判别联合。跨 Workspace、artifact 不属于 Run 或 ID 枚举统一 `404`。
- focused 列表为空且数据库不存在 artifact；full 运行中可读取已持久化子集，但五项齐备且行为通过前不能发布报告。
- 每个 artifact 的 evidence/claim/assumption/challenge/source packet 引用必须在同一 Workspace/Run 可达，`strategic_lens.completed` 事件只保存 ID、类型、角色、引用计数和 hash。

### MCP 与数据源

- Exa 搜索结果先进入 `RawArtifact`，不能直接成为正式 Claim。
- Firecrawl 只抓取初筛后的 URL，并保留原始 URL、时间和结果哈希。
- Exa 无 Key、Key 失效、限流和额度耗尽时能切换 Tavily 或缓存路径。
- Firecrawl 不可用时能切换基础抓取、已有 RawArtifact 或缓存正文。
- 用户能从审核目录添加 BYOK 连接器，不能提交任意 MCP URL 或写工具。
- 密钥不出现在浏览器响应、SSE、审计事件和应用日志中；任何完整 API Key 出现都视为发布阻断。
- 其他 Workspace 无法读取或调用当前 Workspace 的连接器。

### 沙盘

- 从报告进入沙盘后先显示当前建议和最多三个最脆弱条件，可在不展开完整图的情况下完成压力测试。
- 压力测试以业务单位显示输入和结果，并解释建议保持、翻转或证据不足。
- 从报告生成图后节点和边数量符合最低要求。
- 自动生成节点/边先为草稿；确认、修改或否决后才能保存首个正式图版本并运行正式 SimulationRun。
- 编辑节点和边后保存图版本。
- 运行三情景返回选项评分和敏感性排序。
- formal SimulationRun 冻结 Graph/Strategy/Scenario、ScoreDefinition ID/version、Profile ID/version、实际 riskTolerance、engineVersion、epsilon、maxSteps 和 `inputHash`；相同冻结输入重放 hash/结果一致，任一字段变化产生不同 inputHash。
- `nodeShifts` 按归一化 delta 解释；传播 effect 精确为 delta × polarity × strength × edgeMultiplier × damping，质量分只产生 warning/发布门，不改变数值。
- `L < 1` 的 fixture 收敛，达到 maxSteps 或稳定性条件失败返回 non-converged；non-converged 不得改变正式建议、生成可签署 payload 或冒充成功。
- `ScenarioVersion` 只从用户审阅接受的 ready `scenario_planning` artifact frame 创建，保存 `sourceLensArtifactId/sourceStrategicScenarioId`、`strategySurvives` 和 early warning；不得含 `riskTolerance`，风险偏好来自冻结 Charter/ScoreDefinition/Strategy。

### Decision 与 Review

- SignoffRequest 冻结完整 payload：Case/Run/Report/Judgment/Dissent/Graph/Simulation、system option/abstain、人的选择、决定文本、条件、阈值、退出条件、行动项、领先指标、Unknown 与复盘日期；payloadHash 对任一字段变化都改变。
- 只有活动 session、有效 membership、`sign` capability、正确 payloadHash 和一次 nonce 可在同一事务创建 append-only DecisionRecord；nonce 重放、撤销 session、缺 capability、过期或 payload 漂移均失败。
- DecisionRecord 保存后可按 Case 重新读取，并保持来源报告/图版本。
- Review 可保存、按 Case/DecisionRecord 读取、刷新回显，并通过跨 Workspace 404 测试；来源 Case/Run/GraphVersion/SimulationRun 由服务端从 DecisionRecord 冻结，客户端不能伪造。
- Review 必须分别验证建议采纳、执行偏差、决策过程质量、结果质量、外部变化、现实结果、原假设状态、教训和下一轮改变；只提交 outcome/notes 的请求必须校验失败。
- Review 不覆盖原决定，也不把 SimulationRun 当作现实结果；自动到期提醒不属于 P0。

### DeepSeek Provider

- Gate 0 probe 使用默认 `provider=deepseek`、`base_url=https://api.deepseek.com`、`model=deepseek-v4-pro`，记录请求 model id 与 API 返回版本/模型标识；环境覆盖仍可用。
- DeepSeek V4 Pro thinking 默认启用；strict tool calls 在 thinking/non-thinking 均有契约测试。
- JSON Output 返回空 `content` 或 schema 不符时只修复重试一次；仍失败返回结构化错误，不解析自由文本。
- `reasoning_content` 只存在于单次工具调用链内存，不进入数据库、事件、SSE、日志、报告或快照。
- Research/Critic/Synthesis/Validation 即使共用一个模型，也必须有隔离的上下文、Prompt、产物、预算、事件和 tool trace。

## 端到端测试脚本

P0 E2E 步骤：

1. 登录后进入日常问答，打开案例列表并选择 Workspace 和球形机器人 DecisionSubject。
2. fixture 金路径进入 `seed_demo.py` 幂等创建的唯一 seed Case：`资金与研发资源有限的球形机器人项目，应该优先进入救援市场，还是家庭服务市场？`；案例创建页另用 live/contract E2E 验收，普通新建 Case 不能加载 demo `external/`。
3. 上传一份 TXT 演示材料，确认形成 RawArtifact；回答 3 个澄清问题。
4. 确认结构化档案中出现目标、硬约束、假设和未知项，并查看同步的 `ArgumentTree`。
5. 点击“分析这个问题”，选择完整战略分析。
6. 确认路由到 `hardtech-market-direction@1.1.0`，查看理由和边界后确认 Charter。
7. 确认来源状态显示 Exa 搜索和 Firecrawl 抓取，或显示明确的 Tavily/缓存降级。
8. 观察 SSE 中五项 `strategic_lens.completed` 和 Run 从 `queued` 到 `ready`，逐个读取 artifact 并核对固定 producerRole。
9. 本次选择 `full`，打开报告页并确认简报、五项透镜、反方审查、引用、HTML 预览和本次 PDF 下载存在；另用契约测试验证 `focused` 没有 lens/PDF/沙盘权限。
10. 点击生成沙盘，默认视图显示当前建议和最多三个最脆弱条件，不要求先进入完整因果图。
11. 选择“采购周期”，将其调整为 14 个月并运行压力测试；检查业务单位、相对基线变化、关键影响路径、翻转阈值或当前测试范围。
12. 从结果生成一条候选验证行动并保存命名实验分支；展开完整模型后确认/修改/否决高影响节点和边，保存正式图版本。
13. 切换至少 3 个由 ready `scenario_planning` frame 经用户审阅生成的 confirmed 业务情景，核对 source lens/frame、early warnings 与策略测试，其中至少一个情景推翻当前策略。
14. 人类创建 SignoffRequest，确认冻结的系统 option/abstain、Judgment、Dissent、Graph/Simulation（如有）、条件、阈值、退出条件、Unknown、行动项、领先指标和复盘日期，并核对 payloadHash。
15. 具有活动 session 和 `sign` capability 的人类用一次 nonce 独立签署；验证 DecisionRecord append-only、来源 Run/Report/Judgment/Dissent/Graph/Simulation 冻结且 Case 进入 `decided`。随后重放 nonce 与撤销 session 再签均失败。
15. 保存一条 Review，刷新后重新打开并核对来源版本。
17. 回到案例列表，确认状态为 `decided`，并可由人类启用 monitoring。

另建独立 E2E 取消一个活动 Run，验证取消终态和禁止发布；主金路径 Run 不取消，也不通过 fixture 跳过。

## 报告质量验收

报告必须满足：

- 一页简报包含决策问题、推荐、原因、条件、阈值、退出条件、领先指标和复盘日期。
- 详细报告包含背景、目标、约束、选项比较、证据审查、反方审查、建议和残余不确定性。
- 每个核心判断至少关联一条 `accepted` 或 `conditional` 证据；非核心判断若仅依赖假设必须明确标记且不能提升为正式核心结论。
- 来源显示等级、发布时间或检索时间。
- 涉及跨期、跨样本、跨地域、跨币种或比例比较时显示对齐口径和分母；无法对齐的资料不得支撑核心结论。
- `conditional` 证据只支撑带条件判断，`lead_only/rejected` 不得进入核心结论；Evidence verdict 与正文使用方式不一致时阻断。
- 冲突来源有解释，不用单一结论掩盖分歧。
- 反方审查至少包含 3 条反对理由，其中 1 条必须是高严重度或关键假设。
- 高严重度反方发现必须实际改变正文、条件、阈值、退出标准、质量状态或 escalation，不能只增加风险附录。
- full 报告至少包含一个资源尺度反事实，并明确资源变化是否改变策略性质、选项排序或只改变执行节奏。
- 建议不得写成无条件命令，必须有成立边界。
- 简报必须把复盘日期放在低成本退出窗口之前，并用假设指标与执行指标共同支持后续区分决策质量、执行质量、外部冲击和结果质量。
- full 报告五个 `lensArtifactIds` 必须独立可读；报告摘要不得替代原 artifact，任一 lens 行为失败即质量门失败。

## 五项 Lens 行为验收

球形机器人 eval 以行为断言验收，不接受只出现标题或空模板：

| Lens | 必须通过的行为断言 |
|---|---|
| Porter | 分别分析救援和家庭服务两个市场；每个市场行业边界完整、标准五力各一次、每力至少 2 个 Evidence 和趋势；另有监管/变化、互补品、跨市场含义，`scoreIsNotDecisionFormula=true` |
| Pre-Mortem | perspectives 精确覆盖 internal/external/systemic_hindsight；至少 5 causes；topRisks 精确 3 项且 prevention/contingency/detection 不为空；verdict 为 continue/modify/abandon/validate_first；至少覆盖采购超过现金窗口或复杂环境可靠性失败机制 |
| Counterparty Response Matrix | 1-2 个关键 actor，2-3 个 observable actions 且恰好一个 no-action；每个 actor/action 有 optimal/worst/likely response、window、ourCounterResponse；publication test、downside asymmetry、exit cost 和 reflexivity 均存在 |
| Scenario Planning | predetermined elements 非空；至少 2 个 high-impact/high-uncertainty，精确 2 axes；3-4 个情景且一个 baseline、至少两个 structural break；每个含 timeline、至少 3 stakeholder states、3-5 early warnings；逐选项 strategy test 且至少一个 killed |
| Meadows Leverage Points | systemMap 含 stocks/flows、强化/平衡回路、delays、rules/incentives；`levelsCovered` 至少 3；至少一个 1-4 highLeverageGap、一个 runaway reinforcing loop、两步 intervention sequence，并显式记录 disruption/risk tradeoff |

`fixtures/spherical-robot/expected/strategic-lenses/` 保存五项正例，`fixtures/spherical-robot/negative/strategic-lenses/` 的负面 fixture 分别删除一力 Evidence、Pre-Mortem 第五 cause、Counterparty no-action、Scenario killed strategy、Meadows highLeverageGap。五种情况都必须阻止 full ready；Validation 不得用自由文本或报告内联段落补齐，也不得另建平行别名目录。

## `探讨` 迁移行为等价验收

该验收验证迁移后的行为纪律，不把历史输出当逐字 gold answer，也不替代球形机器人 P0 金路径：

1. 产品方书面授权并完成去标识化后，从 `探讨` 既有成功实验中选择至少 2 个不同决策案例；manifest 保存授权引用、去标识化复核、用途/保留期限和输入/输出 hash。未授权、无法确认来源或仍含个人/客户标识的案例不得进入 suite。
2. 每个案例分别运行旧框架与 Ludus，并锁定相同 provider、请求 model/version、推理参数、资料快照/hash、连接器可用性、预算和时间边界。无法在相同条件下重放的案例不计入“至少两个”。
3. 比较单位是下表行为 rubric。每项记录 `pass/partial/fail` 和可定位的 artifact/段落/引用证据，由确定性规则与人工复核共同签署；不比较措辞、文风、段落顺序或逐字相似度。

| Rubric 维度 | 可举证验收 |
|---|---|
| 证据纪律 | 核心判断有合格证据，事实/假设/判断分离，冲突与弱证据不被隐藏 |
| 反方改变正文 | 重要 Critic 发现实际改变正文、条件、质量状态或进入 escalation，不只是附录出现 |
| 五透镜完整性 | 五项 lens 均满足数量、角色、引用与行为合同；Ludus 还必须存在五个独立 ready artifact |
| 条件化建议 | 建议包含成立条件、阈值、退出/转向边界，不写成无条件命令 |
| 剩余未知 | 不可约简未知与追加验证任务显式保留，不以流畅文本掩盖 |
| 可追溯 | 结论可回到证据、假设、挑战、方法/模型版本和来源材料 |

每个 Ludus 案例六项均不得为 `fail`，且“五透镜完整性”“可追溯”必须为 `pass`，suite 才通过；旧框架分数是迁移基线而不是成功概率。禁止用模型投票、自评分或 rubric 聚合值声称成功概率。suite 尚未在至少两个案例上完成并签署时，只能声明“转换合同完成”，不得声明“已复现原效果”“效果等价”等。球形机器人仍是唯一 P0 金路径、5 分钟演示与发布阻断用例；legacy parity 是额外迁移验收，不阻断满足其他 gate 的 P0 产品发布，只阻断效果等价声明。

## 引用验收

引用验收规则：

| 规则 | 失败处理 |
|---|---|
| 报告引用的 `evidenceId` 必须存在 | 阻止发布 |
| 来源等级缺失 | 阻止发布 |
| URL 和文件路径均为空 | 允许一手访谈摘要，但必须标注来源类型 |
| 过期资料支撑核心结论 | 降低证据可用性状态并在报告标注 |
| 冲突组没有解释 | 阻止发布 |

引用存在不等于引用正确。预置案例的每个核心 Claim 还必须人工核验：引用摘录是否直接支持或反对该命题、时间与适用范围是否一致、二手网页是否实际引用同一原始来源。方向错误、断章取义或仅相关但不支持均阻止正式发布。

## 沙盘验收

沙盘必须满足：

- 首次进入默认显示当前条件化建议和最多三个最脆弱条件，用户无需先理解或编辑完整因果图。
- 用户可以选择一个业务变量或情景完成压力测试；结果显示业务单位、相对基线变化、关键影响路径和建议保持/翻转/证据不足。
- 建议保持时显示已测试范围；建议翻转时显示翻转到的选项、阈值或硬约束；证据不足时提供验证行动，不伪造阈值。
- 用户可以从压力测试结果生成候选验证行动、保存命名实验分支，并按需展开完整模型。
- 完整模型至少 8 个节点、10 条边。
- 至少包含 1 个 `decision`、2 个 `lever/external/unknown`、1 个 `constraint`、2 个 `outcome/indicator` 节点；其余按案例需要使用统一八类枚举。
- 每条边有方向、强度、延迟和关系质量。
- 用户可以新增、编辑、删除节点和边；高影响低质量项优先审阅，其余项可折叠并安全批量确认。
- 三情景切换会改变结果或明确说明没有变化原因。
- 敏感性排序能指出前 3 个关键变量。
- 页面明确标注“不代表精确预测”。
- 业务单位进入引擎后使用 normalized baseline，禁止归一化状态减原始月份/金额。
- `ScoreDefinition` 明确关联选项、结果、目标、风险和约束，不根据标签猜测。
- 相同 graph/strategy/scenario/engine 版本重复运行结果完全相同。
- 用户可创建分支、比较版本并非破坏性回滚；回滚后的新版本保留来源历史。
- 非收敛、饱和和无效数值有明确状态，不能用于正式推荐。

## 自定义因素与即时预览验收

- 用户只能在完整模型中看到“添加影响因素”，默认压力测试首屏仍保持最多三个脆弱条件和单一主任务。
- 自然语言“地方预算审批稳定性会影响采购周期”生成待审阅 `FactorCandidate`，不直接修改 GraphVersion。
- 候选包含 type、unit、baseline/current/min/max、controllability、evidenceStatus、rationale；用户添加入口拒绝 `decision` 类型。
- 无可追溯证据时默认 `assumed | unknown`，UI 显示待验证警告，API 不允许伪装为 supported。
- 每条建议关系都必须确认、修改或否决；存在未审阅关系时返回 `RELATIONSHIP_REVIEW_REQUIRED`。
- 两个客户端基于同一 revision 修改工作副本时，后提交者得到 `WORKING_COPY_REVISION_CONFLICT`，历史版本不被覆盖。
- P0 fixture 图在稳定测试环境中连续运行预览，目标 `p95 <= 1s`；超时显示失败与重试，不沿用旧结果。
- 相同 working-copy revision、strategy、scenario、score definition、engine 和 steps 产生完全相同的预览。
- 工作副本变化后旧预览标记 stale；尝试用于 PDF、Decision 或正式推荐返回 `PREVIEW_NOT_FORMAL` 或 `PREVIEW_STALE`。
- 保存工作副本只创建新的 immutable draft GraphVersion；formal run 仍拒绝未 confirmed 版本。
- 键盘可完成因素输入、候选审阅和关系审阅；状态不只依赖颜色，窄屏不产生横向溢出。
## Agent、工具、MCP 与 Skill 验收

测试类型参考 Hermes 已有 registry、delegate、MCP 和 Skill 测试：

- Tool Registry：未知工具、schema 错误、availability 失败、handler 异常和名称冲突返回结构化错误。
- Delegate：子任务工具权限只能是父任务子集，并发、深度、迭代和预算达到上限后停止；父任务只收到结构化摘要和 tool trace。
- MCP：审核连接器 schema 转换、命名空间、超时、错误清洗、连接断开和动态刷新；P0 拒绝任意 URL、stdio/npx 和写工具。
- Skill Loader：frontmatter、版本、内容哈希、缺字段、重复 ID、未发布包和路径穿越。
- Strategic Lens schema：canonical lens id 与 ways strict stage output 一致，五类 payload 数量/contains 约束、角色 phase、内容 hash 和 report ID 集合均通过。
- Ways Installer：只从 `ways/hardtech-market-direction/1.1.0` 安装，规范化哈希稳定；runtime `method-packs` 手改、同版本不同哈希或运行时直读 ways 均阻断。
- Safety Anchor：作为 Critic 子阶段执行，重要发现必须改变正文、条件、质量状态或进入 escalation。

## Web 事件与恢复验收

参考 Open WebUI 的 status/task/tool/citation/confirmation 交互，验证：

- `agent.status` 和 `agent.task` 按 Run/消息作用域更新，不串到其他 Case。
- `tool.call` 显示运行、完成、错误、耗时和 `live/cached/fixture`，不泄露 Key 或原始敏感正文。
- `citation.added` 可跳到 Evidence Drawer 和关联 Claim。
- `user.confirmation.required` 的取消、确认、输入和恢复结果一致。
- SSE 断线后用 `Last-Event-ID` 重连，历史事件不重复、任务状态不倒退。

## 降级验收

| 故障 | 验收 |
|---|---|
| 模型在备用配置后仍不可用 | 用户显式启用 fixture provider；外部响应确定化，但 Worker、质量门、报告和沙盘仍真实执行 |
| 搜索不可用 | 使用缓存证据，事件和 UI 标注缓存 |
| Exa Key 失效或额度耗尽 | 自动切换 Tavily；备用也不可用时使用缓存证据 |
| Firecrawl Key 失效或额度耗尽 | 使用基础抓取、已有 RawArtifact 或缓存正文 |
| PDF 生成失败 | HTML 仍可用，PDF Export 显示 `failed` 并允许修复后重试；不以预生成 PDF 冒充本次导出 |
| Worker 中断 | 重启后可恢复或显示手动重试 |
| SSE 断线 | 前端可重新连接并读取历史事件 |
| DeepSeek JSON 空内容 | 空内容/schema 检测后最多一次修复重试；仍失败时阻断或由用户显式 fixture |

## 风险登记表

| 风险 | 严重度 | 触发信号 | 缓解措施 | 验收方式 |
|---|---|---|---|---|
| 数据模型变动导致前后端阻塞 | 高 | 字段频繁改名 | 第 12 小时冻结核心 ID/版本/originMode，第 30 小时冻结运行、事件与最小 simulationSeeds 子合同，第 48 小时冻结完整报告合同；新增字段保持向后兼容 | Mock 数据可持续跑通 |
| 报告内容看似完整但无引用 | 高 | 引用列表为空 | 质量门强制引用检查 | 发布前校验失败 |
| 沙盘结论被误解为预测 | 中 | 文案出现确定预测 | 固定限制说明和 UI 提示 | 文案审查 |
| Run 状态丢失 | 高 | 页面刷新后进度消失 | `analysis_runs` 与 `analysis_events` 持久化 | 刷新后恢复进度 |
| 演示现场网络不稳 | 高 | 搜索或模型超时 | 预置 Case 输入、真实缓存证据、显式 fixture provider；HTML 保底 | 断网演练通过且核心状态机真实运行 |
| AI 辅助切片失去可运行状态 | 高 | 连续多个任务只有代码没有端到端结果 | 每个切片同时交付 schema、API、UI、fixture 和测试 | 每个时间段结束运行金路径 |
| 迁移效果被过早宣称 | 高 | 少于两个授权案例、条件不一致或用逐字/模型投票比较 | 固定 manifest/rubric 和声明 gate；未签署前只说“转换合同完成” | 两案例 parity 报告逐项含证据，球形机器人金路径独立通过 |
| 连接器凭证泄露 | 高 | 响应、SSE 或日志出现 Key | 服务端加密、统一脱敏、负面测试 | 搜索所有测试日志与响应 |
| 发布资产未完成 | 高 | 第 60 小时仍在增加功能 | 第 60 小时冻结功能，最后 12 小时专用于验收、部署与展示 | 72 小时交付清单 |

## 验收清单

- 新目录文档齐全，团队能按文档拆任务。
- P0 链路在预置案例上 100% 可跑。
- full 球形机器人链路持久化并可读取五项行为合格的 StrategicLensArtifact；focused 不创建；lens set 变化只能 replacement Charter + new Run。
- legacy parity 只有在至少两个获产品授权且去标识化的 `探讨` 成功实验于固定同一模型/资料条件下完成六维比较后才可通过；不比较逐字文本，不把模型投票当概率。
- 当前 `ways` 中的脑机接口 seed/angel 文件是资源尺度 parity eval 规格，不是旧框架与 Ludus 的实际双轨执行结果；legacy parity 仍保持 pending。
- 球形机器人仍是 P0 金路径；parity suite 为 pending/failed 时不阻断其他 P0 gate，但所有对外文案只能说“转换合同完成”，不得声称已复现原效果。
- 案例列表/创建、PDF/TXT/Markdown 文件入口、CandidateReview、ArgumentTree、Run cancel、HTML/PDF 导出、图确认、决定与 Review 保存/读取均有自动化验收。
- 自由输入案例至少可完成创建、澄清和非正式快速分析；unsupported 场景不能生成报告草稿。
- 所有关键失败路径有 UI 状态。
- 生成内容不会混淆事实、假设和判断。
- 最终决定保存后可回看当时版本、报告和沙盘。
- 至少一个审核目录 BYOK 连接器可添加，且所有连接器故障状态可验证。
- 对话入口、三档分析深度、方法理由、Charter 冻结和 unsupported 阻断均通过验收。
- 5 分钟 Web 演示、60-90 秒宣传录屏、6 张截图、一页说明和备用录屏齐备。
- fixture 验证从 `fixtures/spherical-robot/seed/` 与 `external/` 运行真实核心链路，只用 `expected/` 比较；lens 正负样例唯一位于 `expected/strategic-lenses/` 与 `negative/strategic-lenses/`，运行时代码读取 `expected/` 或 `negative/` 即发布失败。

## 决策操作系统工程红线验收（CCR-20260719-002 / CCR-20260721-003）

### 数据、责任与可追溯

- `ResponsibilityStamp` 必须拒绝 analysis actor 伪装为 human，也拒绝 human/analysis 对象被标记成 unknown；
- imported/model/user Claim 均必须引用至少一个 SourceSpan；用户输入先成为 `pre_run human_input` SourceRecord/Span，Run 创建时冻结为新的 `run_frozen` 记录；pre-run 不带 AnalysisRun，run-frozen 必须带 AnalysisRun 与来源引用；
- SourceSpan locator 与 quoteHash 必须能在冻结材料快照中复验；跨 Workspace/Case/Run 引用返回 404 或结构化校验失败；
- JudgmentSet 必须引用 supporting/opposing Claim、Unknown 和 Challenge；DissentRecord 不得为空壳或未被 Synthesis 消费。

### 生命周期、签署与不可变决定

- 精确合法路径为 `draft→scoped→ready→running→review→pending_signoff→decided→monitoring`；跨阶段跳转失败；
- chaotic/disorder Cynefin gate 默认不能进入 ready/running；override 必须是人类、带 reason 且被冻结；
- 工具注册表和 MCP catalog 精确证明不存在 `sign_decision`、`transition_to_decided`、`decision_record_update` 等价能力；
- 未签署、过期、payloadHash/nonce/version 不匹配、session revoked/expired、membership 无效、缺少 `sign` capability 或非 human signer 的请求不能创建 DecisionRecord；
- `signoff.signed`、DecisionRecord insert 与 Case projection 必须在同一事务；
- DecisionRecord UPDATE/DELETE 被数据库与 repository 拒绝；revision 创建新记录并保留旧 hash。

### Run、报告与九验证

- 没有 qualifying Run 时不能创建 Report；Run 未 ready 或任一 validator blocker 存在时不能 ready/publish/export/from-report/signoff；
- DeepAnalysis 正式 schema 不含 chat `messages[]` 主字段；Request 与 `06/26` 字段精确一致，Result 只返回 JudgmentSet、DissentRecord、DraftRecommendation、Unknown、V1-V9、quality gate 与 provenance 的持久化 ID/hash；
- V1-V9 必须是精确集合，每项有版本、executionMode、artifact refs 与 outcome；block 不能被多数 pass 抵消；
- 确定性 validator 不调用模型；模型辅助 validator 经 provider adapter，模型名不进入领域枚举；
- Ways 1.1.0 的所有 JSON Schema 可编译，manifest 引用存在，31 Skill 名称与 13/7/8/1/2 计数一致。
- Recommendation/SystemRecommendation 的 option/abstain 判别联合必须编译；fatal path 精确返回 abstain，DecisionRecord 仍只保存人的合法选择并保留系统 abstain。
- Simulation 属性测试覆盖确定性、inputHash、稳定性、epsilon/maxSteps、归一化 nodeShifts、质量分不进入 effect 和 non-converged fail-closed。

最低专项测试名：

```text
test_no_agent_decision_tool
test_pending_signoff_requires_human_signature
test_decision_record_update_delete_rejected
test_decision_revision_supersedes_without_overwrite
test_no_run_no_report
test_report_ready_requires_ready_run_and_validation
test_claim_requires_source_span
test_source_span_quote_hash_matches_snapshot
test_pre_run_source_freezes_into_run_scoped_source
test_revoked_session_and_missing_sign_capability_rejected
test_signoff_payload_hash_covers_all_fields
test_system_recommendation_abstains_on_fatal_path
test_deep_analysis_request_result_shapes_match_06_and_26
test_simulation_input_hash_and_replay_determinism
test_simulation_quality_score_does_not_change_effect
test_simulation_non_convergence_blocks_formal_recommendation
test_cynefin_chaotic_and_disorder_block_formal_run
test_deep_analysis_contract_has_no_chat_messages
test_nine_validator_contracts_exact_set
test_validation_blocker_cannot_be_outvoted
```
