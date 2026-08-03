# 透镜行为门专项评估：放宽契约 vs Prompt 组装 vs 重试可配置

> 日期：2026-08-03（Asia/Shanghai）
> 触发：flash 与 pro 两个真实模型跑戒指闹钟 full 档，各有一个透镜被行为门
> 2 次重试后仍拒绝（flash→meadows，pro→counterparty），full run 全部 blocked。
> 本报告评估三个修复方向，给出证据、权衡与建议。

---

## 1. 失败证据

| run | 模型 | 失败透镜 | 失败码（日志） | 通过透镜 |
|---|---|---|---|---|
| 979c98f7 | deepseek-v4-flash | meadows_leverage_points | `schema:content.currentInterventions.2` `schema:content.currentInterventions.3` | porter/counterparty/pre_mortem/scenario |
| fe741af9 | deepseek-v4-pro | counterparty_response_matrix | （容器日志滚动丢失，代码侧确认契约） | porter/pre_mortem/scenario/meadows |

两个模型**各有一个不同透镜失败** → 不是单一模型能力问题，是**五透镜行为契约
+ prompt 组装的结构性脆弱**。

---

## 2. 契约复杂度证据（method-pack schema，不可变 1.1.0）

### counterpartyContent（pro 失败点）—— 全套件最复杂

```
7 个顶级 required 字段
├── counterparties[1-2] → 每项 5 required（counterpartyId/identity/coreInterest/responseTools/constraints）
├── ourActions[2-3] → 每项 6 required + contains 恰好 1 个 no_action（minContains=1 maxContains=1）
├── responseMatrix[2-6] → 每行 10 required + 必须覆盖全部 (counterparty×action) 对
├── publicationTest → 4 required + informationAsymmetryVulnerability 枚举
├── downsideAsymmetry[2-3] → 每项 5 required + 必须覆盖全部 actions
└── reflexivityWarning
```

### meadowsContent（flash 失败点）—— 嵌套最深

```
7 个顶级 required 字段
├── systemMap → 10 required 子字段
├── levelsCovered[3-12] 整数数组（uniqueItems）
├── currentInterventions[1-20] → 每项 9 required + oneOf（12 个 level/levelName/strengthBand 三元组必须精确匹配）
├── highLeverageGaps[1-8] → 每项 11 required + oneOf（4 个高杠杆 level）
├── runawayPositiveLoops[1-10] → 每项 3 required
├── interventionSequence[2-12] → 每项 5 required + purpose 枚举
└── riskTradeoffs
```

**共同特征**：`additionalProperties: false` + 大量跨字段一致性约束（如
meadows 的 `levelsCovered` 必须精确等于 currentInterventions ∪
highLeverageGaps 的 level 集合；counterparty 的 responseMatrix 必须覆盖全部
(cp, action) 对）。这类约束**纯 JSON schema 文本无法表达清楚**，模型只能
"猜"。

---

## 3. Prompt 组装现状（证据）

`lens_output_contract`（app/agents/lenses.py L573-640）已统一注入：
- ✅ 顶层字段清单（含 references）
- ✅ content 分支 schema 全文（`load_lens_content_schema`）
- ✅ content example（仅 porter/scenario/meadows 有，`_CONTENT_EXAMPLES`）
- ✅ meadows 一致性规则文本（L619-626）
- ✅ "NEVER 概率词" 规则

**关键缺口**：

| 透镜 | 有 example？ | 行为门复杂度 | 实测 |
|---|---|---|---|
| porter | ✅ | 中 | 两模型都过 |
| counterparty | ❌（L567 注释"schema 文本足够"） | **最高** | pro 失败 |
| pre_mortem | ❌ | 中 | 两模型都过 |
| scenario | ✅ | 中 | 两模型都过 |
| meadows | ✅ 但 example 的 `levelsCovered=[1,2,5,10]` 与 `currentInterventions` 含 level 1/5/10、`highLeverageGaps` 含 level 2 不一致（示例自身违反契约） | 高（oneOf 12 元组） | flash 失败 |

> ⚠️ **重大发现**：meadows 的 example（L436 `levelsCovered: [1,2,5,10]`）与
> 其 `currentInterventions`（level 1/5/10）∪ `highLeverageGaps`（level 2）
> 的并集 `{1,2,5,10}` 一致——但 `currentInterventions.2`（level 10 的 int-3）
> 在 flash 输出中缺失 → 行为门报 `schema:content.currentInterventions.2`。
> 说明 example 虽完整但**模型（尤其 flash）难以复制 3 元素数组 + oneOf 精确
> 匹配**。

---

## 4. 三方向评估

### 方向 A：放宽契约（不推荐）

