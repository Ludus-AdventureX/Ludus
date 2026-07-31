# Worktree 清理与集成待办 — 2026-07-29

## 背景

依据 AGENTS.md 第 20 节 worktree 生命周期约定,经产品方逐项授权,于 2026-07-29 完成存量 worktree 全量审计与清理。

## 清理结果

- 清理前:109 个 worktree(含主工作树),无悬挂条目。
- 清理后:仅保留 2 个 —— `decision-lab`(主工作树)与 `decision-lab-mainline-integration`(main 分支 checkout)。
- 107 个已完结任务的 worktree 目录已删除;**全部 137 个本地分支保留**,历史提交零丢失。
- 审计明细:`../../../output/worktree-audit.csv`(仓库外部,盘点快照)。
- 已删除 worktree 中不在任何提交里的 9 个孤本文件与 2 份 tracked 改动 diff,归档于仓库外部 `../../../output/worktree-archive/`(均为 QA 探针副本,其正式版本已在 main)。

## 集成待办(内容尚未进入 main,分支已保留)

按 AGENTS.md 第 19 节,以下分支的集成 MUST 由指定 Mainline Audit/Integration owner 走 QA 门与合同检查流程,不得直接合并:

| # | 分支 | HEAD SHA | 内容 | 优先级建议 |
|---|------|----------|------|-----------|
| 1 | `codex/workspace-ledger` | d6e7a0a | Web 修复 4 连:ProjectDrawer 真实案例列表(GET /cases)、composer 候选提取失败降级(MODEL_OUTPUT_INVALID 单次重试)、/api rewrite 3 分钟 proxyTimeout(修复 ECONNRESET)、compose 传递 MODEL_*/worker | 高——均为用户可感知缺陷修复 |
| 2 | `codex/task11-evidence-b2-r2` | 684ec5d(其集成分支 `codex/task11-evidence-b2-r2` 顶点 a581ece 含 main 回合并) | Task 11 Evidence B2 对抗性缺口收尾(EvidenceDrawer/报告解析链) | 中——main 已含 B2-r1,需 diff 复核 r2 增量是否仍适用 |
| 3 | `codex/task-13-sandbox-r1` | efa8722 | `CCR-20260725-SANDBOX-01.md` 等治理/合同文档不在 main;含 Task 13 sandbox 次级范围正式化 | 中——文档型,需 Contract Lead 复核 CCR 状态 |

## 已判定"被 main 吸收、无需集成"的未并入分支(留档说明)

`codex/task-12-simulation-engine`(被 r2 取代)、`codex/task-07-agent-runtime`(被 r2 取代)、`codex/task-11-web-analysis-shell`/`-r2`(被 Task 11 phase0 shell 取代)、`codex/qa-*` 各 QA 留痕分支(QA 记录,正式测试已在 main)、`codex/lens-scenario-r2`/`codex/task-19a-contract-hardening-fixes`(仅 HEAD/HISTORY 归档提交)。

## 验证记录

- `git worktree list` 输出 2 条,与磁盘一一对应,missing=0。
- `git branch --list` 计数 137,清理前后不变。
- 3 个集成候选分支 `git branch --list` 逐一确认存在。
