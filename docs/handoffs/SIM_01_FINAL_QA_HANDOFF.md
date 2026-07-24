# SIM_01_FINAL_QA_HANDOFF — CCR-SIM-01 最终修复候选

- QA owner: qa_release; **QA branch/head**: `codex/qa-ccr-sim-01-final`（QA commit 见 git log，推送后四 ref 实时回读见文末）。
- **exact tested product head**: `codex/ccr-sim-01-db-self-loop-fix` @ **`9658e31b02b9c8d554c209c6bf2596f4c765379a`**（ancestry 精确：`1ff2cc9 → 228dd5d → 9658e31`，逐 parent rev-parse 实证）。被测组合 = 最终产品树（逐字节）+ 采纳自 `49c0321` 的完整 QA delta（审计确认仅 tests/handoffs/lifecycle，**未覆盖** schemas.py wire 修复 / models.py CHECK / migration CHECK）+ 本轮 4 个 xfail 转正。
- **remote verification（硬门）**：第一条命令 `ls-remote main` = `3ab888a...` ✔；final product = `9658e31...` ✔；prior QA = `49c0321` ✔；parent fixes `1ff2cc9`/`228dd5d` ✔。无 BASELINE_STALE / REMOTE_SYNC_BLOCKED。

## 二：4 个 xfail 转正结果 — 全部 CLOSED & GREEN

| 测试 | 处置 | 结果 |
|---|---|---|
| `test_causal_node_supported_requires_evidence_ids` | 移除 xfail 标记，断言原样 | **PASS** |
| `test_causal_edge_confirmation_requires_traceable_sources` | 移除 xfail 标记，断言原样（confirmed 无 claimIds + 三类引用全空双分支） | **PASS** |
| `test_causal_edge_self_loop_rejected_on_wire` | 移除 xfail 标记，断言原样 | **PASS** |
| `test_graph_edge_self_loop_is_rejected`（DB 级） | 移除 xfail 标记，断言原样（真实 insert 被 CheckViolation 拒绝） | **PASS** |

未删除测试、未放宽异常、未改 payload、未 skip、wire 与 DB 双层均独立验证。**QA-SIM01-001/002/003 全部 CLOSED**。

## 三：产品字节与约束复核

- **Wire (228dd5d)**：`schemas.py` 实证包含——supported node 要求 evidenceIds 非空；confirmed edge 要求 claimIds 非空；每条边至少一类 traceable source；GraphVersion 校验器拒绝 `sourceNodeId == targetNodeId`（ValidationError）✔
- **DB (9658e31)**：`models.py`（`name="no_self_loop"` → 规范前缀展开）与 migration（`op.f('ck_graph_edges_no_self_loop')`）**同名同语义** `source_node_id <> target_node_id`；pg_constraint 存在，**convalidated=t**，def = `CHECK ((source_node_id <> target_node_id))`；source≠target 可写、source==target 拒绝（DB 测试实证）；downgrade 后约束随表消失（count=0）、re-upgrade 恢复 ✔
- 最终产品 delta（228dd5d..9658e31）仅 models.py + migration；packages/contracts、apps/web、main.py 相对 base 零触碰（scope 扫描）✔

## 四：Migration lifecycle（独立干净库 `qa_sim01_final`）

- `heads` 恰一条 `a3f8c2d47e19`；`upgrade → current = a3f8c2d47e19`；`downgrade d7e2a91c5b48 → upgrade head` 往返；`alembic check` 干净
- 8 张 SIM 表 / 6 PG enum / 7 Python enum 精确（r2 电池随 QA delta 全绿复跑）；4 条 simulation_runs FK + 2 条 edge same-version FK **全部 convalidated=t**；DB self-loop CHECK 在位
- **orphan preflight 在最终迁移文件上重证**：负例（孤儿行 → RuntimeError 中止）+ 正例（清除后 upgrade 达 head）✔；downgrade 保留共享 `origin_mode` enum ✔；单 head 无分叉 ✔

## 五：完整回归与实际测试计数（fresh，`-W error`，`-rxX` 显式核查）

- **全量 `pytest tests app/simulations/tests` = 378 passed, 0 failed, 0 xfailed, 0 xpassed** —— 与预测 378 精确一致（374 + 4 转正）；无新 warning（-W error 下全绿）；无 skip/xfail/xpass 隐藏失败
- 全套后**同库** lens_lanes = **121 passed**（Artifact IO 隔离修复零退化）
- 定向：SIM schema+ORM 42（含 4 项转正）/ Task 12 engine 28 / persistence 16 / read-path+IO semantics 16 / models+invariants 34 全绿
- Ruff（app+tests+migrations）PASS；compileall exit 0

## 六：Contracts 与静态门禁

- `OPENAPI_SEMANTIC_DRIFT_OK`；openapi.json/types.gen.ts 零变化（候选零 contracts 触碰）。官方 ps1 TS 全链受 QA worktree 无 node_modules 限制（历轮同一记录，等效复现）。
- `git diff --check` / scope audit / secret scan / lifecycle 冲突标记扫描全干净。

## Findings

- **P0: 0. P1: 0. P2: 0 new.** 前轮三项 P2（QA-SIM01-001/002/003）全部 CLOSED。

## RELEASE_CONTENT_VERDICT: PASS

SIM-01 达到 **RELEASE_READY / MAINLINE_INTEGRATION_PENDING**。允许 Mainline Lead 合入：对象 = `9658e31` + 本 QA tip（被测组合；4 项转正测试与全部 SIM 契约电池成为永久回归）。合并前实时复读 remote main（须仍 `3ab888a`）与两个 ref。
