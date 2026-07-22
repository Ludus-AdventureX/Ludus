# 27. MVP 与黑客松原型开工准备审计

> **修复前审计 / superseded：** 本文是 2026-07-21 合同修复前的问题清单。所列 blocker 的关闭证据、验证结果和最终 Go/No-Go 以 `28-contract-repair-completion-audit-20260721.md` 为准；本文中的旧 IA、视觉和环境结论不得继续驱动实现。

- 审计日期：2026-07-21（Asia/Shanghai）
- 审计对象：`decision-lab-product-plan` 全部主文档、CCR、Agent manifest、工程模板、`decision-lab/` 当前仓库状态、`look/` 视觉基线和 Gate 0 环境
- 审计结论：**Conditional Go — Contract Repair First**

## 1. 结论先行

### 现在可以开始

1. 修订 canonical 合同、清理文档污染和冻结命名；
2. 初始化独立 Git 仓库、根 `.gitignore`、monorepo 骨架和 CI；
3. 建立 OpenAPI/Pydantic/TypeScript 单向生成链；
4. 建立离线 fixture、方法包安装器、测试框架和最小健康检查；
5. 实现不依赖争议 DTO 的基础设施切片。

### 现在不能开始

1. 不能把当前 `06/10/26` 当作无冲突合同并行生成数据库、API、Worker 和前端；
2. 不能启动正式 72 小时黑客松计时；
3. 不能开始 live DeepSeek/Postgres 金路径集成并宣称 Gate 0 已通过；
4. 不能按当前 18/19 个任务直接并行调度到 Release；
5. 不能宣称当前文档已经达到“完整 P0 可直接实现”的状态。

### Go / No-Go

| 事项 | 结论 |
|---|---|
| 合同修复与 Phase 0 | **Go** |
| 离线工程骨架、fixture、测试框架 | **Go** |
| 黑客松窄切片原型 | **Conditional Go**，先冻结本文第 8 节切片和关键 DTO |
| 按当前完整 P0 并行实现 | **No-Go** |
| 正式 72 小时计时 | **No-Go** |
| live DeepSeek/Postgres/BYOK 集成 | **No-Go**，Gate 0 未通过 |
| 对外发布或宣传完整 MVP | **No-Go** |

## 2. 发布阻断级问题

### B1. `SourceRecord` 不能表达 Run 前的用户输入

`06-data-model.md:1691-1696` 要求所有 `SourceRecord` 都有必填 `analysisRunId` 和 `rawArtifactId`，但 `06-data-model.md:1919` 又要求用户输入先转换为 `human_input SourceRecord/SourceSpan`。聊天消息和 Case 字段通常在正式 Run 创建前存在，也不一定有 `RawArtifact`。

**必须修复：** 将 Source 建模为判别联合，或明确 `PreRunSourceRecord -> FrozenRunSourceRecord` 的冻结转换；不要靠空字符串、伪造 Run 或虚构 RawArtifact 兼容。

### B2. canonical ID 命名漂移

`06-data-model.md` 同时使用 `decisionCaseId/caseId` 和 `analysisRunId/runId`。`CaseVersion` 使用 `decisionCaseId`，`AnalysisEvent` 使用 `caseId/runId`，Report、Graph、Decision 又回到 `caseId`。该文档同时声明禁止平行 DTO 和别名，因此当前状态无法安全生成 ORM/Pydantic/OpenAPI/TypeScript。

**必须修复：** 在全域只保留一套字段名；建议 wire/domain 都统一为 `decisionCaseId`、`analysisRunId`，数据库列使用 snake_case 映射。

### B3. `06` 与 `26` 的 DeepAnalysis I/O 互不兼容

- `26:160-174`：`method: { id, version, contentHash }`；
- `06:1885-1900`：`methodId/methodVersion/methodContentHash`；
- `26:180-188`：结果内嵌 `JudgmentSet/DissentRecord/DraftRecommendation`，并使用 `runId`；
- `06:1903-1914`：结果返回对象 ID，并使用 `analysisRunId`。

**必须修复：** 通过新的 CCR 选择一种 wire contract。建议 Engine 返回已持久化对象 ID 和不可变 hash，完整对象通过明确读取接口获取。

