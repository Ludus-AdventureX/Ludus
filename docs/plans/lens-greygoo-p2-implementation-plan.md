# Ludus × Grey-Goo P2 实现方案（原则⑭⑮ 与深度管线升级）

> 状态：**方案记录（未实施）**。P0（审查闭环重试）与 P1（E 页成熟化）已在
> `codex/lens-behavior-closed-loop` 实施；本文件记录后续更大工程的实现路径，
> 供单独排期时逐项执行。参照 Grey-Goo 方法论 v5.1（探讨/skills/research/
> framework-selector/references/grey-goo-methodology-v5.1.md）原则⑭⑮ 与
> v6-analysis-agent（§3 检索纪律 / §8 Self-Anchor / §12 交叉阅读 / §13 逻辑抽查）。

---

## 总览

| 项 | 机制 | Grey-Goo 来源 | 现状 | 工作量 |
|---|---|---|---|---|
| P2-1 | 透镜中期交叉阅读（Agent 交叉验证） | 原则⑭ / v6-analysis-agent §12 | ❌ 透镜互不阅读 | M |
| P2-2 | 复杂度自适应降级 | 原则⑮ / framework-selector v6.2 | ❌ 无中途降级 | M |
| P2-3 | 多轮迭代（Think-First/Search-Later） | v6-analysis-agent §7 | ❌ 单轮串行 | L |
| P2-4 | Self-Anchor 自锚定验证 | v6-analysis-agent §8 | ❌ 无 | S |
| P2-5 | 逻辑抽查回应协议 | v6-analysis-agent §13 | ❌ 无 | S |
| P2-6 | 检索纪律与检索覆盖索引 | v6-analysis-agent §3 | ❌ 无纪律约束 | M |
| P2-7 | TDD 丢弃记录持久化（E 页） | 原则⑩ / quality-gate ㉑ | ❌ 漏斗 audit 仅内存 | M |
| P2-8 | 叙事回音预防（偏离度评分） | framework-selector v6.12.8 | ⚠️ 有 critic 无评分 | L |
| P2-9 | 安全锚降级前置检查 | framework-selector v6.9.5 | ⚠️ 有锚无门 | S |

**共同前置约束（AGENTS.md 第 1/13 节）**：P2 各项凡是触碰 schema、API、事件或
错误码的，MUST 先写 CCR 文档 → 获批 → 官方 `scripts/generate_contracts.ps1`
重新生成 → `-Check` 通过，才允许改代码。涉及领域文档（04/06/10/17/23/26）的
同步在各自小节标注。

---

## P2-1 透镜中期交叉阅读（原则⑭）

**目标**：五个透镜在执行顺序中，后续透镜阅读已完成透镜的中期发现，再深化自身
结论；批注入库供 synthesis 追溯。对齐原则⑭ "每个 Agent 知道自己不知道什么"。

### 数据流设计

```
porter（ANALYZING 阶段）──产出 lens artifact（draft）
  │
  ▼
counterparty（CRITICIZING 阶段）── 读取 porter 的 content 摘要
  │                              （只读，不修改；批注写入自身 references）
  ▼
pre_mortem ── 读取 counterparty + porter
  │
  ▼
scenario / meadows（SYNTHESIZING 阶段）── 读取前三件
```

### 实现步骤

1. **读取源**：`_execute_dedicated_lens` 构造 `LensRequest` 时，从 DB 读取同
   run 已 ready/draft 的透镜 artifact（`StrategicLensArtifact` 表，
   `lens_artifact_reads.py` 的查询可复用），把 `content` 的**压缩摘要**
   （≤800 字符/件，截断规则：headline + 前 3 条 keyFinding）拼入
   `LensRequest` 新字段 `upstreamLensDigests: list[dict]`。
2. **契约面**：`LensRequest` 是内部类型（app/agents/lenses.py），非 wire 合同
   ——扩字段无需 CCR；但 method-pack 的 prompt（`ways/hardtech-market-direction/
   1.1.0`）需要声明"你必须先阅读 upstreamLensDigests 再作答"——**method-pack
   变更必须升 SemVer 后重新安装**（AGENTS.md 第 6 节），属 P2-1 的显式前置。
3. **批注持久化**：透镜 artifact 的 `references` 已有 frozen 引用字段，追加
   `upstreamLensArtifactIds: string[]`（新引用类型）→ **触碰契约，需 CCR**；
   或降级方案：批注只进入 lens content 的 `content.crossReadNotes`（模型可写
   字段，不新增顶层契约）——推荐先走降级方案，CCR 版本作为后续增强。
