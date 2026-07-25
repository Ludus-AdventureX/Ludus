# Task 11 Phase 0 Session B Handoff — Project Drawer、slot 合同与收尾

- Date: 2026-07-25 (Asia/Shanghai)
- Role: Web/UX Owner (Fable5)
- Branch: `codex/task-11-phase0-shell-b`
- 唯一父提交：会话 A 精确 push SHA `b35870635a601f09422d5c2d7a79cc10d15d6d85`
- Gate 0（本会话第一条命令）：`git ls-remote origin refs/heads/main` = `51ae45c900ae4efa01b72d5d6842adb74ad50c91`（精确命中预期 `51ae45c`，无前进）；`refs/heads/codex/task-11-phase0-shell-a` = `b358706…`（与 A 汇报一致）。
- 消费输入：`docs/handoffs/TASK11_PHASE0_SHELL_A_HANDOFF.md`（组件对照表 §4、slot 锚点 §5、B 待办 §7）。

## 1. 设计快照纪律

- 冻结的 `design/look-source-manifest.json` 自会话 A 在同一 base 上完成六文件 SHA256 字节校验以来未变；本会话未重采样，仅以 `index.html` `#caseDrawer`（L587-607）与 `look-styles.css` 既有类为结构/样式参照。
- 生产代码不加载 `../look/app.js`；抽屉焦点陷阱行为按 `DecisionShell.tsx` 既有 React 模式实现。

## 2. 交付物

| 文件 | 类型 | 说明 |
|---|---|---|
| `apps/web/components/shell/ProjectDrawer.tsx` | 新增 | Look V7 `#caseDrawer` 落成生产抽屉：工作区列表消费 Task 3 只读 `GET /api/auth/session`（membership 摘要）；loading/401 未登录/错误可重试/空工作区四种诚实状态；「空工作台」链接 `/cases/new`；焦点陷阱 + Escape + scrim 关闭 + 焦点归还 trigger |
| `apps/web/components/shell/DecisionHealthBar.tsx` | 新增 | 五段骨架：证据(E)/因果链(C)/战略稳健性(S)/质量门(G)/版本(V)，全部「未接入」；**不显示总可信百分比**；`onSelectSegment` 为点击行为 slot，缺省时分段禁用 |
| `apps/web/lib/shell/projects.ts` | 新增 | Task 3 会话 API 只读消费层（信封解析、401/网络错误归一）；`caseListRouteAvailable = false` 是 case 列表缺口的单一事实来源 |
| `apps/web/lib/shell/slotContracts.ts` | 新增 | 正式 slot/props 合同（见 §3）：每个 slot 的 props 边界类型 + `shellSlotContract` 注册表（host/owner/status/mount） |
| `apps/web/components/shell/CaseShell.tsx` | 挂载点最小修改 | project-drawer slot 由禁用占位替换为真实 trigger（`aria-controls`/`aria-expanded`）+ 移动端 `.mobile-case-trigger`；抽屉打开时 masthead/spine/stage `inert`；`?panel=projects` 与 `?view=` 一起做刷新恢复；挂载 `<ProjectDrawer/>` |
| `apps/web/components/shell/DecisionSpine.tsx` | 挂载点最小修改 | 新增可选 `inert` prop（抽屉打开时让 spine 退出 tab 序）；其余不变 |
| `apps/web/components/shell/views/WorkspaceView.tsx` | 挂载点最小修改 | ledger-body 内 decision-health-bar 占位替换为 `<DecisionHealthBar />`（锚点属性由组件自带，slot 名不变） |
| `apps/web/tests/case-shell.test.tsx` | 断言更新 | 仅两处：project-drawer trigger 由「disabled」改为「enabled + aria-haspopup」（B 合法填充该 slot 的直接后果）；其余 A 断言原样保留 |
| `apps/web/tests/project-drawer.test.tsx` | 新增 | 9 条测试（见 §5） |

未触碰：`/demo` 页面、guest client、`next.config.ts`、`package.json`（零新依赖）、`services/api/**`、`packages/contracts/**`、`DecisionShell.tsx`、Look 快照与 `look-styles.css`/`look-themes.css`。

## 3. 正式 slot/props 合同（后续 phase 只准填 slot，不准改 shell）

机器可读版本：`apps/web/lib/shell/slotContracts.ts`（类型 + 注册表）。规则：

1. 只允许替换/填充携带自己 `data-phase-slot` 锚点的节点（或走文档化的替换 prop）；不得改动 shell、spine、view router 或他人 slot 的结构。
2. shell 保证给每个 slot 的 props 边界仅限下表；Run/报告/证据等状态由填充 phase 自己从真实 API 获取，shell 永不注入 mock。
3. slot 名冻结；新增 slot 需要新的 shell 会话，不允许 phase 内自加。

