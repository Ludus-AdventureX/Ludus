# READ_PATH_R2_QA_HANDOFF — StrategicLensArtifact read-only consumption path

- QA owner: qa_release; **QA branch/head**: `codex/qa-lens-artifact-read-path-r2`（全新分支，未复用旧 QA 分支；QA commit 见 git log，推送后实时回读）。
- **exact_tested_head**: `codex/task-lens-artifact-read-path` @ **`2f0fe40e11e82bfe1f639e105fd3892a453d3756`** — 独立干净 worktree，产品树逐字节；被测组合 = 候选产品树 + 本 QA 提交（24 项 probe 转正的 `tests/test_lens_artifact_read_path.py`，11 个正式测试）。QA 未改任何产品文件。
- **remote verification（硬门）**：QA Lane 第一条命令 `ls-remote main` = `4de362835f728ab155fc197b9f11b9ac248f2936` ✔ 精确；candidate ref = `2f0fe40e...` ✔ 精确。无 BASELINE_STALE / REMOTE_SYNC_BLOCKED。QA 分支推送后实时回读见文末。

## Verdicts

- **canonical ordering verdict: PASS** — 实测乱序插入五 lens 后按 **porter → counterparty → pre_mortem → scenario → meadows** 精确返回（本轮修正确认）；counterparty 严格早于 pre_mortem 有独立断言；`created_at` 为第一 tie-breaker、`strategic_lens_artifact_id` 为最终稳定 tie-breaker（同时刻双行实证）。
- **404/403 anti-enumeration verdict: PASS** — foreign case/run anchor、ghost anchor、跨 case 混合锚点、外部 artifact id + 本地锚点：**全部返回同一 `CASE_NOT_FOUND` 404 签名**（code+message+status 集合大小 = 1）；无 review capability 的调用者对 foreign/ghost 锚点得到的**是 404 而非 403**（anchor 404 先于 capability 403，无法用 403/404 差异探测外部资源）。
- **capability verdict: PASS** — audit 读取仅 `review` capability 可见 draft/rejected：owner（角色投影全集）✔、显式 review member ✔、仅 contribute member → `MEMBERSHIP_CAPABILITY_REQUIRED` 403，details 精确 `{"requiredCapability": "review"}`，符合既有 capability 合同。
- **ready-only 消费: PASS** — 消费列表仅 ready；draft/rejected/不存在的单项 get **错误签名完全一致**；lens_type 过滤精确；workspace/case/run 三层范围正确（跨 case 不串）。
- **投影安全: PASS** — `LensArtifactView` frozen dataclass（setattr 抛 FrozenInstanceError）；payload 深拷贝（消费方改写嵌套 dict 后重取 ORM 数据不变）；四个 refs/origin_modes 均为 tuple 不可变；纯进程内投影，模块零 APIRouter/BaseModel/HTTP DTO（源扫描证实）。
- **scope: PASS** — changed set 仅 lifecycle + `app/analyses/lens_artifact_reads.py`（case_api_data scope）；零 models/migrations/contracts/strategic_lenses/persistence/router 改动。
- **RELEASE_CONTENT_VERDICT: PASS** — P0=0, P1=0, P2=0 new。

## 实际测试计数（fresh，`-W error`，全新纯迁移库 `qa_read_path_r2`）

- 干净库：`upgrade head` → `d7e2a91c5b48`；`alembic check` 干净
- read-path 定向：**11 passed**（24 项 probe 全部覆盖转正，落点 `services/api/tests/test_lens_artifact_read_path.py`，qa_release 所有）
- 全量：`pytest tests app/simulations/tests` = **315 passed, 0 failed, 0 skipped**（= 304 基线 + 11 新增，自洽）
- `pytest tests/lens_lanes` = **105 passed**
- Ruff PASS；compileall exit 0；`git diff --check`/secret scan/冲突标记扫描全干净

## Findings

- P0: 0. P1: 0. P2: 0 new.

## 移交 Mainline Lead

内容放行：合入对象 = `2f0fe40` + 本 QA 分支 tip（被测组合）。合并前实时复读 remote main（须仍 `4de3628`）与两个 ref；HTTP 暴露仍属 Contract Lead 后续 CCR（本候选如实未含 endpoint）。