4. **审计**：validating 阶段 `audit_full_run_lens_set` 增加弱检查（P2-1 不阻断，
   仅记录"未交叉阅读"为 findings 中的 note；强检查等 P2-3 多轮迭代落地后加）。

### 验收断言

- 同一 run 中，`scenario_planning` artifact 的 `content.crossReadNotes` 非空
  且引用了 ≥1 个上游透镜的发现（fixture 模式下 stub 直接注入）。
- 透镜行为门新增校验：`crossReadNotes` 若存在必须引用已存在 artifact id
  （沿用 `LensReferenceResolutionError` 语义）。

---

## P2-2 复杂度自适应降级（原则⑮）

**目标**：第 1 轮后复杂度重评，收敛且高置信时提议降级；安全锚发现共享盲区时
阻止降级（v6.9.5 约束）。

### 实现步骤

1. **判定输入**（全部已有）：
   - 收敛度：五个透镜 `validate_behavior` 均通过 + `_deterministic_gate` 的
     `dims` 值（evidence/adversarial/consistency ≥0.8）；
   - 置信度：`qualityGatePassed=true`（模型 validator）；
   - 安全锚：CRITICIZING 子阶段的 `safety_anchor` digest 中 `keyFindings` 的
     "共享未检验假设"数量 ≥2 → 阻止降级。
2. **状态机**：`AnalysisRun` 新增可选降级字段（如 `complexity_downgraded:
   bool` + `downgrade_chain: jsonb`）→ **schema 变更，需 CCR + migration**。
   降级方向：full→focused（跳过 synthesis 的 scenario/meadows 中一件？不——
   五件契约锁定。正确降级面是**预算与迭代数**而非透镜数：降级后跳过 P2-3 的
   第 3 轮与 P2-1 交叉阅读，透镜仍五件齐）。
3. **降级点**：CRITICIZING 完成、SYNTHESIZING 开始前（对齐 Gray 第 1 轮后）。
   降级事件：`analysis.stage.progressed` payload 增加 `downgrade` 标记
   （事件 payload 是自由 JSON，不触合同；但**事件类型不新增**）。
4. **报告标注**：`report_builder` 在"研究局限"节显式输出降级链与原因。

### 验收断言

- fixture 全收敛 run → 触发降级记录；含 ≥2 共享盲区的 run → 不降级；
- 降级后五件透镜仍齐（五件契约不被破坏）；
- `blocked/ready` 终态语义不变。

---

## P2-3 多轮迭代（Think-First / Search-Later）

**目标**：研究/批判角色从单次调用升级为 2-3 轮（第 1 轮纯推理 → 识别知识缺口
→ 检索 → TDD 纳入 → 第 2/3 轮深化），对齐 v6-analysis-agent §7。

### 实现步骤

1. **执行器改造**：`RoleExecutors` 的 research/critic executor 内部增加
   round 循环（worker 不变，只改 prompt 组装层）。每轮产出追加
   `roundProgression` 到 stage output（第 1 轮 knowledgeGaps[]、第 2 轮
   incorporatedFindings[]）。
2. **预算**：复用 charter `budget.max_model_calls`（已有），round 数
   = focused 2 / full 3（对齐 Gray 标准/深度档）。
3. **知识缺口→检索闭环**：第 1 轮 gaps 作为 `search_web` 二次查询条件
   （P2-6 检索纪律落地后改为查询 `_search_index`）；检索结果经
   `apply_evidence_funnel` 同管（复用，零新代码）。
4. **阶段产物**：round 轨迹写入 `stage_results[stage]["rounds"]`（已有 jsonb
   容器，扩 key 不触 schema 合同；但 06-data-model 的 Run stage 文档需同步）。
5. **质量门联动**：`_deterministic_gate` 的 consistency 维增加"第 2 轮后仍有
   未解决矛盾 → 0.7 系数"（对齐 Gray ㉒ 跨 Agent 逻辑自洽）。

### 验收断言

- fixture 模式：round 计数写入 stage_results，`research.packet.completed`
  事件数随 round 增长；
- 第 1 轮纯推理无检索（断言 search_web 在第 1 轮未被调用——依赖 P2-6 的
  调用点收口）。

---

## P2-4 Self-Anchor 自锚定验证（v6-analysis-agent §8）

**目标**：每轮推理后强制自检：引用已入账证据条目 → 生成可检验推论 → 冲突则
降置信度。防内部逻辑漂移的最小前置机制。

### 实现步骤

1. **prompt 追加**：`_STAGE_ASKS` 的 researching/criticizing 段追加
   `selfAnchorVerification` 输出要求（引用 evidence ids + 检验结论
   `pass|uncertain|conflict`）。
