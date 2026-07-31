# Git 禁令机械执行覆盖清单

生成日期：2026-07-29。本文件记录 `.githooks/` 与 `scripts/merge-preflight.ps1` 对 `AGENTS.md` 发布阻断规则与 Git 禁令的机械化覆盖映射。规则文字本身以 `AGENTS.md` 为准，本文件不改变、不替代任何规则。

## 激活方式

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup-hooks.ps1          # 激活
powershell -ExecutionPolicy Bypass -File scripts/setup-hooks.ps1 -Verify  # 校验
git config --local --unset core.hooksPath                                 # 停用
```

钩子通过 `core.hooksPath=.githooks`（仅本地 git config，不涉及远端配置）生效，对本仓库全部 worktree 共享；在未包含 `.githooks/` 的旧分支 worktree 中钩子目录不存在时静默不生效（与现状相同，无回归）。

## 覆盖映射

| AGENTS.md 规则 | 执行面 | 检查 | 失败行为 |
|---|---|---|---|
| §19/§21 MUST NOT force-push / 重写共享历史 | `.githooks/pre-push` | 检测 non-fast-forward（remote SHA 非 local SHA 祖先） | 拒绝；仅 `LUDUS_ALLOW_FORCE_PUSH=1` 显式确认后放行 |
| §19 仅 Mainline Integration owner 可更新 main | `.githooks/pre-push` | 拒绝任何对 `refs/heads/main` 的直接 push | 无条件拒绝 |
| §17/§19 只允许 canonical Private origin | `.githooks/pre-push` | push 目标 URL 必须精确等于 `https://github.com/Ludus-AdventureX/Ludus.git` | 无条件拒绝 |
| §13 MUST NOT 在已完成 Task 6 分支继续提交 | `.githooks/pre-commit` + `.githooks/pre-push` | 当前分支 / push 目标 ref 命中三个冻结分支名 | 无条件拒绝 |
| §13/§19 新开发使用 codex/<task-name> 分支 | `.githooks/pre-commit` | 拒绝在 main 上直接 commit | 拒绝；仅 `LUDUS_ALLOW_MAIN_COMMIT=1` 显式确认后放行 |
| §12 禁止提交 API Key/密钥/`.env`/`.key` | `.githooks/pre-commit` | 阻止 staged `.env`（`.env.example` 除外）、`*.key`；staged diff 高置信 secret 模式扫描（sk-/AKIA/ghp_/PRIVATE KEY） | 拒绝；仅 `LUDUS_ALLOW_SECRET_PATTERN=1`（误报场景）放行 |
| §4/§12 `探讨/.env`、`探讨/auth.json` MUST NOT 提交 | `.githooks/pre-commit` | banned path 精确匹配 | 无条件拒绝 |
| §17 根目录 MUST NOT 添加 LICENSE | `.githooks/pre-commit` + `merge-preflight` | staged/存在性检查 | 拒绝 / FAIL |
| §19 合并前必须新鲜读取 remote main SHA | `scripts/merge-preflight.ps1` | `git ls-remote origin main` 实时回执；失败即 blocked | FAIL（不得以本地缓存冒充远端结论） |
| §19 合并前检测 remote main 并发前进 | `scripts/merge-preflight.ps1` | 本地 main SHA == 远端 main SHA | FAIL |
| §14/§21 contract drift 必须 clean | `scripts/merge-preflight.ps1` | 委托 `generate_contracts.ps1 -Check` == `CONTRACT_DRIFT_OK` | FAIL |
| §14 lint/compile/合同校验/前端 build | `scripts/merge-preflight.ps1` | ruff / compileall / `verify_decision_os_contracts.py` / `pnpm build` | FAIL |
| §13 合并操作要求干净工作树 | `scripts/merge-preflight.ps1` | `git status --porcelain` 为空 | FAIL |

## 已知未覆盖项（仍依赖流程与人工）

- 远端（GitHub 服务器侧）分支保护：本次核查中 `gh` CLI 不可用（shim 指向缺失目标），无法读取远端 protection 配置；服务器侧 force-push/删除保护是否开启未验证。按 §19 属 blocked 状态。任何远端配置变更需产品方授权后另行执行。
- §19 QA verdict PASS / P0-P1 归零 / manifest owner 写域校验：需要结构化 QA 产物输入，暂无机械检查面。
- §18 HEAD/HISTORY 归档纪律、§20 worktree 回收授权：属于流程约定，不在 git 钩子可拦截面内。
- 旧基线 worktree（未含 `.githooks/`）内钩子不生效：合入 main 后随基线更新逐步覆盖。
