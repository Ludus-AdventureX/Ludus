# 23. 3/4/6 Agent 容量与执行计划

## 目的

本文把团队容量与交付范围分开，防止把“更多并发”误写成“完整 MVP 一定能在 72 小时完成”。机器任务、owner、依赖与 write scope 以 `agent-work-manifest.yaml` 为准。

- **6 Agent / 72h**：只用于 Hackathon Prototype Slice；
- **4 Agent / 108h**：完整 MVP 的优先稳健档；
- **3 Agent / 144h**：完整 MVP 的最小核心档；
- 少于 3 个持续槽位、不能隔离 worktree 或缺少 Contract Lead 时必须重新估算。

## 共同 Gate 0

任何档位计时前都必须通过：

- canonical 文档、CCR-20260721-003 与最终修复审计无阻断冲突；
- `decisionCaseId/analysisRunId`、Source、DeepAnalysis、权限、Signoff、abstain、Simulation 合同验证；
- `ways/hardtech-market-direction/1.1.0` 安装与 31-Skill 双账本检查；
- Docker/Postgres、Python/Node/pnpm、浏览器环境；
- OpenAPI/TypeScript drift clean；
- `.gitignore`、secret scan、CSRF、connector master key 和 SSRF 配置；
- 配置的模型/provider 进行 launch-time probe；无 live key 可做不计时离线开发，但不能宣称 live Gate 通过；
- 每条泳道独立 `codex/*` branch/worktree；
- manifest DAG、owner/scope validator 通过；
- Task 17 依赖 Task 19；Task 18A 只负责部署封装，最终 Task 18 同时依赖 Task 18A、Task 17 和 Task 19。

## 不可降级核心

所有档位都必须保留：

- 单一合同生成链；
- Workspace 隔离、UserSession 撤销和 capability；
- pre-run/run-frozen SourceRecord/SourceSpan；
- confirmed Charter 与真实 AnalysisRun；
- V1–V9 blocker fail-closed 与 no-run-no-report；
- option/abstain；
- 完整 SignoffPayload、人类 sign、append-only DecisionRecord；
- fixture/cached/live 真实标识；
- Simulation inputHash 与非收敛不进入正式建议；
- Look V7 五工作区与静态原型不进入生产运行时。

## 6 Agent / 72h：Hackathon Prototype Slice

### 槽位

| 槽位 | Owner | 主要任务 |
|---:|---|---|
| 1 | Contract/Integration Lead | 合同、迁移、生成类型、Task 18A 部署封装、集成门、Task 19 gate 审批 |
| 2 | Ways/Agent Pipeline | 方法、Agent Engine、V1–V9、Report Publisher |
| 3 | Case/API/Data | auth/session/workspace、Case/Source、signoff/Decision |
| 4 | Web/UX | Task 1W Look snapshot、五工作区 Shell、Task 14W Decision/Review/dialog |
| 5 | Simulation/Graph | confirmed fixture graph、纯函数引擎、inputHash、最小 sandbox |
| 6 | QA/Release | contract/security/E2E、Task 18 发布验证、恢复与演示资产 |

### 范围

使用 `12-72-hour-execution-plan.md` 的“必须交付/Stretch”边界。后端可以用通用 artifact viewer 显示五项 lens；PDF、完整图编辑、分支比较、BYOK UI、完整 Review 和十主题全部精修不阻断 Prototype。任何 stretch 完成后也不能扩大不可降级合同。

### 冻结点

- 12h：auth/session/Workspace、schema/migration、Look shell；
- 30h：Case snapshot、Source freeze、Charter/Run/SSE；
- 48h：V1–V9、报告、最小 sandbox；
- 60h：Signoff/Decision 与 E2E；
- 60–72h：只修 blocker、部署、彩排和恢复。

### 成立条件

六个槽位必须持续可用，不把 Contract Lead 兼任为两个实现 owner；每 6 小时集成。缺一持续槽位即停止沿用 72h 估算，不把剩余任务改写成单 Agent 的线性 72h。

## 4 Agent / 108h：完整 MVP 优先档

### 槽位

| 槽位 | 合并 owner | 范围 |
|---:|---|---|
| 1 | Contract/Integration + QA gate | schema、迁移、contract、安全门、集成、release |
| 2 | Ways/Agent Pipeline + Report | 方法、Provider、Source consumers、五 lens、V1–V9、HTML/PDF |
| 3 | Case/API/Data + Simulation API | auth/Workspace、Case、connector/file、graph/simulation、signoff/Decision/Review |
| 4 | Web/UX + E2E | Look V7、五工作区、完整图 UI、BYOK UI、Review、Playwright |

### 目标范围

完整 MVP 包含：quick/focused/full、五 lens 专用 UI、HTML/PDF、PDF/TXT/Markdown、至少一种 BYOK UI、完整图审阅/工作副本/分支/比较/回滚、完整 Review、十主题与三视口。DOCX/CSV/JSON、复杂协作、多方法包和计费仍可在 MVP 后。