### B4. 权限模型没有进入 canonical schema

`17-product-design-v2.md:55-70` 要求 `User -> WorkspaceMembership -> Workspace`，P0 角色为 `owner/member`；`18` 和 `26` 又要求 contributor/reviewer/signer capability。但 `06-data-model.md` 没有 User、WorkspaceMembership、session 或 capability 的 canonical 持久化模型。

**必须修复：** 在 `06` 增加最小认证与授权模型，并明确 membership role、signer capability、session/nonce、撤销和审计边界。`18` 中的 Python dataclass 不能替代 canonical schema。

### B5. SignoffRequest 没有冻结实际签署内容

`10-api-and-events.md:690-713` 的签署请求包含 Graph/Simulation 来源、conditions、thresholds、exitCriteria、actionItems、leadingIndicators 和 reviewDate；`06-data-model.md:1841-1859` 的 `SignoffRequest` 没有保存这些字段，也没有保存 Graph/Simulation 来源。

**必须修复：** 定义不可变 `SignoffPayload`，保存完整 canonical payload 或 `payloadHash + immutable payload artifact`；同时定义 nonce 签发、读取、失效、重放拒绝和事务原子性。

### B6. Agent manifest 的 Release 依赖图错误

`18-detailed-development-plan.md:1710` 明确 Task 19 必须在 Task 17/18 验收前完成，但 `agent-work-manifest.yaml:351-354` 的 Task 17 不依赖 Task 19，Task 18（369-372）只依赖 Task 1 和 Task 17。

**必须修复：** 至少令 Task 17 显式依赖 Task 19，Task 18 依赖 Task 17 和 Task 19。

### B7. Agent manifest 的写入范围不可执行

- Task 2 的详细计划创建 `services/api/app/db.py`、`models.py`、`types.py`（`18:481-487`），manifest 却授权 `services/api/app/db/**` 和 `models/**`（`agent-work-manifest.yaml:145-146`），不能匹配这些文件；
- Task 19 只声明一个 `secondary_owner: case_api_data`，却把 Reports、Agents、Ways、Web Decision 等多个 owner 的路径放入同一 `secondary_write_scope`；
- 详细计划与 manifest 混用 `tenancy/workspaces`、`conversations/discussion` 等目录名。

**必须修复：** 以真实文件路径重写 scope；每个路径只能有一个 owner；Task 19 拆成 19A-19D，按数据、Agent、Web、QA 分配互不重叠的写集合。

### B8. `07-agent-workflow.md` 被 PowerShell 片段污染

`07-agent-workflow.md:140-141` 混入 PowerShell here-string 终止符和 `$section07` 赋值语句。

**必须修复：** 删除污染并重新执行 Markdown、代码块和合同 token 验证。

### B9. 活动方法版本仍漂移到 `1.0.0`

canonical 当前版本是 `hardtech-market-direction@1.1.0`，但 `10-api-and-events.md:249,280,328` 和 `18-detailed-development-plan.md:123,125` 仍使用 `1.0.0`。

**必须修复：** 历史目录可以保留 1.0.0，但所有活动路由、Charter、示例、安装目标和测试统一到 1.1.0。

### B10. `08` 的完整 StructuredReport 示例不满足 `06`

`08:434-494` 的 `residualUncertainty`、`candidateNodes`、`candidateEdges` 缺少 `06` 中多项必填字段，例如 Workspace/Case scope、baseline/current/min/max、controllability、evidenceQualityScore、assumptionIds、rationale、status、strength、delaySteps 和 relationshipQualityScore。

**必须修复：** 不维护手写平行示例；从 canonical schema 生成示例并加入 schema validation test。

### B11. 数据模型不支持系统 abstain

`04-decision-methodology.md:20` 允许所有选项 `fatal_fail` 时不给出市场赢家，但 `DraftRecommendation.recommendedOptionId`（`06:1831`）和 `DecisionRecord.systemRecommendedOptionId`（`06:1513`）都是必填。

**必须修复：** 使用判别联合表达 `recommendation | abstain`，或将“继续研究/暂缓”定义为每个正式 Case 必有的 canonical option；不要用空字符串。

### B12. 前端主工作区合同冲突

