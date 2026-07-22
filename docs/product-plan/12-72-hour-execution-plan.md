# 12. 72 小时 Hackathon Prototype Slice 执行计划

## 可行性结论

72 小时只承诺 **Hackathon Prototype Slice**，不承诺完整 MVP 或发布候选。该结论仅在 Gate 0 通过、6 个持续并发槽位、独立 worktree、每 6 小时集成和阻断产品决策快速响应时成立。单 Agent、少于 6 个槽位、无法运行 Docker/Postgres/浏览器、合同未冻结或真实 provider probe 未通过时，不能沿用 72 小时估算。

完整 MVP 使用 `23-multi-agent-capacity-execution-plan.md` 的 4 Agent/108 小时、3 Agent/144 小时档，或在真实团队/环境明确后重新估算；不得把 Prototype 的静态展示、宽度降级或 fixture 外部输入当成完整 MVP。

唯一金路径案例：`资金与研发资源有限的球形机器人项目，应该优先进入救援市场，还是家庭服务市场？`

## Prototype 不可降级合同

即使在黑客松范围内，以下能力不得用静态页面或预生成最终对象伪造：

- 单一 Pydantic → OpenAPI → TypeScript 合同链；
- `decisionCaseId/analysisRunId` canonical ID；
- UserSession、WorkspaceMembership 和 human `sign` capability；
- pre-run/run-frozen SourceRecord/SourceSpan 与 quoteHash；
- 正式 AnalysisRun 状态持久化；
- no-run-no-report 和 validator blocker fail-closed；
- `SystemRecommendation` option/abstain；
- 完整 SignoffPayload、payloadHash、一次 nonce 和原子签署；
- append-only DecisionRecord；
- live/cached/fixture 的真实来源标识；
- Look V7 五主工作区、Project Drawer、empty view 和 Review dialog 语义。

fixture 只可替代模型/搜索/抓取的外部响应，不能替代 Postgres、Run、Source freeze、质量门、报告对象、签署事务或 DecisionRecord。

## 72 小时承诺范围

### 必须交付

- Web/API/Worker/Postgres 可重复启动，迁移和 seed 可重放；
- 注册/登录/退出、session 撤销、一个 Workspace、一个 signer；
- 空项目、Project Drawer、Case 创建/进入；
- 问题工作区的讨论输入、最小 CandidateRevision 审阅和 confirmed Case snapshot；
- `quick` 与一条正式 `full` 金路径；focused 可显示授权边界但不是必需演示路径；
- `hardtech-market-direction@1.1.0` 安装、confirmed Charter 和真实 AnalysisRun/SSE；
- fixture external responses 驱动真实 Research/Critic/Synthesis/Validation pipeline；如 live provider 可用，增加一次 live smoke；
- 至少一条完整 SourceSpan → Claim → Judgment 链，V1-V9 结构存在且 blocker fail-closed；
- 一份可读取的 StructuredReport，包含 option 或 abstain、条件、阈值、退出条件、行动项、领先指标和未知项；
- 判断工作区可读取报告与引用；HTML 渲染必须可用；
- 推演工作区至少运行一个确定性 confirmed fixture graph/scenario 的 formal SimulationRun，保存 inputHash，并可展示一个翻转条件；
- 决定工作区创建完整 SignoffRequest，由授权人类签署并读取不可变 DecisionRecord；
- 默认 `ink` 主题与 Look V7 token/组件骨架；
- 1440×900 和 390×844 的金路径；键盘可完成登录、Case、Run、报告和签署；
- 5 分钟演示、60–90 秒录屏、至少 6 张截图、恢复手册和断网演示路径。

### Stretch，不阻断 Prototype

- focused 完整体验；
- 五项 StrategicLensArtifact 的完整专用 UI（后端产物可以先通过通用 artifact viewer）；
- PDF 导出；
- PDF 以外的 TXT/Markdown 上传，以及 DOCX/CSV/JSON；
- 完整图编辑、FactorCandidate、undo/redo；
- 命名分支、比较和非破坏性回滚；
- BYOK 配置 UI（连接器服务端合同和 secret 边界仍需存在）；
- 完整 Review 创建/历史，Prototype 可先提供只读 dialog 骨架；
- 十主题切换的全部视觉精修；默认 `ink` 与 token 基础必须完成；
- 自动提醒、复杂监测、多用户协作和多方法包。

## Gate 0：计时前准入

必须验证：

```powershell
uv --version
uv python find 3.12
node --version
pnpm --version
docker version
docker compose version
git rev-parse --show-toplevel
git worktree list
py -3.12 scripts/verify_decision_os_contracts.py
```

同时满足：

