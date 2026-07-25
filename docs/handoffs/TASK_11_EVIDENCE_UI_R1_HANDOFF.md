# Task 11 数据接入 — 证据溯源线（B2 r1）Handoff

## 1. Lane identity

- Task: Task 11 数据接入 — 证据溯源线（B2 r1），Web/UX Owner，Fable5。
- Base: `23ab477649716f52b3aa913e5efb209442397efa`（= Gate 0 时的 origin/main；ls-remote 原文已按时回报）。
- Branch: `codex/task-11-evidence-ui-r1`（全新 worktree `decision-lab-task11-evidence-ui-r1`）。
- Supersedes: 本任务书废止此前所有 B2/证据线委托。

## 2. Contract sources (read-only, transcribed — never guessed)

- `docs/product-plan/10-api-and-events.md`「证据溯源与冲突读取 API」子节（L1029-1039）：7 条只读 GET + 反枚举语义。
- `services/api/app/evidence/schemas_api.py`：11 个 camelCase CanonicalModel wire DTO，逐字段转写为
  `apps/web/lib/api/evidence.ts` 的 TS 类型（QualityDimensionsView / EvidenceItemView / RawArtifactView /
  SourceSpanView / SourceRecordView / EvidenceProvenanceView / EvidenceDirectionView / SameSourceGroupView /
  ConflictRelationView / RunEvidenceListView / ConflictListView）。
- `packages/contracts/src/types.gen.ts`：7 条 evidence GET + `GET .../analyses/{analysisRunId}/events`（SSE）
  路径类型均已挂载确认；生成层 data 为 `{[key:string]: unknown}`，故形状以 schemas_api.py 为准。
- 枚举字面量：`EvidenceVerdict`（accepted|conditional|lead_only|rejected）、`OriginMode`（live|cached|fixture）
  取自 `app/types.py`；`sourceGrade` 六档 L1_primary…L6_unverified 取自 06-data-model.md L672（wire 层按
  MOUNT-01 M10 姿态是普通字符串，前端容忍未知值并原样展示，不臆造档位）。
- 信封：`{ ok, data }`；404 统一 `CASE_NOT_FOUND` / "Case material not found."（`app/evidence/routes.py`）。

## 3. Write domain (all changes)

新增：
- `apps/web/lib/api/evidence.ts` — 7 GET 读取器 + 类型转写 + `EvidenceApiError`/统一 404/401 判别 +
  `evidenceAnchorsRouteAvailable` 单开关 + `subscribeCitationAdded` SSE 被动刷新钩子（仅 citation.added）。
- `apps/web/components/quality/EvidenceDrawer.tsx` — 抽屉编排（账本 + 逐条溯源详情 + 全状态处理 + 焦点管理）。
- `apps/web/components/quality/EvidenceDrawerTrigger.tsx` — slot 填充触发器（保留 `data-phase-slot` 锚属性）。
- `apps/web/components/quality/SourceGradeBadge.tsx` — L1-L6 来源类别徽标（类别≠可信分）。
- `apps/web/components/quality/QualityDimensionsPanel.tsx` — 七项正交维度（小数呈现，永不合成总分/百分比）。
- `apps/web/components/quality/VerdictBlock.tsx` — 四级 verdict + 理由码 + 适用限制（conditional 缺限制时明示）。
- `apps/web/components/quality/ProvenanceChain.tsx` — 溯源链 + SameSourceGroupNote + DirectionPanel。
- `apps/web/components/quality/ConflictList.tsx` — 冲突列表（不平均、无解释即明示）。
- `apps/web/tests/evidence-drawer.test.tsx` — 14 条自有测试。

slot 填充（合同内 `mount: "replace-phase-slot-node"`，仅替换锚点节点）：
- `apps/web/components/shell/views/AnalysisView.tsx` — custody-strip 的 PhaseSlot 节点 → `<EvidenceDrawerTrigger />`。
- `apps/web/components/shell/views/ReportView.tsx` — dissent-page 的 PhaseSlot 节点 → `<EvidenceDrawerTrigger />`。

生命周期：`HEAD`（替换为本任务）、`HISTORY`（append-only 归档，前缀校验通过）。

## 4. Adjudications & disclosures (fail-closed, no unauthorized shell increment)

1. **slotContracts.ts 未改（status 仍为 "reserved"）。** 合同注册表属 shell 冻结文件；把
   `evidence-drawer-trigger` 的 status 翻为 "filled" 会同时要求改动基线测试
   `tests/project-drawer.test.tsx` L228-230 的覆盖断言（QA lane 文件，超出本 lane 写域）。Task 13 先例中该类
   更新是"经授权 shell 增量"的一部分。→ 留给 shell owner / 下一授权波次：翻 status + 更新覆盖断言两处一并做。
