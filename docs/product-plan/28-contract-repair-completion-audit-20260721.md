# 28. 合同修复完成审计与开工结论

- 状态：**accepted / contract-ready**
- 权威日期：**2026-07-21（星期二，Asia/Shanghai）**
- 审计对象：`decision-lab-product-plan` 活动文档、CCR、Agent manifest、`decision-lab/ways/hardtech-market-direction@1.1.0`、合同验证器与 `look/` 固定设计源
- 前置审计：[27-mvp-and-hackathon-readiness-audit-20260721.md](27-mvp-and-hackathon-readiness-audit-20260721.md)
- 接受变更：[CCR-20260721-003](docs/contract-changes/CCR-20260721-003.md)
- 恢复备份：`../decision-lab-product-plan-backup-20260721-before-contract-repair.zip`

> 本文取代 27 的修复前 Go/No-Go。27 继续作为问题发现记录保留，不再作为实施合同。

## 1. 最终结论

| 事项 | 结论 | 条件 |
|---|---|---|
| 文档与 canonical 合同基线 | **GO** | 12 项发布阻断均已关闭，静态合同验证通过 |
| Hackathon Prototype 离线 bootstrap/开发 | **GO，可立即开始** | 先执行 Task 1 / Task 1W，不启动正式容量计时 |
| 正式 72 小时黑客松计时 | **Conditional GO** | 必须先通过 Gate 0；未通过时只能做不计时离线准备 |
| 完整 MVP 实施 | **GO，可进入实施** | 使用 4 Agent/108 小时、3 Agent/144 小时或根据真实团队重新估算 |
| “完整 MVP 72 小时交付”承诺 | **NO-GO** | 72 小时只承诺 Hackathon Prototype Slice |
| live DeepSeek/Postgres、迁移、Docker、完整 E2E | **尚未验证** | 属于 Gate 0 和实施期验证，不由文档静态审计替代 |
| 对外发布/生产部署 | **NO-GO** | 等待实现、迁移、安全测试、E2E、备份恢复和发布门全部通过 |

因此，可以从现在开始进行黑客松原型的离线工程骨架、合同生成、fixture、Look 快照转换和测试框架开发；但不能把“开始写代码”等同于 Gate 0 已通过，也不能从现在起计算正式 72 小时。

## 2. 12 项发布阻断关闭证据

