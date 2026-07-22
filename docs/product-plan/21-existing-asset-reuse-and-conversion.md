# 21. 现有资产复用与转换合同

## 目的与约束

本文是 `探讨`、Hermes Agent 和 Open WebUI 0.10.2 到 Ludus 的文件级转换账本。它回答四个问题：源资产能否复用、以何种方式复用、落到哪个 Ludus 文件、如何证明转换没有引入平行合同或许可证风险。

本文不授权运行时读取三个参考目录。Ludus 的生产运行时只读取自身代码、数据库、已发布 `method-packs` 和经授权的外部输入。参考目录不得被复制进镜像、fixture 或部署卷。

复用判定只使用以下四类：

| 判定 | 含义 | P0 规则 |
|---|---|---|
| **Extract & adapt** | 提取自有方法内容，或在兼容开源许可下抽取边界清楚的纯函数/小模块并适配 | `探讨` 必须记录来源版本和编译裁剪；开源代码必须保留许可/版权、记录精确函数来源并补 Ludus 契约测试 |
| **Reimplement from verified behavior** | 已核验源文件行为，但在 Ludus 技术栈和领域合同中重新实现 | Hermes/Open WebUI 的默认方式；不复制其 UI、单体循环或通用运行时 |
| **Reference only** | 只保留设计证据或 P1 评估入口，不进入 P0 依赖图 | 不安装、不 import、不形成运行时 fallback |
| **Do not use** | 禁止检查、复制、执行、打包或作为产品状态 | 密钥资产、弃用资产、与 P0 授权边界冲突的通用执行能力 |

## 方法论复用与运行框架复用必须分离

`探讨/skills/research/**` 主要是**方法论资产**：诊断问题、分析阶段、证据纪律、反方、综合、质量门和交付标准。它们只能在发布前编译进 `ways/hardtech-market-direction/1.1.0`，再由安装器生成不可变 `method-packs`。

Hermes、`探讨/config.yaml` 的非秘密结构和 Open WebUI 文件主要提供**运行框架机制**：注册、加载、权限收窄、预算、事件、取消、引用和 UI 状态。它们落到 `services/api/app/**` 与 `apps/web/**`，不得写回方法 Prompt，也不得让方法包控制租户、密钥、队列或网络连接。

一次 `full` Run 不加载全部 31 个研究 Skill。原因是：

1. `MethodRouter` 先选择一个已发布方法包，Run 只加载该包 manifest 指定的四类 Worker Prompt、schema、质量门和允许工具。
2. 31 个 Skill 同时进入上下文会制造重复角色、相互冲突的文档格式、不可控检索和预算膨胀，破坏可重放哈希。
3. Chief of Staff、Devil's Advocate、Safety Anchor 和 Coordinator 是已编译能力或子步骤，不是额外正式 Worker；正式 Worker 始终只有 Research、Critic、Synthesis、Validation。
4. 行业或任务不匹配的框架留给后续方法包；运行时不得临时拼装“万能 full Run”。

验收：任一 Run 的审计记录可列出唯一 method ID/version/hash、实际加载的 Prompt/schema、四类 Worker、工具白名单和预算；不得出现对 `探讨/skills` 的运行时文件读取。

## 原 Hermes 战略分析师到 Ludus 的转换链

`探讨` 不是单独的一组 Prompt，而是“战略分析师行为 + 方法选择 + RAG + 多 Agent + 质量门 + 交付模板”运行在 Hermes 上的组合。Ludus 按以下一一映射保留其有效机制，同时把临时文件和个人环境转换为正式产品对象：

