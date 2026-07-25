# Task 13 Sandbox Interaction r1 Handoff — 决策用户优先的沙盘交互

- Date: 2026-07-25 (Asia/Shanghai)
- Role: Simulation/Graph Owner (primary) with principal-authorized Web/UX secondary-owner slot integration
- Branch: `codex/task-13-sandbox-r1`（全新 worktree `decision-lab-task13-sandbox-r1`）
- Original Gate 0 base: remote main `70e7dbe810f13044c0afb46d5fe91dd4e31474df`
- Latest-main refresh: merge commit `8bf6a77` incorporates remote-verified main `4941e58bee3b91f14a4a92b7fab92750ef85b3b6` without rewriting the published Task 13 history.
- Gate 0 记录：本会话第一次 Gate 0 命中 `4508b30`（不含 Task 11 Phase 0 shell），按任务书 fail-closed 阻断上报；波次一发布 `70e7dbe8`（含 shell Sessions A+B + 对抗 QA `4fb0999`）后重跑 Gate 0 三项验收（祖先关系双向、shell 文件树、SIM-02A run API 挂载）全部通过后开工。
- 计划依据：`docs/product-plan/18-detailed-development-plan.md` Task 13 节（L1248-1322），逐字消费。
- Scope authority: accepted `CCR-20260725-SANDBOX-01`; `agent-work-manifest.yaml` records `simulation_graph` as primary owner and `web_ux` as secondary owner for the four exact shell integration paths.

## 1. 任务书裁决记录（两处，均先上报后执行）

1. **写域路径冲突**：任务书写 `components/sandbox/**`，计划原文 Files 节逐字要求 `apps/web/components/simulation/*.tsx` + `apps/web/tests/sandbox-view.test.tsx`。按任务书自身条款「与本任务书冲突时以原文为准」采**计划原文路径**。
2. **slot 合同缺口**：冻结的 `lib/shell/slotContracts.ts`（8 slot 注册表）不含任何沙盘 slot，`SandboxView` 无锚点；合同规则「slot 名冻结；新增 slot 需要新的 shell 会话」与本任务书「禁碰 shell 既有文件」叠加后无合法挂载路径。上报后获调度方**显式授权最小 shell 增量**（本 handoff §3 全量披露）。
3. **Governance closure**: `CCR-20260725-SANDBOX-01` synchronizes the primary/secondary owners, four shell paths, and additive-only slot semantics into the manifest and detailed plan; scope gates no longer depend on a temporary exception.

## 2. 交付物（新建 `apps/web/components/simulation/**`）

| 文件 | 说明 |
|---|---|
| `types.ts` | 沙盘域类型（业务语言）+ SIM-02A wire 类型；引擎内部概念（normalized/damping/multiplier/评分公式/成功概率）零出现 |
| `runClient.ts` | SIM-02A run API 客户端：POST/GET runs、`Idempotency-Key` 走 HTTP header、`X-CSRF-Token` 双提交、统一 404/幂等冲突/GRAPH_NOT_CONFIRMED/未收敛错误判别、`replayMatchesRun` GET 重放等价 |
| `interpret.ts` | 纯函数结果解释（保持/翻转/证据不足）+ 1-3 条文字化影响路径构建；阈值只来自真实已测试点，不伪造 |
| `sandboxData.ts` | 诚实数据可用性合同（`sandboxCaseDataRouteAvailable = false` 单一事实来源，仿 Session B `caseListRouteAvailable` 先例） |
| `CurrentRecommendationSummary.tsx` | 建议 + 成立条件 + 来源报告版本 + 非预测限制 |
| `FragileConditionList.tsx` | 只显示前三；业务单位/可控性/证据状态/一句影响说明 |
| `StressTestControl.tsx` | 一次聚焦一个条件；业务单位滑杆+数值输入；已确认情景预设；重置；显式运行；调整只写工作副本 |
| `StressTestResult.tsx` | 自然语言优先；保持→已测试范围；翻转→目标选项+阈值+硬约束；证据不足→缺失证据；幂等重放标记；引擎版本次要展示 |
| `ImpactPathSummary.tsx` | 1-3 条可读路径 + 定位到完整图 |
| `ValidationActionCTA.tsx` | 脆弱未知项→候选验证行动；只创建 CandidateRevision，零档案写入 |
| `CausalCanvas.tsx` | 渐进展开（点击才挂载）；被测变量/关键路径高亮；节点类型用形状 class+图标+文字共同区分 |
| `NodeInspector.tsx` / `EdgeInspector.tsx` | 业务值/基线/区间/来源/关系质量/影响强度/适用限制/确认状态 |
| `GraphConfirmationPanel.tsx` | 按决策影响排序（改推荐/触发硬约束/高影响低质量优先）；其余折叠+安全批量确认；formal 门禁说明 |
| `ScenarioControl.tsx` | 读 scenario_planning frame（external/unknown driver、strategySurvives、early warnings）；确认/修改后才创建 ScenarioVersion 候选；**不采集风险偏好** |
| `BranchTimeline.tsx` | 命名实验保存/比较/非破坏性回滚；次级流程不占默认界面 |
| `ImpactPathOverlay.tsx` | 完整模型内已定位路径的文字覆盖层 |
| `SandboxWorkspace.tsx` | 编排器（挂 `data-phase-slot="sandbox-workspace"` 锚点）；无真实档案输入时渲染与 Phase 0 骨架一致的诚实空态 |
| `apps/web/tests/sandbox-view.test.tsx` | 新增 15 条测试（见 §5） |

