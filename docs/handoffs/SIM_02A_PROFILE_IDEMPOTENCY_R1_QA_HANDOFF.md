# SIM_02A_PROFILE_IDEMPOTENCY_R1_QA_HANDOFF — CCR-SIM-02A P1+P3 独立 QA

- QA owner: qa_release；**QA branch**: `codex/qa-sim-02a-profile-idempotency-r1`（全新独立干净 worktree；head 见 git log，push 后实时回读见文末）。
- **exact tested product**: `codex/sim-02a-profile-idempotency-r1` @ **`fb75b8f5dc282b9df3cf8172e3ed114fe23ae29a`**（main `387041d` 直系后代，merge-base 精确 = main）。被测组合 = 产品树逐字节 + 本 QA 提交。
- **remote verification（硬门第一条命令）**：`ls-remote main` = `387041d40442faf16557b266ef3f844b7af8fb69` ✔；candidate = `fb75b8f...` ✔；contract `codex/ccr-sim-02a-run-api-contract` = `0289b2e...` ✔；`b2c7e9d4a1f6.down_revision = a3f8c2d47e19` ✔（git show 原文）。无 BASELINE_STALE / REMOTE_SYNC_BLOCKED / MIGRATION_HEAD_STALE。
- 合同 `CCR-20260724-SIM-02A.md` 经 `git show` 只读消费（471 行全文），未 merge/cherry-pick。

## 一：四项 MANDATORY OLD-QA FIXES — 全部修复，语义保持

| # | 测试 | 修复 |
|---|---|---|
| 1 | `test_models.py::test_core_table_set_and_workspace_scope` | 精确集合 +`decision_maker_profiles` +`idempotency_records`（**保持 exact equality，未放宽为 subset**）；两新表 workspace_id 列纳入既有 tenancy 扫描 |
| 2 | `test_models.py::test_task_19a_simulation_replay_numeric_constraints_are_enforced` | `seed_simulation_reference_stack` 扩展：种下合法冻结 profile（workspace-global v1），base insert 引用之；8 个数值约束负例原样保留（含 version 0） |
| 3 | `test_sim01_graph_contract_qa.py::test_simulation_run_frozen_refs_reject_cross_workspace_targets` | 每 workspace stack 各种一个 profile；baseline 用合法 profile；原 4 攻击保留；**新增真实 foreign profile ID 与真实 (ID, version) 对两个跨租户 FK 攻击** |
| 4 | `test_simulation_repository_service_qa.py::test_run_level_parameters_each_change_input_hash` | riskTolerance 不再是 request field：以 **profile v2（rt 0.61）选择走完整 service path** 验证 hash 变化；epsilon/maxSteps 断言原样保留；ghost version/ghost id 由"hash 不变"改为 **uniform 404 + 零残留行** |

复现纪律：修复前逐项在干净库复现 candidate handoff §5 宣称的 4 failures（第一项失败信息 `Extra items: idempotency_records, decision_maker_profiles` 原文留档）。

**修复后、QA 新增前组合基数 = 434 passed**（= current-main 417 + candidate 净新 owner 17，精确命中预测）。

## 二：迁移生命周期（全新库 `qa_sim02a_mig`，gate-r3 PG16）

- `heads` 恰一条 `b2c7e9d4a1f6`；upgrade→`current`=head；`alembic check` = "No new upgrade operations detected"
- **orphan preflight 负例**：升级至 `a3f8c2d47e19` → 种下合法 SIM-01 全栈 + ghost-profile run → `upgrade head` 精确 RuntimeError（"cannot be resolved ... backfill frozen profile rows or archive"），事务回滚、版本停留 a3f8c2d47e19 ✔
- **正例**：删除 orphan run 后 `upgrade head` 成功 ✔
- downgrade `a3f8c2d47e19`：两新表 + `fk_simulation_runs_workspace_profile_version` 精确移除；SIM-01 十表 + `simulation_runs.origin_modes` 全保留 ✔；re-upgrade + check ✔
- head 态清单：新 FK `convalidated=t`、`confdeltype=r`（RESTRICT）；4 个索引/唯一键在位；**零新 PG enum**（enum 全集盘点，无 idempot*/response*/profile*）✔

## 三：QA 独立电池（`tests/test_sim_02a_profile_idempotency_qa.py`，12 项，owner fixture 按路径加载零修改）