| 原组合资产 | Ludus 转换 | 保留的效果 | 明确变化 |
|---|---|---|---|
| `SOUL.md` 战略分析师人格/纪律 | 版本化 `system_policy.py` + 方法 Prompt | 证据优先、反谄媚、反方闭环、坦诚未知、条件化判断 | 删除旧人格名、个人画像、平台偏好和旧版本号；Workspace 用户偏好进入自己的 Profile |
| `framework-selector` + `full-mode-composer` | Method Router + published manifest + AnalysisCharter | 适用性判断、方向确认、阶段前置、完整性检查 | Router 不能动态拼任意 Skill；confirmed Charter 冻结方法/材料/预算 |
| `v6-rag-pool` + `pool_manager.py` | `RetrievalTask -> Provider Adapter -> RawArtifact -> EvidenceItem -> Information Gate` | 优先级、去重、来源分级、失败恢复和证据引用 | 文件队列改为 Postgres；外部文本不可信；只读 Exa/Firecrawl/Tavily 稳定工具 |
| Hermes `delegate_tool.py` + v6 多 Agent 协议 | Research/Critic/Synthesis/Validation 四角色 + stage artifact | 隔离上下文、并行研究、权限收窄、失败隔离、交叉消费 | 角色是工作流职责而非四个基座模型；深度/并发/调用预算有硬上限 |
| Safety Anchor + Devil's Advocate + 五个直接相关 Skill | Critic/Synthesis/Research 的强制子协议 + 五份 `StrategicLensArtifact` | 盲区、事前验尸、对手响应、行业结构、结构情景和系统杠杆 | 每项必须通过独立 schema/行为 eval；不能只在一段 Prompt 里提到名称 |
| Pipeline Coordinator + quality gate | persisted `AnalysisRun` 状态机 + Validation + repair target | 自动推进、失败恢复、阻断和修复闭环 | Postgres 是唯一状态；质量分只判断交付资格，不是正确率 |
| 临时分析目录 + 报告模板 | canonical entities + ArtifactStore + HTML/Playwright PDF | 可重放阶段产物、引用、正式报告和可读交付 | 不以 Markdown/LaTeX 目录为唯一状态；HTML/PDF 同源 |

方法包行为验收不是比较措辞。当前 `ways` 已包含 5 个 eval 规格：球形机器人 exact/full 金路径；同一去标识化脑机接口平台案例在 seed/full 与 angel/full 两种资源尺度下的策略敏感性配对；信息不足的 partial/full 阻断；不适用营销优化问题的 unsupported/focused 阻断。球形机器人仍验证同一冻结 Case 能产生隔离研究/批判/综合/校验产物、五份完整透镜、可回溯证据、被反方修改过的条件化建议、质量门阻断/修复记录以及可映射到沙盘的 scenario/leverage 结果。脑机接口配对只是 parity eval specification，用于约束“规模会改变策略性质”的预期行为，不代表旧 Hermes 与 Ludus 已在同一模型和材料条件下实际运行。

## 二次开发授权记录

产品方已确认可对 `探讨`、Hermes Agent 和 Open WebUI 进行二次开发。实施前仍需在目标仓库 `docs/asset-authorizations/` 建立非敏感摘要，记录授权主体、资产版本、允许复制/修改/重写的范围、品牌处理、分发限制、有效期、审批引用和责任人。授权摘要不会替代上游 LICENSE/NOTICE；在摘要和逐文件 provenance 未完成前，继续采用本文件的最保守判定。

## 许可证、来源与 NOTICE

| 来源 | 已核验许可 | 允许方式 | NOTICE/发布要求 |
|---|---|---|---|
| `探讨` | 根目录未发现统一 `LICENSE`；视为产品方控制的内部来源，不能从子目录第三方许可证推断整个目录许可 | 仅在所有权已确认的 Ludus 工作区内 **Extract & adapt**；对外发布前由产品方确认授权 | `ways/hardtech-market-direction/1.1.0/SOURCES.md` 记录 Skill 路径、frontmatter 版本和编译贡献；外部引用内容不得因出现在 Skill 中就被复制 |
| Hermes Agent | `hermes-agent-hermes-hermes-a8a19433/LICENSE`，MIT，Copyright 2025 Nous Research | 对解析、schema 规范化和注册表等纯函数/小模块使用 **Extract & adapt**；对状态化、同步或高权限胶水使用 **Reimplement from verified behavior** 或禁用 | 建立 `decision-lab/THIRD_PARTY_NOTICES.md`，记录本地版本、精确源文件/函数和 MIT；任何实质代码复用同时复制完整 LICENSE |
| Open WebUI 0.10.2 | `LICENSE`、`LICENSE_NOTICE`、`LICENSE_HISTORY`；本地版本含 MIT、BSD-3-Clause 与带品牌限制的 Open WebUI License 时间分段 | 因单个本地文件的提交归属未逐文件证明，P0 统一按最严格边界 **Reimplement from verified behavior**，不复制 Svelte、样式、品牌或 MCP client | `THIRD_PARTY_NOTICES.md` 记录版本与三个许可文件；任何源码复制必须先做提交级 provenance 和法律复核，本计划默认禁止 |

