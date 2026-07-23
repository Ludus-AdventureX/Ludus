# Hardtech Market Direction 1.1.0 能力地图

本文记录 `探讨/skills/research` 全部 31 个 Skill 如何沉淀到 `hardtech-market-direction@1.1.0`。它解决两个不同问题：

1. **知识是否被处置和保留**：31 个 Skill 必须全部有版本、状态、目标位置和理由，不允许静默遗漏。
2. **能力是否在本方法运行时加载**：只有与“资源受限硬科技市场方向选择”直接相关且能被 Schema、质量门和 eval 验收的能力，才进入当前 full/focused Run。

“未加载”不等于“未沉淀”。后续方法、平台合同或禁用决定也是正式沉淀结果。运行时不得直接读取 `探讨/skills`；本文件只用于设计审计、版本评审和后续方法包规划。

## 沉淀状态定义

| 状态 | 含义 | 是否进入本包运行时 |
|---|---|---|
| P0 直接编译 | 核心步骤被转换为 manifest、Prompt、Schema、质量门或 eval | 是，按固定阶段加载 |
| 能力已被其他合同吸收 | 能力进入通用 system policy、数据模型、状态机、报告或 Review，不保留独立 Skill 身份 | 不作为独立 Skill 加载 |
| 延后到下一方法包 | 能力有效，但适用问题、分析单位或交付物与本方法不同 | 否，由未来 Router 选择其他 ways |
| 仅参考 | 只保留设计原则或供应商适配经验，不形成当前产品依赖 | 否 |
| 禁用 | 与安全、正式输出链或弃用状态冲突 | 否，并要求测试阻止进入主路径 |

## 31 个 Skill 全量映射

