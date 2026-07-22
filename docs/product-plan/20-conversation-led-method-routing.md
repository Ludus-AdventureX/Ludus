# 20. 对话驱动的方法路由

## 文档状态

本文记录截至 2026-07-14 确认的入口、需求归纳、方法选择和正式分析契约。核心原则是：**不锁死入口，锁死正式分析的执行契约**。本文已与本目录 01-23、README 和机器清单同步；出现冲突时必须先统一文档，不允许实现自行选择版本。

## 产品决策

- 用户登录后直接进入日常问答，不先选择决策模板。
- 系统从对话和已确认档案中归纳决策问题、期限、目标、约束、选项、倾向、偏见、材料和未知项。
- 用户只需要决定问题是否值得分析，并选择快速分析、聚焦研究或完整战略分析。
- 快速分析直接在对话中生成 `QuickAnalysisResult`；聚焦/完整分析由系统在后台推荐方法包，并在 `AnalysisCharter` 中显示方法名称、版本、适用理由、边界、替代方法和缺失输入。
- 用户确认 focused/full Charter 后，档案快照、问题范围、分析等级、方法版本、允许材料和预算同时冻结。
- full Charter 同时冻结五项 `requiredStrategicLensTypes`；用户不逐项选择 lens，focused 该集合为空。
- 修改正式分析范围必须创建新 Charter draft，不覆盖已确认契约。

## 为什么不采用模板先行

模板先行要求用户在问题尚未澄清时理解“市场进入、产品方向、技术路线、资源投入”等方法差异，会把战略参谋变成咨询表单。完全自由生成分析流程又无法稳定测试、版本化和审计。

Ludus 因此采用混合模式：对话负责理解真实问题，方法包负责稳定执行，Charter 负责让用户确认边界。

## 三层方法体系

### 通用决策内核

所有分析强制执行类型分离、证据质检、来源冲突、反方审查、版本、质量门和复盘。用户不能关闭这些要求。

### 决策方法包

方法包定义适用/排除条件、诊断问题、证据需求、Worker、预算、输出结构、质量门和沙盘映射。P0 唯一正式方法包是 `hardtech-market-direction@1.1.0`。投资项目批量筛选是活动后的第二方法包，不参与本次 Router 候选集。

### 行业适配层

机器人、硬科技、机构采购、安全责任、供应链和量产作为适配模块叠加，不独立决定分析流程。

## Method/Skill Loader

方法内容不在 72 小时实施阶段重新发明。`ways/hardtech-market-direction/1.1.0` 是吸收 `探讨/skills/research/framework-selector/SKILL.md` v6.12.x 及关联研究技能后的唯一源资产；校验和安装流程将其发布为 `method-packs/hardtech-market-direction/1.1.0`。`ways` 可审阅、不可被运行时直接执行，`method-packs` 是内容寻址、不可变的 runtime method catalog。Loader 参考 Hermes `agent/skill_utils.py` 和 `agent/skill_commands.py` 的 frontmatter、目录发现与按需加载方式，但增加 Ludus 正式发布约束：

- manifest 必须包含 ID、语义化版本、适用/排除条件、必需输入、Worker、工具权限、预算、输出 schema、质量门、沙盘映射、eval 和来源技能清单。
- 加载时计算整个方法包内容哈希；Charter 和 Run 同时保存 ID、版本与哈希。
- 只有已发布目录中的包可进入 Router；Workspace 私有草稿不能生成正式输出。
- 路径穿越、重复 ID/版本、frontmatter 缺失、未知 Worker/工具或 schema 不兼容均阻止启动。
- 运行期间不重载方法包；升级产生新版本，不改变历史 Run。
- 同一 ID/版本的 ways 与已安装 method-pack 哈希不一致时阻止启动；修复必须重新安装或发布新版本，不能手改运行时产物。

`探讨` 的 A/B/C 能力映射为 Ludus 的 quick/focused/full，但用户界面只展示 Ludus 三档名称：A 的轻量框架能力进入 quick；B 的定向检索和简报进入 focused；C 的完整多 Agent 与质量门进入 full。原系统的内部角色名称由方法包吸收，不增加用户选择负担。

## 用户可见的分析等级

| 等级 | 用户看到的含义 | P0 输出 |
|---|---|---|
| 快速分析 | 使用已确认档案快速整理判断 | 结构化判断、反方、关键未知和下一步；不生成正式报告或正式沙盘 |
| 聚焦研究 | 针对 1-2 个关键方向检索和验证 | 仅在正式方法包匹配时生成执行简报、结构化建议、证据账本、反方、剩余未知和六维质量画像 |
| 完整战略分析 | 运行完整研究、批判、综合、校验和沙盘 | 仅在正式方法包匹配且质量门通过时生成正式报告、PDF 和正式沙盘 |