- **A Profile**：row PK 与 stable profile_id 分离（跨版本同 profile_id 异 row id）；UNIQUE(ws,profile,version) 双版本重复拒绝；version 0/-1、rt ±界外、空 display_name/content_hash、ghost workspace/user/case FK 九负例；rt **0.0/1.0 闭区间边界合法**；repository/service 无 update/delete 表面（独立扫描）
- **Profile 锚点攻击矩阵**：ghost id / ghost version 99 / version 0 / 真实 foreign ws profile / 真实 foreign **case-scoped** profile / 真实 foreign (id,version) 对 → **6 形态签名集合 = {("CASE_NOT_FOUND",404)}**（大小 1 不可枚举），零 run 残留
- **B content_hash**：**深层嵌套 key 乱序不变性**（canonical JSON 每层排序）；repository 签名无 content_hash 参数且传入即 TypeError；**独立 hashlib/json 重推导**种子行 content_hash 逐字节相等（未调用产品 helper，钉死 wire 形状）
- **C 冻结 FK**：pg_constraint `contype=f / convalidated=t / confdeltype=r / 引用表=decision_maker_profiles`；被引用 profile 行 DELETE → RESTRICT 拒绝
- **D Service authority**：SimulationRunRequest 无 risk_tolerance 字段、构造传入即 TypeError；baseline view+持久化行 rt=0.5（种子 profile 冻结值）；v2(rt 0.9) 选择 → view/行/hash 三处齐变；**profile scope 失败先于 engine**（run_simulation 哨兵未触发）+ 零行
- **E Idempotency（persistence only）**：**精确 11 列字段集**；UNIQUE(ws,route,key) 同 scope 拒绝、跨 workspace/跨 route 可复用；response_kind 仅 success/non_converged（"replayed"/"" 拒绝）；两个合同终态 (201,success)/(409,non_converged) 均可持久化；http_status 99/600 拒绝；expires_at<=created_at 拒绝；ghost workspace FK 拒绝；两索引在位；无新 PG enum；**simulation_runs 零 idempotency 列**；service/repository 源码零 idempotency 引用；`app.simulations.routes` 不存在、main/tenancy 无 simulations 挂载 → **当前无任何 route/header/replay/concurrency runtime flow** ✔
- **G P2 pending**：`engine.py` blob OID 与 main 逐字节一致（`a699e45`，git 证明；domain.py/openapi.json 同样等 blob）；`ENGINE_VERSION == "sim-engine-1.0.0"`；`compute_input_hash` 源无 profile/content_hash token；**同 rt 异 profile 身份 → 同 inputHash**（当前行为钉死，CCR-ENG-02 落地时必须翻转该断言 + bump ENGINE_VERSION）。P2 未实施 = **accepted pending dependency，非 finding**
- **H Addendum A1 非回归**：`score_constraint_operator_unsupported`（"="）与 `strategy_edge_gating_unsupported`（enabledEdgeIds 非空）owner+QA 双侧既有测试在 446 全量中全绿

## 四：CONTRACT_ERRATUM_CONFIRMED

CCR-SIM-02A §2 尾句 **"Internal service-level callers (tests) are unaffected until the route lands"** 与事实不符：composite FK + `SimulationRunRequest.risk_tolerance` 移除是结构性破坏（4 个 QA 基线测试失败，candidate handoff §4.2 已如实预申报，本轮已修复）。**QA 未修改合同文档**；交 Contract Lead 在 CCR-ENG-02 / SIM-02A addendum 修正措辞。

## 五：owner 测试审查

**test_ownership_verdict: ADOPT** — 17 项净新 owner 测试独立复跑全绿（owner 套件 69 = 52 r1 + 17）；深度合格：hash 决定性/every-field 敏感、append-only 双证、FK 三向攻击、case-scope 服务门、uniform 404、无 runtime flow 自检。QA 电池不依赖 owner 自证，独立面（pg_catalog 形状、独立 hash 重推导、闭区间边界、深嵌套排序、routes 缺失、P2 钉死）为净新增。

## 六：计数与静态门（全新库 `qa_sim02a`，单 head，check 干净）

- 定向：owner **69**（含 engine **28**）；persistence **16**（lens_lanes/test_lens_persistence 10 + _qa 6）；read-path+IO **16**；models+invariants **34**；QA 新电池 **12**
- **full `pytest tests app/simulations/tests -q -W error -rxX` = 446 passed / 0 failed / 0 xfailed / 0 xpassed**（= 434 + QA 12，自洽；434 非固定目标，实测值如实报告）
- 全套后**同库** lens_lanes = **121 passed** ✔
- 官方 `powershell -File scripts/generate_contracts.ps1 -Check` → **`CONTRACT_DRIFT_OK`**（exit 0；预置只读工具链：uv 0.11.30 + openapi-typescript 7.13.0，junction venv + UV_NO_SYNC/UV_OFFLINE，零安装零联网）；`packages/contracts` 零 diff（本切片零合同变化符合 CCR §10"生成仅由 I2 Contract Lead 执行"）
- ruff / compileall / `git diff --check` / 冲突标记 / secret（仅 fixture 占位符 `not-a-real-hash`）全干净
- scope audit：QA 仅触碰 `services/api/tests/**`（3 改 1 增）+ 本 handoff + HISTORY；产品/迁移/contracts/scripts/web 零触碰

## Findings

- **P0: 0. P1: 0. P2: 0.**（全部新 finding 维度）
- **P3-a**（owner: SIM-02A I1 lane）：`idempotency_records.http_status` DB CHECK 为 100..599 sanity 范围；合同 {201,409} 语义域由 I1 runtime flow 强制（合同仅对 response_kind 明文要求 enum-check）。QA 已实证两个合法值持久化、99/600 拒绝。I1 落地时 route 层必须只写 201/409。
- **P3-b**（备注）：idempotency_key 201 字符在 `VARCHAR(200)` 类型层截断拒绝（DBAPIError），先于 1..200 CHECK 评估——两层皆 fail-closed，无缺口。
- P2 engine hash gap = accepted pending（CCR-ENG-02），QA 已钉死当前行为防静默漂移。

## RELEASE_CONTENT_VERDICT: PASS

- **ready_for_public_route = NO**（合同 §2/§3 双封锁：P2 engine hash 未落地；无路由存在——QA 实证）
- **ready_for_CCR_ENG_02 = YES**（engine.py 与 main 字节一致的干净基座；profile 持久化 + FK + service authority 全部就位；QA 钉死断言将在 ENG-02 处精确翻转）
- 允许 Mainline Lead 合入：对象 = `fb75b8f` + 本 QA tip（4 项基线修复 + 12 项电池成为永久回归）。合并前实时复读 remote main（须仍 `387041d`）与 candidate/contract 两 ref。