| Skill | 状态 | 沉淀目标 | 当前运行行为与验收 |
|---|---|---|---|
| `allison-three-models@1.0.0` | 延后到下一方法包 | 未来政府/组织决策 ways | 本方法 Router 不返回；不得把组织过程、官僚政治和理性行动三模型强塞进硬科技市场比较 |
| `analysis-quality-gate@2.4.1` | P0 直接编译 | `quality-gates.yaml`、Validation Prompt、`quality-gate-result` Schema | 四维乘法值只判交付资格；`AG-*` 阻断优先于分数，禁止解释为正确率或成功概率 |
| `analytical-lens@3.6.0` | 能力已被其他合同吸收 | 通用快速分析/system policy/`QuickAnalysisResult` | 追问、反向思考、事实/假设/判断分离用于 quick；不得因此创建正式 Run 或伪装为 full 方法执行 |
| `arxiv@1.0.0` | 仅参考 | Evidence Provider 的论文元数据、版本和发布日期意识 | P0 统一通过受控 `search_web/fetch_url`；不运行源脚本，不绕过 Evidence Gateway |
| `bp-writing@1.1.0` | 延后到下一方法包 | 未来融资叙事与 BP 交付 ways | 当前报告不生成融资 BP/PPTX，不把市场选择结论自动改写为融资故事 |
| `business-diagnosis-ten-questions@1.3.0` | P0 直接编译 | `diagnostic-questions.yaml` 的商业基线、需求真实性、采购和最小楔子 | route/full 阻断问题不可跳过；eval 必须覆盖真实行为、付款方、采购周期和最小切入点 |
| `counterfactual-comparison@1.0.2` | 延后到下一方法包 | 未来政策、平台规则或外力干预 ways | 当前只执行资源尺度反事实，不声称执行完整政策反事实框架 |
| `counterparty-response-matrix@1.0.0` | P0 直接编译 | Critic 强制 lens、`StrategicLensOutput` 判别分支、`LQ-COUNTERPARTY` | 1-2 个关键对手方、2-3 个含 no-action 的行动、三类回应、窗口、反制、公开发布、下行与反身性必须完整 |
| `deliverable-standards@1.3.0` | 能力已被其他合同吸收 | `focused-result`/`structured-report` Schema、HTML/PDF renderer | 结论先行、条件、行动、来源和局限成为结构字段；不加载 20 类文档模板或 LaTeX/PPTX 流程 |
| `document-type-selector@1.3.0` | 能力已被其他合同吸收 | quick/focused/full 输出授权合同 | 输出类型由分析等级和 Run 状态确定，不允许用户或模型在自由文档类型列表中绕过正式合同 |
| `framework-selector@6.12.7` | P0 直接编译 | manifest applicability/exclusions、Method Router、Charter 前置 | 先判断问题和材料是否适用，再研究；Router 只选择已发布方法包，不运行时拼装任意 Skill |
| `full-mode-composer@5.6.2` | P0 直接编译 | execution order、Synthesis/Validation 收束、full 完整性检查 | Research→五 lens/Critic→Synthesis→Validation 顺序固定；缺阶段产物不得继续或交付 |
| `hv-analysis@2.0.0` | 延后到下一方法包 | 未来横向/纵向深度研究 ways | 不成为当前四个 research track，也不把 LaTeX 交付结构带入本方法 |
| `iceberg-model@1.0.0` | 延后到下一方法包 | 未来系统根因诊断 ways | 当前 Meadows 可表达系统层级，但不得宣称已执行 Iceberg 的事件/模式/结构/心智模型完整协议 |
| `latex-to-pdf@1.3.0` | 禁用 | 无运行时目标；由 `StructuredReport -> HTML -> Playwright PDF` 替代 | P0 不安装或调用 Tectonic/LaTeX fallback；HTML 与 PDF 必须同源 |
| `meadows-leverage-points@1.0.0` | P0 直接编译 | Synthesis 强制 lens、系统图与沙盘 lever/feedback 映射、`LQ-MEADOWS` | 系统边界、存量/流量、增强/平衡回路、延迟、规则、至少三层杠杆、高杠杆缺口和干预顺序必须可审计 |
| `organization-diagnosis@1.0.0` | 延后到下一方法包 | 未来组织执行、组织变革或并购整合 ways | 当前只把团队和交付能力作为约束证据，不输出组织诊断结论 |
| `porter-five-forces@1.0.0` | P0 直接编译 | Research 强制 lens、`LQ-FIVEFORCES` | 对每个候选市场分别定义行业边界并执行五力；每力有证据和趋势，监管/互补品单独校正，分数不作为决策公式 |
| `post-mortem@1.0.0` | 能力已被其他合同吸收 | canonical `Review`、决策质量/执行/外部冲击/结果分离 | Run 本身不自动执行完整 Post-Mortem Skill；决定后的 Review 使用冻结证据、指标和实际结果复盘 |
| `pre-mortem@1.0.0` | P0 直接编译 | Critic 强制 lens、`LQ-PREMORTEM` | 假定失败已发生，覆盖 internal/external/systemic hindsight，至少五项原因和 Top 3 防范/应急/检测，并给出 verdict |
| `scenario-planning@1.0.0` | P0 直接编译 | Synthesis 强制 lens、ScenarioVersion 候选、`LQ-SCENARIO` | 使用两个高影响高不确定轴生成 3-4 个结构不同情景；必须包含 baseline、结构断裂、预警信号和至少一个 killed strategy |
| `slide-deck-generator@1.6.2` | 禁用 | 无 P0 目标 | 源 Skill 已弃用；不安装脚本、不生成 PPTX、不让幻灯片格式决定领域模型 |
| `structural-demographic-theory@1.0.0` | 延后到下一方法包 | 未来宏观政治稳定性/公共事务 ways | 当前方法不推导精英过剩、民众压力或国家财政压力等宏观结论 |
| `three-horizons@1.0.0` | 延后到下一方法包 | 未来创新组合、转型和长期路线 ways | 当前 Run 选择优先验证路径，不承担 H1/H2/H3 组合治理和长期迁移协议 |
| `v6-analysis-agent@1.3.1` | P0 直接编译 | Research Prompt、`research-packet` Schema、2-3 轮研究预算 | 每个研究轨有任务、证伪条件、证据引用、缺口和停止条件；不能创造无来源事实 |
| `v6-chief-of-staff@1.2.0` | 能力已被其他合同吸收 | Synthesis 的条件化建议、阶段路径、风险响应、领先指标和 Review 日期 | 不注册第五个正式 Worker；行动建议必须由 Synthesis 消费 Research/Critic/lens 后输出 |
| `v6-devils-advocate@1.1.0` | 能力已被其他合同吸收 | Critic adversarial review、Challenge、`AG-05/AG-07` | 最强反方、失败类比、利益相关方阻力和致命缺陷必须改变正文、条件或质量状态 |
| `v6-pipeline-coordinator@1.0.0` | 能力已被其他合同吸收 | `AnalysisRun` 状态机、预算、heartbeat、repair target、恢复和升级 | 方法包只声明顺序/预算/修复目标，不控制线程、进程、文件系统、租户或队列 |
| `v6-rag-pool@2.0.0` | P0 直接编译 | Research 检索任务、来源分级、去重、重试、调用预算和 Evidence Gateway | 保留检索纪律，不复制三 Agent 文件队列；provider/live/cached/fixture 由运行时 Adapter 决定 |
| `v6-safety-anchor@1.3.0` | P0 直接编译 | Critic mandatory substep、`safety-anchor` Schema | 检查共享盲区、共同假设、叙事回音和伪收敛；高严重度发现必须进入 Challenge 和修复链 |
| `v6-strategy-synthesis@1.2.1` | P0 直接编译 | Synthesis/Validation Prompt、跨因素收敛与分歧、支撑强度和修复 | 综合只能消费引用完整的上游产物；冲突、脆弱假设和不可约简未知不得被流畅文本隐藏 |