上述交付范围是授权合同：`focused` 不调用 PDF 与 `simulations/from-report`，`full` 才能创建 `StructuredReport` 和正式沙盘；两者都使用 confirmed Charter、持久化 AnalysisRun 和四类 Worker，但预算、研究方向数和输出 schema 不同。

full 的输出合同还要求五个独立 `StrategicLensArtifact`：Research=`porter_five_forces`，Critic=`pre_mortem` + `counterparty_response_matrix`，Synthesis=`scenario_planning` + `meadows_leverage_points`。Validation 只验证集合、行为和引用，不创建第五类 Worker，也不能把报告内联文本当作 artifact。`StructuredReport.lensArtifactIds` 必须解析到同 Workspace/Run 的五个 ready artifact；focused 不创建。

主界面不要求用户选择方法论名称。Charter 中显示方法详情是为了解释和审计，不把方法选择责任转嫁给用户。

## 方法路由输入与输出

正式 `MethodRouter` 的输入只能使用当前 Workspace 内已确认的 Case 与档案快照。用户当前消息可以触发“是否值得分析”的非绑定提示，但必须先形成并确认 `CandidateRevision`；未确认消息不得进入正式路由、Charter 或 Run：

输入使用 `06-data-model.md` 的 canonical `MethodRouteInput`，必须携带 `caseVersion`、Case/Dossier 快照哈希和 `focused | full` 请求等级。

输出必须结构化且可解释：

输出使用 `06-data-model.md` 的 canonical `MethodRecommendation`，包括快照引用、匹配状态、方法 ID/版本、理由、适用边界、缺失输入、替代方法、Router 版本和 `formalAnalysisAllowed`。

方法路由先用 manifest 的适用/排除规则筛选，再让模型在候选集合内生成结构化解释。模型不能发明不存在的方法包，也不能仅凭自评分把 `partial` 提升为 `exact`。

Router 决策和 Loader 解析均写入方法 ID、版本、内容哈希、来源技能版本和 routerVersion；`探讨` 的后续变化只能经评审导入新的 ways 版本，再安装为新的 runtime method-pack，不能绕过唯一源资产或破坏历史可重放性。

## P0 匹配规则

`hardtech-market-direction@1.1.0` 只有在以下条件满足时允许正式分析：

- 决策主体是硬科技、机器人或具有显著研发/交付约束的产品。
- 问题是市场方向、细分场景或高切换成本的产品市场选择。
- 至少有两个可比较选项。
- 已确认目标、硬约束和决策期限。
- 用户确认允许进入分析的材料和关键未知项。

`MethodRouter` 只为 `focused/full` 判定正式方法资格。若只有部分满足，Router 返回 `partial`，Charter 展示缺口，用户补充后重新路由。若不匹配，返回 `unsupported`：

- 日常问答继续可用。
- 快速分析可以独立运行，但固定标注“非正式方法输出”，不创建 Charter 或正式 Run。
- 聚焦研究和完整战略分析不可启动。
- 不生成正式报告、正式 PDF 或正式沙盘。
- 系统说明当前缺少匹配方法包，不用通用 Prompt 冒充正式战略分析。

## Analysis Charter

Charter 至少包含：

- 决策问题、决策期限和决策主体。
- 档案快照版本。
- 目标、硬约束、选项、当前倾向和可能偏见。
- 已确认材料、关键未知项和禁止进入分析的内容。
- 用户选择的分析等级。
- 推荐方法包 ID、版本和内容哈希。
- 推荐理由、适用边界、替代方法和缺失输入。
- 预计时间、检索/模型预算和允许连接器。
- `formalAnalysisAllowed` 和阻断原因。
- `requiredStrategicLensTypes`：focused 为空；full 为 canonical 五项完整集合。

Charter 状态流：

```text
draft
→ awaiting_confirmation
→ confirmed

draft / awaiting_confirmation → superseded
confirmed → superseded（仅在替代 Charter 被确认后）
```

只有 `confirmed` 且 `formalAnalysisAllowed=true` 的 Charter 能创建聚焦研究或完整战略 `AnalysisRun`。同一 Case 在 P0 同时最多存在一个活动正式 Run。

`requiredStrategicLensTypes` 与问题、目标、选项、偏好权重、硬约束、材料/连接器、预算、方法和分析深度具有相同冻结语义。任何增删或替换都分类为 `strategic_lens_set` amendment：创建 replacement Charter，确认后创建 new Run 并取消/关联旧 Run；不得 PATCH confirmed Charter、以 resolution 恢复或覆盖旧 lens artifact。

## 页面交互

