# Sources And Compilation Notes

版本以各源文件 frontmatter 的 `version` 为准。

本文件记录实际编译或直接影响当前方法合同的来源与版本。31 个研究 Skill 的全量处置、未加载原因、平台吸收位置和后续方法包规划见 `CAPABILITY-MAP.md`；不得仅根据本表行数推断其他 Skill 被遗漏。

| Source | Version | Repository path | Compiled contribution |
|---|---:|---|---|
| framework-selector | 6.12.7 | `探讨/skills/research/framework-selector/SKILL.md` | 适用边界、前置诊断、先想后搜、失败恢复、质量闭环 |
| full-mode-composer | 5.6.2 | `探讨/skills/research/full-mode-composer/SKILL.md` | 管道完整性、结构化报告收束、交付前终检 |
| v6-rag-pool | 2.0.0 | `探讨/skills/research/v6-rag-pool/SKILL.md` | 检索任务上限、来源分级、重试/降级、去重 |
| v6-analysis-agent | 1.3.1 | `探讨/skills/research/v6-analysis-agent/SKILL.md` | 因素研究包、TDD 证据纳入、轮次与缺口纪律 |
| v6-safety-anchor | 1.3.0 | `探讨/skills/research/v6-safety-anchor/SKILL.md` | 集体盲区、假设翻转、伪收敛、叙事回音 |
| v6-strategy-synthesis | 1.2.1 | `探讨/skills/research/v6-strategy-synthesis/SKILL.md` | 跨因素收敛/分歧、支撑强度、综合修复 |
| v6-chief-of-staff | 1.2.0 | `探讨/skills/research/v6-chief-of-staff/SKILL.md` | 条件化行动、路径、风险响应、领先指标 |
| v6-devils-advocate | 1.1.0 | `探讨/skills/research/v6-devils-advocate/SKILL.md` | 最强反方、失败模式、利益相关方阻力、致命缺陷 |
| v6-pipeline-coordinator | 1.0.0 | `探讨/skills/research/v6-pipeline-coordinator/SKILL.md` | 阶段前置校验、预算/恢复、结构化升级点 |
| analysis-quality-gate | 2.4.1 | `探讨/skills/research/analysis-quality-gate/SKILL.md` | 信息充分性、反方、逻辑、自洽与乘法交付门 |
| business-diagnosis-ten-questions | 1.3.0 | `探讨/skills/research/business-diagnosis-ten-questions/SKILL.md` | 商业基线与已合并的需求真实性第 11-16 问 |
| deliverable-standards | 1.3.0 | `探讨/skills/research/deliverable-standards/SKILL.md` | 结论先行、可行动建议、局限与来源可追溯 |
| pre-mortem | 1.0.0 | `探讨/skills/research/pre-mortem/SKILL.md` | 既成失败视角、三类原因、Top 3 防范/应急/检测与 verdict |
| scenario-planning | 1.0.0 | `探讨/skills/research/scenario-planning/SKILL.md` | 结构性情景、早期信号、策略韧性与 killed 测试 |
| porter-five-forces | 1.0.0 | `探讨/skills/research/porter-five-forces/SKILL.md` | 分市场边界、五力证据、趋势及监管/互补品校正 |
| counterparty-response-matrix | 1.0.0 | `探讨/skills/research/counterparty-response-matrix/SKILL.md` | 一层回应、no-action 基线、反制、公开发布与反身性测试 |
| meadows-leverage-points | 1.0.0 | `探讨/skills/research/meadows-leverage-points/SKILL.md` | 系统映射、跨层杠杆、高杠杆空缺、失控回路与干预顺序 |

## 案例教训与校准来源

以下材料不作为运行时知识库或预置结论，只用于编译质量门、构造 eval 和记录方法为何存在：

| Source | Repository path | Compiled contribution |
|---|---|---|
| BrainCo 战略分析教训 | `探讨/lessons/2026-05-07_brainco-strategy-case-lessons.md` | 时间窗口对齐、来源偏见方向、证据标注与正文使用一致、国内直接竞品覆盖 |
| DeepSeek 战略分析教训 | `探讨/lessons/2026-05-08_deepseek-strategy-case-lessons.md` | 框架收敛不等于结论可靠、理论引用不等于因果深度、诚实边界优先 |
| GED 战略分析教训 | `探讨/lessons/2026-05-14_ged-strategy-case-lessons.md` | 决策视角和用户战略意图优先，阻力最小路径不自动等于正确路径 |
| BCI 三线平台战略 | `探讨/skills/research/framework-selector/references/bci-platform-strategy-scale-changes-nature.md` | “规模改变性质”、资源阶段翻转、多方向并行容量约束；形成 seed/angel 双轨 parity eval |
| 决策质量与结果质量 | `探讨/skills/research/analysis-quality-gate/references/decision-vs-outcome-quality.md` | 复盘时区分决策过程、执行、外部冲击和结果，避免结果论追责 |