`THIRD_PARTY_NOTICES.md` 是发布清单，不是把参考项目变成运行时依赖的手段。CI 应扫描镜像和产物，确保不存在 `open-webui-0.10.2/`、`hermes-agent-hermes-hermes-a8a19433/`、`探讨/.env`、`探讨/auth.json` 或参考目录源码。

## `探讨` 顶层资产转换表

下表每一项共同适用：`探讨` 根目录未发现统一 `LICENSE`，只在产品方确认拥有的范围内转换；方法内容在 `ways/.../SOURCES.md` 留存来源，秘密资产和未获授权的第三方内容不进入 NOTICE 或发布物。

| 源文件/目录 | 判定 | Ludus 目标文件 | 适配点 | 验收 |
|---|---|---|---|---|
| `探讨/SOUL.md` | **Extract & adapt** | `ways/hardtech-market-direction/1.1.0/prompts/*.md`；计划新增 `services/api/app/agents/system_policy.py` | 将智力诚实、事实/假设分离、反谄媚、反方和不确定性表达拆成版本化 system policy 与方法 Prompt；删除个人身份、单一用户偏好、飞书、人格表演和旧版本号 | Prompt snapshot 测试证明不含个人名、平台名或隐藏推理要求；方法输出仍执行证据、反方和条件化建议 |
| `探讨/config.yaml` 的非秘密结构 | **Extract & adapt** | `services/api/app/core/config.py`、`services/api/app/agents/model_provider.py`、`services/api/app/agents/budget.py`、`services/api/app/connectors/registry.py` | 只白名单转换 provider/model、timeout、compression、delegation budget、tool availability 等结构；改为 Pydantic typed settings 和环境注入；不整体复制文件 | 配置缺字段/未知字段/非法预算测试失败；API、SSE 和日志不返回完整 Key；默认 DeepSeek 可被环境覆盖 |
| `探讨/.env`、`探讨/auth.json` | **Do not use / Do not inspect** | 无 | 视为秘密资产；禁止读取、复制、解析、加入 fixture、镜像、日志、文档示例或迁移脚本 | preflight/CI 对路径和常见密钥模式做发布阻断扫描；镜像与 Git 清单不存在这些文件 |
| `探讨/config.yaml` 中任何内联凭证值 | **Do not use** | 无；只允许目标环境变量或服务端加密 secret store | 即使与当前默认 Provider 相同也不得迁移；源凭证由所有者独立轮换 | 配置转换测试只输出字段名和非秘密默认值，不输出原值 |
| `探讨/skills/research/**` | **Extract & adapt**，逐项见下表 | `ways/hardtech-market-direction/1.1.0/**`、`CAPABILITY-MAP.md`、后续版本化 ways | 只编译命中 P0 方法的内容；31 项全部记录版本、处置、目标位置和裁剪理由，不复制临时目录协议 | source validator、内容哈希、eval、`SOURCES.md` 和能力地图一致 |
| `探讨/skills/research/v6-rag-pool/scripts/pool_manager.py` | **Reimplement from verified behavior** | `services/api/app/evidence/service.py`、`services/api/app/agents/tools/web_search.py` | 复现优先级、去重、重试、来源分级和 `infra_failure` 语义；改为 Postgres/Provider Adapter，不运行文件队列 | 检索上限、去重、fallback、来源模式和恢复测试通过 |
| `探讨/prediction-log.md` | **Reference only** | P1 `Review`/决策校准设计 | 只提取“事前记录判断与翻转条件、事后比较结果”的机制；原案例内容不进入共享数据或 runtime RAG | P0 `DecisionRecord`/`Review` 已有来源版本、阈值和复盘日期；自动校准明确留到 P1 |
| `探讨/lessons/*.md` | **Reference only** | `ways/**/evals` 候选库、开发失败模式清单 | 逐份去标识化、事实/许可评审后才能转成 eval；不得把历史案例原文塞入生产提示词或跨 Workspace 检索 | 新 eval 有来源、授权、脱敏审查和确定性断言；未审条目不打包 |
| `探讨/memories/MEMORY.md`、`USER.md` | **Do not use** | 无 | 含历史个人/会话记忆，不能迁移到共享 system policy、方法包或 fixture | CI/镜像扫描零命中；跨租户测试证明没有原用户画像默认值 |
| `探讨/templates/01_research_report/**` | **Extract & adapt** | `services/api/app/reports/templates/report.html`、print CSS 与 renderer snapshot | 在产品方确认所有权后提取信息层级、章节和打印经验，改为 Ludus 自有 HTML/CSS；不把 LaTeX 设为主路径，不复制未经审计的外部字体/素材 | 同一 StructuredReport 生成 HTML/PDF；视觉快照、引用完整性和许可证扫描通过 |
| `探讨/templates/02_*` 至 `20_*` | **Reference only** | P1 独立交付物方法包 | 财务模型、PPTX、BP、投委会等不是球形机器人 P0；逐模板完成许可/字段/渲染审计前不复制 | P0 renderer 不加载这些路径；未来每类模板有独立 schema、ways 版本和验收 |
| `探讨/skills` 中非 `research` Skill | **Reference only** | P1 工具/交付能力目录 | Feishu、PPT、OCR、浏览器和其他通用能力不进入首个战略方法包，也不扩大 P0 工具权限 | method-pack source list 只出现已批准研究 Skill；运行时工具白名单无平台写能力 |
| `探讨/imf-data-mcp/**` | **Reference only** | P1 审核连接器候选 | 只评估数据语义和只读调用边界；P0 不启动本地脚本、不接受任意 MCP URL，也不复用源认证状态 | P0 配置/API 无该 server；P1 接入前完成许可证、schema、超时、数据来源和密钥审计 |
| `探讨/tools/**` | **Reference only** | P1 报告/演示工具候选 | 目录含嵌套第三方仓库与各自许可证；未逐文件 provenance 前不得复制脚本、资产或依赖，P0 不生成 PPTX | 镜像、依赖树和发布物不含该目录；未来采用项单独建 NOTICE 与测试 |
| `探讨` 的临时项目目录、Markdown 状态、LaTeX/PPTX 运行链 | **Do not use** | 无；对应状态进入 Postgres/ArtifactStore/StructuredReport | 不作为唯一生产状态，不让报告格式决定领域模型 | 删除临时目录后 Run 仍可从数据库恢复；HTML/PDF 同源 |

