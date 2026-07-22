# Ludus Demo 开工准备审计

> **历史审计 / superseded：** 本文记录 2026-07-16 的环境与 V5.2 基线，仅供追溯；当前合同与开工结论以 `28-contract-repair-completion-audit-20260721.md`、CCR-20260721-003 和活动领域文档为准。本文不得作为实现或 Gate 0 当前状态来源。

- 审计日期：2026-07-16（Asia/Shanghai）
- 审计范围：`decision-lab-product-plan`、`decision-lab/ways`、V5.2 原型、本机 Gate 0、Git/worktree、外部服务与代码骨架。

## 结论

**Conditional Go：可以立即开始 Demo 的 Phase 0 和离线开发，但不能宣称所有要素齐全，也不能启动正式 72 小时集成计时。**

## 已具备

- P0 金路径、方法路由、Charter、运行时角色、五项 Strategic Lens、质量门、报告、沙盘、Decision、Review、测试和演示剧本已有合同。
- `hardtech-market-direction@1.1.0` 方法源存在，包含 manifest、Prompt、schema 和 eval；JSON 文件可解析。
- V5.2 静态视觉与关键交互原型已通过桌面和移动端回归。
- Node 22、pnpm 9、Python 3.12 和 Exa Key 可用。

## 产品合同状态

“自行添加影响因素并即时生成实验结果”的 canonical 合同已于 2026-07-16 通过 `CCR-20260716-001` 补齐：

- 入口仅位于按需展开的完整模型；
- 自然语言先生成 FactorCandidate 与候选关系；
- 因素类型、业务单位、基线、可控性、证据状态和理由均为必填合同；
- 用户必须确认、修改或否决候选节点和关系；
- 修改写入 revision 工作副本，并生成不可用于正式决定的 ExperimentPreview；
- 正式 SimulationRun 仍要求保存不可变 confirmed GraphVersion 并由用户主动运行。

因此 Graph/Simulation 的合同冻结门已经解除，但工程、环境和集成门仍未解除。

若该能力纳入 P0，需要同步 `06`、`09`、`10`、`11`、`13`、`14`、`17`、`18`、`24` 和 manifest/CCR。

## Gate 0 当前状态

- `uv` 缺失；默认 `python` 是 3.14.3，但 `py -3.12` 可用；
- Docker CLI 存在，但 Docker 服务停止；
- Postgres、Redis 未启动，连接配置缺失；
- DeepSeek Key 与模型能力 probe 缺失；
- Firecrawl、Tavily Key 缺失；
- `decision-lab` 不是独立 Git 仓库，父仓库没有首个 commit；
- worktree、分支、handoff 尚未创建；
- OpenAPI 到 TypeScript 生成链尚不存在；
- `fixtures/spherical-robot/{seed,external,expected}` 尚不存在；
- Python 3.12 环境缺少 YAML 与 JSON Schema 严格校验依赖。

## 当前代码状态

`decision-lab` 共有 34 个文件：33 个方法包文件和 1 个 `AGENTS.md`。后端、前端、迁移、API、Worker、测试和部署代码均尚未建立。

## 建议执行顺序

1. 按 accepted CCR 实现自定义因素 schema、migration、API、UI、fixture 与测试；
2. 初始化独立仓库和首个基线 commit；
3. 建立 backend、web、migrations、tests、fixtures 骨架；
4. 安装并固定 Python 3.12 与 uv 依赖；
5. 启动 Docker/Postgres，完成模型和连接器 probe；
6. 建立 OpenAPI 到 TypeScript 生成链；
7. 校验方法包并创建 Agent worktree；
8. Gate 0 通过后启动正式计时。

## Go / No-Go

| 事项 | 结论 |
|---|---|
| 初始化工程与离线 fixture 开发 | Go |
| Case、Dossier、Charter 等非模拟泳道 | Go |
| Graph / Simulation | Go（合同已冻结）；实现必须遵守 CCR-20260716-001，尚不可宣称功能完成 |
| live DeepSeek / Postgres 集成 | No-Go |
| 启动 72 小时 Demo 计时 | No-Go |

