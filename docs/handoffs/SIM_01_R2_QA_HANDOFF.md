# SIM_01_R2_QA_HANDOFF — CCR-20260724-SIM-01 post-Artifact-IO 刷新候选 (r2)

- QA owner: qa_release; **QA branch/head**: `codex/qa-ccr-sim-01-integration-r2`（QA commit 见 git log，推送后实时回读见文末）。
- **exact tested candidate**: `codex/ccr-sim-01-integration-r2` @ **`1ff2cc9e37e8c8c14c9f1758a311ceae13662e26`**（product-equivalent `995bc83` 已验证：差异仅 HEAD/HISTORY）。被测组合 = 候选产品树（逐字节）+ 本 QA 提交（两个旧测试修复 + SIM-01 契约/wire 测试电池）。
- **remote verification（硬门）**：第一条命令 `ls-remote main` = `3ab888a...` ✔ 精确；candidate = `1ff2cc9e...` ✔；frozen source = `4d45391...` ✔。三 ref 全部精确，无 BASELINE_STALE / REMOTE_SYNC_BLOCKED。

## Ancestry / 字节门

- `3ab888a`(base)、`4d45391`(frozen source)、`3ee8e0a`(Artifact IO exact combination)、`ad8f9d3`、`d05abd3`（SIM 审计链）**全部**为候选祖先 ✔（审计链完整保留）
- **5 路径 vs 4d45391 逐字节一致**（types.py / models.py / simulations/schemas.py / migration a3f8c2d47e19 / CCR 文档）：diff 全空 ✔
- **Artifact IO 路径 vs main 3ab888a 一致**（repository.py / lens_artifact_reads.py / persistence+read-path+io 测试 / workspace 作用域隔离修复）：diff 全空 ✔
- 产品装配冲突仅 HEAD/HISTORY；HISTORY 纯追加（46/0）；全树零冲突标记 ✔

## 两个旧 QA-owned 测试修复结果（本 QA 分支，changed paths = tests/test_models.py）

1. **`test_core_table_set_and_workspace_scope`: FIXED & GREEN** — 精确集合加入 8 张 canonical SIM 表（未放宽精确断言，集合仍全等锁定）。
2. **`test_task_19a_simulation_replay_numeric_constraints_are_enforced`: FIXED & GREEN** — 新增 `seed_simulation_reference_stack` 助手：同 workspace/case 创建 lens artifact → causal_graph → graph_version → strategy_version → scenario_version → score_definition 完整合法链，四条复合 FK 全部满足；**原数值约束电池逐条保留**（steps/risk_tolerance/epsilon/max_steps/profile_version 8 项负例原样）。

## Migration lifecycle（独立干净库 `qa_sim01`）

- `alembic heads` → **恰一条 `a3f8c2d47e19`**；`upgrade head` → current = `a3f8c2d47e19`；`downgrade d7e2a91c5b48 → upgrade head` 往返干净；`alembic check` "No new upgrade operations detected"
- **orphan preflight 负例实证**：downgraded 态插入孤儿 simulation_run → upgrade **以清晰 RuntimeError 中止**（"has 1 orphan row(s) for graph_version_id; backfill or archive…"）；清除孤儿后 upgrade 成功（正例）
- **downgrade 移除验证**：8 表 = 0、6 新 enum = 0、4 条 sim FK = 0，共享 `origin_mode` enum 保留 = 1 ✔

## Table / enum / constraint verdict: PASS

- 8 张新表存在；**6 个 PG enum 精确**（graph_version_status/edge_polarity/factor_authorship/factor_evidence_status/factor_controllability/graph_branch_status，标签集与 Python enum 全等）；**`constraint_comparison` 无 PG enum** ✔
- **7 个 Python enum 值精确断言通过**（GraphVersionStatus/EdgePolarity/FactorAuthorship/FactorEvidenceStatus/FactorControllability/GraphBranchStatus/ConstraintComparison）。⚠️ **请求文本陈旧项如实登记**：请求所列 NodeNormalization/NodeControllability/NodeEvidenceStatus/GraphElementStatus 与 ConstraintComparison 四值（>、>=、<、<=）**不是** canonical——已接受 CCR 与 canonical `06-data-model.md` 定义为 Factor* 系列 + `ConstraintComparison` **五值（含 `=`）**；QA 按 canonical 契约断言（五值精确），normalization 为 CHECK 字符串列（linear/inverse_linear）。
- 4 条 simulation_runs 复合 FK **convalidated = true** 全部实证；NodeType 复用 canonical enum，`graph_nodes.node_type` 为 CHECK 字符串列；`review_status` DB 列 + CHECK（draft/confirmed/rejected）正确，wire 字段仍为 `status` ✔
- **ORM 负面（A-E）**：四类冻结引用"真实存在但属另一 workspace"攻击形态全部 FK 拒绝；edge 跨 version（source/target 各自）与跨 workspace 拒绝、同 version 合法；graph_version confirmed 缺 confirmed_at CHECK 拒绝、多条 confirmed 共存、**无** confirmed partial unique index（pg_indexes 实证）、current 指针无 FK（服务责任，合同已记录）；scenario source_lens_artifact 同 workspace 合法/跨 workspace 复合 FK 拒绝（lens_type/status 应用层校验如实登记为后续 service 责任）；score_definition content_hash 非空 CHECK、ConstraintRule wire 校验 operator/threshold/penalty（节点引用存在性 = 后续写路径责任，仅确认合同已记录，未虚构 service 行为）。

