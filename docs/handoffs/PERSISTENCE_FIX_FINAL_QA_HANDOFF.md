# PERSISTENCE_FIX_FINAL_QA_HANDOFF — QA-WAYS-PERSIST-001 fix (009e0df)

- QA owner: qa_release; **QA branch/head**: `codex/qa-ways-lens-persistence-r2-p2-fix`（全新分支；QA commit 见 git log，推送后实时回读）。
- **exact_tested_head**: `codex/ways-lens-persistence-r2-p2-fix` @ **`009e0dfd03ae766b201ef5f6aeede1255671e5c4`**（`911bf87` 的直接子提交，唯一产品改动 = `strategic_lenses/repository.py`；被测组合 = 候选产品树 + 采纳自 `830e858` 并按修复合同收紧/扩展的 QA 测试）。`repository.py` 未被 QA 修改；QA 改动仅 `services/api/tests/**` + handoff/lifecycle。
- **remote verification（硬门）**：第一条命令 `ls-remote main` = `4de3628...` ✔；fix candidate = `009e0df...` ✔；原产品分支 = `911bf87...` ✔；原 QA 分支 = `830e858...` ✔。四 ref 全部精确，无 BASELINE_STALE / REMOTE_SYNC_BLOCKED。

## Verdicts

- **error mapping verdict (A): PASS** — 双 draft 竞争 ready：胜者恰好一个；败者收到 **`LensArtifactConflict`**（收紧后的测试不再容忍裸 `IntegrityError`，并显式断言异常非 IntegrityError 实例）；库内最终恰好一条 ready；约束名匹配映射（`uq_strategic_lens_artifacts_ready_per_run_lens` → Conflict，其他完整性错误 → `LensPersistenceError`）代码审阅确认。
- **savepoint verdict (B): PASS** — QA 测试**移除了自带的 savepoint 防护**：修复内部的 `begin_nested` 必须独立保住外层事务——冲突后同一调用方事务继续查询（ready 计数）并成功完成后续写入（败者 draft→rejected）双双实证；无 PendingRollbackError/失效 session。
- **rowcount verdict (C): PASS** — 幽灵 artifact → `LensRunNotFound`；terminal artifact → `LensArtifactImmutable`；**真实双连接竞争同一 draft**（NullPool 双 racer，提交语义）：恰好一胜，败者收到稳定领域错误（rowcount=0 → 重读 → Immutable，或读时已 terminal），零 silent success，库内恰好一条 ready；测试自清理避免污染全局计数断言。
- **QA-WAYS-PERSIST-001 状态: CLOSED** — A/B/C 全部通过（按指令不再使用 P2-001 编号）。
- **原 A-H 行为回归: PASS** — lane 套件 10 项（三键 tenancy、terminal/paused run 拒写、17 server-owned 字段拒绝、schema/behavior fail-closed、五类引用 ledger、幂等、ready 异 hash 冲突、draft→ready witness、draft→rejected 审计、terminal 不可变）+ QA 的 content_hash 确定性/origin_modes 去重全绿。
- **合同结论确认**：schema_version 短 SemVer 已按 Contract Lead 裁决 A 处理，非 CONTRACT_REVIEW；本轮未触碰列宽/模型/migration（changed set 实证）。
- **RELEASE_CONTENT_VERDICT: PASS** — P0=0, P1=0, P2=0 new。

## 实际测试计数（fresh，`-W error`，全新纯迁移库 `qa_persist_fix2`）

- 干净库：`upgrade head` → **`d7e2a91c5b48`**；`alembic check` 干净
- persistence 定向（lane + QA，同库同序）：**16 passed**（lane 10 + QA 6；候选声明的 13 = lane 10 + 830e858 的 3，QA 本轮净增 3 项 rowcount/竞争测试并收紧 1 项）
- 全量：`pytest tests app/simulations/tests` = **320 passed, 0 failed, 0 skipped**（= 候选声明 317 + QA 净增 3，自洽）
- `pytest tests/lens_lanes` = **121 passed**
- Ruff PASS；compileall exit 0；scope/secret/`git diff --check`/冲突标记扫描全干净

## Findings register

- P0: 0. P1: 0. P2: 0 new.
- **P3（QA 测试健壮性，非产品缺陷，已在 QA 侧缓解）**：lane 套件 `test_lens_persistence.py` 的 `_artifact_count` 为全表无作用域计数断言（`== 0`），任何提交型并发测试都会使其误报——QA 的竞争测试已加 run 级自清理规避；建议 lane 后续把计数断言限定到本测试的 run/workspace 作用域（owner: ways_agent_pipeline，非阻断）。

## 移交 Mainline Lead

内容放行：合入对象 = `009e0df` + 本 QA 分支 tip（被测组合，含收紧后的回归——合并后 double-ready 用例将永久拒绝裸 IntegrityError 回归）。合并前实时复读 remote main（须仍 `4de3628`）与候选 ref。