## `探讨/skills/research` 全量处置账本

状态只使用：**P0 直接编译**、**能力已被其他合同吸收**、**延后到下一方法包**、**仅参考**、**禁用**。版本来自各 Skill frontmatter；正文与 frontmatter 不一致时以 frontmatter 为审计版本。

以下 31 行共同适用 `探讨` 的内部来源边界；全部处置必须同步到 `ways/.../CAPABILITY-MAP.md`。实际直接编译或直接改变当前方法合同的来源写入 `SOURCES.md` 和 manifest `source_skills`；平台层吸收、延后、参考和禁用项记录目标位置与理由，但不得伪装成当前运行时 Skill。

| Skill | 状态 | 原因、目标与验收 |
|---|---|---|
| `allison-three-models@1.0.0` | 延后到下一方法包 | 政府/组织决策三透镜不属于硬科技市场方向 P0；目标为未来公共事务/组织决策 ways；当前 Router 不得返回 |
| `analysis-quality-gate@2.4.1` | P0 直接编译 | 四个正交交付门进入 `quality-gates.yaml` 与 Validation Prompt；验收严重短板可阻断且分数不解释为概率 |
| `analytical-lens@3.6.0` | 能力已被其他合同吸收 | A 模式的追问、反向思维、假设与快速质检进入非正式 `QuickAnalysisResult`/system policy；不得创建正式 Run |
| `arxiv@1.0.0` | 仅参考 | 只参考论文元数据与版本意识；P0 统一走 `search_web/fetch_url`，不运行其脚本或绕过 Evidence Gateway |
| `bp-writing@1.1.0` | 延后到下一方法包 | 融资 BP/PPTX 是独立交付方法包，不属于市场方向报告；P0 不触发 |
| `business-diagnosis-ten-questions@1.3.0` | P0 直接编译 | 商业基线和需求真实性第 11-16 问进入 `diagnostic-questions.yaml`；eval 必须覆盖真实需求、采购和最小楔子 |
| `counterfactual-comparison@1.0.2` | 延后到下一方法包 | 适合政策/平台外力干预，不强塞进球形机器人 full；未来专用方法包单独校准 |
| `counterparty-response-matrix@1.0.0` | P0 直接编译 | 编译为 Critic 的 `counterparty_response_matrix` 强制透镜、独立 stage-output schema 与 persisted artifact；必须覆盖 1-2 个关键对手方、2-3 个含 no-action 的我方行动、最优/最差/最可能回应、窗口、再回应、公开发布测试、下行不对称和反身性；不增加新 Worker |
| `deliverable-standards@1.3.0` | 能力已被其他合同吸收 | 结论先行、行动标题、来源和局限进入 `structured-report.schema.json` 与 HTML renderer；20 类文档和 PPTX/LaTeX 不加载 |
| `document-type-selector@1.3.0` | 能力已被其他合同吸收 | P0 输出由 quick/focused/full 授权合同固定，不让用户或模型在 20 类文档中另选 |
| `framework-selector@6.12.7` | P0 直接编译 | 适用/排除边界、先想后搜、失败恢复和闭环进入 manifest/Prompt；Router 只从已发布目录选择 |
| `full-mode-composer@5.6.2` | P0 直接编译 | 管道完整性和收束检查进入 Synthesis/Validation；不采用正文声称的未发布 5.6.3 版本 |
| `hv-analysis@2.0.0` | 延后到下一方法包 | 横纵深研与 LaTeX 交付是独立研究方法，不作为本包四轨之一 |
| `iceberg-model@1.0.0` | 延后到下一方法包 | 系统诊断适合问题根因类 ways；当前沙盘可表达层级但不宣称执行该 Skill |
| `latex-to-pdf@1.3.0` | 禁用 | P0 固定 `StructuredReport -> HTML -> Playwright PDF`；不得把 Tectonic/LaTeX 变成 fallback 主路径 |
| `meadows-leverage-points@1.0.0` | P0 直接编译 | 编译为 Synthesis 的 `meadows_leverage_points` 强制透镜；schema 必须表达系统边界、存量/流量、反馈、延迟、规则/激励、至少三个杠杆层级、被忽略高杠杆、失控增强回路和高杠杆副作用，并映射沙盘 lever/feedback；不增加新 Worker |
| `organization-diagnosis@1.0.0` | 延后到下一方法包 | 组织执行/并购整合是后续组织变革 ways；P0 只把交付能力作为约束证据 |
| `porter-five-forces@1.0.0` | P0 直接编译 | 编译为 Research 的 `porter_five_forces` 强制透镜；对两个市场分别界定行业边界、逐项五力证据/趋势/监管和战略含义，明确分数不是选项决策公式 |
| `post-mortem@1.0.0` | 能力已被其他合同吸收 | 过程/结果/执行/外部冲击分离进入 canonical `Review`；自动复盘和完整 Skill 运行延后 |
| `pre-mortem@1.0.0` | P0 直接编译 | 编译为 Critic 的 `pre_mortem` 强制透镜；假定失败已发生，覆盖内部/外部/系统视角、至少五项原因、前三风险、预防/应急/检测和继续/修改/放弃判断；不创建第五类 Agent |
| `scenario-planning@1.0.0` | P0 直接编译 | 编译为 Synthesis 的 `scenario_planning` 强制透镜；区分既定因素与关键不确定轴，生成至少三个结构不同且含时间线/利益相关方/预警信号的情景，并至少推翻一次当前策略；禁止退化为乐观/基准/悲观缩放 |
| `slide-deck-generator@1.6.2` | 禁用 | 源 Skill 自身已标记弃用；P0 不生成 PPTX，也不调用其脚本 |
| `structural-demographic-theory@1.0.0` | 延后到下一方法包 | 宏观政治不稳定分析与 P0 领域不匹配；未来政治风险 ways 另行评审 |
| `three-horizons@1.0.0` | 延后到下一方法包 | 组合创新与转型过渡需要独立长期战略方法包，不混入市场方向单次 Run |
| `v6-analysis-agent@1.3.1` | P0 直接编译 | 因素研究包、2-3 轮上限、TDD 证据纳入和缺口进入 Research Prompt/schema；以 frontmatter 1.3.1 为准 |
| `v6-chief-of-staff@1.2.0` | 能力已被其他合同吸收 | 条件化建议、阶段路径、风险响应和领先指标已编译进 Synthesis；不得注册独立正式角色 |
| `v6-devils-advocate@1.1.0` | 能力已被其他合同吸收 | 最强反方、致命缺陷和执行压力进入 Critic mandatory substep；发现必须反馈正文/条件 |
| `v6-pipeline-coordinator@1.0.0` | 能力已被其他合同吸收 | 阶段前置、预算、恢复和升级进入 `AnalysisRun` state machine/Worker；方法包不能控制进程或文件系统 |
| `v6-rag-pool@2.0.0` | P0 直接编译 | 检索请求 schema、来源分级、去重、重试和调用预算进入 Research 与 Evidence 服务；不复制三 Agent 文件队列 |
| `v6-safety-anchor@1.3.0` | P0 直接编译 | 集体盲区、共享假设和伪收敛进入 Critic 子步骤；按 frontmatter 1.3.0，不采纳文件中未发布版本标题 |
| `v6-strategy-synthesis@1.2.1` | P0 直接编译 | 跨因素收敛/分歧、支撑强度和修复进入 Synthesis/Validation；不能创造无引用事实 |

