# 10. API 与事件模型

## API 设计原则

所有 HTTP schema 由 Pydantic 2 生成 OpenAPI，再生成 TypeScript types/client；`packages/contracts/openapi.json` 与 `types.gen.ts` 禁止手工修改。任何 API、事件、状态或错误码变化必须先更新 canonical 文档并通过 CCR。Cookie mutation 统一经过 CSRF dependency；任何服务器端远程 URL 统一经过 SSRF-safe client；限流在进入高成本领域操作前执行。

P0 API 以 Workspace 作用域下的 `DecisionCase` 为业务中心。快速分析同步或短流式返回 `QuickAnalysisResult`；focused/full 创建持久化 `AnalysisRun` 并返回 `analysisRunId`，前端通过 SSE 订阅进度。所有业务路由显式携带 Workspace，关键写接口支持幂等键。

通用 Header：

```http
Content-Type: application/json
Idempotency-Key: charter_001_v1_full
```

通用响应包装：

```json
{
  "ok": true,
  "data": {},
  "eventId": "evt_001"
}
```

错误响应：

```json
{
  "ok": false,
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "推荐缺少退出条件，报告未发布。",
    "retryable": false,
    "details": { "missingFields": ["recommendation.exitCriteria"] }
  }
}
```

## 核心 API