`11-frontend-spec.md:16-24` 写“五个 canonical 主工作区”，实际只列四个，并声明 Decision 是抽屉；同文档 `235-243` 又定义“页面五：决定与复盘”，并称其为 canonical 主工作区。`24:284-288` 也要求独立 Decision/Review 主工作区；`decision-lab/AGENTS.md:225` 则写四个核心工作区。

**必须修复：** 冻结一种 IA。建议黑客松使用“四页 + canonical Decision drawer”，Review 独立页延后；如果保留第五页，则同步路由、E2E、manifest 和 AGENTS。

## 3. 高风险技术与工程问题

### H1. SimulationRun 不能完整重放

评分公式使用 `risk_tolerance`（`09:264-267`），但 `SimulationRun`（`06:1466-1484`）没有冻结风险偏好值或 DecisionMakerProfile/Charter preference 版本。

**建议：** 在 RunManifest 或 SimulationRun 保存实际 `riskTolerance`、偏好版本和输入 hash。

### H2. 沙盘数值语义需要收敛

- `relationshipQualityScore` 被直接乘入因果效应（`09:105-113`），把“证据/解释质量”变成“效应强度衰减”；
- 文档声称阻尼使带环图收敛，但固定阻尼不自动保证所有图收敛；
- 伪代码没有实现 epsilon 判断，正文却要求 `converged/max_steps`（`09:162-203`）；
- `ScenarioVersion.nodeShifts` 没说明是业务单位还是归一化单位；
- ±10% 敏感性对零值、边界值和非比例变量不稳健。

**建议：** 明确 P0 是启发式压力测试，不是预测模型；分离 effect strength 与 evidence quality；定义归一化、收敛容差、边界处理和数值属性测试。

### H3. API 读取面不足

`10:40-101` 缺少清晰的 DecisionRecord GET、SimulationRun GET、报告历史列表、图/分支历史列表和 SignoffRequest 读取接口。刷新页面或跨页面回到历史对象时会依赖未定义 API。

错误码表也没有统一 HTTP status 映射；`ANALYSIS_RUN_ALREADY_ACTIVE` 同时表达业务冲突和幂等命中，语义应拆分。

### H4. 安全设计仍有实现级空白

- 登录也要求 double-submit CSRF，但没有定义匿名 CSRF token 的签发/刷新流程；
- JWT 含 `session_id`，没有 session 表、撤销和被盗 token 处理合同；
- BYOK 只写“服务端加密”，没有算法、master-key 版本、AAD 和轮换策略；
- 限流要求存在，但未锁定共享存储和多进程语义；
- SSRF 要求 DNS 后连已校验地址，但未给出 TLS SNI/Host 保持与 DNS rebinding 实施范式；
- TXT/Markdown 不存在像 PDF 那样稳定的 magic bytes，应改为编码、内容和解析策略；
- Task 1 未创建根 `.gitignore`，之后直接 `git add .`（`18:475`）。

**建议：** 黑客松原型若来不及安全实现，应删除任意 URL、BYOK 和非必要上传面，而不是实现不完整的安全版本。

### H5. 72 小时完整 P0 规模过大

`23:19-32` 将认证、多租户、方法路由、持久化 Run、恢复、五透镜、报告、HTML/PDF、图审阅、情景、敏感性、Decision 和完整安全门都列为不可降级核心；Task 18 还包括文件、BYOK、分支比较、回滚、Review、部署和宣传资产。

6 Agent 档实际只有 4 个专职实现泳道、1 个 Lead 和 1 个只提交缺陷 handoff 的 QA；计划没有足够集成缓冲。当前范围更接近 Alpha vertical slice，而不是 72 小时原型。

### H6. 视觉基线未冻结

- `24` 锁定 V5.2 Paper/Graphite/System；
- `look/README.md` 已是 V7 十主题；
- `look/HEAD` 是进行中的 Logo/Icon 工作；
- `decision-lab/AGENTS.md:227` 引入“氧化铜”活动色，与 `24` 的酒红/烟墨语义体系不一致。

**建议：** 黑客松只实现 Paper + Graphite 两主题；V7 十主题作为活动后实验，不进入 P0 acceptance。

### H7. Paper tertiary 文本对比度不足