固定计数：**P0 直接编译 13、能力已被其他合同吸收 7、延后到下一方法包 8、仅参考 1、禁用 2，合计 31。**

## 核心战略分析框架如何进入当前 Run

第一版 full Run 的战略主干不是单一框架，而是一个有先后关系的组合：

1. `framework-selector` 决定是否适用并冻结分析边界。
2. `business-diagnosis-ten-questions` 与 `v6-analysis-agent` 建立需求、采购、技术、交付、现金、供应链、竞争和可逆性研究轨。
3. `porter-five-forces` 分市场解释竞争结构。
4. `v6-safety-anchor`、`counterparty-response-matrix`、`pre-mortem` 和 `v6-devils-advocate` 对当前倾向施加反方压力。
5. `scenario-planning` 检查策略在结构变化下是否存活。
6. `meadows-leverage-points` 把建议从“选择哪个市场”推进到“改变哪个系统机制”。
7. `v6-strategy-synthesis` 与 Chief-of-Staff 能力形成条件化路径、阈值、退出标准和领先指标。
8. `analysis-quality-gate` 与 Validation 决定是否允许正式交付，而不是替结论制造概率背书。

这一组合由 `manifest.yaml` 的 execution order 固定，并由五个 `LQ-*`、`AG-*`、Schema 与 eval 共同验收；模型只提到框架名称不算执行。

## 工具与方法包的边界

`探讨` 中的脚本、文件队列、LaTeX/PPTX、平台聊天、委派和供应商连接能力不直接复制进方法包。方法包只能声明稳定的抽象能力与约束：

- `search_web`、`fetch_url`、读取已授权资料等只读工具名；
- 哪个 Worker 可以调用、最大调用次数、超时和失败语义；
- 输出 Schema、引用要求、质量门和修复路径；
- 禁止写文件、启动进程、读取其他 Workspace、任意 MCP 地址或直接处理密钥。

Provider、API Key、缓存、网络、SSRF、Workspace 权限、任务队列、事件和进程生命周期属于平台运行时。该分离确保方法可以版本化和审计，同时不让一个方法包获得基础设施控制权。

## 后续方法包候选

延后项不是永久丢弃。建议按分析对象而不是按单个 Skill 建包：

| 候选方法包 | 可组合来源 |
|---|---|
| `organization-strategy-and-change` | Allison Three Models、Organization Diagnosis、Iceberg Model、Post-Mortem |
| `innovation-portfolio-and-transition` | Three Horizons、HV Analysis、Scenario Planning、Meadows Leverage Points |
| `policy-and-platform-counterfactual` | Counterfactual Comparison、Allison Three Models、Structural-Demographic Theory |
| `fundraising-narrative-and-bp` | BP Writing、Deliverable Standards，以及独立且重新评审的 deck renderer |

后续包可以复用已发布的通用 Schema 或平台能力，但必须拥有独立 applicability、诊断问题、Prompt、质量门、eval 和 SemVer，不能在当前 Run 中临时拼装。

## 变更规则

- 31 项名称集合或状态变化必须同步本文、`SOURCES.md`、产品规划处置账本和相应 eval。
- 直接编译能力改变 Prompt、Schema、质量门、预算或工具权限时，必须提升方法包 SemVer。
- 延后项进入新方法包时，不修改已发布的 `hardtech-market-direction@1.1.0`。
- 禁用项进入任何生产链必须提交独立安全和架构评审，不能作为 fallback 偷渡。

## 1.1.0 工程语义补齐

31 个研究 Skill 的名称集合与既有处置计数不变。`framework-selector` 的 Cynefin 前置门现在由 `cynefin-gate-result`、RunManifest freeze 和 gate eval 承载；RAG 的精确引用由 `source-span` 承载；综合/反方由 `judgment-set`、`dissent-record`、`draft-recommendation` 承载；质量门由 V1-V9 `validator-aggregate` 承载。平台领域层仍负责 signer、DecisionRecord append-only 和 no-run-no-report，方法包不拥有这些权限。