| ID | 修复前问题 | 状态 | 关闭证据 |
|---|---|---|---|
| B1 | SourceRecord 无法表达 Run 前用户输入 | **Closed** | [06-data-model.md](06-data-model.md) 使用 `SourceScope = pre_run \| run_frozen`、`PreRunSourceRecord/RunFrozenSourceRecord` 与对应 SourceSpan 联合；`rawArtifactId` 改为可选；[13-testing-and-acceptance.md](13-testing-and-acceptance.md) 增加冻结转换测试。 |
| B2 | `caseId/decisionCaseId`、`runId/analysisRunId` 混用 | **Closed** | 活动主文档、README、manifest 与 [decision-lab/AGENTS.md](../../AGENTS.md) 统一 `decisionCaseId/analysisRunId`；验证器对活动合同执行词边界扫描，结果为 0。历史审计与迁移说明不作为 wire contract。 |
| B3 | 06 与 26 的 DeepAnalysisRequest/Result 冲突 | **Closed** | [06-data-model.md](06-data-model.md) 与 [26-decision-os-invariants-and-agent-engine-contract.md](26-decision-os-invariants-and-agent-engine-contract.md) 的 `FormalAnalysisLevel`、`MethodVersionRef`、`DeepAnalysisRequest`、`DeepAnalysisResult` 字段、类型和顺序精确一致；正式结果为 ID/hash-only。 |
| B4 | Membership、session、sign capability 不在 canonical 模型 | **Closed** | [06-data-model.md](06-data-model.md) 增加 `User`、`WorkspaceMembership`、`UserSession`、`WorkspaceRole`、`WorkspaceCapability`；[10-api-and-events.md](10-api-and-events.md) 与 [22-contract-generation-and-security-plan.md](22-contract-generation-and-security-plan.md) 固化活动 session、membership、capability、CSRF、撤销和事务校验。 |
| B5 | SignoffRequest 未冻结实际签署内容 | **Closed** | `SignoffPayload` 精确冻结 18 个决定字段；`SignoffRequest` 保存不可变 payload、payloadHash、nonce；`DecisionRecord` 现在原样保存 payload 与 payloadHash，并把 Judgment/Dissent/Graph/Simulation 等作为不可变索引投影。 |
| B6 | Task 17/18 未依赖发布硬化 Task 19 | **Closed** | [agent-work-manifest.yaml](agent-work-manifest.yaml) 中 Task 17 依赖 Task 19；Task 18 依赖 Task 18A、17、19；Task 19 依赖 19A–19D；DAG 无环。 |
| B7 | owner/write scope 与详细计划不匹配 | **Closed** | [18-detailed-development-plan.md](18-detailed-development-plan.md) 与 manifest 增加 Task 1W、14W、18A；Task 19 分成原 owner 的 19A–19D；6 个 owner、26 个可调度 task/subtask、secondary scope、reserved scope 与 plan anchor 均通过验证。 |
| B8 | 07 混入 PowerShell 残片 | **Closed** | [07-agent-workflow.md](07-agent-workflow.md) 已清除脚本残片；验证器拒绝 `$OutputEncoding`、`Get-Content`、`Set-Content`、`Get-ChildItem` 等污染标记。 |
| B9 | 活动方法版本在 1.0.0/1.1.0 漂移 | **Closed** | `hardtech-market-direction/1.1.0` 的 manifest、diagnostic、quality-gates、10 个 prompt 及全部 schema URN 统一到活动方法版本 1.1.0；1.0.0 目录只读历史。源 Skill 自身版本和文档 `schemaVersion` 是独立历史元数据，不被错误改写。 |
| B10 | 08 StructuredReport 示例不符合 06 | **Closed** | [08-deep-research-pipeline.md](08-deep-research-pipeline.md) 唯一完整报告 JSON 示例与 `StructuredReport` 的 17 个顶层字段集合一致，Recommendation 使用 `outcome` 判别联合。 |
| B11 | 系统可 abstain，但 Recommendation 强制 option | **Closed** | `SystemRecommendation`、`Recommendation`、`DraftRecommendation` 统一 `option \| abstain`；[draft-recommendation.schema.json](../../ways/hardtech-market-direction/1.1.0/schemas/draft-recommendation.schema.json)、[focused-result.schema.json](../../ways/hardtech-market-direction/1.1.0/schemas/focused-result.schema.json)、quality gate 与 synthesis prompt 同步。 |
| B12 | 四页加抽屉与五主工作区冲突 | **Closed** | [11-frontend-spec.md](11-frontend-spec.md) 与 [24-frontend-visual-theme.md](24-frontend-visual-theme.md) 冻结 Look V7 五工作区：问题 `workspace`、证据 `analysis`、判断 `report`、推演 `sandbox`、决定 `decision`；Review 为 dialog/drawer，Case 选择为 Project Drawer，无 Case 为 `empty`。 |

## 3. 修复期间新增发现

本次不是只按原清单机械关闭，还补齐了静态验证发现的三个隐藏问题：

1. `DecisionRecord` 原先声称“原样复制 SignoffPayload”，但接口没有保存 payload，也缺少 Judgment/Dissent 来源。现已把完整 signed payload 和 payloadHash 设为事实源，顶层字段只能作为不可变投影。
2. `draft-recommendation.schema.json` 的 abstain rationale 引用了不存在的 `#/$defs/text`。现已增加严格文本定义，并由本地 `$ref` 解析器验证。
3. Task 15 的 `scripts/verify_fixture.py` 与 Task 19D 的 `scripts/verify_*.py` 形成跨 owner 写域重叠。Task 19D 已收窄为 `scripts/verify_decision_os_contracts.py`。