按 `24:73,81` 的 `#888074` 对 `#eee8dc` 计算，对比度约 **3.20:1**，不满足普通正文 WCAG AA 4.5:1。Paper secondary 与 analysis 仅略高于 4.5。

**建议：** tertiary 仅用于非文本装饰/大号文本，或加深 token；加入自动 contrast test。

### H8. Verifier 只检查 token，且错误依赖视觉 HEAD

当前执行：

```text
decision-os-contracts: FAIL: ...\look\HEAD: missing 'Status: completed'
```

`verify_decision_os_contracts.py:35` 强制无关 Logo 工作必须 completed，导致 schema 验证被视觉工作状态阻断。脚本还只检查字符串 token，无法发现 DeepAnalysis shape、ID、signoff payload 和 DTO 漂移。

**建议：** 拆成 `verify_contract_semantics.py`、`verify_visual_baseline.py`、`verify_release_gate.py`，schema 使用真实 parser/validator。

### H9. 外部服务资料有漂移

截至 2026-07-21 的官方资料核验：

- DeepSeek `deepseek-v4-pro`、thinking/tool-call 以及 `deepseek-chat/deepseek-reasoner` 于 2026-07-24 弃用的主张仍成立；
- Firecrawl 免费 1,000 credits 和 Tavily 免费 1,000 credits 的量级仍成立；
- Exa 当前 Free Tier 表述是每月赠送美元 credits，并按操作计费，不再是固定“每月最多 20,000 次请求”；
- Firecrawl 当前官方 remote MCP 配置要求 API key，`19:23` 的“按 IP 限速免 Key MCP”不应继续作为事实。

这些变化不阻止 P0 使用直接 HTTP Provider Adapter，但 `19` 的免费额度表必须更新。

### H10. 文档治理与历史计划容易误导 Agent

- `18:3` 强制依赖 `superpowers:subagent-driven-development` 或 `executing-plans`，不应成为项目必需运行机制；
- `docs/superpowers/plans/2026-07-13-ludus-product-plan-rewrite.md` 仍有 96 个未勾选任务，未标记 archived/completed；
- `GPT-5.6-sol` 在多文档出现，但没有 runtime provider id、配置来源、成本和可用性合同；
- README 和 `12:56` 声称 canonical baseline 无已知冲突，与当前事实不符。

## 4. 逐份文档审计结果