## Wire schema verdict: PASS（2 项纪律缺口以 xfail 探针登记，见 Findings）

- ScenarioVersion：`riskTolerance` extra=forbid 拒绝 ✔ + ORM 无 `risk_tolerance` 列 ✔；damping 0/1.01/-0.5 拒、(0,1] 收（含边界 1）✔；defaultEdgeMultiplier<0 拒；edge multiplier 负值/inf 拒；nodeShift ±1.01/NaN 拒、±1 边界收 ✔
- CausalNode：min>=max、baseline/current 越界、NaN/Infinity、evidenceQualityScore 越界全拒；边界收 ✔
- CausalEdge：strength/relationshipQualityScore 越界、delaySteps<0、非法 polarity/status 全拒 ✔
- GraphVersion：node/edge id 重复拒、edge 引用幽灵节点拒、confirmed 缺 confirmedAt 拒、server-owned identity 字段必填形状 + extra=forbid ✔

## 回归（六）与实际测试计数（fresh，`-W error`，干净库 qa_sim01）

- **全量 `pytest tests app/simulations/tests` = 374 passed, 0 failed, 4 xfailed**（对账：owner 基线 334+2 → 修复后 336 全绿 + QA 新增 38 绿 + 4 xfail 探针 = 374/4；不以 336 为固定目标，如实报告）
- 全套后**同库**再跑 lens_lanes = **121 passed**（Artifact IO 测试隔离修复零退化）✔
- 定向：persistence 16 / read-path+io 16 / **Task 12 engine 28** / models+invariants 34 全绿
- Ruff（app+tests+migrations）PASS；compileall exit 0

## Contract drift（七）

- `OPENAPI_SEMANTIC_DRIFT_OK`（canonical builder vs committed 语义全等；openapi.json/types.gen.ts 零变化——候选零 packages/contracts 触碰，scope 扫描实证）。官方 ps1 TS 全链在本 QA worktree 无 node_modules（历轮同一环境限制，等效复现，如实记录）。
- scope（packages/contracts、apps/web、main.py 零触碰）/secret/`git diff --check`/冲突标记扫描全干净。

## Findings（P0: 0 / P1: 0 / P2: 3 new，xfail 探针已入库追踪）

- **QA-SIM01-001 (P2, owner: sim graph contract lane)**：wire `CausalNode` 未拒绝 `evidenceStatus=supported` 且 `evidenceIds=[]`（AGENTS §10 证据纪律"禁止冒充 supported"目前无 schema 级守卫）。
- **QA-SIM01-002 (P2, 同上)**：wire `CausalEdge` 未拒绝 `status=confirmed` 且 `claimIds=[]`，亦未拒绝 claim/evidence/assumption 全空（§10"每条边必须保存来源"无守卫）。
- **QA-SIM01-003 (P2, 同上)**：自环边（source==target）在 **DB CHECK 与 wire 两层均未拒绝**（迁移无对应约束，GraphVersion 校验器不查自环）。
- 三项均为尚无消费方的合同纪律缺口（无 route/service 使用这些 wire 类型），不阻断本 schema 切片合入；修复属加严校验（additive），建议随图写路径 service CCR 一并落地。xfail 探针（strict=False）已随 QA 分支入库，owner 修复后转正即可。

## RELEASE_CONTENT_VERDICT: PASS

允许 Mainline Lead 合入：对象 = `1ff2cc9` + 本 QA tip（被测组合；两个旧测试修复 + SIM-01 契约电池随 QA 分支进入主线成为永久回归）。合并前实时复读 remote main（须仍 `3ab888a`）与两个 ref。三项 P2 已路由 sim graph contract lane，在图写路径 service 落地前修复即可。
