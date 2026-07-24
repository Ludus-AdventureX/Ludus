# SIM_REPOSITORY_SERVICE_R1_QA_HANDOFF — Simulation Repository & Service (r1)

- QA owner: qa_release; **QA branch/head**: `codex/qa-simulation-repository-service-r1`（全新 worktree/分支；QA commit 见 git log，推送后实时回读见文末）。
- **exact tested product head**: `codex/task-simulation-repository-service-r1-doc-refresh` @ **`9cc4e8736bf59a1761d5de4f38081faed0081b07`**。被测组合 = 产品树逐字节 + 本 QA 提交（独立电池 `tests/test_simulation_repository_service_qa.py`，15 项）。QA 未触碰任何禁改路径。
- **remote verification（硬门）**：第一条命令 `ls-remote main` = `3ed23b9...` ✔；doc-refresh = `9cc4e87...` ✔；impl parent = `7844a16...` ✔；Addendum A1 = `b28dda6...` ✔。四 ref 全部实时精确，无 BASELINE_STALE / REMOTE_SYNC_BLOCKED。

## 一：Ancestry / 装配 / 字节门 — 全过

- `3ed23b9` 是 `7844a16` 祖先 ✔；`7844a16` 是 `9cc4e87` 唯一直接父（rev-parse）✔；产品差异仅 `domain.py` 模块 docstring + doc-refresh handoff/lifecycle ✔
- **`DOMAIN_EXECUTABLE_AST_EQUIVALENT`**：去 docstring 后两版 AST 精确等价（程序化验证）✔
- 12 个文件 vs `7844a16` 逐字节一致（repository/assembly/service/errors/engine/schemas/owner tests/types/models/migration/openapi.json/types.gen.ts：diff 全空）✔
- main 区（strategic_lenses/analyses/engine.py/contracts/web/agents/main.py）vs `3ed23b9` diff 全空 ✔
- 零冲突标记；HISTORY 纯追加（122/0）；stale 句 "graph-side wire types do not yet exist" **产品代码零命中**（HISTORY/handoff 中 2 处为"扫描结果 0 hits"的历史引用记录，非文档残留，如实登记）✔
- Addendum A1（`b28dda6`）按 authoritative input 精确读取，未 merge/cherry-pick 到 QA 分支 ✔

## 三：Addendum A1 验证 — 全 PASS（未反向登记为缺陷）

- **A UUID identity**：零 node_key/edge_key（模型/迁移/wire 扫描）；repository 对节点与边显式 `ORDER BY id ASC`（源审阅 + 测试实证）；assembly 对乱序输入产出相等结果；Scenario/Strategy/Score 节点/边引用均为 UUID Identifier ✔
- **B "=" fail-closed**：`=` 经显式成员检查拒绝（**先于** `Comparison()` 映射，不可能落入 `<=`——代码审阅 + 断言错误信息无 `<=`）；engine 被 monkeypatch 哨兵证实未执行；零 SimulationRun 插入；稳定错误 `score_constraint_operator_unsupported` ✔（PASS，非 finding）
- **C enabledEdgeIds fail-closed**：非空即 `strategy_edge_gating_unsupported`，engine 未执行，零插入 ✔（PASS，非 finding）
- **D Enum authority**：`domain.Controllability is FactorControllability`、`EvidenceStatus is FactorEvidenceStatus`、`EdgePolarity`/`GraphVersionStatus` 同为 `app.types` 身份别名（is 断言）；`ElementStatus/Normalization/Comparison` 保持 engine-internal（`__module__` 断言，Comparison 精确四值）✔

## 四/五：Repository tenant scope 与 Lens 溯源

- 10 个 repository 方法源审阅：**每条 SELECT 在 SQL 层绑定 workspace_id**（多数额外绑定 decision_case_id），无"裸 UUID 查询后 Python 补租户"路径；授权唯一来源为已验证 `WorkspaceContext`，`SimulationRunRequest` 无可覆盖的裸 workspaceId 字段（frozen dataclass 字段清单审阅）✔
- **真实跨租户 ID 攻击矩阵**（QA 独立测试）：foreign case/graph_version/strategy/scenario/score（各自真实存在于 B 租户）、5 类 ghost、混合合法锚点（graph A + strategy B + scenario A + score B）→ **11 种攻击全部同一 `("CASE_NOT_FOUND", 404)` 签名**（集合大小 1，不可枚举）；同 workspace 其他 Case 锚点同签名；同 Case 跨 graph 聚合（scenario/strategy/score graph_id 不匹配）→ 同租户稳定 `graph_scope_mismatch`（owner 测试覆盖）；全部零 SimulationRun 残留 ✔
- **Lens 溯源**：合法（同 ws/case + scenario_planning + ready）执行成功；draft/rejected/wrong-type/其他 case 的真实 ready lens → 统一 404 签名（4 变体集合大小 1），零插入；ghost lens 无法持久化（复合 FK 拒绝，DB 层实证），其枚举面由 ghost scenario_version 覆盖 ✔

