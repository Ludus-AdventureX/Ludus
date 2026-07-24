# LENS_ARTIFACT_IO_INTEGRATION_QA_HANDOFF — 统一 IO 集成候选 (r1)

- QA owner: qa_release; **QA branch/head**: `codex/qa-lens-artifact-io-integration-r1`（QA commit 见 git log，推送后实时回读）。
- **exact tested candidate**: `codex/lens-artifact-io-integration-r1` @ **`239bb7de7fde967aae31dd6e99e5580f6219c4db`**（product-equivalent `9cff0f3` 已验证：差异仅 HEAD/HISTORY）。被测组合 = 候选产品树（逐字节）+ 本 QA 提交（测试隔离修复 + 5 项组合语义固化）。
- **remote verification（硬门）**：第一条命令 `ls-remote main`（443 间歇，重试后成功）= `4de362835f...` ✔ 精确；candidate ref = `239bb7de...` ✔ 精确。无 BASELINE_STALE / REMOTE_SYNC_BLOCKED。QA 分支推送后实时回读见文末。

## Ancestry / 字节门

- **祖先**：base `4de3628`、persistence `009e0df`、persistence-QA `b5890f4`、read-path `2f0fe40`、read-path-QA `b44ec92` **全部**为候选祖先 ✔；**SIM-01 `4d45391` 非祖先** ✔（exit 1 实证）
- **装配序**：`f7f81c8`（persistence+QA）→ `9cff0f3`（read path+QA），persistence → read path ✔
- **字节门四区全空 diff**：`repository.py == 009e0df`、`lens_artifact_reads.py == 2f0fe40`、`test_lens_persistence_qa.py == b5890f4`、`test_lens_artifact_read_path.py == b44ec92` ✔
- **零改动区**：models/types/migrations/contracts/main.py/reports/agents 相对 base 空 ✔
- **lifecycle**：HISTORY 纯追加（172/0 numstat），产品冲突仅 HEAD/HISTORY，全树零冲突标记 ✔

## A: 独立干净库结果（`qa_io_r1` / 终验 `qa_io_r1_clean`，均纯迁移）

- `upgrade head` → **`d7e2a91c5b48`**；`alembic check` 干净
- 全量（候选原树）：**331 passed** = 候选声明精确一致；加 QA 的 5 项组合语义后终验 **336 passed / 0 failed / 0 skipped**
- lens_lanes **121**；persistence 定向 **16**；read-path 定向 **11**；io 组合语义 **5** —— 全部与声明一致或按 QA 增量自洽

## B: 测试隔离专项（按令复现，未用换库回避）

1. **复现成功**：同一库先跑全套（331 passed）→ 不清库跑 lens_lanes → **精确复现 6 failed**，全部命中 `test_lens_persistence.py`
2. **根因确认**：`_artifact_count` 为全表绝对计数（`select count(*) from strategic_lens_artifacts` 无作用域），被前轮提交型测试遗留行干扰 —— **QA-owned 测试隔离缺陷，非产品缺陷**
3. **修复（本 QA 分支，changed path = `services/api/tests/lens_lanes/test_lens_persistence.py`）**：`_artifact_count` 改为按**本测试 workspace 作用域**计数（7 处调用点更新；跨 workspace 用例同时断言攻击者与锚点两个 workspace 均为 0，语义比原全局断言更精确）；**未**清空业务表、**未**掩盖作用域问题
4. **修复证明**：
   - 脏库直接跑 lens_lanes：121 passed ✔
   - 同库连续：全套 336 → lens_lanes 121 → 再 lens_lanes 121 ✔
   - 变换顺序（io 语义 → lens_lanes → read-path 同批次）：137 passed ✔
   - 全新干净库终验：336 / 121 / 16 / 11 / 5 全绿 ✔

## C: 5 项组合语义（固化为 `tests/test_lens_artifact_io_semantics.py`，全过）

1. persist draft → ready-only list/get 不可见（get 统一 `CASE_NOT_FOUND`）✔
2. draft→ready → list/get 可见 ✔
3. draft→rejected → 普通消费不可见；review audit 可见；无 review capability → `MEMBERSHIP_CAPABILITY_REQUIRED` ✔
4. foreign workspace/case/run 锚点 → 三种入口统一 `("CASE_NOT_FOUND", 404)` 单一签名，不可枚举 ✔
5. persistence 返回的 artifact id 在正确三层锚点下重复读取字段级稳定一致 ✔

同步确认：schema_version 短 SemVer 语义不变；**QA-WAYS-PERSIST-001 保持 CLOSED**（收紧后的 double-ready 用例在候选树上原样绿）；canonical ordering porter→counterparty→pre_mortem→scenario→meadows 回归绿；review 门禁与 ready 唯一性/并发映射零退化（16+11 定向全绿）。

## 其他验证

- Ruff PASS；compileall exit 0
- Contract drift：`OPENAPI_SEMANTIC_DRIFT_OK`（候选零 contracts 触碰；官方 ps1 TS 全链依旧受 QA worktree 无 node_modules 限制，等效复现，历轮同一记录）
- scope/secret/`git diff --check`/lifecycle 冲突标记扫描：全干净
- **migration result**: current = `d7e2a91c5b48`，check 干净（两个独立新库分别验证）

## Findings

- **P0: 0. P1: 0. P2: 0 new.** 测试隔离问题按 owner 披露确认为 QA-owned 缺陷并已在本分支修复（原 P3 备注就此闭环）。

## RELEASE_CONTENT_VERDICT: PASS

允许 Mainline Lead 合入：对象 = `239bb7d` + 本 QA tip（被测组合；隔离修复与 5 项组合语义随 QA 分支进入主线后成为永久回归）。合并前实时复读 remote main（须仍 `4de3628`）与两个 ref。