## 3. 授权 shell 增量（全量披露，QA 重点审计面）

| 文件 | 改动 | 性质 |
|---|---|---|
| `components/shell/PhaseSlot.tsx` | union 增加 `"sandbox-workspace"` | slot 名登记（合同要求新 slot 走 shell 会话；此为调度方显式授权的替代） |
| `lib/shell/slotContracts.ts` | 增加 `SandboxWorkspaceSlotProps = { decisionCaseId: string }` + 注册表 `sandbox-workspace`（status filled, mount replace-phase-slot-node） | 合同登记 |
| `components/shell/views/SandboxView.tsx` | 静态骨架内容移入 `SandboxWorkspace` 空态分支；view 外壳（section/id/data-view-panel/aria）原样保留 | 最小挂载点修改（仿 Session B WorkspaceView 先例） |
| `components/shell/CaseViewRouter.tsx` | 单行：`<SandboxView decisionCaseId={decisionCaseId} />` | props 透传 |
| `apps/web/tests/project-drawer.test.tsx` | slot 覆盖断言加入 `sandbox-workspace`（+filled 断言） | 合法填充 slot 的直接后果（Session B 更新 case-shell 断言同款先例） |

未触碰：`/demo`、guest client（`lib/demo/**`、`components/demo/**`）、`next.config.ts`、`package.json`（零新依赖；仅 `pnpm install --frozen-lockfile` 还原锁定依赖）、`services/api/**`、`packages/contracts/**`、其他 slot、DecisionShell/CaseShell/DecisionSpine/ProjectDrawer/DecisionHealthBar 及其余视图。

## 4. API 契约消费（frozen CCR-20260724-SIM-02A，零发明）

- `POST /api/workspaces/{workspaceId}/simulations/{graphId}/runs`：mode（experimental/formal）+ 版本 anchors + `nodeOverrides`（原始业务值，服务端负责归一化）；`Idempotency-Key` header；`X-CSRF-Token`（GET `/api/auth/csrf`）。
- 幂等语义：每次显式运行意图生成新 key（`sandbox-` 前缀 UUID）；网络失败重试**复用同一 key**；`meta.idempotencyReplay === true` 时 UI 标记「幂等重放（未重复计算）」。
- 统一 404：`CASE_NOT_FOUND`（跨租户/跨图坍缩）呈现为「该因果图在当前工作区不可见（未找到）」，不泄露存在性、不提供重试。
- `engineVersion=sim-engine-1.1.0` 由响应透传展示（测试断言）。
- GET replay 等价：`replayMatchesRun`（runId+inputHash+engineVersion）。
- formal 门：图审阅未完成或 draft 时 formal 入口禁用 + 文案明示「前端禁用只是反馈，正式运行始终由 API 校验兜底」；`GRAPH_NOT_CONFIRMED`（409）单独诚实呈现。

## 5. 数据缺口记录（不自造后端）