## 六/八：确定性装配与 inputHash

- repository 返回按 UUID 升序；`assemble_graph(乱序) == assemble_graph(正序)`；owner 套件另有反向插入世界验证 ✔
- **JSONB 防御性复制**：装配后改写 node_overrides/node_shifts/edge_multipliers/三类 score 列表 → 装配对象逐项不变 ✔
- 同冻结输入重复运行：inputHash/nodeResults/optionScores/steps/convergence 逐项一致 ✔
- **真实持久化 graph v2 全 service 路径**：v2（克隆节点新 UUID + 一条边 strength 0.8→0.7 + v2-scoped score）→ inputHash 变化 ✔；riskTolerance/epsilon/maxSteps 各自变化 → hash 各自变化 ✔
- **profile id/version 不改变 hash——per 冻结 Task 12 规则**（`engine.compute_input_hash` payload 字段：engineVersion/mode/epsilon/maxSteps/riskTolerance/graph/strategy/scenario/scoreDefinition/nodeOverrides；profile 是 run 元数据，其影响仅经冻结 riskTolerance 进入）。QA 按合同断言不变，未改 hash 算法 ✔

## 七/九/十：formal/experimental、生命周期与错误映射

- **Formal 双门**：draft 图 formal → 拒绝且零行；**monkeypatch 绕过 service 预检后 engine 内门仍拒绝**且零行 ✔。当前边界表面错误为 engine 的 `SimulationAuthorizationError`（结构化领域错误）；`errors.FormalAuthorizationError.code == "formal_authorization_rejected"` 已注册为 envelope 映射（断言绿）——见 P3 备注。
- **Experimental**：draft 图允许（Task 12 合同）、以 experimental 持久化恰一行；graph 仍 draft/无 confirmed_at、case options 不变、七类冻结输入表行数逐表不变（无 UPDATE/DELETE、无 DecisionRecord/Signoff/DomainEvent 伪造）✔
- **compute-then-insert 零僵尸行**：engine 失败（owner）/sensitivity 失败/wire 自检失败/insert SQLAlchemyError 四条失败路径全部增量 0；insert 失败映射 `simulation_persistence_failed`（非 SQLAlchemyError 实例、消息无 asyncpg/IntegrityError 泄露）、rollback 后 session 继续可查 ✔
- 持久化字段精确（owner round-trip 测试 + QA view 断言）；`SimulationRunView` frozen dataclass 非 ORM，tuple 字段不可变，setattr 抛 FrozenInstanceError ✔；ScenarioVersion 无 riskTolerance（ORM 列扫描），run-level riskTolerance 来自冻结请求输入 ✔

## 十一：Owner 测试审查

**test_ownership_verdict: ADOPT** — 24 项 owner 测试独立复跑全绿（52 passed 含 engine 28）；rollback-only session fixture、反向插入世界、覆盖面与断言质量合格；QA 独立电池（15 项）覆盖全部指令要求的最低独立面，未依赖 owner 自证（owner fixture 仅按路径加载复用 seeding，零修改）。

## 十二：Migration / 回归 / 静态（独立干净库 `qa_sim_repo`）

- `heads` 恰一条 `a3f8c2d47e19`；`upgrade → current = a3f8c2d47e19`；`check` 干净；本候选零 migration 变化（字节门）✔
- 定向基线**全部精确命中**：owner 52 / engine 28 / persistence 16 / read-path+IO 16 / lens_lanes 121 / models+invariants 34；QA 新电池 15 passed
- **full `pytest tests app/simulations/tests -q -W error -rxX` = 417 passed, 0 failed, 0 xfailed, 0 xpassed**（= 候选基线 402 + QA 15，自洽；无隐藏失败/无新告警）
- 全套后同库 lens_lanes = 121（隔离修复零退化）✔
- `OPENAPI_SEMANTIC_DRIFT_OK`（contracts 零触碰；官方 ps1 TS 全链同历轮 node_modules 环境限制，等效复现）；ruff/compileall/`git diff --check`/scope/secret/冲突标记全干净

## Findings

- **P0: 0. P1: 0. P2: 0.**
- **P3（非阻断备注，owner: sim service lane / Contract Lead）**：`errors.FormalAuthorizationError`（code `formal_authorization_rejected`）当前无产品调用方——service 边界表面 engine 的 `SimulationAuthorizationError`。这与"只验证当前 repository/service 边界，不虚构 route 行为"一致；CCR-SIM-02 路由层落地时必须把 `SimulationAuthorizationError` 映射到该已注册错误码（QA 已断言错误码常量存在且精确，防漂移）。

## RELEASE_CONTENT_VERDICT: PASS

允许 Mainline Lead 合入：对象 = `9cc4e87` + 本 QA tip（被测组合；15 项独立电池成为永久回归）。合并前实时复读 remote main（须仍 `3ed23b9`）与两个 ref。