- canonical 文档已通过 CCR-20260721-003 和最终修复审计；
- `ways/hardtech-market-direction/1.1.0` 校验/安装通过；
- OpenAPI/TypeScript drift clean；
- `.gitignore` 在首次 staging 前存在，secret scan 配置就绪；
- Docker daemon、Postgres 16、浏览器环境可用；
- 配置的模型 ID 由环境提供，并对文本、structured output、tool-call/thinking 实际需要做启动 probe；文档不以营销名代替运行时验证；
- 至少一个外部来源 provider 可以 live probe；否则明确记录只进行 fixture prototype，不能宣称 live 验收；
- 6 条泳道均有独立分支/worktree，write scope 无重叠；
- Task 19A–19D 与 Task 19 gate 已进入 manifest，Task 17/18 依赖 gate。

Gate 0 未通过可以继续不计时的离线准备，但不得宣布 72 小时冲刺开始。

## 六条泳道

| Owner | Prototype 责任 | 禁止越界 |
|---|---|---|
| Contract/Integration Lead | schema、迁移、OpenAPI、集成门、Task 19 gate 审批 | 不替其他 owner 发明 UI/业务捷径 |
| Ways/Agent Pipeline | 方法安装、DeepAnalysis、V1-V9、报告 publisher | 不签署决定，不返回平行 DTO |
| Case/API/Data | auth/session/workspace、Case、Source、signoff、Decision | 不修改生成合同或模拟 model 输出 |
| Web/UX | Look V7 shell、五工作区、Project/Review/dialog、generated client | 不加载 `look/app.js`，不手写 response DTO |
| Simulation/Graph | confirmed fixture graph、纯函数引擎、inputHash、最小 sandbox | 不把 preview/non-converged 用于正式建议 |
| QA/Release | contract/security/E2E、恢复、截图、录屏 | 只报缺陷，源修复回原 owner |

## 时间盒与冻结点

| 时间 | Prototype 切片 | 退出条件 |
|---|---|---|
| 0–12h | 仓库、合同、迁移、auth/session、Workspace、Look shell | fresh migration、登录、empty/Case、contract checks 通过 |
| 12–30h | Candidate/Case snapshot、Ways、Charter、Run、Source freeze、SSE | 一条 fixture formal Run 到 validating，SourceSpan 可复验 |
| 30–48h | V1–V9、StructuredReport、判断页、最小 sandbox | no-run-no-report、abstain、Simulation inputHash tests 通过 |
| 48–60h | SignoffPayload、nonce、DecisionRecord、端到端联调 | 授权人类签署原子测试和金路径 E2E 通过 |
| 60–72h | 功能冻结、修阻断、响应式、部署、彩排、恢复资产 | 只接受 blocker；演示与断网恢复完成 |

每 6 小时先合并 schema/migration/generated contracts，再合并消费者；任何合同 drift、跨租户、secret、signoff 或 no-run-no-report 失败都会阻止该集成门。

## 第 36 小时硬检查

必须至少满足：

- confirmed Charter 可创建；
- AnalysisRun 可恢复/取消且 source freeze 完成；
- 四类运行时角色各产生隔离结构化产物；
- V1–V9 exact set 可运行；
- StructuredReport 可渲染 HTML；
- 报告引用可跳到 SourceSpan；
- 质量门可以产生 abstain；
- 最小 confirmed graph 可确定性推演并保存 inputHash。

失败时停止新增宽度。优先放弃 PDF、完整 lens UI、完整图编辑、分支、BYOK UI、完整 Review 和额外主题精修；不得放弃不可降级合同。

## 停止线

| 风险 | 停止线 | 处理 |
|---|---|---|
| canonical drift | 出现平行 ID/DTO/状态 | 停止受影响实现，先修文档与生成合同 |
| session/signoff 缺陷 | 可伪造 signer、nonce 可重放或 payload 未冻结 | 发布阻断，先修原子事务 |
| no-run-no-report 失败 | 可直接创建 ready Report | 发布阻断，修 publisher/FK/gate |
| fixture 冒充 live | UI/事件不标来源或读取 expected 输出 | 发布阻断 |
| Simulation 不可重放 | inputHash 缺字段或非 converged 改变建议 | 发布阻断 |
| 并发不足 | 少于 6 个持续槽位 | 72 小时 Prototype 估算失效，切完整 MVP 档或重估 |
| 第 60 小时仍加功能 | 功能冻结被破坏 | 回退到最后通过集成门的切片，只修 blocker |

## 交付物

- Prototype source、迁移、生成合同和可重复启动命令；
- Look source manifest/token/组件映射；
- 球形机器人 seed、external fixture 与 expected 断言；
- contract/security/Simulation/signoff 测试报告；
- Web 金路径、断网 fixture 路径和恢复清单；
- 5 分钟脚本、60–90 秒录屏、截图、一页说明、架构图与完整备用录屏；
- 明确的 stretch backlog 和完整 MVP 108/144 小时接续计划。

## 完成定义

72 小时 Prototype 只有在不可降级合同、必须交付项、阻断测试和演示恢复同时完成时才可宣布完成。未完成 stretch 项不影响 Prototype 结论，但必须清楚标记；任何静态假数据绕过真实领域链、签署或来源追踪都会使结论失败。
