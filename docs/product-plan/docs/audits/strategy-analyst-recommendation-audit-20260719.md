# Ludus 战略分析师建议与 Ways 资产审计

- 日期：2026-07-19（星期日）
- 状态：完成审计，建议已采纳并进入 canonical 合同
- 审计对象：`decision-lab-product-plan`、`decision-lab`、`探讨/skills/research`
- 安全边界：未读取、复制或输出 `探讨/.env`、`探讨/auth.json` 或其他凭证材料

## 1. 结论

战略分析师的判断成立：Ludus 的差异化不是聊天式 AI，而是把 **Human / Analysis / Unknown** 三类责任语义落实到数据、权限、状态转换、产物和测试中。现有计划方向正确，但在精确来源定位、独立 Judgment、完整决策生命周期、人类签署、DecisionRecord 不可变、Cynefin 前置门、顶层 Agent Engine I/O 和九项验证职责上存在缺口。

本轮决定：

1. 采纳 `Source → Claim → Evidence → Judgment → Decision` 可追溯链，并补充 `SourceRecord/SourceSpan`；
2. 采纳 `Draft → Scoped → Ready → Running → Review → PendingSignoff → Decided → Monitoring`；
3. 采纳冻结 `RunManifest` 后执行的深度分析管道；
4. 采纳三条工程红线，并要求数据库、领域服务、API 和测试四层共同执行；
5. 采纳非聊天式 Agent Engine I/O；
6. 采纳九项独立验证职责，但不采纳“九个常驻模型服务”这一可能的过度实现；
7. Night Desk、数据库任务队列和最小权限体系可实现；复杂 RBAC 与九模型并发服务分期实施。

## 2. 逐项审计矩阵

| 建议 | 审计前状态 | 证据 | 结论与修复 |
|---|---|---|---|
| Source→Claim→Evidence→Judgment→Decision | 部分做到 | `06-data-model.md` 已有 RawArtifact、Claim、EvidenceItem、ClaimEvidence、AnalysisRun、ReportArtifact、DecisionRecord | 增加 SourceRecord、SourceSpan、Judgment、JudgmentSet、DissentRecord；Claim 必须有精确 provenance |
| Claim 定位 Source 具体段落 | 未做到 | Evidence 只有 `snippet/rawArtifactId/url/filePath` | 增加页码、段落、字符区间、quoteHash 与 locator；服务端校验 quoteHash |
| Decision 绑定 Run 与签署人 | 部分做到 | 有 `sourceAnalysisRunId`，但 `decidedBy?` 可空 | 改为 SignoffRequest + 人类 sign command；签署人、时间、声明和签名哈希必填 |
| 完整决策生命周期 | 未做到/存在冲突 | Case 只有 `draft/active/decided/archived`，Run 有独立细状态 | 新增 DecisionLifecycleStage；保留 AnalysisRun 子状态机与 operational status |
| PendingSignoff 不得自动进入 Decided | 未做到 | 原 API `POST /cases/{caseId}/decisions` 可直接产生 decided | 拆分 request/sign；Agent 工具表禁止 sign/decide；数据库验证签署请求与人类 actor |
| 冻结 Run Manifest | 部分做到 | Run 已有 Case/Dossier/Method 哈希和幂等字段 | 增加 Material Snapshot、Source 哈希、Cynefin、预算、允许工具和 provider request metadata 的不可变 manifest |
| Cynefin 前置门 | 声明吸收但未执行 | `framework-selector` 已映射；Ways manifest 与顺序没有 `cynefin` | 在 `hardtech-market-direction@1.1.0` 增加 deterministic gate schema、路由与 override 记录 |
| 多 Agent→对抗→综合→结构化 JSON | 基本做到 | 四 Worker、五 lens、strict schema、质量门已存在 | 增加顶层 DeepAnalysisRequest/Result、Judgment Set、Dissent Record 和 ValidatorAggregate |
| 没有 Run 就没有 Report | 基本做到但未硬化 | `ReportArtifact.analysisRunId` 必填且无通用 create report API | 增加 FK/scope/ready gate、publisher 专属服务和 `no_run_no_report` 测试 |
| DecisionRecord 不可覆盖 | 部分做到 | 文档要求版本与 Review 不覆盖，但 Record 自带可变 status | Record 改为 append-only；修订用 `supersedesDecisionRecordId`；生命周期用事件投影 |
| Human/Analysis/Unknown 代码语义 | UI/文案已有，代码合同不足 | 主题和 StatementType 有区分，未统一责任 stamp 与授权 | 增加 ResponsibilityClass/Stamp、actor 约束、schema 与测试 |
| Night Desk 因果图谱 | 已有详细合同 | GraphVersion、SimulationRun、审阅、分支和非破坏回滚已定义 | 可实现；full Run 后启用，不阻塞最窄 focused MVP |
| 异步任务队列 | 已有详细合同 | Postgres `FOR UPDATE SKIP LOCKED`、heartbeat、SSE、恢复 | P0 必需且可实现；无需 Redis/Celery |
| 多角色权限 | 不完整 | 仅 owner/member，且产品以单决策人为主 | P0 改为最小能力：owner/contributor/reviewer + signer capability；复杂 RBAC 延后 |
| 9 个验证 Agent | 未正式定义 | 当前只有一个 Validation Worker | 一个编排器执行九个版本化 Validator Contract；确定性优先、语义模型按需、blocker fail-closed |
| GPT-5.6-sol 辅助实现 | 可行但不能成为权威 | 领域层已有 provider-neutral 原则 | 可用于代码、Schema、测试和语义校验；不得承担授权、状态迁移、签署或数据库不可变性 |