当前计数固定为：P0 直接编译 13、能力已被其他合同吸收 7、延后到下一方法包 8、仅参考 1、禁用 2，合计 31。自动检查必须同时核对名称集合和这五类计数。

账本验收：CI 从 `探讨/skills/research/*/SKILL.md` 生成名称集合，与本文表格及 `ways/.../CAPABILITY-MAP.md` 名称集合比较；缺行、重复行、状态/计数不一致或未知状态即失败。直接编译状态变化必须同步 `SOURCES.md`、manifest、SemVer 和 eval；其他状态变化至少同步能力地图、目标方法包规划与授权说明，不能只改本文。

## Hermes 逐文件转换表

Hermes 源许可证为 MIT。Ludus 应直接利用边界清楚的纯函数和小型注册机制，同时把 async、Workspace、Pydantic、Postgres 与四角色状态胶水留在自身架构中。下表每一项共同要求 `THIRD_PARTY_NOTICES.md` 记录 MIT 来源；实际抽取代码必须把完整 MIT 文本随发布物分发并记录精确函数。

| Hermes 文件 | 判定 | 已核验行为 | Ludus 目标文件 | 适配点与验收 |
|---|---|---|---|---|
| `tools/registry.py` | Extract & adapt | `ToolEntry`、`ToolRegistry.register/get_definitions`、availability cache、toolset 查询、统一 dispatch | `services/api/app/agents/tool_registry.py` | 保留 MIT 署名并抽取注册/定义/缓存核心；handler 改为 Pydantic 原生 async，强制 `workspace_id/run_id/read_only/required_scopes`；契约测试覆盖碰撞、不可用工具、scope 和跨租户 |
| `agent/skill_utils.py` | Extract & adapt | `yaml_load`、`parse_frontmatter`、平台/条件提取与确定性排序发现 | `services/api/app/methods/source_validator.py`、`loader.py` | 保留 MIT 署名，抽取纯解析函数；限制为固定 ways/runtime 根，拒绝外部目录/路径穿越，增加 SemVer、内容哈希和 schema 兼容；测试 malformed YAML、重复 ID/version 和哈希漂移 |
| `tools/delegate_tool.py` | Reimplement from verified behavior | 新上下文、父子工具集取交集、阻断工具、并发/深度/迭代上限、父级只接收 summary/tool trace | `services/api/app/agents/runner.py`、`context.py`、`budget.py` | 改为四类 Worker 和 async task；最大派生深度 1，权限只能收窄；不继承原始 API key，不允许 clarify/memory/write；测试越权、预算、取消、隔离和结构化摘要 |
| `tools/mcp_tool.py` | Extract & adapt（纯函数）/ Reference only（runtime） | `_build_safe_env`、`_sanitize_error`、`_normalize_mcp_input_schema`、`_convert_mcp_schema`，以及 namespace/timeout/lifecycle 行为 | `services/api/app/agents/tool_schema.py`、`connectors/registry.py` | 仅抽取经测试的纯 schema/清洗函数并保留 MIT；P0 不运行 stdio/npx/任意 MCP URL/dynamic OAuth，不复制连接 runtime；测试 schema 兼容、错误脱敏、供应商超时和 Key 掩码 |
| `agent/context_compressor.py` | Reimplement from verified behavior | 保护头尾、裁剪旧工具结果、结构化增量摘要、压缩预算 | `services/api/app/agents/context.py` | 摘要必须引用 confirmed Case/Dossier 版本，保护目标/约束/决定/来源；不持久化隐藏推理或 `reasoning_content`；重放测试证明压缩前后冻结字段不漂移 |
| `tools/mixture_of_agents_tool.py` | Reference only | 并行参考响应、失败隔离、聚合器只消费成功结果 | `services/api/app/agents/runner.py`、ways quality gates | 只借鉴并行独立研究和失败隔离；不暴露通用 MoA 工具、不做模型投票、不把聚合当正确概率；测试单 Worker 失败可审计且质量门决定是否阻断 |
| `run_agent.py`、CLI、Gateway、`hermes_state.py` | Do not use | 通用单体循环、CLI/消息平台与 SQLite 会话 | 无直接目标；领域机制进入 `analyses/*`、`workers/analysis_worker.py` | 不 import、不复制；Postgres 是唯一正式状态，SSE 是正式进度；镜像扫描无 Hermes 包 |