| slot | 位置（host） | props 边界（shell 提供） | 填充者 | 状态 |
|---|---|---|---|---|
| `analysis-charter-form` | WorkspaceView intro-actions | `{ decisionCaseId: string }` | AnalysisCharterForm（Step 2） | reserved |
| `analysis-progress` | AnalysisView analysis-trace | `{ decisionCaseId: string }` | AnalysisProgress（Step 3） | reserved |
| `quality-gate-panel` | AnalysisView quality-margin | `{ decisionCaseId: string }` | QualityGatePanel（Step 5） | reserved |
| `evidence-drawer-trigger` | AnalysisView custody-strip；ReportView dissent-page | `{ decisionCaseId: string }` | EvidenceDrawer（Step 4） | reserved |
| `decision-health-bar` | WorkspaceView ledger-body | `{ onSelectSegment?: (segment) => void }` | 骨架已由 B 挂载；分项数据/点击详情由各负责 phase 接 | **filled** |
| `decision-signoff` | DecisionView intro-actions | `{ decisionCaseId: string }` | Task 14W Decision signoff | reserved |
| `review-dialog-trigger` | DecisionSpine 第六步（disabled 占位） | 经 `DecisionSpine reviewSlot?: ReactNode` prop 替换；`{ decisionCaseId: string \| null }` | Task 14W ReviewDialog | reserved（mount = prop） |
| `project-drawer` | CaseShell masthead trigger + drawer 挂载 | `{ open, decisionCaseId, onClose }` | ProjectDrawer | **filled** |

DecisionHealthBar 五段与负责方：证据→证据账本（Step 4）；因果链→推演模型 UI；战略稳健性→五视角报告（Step 6）；质量门→质量门面板（Step 5）；版本→Case 版本档案。每段点击进入负责该状态的详情（`onSelectSegment` slot），永不显示总可信百分比。

## 4. API 缺口记录（不自造后端）

- **已消费**：`GET /api/auth/session`（Task 3 已上线）——workspace membership 摘要（`workspaceId/workspaceName/role`）驱动抽屉工作区列表；401 走诚实未登录空态。
- **缺口**：**decision-case 列表只读路由不存在**。`services/api/app/tenancy/routes.py` 的 `workspace_router` 目前只挂了 simulations；无 `GET /api/workspaces/{workspaceId}/cases`（Task 4+ 才有）。抽屉以 `case-drawer-note` 显式披露缺口并渲染空态；`lib/shell/projects.ts` 的 `caseListRouteAvailable=false` 是唯一开关，路由上线后翻转即接入真实列表，无需重排 UI。
- 未发明任何端点；未 mock 任何分析/案例数据。

## 5. 验收门结果（会话 B）

- `pnpm --dir apps/web test`：**29 passed / 0 failed** —— A 基线 20 条零回归（其中 case-shell 2 处断言因 B 合法填充 slot 而更新，见 §2）+ B 新增 9 条：drawer 打开/真实工作区列表/缺口披露、401 诚实空态、错误可重试、焦点陷阱 + Escape + 焦点归还、`?view=&panel=` 刷新恢复、移动端 trigger、健康栏五段无百分比、分段点击 slot、slot 合同完整性。
- `pnpm --dir apps/web typecheck`、`lint`：干净。
- `pnpm --dir apps/web build`：通过；`/cases/[decisionCaseId]` route size **16.1 kB / First Load JS 131 kB**（A 时 11 kB / 125 kB；增量为 drawer + 健康栏 + 数据层）。
- `git diff --check`、conflict-marker、secret、写入范围审计：见 HISTORY 完工记录（提交前逐项跑）。

## 6. 两会话累计汇报（A + B）

- **提交链**：`51ae45c`(main base) → A：`c67fb1a` kickoff → `9d17efa` feat → `b358706` 完工 → B：`9d98303` kickoff → feat → 完工（精确 SHA 见 push 汇报）。
- **文件清单（累计）**：apps/web 新增 18 个源文件/测试（A 13 + B 5：ProjectDrawer、DecisionHealthBar、projects.ts、slotContracts.ts、project-drawer.test.tsx），B 另最小修改 4 个既有文件（CaseShell、DecisionSpine、WorkspaceView、case-shell.test.tsx）；handoff 2 份；HEAD/HISTORY 生命周期记录。
- **测试数**：套件累计 **29 条**（demo/guest 基线 14 + A 6 + B 9），零回归零跳过。
- **build 产物**：`/cases/[decisionCaseId]` 16.1 kB（First Load 131 kB）；`/` 与 `/demo` 未受影响（11.7 kB / 4.08 kB）。
- **slot 合同摘要**：8 个冻结 slot（6 reserved + 2 filled），props 边界与挂载方式见 §3 与 `lib/shell/slotContracts.ts`；后续 phase（Charter/Progress/QualityGate/Evidence/14W Decision/Review）只准填 slot。
- **ready_for_qa = YES**（范围：Task 11 Phase 0 全部——五工作区 shell + ProjectDrawer + slot 合同 + DecisionHealthBar 骨架；已知边界：case 列表路由缺口见 §4，theme/dossier drawer 不在 A/B 范围）。

## 7. 后续 phase 消费指引

1. Charter（Step 2）从 `analysis-charter-form` slot 进入；只拿 `decisionCaseId`。
2. Progress/QualityGate/Evidence（Step 3/4/5）分别填各自 slot；EvidenceDrawer 同时服务 AnalysisView 与 ReportView 两处锚点。
3. Task 14W 用 `DecisionSpine reviewSlot` prop 替换复盘占位步，用 `decision-signoff` slot 挂签署流。
4. Case 列表路由上线后：翻转 `caseListRouteAvailable` 并在 ProjectDrawer 内把工作区条目展开为真实 case 列表；不得改 shell 结构。