```text
登录
→ 日常问答
→ 系统识别候选决策问题
→ 用户点击“分析这个问题”
→ 选择快速 / 聚焦 / 完整
→ 快速：生成 QuickAnalysisResult 并返回对话
→ 聚焦/完整：查看 Analysis Charter
→ 补充缺口或确认
→ 创建 AnalysisRun
```

快速、聚焦、完整使用分析深度选择控件。方法名称、版本和理由放在“分析方法”可展开区域，不使用模板卡片墙作为首页。

## API 边界

路由、Charter 与 Run API 的 Web 调用只允许使用生成 client。任何字段或错误码缺口必须提交 CCR；不得因为方法路由开发较快而在前端复制一份 MethodRecommendation/AnalysisCharter DTO。所有 mutation 同时服从统一 CSRF 和限流依赖。

- `POST /api/workspaces/{workspaceId}/cases/{decisionCaseId}/method-route`：根据已确认 `caseVersion`、档案快照和请求等级返回方法建议，不读取未确认消息，也不启动任务。
- `POST /api/workspaces/{workspaceId}/cases/{decisionCaseId}/analysis-charters`：从某次路由结果创建 Charter draft。
- `PATCH /api/workspaces/{workspaceId}/analysis-charters/{charterId}`：修改 draft；已确认 Charter 返回版本冲突。
- `POST /api/workspaces/{workspaceId}/analysis-charters/{charterId}/confirm`：冻结快照和方法版本。
- `POST /api/workspaces/{workspaceId}/conversations/{conversationId}/quick-analyses`：创建非正式 `QuickAnalysisResult`，不创建 Charter/Run。
- `POST /api/workspaces/{workspaceId}/analysis-charters/{charterId}/runs`：只有确认且允许正式分析时创建 `AnalysisRun`。
- `GET /api/workspaces/{workspaceId}/analyses/{analysisRunId}/strategic-lenses`：按 `06-data-model.md` canonical 顺序返回 full Run 的 `StrategicLensArtifactSummary[]`，只含 ID/type/producer/status、引用计数、版本/hash/origin/createdAt，不含 `content` 或 `researchRequests`；focused 返回空列表。
- `GET /api/workspaces/{workspaceId}/analyses/{analysisRunId}/strategic-lenses/{artifactId}`：读取一个完整 `StrategicLensArtifact` 判别联合；跨 Workspace、artifact 不属于 Run 或 ID 枚举统一 `404`。

Lens API 只读，不提供客户端 POST/PATCH/DELETE。Worker 通过内部 repository 幂等写入；相同 Run/lens 不同内容哈希阻断报告。API 路径、status 和响应对象以 `06-data-model.md` 为 canonical，本文不维护平行 DTO。

## 事件与审计

至少记录：

- `decision_candidate.detected`
- `method_route.completed`
- `method_route.unsupported`
- `analysis_charter.created`
- `analysis_charter.superseded`（替代 Charter 确认时）
- `analysis_charter.confirmed`
- `analysis_start.blocked`

事件保存输入快照哈希、路由规则版本、候选方法、最终方法版本和原因码，不保存模型内部思维链。

## 测试与验收

- 登录后直接进入问答，不出现强制模板选择页。
- 球形机器人案例稳定路由到 `hardtech-market-direction@1.1.0`，状态为 `exact`。
- 缺少目标或期限时返回 `partial` 和可执行缺口，不启动正式分析。
- 非匹配案例返回 `unsupported`，仍可聊天和快速分析，但正式研究按钮禁用。
- 用户只选择分析等级；方法名称和理由在 Charter 详情中可见。
- 已确认 Charter 不可修改，修改先产生替代 draft；只有替代 Charter 被确认后才产生旧 Charter 的 `superseded` 事件。
- 方法包升级不能改变历史 Charter 和 AnalysisRun。
- Router 不得返回方法目录中不存在的 ID 或版本。
- full Charter 的 lens 集合精确为 `porter_five_forces/pre_mortem/counterparty_response_matrix/scenario_planning/meadows_leverage_points`，focused 为空；集合变更只能 replacement Charter + new Run。
- full 报告的五个 lens ID 均可通过 Workspace-scoped API 读取且行为 schema 通过；缺一项或角色映射错误时不得 ready。focused 不得产生 lens artifact。

## 72 小时边界

P0 不实现可视化模板市场、方法编辑器、任意方法组合、自动生成新方法包、投资项目批量筛选或跨行业正式深度分析。只实现一个 Router、一个正式方法包、三个分析等级和完整的 Charter 确认链路。

## 完成定义

用户可以从自由对话开始，不理解方法论也能形成结构化决策问题；系统能解释推荐哪种方法及其边界；用户确认后冻结可重放的分析契约；不匹配问题不会被包装成正式战略报告。