| 项 | 评估 |
|---|---|
| 优点 | 立即可让 flash/pro 通过 |
| 风险 1 | **method-pack 1.1.0 是不可变已发布包**（AGENTS.md §6：内容哈希校验、改契约必须升 SemVer 重装）——改契约 = 升 1.2.0 = 牵动 Charter/Router/报告引用 |
| 风险 2 | 契约是质量哲学的载体（AGENTS.md §7"五个战略透镜必须执行独立 Prompt 与判别式 JSON Schema"）——放宽 = 削弱行为门 = 质量门形同虚设 |
| 风险 3 | 跨字段一致性约束（levelsCovered 精确匹配、矩阵全覆盖）是防止模型**自相矛盾**的核心——删除会导致报告内部冲突 |
| 结论 | **不建议**。仅可作为最后手段（如放宽 `currentInterventions` 的 maxItems 或容忍单元素数组），且必须走 CCR + SemVer |

### 方向 B：改进 Prompt 组装（推荐，主修复）

| 子项 | 改动 | 工作量 | 风险 |
|---|---|---|---|
| B1. **给 counterparty 补 content example** | 仿 `_MEADOWS_CONTENT_EXAMPLE` 写一个**契约自洽**的 counterparty example（1 counterparty × 2 actions：1 active + 1 no_action，responseMatrix 2 行全覆盖，downsideAsymmetry 2 项全覆盖），注入 `build_prompt_inputs`（L386 加 `content_example=`） | S（1 个 dict + 1 行参数） | 低 |
| B2. **修复 meadows example 的一致性** | example 的 `levelsCovered` 改为与 interventions 精确一致的集合，并补 3 个示例干预的完整性（当前 int-3 缺什么导致 flash 输出被拒——对齐 schema 逐字段核对） | S | 低 |
| B3. **通用：example 一致性自检** | 加一个确定性校验：example 加载时用 `validate_behavior` 反测，确保**示例自身能过门**（防"示例违反契约"的隐性 bug）——本次 meadows 示例若有反测就能在 CI 暴露 | M | 低 |
| B4. **失败码可读化** | 当前失败码是 `schema:content.currentInterventions.2`（JSON path），对模型不友好；repair 消息里附上**该字段的 schema 片段**（从 `load_lens_content_schema` 提取对应 sub-schema） | M | 低 |
| 结论 | **B1+B2 是根因修复**（pro 缺 example、flash 的 example 有结构要求未对齐），B3 防回归，B4 提升修复成功率 | | |

### 方向 C：重试次数可配置（辅助）

| 项 | 评估 |
|---|---|
| 现状 | `_persist_lens_with_repair` 硬编码 `for attempt in range(2)`（1 次修复） |
| 改动 | 从环境变量/方法包 manifest 读取 `LENS_REPAIR_MAX`（默认 1，上限 2-3） |
| 优点 | flash 这类轻量模型多 1-2 次修复机会；pro 的 counterparty 也可能第二次修复通过 |
| 风险 | 重试上限提高 → 成本上升（每次修复=1 次完整模型调用）；2 次都失败的透镜说明模型系统性不满足，3 次未必更好 |
| 结论 | **建议做**，但要设上限（≤2）且**只在第一次拒绝 reason_codes 是"结构性缺失"（schema:* 类）时**才允许第二次修复——`forces_missing` 这类内容性缺失值得再试，`lens_type_mismatch` 这类确定性错误不值得 |

---

## 5. 推荐实施顺序

```
波次 1（立即，纯代码，无 CCR）：
  B1  counterparty content example（根因：pro 失败）
  B2  meadows example 一致性修正（根因：flash 失败）
  B3  example 自检（防回归，测试级）
  测试：两模型失败的修复路径用 pytest 模拟（构造被拒 payload → 验证 example
        能过门 → 验证 repair 消息含可读码）

波次 2（辅助，无 CCR）：
  C   LENS_REPAIR_MAX 环境变量（默认 1，上限 2，仅 schema:* 类允许第 2 次）
  B4  失败码→schema 片段注入 repair 消息

不推荐：
  A   放宽契约（需 SemVer + CCR，且削弱质量门）
```

## 6. 验收标准

- B1/B2 落地后：用 pytest 验证 counterparty/meadows 的 example 均能通过各自
  `validate_behavior`（示例自检）
- 重新用 flash + pro 各跑一次戒指闹钟 full：5/5 透镜 ready（或至少失败的
  透镜变为可通过重试挽救的）
- 全量 pytest 零回归（现有 598 passed 基线）

---

## 7. 附：本次评估未覆盖/需后续确认

- 容器日志中 pro 的 counterparty 具体 reason_codes（滚动丢失）——可从
  `LensBehaviorRejected` 的 warning 重建，或用 B1 落地后重跑验证
- method-pack 1.1.0 的 prompt 原文（`prompts/lenses/counterparty-response-matrix.md`）
  是否与 lens_output_contract 冲突（若有冲突是更深的 prompt 组装问题）