Hermes NOTICE 验收：`THIRD_PARTY_NOTICES.md` 和源码注释记录 MIT 来源与被抽取函数；发布物包含完整 MIT 许可。抽取后必须先通过 Ludus 的 async、Workspace、权限、错误脱敏与路径边界测试，不能因为来源成熟就跳过适配验收。

## Open WebUI 逐文件转换表

下表每一项共同适用本地 `LICENSE`、`LICENSE_NOTICE`、`LICENSE_HISTORY` 的多许可证边界，并在 `THIRD_PARTY_NOTICES.md` 记录版本和路径。未完成提交级 provenance 前一律不复制源码、样式、图标、文案或品牌。

| Open WebUI 文件 | 判定 | 已核验行为 | Ludus 目标文件 | 适配点与验收 |
|---|---|---|---|---|
| `src/lib/components/chat/Chat.svelte` | Reimplement from verified behavior | message-scoped 事件、`statusHistory`、task IDs、取消、确认/输入、source/citation、重连后任务调和 | `apps/web/components/chat/MessageList.tsx`、`analysis/AnalysisProgress.tsx` | React/TanStack Query/SSE 重写；正式状态来自 Postgres 和 `Last-Event-ID`，取消后重新读取 canonical Run；E2E 覆盖重连不重复、取消不倒退、确认回调 |
| `src/lib/components/common/ToolCallDisplay.svelte` | Reimplement from verified behavior | 运行/完成/错误、参数与结果折叠、长结果预览 | `apps/web/components/analysis/ToolCallDisplay.tsx` | 只展示安全摘要、耗时、`originMode` 和 typed error；不展示 Key、原始敏感正文或隐藏推理；组件测试覆盖截断、错误和 aria-label |
| `src/lib/components/chat/Messages/Citations.svelte` | Reimplement from verified behavior | 来源归并、编号、详情弹层和可访问按钮 | `apps/web/components/quality/EvidenceDrawer.tsx`、`analysis/ReportSectionViewer.tsx` | 按 Evidence ID/Claim ID 跳转，展示支持/反对、等级、时间、冲突和适用范围；不得用距离值冒充可信度；引用完整性 E2E 通过 |
| `src/lib/components/chat/Messages/ResponseMessage/TaskList.svelte` | Reimplement from verified behavior | 任务计数、pending/in_progress/completed/cancelled 与折叠 | `apps/web/components/analysis/AgentTaskList.tsx` | 映射 canonical Worker/stage 状态，固定尺寸避免跳动；刷新后从事件历史恢复；组件测试覆盖四状态和键盘操作 |
| `backend/open_webui/events.py` | Reimplement from verified behavior | frozen event definitions、actor/subject/source/data envelope、多 sink 发布与错误隔离 | `services/api/app/analyses/schemas.py`、`repository.py`、`routes.py` | 只使用 Ludus canonical category/type；append-only sequence、Workspace scope、SSE replay；不采用 webhook/function 插件扩展；测试 `Last-Event-ID`、脱敏和 sink 失败隔离 |
| `backend/open_webui/utils/mcp/client.py` | Reference only（P1） | `AsyncExitStack` 生命周期、initialize timeout、tools/resources、幂等 disconnect | 无 P0 runtime 目标；P1 评估入口为 `services/api/app/connectors/` | P0 禁止远程 MCP、任意 URL、动态 OAuth 和资源读取；P1 只借鉴生命周期/超时/断开行为并用 Python 自行实现。测试确保 P0 API/配置不存在任意 MCP 地址输入和 stdio/npx 启动 |