## 4. 高风险项收敛结果

| 高风险 | 状态 | 已冻结合同 |
|---|---|---|
| Simulation 重放输入不完整 | **Closed at contract level** | SimulationRun 固定 Graph/Strategy/Scenario、ScoreDefinition、Profile、riskTolerance、engineVersion、epsilon、maxSteps 和 inputHash；相同输入确定性重放。 |
| 数值收敛语义不清 | **Closed at contract level** | effect 明确为 `delta × polarity × strength × edgeMultiplier × damping`；`relationshipQualityScore` 不进入 effect；formal 运行使用稳定性充分条件、epsilon/maxSteps 和 fail-closed non-converged 语义。 |
| 安全实施决策未闭合 | **Closed at contract level** | 会话撤销、double-submit CSRF、AES-256-GCM、SSRF URL 规范化、DNS/IP pinning、Host/SNI/证书、重定向复核、Postgres-backed 限流和文本上传边界已进入 13/22/AGENTS。 |
| Look V5.2/V7 漂移 | **Closed** | `look/` 是唯一最终视觉与关键交互源；固定核心 bundle hash 为 `sha256:c5d5d65bf62efdd14e4e3e13d1c70b92f9d6b4cdd4dbd2f652107d84d1a55e98`。 |
| 72 小时范围过大 | **Closed** | 72 小时只承诺 Hackathon Prototype Slice；完整 MVP 使用 108/144 小时档或重估。 |

## 5. `look/` 的生产接入方式

`look/` 不应作为生产 Web 的运行时依赖，也不应通过 `<script>`、iframe、DOM query 或复制原型全局状态直接加载。正确接入是一次性、可审计的设计转换：

1. Task 1W 运行 `scripts/snapshot_look.py`，读取六个核心文件并生成 `design/look-source-manifest.json`；manifest 保存 `look/VERSION`、每文件 SHA-256、bundle hash 与导入日期。
2. 将 `themes.css` 转换为生产集中 design token；公开主题 ID 精确为 `ink/ledger/vermilion/red/orange/yellow/green/cyan/blue/purple`，默认 `ink`。
3. 将 `styles.css` 拆成 semantic token、component token 和生产样式层，避免在 JSX 中散布十套颜色常量。
4. 将 `index.html` 的五工作区、Project Drawer、Review dialog、empty view 转换为 React/Next.js 组件，并连接 canonical API 状态。
5. `app.js` 只用于提取行为规则、键盘交互和状态转换，不进入生产 bundle。
6. 把 Look 原型中的关键行为转成 Playwright/Axe E2E；后续 Look 变更必须产生新 hash 和设计变更记录，不能静默覆盖。

这使视觉设计能够稳定接入，同时避免静态原型成为第二套数据模型、路由器或状态机。

## 6. 验证器与实际结果

权威验证器：[`decision-lab/scripts/verify_decision_os_contracts.py`](../../scripts/verify_decision_os_contracts.py)。它固定只读取规划、Look 六个核心文件、Ways 元数据/Schema/eval 和 Skill 目录名，不读取 `.env`、`auth.json` 或任何 API Key/Token。

执行命令：

```powershell
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH='C:\Users\xiayu\AppData\Local\Temp\codex-pyyaml-20260721;C:\Users\xiayu\AppData\Local\Temp\codex-jsonschema-20260721'
py -3.12 .\decision-lab\scripts\verify_decision_os_contracts.py
```

最终验证覆盖：