2. **EvidenceDrawerTriggerSlotProps 的 `decisionCaseId` 无法由宿主提供。** Phase 0 的 AnalysisView/ReportView
   均无 props，把 `decisionCaseId` 从 CaseViewRouter 穿透下来是 Task 13 同型的 shell 增量（需先授权）。本 lane
   不做未授权增量：触发器将 `decisionCaseId` 设为可选；且当下即使拿到 caseId 也无路由可解析到 run（见 3）。
3. **数据缺口单开关（沙盘先例）。** 已挂载的证据读取面全部以 workspaceId+analysisRunId / evidenceItemId 为锚，
   但不存在 decisionCaseId → analysisRun 的只读解析路由（types.gen.ts 全路径核对）。
   `evidenceAnchorsRouteAvailable = false` 为唯一开关；生产 UI 渲染诚实缺口说明、零 fetch、零伪造。
   解析路由上线后翻开关即可，UI 无需重构。
4. **SSE 钩子仅预留 citation.added。** 完整进度条/Last-Event-ID 簿记归 B1 AnalysisProgress lane；本钩子只做
   账本静默重读，失败的静默刷新不降级已显示数据。

## 5. Deliverable behavior summary

- 证据抽屉：L1-L6 来源类别徽标与七项正交质量维度分开呈现；verdict 四级 + 理由码 + 适用限制；
  全 UI 无任何百分比字符、无总可信度数值（测试断言 `not.toContain("%")`）。
- 溯源链：RawArtifact 存储指针元数据（hash/字节数/URL/originMode，无磁盘路径）→ 冻结 SourceRecord + spans →
  质量评估；同源组明示"N 条引用 = M 个独立来源"（三文一源=1）；支持/反对方向分列不抵消。
- 状态处理：loading / 慢网（阈值后如实承认仍在读取）/ 401 会话文案 / 404 单一反枚举文案
  （`UNIFORM_NOT_FOUND_COPY`，跨租户与不存在字节一致、不回显 id）/ 空账本诚实空态 / 信封畸形降级 + 重试。
- a11y：焦点陷阱、初始焦点、Escape、Tab 循环逐行照 ProjectDrawer 先例；关闭后焦点回触发按钮；
  `role=dialog` + `aria-modal` + `aria-haspopup/expanded`。

## 6. Gate results

- `pnpm --dir apps/web test`：**82 passed (10 files)** = 基线 68（9 files）零回归 + 新增 14。
- `pnpm --dir apps/web typecheck`：通过。
- `pnpm --dir apps/web lint`：0 error（1 warning 为 base 既有 `simulation-demo-panel.test.tsx` 未用变量，
  属 demo/guest lane，Task 13 handoff §7 已披露）。
- `pnpm --dir apps/web build`：通过。
- scope audit：diff 仅含写域文件（上节清单）；未触碰 slotContracts.ts、PhaseSlot.tsx、CaseViewRouter、
  /demo、guest、simulation、next.config.ts、services/api、packages/contracts。
- secret scan：净。conflict-marker scan（HEAD/HISTORY）：净。组件源码 `%` 字符扫描：净。

## 7. QA suggested entry points (§8)

- 反枚举：`UNIFORM_NOT_FOUND_COPY` 为唯一 404 文案出口；对抗性检查可再构造"缺失 run vs 跨租户 ws"双例比对
  DOM 字节一致（已有测试 `uniform 404 shows ONE anti-enumeration copy`）。
- 无百分比：全 UI 扫描 `%`、`\d+\s*％`（全角）与"总可信/置信度+数字"组合；现断言覆盖半角。
- slot 合同：确认 `data-phase-slot="evidence-drawer-trigger"` 锚在两宿主视图仍可命中（case-shell 基线已断言）；
  确认 slotContracts.ts 零 diff。
- SSE 钩子：确认监听器集合恰为 `["citation.added"]`（测试已断言），无 stage/progress 解析。
- a11y：与 ProjectDrawer 逐行 diff 焦点陷阱实现；zero-focusable 分支（focusable.length===0）未被测试覆盖。
- 已知限制：慢网阈值默认 8s 仅组件 prop，可注入缩短；quiet 刷新与用户手动重试并发时以 requestSeq 判重。

## 8. ready_for_qa

YES.