2. **确定性校验**：`_sanitize_packet` 后新增 `_admit_self_anchor`——两条全
   conflict → 该 packet `claim_support_score` 上限 0.5（不整体丢弃，
   对齐 §8 "降两级"而非删证据）。纯 worker 内逻辑，零合同变更。
3. **可见性**：`research.packet.completed` 事件 payload 追加
   `selfAnchorPassed`（事件 payload 自由 JSON，不触合同）。

### 验收断言

- 全 conflict 的 packet 分数被压到 ≤0.5；`selfAnchorPassed` 进入事件。

---

## P2-5 逻辑抽查回应协议（v6-analysis-agent §13）

**目标**：第 1 轮后 worker 对 research/critic 输出的推理链做**浅层**抽查
（循环论证 / 预设偷换 / 与已入账事实矛盾），发现问题则追加一轮带修正提示的
修正（不是新 stage）。

### 实现步骤

1. **确定性检查器**：`_logic_spot_check(output)` 纯函数：
   - 循环论证：conclusion 与 premise 的 token 重叠率 >80%（启发式）；
   - 预设偷换：packet.factor 与 conclusion 主语不一致（命名实体近似）；
   - 事实矛盾：conclusion 与已入账 packet 的 conclusion 语义冲突
     （fixture 模式用 stub 断言，live 用 LLM 二次调用标注 "uncertain"）。
2. **修正轮**：命中 → 追加一次 executor 调用（复用 roleOverride 机制，
   `_ROLE_ASKS` 增加 `logic_repair` ask），输出替代 packet；原 packet 保留
   在 discarded_claims（已有字段，零变更）。
3. **质量门**：consistency 维对"抽查命中但未修正"的 run 乘 0.7。

### 验收断言

- 构造循环论证 fixture → 修正轮被触发且最终 packet 替换；
- 修正后原 packet 出现在 `discarded_claims`。

---

## P2-6 检索纪律与检索覆盖索引（v6-analysis-agent §3）

**目标**：检索集中化 + 覆盖索引冻结 + 默认不重复检索，避免多角色冗余搜索
（Gray 实测 90 次搜索超时教训）。

### 实现步骤

1. **索引表**：新增 `retrieval_coverage` 表（workspace/run/关键词/时间/摘要/
   结果哈希）→ **schema 变更，需 CCR + migration**；对应领域文档
   `06-data-model.md` 证据链节同步。
2. **写入点**：`search_web` 调用统一收口到 worker 的 `_retrieve_once`（当前
   RETRIEVING 阶段 + P2-3 的 round 检索都经它），每次调用先查索引、命中即
   复用（幂等），新检索写入索引。
3. **搜索上限**：focused ≤3 / full ≤5（charter budget 已有 max_model_calls，
   叠加此硬上限，超限则降级该 packet 置信度——对齐 §3 惩罚语义）。
4. **E 页展示**（P1 延续）：`retrieval_coverage` 的只读查询挂到 evidence
   read 路由（**新路由，需 CCR**），E 页"检索覆盖"分区渲染。

### 验收断言

- 相同关键词二次检索零新请求（fixture 计数断言）；
- 超上限后 packet 置信度被压制且有日志。

---

## P2-7 TDD 丢弃记录持久化（E 页补完）

**目标**：把 `apply_evidence_funnel` 的 audit（discards/warnings/opposingIds）
从运行时内存变成可查询数据，E 页"被过滤的事实"分区才能渲染（P1 因数据不
持久化未做）。

### 实现步骤

1. **持久化载体**（三选一，需 CCR 决策）：
   - (a) 新增 `evidence_funnel_audits` 表（run 级 1:N，含 discarded 明细）——
     最完整，查询友好；
   - (b) `AnalysisRun` 增加 `evidence_funnel_audit: jsonb` 列——最轻，
     但 run 级单份、历史轮次覆盖；
   - (c) 复用 `AnalysisEvent` 新增 `evidence.funnel.audited` 事件类型——
     事件 append-only，天然审计友好，但查询要扫事件表。
   **推荐 (a)**：E 页按 run 读取 + 与 EvidenceItem 表 join 展示"丢弃→存活"
   因果。
2. **写入点**：worker RETRIEVING 阶段 `apply_evidence_funnel` 返回后立即
   （当前只合并进 stage_output）。
3. **E 页**：`list_run_evidence` 路由响应增加 `funnelAudit`（**API 变更，
   需 CCR + 合同重生成**）；前端复用 P1 的 `EvidenceSetWarnings` 模式渲染
   "被过滤的事实"分区（factor/reason/check 三列）。
4. **QA 联动**：`_deterministic_gate` 的 evidence 维已消费低质/反方警告
   （现有），丢弃记录持久化后无需改公式。