| 文档 | 状态 | 结论与主要问题 |
|---|---|---|
| `README.md` | 高风险 | 导航清楚，但 2026-07-14 Gate 0 状态已过期，并错误暗示合同已足够就绪；应链接本审计并更新状态。 |
| `01-product-vision.md` | 可保留 | 定位和可信度原则清楚；P0 成功指标过宽，应为黑客松切片另设更窄指标。 |
| `02-prd-and-user-flows.md` | 阻断 | Mermaid 重复定义节点 `N`（80/82）；P0 与黑客松切片未分层。 |
| `03-existing-assets-assessment.md` | 需修订 | 资产边界总体可信；“72 小时仍需实现”的规模低估了领域系统的新建工作，并固定四页 IA。 |
| `04-decision-methodology.md` | 需联动修订 | 方法论质量较高；abstain/fatal-fail 没落到数据和 API 合同。 |
| `05-system-architecture.md` | 条件通过 | 模块、Postgres queue、SSE/恢复方向合理；必须等待 `06/10/26` 合同冻结。 |
| `06-data-model.md` | 阻断 | Source、ID、权限、Signoff、abstain、DeepAnalysis 均有 canonical 缺陷。 |
| `07-agent-workflow.md` | 阻断 | 有脚本污染；模型命名和 validator 实现边界需参数化。 |
| `08-deep-research-pipeline.md` | 阻断 | StructuredReport/SimulationSeeds 示例与 `06` 不一致。 |
| `09-simulation-engine.md` | 高风险 | 可做原型启发式引擎，但重放输入、数值单位、收敛和证据质量语义未闭合。 |
| `10-api-and-events.md` | 阻断 | Signoff payload、方法版本、读取 API、错误 status mapping 未闭合。 |
| `11-frontend-spec.md` | 阻断 | 四页/五页/Decision drawer 自相矛盾；依赖未定义读取 API。 |
| `12-72-hour-execution-plan.md` | 阻断 | Gate 0 未通过；“canonical baseline 无已知冲突”不成立；完整 72h 范围不可信。 |
| `13-testing-and-acceptance.md` | 条件通过 | 测试面完整，是优势；需加入 signoff payload、pre-run source、membership、abstain、数值性质和 API refresh 测试。 |
| `14-demo-script.md` | 需修订 | 演示链过长，依赖大量 stretch 功能；应改成 5 分钟窄金路径并准备 fixture/live 双轨。 |
| `15-open-source-references.md` | 条件通过 | 许可策略谨慎；目标授权摘要和 NOTICE 尚未落盘。 |
| `16-post-hackathon-roadmap.md` | 基本通过 | 适合作为活动后路线；需把从完整 P0 移出的 stretch 明确迁入。 |
| `17-product-design-v2.md` | 阻断 | 产品模型清楚，但 Membership/capability 没同步到 `06`；完整 P0 范围仍过宽。 |
| `18-detailed-development-plan.md` | 阻断 | 路径、manifest、版本、`.gitignore`、安全实现和 72h 容量均有问题；不应直接照单执行。 |
| `19-mcp-data-sources-and-launch-constraints.md` | 需修订 | DeepSeek 主合同当前有效；Exa 免费额度和 Firecrawl 免 Key MCP 信息已漂移。 |
| `20-conversation-led-method-routing.md` | 基本通过 | 三档与 Charter 逻辑清楚，1.1.0 一致；等待 canonical DTO 冻结。 |
| `21-existing-asset-reuse-and-conversion.md` | 条件通过 | 复用/重写边界较清楚；授权摘要和 `THIRD_PARTY_NOTICES.md` 缺失，阻止发布而非阻止离线骨架。 |
| `22-contract-generation-and-security-plan.md` | 高风险 | 安全目标正确，但 CSRF/session/BYOK/rate-limit/SSRF/TXT 细节尚未成为可实现决定。 |
| `23-multi-agent-capacity-execution-plan.md` | 阻断 | 完整 P0 的 72h 容量模型不可信；Task 19 依赖未进入 manifest。 |
| `24-frontend-visual-theme.md` | 阻断 | 与 V7/AGENTS/IA 漂移；Paper tertiary 对比度不合格。 |
| `25-demo-development-readiness-audit.md` | 过期 | 文件数 34 已变为 77；合同冻结结论已被后续 CCR 和当前冲突推翻，应被本文取代。 |
| `26-decision-os-invariants-and-agent-engine-contract.md` | 阻断 | 原则正确，但 DeepAnalysis I/O 与 `06` 冲突，权限能力没有 canonical schema。 |
| `agent-work-manifest.yaml` | 阻断 | YAML 可解析，但依赖图、owner、scope 和详细计划路径不一致。 |
| `CCR-20260716-001.md` | 部分落地 | 自定义因素边界合理，但 `08` 示例和完整 DTO 仍未完全同步。 |
| `CCR-20260719-002.md` | 部分落地 | 决策责任红线正确，但同步不完整，导致 `06/26/manifest` 冲突。 |
| `docs/audits/*` | 参考 | 分析有价值，但不能替代最新 canonical readiness 审计。 |
| `docs/superpowers/*` | 应归档 | 历史重写计划状态不清，可能被误当为当前实施计划。 |
| `templates/*` | 基本通过 | Markdown/JSON/YAML 模板结构可用；真实授权摘要尚未生成。 |

## 5. 当前 Gate 0 事实

### 仓库

- `decision-lab` 没有独立 `.git`，当前仍处于父仓库 `No commits yet on master`；
- 不存在 `package.json`、`pnpm-workspace.yaml`、`compose.yaml`、`.env.example`；
- 不存在 `apps/`、`services/`、`packages/`、`fixtures/`、`method-packs/`；
- 不存在 `docs/asset-authorizations/` 和 `THIRD_PARTY_NOTICES.md`；
- 当前共有 77 个文件，主要是 `AGENTS.md`、Ways 1.0.0/1.1.0 和 verifier。

### 工具与服务