Open WebUI NOTICE 验收：不复制 Svelte、CSS、图标、文案或品牌；`THIRD_PARTY_NOTICES.md` 记录本地 0.10.2、`LICENSE`、`LICENSE_NOTICE`、`LICENSE_HISTORY`。源码 provenance 未完成前，任何相似代码评审按阻断处理。

## 目标文件总览与完成标准

| 转换域 | 目标文件 | 最低验收 |
|---|---|---|
| 方法源 | `ways/hardtech-market-direction/1.1.0/**`、`SOURCES.md`、`CAPABILITY-MAP.md` | source validator、SemVer、hash、31 项能力处置、5 个 eval、9 个 strict schema、43 个诊断问题、29 项质量检查、四 Worker 和运行时不读 ways |
| 方法安装/路由 | `services/api/app/methods/{source_validator,installer,loader,router,schemas}.py` | exact/partial/unsupported、发布目录限定、哈希漂移阻断 |
| Agent runtime | `services/api/app/agents/{tool_registry,budget,context,runner,model_provider}.py` | async、Workspace scope、权限取交集、预算、取消、隔离产物 |
| Evidence/connector | `services/api/app/evidence/*`、`connectors/registry.py`、`providers/*` | read-only、live/cached/fixture、Key 脱敏、信息质量门 |
| 分析事件 | `services/api/app/analyses/{models,schemas,state_machine,repository,routes}.py` | append-only、SSE replay、canonical state、跨租户 404 |
| Web 交互 | `MessageList.tsx`、`AnalysisProgress.tsx`、`AgentTaskList.tsx`、`ToolCallDisplay.tsx`、`EvidenceDrawer.tsx` | Playwright 重连/取消/引用/任务状态，React 实现无 Svelte 依赖 |
| 许可证 | `THIRD_PARTY_NOTICES.md`、镜像/依赖扫描 | MIT 与 Open WebUI 多许可证来源有记录；参考源码不进入发布物 |