所有路径参数和 wire 字段只使用 `decisionCaseId`、`analysisRunId`；数据库列分别映射为 `decision_case_id`、`analysis_run_id`。实体详情可以有其他对象自己的 `id`，但不得为 Case/AnalysisRun 再引入 legacy short aliases。

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/auth/csrf` | 获取/刷新可读 CSRF token 与 cookie |
| `POST` | `/api/auth/register` | 注册并创建首个可撤销 UserSession |
| `POST` | `/api/auth/login` | 登录并创建可撤销 UserSession |
| `POST` | `/api/auth/logout` | 撤销当前 UserSession 并清除会话 cookie |
| `GET` | `/api/auth/session` | 读取当前用户、session 状态和可见 Workspace membership 摘要 |
| `POST` | `/api/workspaces/{workspaceId}/subjects` | 创建长期决策主体 |
| `GET` | `/api/workspaces/{workspaceId}/subjects/{subjectId}` | 读取主体与当前 Dossier 版本 |
| `POST` | `/api/workspaces/{workspaceId}/cases` | 创建决策项目 |
| `GET` | `/api/workspaces/{workspaceId}/cases` | 列出当前 Workspace 的案例 |
| `GET` | `/api/workspaces/{workspaceId}/cases/{decisionCaseId}` | 读取当前 `DecisionCase`、确认档案版本和 `ArgumentNode[]` 投影 |
| `GET` | `/api/workspaces/{workspaceId}/cases/{decisionCaseId}/versions/{version}` | 读取历史版本 |
| `PATCH` | `/api/workspaces/{workspaceId}/cases/{decisionCaseId}` | 更新用户确认的结构化档案 |
| `POST` | `/api/workspaces/{workspaceId}/cases/{decisionCaseId}/messages` | 发送讨论消息并生成候选档案变更 |
| `GET` | `/api/workspaces/{workspaceId}/cases/{decisionCaseId}/candidates` | 读取待审阅 `CandidateRevision` |
| `POST` | `/api/workspaces/{workspaceId}/cases/{decisionCaseId}/candidates/{candidateId}/confirm` | 确认候选并生成正式档案/Case 版本 |
| `POST` | `/api/workspaces/{workspaceId}/cases/{decisionCaseId}/candidates/{candidateId}/reject` | 否决候选但保留审计事件 |
| `POST` | `/api/workspaces/{workspaceId}/cases/{decisionCaseId}/candidates/bulk-review` | 批量确认、修改或否决候选 |
| `POST` | `/api/workspaces/{workspaceId}/conversations/{conversationId}/quick-analyses` | 生成非正式快速分析 |
| `POST` | `/api/workspaces/{workspaceId}/cases/{decisionCaseId}/method-route` | 按用户选择的分析等级推荐方法 |
| `POST` | `/api/workspaces/{workspaceId}/cases/{decisionCaseId}/analysis-charters` | 从路由结果创建 Charter draft |
| `PATCH` | `/api/workspaces/{workspaceId}/analysis-charters/{charterId}` | 修改未确认 Charter |
| `POST` | `/api/workspaces/{workspaceId}/analysis-charters/{charterId}/replacements` | 为 amendment 创建 replacement Charter draft |
| `POST` | `/api/workspaces/{workspaceId}/analysis-charters/{charterId}/confirm` | 冻结分析契约 |
| `POST` | `/api/workspaces/{workspaceId}/analysis-charters/{charterId}/runs` | 从 confirmed Charter 创建正式 Run |
| `GET` | `/api/workspaces/{workspaceId}/analyses/{analysisRunId}` | 查询 AnalysisRun 状态 |
| `GET` | `/api/workspaces/{workspaceId}/analyses/{analysisRunId}/events` | SSE 订阅 Run 事件 |
| `GET` | `/api/workspaces/{workspaceId}/analyses/{analysisRunId}/strategic-lenses` | 按 canonical 顺序列出当前 full Run 的五份战略透镜产物 |
| `GET` | `/api/workspaces/{workspaceId}/analyses/{analysisRunId}/strategic-lenses/{artifactId}` | 读取一份精确战略透镜产物 |
| `POST` | `/api/workspaces/{workspaceId}/analyses/{analysisRunId}/resolutions` | 分类并追加 resolution，恢复 needs_attention Run |
| `POST` | `/api/workspaces/{workspaceId}/analyses/{analysisRunId}/cancel` | 幂等取消 queued/执行中/needs_attention Run |
| `GET` | `/api/workspaces/{workspaceId}/evidence/{evidenceItemId}` | 读取证据条目详情（EvidenceItemView） |
| `GET` | `/api/workspaces/{workspaceId}/evidence/{evidenceItemId}/quality` | 读取证据质量评估维度 |
| `GET` | `/api/workspaces/{workspaceId}/evidence/{evidenceItemId}/provenance` | 读取证据溯源链（RawArtifact/SourceRecord/Quality） |
| `GET` | `/api/workspaces/{workspaceId}/evidence/{evidenceItemId}/direction` | 读取证据支持/反对方向投影 |
| `GET` | `/api/workspaces/{workspaceId}/evidence/{evidenceItemId}/same-source-group` | 读取同源独立性分组与独立来源计数贡献 |
| `GET` | `/api/workspaces/{workspaceId}/analyses/{analysisRunId}/evidence` | 列出该 Run 的证据条目 |
| `GET` | `/api/workspaces/{workspaceId}/analyses/{analysisRunId}/evidence-conflicts` | 列出该 Run 的证据冲突关系 |
| `GET` | `/api/workspaces/{workspaceId}/cases/{decisionCaseId}/reports` | 按版本/状态分页列出报告 |
| `GET` | `/api/workspaces/{workspaceId}/cases/{decisionCaseId}/reports/{reportId}` | 读取报告 |
| `POST` | `/api/workspaces/{workspaceId}/cases/{decisionCaseId}/reports/{reportId}/exports` | 创建 HTML/PDF 导出 |
| `GET` | `/api/workspaces/{workspaceId}/exports/{exportArtifactId}` | 读取导出 metadata/status |
| `GET` | `/api/workspaces/{workspaceId}/exports/{exportArtifactId}/content` | 鉴权下载 HTML/PDF |
| `POST` | `/api/workspaces/{workspaceId}/exports/{exportArtifactId}/retry` | 重试 failed 导出 |
| `POST` | `/api/workspaces/{workspaceId}/files` | 上传 Workspace 文件并创建 RawArtifact |
| `GET` | `/api/workspaces/{workspaceId}/files/{rawArtifactId}` | 鉴权读取上传文件 metadata/content |
| `POST` | `/api/workspaces/{workspaceId}/cases/{decisionCaseId}/simulations/from-report` | 从 ready 报告生成沙盘 |
| `GET` | `/api/workspaces/{workspaceId}/simulations/{graphId}/versions` | 分页读取图版本历史 |
| `GET` | `/api/workspaces/{workspaceId}/simulations/{graphId}/versions/{graphVersionId}` | 读取精确图版本 |
| `POST` | `/api/workspaces/{workspaceId}/simulations/{graphId}/runs` | 运行持久化的 experimental/formal 情景推演 |
| `GET` | `/api/workspaces/{workspaceId}/simulations/{graphId}/runs/{simulationRunId}` | 读取可重放 SimulationRun |
| `POST` | `/api/workspaces/{workspaceId}/simulations/{graphId}/working-copies` | 从指定图版本创建隔离工作副本 |
| `POST` | `/api/workspaces/{workspaceId}/simulations/{graphId}/working-copies/{workingCopyId}/factor-candidates` | 从自然语言生成待审阅因素与关系候选 |
| `PATCH` | `/api/workspaces/{workspaceId}/simulations/{graphId}/working-copies/{workingCopyId}` | 以 revision 乐观锁审阅或编辑节点和边 |
| `POST` | `/api/workspaces/{workspaceId}/simulations/{graphId}/working-copies/{workingCopyId}/previews` | 为精确工作副本 revision 生成实验预览 |
| `POST` | `/api/workspaces/{workspaceId}/simulations/{graphId}/working-copies/{workingCopyId}/versions` | 保存工作副本为不可变图版本 |
| `POST` | `/api/workspaces/{workspaceId}/simulations/{graphId}/versions/{graphVersionId}/bulk-review` | 逐节点/逐边确认、修改或否决并创建 confirmed 图版本 |
| `POST` | `/api/workspaces/{workspaceId}/simulations/{graphId}/branches` | 从指定历史版本创建实验分支 |
| `GET` | `/api/workspaces/{workspaceId}/simulations/{graphId}/branches` | 分页读取活动/归档分支 |
| `GET` | `/api/workspaces/{workspaceId}/simulations/{graphId}/compare` | 比较两个图版本、结果和推荐 |
| `POST` | `/api/workspaces/{workspaceId}/simulations/{graphId}/rollback` | 从历史版本创建新的当前版本 |
| `POST` | `/api/workspaces/{workspaceId}/simulations/{graphId}/adoptions` | 将沙盘结论提交为候选档案更新 |
| `POST` | `/api/workspaces/{workspaceId}/cases/{decisionCaseId}/scope-confirmations` | 人类确认问题边界并进入 scoped |
| `POST` | `/api/workspaces/{workspaceId}/cases/{decisionCaseId}/readiness-checks` | 执行输入、Cynefin 与运行前门，满足时进入 ready |
| `POST` | `/api/workspaces/{workspaceId}/cases/{decisionCaseId}/signoff-requests` | 人类从 review 创建待签署请求并进入 pending_signoff |
| `GET` | `/api/workspaces/{workspaceId}/signoff-requests/{signoffRequestId}` | 读取不可变 payload、payloadHash、状态和有效期；不返回 nonce 明文 |
| `POST` | `/api/workspaces/{workspaceId}/signoff-requests/{signoffRequestId}/nonce-rotations` | 授权 signer 轮换一次性 nonce，旧 nonce 原子失效 |
| `POST` | `/api/workspaces/{workspaceId}/signoff-requests/{signoffRequestId}/sign` | 授权人类签署并原子创建不可变 DecisionRecord |
| `GET` | `/api/workspaces/{workspaceId}/cases/{decisionCaseId}/decisions` | 分页读取 original/revision 决定历史 |
| `GET` | `/api/workspaces/{workspaceId}/decisions/{decisionId}` | 读取不可变 DecisionRecord |
| `POST` | `/api/workspaces/{workspaceId}/decisions/{decisionId}/monitoring-activations` | 人类启用监测计划并进入 monitoring |
| `POST` | `/api/workspaces/{workspaceId}/decisions/{decisionId}/revisions` | 创建 superseding DecisionRecord，不覆盖旧记录 |
| `GET` | `/api/workspaces/{workspaceId}/decisions/{decisionId}/reviews` | 分页读取复盘历史 |
| `POST` | `/api/workspaces/{workspaceId}/decisions/{decisionId}/reviews` | 创建决策复盘 |
| `GET` | `/api/workspaces/{workspaceId}/decisions/{decisionId}/reviews/{reviewId}` | 读取决策复盘 |
| `GET` | `/api/workspaces/{workspaceId}/connectors/catalog` | 读取审核连接器目录 |
| `GET` | `/api/workspaces/{workspaceId}/connectors` | 读取 Workspace 已配置来源和状态 |
| `POST` | `/api/workspaces/{workspaceId}/connectors` | 从目录添加 BYOK 连接器 |
| `PATCH` | `/api/workspaces/{workspaceId}/connectors/{connectorId}` | 启停、更新 Key 或预算 |
| `POST` | `/api/workspaces/{workspaceId}/connectors/{connectorId}/check` | 检查凭证、额度和可用性 |

## 认证、session 与 CSRF

`GET /api/auth/csrf` 是匿名可调用的 safe endpoint：服务端生成随机 token，设置非 HttpOnly 的同源 CSRF cookie，并在响应 body 返回相同 token。浏览器在调用 login/register/logout 或任何 Cookie mutation 前，把 token 放入 `X-CSRF-Token`；服务端同时验证精确 `Origin`（缺失时验证同源 `Referer`）并做常量时间比较。

登录成功后服务端创建 `UserSession`，JWT 的 `session_id` 只引用该记录；每次请求检查 session 未撤销、未过期且 `tokenVersion` 有效。退出在数据库中设置 `revokedAt`，再清除 Cookie。Workspace 授权每次从 `WorkspaceMembership` 读取 `owner | member` 与 `capabilities[]`；token 不永久缓存 Workspace 权限。`sign` 还必须在签署事务中再次校验活动 session 与 capability。

## 添加审核目录连接器

请求只接受目录 Provider，不接受任意 URL：

```http
POST /api/workspaces/ws_demo/connectors
```

```json
{
  "provider": "exa",
  "displayName": "团队 Exa",
  "apiKey": "<secret>",
  "allowedTools": ["search_web"],
  "budget": {
    "maxCallsPerRun": 12,
    "maxResultsPerCall": 20,
    "maxCrawlPages": 0
  }
}
```

响应不得回显 Key：

```json
{
  "ok": true,
  "data": {
    "connectorId": "conn_exa_demo",
    "provider": "exa",
    "displayName": "团队 Exa",
    "credentialMask": "exa_****7f2a",
    "readOnly": true,
    "status": "available"
  },
  "eventId": "evt_connector_added"
}
```

## 创建决策项目

主体创建最小请求为 `{ "name": "球形机器人项目", "description": "硬科技产品与市场方向的长期记忆边界" }`，响应返回 `subjectId`、`dossierId` 和 `currentDossierVersion`。`GET /subjects/{subjectId}` 返回 `DecisionSubject` 与当前 `DecisionSubjectDossier`；跨 Workspace 一律按不存在返回 `404`。

The client MUST NOT send `slug`; the server generates it and returns it in the `DecisionSubject` projection. The slug is unique and immutable within the Workspace, and a display-name rename never silently changes it.

For every subject/case relationship (Initiative, Case, case-scoped DossierEntry, Conversation, Message, and QuickAnalysisResult), the service validates both Workspace and Subject identity before writing. Same-Workspace but cross-Subject references are rejected with `VALIDATION_FAILED` (or a not-found response when the referenced object is not visible); no partial mutation is allowed.

案例列表支持 `?status=draft|scoped|ready|running|review|pending_signoff|decided|monitoring&operationalStatus=ok|blocked|needs_attention|cancelled|reopened|archived&limit=50&cursor=...`，返回 `{ "items": [{ "decisionCaseId", "title", "status", "currentVersion", "updatedAt" }], "nextCursor" }`。列表查询必须按 Workspace 限定，不能以全局查询后过滤。

案例详情返回 canonical `DecisionCase`、当前确认的 `DossierVersion` 引用、`caseVersion` 和按 `06-data-model.md` 组装的 `argumentNodes: ArgumentNode[]`。`ArgumentTree` 是该投影的前端视图，不维护第二套树节点 DTO；候选确认、修改类型或否决产生新版本后，客户端重新读取该详情投影。

请求：

```http
POST /api/workspaces/ws_demo/cases
```

```json
{
  "decisionQuestion": "资金与研发资源有限时，球形机器人应该优先进入救援市场还是家庭服务市场？",
  "initialContext": "项目已有可运行原型，但续航、载荷和复杂地形能力仍需验证；团队只能优先投入一个市场方向。"
}
```

响应：

```json
{
  "ok": true,
  "data": {
    "decisionCaseId": "case_spherical_robot",
    "version": 1,
    "title": "球形机器人市场方向决策",
    "inferredDecisionType": "market_direction",
    "clarifyingQuestions": [
      "这个决定最重要的成功指标是什么？",
      "哪些风险是不可接受的？",
      "目前已有的一手客户证据有哪些？"
    ]
  },
  "eventId": "evt_case_created"
}
```

## 讨论消息

请求：

```http
POST /api/workspaces/ws_demo/cases/case_spherical_robot/messages
```

```json
{
  "message": "目标是在 9 个月现金窗口内验证真实需求，只能优先投入救援或家庭服务中的一个方向。",
  "proposeStructuredUpdates": true
}
```

响应：

```json
{
  "ok": true,
  "data": {
    "candidateRevisionId": "candidate_002",
    "baseDossierVersion": 2,
    "baseCaseVersion": 1,
    "assistantMessage": "我已把现金窗口和单一方向约束写入候选档案。还需要确认采购周期、复杂地形能力和安全责任边界。",
    "proposedPatch": {
      "goalsAdded": 1,
      "constraintsAdded": 1,
      "unknownsAdded": 2
    }
  }
}
```

该接口只创建 `ConversationRevision` 和 `CandidateRevision`，不提升 `CaseVersion`。用户调用 confirm/bulk-review 后，服务在同一事务中生成正式 Dossier/Case 版本和领域事件。

## 方法路由与 Analysis Charter

请求：

```http
POST /api/workspaces/ws_demo/cases/case_spherical_robot/method-route
```

```json
{
  "caseVersion": 3,
  "requestedLevel": "full"
}
```

响应：

```json
{
  "ok": true,
  "data": {
    "methodRecommendationId": "route_001",
    "caseVersion": 3,
    "caseSnapshotHash": "sha256:fixture-spherical-robot-v3",
    "dossierSnapshotVersion": 2,
    "dossierSnapshotHash": "sha256:fixture-spherical-robot-dossier-v2",
    "decisionType": "market_direction",
    "matchStatus": "exact",
    "recommendedMethodId": "hardtech-market-direction",
    "recommendedMethodVersion": "1.1.0",
    "recommendedMethodContentHash": "sha256:method-hardtech-market-direction-1.1.0",
    "reasons": ["硬科技产品", "两个高切换成本市场选项", "存在明确研发和现金约束"],
    "applicabilityLimits": ["只评估市场方向，不替代工程安全认证"],
    "missingInputs": [],
    "formalAnalysisAllowed": true,
    "routerVersion": "router-1.0.0"
  }
}
```

用户确认前创建 Charter draft；确认后才可创建正式 Run：

```http
POST /api/workspaces/ws_demo/analysis-charters/charter_001/confirm
POST /api/workspaces/ws_demo/analysis-charters/charter_001/runs
```

```json
{
  "ok": true,
  "data": {
    "analysisRunId": "run_research_001",
    "status": "queued",
    "analysisLevel": "full",
    "progress": 0,
    "originModes": [],
    "charterId": "charter_001",
    "charterVersion": 1,
    "caseVersion": 3,
    "caseSnapshotHash": "sha256:fixture-spherical-robot-v3",
    "methodId": "hardtech-market-direction",
    "methodVersion": "1.1.0",
    "attempt": 1,
    "maxAttempts": 2,
    "eventsUrl": "/api/workspaces/ws_demo/analyses/run_research_001/events"
  }
}
```

## AnalysisRun 状态

```json
{
  "analysisRunId": "run_research_001",
  "decisionCaseId": "case_spherical_robot",
  "analysisLevel": "full",
  "status": "criticizing",
  "progress": 0.62,
  "originModes": ["live"],
  "attempt": 1,
  "startedAt": "2026-07-10T15:10:00+08:00",
  "heartbeatAt": "2026-07-10T15:12:30+08:00"
}
```

## 战略透镜产物

`StrategicLensArtifact` 是 Worker 的只读阶段产物，不提供客户端创建、修改或删除接口。列表接口按 Porter、Pre-Mortem、Counterparty、Scenario、Meadows 的 canonical 顺序返回 `StrategicLensArtifactSummary[]`，不传输大型 `content/researchRequests`；单项接口才返回完整判别联合：

```json
{
  "ok": true,
  "data": [
    {
      "id": "lens_scenario_001",
      "lensType": "scenario_planning",
      "producerRole": "synthesis",
      "phase": "strategic_synthesis",
      "status": "ready",
      "referenceCounts": {
        "sourcePacketCount": 4,
        "claimCount": 9,
        "evidenceCount": 11,
        "assumptionCount": 5,
        "challengeCount": 3
      },
      "charterVersion": 1,
      "caseVersion": 3,
      "methodId": "hardtech-market-direction",
      "methodVersion": "1.1.0",
      "schemaVersion": "1.0.0",
      "sourceSkillVersion": "1.0.0",
      "contentHash": "sha256:lens_content",
      "originModes": ["live"],
      "createdAt": "2026-07-10T15:18:00+08:00"
    }
  ]
}
```

`lensType` 只允许 `porter_five_forces | pre_mortem | counterparty_response_matrix | scenario_planning | meadows_leverage_points`。item 接口返回 `06-data-model.md` 的完整 `StrategicLensArtifact`，包括 resolved reference IDs、`researchRequests` 与 lens-specific `content`。full Run 在进入 `ready` 前必须各有一份 `ready` 产物，报告恰好引用这五个 ID。数据库对 `(workspaceId, analysisRunId, lensType)` 建唯一约束；相同 `contentHash` 的幂等重放返回已有对象，不同哈希返回冲突，重做必须创建 new Run。服务端从 Run 和当前 Workspace 推导所有权，不接受客户端传入 `workspaceId/decisionCaseId/analysisRunId`，跨 Workspace 一律返回 `404`。响应不得包含隐藏思维链、原始 Provider `reasoning_content` 或未清洗的工具结果。

每份产物完成时追加 `agent.task` 类别、`strategic_lens.completed` 类型的 SSE 事件，payload 只包含 `lensArtifactId`、`lensType`、`producerRole`、`referenceCounts`（与 `StrategicLensArtifactSummary.referenceCounts` 同形）和 `contentHash`，且只能在 artifact 行持久化提交成功后追加（CCR-20260725-ANALYSIS-01）。事件消费者随后通过上述读取接口获取正文，避免把大型 content 重复写入事件流。

## SSE 事件

SSE 格式：

```text
id: evt_045
event: agent.status
data: {"id":"evt_045","sequence":45,"workspaceId":"ws_demo","decisionCaseId":"case_spherical_robot","analysisRunId":"run_research_001","category":"agent.status","type":"analysis.stage.progressed","originMode":"live","sourceOriginModes":["live"],"createdAt":"2026-07-10T15:13:00+08:00","payload":{"status":"analyzing","progress":0.48,"message":"已完成救援需求、采购周期和技术风险分析"}}
```

事件负载：

```json
{
  "id": "evt_046",
  "sequence": 46,
  "workspaceId": "ws_demo",
  "decisionCaseId": "case_spherical_robot",
  "analysisRunId": "run_research_001",
  "category": "agent.task",
  "type": "research.packet.completed",
  "originMode": "live",
  "sourceOriginModes": ["live"],
  "createdAt": "2026-07-10T15:14:00+08:00",
  "payload": {
    "packetId": "packet_rescue_demand",
    "factor": "救援需求与采购可达性",
    "claimSupportScore": 0.64
  }
}
```

所有 SSE 事件使用统一信封：

```json
{
  "id": "evt_047",
  "sequence": 47,
  "workspaceId": "ws_demo",
  "decisionCaseId": "case_spherical_robot",
  "analysisRunId": "run_research_001",
  "category": "tool.call",
  "type": "tool.call.completed",
  "originMode": "live",
  "sourceOriginModes": ["live"],
  "createdAt": "2026-07-10T15:15:00+08:00",
  "payload": {
    "taskId": "task_retrieval_03",
    "tool": "search_web",
    "status": "completed",
    "resultSummary": "返回 12 个候选来源，5 个通过初筛"
  }
}
```

事件只使用 `06-data-model.md` 的一套合同：`category` 固定为 `agent.status`、`agent.task`、`tool.call`、`citation.added`、`user.confirmation.required`，用于前端分发；`type` 使用同一合同中更具体的领域枚举，例如 `analysis.stage.progressed`、`research.packet.completed` 或 `tool.call.completed`。SSE 的 `event:` 等于 `category`，`data:` 始终是完整 `AnalysisEvent` 信封。SSE 支持 `Last-Event-ID`，浏览器重连后按持久化 `sequence` 从数据库历史继续。`sequence` 在单个 `analysisRunId` 事件流内严格单调递增：由服务端在持久化时分配，禁止回退，允许缺口（CCR-20260725-ANALYSIS-01）。

DeepSeek V4 Pro 的 `reasoning_content` 是 Provider 内部 transient 协议字段，不是 API 或事件字段。thinking mode 默认启用；同一 assistant turn 发起 tool call 时，Provider 后续回传工具结果必须在内存中原样带回该字段。它不得出现在响应、SSE、数据库、日志、tool trace、报告或 UI；无 tool call 时立即丢弃，中断后也不恢复。strict tool calls 可在 thinking/non-thinking 使用；JSON Output 空 `content` 视为结构失败并至多执行一次既有修复/重试。

## 导出与文件

full ready 报告按类型创建导出；HTML 与 PDF 都从同一个 `StructuredReport` 和 renderer version 生成：

```http
POST /api/workspaces/ws_demo/cases/case_spherical_robot/reports/report_001/exports
Idempotency-Key: report_001_pdf_renderer_1
```

```json
{ "type": "pdf", "rendererVersion": "report-renderer@1.0.0" }
```

```json
{
  "ok": true,
  "data": {
    "exportArtifactId": "export_pdf_001",
    "reportArtifactId": "report_001",
    "type": "pdf",
    "status": "pending",
    "statusUrl": "/api/workspaces/ws_demo/exports/export_pdf_001"
  }
}
```

`GET /exports/{exportArtifactId}` 返回 status、mediaType、byteSize、sha256、rendererVersion、errorCode 和鉴权后的 `contentUrl`，不返回磁盘路径。`GET /exports/{exportArtifactId}/content` 只在 ready 时流式返回正文。`POST /exports/{exportArtifactId}/retry` 只接受 failed artifact，创建新尝试但保留同一 artifact ID 和失败历史；请求必须带 `Idempotency-Key`。PDF 失败不影响已 ready HTML；focused 报告调用任一导出接口返回 `EXPORT_NOT_ALLOWED`。

文件上传使用 multipart，并要求 `Idempotency-Key`：

```http
POST /api/workspaces/ws_demo/files
Content-Type: multipart/form-data
```

字段为 `file`、可选 `decisionCaseId` 和 `purpose=evidence`。PDF 校验文件签名与解析器结果；TXT/Markdown 没有可靠 magic bytes，改用扩展名/MIME 一致性、UTF-8 或 UTF-8 BOM 解码、NUL/控制字符拒绝、文本比例、大小上限和清洗后的解析结果联合判定。响应返回 `rawArtifactId`、originalName、mediaType、byteSize、sha256 和 `originMode`，不返回存储路径。`GET /files/{rawArtifactId}` 返回 metadata；`?download=1` 经 Workspace 所有权与文件下载授权检查后流式返回内容。

P0 ArtifactStore 锁定 filesystem/shared Docker volume。API、Worker 与 Renderer 使用同一挂载，路径必须位于 `workspaces/{workspaceId}/uploads/...` 或 `workspaces/{workspaceId}/reports/{reportArtifactId}/exports/...`；数据库只保存 metadata、Workspace-scoped 相对路径和 hash。跨 Workspace 统一 `404`，拒绝客户端磁盘路径、路径穿越和静态 volume 直链。保留 `ArtifactStore` 接口，活动后才可切换对象存储 provider。

## 从报告生成沙盘

该接口只接受 `analysisLevel == full`、Run `status == ready`、质量门通过且 `StructuredReport.lensArtifactIds` 精确引用五份 `ready` 战略透镜产物的报告；`FocusedResearchResult`、blocked Run、缺失透镜产物和调用方自报的 Case 版本一律拒绝。

请求：

```http
POST /api/workspaces/ws_demo/cases/case_spherical_robot/simulations/from-report
```

```json
{
  "reportArtifactId": "report_001"
}
```

响应：

```json
{
  "ok": true,
  "data": {
    "graphId": "graph_001",
    "graphVersionId": "graphver_001",
    "version": 1,
    "sourceReportArtifactId": "report_001",
    "sourceCaseVersion": 3,
    "originModes": ["live"],
    "nodeCount": 9,
    "edgeCount": 12,
    "status": "draft"
  }
}
```

该响应永远是 `draft`；服务端忽略是错误做法，任何自动确认字段都必须以 `VALIDATION_FAILED` 拒绝。创建请求必须带 `Idempotency-Key`，相同 `reportArtifactId + extractionPromptVersion` 返回同一 draft 结果。

## 批量审阅并确认图版本

```http
POST /api/workspaces/ws_demo/simulations/graph_001/versions/graphver_001/bulk-review
Idempotency-Key: graph_001_graphver_001_review_01
```

```json
{
  "baseGraphVersionId": "graphver_001",
  "confirmAllUnchangedNodes": true,
  "edgeReviews": [
    { "edgeId": "edge_demand_to_trial", "action": "confirm" },
    {
      "edgeId": "edge_procurement_to_cash",
      "action": "modify",
      "patch": {
        "strength": 0.65,
        "delaySteps": 1,
        "relationshipQualityScore": 0.7,
        "rationale": "按已确认采购证据修订。",
        "assumptionIds": ["asm_procurement_window"]
      },
      "finalStatus": "confirmed"
    },
    { "edgeId": "edge_03", "action": "confirm" },
    { "edgeId": "edge_04", "action": "confirm" },
    { "edgeId": "edge_05", "action": "confirm" },
    { "edgeId": "edge_06", "action": "confirm" },
    { "edgeId": "edge_07", "action": "confirm" },
    { "edgeId": "edge_08", "action": "confirm" },
    { "edgeId": "edge_09", "action": "confirm" },
    { "edgeId": "edge_10", "action": "confirm" },
    {
      "edgeId": "edge_11",
      "action": "modify",
      "patch": {
        "strength": 0.4,
        "delaySteps": 0,
        "relationshipQualityScore": 0.55,
        "rationale": "关系方向明确，但证据适用范围有限。",
        "assumptionIds": ["asm_scope_limit"]
      },
      "finalStatus": "conditional"
    },
    { "edgeId": "edge_unsubstantiated", "action": "reject", "reason": "缺少可用依据" }
  ]
}
```

所有 draft 节点和边必须被逐条处理；边的 `modify` 必须携带完整可追溯 patch 并以 `finalStatus == confirmed | conditional` 收口。`confirmAllUnchangedNodes` 只批量确认未修改节点；修改或否决节点必须另交 `nodeReviews`，最终所有参与传播的节点都必须 confirmed。服务端在一个事务中保存审阅事件和新的不可变 confirmed GraphVersion，绝不覆盖 draft：

```json
{
  "ok": true,
  "data": {
    "graphId": "graph_001",
    "sourceGraphVersionId": "graphver_001",
    "graphVersionId": "graphver_002",
    "version": 2,
    "status": "confirmed",
    "confirmedEdgeCount": 10,
    "conditionalEdgeCount": 1,
    "rejectedEdgeCount": 1
  },
  "eventId": "evt_graph_confirmed"
}
```

`baseGraphVersionId` 不是当前待审阅版本、工作副本已变化或同一边缺少审阅结果时分别返回 `VERSION_CONFLICT` 或 `GRAPH_REVIEW_INCOMPLETE`。同一 Idempotency-Key + 同一 body 重放返回原响应；同一 key 不同 body 返回 `IDEMPOTENCY_CONFLICT`。

版本冲突响应的 `details` 固定返回 `{ "submittedBaseGraphVersionId": "graphver_001", "currentDraftGraphVersionId": "graphver_003" }`，不做 last-write-wins。审阅不完整时 `details.unreviewedEdgeIds` 和 `details.unresolvedNodeIds` 给出可操作 ID。

## 工作副本、自定义因素与实验预览

创建工作副本：

```http
POST /api/workspaces/ws_demo/simulations/graph_001/working-copies
Idempotency-Key: 7cbdb1b4-graph-working-copy
```

```json
{
  "baseGraphVersionId": "graphver_004",
  "branchId": "branch_main"
}
```

自然语言输入因素：

```http
POST /api/workspaces/ws_demo/simulations/graph_001/working-copies/gwc_001/factor-candidates
```

```json
{
  "revision": 1,
  "sourceText": "地方预算审批稳定性会影响采购周期",
  "requestedUnit": "index"
}
```

服务返回 `FactorCandidate` 和零到多条 `RelationshipCandidate`。候选必须包含 proposed node 的 type、baseline/current/min/max、unit、controllability、evidenceStatus 与 rationale；建议边必须包含 polarity、strength、delaySteps、relationshipQualityScore、evidenceIds、assumptionIds 与 rationale。该响应不修改工作副本，用户添加入口不得提出 `decision` 节点。

用户通过 `PATCH .../working-copies/{workingCopyId}` 提交 `{ baseGraphVersionId, revision, candidateReviews, nodePatches, edgePatches }`。每个候选使用 `confirm | modify | reject`；未审阅建议关系不得进入传播。成功后 `revision + 1` 并发出 `graph.working_copy.updated`。revision 不匹配返回 `WORKING_COPY_REVISION_CONFLICT`，绝不 last-write-wins。

实验预览请求必须包含精确 `revision`、`strategyVersionId`、`scenarioVersionId`、`scoreDefinitionId/version`、`decisionMakerProfileId/version`、冻结的 `riskTolerance`、`engineVersion`、`epsilon` 和 `maxSteps`。服务端规范化全部输入并计算 `inputHash`。响应固定返回 `simulationMode == experimental_preview`、`workingCopyRevision`、上述冻结输入、结果、敏感因素、建议变化、warnings、convergenceStatus 与 stale。预览不创建 `SimulationRun`，不能用于 Decision、PDF、正式推荐或审计导出；工作副本再次变化后，旧预览读取必须返回 `stale: true` 或 `PREVIEW_STALE`。

保存工作副本为版本继续要求 `Idempotency-Key`，body 必须带当前 revision。保存创建新的不可变 draft `GraphVersion`；只有完成 bulk review 的 confirmed 版本才有资格用于 formal run。

事件新增：

- `graph.factor_candidate.created`
- `graph.working_copy.updated`
- `simulation.preview.ready`
- `simulation.preview.failed`

所有端点继续执行 Workspace scope、鉴权、CSRF、速率限制与统一信封。因素文本视为不可信输入；生成候选时不得执行其中的指令或读取未授权 Workspace 数据。
## 运行沙盘

请求：

```http
POST /api/workspaces/ws_demo/simulations/graph_001/runs
Idempotency-Key: sim-graph_001-formal-v4
```

```json
{
  "mode": "formal",
  "graphVersionId": "graphver_004",
  "strategyVersionId": "strategy_rescue_v2",
  "scenarioVersionId": "scenario_base_v1",
  "scoreDefinitionId": "scoredef_market_direction",
  "scoreDefinitionVersion": "score-v1",
  "decisionMakerProfileId": "profile_founder",
  "decisionMakerProfileVersion": 3,
  "riskTolerance": 0.45,
  "engineVersion": "linear-damped@1.1.0",
  "epsilon": 0.001,
  "maxSteps": 12,
  "nodeOverrides": {
    "node_procurement_cycle_months": 14
  }
}
```

响应：

```json
{
  "ok": true,
  "data": {
    "simulationRunId": "simrun_004",
    "simulationMode": "formal",
    "graphVersionId": "graphver_004",
    "strategyVersionId": "strategy_rescue_v2",
    "scenarioVersionId": "scenario_base_v1",
    "scoreDefinitionId": "scoredef_market_direction",
    "scoreDefinitionVersion": "score-v1",
    "decisionMakerProfileId": "profile_founder",
    "decisionMakerProfileVersion": 3,
    "riskTolerance": 0.45,
    "engineVersion": "linear-damped@1.1.0",
    "epsilon": 0.001,
    "maxSteps": 12,
    "steps": 7,
    "inputHash": "sha256:normalized-simulation-input",
    "convergenceStatus": "converged",
    "originModes": ["live"]
  }
}
```

服务端从数据库读取并验证全部版本引用，拒绝调用方省略 Profile 或从“当前配置”隐式补充风险偏好。`inputHash` 覆盖图/策略/情景/评分内容哈希、Profile ID/version、实际 riskTolerance、normalized overrides、engineVersion、epsilon 与 maxSteps；`GET .../runs/{simulationRunId}` 必须返回完全相同的冻结输入和结果以支持重放。

`mode == formal` 时 `graphVersionId` 必须指向 confirmed GraphVersion，且引擎只传播 `confirmed | conditional` 边；否则返回 `GRAPH_NOT_CONFIRMED`。`mode == experimental` 可读取 draft GraphVersion 并包含 draft 边，但响应与持久化 `SimulationRun` 必须标记 experimental，且不得用于 PDF、正式推荐或最终决定的系统建议。两种模式都必须引用存在且属于同一 graph/case/workspace 的 `scenarioVersionId`，不能只传 `scenarioId` 或内联未版本化情景。非 `converged` formal 结果保持可审计，但不得改变正式系统建议。

## 图分支、比较与回滚

创建分支：

```http
POST /api/workspaces/ws_demo/simulations/graph_001/branches
```

```json
{
  "baseGraphVersionId": "graphver_004",
  "name": "采购周期压力测试"
}
```

比较使用 `?leftVersionId=graphver_004&rightVersionId=graphver_007`，返回节点、边、参数、选项评分和推荐差异。回滚请求 `{ "targetVersionId": "graphver_004", "reason": "恢复已确认基准" }`，服务创建新版本并把其设为当前 head，绝不删除 `graphver_005..007`。

响应：

```json
{
  "ok": true,
  "data": {
    "simulationRunId": "simrun_001",
    "scenarioVersionId": "scenario_base_v1",
    "inputHash": "sha256:normalized-simulation-input",
    "optionScores": [
      { "optionId": "opt_continue_research", "score": 0.68 },
      { "optionId": "opt_rescue_pilot", "score": 0.54 },
      { "optionId": "opt_home_service_pilot", "score": 0.49 }
    ],
    "topDrivers": [
      { "nodeId": "node_procurement_cycle_months", "scoreDelta": 0.18 }
    ],
    "recommendationShift": "采购周期调整为 14 个月后，推荐从救援市场试点切换为继续研究。"
  }
}
```

## 请求签署与保存最终决定

最终决定分成“冻结待签 payload”和“授权人类签署”两个命令，不能由单次创建决定调用直接进入 `decided`。

### 1. 人类请求签署

```http
POST /api/workspaces/ws_demo/cases/case_spherical_robot/signoff-requests
Idempotency-Key: case_spherical_robot_signoff_v5
```

```json
{
  "payload": {
    "caseVersion": 5,
    "sourceAnalysisRunId": "run_research_001",
    "sourceReportArtifactId": "report_001",
    "sourceJudgmentSetId": "judgmentset_001",
    "sourceDissentRecordId": "dissent_001",
    "sourceCausalGraphId": "graph_001",
    "sourceCausalGraphVersionId": "graphver_004",
    "sourceSimulationRunId": "simrun_004",
    "systemRecommendation": {
      "kind": "option",
      "optionId": "opt_rescue_pilot"
    },
    "selectedOptionId": "opt_rescue_pilot",
    "decisionDraft": "在采购和技术门槛满足时优先推进救援市场试点，不启动全面产品化。",
    "conditions": ["完成至少 6 个救援机构访谈", "至少 2 个提供试点意向或测试场地"],
    "thresholds": [
      { "metric": "预计采购周期", "operator": "<=", "value": "12 months", "actionIfMissed": "切换为继续研究" }
    ],
    "exitCriteria": ["采购周期超过现金窗口", "复杂地形或安全测试未达最低门槛"],
    "actionItems": [
      { "id": "action_interviews", "text": "访谈 6 个救援机构并确认采购路径", "owner": "Founder", "dueAt": "2026-08-15", "status": "open" }
    ],
    "leadingIndicators": [
      { "id": "indicator_pilot_intent", "metric": "有效试点意向", "expectedDirection": "up", "threshold": ">= 2", "checkCadence": "biweekly" }
    ],
    "acceptedUnknownIds": ["unknown_procurement_timing"],
    "reviewDate": "2026-10-15"
  }
}
```

服务端校验 Case 当前是 `review`，且 Run/Report/JudgmentSet/Dissent/GraphVersion/SimulationRun 属于同一 Workspace、Case 和冻结版本链；Report 必须 ready，V1-V9 无 blocker，formal SimulationRun 必须 converged。服务端重新解析来源并验证 `systemRecommendation` 与当前 DraftRecommendation 完全一致；客户端不能替换系统建议或以空 option 伪造 abstain。

成功后服务端把规范化 `SignoffPayload` 作为不可变值对象保存，计算 `payloadHash`，生成高熵一次性 nonce，只持久化 `nonceHash`，并原子创建 `SignoffRequest(status=pending)`、让 Case 进入 `pending_signoff`：

```json
{
  "ok": true,
  "data": {
    "signoffRequestId": "signoff_001",
    "status": "pending",
    "payloadHash": "sha256:canonical-signoff-payload",
    "signatureNonce": "single-use-server-issued-nonce",
    "nonceIssuedAt": "2026-07-21T10:00:00Z",
    "expiresAt": "2026-07-21T10:15:00Z"
  }
}
```

`signatureNonce` 只在创建或 `nonce-rotations` 响应中显示一次；`GET /signoff-requests/{signoffRequestId}` 只返回 payload、payloadHash、status、nonceIssuedAt 和 expiresAt。轮换 nonce 时旧 nonce 在同一事务内失效。客户端不得自报签署人。

系统允许 abstain，示例 payload 必须保留真实原因，而人类仍只能从 Case 的合法 option 中作最终选择：

```json
{
  "systemRecommendation": {
    "kind": "abstain",
    "reasonCodes": ["FATAL_UNKNOWN", "NO_OPTION_PASSES_HARD_CONSTRAINTS"],
    "rationale": "现有证据不足以支持任一方案通过现金与安全门槛。"
  },
  "selectedOptionId": "opt_continue_research",
  "acceptedUnknownIds": ["unknown_procurement_timing", "unknown_safety_liability"]
}
```

### 2. 授权人类签署

```http
POST /api/workspaces/ws_demo/signoff-requests/signoff_001/sign
Idempotency-Key: signoff_001_signature_v1
```

```json
{
  "signatureStatement": "我已审阅系统判断、反方意见、成立条件与已知未知，并承担该决定的责任。",
  "payloadHash": "sha256:canonical-signoff-payload",
  "nonce": "single-use-server-issued-nonce"
}
```

服务端必须从已认证 session 解析 `signedByUserId`，并在单一数据库事务内原子验证：UserSession 活动且未撤销、WorkspaceMembership 活动、具有 `sign` capability、payloadHash 匹配、nonceHash 匹配且未使用、Case version 未变化、请求未过期且仍为 pending。任一失败均不得写入部分状态。

事务成功时：

1. 把 SignoffRequest 追加为 signed，并消费 nonce；
2. 将原 SignoffPayload 与 payloadHash 原样复制到不可变 DecisionRecord；顶层读取字段只能作为该 payload 的不可变投影；
3. 追加 `pending_signoff → decided` 生命周期事件；
4. 更新 Case projection。

Worker、ModelProvider、fixture、管理员后台和 Agent 工具注册表都不能调用或模拟该命令。

响应：

```json
{
  "ok": true,
  "data": {
    "decisionId": "decision_001",
    "recordKind": "original",
    "caseVersion": 6,
    "payloadHash": "sha256:canonical-signoff-payload",
    "sourceAnalysisRunId": "run_research_001",
    "sourceReportArtifactId": "report_001",
    "sourceJudgmentSetId": "judgmentset_001",
    "sourceDissentRecordId": "dissent_001",
    "sourceCausalGraphVersionId": "graphver_004",
    "sourceSimulationRunId": "simrun_004",
    "systemRecommendation": { "kind": "option", "optionId": "opt_rescue_pilot" },
    "selectedOptionId": "opt_rescue_pilot",
    "signedByUserId": "user_founder_001",
    "signedAt": "2026-07-21T10:00:00Z",
    "status": "decided"
  }
}
```

DecisionRecord 插入后禁止 UPDATE/DELETE。调整决定必须调用 `/decisions/{decisionId}/revisions` 创建新记录，并写 `supersedesDecisionRecordId`；生命周期、monitoring 与 review 状态通过 append-only 事件投影，不回写历史记录。

## 决策复盘

```http
POST /api/workspaces/ws_demo/decisions/decision_001/reviews
Idempotency-Key: decision_001_review_2026_10_15
```

```json
{
  "reviewDate": "2026-10-15",
  "outcome": "adjust",
  "recommendationAdoption": "adopted",
  "executionAssessment": "minor_deviation",
  "decisionProcessAssessment": "sound",
  "outcomeQuality": "mixed",
  "observedIndicatorValues": { "有效试点意向": "1" },
  "thresholdBreaches": ["有效试点意向 >= 2"],
  "externalChanges": ["地方预算审批窗口较原判断延后一个季度"],
  "actualOutcomes": ["完成 6 次访谈并获得 1 个有效试点意向"],
  "assumptionResults": [
    { "assumptionId": "assumption_procurement_window", "status": "weakened", "observation": "多数机构预计采购周期超过 12 个月" }
  ],
  "lessons": ["访谈数量不能替代可验证的采购承诺"],
  "nextDecisionChanges": ["下一轮把采购授权链证据设为进入试点的前置门槛"],
  "notes": "采购访谈完成，但有效试点意向低于阈值。",
  "nextReviewDate": "2026-11-15"
}
```

服务端从 `DecisionRecord` 复制并冻结 `sourceCaseVersion/sourceAnalysisRunId/sourceCausalGraphVersionId/sourceSimulationRunId`，客户端不得自报来源版本。响应返回 `reviewId`、`decisionId`、`outcome`、来源版本、`createdAt` 和读取 URL。`GET /decisions/{decisionId}/reviews/{reviewId}` 返回 canonical `Review`；创建复盘不会静默改写原 `DecisionRecord`，需要调整决定时另走候选/新决定流程。

## 错误码

| 错误码 | HTTP | 含义 | 是否可重试 |
|---|---:|---|---|
| `CASE_NOT_FOUND` | 404 | 决策项目不存在或不属于当前 Workspace | 否 |
| `WORKSPACE_NOT_FOUND` | 404 | Workspace 不存在、不可见或当前用户无活动 membership；对外部与不存在的资源逐字节一致，不泄露存在性 | 否 |
| `VERSION_CONFLICT` | 409 | 客户端基于旧版本写入 | 否，需刷新 |
| `VALIDATION_FAILED` | 422 | 结构或质量门不通过 | 否，需修正输入 |
| `ANALYSIS_RUN_ALREADY_ACTIVE` | 409 | Case 已有另一条活动正式 Run；不是幂等重放 | 否，读取 details.existingAnalysisRunId |
| `ANALYSIS_RUN_STALE` | 409 | Run 心跳超时并进入 needs_attention | 否，需提交合法 resolution |
| `ANALYSIS_RUN_NOT_RESUMABLE` | 409 | Run 不在 needs_attention 或已经是终态 | 否 |
| `ANALYSIS_RUN_NOT_CANCELLABLE` | 409 | ready/blocked Run 不是可取消的活动任务 | 否 |
| `RUN_AMENDMENT_REQUIRED` | 409 | 输入改变 Charter 冻结字段，禁止原 Run 续跑 | 否，创建 replacement Charter + new Run |
| `RUN_RESOLUTION_INVALID` | 422 | resolution 超出允许 payload 或引用不在冻结范围 | 否 |
| `ANALYSIS_TRANSITION_INVALID` | 409 | 请求隐含的 Run 状态迁移不在 canonical 迁移矩阵内，且没有更具体的错误码适用（CCR-20260725-ANALYSIS-01） | 否 |
| `MODEL_UNAVAILABLE` | 503 | 模型不可用 | 是，可切换或降级 |
| `SEARCH_UNAVAILABLE` | 503 | 搜索不可用 | 是，可使用缓存或审核 fallback |
| `CONNECTOR_NOT_ALLOWED` | 403 | Provider 或工具不在审核目录 | 否 |
| `CONNECTOR_CREDENTIALS_INVALID` | 401 | Key 缺失或失效 | 是，可更新 Key 或切换来源 |
| `CONNECTOR_RATE_LIMITED` | 429 | Provider 限流 | 是，可切换备用来源 |
| `CONNECTOR_QUOTA_EXHAUSTED` | 429 | 当前额度耗尽 | 否，可切换备用来源或缓存 |
| `METHOD_NOT_SUPPORTED` | 422 | 当前问题没有匹配的正式方法包 | 否，可继续讨论或快速分析 |
| `METHOD_INPUTS_INCOMPLETE` | 422 | 方法匹配但缺少目标、期限、约束或选项 | 否，补充后重新路由 |
| `CHARTER_NOT_CONFIRMED` | 409 | 正式分析契约尚未确认 | 否 |
| `CHARTER_IMMUTABLE` | 409 | 尝试修改 confirmed/superseded Charter | 否，创建 replacement draft |
| `CYNEFIN_GATE_BLOCKED` | 422 | domain 为 chaotic/disorder，且没有合法的人类 override | 否，先稳定或补充边界 |
| `LIFECYCLE_TRANSITION_INVALID` | 409 | 当前 Case 阶段不允许目标命令 | 否 |
| `SESSION_REVOKED_OR_EXPIRED` | 401 | UserSession 已撤销、过期或 tokenVersion 失效 | 否，重新登录 |
| `AUTH_INVALID_CREDENTIALS` | 401 | 登录凭据无效；未知邮箱与错误密码返回一致响应，不泄露账户存在性 | 否 |
| `MEMBERSHIP_CAPABILITY_REQUIRED` | 403 | 当前 membership 缺少所需 capability | 否 |
| `SIGNOFF_REQUIRED` | 409 | 尝试绕过 pending SignoffRequest 创建决定 | 否 |
| `SIGNOFF_HUMAN_REQUIRED` | 403 | actor 不是授权人类用户或客户端伪造签署人 | 否 |
| `SIGNOFF_STALE_OR_EXPIRED` | 409 | payloadHash、Case version 或有效期失效 | 否，重新审阅并请求签署 |
| `SIGNOFF_NONCE_INVALID` | 409 | nonce 错误、已使用或已被轮换 | 否，轮换 nonce 或重建请求 |
| `DECISION_RECORD_IMMUTABLE` | 409 | 尝试 UPDATE/DELETE 历史 DecisionRecord | 否，创建 revision |
| `REPORT_RUN_REQUIRED` | 409 | Report 缺少同 Workspace/Case 的 qualifying Run | 否 |
| `REPORT_PUBLICATION_BLOCKED` | 409 | Run 未 ready 或存在 validator/quality blocker | 否，修复对应阶段 |
| `PDF_RENDER_FAILED` | 502 | PDF 渲染失败 | 是 |
| `EXPORT_NOT_ALLOWED` | 403 | focused 或非 ready full 报告请求导出 | 否 |
| `STRATEGIC_LENS_INCOMPLETE` | 422 | full Run 缺少五项战略透镜之一、schema 未通过或报告引用不完整 | 否，回到指定 Worker 修复 |
| `GRAPH_REVIEW_INCOMPLETE` | 422 | draft 图仍有未逐条审阅的节点/边 | 否 |
| `WORKING_COPY_REVISION_CONFLICT` | 409 | 提交的工作副本 revision 已过期 | 否，需刷新或合并 |
| `FACTOR_DEFINITION_INVALID` | 422 | 因素字段、范围、类型或单位不满足合同 | 否，需修改 |
| `RELATIONSHIP_REVIEW_REQUIRED` | 422 | 建议关系尚未逐条确认、修改或否决 | 否 |
| `PREVIEW_NOT_FORMAL` | 409 | 尝试把实验预览用于正式决定、导出或推荐 | 否 |
| `PREVIEW_STALE` | 409 | 预览对应的工作副本 revision 已变化 | 是，重新预览 |
| `GRAPH_VERSION_NOT_FOUND` | 404 | 当前 Workspace 中不存在该图版本 | 否 |
| `GRAPH_NOT_CONFIRMED` | 409 | formal simulation 引用了非 confirmed GraphVersion | 否 |
| `SCENARIO_VERSION_MISMATCH` | 422 | 情景版本不属于同一 Workspace/Case/Graph | 否 |
| `SIMULATION_NOT_CONVERGED` | 409 | formal 运行没有在冻结 epsilon/maxSteps 内收敛 | 否，修正图或仅作 experimental |
| `IDEMPOTENCY_CONFLICT` | 409 | 同一 Idempotency-Key 被用于不同请求体 | 否 |
| `NEEDS_USER_INPUT` | 409 | 需要人工补充或确认 | 否，等待用户 |

幂等重放不是错误：同一 `Idempotency-Key` 与同一规范化 body 返回原有成功资源和原 HTTP success status，并在响应 `meta.idempotencyReplay=true`；不得用 `ANALYSIS_RUN_ALREADY_ACTIVE` 表示幂等命中。

竞争安全保证（CCR-20260725-ANALYSIS-01-ADDENDUM-A1）：任意连接级竞争下，同一 key + 同一 body 始终重放胜者成功——双 200、恰好一条 resolution 行、败者响应携带 `meta.idempotencyReplay: true`；同一 key 不同 body 仍返回 `IDEMPOTENCY_CONFLICT` 409。

## 安全错误码补充

| 错误码 | 含义 | 可重试 |
|---|---|---|
| `CSRF_VALIDATION_FAILED` | Cookie mutation 缺少或未通过同源 CSRF 证明 | 否，先刷新 token |
| `UNSAFE_REMOTE_URL` | URL、DNS/IP、重定向或响应限制未通过 SSRF 安全策略 | 否 |
| `REQUEST_RATE_LIMITED` | 登录、mutation 或高成本任务超过用户/Workspace 配额 | 是，按安全 `retryAfter` |
| `CONTRACT_VERSION_MISMATCH` | 客户端生成合同版本与服务端不兼容 | 否，刷新部署 |

## 幂等与版本冲突

- 所有创建 Run、resolution/cancel、from-report、graph bulk review、SimulationRun、导出/重试、文件上传和 Review 的 `POST` 接口必须带 `Idempotency-Key`。
- `PATCH /api/workspaces/{workspaceId}/cases/{decisionCaseId}` 必须带 `baseVersion`，若当前版本不同返回 `VERSION_CONFLICT`。
- Run 输出只引用创建时冻结的 `caseVersion`，不自动写入后续 Case；若用户已经编辑新版本，报告仍保留原版本引用，用户可创建替代 Charter 重新分析。
- `CandidateRevision`、`ConversationRevision` 不与 `CaseVersion` 共用版本序列。
- 图工作副本 patch 使用 `baseGraphVersionId`；保存、bulk review、分支和回滚均返回新版本 ID。bulk review 的 base 不是当前 draft head 时返回 `VERSION_CONFLICT`，绝不覆盖历史。
- RawArtifact、Evidence 和 connector call 携带单值 `originMode`。AnalysisEvent 保留直接事件的 `originMode`，并在 `sourceOriginModes[]` 保存该阶段涉及的去重来源；聚合事件的显示等级按 `fixture > cached > live` 取最保守值。ReportArtifact 与 ExportArtifact 都使用去重后的 `originModes[]`，不得把混合来源压成单值。从报告建图时 API 只接受 `reportArtifactId`，并从报告派生冻结的 `caseVersion`，拒绝调用方另传版本。

## Run resolution、amendment 与取消

confirmed Charter 永不修改。`needs_attention` Run 只通过 append-only resolution 恢复：

```http
POST /api/workspaces/ws_demo/analyses/run_research_001/resolutions
Idempotency-Key: run_research_001_constraint_resolution_01
```

```json
{
  "payload": {
    "kind": "hard_constraint_confirmation",
    "confirmedConstraintIds": ["constraint_no_legal_advice"]
  }
}
```

服务端先持久化 `RunInterventionClassification`。只有已冻结范围内的 `source_conflict`、`hard_constraint_confirmation`、`provider_recovery` 三类 payload，且 `changedFrozenFields == []`，才追加 `RunResolution` 并原子恢复：

```json
{
  "ok": true,
  "data": {
    "analysisRunId": "run_research_001",
    "classification": {
      "classificationId": "runclass_001",
      "result": "resolution",
      "changedFrozenFields": []
    },
    "resolutionId": "runres_001",
    "status": "synthesizing",
    "resumedFrom": "synthesizing"
  },
  "eventId": "evt_run_resumed"
}
```

Provider recovery 只能重试、使用已有缓存，或切换到 Charter `allowedConnectorIds` 中的连接器；不能增加连接器、材料或预算。`planning/retrieving/analyzing/criticizing/synthesizing/validating` 都可进入 `needs_attention`，resolution 只能回到持久化的 `lastResumableStage`，不能回到 `queued` 或由客户端指定阶段。

改变问题、目标、选项、偏好权重、硬约束定义、材料/连接器范围、预算、方法或分析深度时，服务端保存 `result == amendment` 的 classification，不创建 resolution，并返回 `409 RUN_AMENDMENT_REQUIRED`——分类与 `analysis.amendment_required` 事件先于 409 响应提交（CCR-20260725-ANALYSIS-01-ADDENDUM-A1）：持久化行在调用方收到错误前已 commit，不因 HTTP 响应状态回滚。details 固定为 `{ "changedFrozenFields": [...], "replacementUrl": "..." }`。客户端随后调用：

```http
POST /api/workspaces/ws_demo/analysis-charters/charter_001/replacements
Idempotency-Key: charter_001_replacement_01
```

请求必须带 `baseVersion`、结构化 amendment 和 `replacesAnalysisRunId`；响应是新的 `draft` Charter。新 Charter 确认后才 supersede 旧 Charter；用它创建 new Run 时，服务端原子地把旧 Run 置为 `cancelled`、记录 `cancellationReason == charter_replaced` 与 `supersededByAnalysisRunId`，并在新 Run 写 `supersedesAnalysisRunId`。旧 Run 不得原地续跑。

用户取消：

```http
POST /api/workspaces/ws_demo/analyses/run_research_001/cancel
Idempotency-Key: run_research_001_cancel_01
```

```json
{ "reason": "user_cancelled" }
```

响应返回 `{ "analysisRunId": "run_research_001", "status": "cancelled", "cancelledAt": "..." }`。取消适用于 queued、六个执行阶段和 needs_attention；重复请求返回同一终态。Worker 在下一安全检查点停止，取消后不能发布新报告/导出，已持久化事件与不可变阶段产物保留。`blocked` 是质量门终态，resolution 与 cancel 都不重开它；重做必须创建新 Run。

## 证据溯源与冲突读取 API

证据读取面由 deep research 管线（Task 8）产出，A3 挂载波次（CCR-20260726-MOUNT-01）将其挂入 canonical 契约。全部为只读 `GET`：使用 `require_workspace_context` 鉴权，不涉及 CSRF 或 `Idempotency-Key`；缺失、外部或跨租户 id 一律返回逐字节一致的 `CASE_NOT_FOUND` 404（反枚举）。wire 形状为 camelCase `CanonicalModel` DTO，`evidenceItemId` 是实体自身 id（非 Case/AnalysisRun 别名）。

- `GET /evidence/{evidenceItemId}` → `{ ok, data: EvidenceItemView }`：证据条目全字段（标题、URL/文件指针、来源域、`sourceGrade`、片段、`sourceRecordId`/`sourceSpanIds`、支持/反对 claim id、`freshnessStatus`、`relevance`、`bias`、`conflictGroupId`、`independentSourceGroupId`、`verdict`+`verdictReasonCodes`、`applicabilityLimits`、`originMode`、`rawArtifactId`、`qualityAssessmentId`）。
- `GET /evidence/{evidenceItemId}/quality` → `{ ok, data: QualityDimensionsView }`：七项数值维度（authenticity/sourceQuality/relevance/freshness/applicability/independence/extractionReliability）与 `biasFlags[]`、`completenessWarnings[]`、`conflictGroupIds[]`、`verdict`、`reasonCodes[]`、`assessedAt`。
- `GET /evidence/{evidenceItemId}/provenance` → `{ ok, data: EvidenceProvenanceView }`：`evidenceItemId` + `rawArtifact`（RawArtifactView：kind/mediaType/byteSize/sha256/sourceUrl/originMode/createdAt，不含磁盘路径）+ `sourceRecord`（SourceRecordView 及 `spans[]`）+ `quality`。
- `GET /evidence/{evidenceItemId}/direction` → `{ ok, data: EvidenceDirectionView }`：`evidenceItemId` + `supportsClaimIds[]` + `contradictsClaimIds[]` + `verdict`。
- `GET /evidence/{evidenceItemId}/same-source-group` → `{ ok, data: SameSourceGroupView }`：`independentSourceGroupId` + `memberEvidenceItemIds[]` + `independentSourceCountContribution`（同源多篇引用计为一个独立来源）。
- `GET /analyses/{analysisRunId}/evidence` → `{ ok, data: RunEvidenceListView }`：`analysisRunId` + `items: EvidenceItemView[]`（该 Run 工作区内的证据条目）。
- `GET /analyses/{analysisRunId}/evidence-conflicts` → `{ ok, data: ConflictListView }`：`analysisRunId` + `conflicts: ConflictRelationView[]`（`fromEvidenceItemId`/`toEvidenceItemId`/`groupId`/`rationale`）。

## 决策生命周期事件与不可调用能力

新增 canonical 事件：

```text
case.scope_confirmed
case.readiness_passed
case.lifecycle.transitioned
analysis.run_manifest.frozen
analysis.cynefin_gate.completed
analysis.validator.completed
analysis.deep_result.ready
signoff.requested
signoff.signed
signoff.declined
signoff.expired
decision.record.created
decision.record.superseded
decision.monitoring.activated
report.publication.blocked
```

事件只保存可审计的输入/产物 ID、版本、hash、actor 和 reason code，不保存隐藏推理。`signoff.signed` 与 `decision.record.created` 必须处于同一事务。

公开 API、Agent tool schema 和 MCP catalog 中禁止存在：`sign_decision`、`transition_to_decided`、`update_decision_record`、无 Run 的 `create_report` 或等价能力。安全测试必须枚举工具表并证明这些能力不可达。