## 3. `探讨` 资产吸收审计

安全盘点确认 `探讨/skills/research` 中有 31 个带 `SKILL.md` 的研究技能。产品账本和 Ways `CAPABILITY-MAP.md` 的名称集合为 31/31：

```text
P0 直接编译：13
能力被其他合同吸收：7
延后：8
仅参考：1
禁用：2
合计：31
```

因此，**资产名称和处置账本完整**。但“全面吸收”不能只看名称计数；审计前仍缺少：

1. Cynefin 前置门的运行时 schema 和 stage；
2. SourceSpan 精确引用；
3. canonical Judgment Set；
4. canonical Dissent Record；
5. 顶层 Agent Engine 请求/结果；
6. 九项验证职责；
7. Human/Analysis/Unknown 责任类型；
8. signoff 与不可变 DecisionRecord 的工程约束。

上述缺口由 `26-decision-os-invariants-and-agent-engine-contract.md`、CCR-20260719-002 和 Ways 1.1.0 补齐。原资产中的飞书、临时 Markdown 文件协议、自动文件编排、任意 MCP、通用浏览器写操作、LaTeX/PPTX 交付和凭证配置不进入 P0 运行时。

## 4. 九项验证职责

P0 不建立九个常驻微服务。一个 `ValidationOrchestrator` 在同一 Validation Worker 中运行九个隔离合同：

1. Scope / Charter Validator；
2. Source Traceability Validator；
3. Evidence Quality Validator；
4. Claim–Evidence Entailment Validator；
5. Contradiction / Time / Denominator Validator；
6. Unknown / Assumption Validator；
7. Adversarial / Dissent Validator；
8. Causal / Simulation Integrity Validator；
9. Publication / Decision Authority Validator。

确定性检查优先；需要语义判断的 4、5、7 可通过 provider adapter 调用模型。任何 blocker 都不能被多数投票覆盖。

## 5. 分期可行性

- **P0 必需**：责任类型、SourceSpan、Judgment/Dissent、RunManifest、Cynefin、真实生命周期、signoff、append-only Decision、no-run-no-report、异步队列、九验证合同的单 Worker 版。
- **P0 full 路径**：Night Desk/GraphVersion/正式 SimulationRun。
- **P1**：更细 RBAC、验证并行调度、模型路由优化、外部监控。
- **不采纳**：让模型直接签署、由 Agent 修改 Decided、九 Agent 多数投票、无 Run 的“演示报告”、静默覆盖历史决定。

## 6. 验收依据

后续实现必须至少证明：

- 不存在 Agent 可调用的 `sign_decision` / `transition_to_decided`；
- 未签署的 signoff request 无法创建 DecisionRecord；
- DecisionRecord UPDATE/DELETE 被拒绝；
- Report 缺少 Run 或 Run 未达发布门时被拒绝；
- imported/model Claim 缺 SourceSpan 时 schema/服务校验失败；
- Cynefin chaotic/disorder 默认阻断正式长分析；
- DeepAnalysis 正式接口没有 chat `messages[]` 主合同；
- 31 项 Skill 名称集合与 13/7/8/1/2 计数一致。