案例中的企业名、用户信息、非公开数字和原始结论不会进入模型 Prompt。eval 只保留经去标识化的决策结构、资源约束和应观察的方法行为。

## 编译裁剪

- 原 A/B/C 映射为 Ludus `quick/focused/full`。quick 不执行正式方法；focused/full 使用同一四 Worker 契约，只在覆盖、预算和输出 schema 上不同。
- 原系统的多个分析 Agent、RAG Agent、Safety Anchor、Chief of Staff、Devil's Advocate 和 Coordinator 不再成为并行正式角色。Ludus 只暴露四类 Worker；Safety Anchor/魔鬼审查是 Critic 子步骤，行动建议由 Synthesis 产出，协调属于运行时状态机。
- 删除 Hermes/飞书聊天交互、`delegate_task`、临时目录、文件写入绕行和平台超时协议。保留的是结构化输入/输出、预算、失败修复和审计要求。
- 删除 LaTeX/PPTX 模板与直接编译要求。Ludus 先生成 canonical `StructuredReport`，再由平台从同一表示渲染 HTML/PDF。
- 将供应商/RAG 池细节替换为稳定只读工具名；Provider、缓存和 fixture 的选择属于运行时 Adapter。
- 不复制通用框架市场、文档类型选择器或跨行业方法组合器。本包只处理高切换成本硬科技市场方向。
- 没有采用独立 `demand-reality-check` 路径：该能力已经合并到 `business-diagnosis-ten-questions@1.3.0` 的第 11-16 问。
- 五个战略 lens 不是新增顶层 Worker，而是绑定 Research/Critic/Synthesis 固定阶段的 full 子协议；每种 lens 最多一次模型调用，focused 不调用。
- 源技能的自由文本模板被编译为 `StrategicLensOutput` 判别联合与 `LQ-*` 行为门。模型 stage output 与 canonical `StrategicLensArtifact` 严格分离：只有服务端能注入冻结上下文、身份、provenance、哈希、时间戳和 `ready` 状态。
- `StructuredReport` 不复制五份 lens 内容，只保存恰好五个 `lensArtifactIds`；内容通过独立 artifact 读取合同访问。
- 所有 31 个研究 Skill 均已在 `CAPABILITY-MAP.md` 中完成处置；只有与本方法适用边界直接相关且能通过 Schema、质量门和 eval 验收的能力进入当前 Run。

## 已知来源不一致

- `full-mode-composer` 的描述/正文提到 v5.6.3，但 frontmatter 为 `5.6.2`；本包按 frontmatter 记录 `5.6.2`。
- `v6-analysis-agent` 正文标题仍写 v1.3.0，但 frontmatter 为 `1.3.1`；本包记录 `1.3.1`。
- `v6-safety-anchor` 文件内含标为 v1.4.0 的后续小节，但 frontmatter 为 `1.3.0`；本包只声明 `1.3.0` 来源，不把小节标题当作已发布版本。
- `framework-selector@6.12.7` 内含面向下一版的局部标题；本包只采用与 6.12.7 主合同一致且能映射到 Ludus 的机制。

## 已知限制

- 当前阈值来自首个 P0 案例与源体系经验，尚未跨硬科技子行业校准。每次 eval 和真实 Run 应保留单维结果以便后续版本回溯。
- 本包不提供工程安全、法律、监管或财务专业签字；这些结论只能作为待验证约束。
- 沙盘种子是 `draft` 因果假设。正式图需要用户确认，推演结果不得称为成功概率。
- `ways` 当前状态为 `release_candidate`；发布编译器、运行时 Loader 与内容哈希回填由后续 `method-packs` 实现承担。
- 当前包包含 17 个声明 Skill 来源、5 类案例/校准来源、10 个 Prompt、9 个 Draft 2020-12 schema 和 5 个 eval。

## 2026-07-19 复审补充

- `探讨/skills/research/framework-selector/SKILL.md` 的 Cynefin 前置门被转换为 `cynefin-gate-result` 和 deterministic route contract；没有复制飞书、临时文件编排或凭证。
- `探讨/skills/research/v6-rag-pool/SKILL.md` 的来源纪律被转换为 `source-span` locator/quoteHash；不能由 snippet 代替。
- `v6-strategy-synthesis`、`v6-devils-advocate`、`analysis-quality-gate` 的可复用语义被转换为 Judgment/Dissent/DraftRecommendation 和 V1-V9 schemas。
- `.env`、`auth.json`、个人 memories、外部写工具和任意 MCP 仍明确禁止读取或打包。