沙盘所需的只读输入今日均无路由：结构化报告（条件化建议）、确认图/图版本读取、scenario_planning artifact 读取、案例级 simulation anchors。`sandboxData.ts` 的 `sandboxCaseDataRouteAvailable = false` 为单一事实来源 → 生产挂载渲染与 Phase 0 骨架同文案的诚实空态（`推演尚未开放`），零 API 调用、零伪造。全部交互经 `SandboxWorkspace` 的 `data` prop 由测试 fixture 驱动（wire 层 mock 的是 HTTP，组件不伪造结果）。路由上线后翻转 flag 即接入，无需重排 UI。

## 6. 验收门结果

- `pnpm --dir apps/web test`：**56 passed / 0 failed**（基线 41 条零回归，其中 project-drawer 1 处 slot 覆盖断言因授权新增 slot 更新；新增 15 条：首屏建议+前三脆弱条件+无画布、14 个月主流程+请求纪律+引擎概念零泄露断言、翻转阈值+硬约束、证据不足无伪造阈值+CTA 候选修订零写入、幂等 key 复用+重放标记、统一 404 呈现、formal 门禁→审阅完成→mode=formal、GRAPH_NOT_CONFIRMED、渐进展开+节点形状/图标/文字区分+双检查器、审阅优先级排序、情景确认才建版本+不采集风险偏好、情景预设+分支非破坏回滚、诚实空态零请求、slot 合同符合性、键盘路径）。
- `pnpm --dir apps/web build`：通过；`/cases/[decisionCaseId]` 24.5 kB / First Load 139 kB（base 时 16.1 kB / 131 kB；增量为沙盘交互）；`/`、`/demo` 不受影响。
- `pnpm --dir apps/web lint`：0 error（1 个 warning 位于禁区既有文件，见 §7）。
- `git diff --check`、conflict-marker、secret-pattern、写域 scope 审计：全净。

## 7. base 既有缺口披露（非本 lane 引入，未触碰）

`apps/web/tests/simulation-demo-panel.test.tsx`（demo/guest 禁区）在 base `70e7dbe8` 上即缺 `DemoFlowResult` 导入：`pnpm --dir apps/web typecheck` 因此在干净 base 上就失败（TS2304 L67），lint 同处 1 warning。本 lane 验收门（test/build）不受影响且全绿；修复权属 demo/guest owner lane。

## 8. QA 建议切入点

- formal 门禁 UI：`SandboxWorkspace` `qualityGatePassed`（draft + 审阅余量）与 API 409 双层。
- 幂等重放：`pendingKey` 仅网络失败保留；`IDEMPOTENCY_CONFLICT` 后强制新 key。
- 404 呈现：`runStressTest` 的 `isUniformNotFound` 分支。
- slot 合同：`shellSlotContract["sandbox-workspace"]` + 锚点 `data-phase-slot="sandbox-workspace"`；shell 增量以 §3 清单为界做 merge-base diff scope audit。
- a11y/键盘：滑杆/数值输入均有显式 label；fragile 列表 `aria-pressed`；结果区 `aria-live="polite"`；错误 `role="alert"`；渐进展开按钮 `aria-expanded`。

## 9. Latest-main refresh and governance closure

- Published Task 13 implementation commit `904708780099db8000f99c55b0ef36a852fb5cdc` remains in history unchanged; no rebase, amend, force-push, or replacement commit was used.
- Merge commit `8bf6a77530234d2d77eac6e5fb428273b1fdc46b` refreshes the branch onto live-verified `main` `4941e58bee3b91f14a4a92b7fab92750ef85b3b6`.
- Accepted `CCR-20260725-SANDBOX-01`, `agent-work-manifest.yaml`, and Task 13 Files now agree on `simulation_graph` primary ownership plus `web_ux` secondary ownership for the four exact shell integration paths in section 3.
- Post-refresh verification: `pnpm --dir apps/web test` = **56 passed / 0 failed**; `pnpm --dir apps/web build` = **PASS**; `scripts/verify_decision_os_contracts.py` = **PASS**; API/OpenAPI/generated-contract input diff against latest `main` = empty.
- The remaining branch delta is intentionally limited to Task 13 simulation components, the four CCR-authorized shell files, QA evidence, lifecycle/handoff records, and canonical governance synchronization. Final publication uses normal push followed by live `ls-remote` SHA equality verification.

- 本文档不含任何凭据或 secret 值。