### 验收断言

- 有丢弃的 run → E 页显示完整丢弃明细（factor/reason/check）；
- 零丢弃 run → 显示"本轮无事实被过滤"诚实空态。

---

## P2-8 叙事回音预防（framework-selector v6.12.8）

**目标**：派发前五项检查（视角对称 / 假设压力测试 / 检察官强制 / 失败信号 /
资本市场信号）+ 收敛偏离度评分，<4 分触发重新派发。

### 实现步骤

1. **五项检查**：charter 确认后、执行前，worker 用确定性规则预检
   （prompt 文本是否含"我们/我们的"统一视角、是否有反对角色、历史失败案例
   是否作为强制分析目标）——纯配置/文本检查，零合同变更；结果写入
   `planning` stage output 的 `echoChecklist`。
2. **偏离度评分**：analyzing 完成后，对 research/critic 输出做嵌入近似
   （fixture 模式用关键词重叠，live 模式一次模型调用打分 0-10）。
   - ≥8 独立；4-6 中度回音 → 安全锚必须推荐 prompt 重写；<4 → 重新派发
     （新增检察官 executor 调用，复用 roleOverride）。
3. **阻断语义**：重新派发不改变 run 状态机（仍 analyzing），只是额外一轮
   executor 调用——**不触状态枚举，无 CCR**；但 23 号文档多智能体容量节
   需同步。

### 验收断言

- 构造"全员支持"fixture → 偏离度低 → 检察官重派发生且最终 report 出现
  反对论证；
- 数学收敛（可独立推导的定量结论）不被误判为回音（§6 判别规则落测试）。

---

## P2-9 安全锚降级前置检查（framework-selector v6.9.5）

**目标**：P2-2 降级提议前，若安全锚已标记共享盲区（≥2 Agent 共有的
collective_blind_spots），阻止降级——收敛可能是伪收敛。

### 实现步骤

1. **读取**：CRITICIZING 子阶段 `safety_anchor` digest 的 keyFindings 数量
   （现有 `_enrich_role` 已持久化到 stage_outputs["safety_anchor"]）。
2. **接线**：P2-2 的降级判定函数增加前置：`anchor_shared_blind_spots >= 2`
   → `downgrade_blocked=true`，降级事件 payload 标注
   `blockedBy: "safety_anchor_shared_blind_spots"`。
3. **报告**：研究局限节输出"降级被阻止：安全锚发现共享盲区"。

### 验收断言

- 含 ≥2 共享盲区 fixture → 降级被阻止且事件标注原因。

---

## 排期建议与依赖

```
阶段 A（S+M，可与 P0/P1 同分支继续）：
  P2-4 Self-Anchor ── 纯 worker 内，无 CCR，最快见效
  P2-5 逻辑抽查 ──── 纯 worker 内，无 CCR
  P2-9 安全锚前置 ── 依赖 P2-2 判定函数，可先单独落地判定器

阶段 B（M，需一次 CCR 波次）：
  P2-2 复杂度自适应 ── 需 migration（降级字段）
  P2-6 检索纪律 ──── 需 migration（retrieval_coverage）
  P2-7 TDD 丢弃持久化 ── 需 migration + API 变更 + 合同重生成

阶段 C（L，独立排期，依赖 A+B）：
  P2-1 交叉阅读 ──── 依赖 method-pack 升版 + 可选 CCR
  P2-3 多轮迭代 ──── 依赖 P2-6（检索收口）与 P2-5（抽查修正）
  P2-8 叙事回音 ──── 独立，但建议在 P2-3 后（需要多轮产物评分）
```

**每项完成定义**（AGENTS.md 第 16 节）：后端 pytest 零回归（一次性 PG16
容器）、前端 vitest/build 零错误、合同 `-Check` = CONTRACT_DRIFT_OK
（触合同项）、handoff 落 `docs/handoffs/`、QA 电池随候选提交。

---

## 附：与现有约束的边界声明

- 本方案不改变：AnalysisRun 状态枚举、五件透镜契约、fail-closed 审计、
  跨租户 404 语义、Charter 不可变、质量门乘法公式（仅增维度系数）。
- 本方案不引入：新依赖（AGENTS.md 第 3 节零新增纪律）、新 Worker 角色
  （P2-8 检察官复用 critic executor 的 roleOverride）、新状态机。
- 领域文档同步清单：04（决策方法论）、06（数据模型：P2-2/6/7 表与列）、
  10（API：P2-7 路由变更）、17（产品设计 v2：E 页成熟化）、23（多智能体
  容量：P2-3/8 调用数变化）、26（Agent Engine 契约：P2-1 交叉阅读输入）。
