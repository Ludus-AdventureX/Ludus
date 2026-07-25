# Task 11 Phase 0 Session A Handoff — 五工作区前端 Shell（布局与导航）

- Date: 2026-07-25 (Asia/Shanghai)
- Role: Web/UX Owner (Fable5)
- Branch: `codex/task-11-phase0-shell-a`
- Base: remote main `51ae45c900ae4efa01b72d5d6842adb74ad50c91`（Gate 0 精确命中预期 `51ae45c`，无前进）
- Session B 规则：以本 handoff 报告的精确 push SHA 为唯一父提交继续；分支 `codex/task-11-phase0-shell-b`。

## 1. Gate 0 与设计快照纪律

- `git ls-remote origin refs/heads/main` = `51ae45c900ae4efa01b72d5d6842adb74ad50c91`。
- Look V7 源字节校验：`VERSION / README.md / index.html / themes.css / styles.css / app.js` 六个文件 SHA256 与冻结的 `design/look-source-manifest.json` 逐一相等（bundle `c5d5d65b…d1a55e98`）。无 snapshot diff，无重采样。
- `look/app.js` 仅作为行为参照（键盘导航等以 React 重写）；生产 bundle 不加载它。`look/HEAD` 未读取。

## 2. 交付物（全部为 `apps/web/**` 新增文件，零既有文件修改）

| 文件 | 说明 |
|---|---|
| `apps/web/app/(workspace)/cases/[decisionCaseId]/page.tsx` | 稳定 Case 路由骨架（server component，`params` 为 Promise）；保留段 `new` → 空态；不读任何 API |
| `apps/web/components/shell/CaseShell.tsx` | Case 壳：masthead + DecisionSpine + stage；`?view=` URL 同步与刷新恢复；空态时挂 `body.empty-case` |
| `apps/web/components/shell/DecisionSpine.tsx` | 五主工作区导航 + Task 14W 复盘 trigger slot；`aria-current="page"` 高亮；方向键/Home/End roving focus |
| `apps/web/components/shell/CaseViewRouter.tsx` | 按 `decisionCaseId`（null→empty）与工作区状态挂载视图的 view router |
| `apps/web/components/shell/views/WorkspaceView.tsx` | 问题工作区静态布局框架（view-intro + ledger-sheet + folio-peek） |
| `apps/web/components/shell/views/AnalysisView.tsx` | 证据工作区框架（研究轨迹 + quality-margin + custody-strip） |
| `apps/web/components/shell/views/ReportView.tsx` | 判断工作区框架（report-spread：recommendation-page + dissent-page） |
| `apps/web/components/shell/views/SandboxView.tsx` | 推演工作区框架（pressure-mode + fragile-index + pressure-layout） |
| `apps/web/components/shell/views/DecisionView.tsx` | 决定工作区框架（decision-sheet + conditions + signature） |
| `apps/web/components/shell/EmptyCaseView.tsx` | 无 Case 空态：问题优先表单，无模板卡片墙、无伪造计数 |
| `apps/web/components/shell/PhaseSlot.tsx` | 后续 phase 的稳定挂载锚点组件（`data-phase-slot`） |
| `apps/web/lib/shell/workspaces.ts` | canonical 五工作区 IA 常量与类型（含复盘 trigger 定义） |
| `apps/web/tests/case-shell.test.tsx` | 本会话新增测试（6 条，见 §6） |

未触碰：`/demo` 页面、guest client、`next.config.ts`、`package.json`（零新依赖）、`services/api/**`、`packages/contracts/**`、`DecisionShell.tsx`（`/` 首页原样）。

## 3. 五工作区命名裁决（披露）

任务书枚举为“问题/研究/沙盘/决定/复盘”，但以“命名与 Look V7 对齐”为准。冻结的 Look V7 与 B12 裁决（`28-contract-repair-completion-audit`、`03-existing-assets-assessment` L190、`24-frontend-visual-theme`）规定五主工作区为：

| id | 坐标 | 中文 | 副题 |
|---|---|---|---|
| `workspace` | Q | 问题 | 界定边界 |
| `analysis` | E | 证据 | 研究与质疑 |
| `report` | J | 判断 | 条件化建议 |
| `sandbox` | G | 推演 | 寻找翻转 |
| `decision` | D | 决定 | 冻结行动 |

复盘（R）在 Look V7 中是 spine 上的 Review dialog trigger（`id="openReview"`，无 `data-view`），不是第六个工作区；本会话按此渲染为禁用的 `data-phase-slot="review-dialog-trigger"` 占位步，由 Task 14W 接入 dialog。DecisionSpine 提供 `reviewSlot?: ReactNode` prop 作为替换点。

## 4. index.html 区块 → React 组件对照表（供 B 与后续 phase 消费）

