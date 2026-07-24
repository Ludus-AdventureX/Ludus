# SIM_REPOSITORY_SERVICE_R1_QA_CONTRACT_CLOSURE — 官方 TS 合同门补齐（doc-only follow-up）

- QA owner: qa_release；task_type = QA GATE CLOSURE ONLY（合同生成闭环，不重做产品/测试验证）。
- **本文档补齐的缺口**：上一轮 `SIM_REPOSITORY_SERVICE_R1_QA_HANDOFF.md` 的产品/测试验证为 PASS（417 全绿），
  但合同门只报告了 `OPENAPI_SEMANTIC_DRIFT_OK`（语义等价比较），**未运行官方
  `scripts/generate_contracts.ps1 -Check` 完整 TypeScript 链**。因此上一轮
  `RELEASE_CONTENT_VERDICT: PASS` 被发起方降格为 CONDITIONALLY_PENDING_CONTRACT_CLOSURE。
  本 closure 在 code/test 字节等价的 QA 树上运行了官方完整命令并取得 `CONTRACT_DRIFT_OK`，闭合该缺口。
- 上一轮 handoff 中的 PASS 自本文档起：**superseded for release gating by this contract-closure result**。
  产品与测试结论不变、不被重新否定；原 handoff 原样保留（未覆盖、未删除）。

## Refs（全部实时 ls-remote 精确验证，本 lane 第一条命令）

| ref | 期望 | 实测 | 结果 |
| --- | --- | --- | --- |
| main | `3ed23b92e0b2a1326518a6f550984abb02f11179` | 同左 | ✔ |
| prior QA `codex/qa-simulation-repository-service-r1` | `a2cc9878d8444565b100a6ecd088d02ecc169edf` | 同左 | ✔ |
| product `codex/task-simulation-repository-service-r1-doc-refresh` | `9cc4e8736bf59a1761d5de4f38081faed0081b07` | 同左 | ✔ |
| Addendum A1 `codex/ccr-sim-01-addendum-a1` | `b28dda67f9794d705e79ac45c2a1cf2458d7cf7b` | 同左 | ✔ |

无 BASELINE_STALE / REMOTE_SYNC_BLOCKED。closure 分支远端此前不存在（无碰撞）。

## Closure 分支与 direct-parent 证明

- 分支：`codex/qa-simulation-repository-service-r1-contract-closure`（全新独立干净 worktree，禁复用纪律遵守）。
- direct-parent proof：closure head `git log -1 --format=%P` = `a2cc9878d8444565b100a6ecd088d02ecc169edf`（唯一直接父 = prior QA head）。
  a2cc987 自身的唯一父 = 产品候选 9cc4e87（上一轮已证）。不 amend、不 force push。
- changed paths（scope audit，`git diff a2cc987..HEAD --name-only` 仅命中）：
  - `docs/handoffs/SIM_REPOSITORY_SERVICE_R1_QA_CONTRACT_CLOSURE.md`（新增，本文档）
  - `HISTORY`（纯追加）
  - HEAD 未改动（上一轮 QA 同样未触碰 HEAD，与 lane 惯例一致）。

## 官方完整合同检查 — CONTRACT_DRIFT_OK

从 closure worktree 仓库根目录运行官方命令（原文）：

```
powershell -File scripts/generate_contracts.ps1 -Check
```

官方 stdout（原文，逐行）：

```
CANONICAL_OPENAPI_EXPORTED E:\Temp\xiayu\Documents\adventure-x\decision-lab-G0\worktrees\qa-sim-repo-r1-contract-closure\.contract-check\contracts-check\openapi.json
✨ openapi-typescript 7.13.0
🚀 ...\.contract-check\contracts-check\openapi.json → ...\.contract-check\contracts-check\types.gen.ts [84.8ms]
CONTRACT_DRIFT_OK
```

exit code = 0。**未**用手工 OpenAPI JSON 比较替代；语义等价检查未被重命名为通过——通过标准就是官方脚本的 `CONTRACT_DRIFT_OK`。

### 环境（只读复用预置，零安装零联网）

- PATH 仅在当前 PowerShell 进程前置预置目录：`decision-lab\.tools\uv`（uv 0.11.30）与
  `decision-lab\packages\contracts\node_modules\.bin`（openapi-typescript 7.13.0）。未复制/安装/更新/提交 node_modules。
- closure worktree 无自有 `.venv`；以 NTFS junction 指向主 checkout 预置 `.venv`（Python 3.12.7），
  并设 `UV_NO_SYNC=1` + `UV_OFFLINE=1` 保证 uv 对预置 venv 零写入、零网络。
  等价性依据：a2cc987 与主 checkout HEAD 的 `services/api/pyproject.toml` blob OID 同为 `0f94168`、
  `packages/contracts/package.json` blob OID 同为 `1faea8d`（逐字节相同）。
- 再生产物落在 worktree `.contract-check/contracts-check/`（脚本默认回退路径）。如实登记一个既有仓库 quirk：
  `.gitignore` 中该目录的忽略行含字面 `` `r`n `` 残留，导致该目录显示为 untracked；本 closure 不将其入库、
  不越权修改 .gitignore（禁改路径），产物目录保留为证据。

### Contracts 产物零 diff

- `packages/contracts/openapi.json`：Git diff 为空 ✔（OpenAPI zero-diff verdict: PASS）
- `packages/contracts/src/types.gen.ts`：Git diff 为空 ✔（TypeScript zero-diff verdict: PASS）
- `git status --short` 无任何 contracts 产物改动（唯一条目为 untracked `.contract-check/`，未入提交）✔

## 字节与测试继承门 — 全过

- 以下目录 closure head vs `a2cc987` `git diff --stat` **全空**（product/test byte-equivalence verdict: PASS）：
  `services/api/app/**`（含 `app/simulations/tests/**`）、`services/api/tests/**`、
  `services/api/migrations/**`、`packages/contracts/**`、`scripts/**`、`apps/web/**`。
  所有 Python 产品与测试文件 blob OID 相对 a2cc987 精确相同（diff 空 = 树对象逐 blob 一致）。
- `git diff --check` 通过；无冲突标记；HISTORY 纯追加。
- 在字节门成立前提下继承上一轮新鲜实跑证据（**prior functional test evidence inherited by exact
  code/test byte identity**）：
  - full = **417 passed / 0 failed / 0 xfailed / 0 xpassed**（`-W error -rxX`，干净库 qa_sim_repo，单 head a3f8c2d47e19）
  - 同库 lens_lanes = **121 passed**
  - owner 52（含 engine 28）/ persistence 16 / read-path+IO 16 / models+invariants 34；QA 电池 15
  - doc-only closure 未人为重复全套 417。

## Findings

- **P0: 0. P1: 0. P2: 0.**
- P3（沿袭上一轮，未变化）：`formal_authorization_rejected` 映射待 CCR-SIM-02 路由层落地（QA 已有防漂移断言）。

## RELEASE_CONTENT_VERDICT: PASS

- 判定依据（五条件全满足）：417 全套代码/测试字节证据成立；官方 `generate_contracts.ps1 -Check`
  输出 `CONTRACT_DRIFT_OK`；contracts 产物零 diff；closure 分支 scope 合法；P0/P1/P2 = 0。
- 合入对象不变：**`9cc4e87`（产品）+ `a2cc987`（QA 电池）**；本 closure head 为 release gating 证据链终点，
  建议随 QA 分支一并合入以保留完整 handoff 链。合并前 Mainline Lead 须实时复读 remote main（须仍 `3ed23b9`）。
- push 后五 ref 实时回读记录见 HISTORY 追加条目。