```text
uv: missing
python default: 3.14.3
py -3.12: 3.12.7
node: v22.20.0
pnpm: 9.14.4
Docker CLI: 29.4.3
Docker Compose: v5.1.3
Docker daemon: unavailable
```

### 仅检查环境变量存在性，未读取值

```text
MODEL_API_KEY=missing
EXA_API_KEY=present
FIRECRAWL_API_KEY=missing
TAVILY_API_KEY=missing
CONNECTOR_MASTER_KEY=missing
JWT_SECRET=missing
CSRF_SECRET=missing
```

因此 Gate 0 明确失败。

## 6. 已执行的静态验证

| 验证 | 结果 |
|---|---|
| Markdown 内本地文件链接 | 33 个，0 个断链 |
| Markdown `json` 代码块 | 51 个，全部可由 `json.loads` 解析 |
| YAML 文件 | 2 个，均可由 PyYAML 解析 |
| Decision OS verifier | FAIL，错误依赖 `look/HEAD Status: completed` |
| Docker daemon | FAIL，Docker Desktop Linux engine pipe 不存在 |
| canonical 语义一致性 | FAIL，存在本报告列出的跨文档冲突 |

“JSON/YAML 可解析”只证明语法正确，不证明 DTO 与 canonical schema 一致。

## 7. 开工前最小修复清单

按顺序完成，未完成前不启动正式计时：

1. 新增 CCR，冻结 `06/10/26` 的 ID、DeepAnalysis I/O、Source、Signoff、权限和 abstain；
2. 从 canonical schema 自动生成 `08` 示例，消除手写平行 DTO；
3. 修复 `07` 污染和所有活动 `1.0.0` 引用；
4. 冻结前端 IA：四页 + drawer，或五页；同步 `11/24/AGENTS/E2E/manifest`；
5. 将完整 P0 与 Hackathon Prototype Slice 分开；
6. 拆分 Task 19，修正 manifest 依赖和 owner/write scope；
7. 补根 `.gitignore`，再初始化独立 Git 和首个基线 commit；
8. 关闭 session/BYOK/rate-limit/SSRF/TXT 实现决策；
9. 更新 `19` 的官方额度/MCP 信息；
10. 重写 verifier，使其验证 schema/manifest，而不是依赖进行中的 Logo HEAD；
11. 启动 Docker/Postgres，安装 uv，创建 secrets，完成 DeepSeek capability probe；
12. 重新生成一份 Gate 0 报告，全部通过后才启动 72/108/144 小时计时。

## 8. 推荐的 Hackathon Prototype Slice

### 必做金路径

```text
预置 Case
→ 用户确认最小范围与 Charter
→ fixture 或已验证 live provider 创建正式 Run
→ 生成可点击来源的 Evidence/Claim
→ 输出一份条件化报告与一份反方意见
→ 对一个关键变量执行压力测试
→ 显示建议保持 / 翻转 / 暂缓及原因
→ 人类签署冻结的 SignoffPayload
→ 保存不可变 DecisionRecord
```

### 原型必须保留

- Human / Analysis / Unknown 责任边界；
- no-run-no-report；
- live/cached/fixture 明示；
- 至少一个可校验 SourceSpan；
- 人类签署和 append-only Decision；
- 单一 canonical DTO 生成链；
- 可重复的 fixture E2E。

### Stretch

- 五透镜全部独立 UI；
- PDF；
- 完整图编辑；
- 分支、比较和回滚；
- BYOK UI；
- Review 完整页；
- 十主题；
- 多文件格式；
- 多 Workspace UI。

如果为了黑客松暂时不实现多租户/BYOK/任意上传，必须从外部接口和宣传中移除这些能力，而不是用不安全的占位实现冒充完成。

## 9. 最终判断

你已经具备较成熟的产品方向、方法论、状态机、测试意识和可信度原则，**不是从零开始**；但当前文档体系仍处于“多个高质量设计增量叠加后尚未完全归一”的状态。

因此正确动作不是停止开发，而是：

> **立即进入 0.5–1 天的合同修复与 Phase 0，然后开发窄切片原型；不要直接按当前完整 P0 开启 72 小时计时。**

完成 B1-B12、修正 manifest，并重新通过 Gate 0 后，才适合进入完整 MVP 的多泳道实现。
