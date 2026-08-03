# CCR-20260803-MOUNT-REPORTS — 核实记录：reports/sandbox API 挂载状态

- Status: verified (no mount change needed)
- Date: 2026-08-03 (Asia/Shanghai)
- Owner: backend/runtime lane (wave F4)

## 结论

E2E 排查确认：**reports router（含因子沙盘 API）已经挂载**——
`app/tenancy/routes.py` 的 `workspace_router.include_router(reports_router)`
（Task 10/13 波次完成），契约（packages/contracts/openapi.json）早已包含：

- `GET  /api/workspaces/{workspaceId}/cases/{decisionCaseId}/reports`
- `GET  /api/workspaces/{workspaceId}/cases/{decisionCaseId}/reports/{reportId}`
- `POST /api/workspaces/{workspaceId}/cases/{decisionCaseId}/reports/{reportId}/exports`
- `GET  /api/workspaces/{workspaceId}/cases/{decisionCaseId}/sandbox`
- `POST /api/workspaces/{workspaceId}/cases/{decisionCaseId}/sandbox/preview`
- exports 读取/重试端点

## 排查过程记录

初始判断"sandbox API 未挂载"源于只检查了 `app/main.py` 的直接
`include_router` 调用，遗漏了 `workspace_router` 的子路由 include。
曾尝试在 main.py 二次挂载 reports_router，导致 Duplicate Operation ID
警告——已回滚（零契约变更）。

## 影响

无契约变更、无代码变更（main.py 回滚后与基线一致）。用户侧访问沙盘的
真实阻塞是：blocked run 不产生报告（fail-closed），以及前端 A 页是否
提供沙盘入口（Task 13 前端已交付，见 HISTORY）。