完成本专项必须同时满足：

1. 31 个研究 Skill 全部在产品账本和方法包 `CAPABILITY-MAP.md` 中有唯一且一致的处置状态，自动集合与固定计数比对通过。
2. `SOURCES.md` 和 manifest `source_skills` 只列实际编译或直接改变当前方法合同的来源；平台吸收/延期/参考/禁用项只在能力地图记录目标位置，不得伪装为运行时 Skill。
3. `SOUL.md` 和非秘密配置结构完成 schema 化转换，个人信息、平台信息和凭证为零。
4. Hermes/Open WebUI 每个指定文件都有判定、目标文件、适配点、许可证/NOTICE 和自动化验收。
5. 生产镜像、fixture、日志和 Git staged files 不含三个参考目录、`.env`、`auth.json`、原始密钥或 Open WebUI 品牌资产。
6. 当前先保留两个去标识化资源尺度 parity eval 规格，用来验证同一案例在 seed/angel 约束下应出现不同策略行为；它们不计作 legacy/Ludus 双轨完成。仍需经产品方授权并去标识化至少两个 `探讨` 既有成功实验，固定可比的模型与资料条件实际运行 legacy/Ludus 双轨行为评测；比较证据纪律、反方是否改变正文、五透镜完整性、条件化建议、剩余未知和追溯链，不比较逐字措辞。该 parity suite 未运行、未签署或未通过前只能宣称“转换合同已完成”，不能宣称“已复现原效果”。

## 2026-07-19 Ways 吸收完整性复审

31/31 名称集合与 13/7/8/1/2 处置计数保持通过，但此前不能据此宣称“工程语义已全面吸收”。本轮补齐：

| 源能力 | 1.1.0 转换目标 | 验收 |
|---|---|---|
| `framework-selector` 的 Cynefin 前置门 | `cynefin_gate` stage + strict schema + Charter/RunManifest freeze | clear/complicated/complex/chaotic/disorder 分流；override 仅人类且可审计 |
| RAG/证据定位 | SourceRecord/SourceSpan + quoteHash | Claim 精确定位页/段/字符或 Case/message locator |
| 分析/综合/参谋长 | JudgmentSet + DraftRecommendation | 建议是 analysis draft，不是 Decision |
| Safety Anchor/Devil/Pre-Mortem | DissentRecord + V7 validator | 反方被综合消费，未解决项保留 |
| quality gate | V1-V9 ValidationOrchestrator | exact set、strict JSON、blocker fail-closed |
| pipeline coordinator | DeepAnalysisRequest/Result + immutable RunManifest | 正式接口不使用 chat messages；可恢复和可重放 |

不吸收项保持不变：飞书、任意浏览器写操作、临时文件队列、自动 LaTeX/PPTX 交付、凭证、`.env`、`auth.json` 与运行时动态拼 Skill。Ways 1.0.0 保留为历史 release candidate；1.1.0 是当前唯一可继续安装的源版本。
