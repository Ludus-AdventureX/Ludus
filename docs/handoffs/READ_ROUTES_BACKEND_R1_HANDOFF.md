# READ_ROUTES_BACKEND_R1_HANDOFF — Case/Sandbox 读表面 + audit binding (r1)

Lane: `codex/task-read-routes-backend-r1` · Base: main `8130410` · CCR: `CCR-20260726-READ-01`

## 交付面（web lane 消费清单）

全部 `{ok, data}` 信封；任何 scope 否定 = 统一 404 `CASE_NOT_FOUND`；GET-only、无 CSRF。

### 1. case→run 锚点（`evidenceAnchorsRouteAvailable` 翻转依据）

`GET /api/workspaces/{workspaceId}/cases/{decisionCaseId}/analyses?limit=1..200`

```json
{ "ok": true, "data": { "decisionCaseId": "…", "items": [ {
  "analysisRunId": "…", "decisionCaseId": "…", "charterId": "…",
  "analysisLevel": "full|focused", "status": "queued|…|ready|blocked|cancelled",
  "caseVersion": 1, "createdAt": "ISO", "completedAt": "ISO|null" } ] } }
```

排序：createdAt DESC。anchor 投影，无 manifest/stage 细节。

### 2. case→graph 锚点（`sandboxCaseDataRouteAvailable` 翻转依据之一）

`GET /api/workspaces/{workspaceId}/cases/{decisionCaseId}/simulations?limit=`
→ items: `{ graphId, title, currentGraphVersionId|null, reportArtifactId, originModes[], createdAt, updatedAt }`

### 3. 报告读（canonical 既有行，新实现）

- `GET …/cases/{decisionCaseId}/reports?status=draft|ready&limit=` → summary items（reportId/analysisRunId/analysisLevel/type/status/caseVersion/contentHash/originModes/publishedAt/createdAt）；未知 status 过滤 = 诚实空页。
- `GET …/cases/{decisionCaseId}/reports/{reportId}` → summary + `structuredContent` + `validation` + sourceJudgmentSetId/sourceDissentRecordId。

### 4. 图版本读（canonical 既有行，新实现）

- `GET …/simulations/{graphId}/versions?limit=` → summary items（graphVersionId/version/status/title/caseVersion/branchId/parentVersionId/sourceGraphVersionId/sourceReportArtifactId/contentHash/originModes/createdAt/confirmedAt），version DESC。
- `GET …/simulations/{graphId}/versions/{graphVersionId}` → summary + `nodes[]`（nodeId/label/nodeType/baseline|current|min|maxValue/unit/normalization/sensitivityStep/controllability/authorship/evidenceStatus/evidenceQualityScore/evidenceIds/assumptionIds/rationale/reviewStatus/editable）+ `edges[]`（edgeId/sourceNodeId/targetNodeId/polarity/strength/delaySteps/authorship/evidenceStatus/relationshipQualityScore/rationale/claimIds/evidenceIds/assumptionIds/reviewStatus）。

### 5. Task 4/5 面（A2 交付路由已挂载）

subjects create/read、cases create/list/read/versions、candidates read/confirm/reject、messages、quick-analyses 现已在生成契约（ops 26→43）；scenario frames 继续经 `GET …/analyses/{runId}/strategic-lenses/{artifactId}` 读取（既有挂载面）。

## audit binding（MOUNT-02 Addendum A1 §A1-⑥，已闭合）

worker VALIDATING 阶段对 full run 调用 `audit_full_run_lens_set(referenced_artifact_ids=run.strategic_lens_artifact_ids 原样)`；不 ok ⇒ blocked，findings 追加 `{"code", "source": "lens_set_audit"}`。focused 跳过。红灯测试：`test_real_audit_blocks_full_run_when_persisted_set_is_corrupt`。

## 门禁记录

- test_case_reads 8/0（含 10 探针统一 404 矩阵、跨 case 报告坍缩、未知 status 空页）
- test_analysis_worker 7/0（as-is 传参钉死 + 真实审计红灯 + focused 零审计）
- 全量电池 934/0（基线 925 零回归 + 9 新增）；canonical 667/0（基线保持）
- generate_contracts.ps1 再生 + -Check = CONTRACT_DRIFT_OK（ops 26→43 additive）
- ruff all-pass；compileall exit 0；git diff --check clean

## Web lane 后续（READ-ROUTES-WEB-FLIP-R1）

翻 `evidenceAnchorsRouteAvailable` / `sandboxCaseDataRouteAvailable` + slotContracts status（已授权）；类型从再生 types.gen.ts 导入；混合可用性（report 有 graph 无）逐块空态。