| Look V7 区块（index.html） | React 组件 | 状态 |
|---|---|---|
| `header.masthead`（L60-90） | `CaseShell` 内 masthead 段 | A：brand + case-title + 诚实 source-mode「档案未接入」；theme trigger/dossier 未搬入 case shell（theme 机制仍在 `/` DecisionShell，后续 phase 统一） |
| `nav.decision-spine`（L92-118） | `DecisionSpine` | A 完成（五步 + review slot） |
| `#view-empty`（L121-162） | `EmptyCaseView` | A 完成（无 examples 墙） |
| `#view-workspace`（L163-291） | `views/WorkspaceView` | A：静态框架；札记 composer/folio 计数等待档案 API phase |
| `#view-analysis`（L293-363） | `views/AnalysisView` | A：静态框架 + 3 个 slot |
| `#view-report`（L365-413） | `views/ReportView` | A：静态框架 + evidence slot |
| `#view-sandbox`（L415-541） | `views/SandboxView` | A：pressure-mode 框架；model-mode（Night Desk 画布）留给 Simulation UI phase |
| `#view-decision`（L543-583) | `views/DecisionView` | A：decision-sheet 框架 + signoff slot（Task 14W） |
| `#caseDrawer`（L587-607） | `ProjectDrawer` | 会话 B 交付；trigger 锚点已留（见 §5） |
| `#themeDrawer`（L608-659） | （沿用 `/` DecisionShell 的 ThemeDrawer 实现） | 不在 A/B 范围 |
| `#dossierDrawer`（L660-680） | EvidenceDrawer/档案抽屉 | 后续 phase（Task 11 Step 4） |
| `#charterDialog`（L682-710） | `AnalysisCharterForm` | 后续 phase（Task 11 Step 2）；slot 已留 |
| `#reviewDialog`（L712-724） | `ReviewDialog` | Task 14W；spine trigger slot 已留 |

## 5. 本会话预留的 slot 锚点（B 负责正式 slot/props 合同）

全部通过 `PhaseSlot`（或 `data-phase-slot` 属性）落位，位置与 Look V7 对应区块一致：

| slot name | 位置 | 未来填充者 |
|---|---|---|
| `analysis-charter-form` | WorkspaceView intro-actions | AnalysisCharterForm（Step 2） |
| `analysis-progress` | AnalysisView analysis-trace | AnalysisProgress（Step 3） |
| `quality-gate-panel` | AnalysisView quality-margin | QualityGatePanel（Step 5） |
| `evidence-drawer-trigger` | AnalysisView custody-strip；ReportView dissent-page | EvidenceDrawer（Step 4） |
| `decision-health-bar` | WorkspaceView ledger-body | DecisionHealthBar 骨架（会话 B） |
| `decision-signoff` | DecisionView intro-actions | Task 14W Decision signoff |
| `review-dialog-trigger` | DecisionSpine 第六步（disabled） | Task 14W ReviewDialog（经 `reviewSlot` prop 替换） |
| `project-drawer` | CaseShell masthead case-title trigger（disabled） | ProjectDrawer（会话 B，替换为真实 trigger + drawer） |

约束：后续 phase 只准往 slot 里填内容/替换 slot 节点，不准改 shell 结构。`.phase-slot` 无专属 CSS（沿用 `margin-label` 等既有 token 类），B 如需样式请走既有 token/组件层，不新增依赖。

## 6. 验收门结果（会话 A）

- `pnpm --dir apps/web test`：**20 passed / 0 failed**（基线 14 条零回归 + 新增 6 条：路由渲染与 landmark/spine 基线、五工作区切换且单一 active 视图、`?view=` 刷新恢复、spine 方向键/Home/End 键盘导航、slot 稳定性与无伪造数据（含无总可信百分比断言）、empty 态无模板卡片墙 + 人主导草稿焦点回归）。
- `pnpm --dir apps/web typecheck`、`lint`：干净。
- `pnpm --dir apps/web build`：通过；`/cases/[decisionCaseId]` route size 11 kB，First Load JS 125 kB。
- `git diff --check`、conflict-marker 扫描、secret 扫描、写入范围审计：干净（详见 HISTORY 完工记录）。
- 已知 jsdom 限制：jsdom 把 section 内的 `header` 也映射为 banner landmark（与 HTML-AAM 不符），masthead landmark 断言改为结构断言；浏览器语义不受影响。

## 7. 会话 B 待办（不属于 A 的缺口）

1. `ProjectDrawer.tsx`：消费 Task 3 已上线的 workspace/case 只读 API；若 case 列表路由缺失则空态 + 记录缺口，不自造后端。
2. 正式 slot/props 合同文档化（基于 §5 锚点）。
3. `DecisionHealthBar` 五段骨架（无总可信百分比，点击行为留 slot）。
4. 响应式与键盘导航补齐（A 已有 spine 键盘导航与 Look 断点 CSS 复用；drawer 焦点陷阱参照 DecisionShell 模式）。
5. drawer/slot 渲染/刷新恢复测试与两会话累计汇报。

## 8. ready_for_qa

会话 A 交付物 ready_for_qa = YES（范围：shell 布局与导航；不含 B 的 drawer/slot 合同/health bar）。
