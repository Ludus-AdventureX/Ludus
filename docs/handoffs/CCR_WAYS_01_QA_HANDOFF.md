# CCR_WAYS_01_QA_HANDOFF — StrategicLensArtifact persistence + ConnectorStatus enum

- QA owner: qa_release; **QA branch/head**: `codex/qa-ccr-ways-01` (based on the candidate head; QA commit recorded below and pushed).
- **exact tested candidate**: `codex/ccr-ways-01-execution` @ **`e57e4747e34d4fcc787e9e44aaa4d8cd90d85a25`** (product-equivalent `06c58cf`; `06c58cf..e57e474` verified lifecycle-only on services/packages).
- **exact tested combination**: `e57e474` product tree (byte-identical) + QA commit on `codex/qa-ccr-ways-01` containing the exact-table assertion update (`test_models.py` adds `strategic_lens_artifacts`) and the new negative-regression suite `tests/test_strategic_lens_artifacts.py` (12 tests). No product/models/types/migration/agents/strategic_lenses/main file modified by QA.
- **Remote verification (QA's own live re-read)**: `refs/heads/main = 2c5e79c`, `refs/heads/codex/ccr-ways-01-execution = e57e474` — both exact. PASS.
- Environment: brand-new empty PG16 database `qa_ccr_ways01`, provisioned exclusively via Alembic.

## Verdicts

- **MIGRATION_VERDICT: PASS** — clean DB `upgrade head` → **`d7e2a91c5b48`**; `downgrade c4a1f0b2d9e7 → head → 0001 → head` all clean; `alembic check` "No new upgrade operations detected"; final current `d7e2a91c5b48 (head)`.
- **MODEL/MIGRATION PARITY: PASS** — `alembic check` (autogenerate diff over Base.metadata + rate_limit_metadata) clean covers columns/FK/enum; live `\d strategic_lens_artifacts` additionally confirms: JSONB reference columns (`payload/claim_refs/evidence_refs/assumption_refs` with jsonb defaults), both composite FKs (`workspace+case` → decision_cases, `workspace+case+run` → analysis_runs, CASCADE), both CHECKs (`content_hash <> ''`, `ready ⇒ validation_accepted_at IS NOT NULL`), the partial unique index `uq_..._ready_per_run_lens (workspace, run, lens_type) WHERE status='ready'`, and the enums `strategic_lens_artifact_status`/`lens_producer_role`/reused `strategic_lens_type`.
- **RELEASE_GATE_VERDICT: PASS** — P0=0, P1=0, P2=0 new. The previously known sole failure (exact-table assertion) is fixed by the QA-side update and green.
- **Mainline 合入许可: YES** — 允许 Mainline Lead 将 `e57e474` 与本 QA 提交（同一被测组合）合入 main；合并前照例实时复读 remote main（当前 `2c5e79c`）与候选 ref；若采用其他 QA commit 需重新复测。

## Negative regressions (all 12 requested items, run against the real migrated PostgreSQL)

1. 错误 Workspace 绑定 → 复合 FK 拒绝 ✅
2. 错误 Case 绑定（他 case 的 run + 伪造 case）→ 复合 FK 拒绝 ✅
3. 错误 AnalysisRun 绑定（他 case 的 run + 伪造 run）→ 复合 FK 拒绝 ✅
4. `status='ready'` 且 `validation_accepted_at IS NULL` → CHECK 拒绝；含正向孪生（ready+witness 接受）✅
5. 同 (workspace, run, lens_type) 第二条 ready → 部分唯一索引拒绝 ✅
6. 同组合多条 draft/rejected 审计历史保留（4 条并存实证）✅
7. `content_hash=''` → CHECK 拒绝 ✅
8. 非法 origin_mode → 拒绝（SQLAlchemy 枚举层 StatementError 先于 DB 拦截，测试同时容忍 DB 层 DBAPIError）✅
9. ConnectorStatus 精确七值集合断言（增/删/改名即红）✅
10. StrategicLensArtifactStatus 精确 draft/ready/rejected ✅
11. `lens_type` 列复用 canonical `strategic_lens_type` 枚举（列类型名 + 成员集合断言）✅
12. 无平行 ConnectorStatus 定义（app/ 全源扫描，唯一定义 = types.py）✅

## Full test counts (fresh, `-W error`, clean-migrated DB)

- `pytest tests app/simulations/tests`: **199 passed, 0 failed, 0 skipped** — 包含 test_models（更新后的 exact-table 断言）、decision_os_invariants、Auth/Workspace/CSRF/Rate-Limiting、Simulation（验收 + owner 28）、Agent Runtime（19）、release-gate、以及新增 12 项 lens-artifact 负面回归。计数自洽：Ways 候选的 292 − lens_lanes 105（该套件在本候选分支上不存在，属五 Lens 集成候选）+ 12 = 199。
- Ruff（app+tests+migrations）PASS；compileall exit 0。
- Contract drift: `OPENAPI_SEMANTIC_DRIFT_OK`（canonical builder vs committed；本候选未触碰 packages/contracts，API shape 无变化）。官方 `generate_contracts.ps1 -Check` 的 TS 全链在本 worktree 不可运行（无 node_modules，历轮同一限制），比较语义已等效复现；types.gen.ts 未被候选触碰。
- Scope/secret/`git diff --check` over `2c5e79c..e57e474`: 全部干净；changed set 精确为 models.py/types.py/migration/CCR 文档/18-plan(write-scope repair)/lifecycle —— contract_lead scope 内。

## Findings register

- P0: 0. P1: 0. P2: 0 new.
- 备注：五 Lens 集成候选（69bbc5d，已 QA PASS）与本候选在文件上零交叠（strategic_lenses/** vs models/types/migration），Mainline Lead 可按任意先后合并，但两者都合入后建议 QA 做一次合并后冒烟（persistence 接线分支开工前的基线确认）。