### 冻结点

- 0–18h：Gate、合同、auth、Workspace、Look snapshot；
- 18–45h：Case/Source/Charter/Run/证据；
- 45–75h：五 lens、报告、HTML/PDF、connector/file；
- 75–93h：完整沙盘、Signoff/Decision/Review；
- 93–108h：集成、安全、E2E、部署、彩排。

每 9 小时集成。Contract Lead 在合并窗口不得同时承担大块业务实现。

## 3 Agent / 144h：完整 MVP 核心档

### 槽位

| 槽位 | 合并 owner | 范围 |
|---:|---|---|
| 1 | Contract/Backend Lead | schema、迁移、auth、Workspace、Case、Source、signoff、release |
| 2 | Analysis/Simulation Lead | Ways、Provider、证据、V1–V9、报告、图/Simulation |
| 3 | Web/QA Lead | Look V7、generated client、五工作区、E2E、部署、演示 |

### 阶段

- 0–24h：合同、环境、auth/Workspace、Look snapshot；
- 24–60h：Case/Source/Charter/Run；
- 60–96h：五 lens、报告、HTML/PDF、connector/file；
- 96–126h：完整沙盘、Signoff/Decision/Review；
- 126–144h：E2E、安全、部署、恢复。

每 12 小时集成。任何 owner 同时只能有一个 in-progress task；跨 owner 文件改动必须先 handoff，不能共享可写工作树。

### 预批准宽度降级

如果 108/144h 仍超时，可按顺序延后：DOCX/CSV/JSON、多个 BYOK provider UI、移动端图编辑、次要 lens 可视化、主题动画。不得延后不可降级核心、PDF、完整图版本链、Signoff、Decision/Review 保存读取或至少一种 BYOK UI。

## Task 19 发布硬化门

Task 19 不再用一个 secondary owner 横跨全部实现路径：

- **19A / Contract Lead**：canonical schema、migration、OpenAPI/types；
- **19B / Case/API/Data**：Source freeze、session/capability、lifecycle、Signoff、Decision、no-run-no-report backend；
- **19C / Ways/Agent Pipeline**：Cynefin、DeepAnalysis、V1–V9、abstain 与 publisher；
- **19D / QA/Release**：专项 tests、manifest/DAG/scope、E2E 和验证报告；
- **Task 19 gate / QA + Contract approval**：汇总 19A–19D，无产品实现 write scope，只产出 gate 报告。

Task 17 必须等待 Task 19 gate；Task 18A 可提前准备镜像/CI，但最终 Task 18 必须等待 Task 18A、Task 17 和 Task 19 gate。任何档位都不能把发布硬化留到最终发布验证之后。

## Manifest 独占切片

为满足 `one_write_owner_per_path`，机器调度额外使用三个不改变产品范围的 owner 切片：

- **Task 1W / Web/UX**：创建 `apps/web/**`、Look snapshot、design tokens；Task 1 不再写这些路径；
- **Task 14W / Web/UX**：在 Task 14 API 后接入 `decision` 工作区与 Review dialog；Case/API/Data 不写前端；
- **Task 18A / Contract Lead**：镜像、Compose 与 CI；最终 Task 18 / QA 只写 runbook、handoff 与演示资产。

测试与发布证据统一由 QA/Release owner 写入；canonical `schemas.py`、migration 和生成合同统一由 Contract Lead 写入。Report Publisher 归 Ways/Agent Pipeline，Case/API/Data 通过生成合同调用，不共享该文件。

## Agent handoff 合同

每个 handoff 至少包含：

```yaml
from_owner: case_api_data
to_owner: web_ux
task_id: task-14
contract_revision: CCR-20260721-003
inputs:
  - packages/contracts/openapi.json
  - packages/contracts/src/types.gen.ts
artifacts:
  - endpoint/status summary
  - fixture IDs
  - tests and results
open_risks:
  - external provider not live-verified
```

消费者不能根据自然语言补字段；发现缺口提交 CCR。QA 只写测试、报告和 handoff，源缺陷由原 owner 修。

## 自动档位切换

- 6 槽位不足：72h Prototype 估算失效；如果目标仍是完整 MVP，切 4/108 或 3/144；
- 4 槽位不足：切 3/144；
- 少于 3 槽位或无独立 worktree：停止引用本文时数，重新排期；
- Gate 0、合同或安全门失败：任何档位计时暂停，恢复后重新确认基线；
- 目标从 Prototype 改为完整 MVP：即使仍有 6 Agent，也必须重新估算，不能自动沿用 72h。

## 完成定义

- 实际容量档、范围和冻结点已记录；
- manifest DAG/owner/scope 校验通过；
- 每个共享生成物只有一个 owner；
- Task 19A–D 与 gate 完成，Task 17/18 依赖生效；
- Prototype 与完整 MVP 的完成声明没有混用；
- 验证、未验证项和剩余风险在 handoff 中明确。