- Look 六文件存在、固定 bundle hash 一致；
- CCR-003 accepted；
- 06/26 MethodVersionRef、DeepAnalysisRequest/Result 精确形状；
- Source 判别联合、Membership/Session/Capability、18 字段 SignoffPayload、DecisionRecord signed payload；
- 08 StructuredReport JSON 示例字段一致；
- 活动合同无裸 `caseId/runId`；
- manifest YAML、26 个任务 ID、依赖存在、DAG 无环、owner/secondary scope、reserved scope、Task 17/18/19 发布门、plan anchor；
- Ways 1.0.0 历史与 1.1.0 活动版本、V1–V9 exact set、31 Skills 与 13/7/8/1/2 处置计数；
- 17 个 Draft 2020-12 Schema 的 JSON 解析、manifest registry、全部本地/URN `$ref` 解析、`Draft202012Validator.check_schema`；
- Draft/Focused/Structured Recommendation 的 abstain 链；
- 全部审计范围 Markdown fence、`json` fence、本地链接、YAML 和 JSON 文件。

最终结果：**全部 7 个检查组 PASS，`decision-os-contracts: PASS`**。

## 7. 尚未验证的实现事项

合同通过不等于应用已经完成。以下事项仍必须在 Gate 0 或实施期验证：

1. 目标独立产品仓库、monorepo、`.gitignore`、OpenAPI 生成、前后端包和 CI 尚未按计划实际创建；当前父仓库仍没有正式基线 commit。
2. 尚未执行真实 Postgres migration、数据库约束、append-only trigger/policy、session revocation 和事务签署实现。
3. 尚未运行 Docker Compose、Worker、SSE、备份恢复、stuck Run 恢复和生产部署。
4. 尚未执行真实 DeepSeek/provider structured output、thinking/tool-call probe；外部 Key、额度、网络与模型返回版本未验证。
5. 尚未执行完整 Playwright/Axe、390×844/1440×900 响应式、PDF renderer、Graph/Simulation 金路径和 live/fixture 双轨 E2E。
6. 尚未生成真实 `THIRD_PARTY_NOTICES.md`、资产授权摘要、生产 secrets 管理、可观测性和发布 runbook。
7. `jsonschema` 静态元 Schema 通过不替代目标运行时的 Ajv/Pydantic/OpenAPI 生成与跨语言 drift 检查。

## 8. Gate 0 与开工顺序

### 现在立即执行

1. Task 1：建立独立产品仓库、Python 3.12/uv、pnpm workspace、API 健康检查、OpenAPI/TypeScript 单向生成链。
2. Task 1W：生成 Look source manifest、tokens 和五工作区生产 Shell，不加载原型 `app.js`。
3. Task 2/19A：先落 canonical schema、迁移和生成合同；未通过 drift check 不并行扩散 DTO。
4. 建立 fixture、Source freeze、no-run-no-report、abstain、Signoff 与 Simulation 的阻断测试。

### 正式计时前必须通过

- Python 3.12/uv、Node/pnpm、Docker daemon/Postgres 和浏览器环境；
- DeepSeek/provider 的真实最小 probe；
- Ways 安装、内容 hash、31-Skill 双账本和 Schema compile；
- OpenAPI/TypeScript drift clean；
- Look hash snapshot；
- fixture 三段边界、安全默认值和最小 E2E。

Gate 0 未通过时，可以继续离线开发和准备，但不得宣布 72 小时冲刺已经开始。

## 9. 最终 Go/No-Go 声明

- **文档/合同：GO。** 当前 canonical 合同已足以指导数据库、API、Worker、前端和测试从同一基线实施。
- **黑客松原型离线开发：GO。** 可以立即开始 bootstrap、合同生成、fixture 和 Look 转换。
- **正式 72 小时计时：暂不自动 GO。** 只有 Gate 0 实际通过后才启动。
- **完整 MVP：可以开始实施，但不能按 72 小时承诺。** 默认采用 4 Agent/108 小时或 3 Agent/144 小时；真实资源不同则重新估算。
- **生产发布：NO-GO，直到实现级验证全部通过。**

当前没有需要产品方补充确认的合同问题；后续只有在 Gate 0 真实 probe、外部供应商能力或实现测试暴露新事实时，才需要提交新的 CCR。
