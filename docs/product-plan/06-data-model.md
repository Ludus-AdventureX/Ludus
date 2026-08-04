# 06. 数据模型

## 设计原则

`DecisionCase` 是一次正式决策的聚合根和版本边界，不是所有状态的容器。`DecisionSubjectDossier` 是主体长期事实来源；Case 冻结本次决策使用的档案快照。聊天生成候选条目，分析生成 Run 产物，沙盘生成实验分支；只有用户采纳后才写回 Case 或长期档案，并通过版本和事件保留变化轨迹。

原则：

- 版本化：每次结构化变更生成 `case_versions` 快照。
- 可追溯：判断、建议和因果边都能追到证据、假设或用户偏好。
- 可编辑：AI 生成内容默认是草稿，用户可确认、修改或否决。
- 可降级：即使没有模型或搜索，也能加载预置 `DecisionCase` 作为用户输入，并由 deterministic fixture provider 提供外部响应；Run、质量门、报告、沙盘和决定仍真实执行。

本文件是 P0 唯一 canonical schema。下文标为独立持久化实体的接口都必须把 `workspaceId` 保存为明确列，repository 的读写条件也必须同时带 `workspaceId`；不能只依赖父对象或 URL 推断租户。仅随所属聚合 JSONB/快照一起保存、没有独立 repository 和生命周期的嵌套值对象（例如 `Goal`、`Threshold`、`BriefSection`）可以不重复携带 `workspaceId`，但不得脱离所属 Workspace 聚合单独持久化。

本文件定义领域语义；实现中的唯一 wire schema 是 Contract Lead 维护的 Pydantic 2 模型。FastAPI 导出的 `packages/contracts/openapi.json` 和生成的 `types.gen.ts` 都是只读派生产物。TypeScript 代码块用于说明 canonical 形状，不授权 Web 或其他 Agent 手写平行 DTO；任何字段、状态或可空性变化必须先同步本文件和 `10-api-and-events.md`，通过 CCR 后重新生成。

### Subject identity and aggregate consistency

`DecisionSubject.slug` is a server-generated stable key. The create request does not accept a client-provided slug; the value is returned by subject reads, is unique within a Workspace, and is immutable after creation. Renaming the display `name` must not silently change the slug.

Workspace equality alone is not sufficient for nested decision references. The database and domain service must enforce the following same-Subject rules: an optional `DecisionCase.initiativeId` must reference an Initiative of the Case's `decisionSubjectId`; a case-scoped `DossierEntry` must reference a Case of the same Subject; a Case-bound `Conversation` and its `Message` rows must keep Subject and Case consistent; and a `QuickAnalysisResult.decisionCaseId` must match the Case bound to its Conversation. These checks use composite Workspace + Subject foreign keys/unique keys, and invalid combinations must be rejected before a mutation is committed.

## TypeScript 示例

```ts
export type StatementType =
  | "fact"
  | "evidence"
  | "assumption"
  | "judgment"
  | "preference"
  | "unknown";

export type QualityLevel = "low" | "medium" | "high";
export type QualityScore = number; // 运行时 schema 强制 [0, 1]；表示单维质量，不表示正确概率或成功概率。
export type EntryStatus = "candidate" | "confirmed" | "rejected" | "expired" | "conflicted";
export type GeneratedContentStatus = "draft" | "confirmed" | "rejected";
export type EvidenceVerdict = "accepted" | "conditional" | "lead_only" | "rejected";
export type OriginMode = "live" | "cached" | "fixture";
export type ResponsibilityClass = "human" | "analysis" | "unknown";
export type ActorType = "human_user" | "system_service" | "analysis_worker" | "fixture_provider";
export type DecisionLifecycleStage =
  | "draft"
  | "scoped"
  | "ready"
  | "running"
  | "review"
  | "pending_signoff"
  | "decided"
  | "monitoring";
export type CaseOperationalStatus = "ok" | "blocked" | "needs_attention" | "cancelled" | "reopened" | "archived";

export interface ResponsibilityStamp {
  responsibility: ResponsibilityClass;
  actorType: ActorType;
  actorId?: string;
  sourceAnalysisRunId?: string;
  producerRole?: "research" | "critic" | "synthesis" | "validation";
  createdAt: string;
}

export type WorkspaceRole = "owner" | "member";
export type WorkspaceCapability = "contribute" | "review" | "sign" | "manage_connectors";

export interface User {
  id: string;
  email: string;
  passwordHash: string;
  status: "active" | "disabled";
  createdAt: string;
  updatedAt: string;
}

export interface Workspace {
  id: string;
  name: string;
  status: "active" | "archived";
  createdByUserId: string;
  createdAt: string;
  updatedAt: string;
}

export interface WorkspaceMembership {
  id: string;
  workspaceId: string;
  userId: string;
  role: WorkspaceRole;
  capabilities: WorkspaceCapability[];
  status: "active" | "suspended" | "revoked";
  createdAt: string;
  updatedAt: string;
}

export interface UserSession {
  id: string; // JWT session_id；随机且不可枚举。
  userId: string;
  tokenVersion: number;
  expiresAt: string;
  revokedAt?: string;
  lastSeenAt: string;
  createdAt: string;
}

export interface DecisionMakerProfile {
  id: string;
  workspaceId: string;
  userId: string;
  version: number;
  displayName: string;
  preferenceWeights: Record<string, number>;
  riskTolerance: number;
  createdAt: string;
  updatedAt: string;
}

export interface DecisionSubject {
  id: string;
  workspaceId: string;
  name: string;
  /** Server-generated stable key; unique and immutable within a Workspace. */
  slug: string;
  description?: string;
  dossierId: string;
  status: "active" | "archived";
  createdAt: string;
  updatedAt: string;
}

export interface Initiative {
  id: string;
  workspaceId: string;
  decisionSubjectId: string;
  name: string;
  description?: string;
  status: "active" | "archived";
  createdAt: string;
  updatedAt: string;
}

export interface DecisionSubjectDossier {
  id: string;
  workspaceId: string;
  decisionSubjectId: string;
  currentVersion: number;
  entryIds: string[];
}

export interface DossierVersion {
  id: string;
  workspaceId: string;
  dossierId: string;
  decisionSubjectId: string;
  version: number;
  parentVersion?: number;
  entryIds: string[];
  snapshotHash: string;
  reason: string;
  createdBy: string;
  createdAt: string;
}

export interface DossierEntry {
  id: string;
  workspaceId: string;
  decisionSubjectId: string;
  decisionCaseId?: string;
  scope: "subject" | "case";
  statementType: StatementType | "constraint";
  content: string;
  status: EntryStatus;
  sourceType: "user" | "ai_candidate" | "evidence" | "analysis_candidate" | "simulation_candidate";
  sourceRef?: string;
  version: number;
}

export interface ConversationRevision {
  id: string;
  workspaceId: string;
  conversationId: string;
  messageId: string;
  createdAt: string;
}

export interface CandidateRevision {
  id: string;
  workspaceId: string;
  decisionCaseId?: string;
  sourceType: "conversation" | "analysis" | "simulation";
  sourceId: string;
  baseDossierVersion: number;
  baseCaseVersion?: number;
  proposals: Array<{ operation: "add" | "update" | "reclassify" | "expire"; entry: DossierEntry }>;
  status: "pending" | "partially_accepted" | "accepted" | "rejected";
  reviewedAt?: string;
}

export interface DecisionCase {
  decisionCaseId: string;
  workspaceId: string;
  decisionSubjectId: string;
  initiativeId?: string;
  currentVersion: number;
  title: string;
  decisionQuestion: string;
  inferredDecisionType: "market_direction" | "market_entry" | "technology_route" | "resource_allocation" | "unknown";
  status: DecisionLifecycleStage;
  operationalStatus: CaseOperationalStatus;
  createdAt: string;
  updatedAt: string;
  summary: CaseSummary;
  fiveWOneH: FiveWOneH;
  goals: Goal[];
  constraints: Constraint[];
  stakeholders: Stakeholder[];
  selectedDossierEntryIds: string[];
  caseEntryIds: string[];
  assumptionIds: string[];
  optionIds: string[];
  charterIds: string[];
  analysisRunIds: string[];
  reportArtifactIds: string[];
  causalGraphIds: string[];
  currentDecisionRecordId?: string;
}

export interface CaseVersion {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  version: number;
  parentVersion?: number;
  dossierVersion: number;
  dossierSnapshotHash: string;
  snapshot: DecisionCase;
  snapshotHash: string;
  reason: string;
  createdBy: string;
  createdAt: string;
}

export interface CaseSummary {
  short: string;
  currentRecommendation?: string;
  openQuestions: string[];
  keyAssumptions: string[];
  lastCompressedAt?: string;
}

export interface FiveWOneH {
  why?: string;
  what?: string;
  who?: string[];
  when?: string;
  where?: string;
  how?: string[];
}

export interface Stakeholder {
  id: string;
  name: string;
  role: string;
  influence: "low" | "medium" | "high";
  position?: "support" | "neutral" | "oppose" | "unknown";
}

export interface UnknownItem {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  question: string;
  priority: "low" | "medium" | "high" | "critical";
  acquisitionPlan?: string;
  owner?: string;
  dueAt?: string;
  status: "open" | "resolved" | "accepted";
}

export interface ResearchPacket {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  analysisRunId: string;
  role: "research" | "critic" | "synthesis" | "validation";
  factor?: string;
  frameworkUsed?: string;
  conclusion: string;
  direction?: string;
  claimSupportScore: QualityScore;
  evidenceIds: string[];
  discardedClaims: string[];
  remainingGaps: string[];
  disclaimer?: string;
  createdAt: string;
}

export interface CaseEvent {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  type: string;
  actor: "user" | "system" | "worker";
  payload: Record<string, unknown>;
  createdAt: string;
}
```

## 方法路由与分析契约

```ts
export type AnalysisLevel = "quick" | "focused" | "full";
export type FormalAnalysisLevel = "focused" | "full";
export type MethodMatchStatus = "exact" | "partial" | "unsupported";
export type StrategicLensType =
  | "porter_five_forces"
  | "pre_mortem"
  | "counterparty_response_matrix"
  | "scenario_planning"
  | "meadows_leverage_points";

export const FULL_REQUIRED_STRATEGIC_LENSES: readonly StrategicLensType[] = [
  "porter_five_forces",
  "pre_mortem",
  "counterparty_response_matrix",
  "scenario_planning",
  "meadows_leverage_points",
];

export interface MethodRouteInput {
  workspaceId: string;
  decisionSubjectId: string;
  decisionCaseId: string;
  caseVersion: number;
  caseSnapshotHash: string;
  dossierSnapshotVersion: number;
  dossierSnapshotHash: string;
  decisionQuestion: string;
  goals: string[];
  constraints: string[];
  options: string[];
  unknowns: string[];
  requestedLevel: FormalAnalysisLevel;
}

export interface MethodRecommendation {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  caseVersion: number;
  caseSnapshotHash: string;
  dossierSnapshotVersion: number;
  dossierSnapshotHash: string;
  decisionType: "market_direction" | "market_entry" | "technology_route" | "resource_allocation" | "unknown";
  requestedLevel: FormalAnalysisLevel;
  matchStatus: MethodMatchStatus;
  recommendedMethodId?: string;
  recommendedMethodVersion?: string;
  recommendedMethodContentHash?: string;
  reasons: string[];
  applicabilityLimits: string[];
  missingInputs: string[];
  alternativeMethods: string[];
  formalAnalysisAllowed: boolean;
  routerVersion: string;
  createdAt: string;
}

export interface AnalysisCharter {
  id: string;
  version: number;
  workspaceId: string;
  decisionSubjectId: string;
  decisionCaseId: string;
  caseVersion: number;
  caseSnapshotHash: string;
  status: "draft" | "awaiting_confirmation" | "confirmed" | "superseded";
  analysisLevel: FormalAnalysisLevel;
  decisionQuestion: string;
  deadline?: string;
  goals: Goal[];
  constraints: Constraint[];
  optionIds: string[];
  currentInclination?: string;
  possibleBiases: string[];
  unknownItemIds: string[];
  allowedMaterialIds: string[];
  excludedMaterialIds: string[];
  dossierSnapshotVersion: number;
  dossierSnapshotHash: string;
  decisionMakerProfileId: string;
  decisionMakerProfileVersion: number;
  preferenceSnapshotHash: string;
  preferenceWeights: Record<string, number>;
  analysisDirections: string[];
  requiredStrategicLensTypes: StrategicLensType[];
  methodRecommendationId: string;
  methodId?: string;
  methodVersion?: string;
  methodContentHash?: string;
  methodReasons: string[];
  applicabilityLimits: string[];
  alternativeMethods: string[];
  missingInputs: string[];
  formalAnalysisAllowed: boolean;
  blockingReasons: string[];
  allowedConnectorIds: string[];
  estimatedDurationMinutes: number;
  budget: Record<string, number>;
  replacesCharterId?: string;
  supersededByCharterId?: string;
  createdAt: string;
  confirmedAt?: string;
}

export type AnalysisRunStatus =
  | "queued"
  | "planning"
  | "retrieving"
  | "analyzing"
  | "criticizing"
  | "synthesizing"
  | "validating"
  | "ready"
  | "blocked"
  | "needs_attention"
  | "cancelled";

export interface AnalysisRun {
  analysisRunId: string;
  workspaceId: string;
  decisionCaseId: string;
  charterId: string;
  charterVersion: number;
  runManifestId: string;
  runManifestHash: string;
  cynefinGateResultId: string;
  analysisLevel: FormalAnalysisLevel;
  status: AnalysisRunStatus;
  progress: number;
  originModes: OriginMode[];
  caseVersion: number;
  caseSnapshotHash: string;
  dossierSnapshotVersion: number;
  dossierSnapshotHash: string;
  methodId: string;
  methodVersion: string;
  methodContentHash: string;
  attempt: number;
  maxAttempts: number;
  idempotencyKey: string;
  heartbeatAt?: string;
  stageResults: Record<string, { inputHash: string; outputHash?: string }>;
  strategicLensArtifactIds: string[];
  lastResumableStage?: Exclude<AnalysisRunStatus, "queued" | "ready" | "blocked" | "needs_attention" | "cancelled">;
  interruptionClassificationId?: string;
  supersedesAnalysisRunId?: string;
  supersededByAnalysisRunId?: string;
  cancellationReason?: "user_cancelled" | "charter_replaced" | "operator_cancelled";
  createdAt: string;
  startedAt?: string;
  completedAt?: string;
  cancelledAt?: string;
}

`AnalysisRun.idempotencyKey` 与 `DeepAnalysisRequest.idempotencyKey` 是 canonical **内部**字段（run/worker 生命周期关联），不属于 HTTP wire 请求体；HTTP 面以 `Idempotency-Key` header 为载体，请求体夹带 `idempotencyKey` 字段的请求必须返回 422（CCR-20260725-ANALYSIS-01-ADDENDUM-A1）。

export type CharterFrozenField =
  | "decision_question"
  | "goals"
  | "options"
  | "preference_weights"
  | "hard_constraints"
  | "material_scope"
  | "connector_scope"
  | "budget"
  | "method"
  | "analysis_level"
  | "strategic_lens_set";

export interface RunInterventionClassification {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  analysisRunId: string;
  result: "resolution" | "amendment";
  changedFrozenFields: CharterFrozenField[];
  reasonCodes: string[];
  createdBy: string;
  createdAt: string;
}

export type RunResolutionPayload =
  | {
      kind: "source_conflict";
      conflictGroupId: string;
      selectedEvidenceIds: string[];
      rationale: string;
    }
  | {
      kind: "hard_constraint_confirmation";
      confirmedConstraintIds: string[];
    }
  | {
      kind: "provider_recovery";
      action: "retry" | "use_cached" | "switch_allowed_connector";
      connectorId?: string;
    };

export interface RunResolution {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  analysisRunId: string;
  classificationId: string;
  payload: RunResolutionPayload;
  resumeStage: Exclude<AnalysisRunStatus, "queued" | "ready" | "blocked" | "needs_attention" | "cancelled">;
  createdBy: string;
  createdAt: string;
}

export type AnalysisEventCategory =
  | "agent.status"
  | "agent.task"
  | "tool.call"
  | "citation.added"
  | "user.confirmation.required";

export type AnalysisEventType =
  | "analysis.stage.started"
  | "analysis.stage.progressed"
  | "analysis.stage.completed"
  | "analysis.needs_attention"
  | "analysis.resumed"
  | "analysis.amendment_required"
  | "analysis.cancelled"
  | "analysis.blocked"
  | "analysis.ready"
  | "research.packet.completed"
  | "retrieval.completed"
  | "quality.warning"
  | "strategic_lens.completed"
  | "tool.call.started"
  | "tool.call.completed"
  | "tool.call.failed"
  | "fallback.cached_evidence"
  | "fallback.fixture.loaded"
  | "citation.added"
  | "user.confirmation.required";

export interface AnalysisEvent {
  id: string;
  sequence: number;
  workspaceId: string;
  decisionCaseId: string;
  analysisRunId: string;
  category: AnalysisEventCategory;
  type: AnalysisEventType;
  originMode: OriginMode;
  sourceOriginModes: OriginMode[];
  createdAt: string;
  payload: Record<string, unknown>;
}

export interface QuickAnalysisResult {
  id: string;
  workspaceId: string;
  conversationId: string;
  decisionCaseId?: string;
  formality: "non_formal";
  judgment: string;
  counterArguments: string[];
  keyUnknowns: string[];
  nextActions: string[];
  createdAt: string;
}
```

来源聚合规则：RawArtifact/Evidence/connector call 使用单值 `originMode`；AnalysisRun、StrategicLensArtifact、ReportArtifact、ExportArtifact、CausalGraph、SimulationRun 和 DecisionRecord 使用去重的 `originModes[]`。AnalysisEvent 同时保存直接 `originMode` 与 `sourceOriginModes[]`；聚合展示按 `fixture > cached > live` 取最保守状态，不丢弃混合来源详情。

已确认 Charter 不可更新。冻结字段包括问题、目标、选项、偏好权重、硬约束、允许/禁止材料与连接器范围、预算、方法和分析等级。运行中输入必须先落一条 append-only `RunInterventionClassification`：只有在 `changedFrozenFields` 为空，且输入仅解决已冻结范围内的来源冲突、确认既有硬约束或恢复已获 Charter 授权的 Provider 时，才能创建 `RunResolution` 并从 `lastResumableStage` 恢复。任何冻结字段变化都是 amendment，必须创建 replacement Charter 和新 Run；旧 Run 取消并以 `supersededByAnalysisRunId` 关联新 Run，不得原地续跑。

替代 draft 尚未确认时旧 confirmed Charter 继续有效；新 Charter 确认后才将旧 Charter 标记为 `superseded`。`blocked` 是质量门终态，不能创建 resolution 或恢复；重做必须创建新 Run。`cancelled` 也是终态，Worker 在下一安全检查点停止且不得再发布新产物，已持久化事件与不可变阶段产物保留。`quick` 使用 `QuickAnalysisResult`，不创建 Charter 或正式 Run；`focused` 和 `full` 必须绑定正式方法包 ID、版本和内容哈希。P0 同一 Case 同时最多存在一个活动正式 Run。

合法中断边为 `planning | retrieving | analyzing | criticizing | synthesizing | validating -> needs_attention`；`needs_attention` 只能在成功追加 resolution 后回到该 Run 的 `lastResumableStage`。`queued` 只用于新 Run 等待 Worker 领取，不是恢复目标。queued、六个执行阶段和 needs_attention 可取消；ready、blocked、cancelled 都不得恢复。六个执行阶段严格按 `planning → retrieving → analyzing → criticizing → synthesizing → validating` 线性推进，不得跳步；`ready` 与 `blocked` 只能从 `validating` 进入（CCR-20260725-ANALYSIS-01）。

## 陈述与证据

```ts
export interface RetrievalTask {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  analysisRunId: string;
  stableToolName: "search_web" | "fetch_url" | "crawl_site" | "extract_document" | "get_source_status";
  querySummary: string;
  inputHash: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  createdAt: string;
  completedAt?: string;
}

export interface RawArtifact {
  id: string;
  workspaceId: string;
  decisionCaseId?: string;
  analysisRunId?: string;
  retrievalTaskId?: string;
  connectorCallId?: string;
  kind: "web_page" | "provider_result" | "uploaded_file";
  originalName?: string;
  mediaType: string;
  byteSize: number;
  sha256: string;
  storageProvider: "filesystem";
  storagePath: string;
  sourceUrl?: string;
  originMode: OriginMode;
  createdAt: string;
}

export interface QualityAssessment {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  analysisRunId: string;
  rawArtifactId: string;
  authenticity: QualityScore;
  sourceQuality: QualityScore;
  relevance: QualityScore;
  freshness: QualityScore;
  applicability: QualityScore;
  independence: QualityScore;
  extractionReliability: QualityScore;
  biasFlags: string[];
  completenessWarnings: string[];
  conflictGroupIds: string[];
  verdict: EvidenceVerdict;
  reasonCodes: string[];
  assessedAt: string;
}

export interface Claim {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  analysisRunId?: string;
  statementType: StatementType;
  text: string;
  importance: "core" | "supporting";
  source: "user" | "ai" | "tool" | "imported";
  responsibility: ResponsibilityStamp;
  sourceSpanIds: string[];
  supportingEvidenceIds: string[];
  opposingEvidenceIds: string[];
  assumptionIds: string[];
  supportScore: QualityScore;
  scope: string;
  status: EntryStatus;
  createdAt: string;
  updatedAt: string;
}

export interface EvidenceItem {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  analysisRunId: string;
  title: string;
  url?: string;
  filePath?: string;
  sourceDomain?: string;
  sourceGrade: "L1_primary" | "L2_reputable" | "L3_industry" | "L4_general" | "L5_opinion" | "L6_unverified";
  snippet: string;
  sourceRecordId: string;
  sourceSpanIds: string[];
  supportsClaimIds: string[];
  contradictsClaimIds: string[];
  publishedAt?: string;
  retrievedAt: string;
  freshnessStatus: "fresh" | "aging" | "stale" | "unknown";
  relevance: number;
  bias?: string;
  conflictGroupId?: string;
  verdict: EvidenceVerdict;
  verdictReasonCodes: string[];
  applicabilityLimits: string[];
  originMode: OriginMode;
  rawArtifactId: string;
  qualityAssessmentId: string;
}

export interface ClaimEvidence {
  id: string;
  workspaceId: string;
  claimId: string;
  evidenceId: string;
  direction: "supporting" | "opposing";
  supportStrength: QualityScore;
  rationale: string;
  verdict: EvidenceVerdict;
  createdAt: string;
}
```

来源等级参考 `探讨/skills/research/v6-rag-pool/SKILL.md` 的分级思路。P0 不需要复杂评分模型，但必须保留等级、时间、相关性和冲突信息。

## 假设、选项和偏好

```ts
export interface Assumption {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  text: string;
  dependsOnOptionIds: string[];
  evidenceIds: string[];
  stabilityScore: QualityScore;
  impactIfWrong: "low" | "medium" | "high" | "fatal";
  validationPlan?: string;
  owner?: string;
  dueAt?: string;
  status: EntryStatus;
}

export interface DecisionOption {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  name: string;
  description: string;
  expectedUpside: string;
  keyRisks: string[];
  requiredResources: string[];
  reversible: boolean;
  score?: OptionScore;
}

export interface OptionScore {
  base: number;
  optimistic: number;
  pessimistic: number;
  rationale: string;
  sensitivityDrivers: string[];
}

export interface Goal {
  id: string;
  metric: string;
  target: string;
  weight: number;
}

export interface Constraint {
  id: string;
  text: string;
  hard: boolean;
  owner?: string;
}
```

## 论证树和挑战

```ts
export interface ArgumentNode {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  optionId?: string;
  parentId?: string;
  type: "claim" | "support" | "counter" | "assumption" | "risk";
  text: string;
  evidenceIds: string[];
  assumptionIds: string[];
  supportScore: QualityScore;
  status: GeneratedContentStatus;
}

export interface Challenge {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  analysisRunId: string;
  category: "core_assumption" | "counterargument" | "failure_pattern" | "stakeholder_resistance" | "bias" | "fatal_flaw" | "blind_spot";
  text: string;
  severity: "low" | "medium" | "high" | "critical";
  affectedOptionIds: string[];
  evidenceIds: string[];
  mitigation?: string;
  status: GeneratedContentStatus;
}
```

## 战略透镜产物

五项战略透镜是 `full` AnalysisRun 的独立、不可变阶段产物，不是 `StructuredReport` 内联段落，也不是新的正式 Worker。角色映射固定为：Research 产出 Porter；Critic 产出 Pre-Mortem 与 Counterparty；Synthesis 产出 Scenario 与 Meadows。`quick/focused` 的 `requiredStrategicLensTypes` 必须为空；`full` 必须等于 `FULL_REQUIRED_STRATEGIC_LENSES` 的完整集合。该集合在 Charter 确认时冻结；增删或替换透镜属于 `strategic_lens_set` amendment，必须 replacement Charter + new Run。

```ts
export interface StrategicLensResearchRequest {
  requestId: string;
  question: string;
  evidenceNeed: "primary" | "counterevidence" | "current_market" | "regulatory" | "technical_test" | "procurement" | "stakeholder";
  priority: "medium" | "high" | "critical";
  affectedClaimIds: string[];
}

export interface PorterForceAssessment {
  forceId: "rivalry" | "new_entrants" | "substitutes" | "supplier_power" | "buyer_power";
  threatScore: 1 | 2 | 3 | 4 | 5;
  keyIndicators: string[];
  evidenceIds: string[];
  reasoning: string;
  directionOfChange: "strengthening" | "stable" | "weakening" | "uncertain";
}

export interface PorterMarketAnalysis {
  optionId: string;
  industryBoundary: {
    coreValue: string;
    upstream: string[];
    downstream: string[];
    adjacentMarkets: string[];
    crossIndustrySubstitutes: string[];
    boundaryRisk: string;
  };
  forces: PorterForceAssessment[];
  averageThreatScore: number;
  changingTrend: string;
  regulatoryAssessment: string;
  complementors: string[];
}

export interface PorterFiveForcesContent {
  marketAnalyses: PorterMarketAnalysis[];
  crossMarketComparison: string;
  strategicImplications: Array<{
    optionId: string;
    strategy: "cost_leadership" | "differentiation" | "focus" | "targeted_defense" | "avoid_entry" | "validate_before_entry";
    logic: string;
    conditions: string[];
  }>;
  scoreIsNotDecisionFormula: true;
}

export interface PreMortemFailureCause {
  causeId: string;
  perspective: "internal" | "external" | "systemic_hindsight";
  category: "external" | "internal_execution" | "assumption_failure" | "relationship_or_politics" | "timing" | "systemic_blind_spot";
  cause: string;
  downstreamConsequences: string[];
  likelihoodScore: 1 | 2 | 3 | 4 | 5;
  impactScore: 1 | 2 | 3 | 4 | 5;
  riskScore: number;
  controllability: "controllable" | "partly_controllable" | "uncontrollable";
}

export interface PreMortemContent {
  failureHorizon: string;
  failureStatement: string;
  perspectives: Array<"internal" | "external" | "systemic_hindsight">;
  failureCauses: PreMortemFailureCause[];
  topRisks: Array<{
    rank: 1 | 2 | 3;
    causeId: string;
    prevention: string;
    contingency: string;
    detectionIndicator: string;
  }>;
  verdict: "continue" | "modify" | "abandon" | "validate_first";
  verdictRationale: string;
  additionalInformationNeeded: string[];
}

export interface CounterpartyProfile {
  counterpartyId: string;
  identity: string;
  coreInterest: string;
  responseTools: string[];
  constraints: string[];
}

export interface CounterpartyResponseMatrixContent {
  maxResponseDepth: 1;
  counterparties: CounterpartyProfile[];
  ourActions: Array<{
    actionId: string;
    actionType: "active" | "no_action";
    description: string;
    observability: "low" | "medium" | "high";
    irreversibility: "low" | "medium" | "high";
    coreAssumptionIds: string[];
  }>;
  responseMatrix: Array<{
    counterpartyId: string;
    actionId: string;
    optimalResponse: string;
    worstResponseForUs: string;
    mostLikelyResponse: string;
    responseWindow: string;
    optimalLikelyGap: string;
    ourCounterResponse: string;
    fallbackCost: string;
    strategyInvalidated: boolean;
  }>;
  publicationTest: {
    responseChangesIfPublished: boolean;
    newInformationRevealed: string;
    informationAsymmetryVulnerability: "none" | "low" | "medium" | "high" | "critical";
    mitigation: string;
  };
  downsideAsymmetry: Array<{
    actionId: string;
    worstCase: string;
    downsideFloor: "bounded" | "unbounded" | "unknown";
    exitPath: string;
    exitCost: string;
  }>;
  reflexivityWarning: string;
}

export interface ScenarioEarlyWarningSignal {
  signalId: string;
  type: "qualitative" | "quantitative" | "structural";
  observable: string;
  thresholdOrPattern: string;
  cadence: string;
}

export interface StrategicScenarioFrame {
  scenarioId: string;
  name: string;
  kind: "baseline" | "structural_break";
  axisStates: string[];
  coreLogic: string;
  timeline: Array<{ period: string; turningPoint: string }>;
  stakeholderStates: Array<{ stakeholder: string; state: string }>;
  earlySignals: ScenarioEarlyWarningSignal[];
}

export interface ScenarioPlanningContent {
  focusQuestion: string;
  timeHorizon: string;
  predeterminedElements: string[];
  keyUncertainties: Array<{
    uncertaintyId: string;
    factor: string;
    impact: "medium" | "high";
    uncertainty: "medium" | "high";
    evidenceIds: string[];
  }>;
  axes: Array<{
    axisId: string;
    uncertaintyId: string;
    lowState: string;
    highState: string;
    selectionRationale: string;
  }>;
  scenarios: StrategicScenarioFrame[];
  strategyTests: Array<{
    scenarioId: string;
    optionId: string;
    performance: "robust" | "viable_with_adjustment" | "high_risk" | "killed";
    failureReason: string;
    requiredAdjustment: string;
    triggerSignalIds: string[];
  }>;
  strategyKilledInAtLeastOneScenario: true;
  monitoringActions: string[];
  irreducibleUnknowns: string[];
}

export type MeadowsLevelName =
  | "transcend_paradigms"
  | "paradigm"
  | "goals"
  | "self_organization"
  | "rules"
  | "information_flows"
  | "reinforcing_feedback"
  | "balancing_feedback"
  | "delays"
  | "stock_flow_structure"
  | "buffers"
  | "parameters";

export interface MeadowsLeverageIntervention {
  interventionId: string;
  level: number;
  levelName: MeadowsLevelName;
  strengthBand: "low" | "medium" | "high";
  target: string;
  action: string;
  feasibility: "low" | "medium" | "high";
  expectedEffect: string;
  failureSignal: string;
}

export interface MeadowsLeveragePointsContent {
  systemMap: {
    boundary: string;
    statedGoal: string;
    actualGoal: string;
    stocks: string[];
    flows: string[];
    reinforcingLoops: string[];
    balancingLoops: string[];
    delays: string[];
    actors: string[];
    rulesAndIncentives: string[];
  };
  levelsCovered: number[];
  currentInterventions: MeadowsLeverageIntervention[];
  highLeverageGaps: Array<MeadowsLeverageIntervention & { whyAvoided: string; disruptionRisk: string }>;
  runawayPositiveLoops: Array<{ loop: string; runawaySignal: string; brake: string }>;
  interventionSequence: Array<{
    order: number;
    interventionId: string;
    purpose: "trust_building" | "information_gain" | "system_change" | "risk_control";
    precondition: string;
    failureSignal: string;
  }>;
  riskTradeoffs: string[];
}

export interface StrategicLensArtifactBase {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  analysisRunId: string;
  charterId: string;
  charterVersion: number;
  caseVersion: number;
  caseSnapshotHash: string;
  methodId: string;
  methodVersion: string;
  methodContentHash: string;
  schemaVersion: string;
  sourceSkillVersion: string;
  status: "ready";
  sourcePacketIds: string[];
  claimIds: string[];
  evidenceIds: string[];
  assumptionIds: string[];
  challengeIds: string[];
  researchRequests: StrategicLensResearchRequest[];
  originModes: OriginMode[];
  contentHash: string;
  createdAt: string;
}

export type StrategicLensArtifact =
  | (StrategicLensArtifactBase & {
      lensType: "porter_five_forces";
      producerRole: "research";
      phase: "research_interpretation";
      content: PorterFiveForcesContent;
    })
  | (StrategicLensArtifactBase & {
      lensType: "pre_mortem";
      producerRole: "critic";
      phase: "adversarial_stress";
      content: PreMortemContent;
    })
  | (StrategicLensArtifactBase & {
      lensType: "counterparty_response_matrix";
      producerRole: "critic";
      phase: "adversarial_stress";
      content: CounterpartyResponseMatrixContent;
    })
  | (StrategicLensArtifactBase & {
      lensType: "scenario_planning";
      producerRole: "synthesis";
      phase: "strategic_synthesis";
      content: ScenarioPlanningContent;
    })
  | (StrategicLensArtifactBase & {
      lensType: "meadows_leverage_points";
      producerRole: "synthesis";
      phase: "strategic_synthesis";
      content: MeadowsLeveragePointsContent;
    });

export interface StrategicLensArtifactSummary {
  id: string;
  lensType: StrategicLensType;
  producerRole: "research" | "critic" | "synthesis";
  phase: "research_interpretation" | "adversarial_stress" | "strategic_synthesis";
  status: "ready";
  referenceCounts: {
    sourcePacketCount: number;
    claimCount: number;
    evidenceCount: number;
    assumptionCount: number;
    challengeCount: number;
  };
  charterVersion: number;
  caseVersion: number;
  methodId: string;
  methodVersion: string;
  schemaVersion: string;
  sourceSkillVersion: string;
  contentHash: string;
  originModes: OriginMode[];
  createdAt: string;
}
```

运行时 schema 继续执行 ways 的数量与包含约束：Porter 对至少两个市场选项分别给出完整五力，每力至少两个 evidence、趋势、监管/变化和战略含义，平均分仅作描述而非决策公式；Pre-Mortem 固定 internal/external/systemic_hindsight 三视角、至少 5 个 cause、严格 top 3 的 prevention/contingency/detection，并给出 `continue | modify | abandon | validate_first`；Counterparty 只选 1-2 个关键 actor，定义 2-3 个可观察我方行动且恰好一个 no-action，对每个 actor/action 给出 optimal/worst/likely response、window、我方 counter-response、publication test、downside asymmetry 和 reflexivity；Scenario 分离 predetermined elements 与高影响/高不确定因素，选择两个 axis，形成 3-4 个结构不同情景及 timeline、至少三个 stakeholder state、3-5 个 early warning，逐策略测试 resilience 且至少一个策略在一个情景中为 `killed`；Meadows 必须映射 stocks/flows、reinforcing/balancing loops、delays、rules/incentives，覆盖至少三个层级，识别被忽略的 1-4 高杠杆空缺、至少一个失控强化回路和高杠杆副作用。只满足字段存在而不满足这些行为约束仍为 schema/quality failure。

每个 artifact 的 `workspaceId/decisionCaseId/analysisRunId/charterId` 必须与所属 Run 完全一致；所有引用 ID 必须存在于同一 Workspace/Run 的已持久化对象中。artifact 写入后不可 PATCH 或覆盖；重做只能创建新 Run。数据库对 `(workspaceId, analysisRunId, lensType)` 建唯一约束，幂等重放相同 `contentHash` 返回已有 artifact，不同哈希必须报冲突并阻止报告发布。

## 报告对象

```ts
export interface ReportArtifact {
  id: string;
  workspaceId: string;
  analysisRunId: string; // 非空 FK；没有 qualifying Run 就不能创建 ReportArtifact。
  sourceJudgmentSetId: string;
  sourceDissentRecordId: string;
  decisionCaseId: string;
  caseVersion: number;
  analysisLevel: FormalAnalysisLevel;
  type: "brief" | "detailed";
  status: "draft" | "ready";
  structuredContent: FocusedResearchResult | StructuredReport;
  originModes: OriginMode[];
  exportArtifactIds: string[];
  createdAt: string;
  validation: ReportValidation;
  publishedAt?: string; // 只有 Run ready 且发布 blocker 全部通过时可写入。
}

export interface ExportArtifact {
  id: string;
  workspaceId: string;
  reportArtifactId: string;
  analysisRunId: string;
  decisionCaseId: string;
  caseVersion: number;
  type: "html" | "pdf";
  status: "pending" | "ready" | "failed";
  storageProvider: "filesystem";
  storagePath?: string;
  sha256?: string;
  byteSize?: number;
  mediaType: "text/html" | "application/pdf";
  rendererVersion: string;
  originModes: OriginMode[];
  errorCode?: string;
  createdAt: string;
}

export interface FocusedResearchResult {
  schemaVersion: string;
  methodId: string;
  methodVersion: string;
  methodContentHash: string;
  executiveBrief: BriefSection;
  recommendation: Recommendation;
  evidenceReview: EvidenceReview;
  counterArguments: Challenge[];
  residualUncertainty: UnknownItem[];
  qualityGate: ReportValidation;
  originModes: OriginMode[];
}

export interface StructuredReport {
  schemaVersion: string;
  methodId: string;
  methodVersion: string;
  methodContentHash: string;
  executiveBrief: BriefSection;
  situation: ReportSection;
  sections: ReportSection[];
  options: OptionAnalysis[];
  evidenceReview: EvidenceReview;
  counterArguments: Challenge[];
  recommendation: Recommendation;
  residualUncertainty: UnknownItem[];
  lensArtifactIds: string[];
  simulationSeeds: SimulationSeeds;
  qualityGate: ReportValidation;
  originModes: OriginMode[];
  appendix: ReportSection[];
}

export interface SimulationSeeds {
  candidateNodes: Array<{
    label: string;
    type: CausalNode["type"];
    claimIds: string[];
    evidenceIds: string[];
    assumptionIds: string[];
    rationale: string;
    status: "draft";
    evidenceQualityScore: QualityScore;
  }>;
  candidateEdges: Array<{
    sourceLabel: string;
    targetLabel: string;
    polarity: "positive" | "negative";
    strength: number;
    delaySteps: number;
    claimIds: string[];
    evidenceIds: string[];
    assumptionIds: string[];
    rationale: string;
    status: "draft";
    relationshipQualityScore: QualityScore;
  }>;
}

export type SystemRecommendation =
  | { kind: "option"; optionId: string }
  | { kind: "abstain"; reasonCodes: string[]; rationale: string };

export interface Recommendation {
  outcome: SystemRecommendation;
  alternativeOptionIds: string[];
  summary: string;
  conditions: string[];
  thresholds: Threshold[];
  exitCriteria: string[];
  risks: string[];
  fragileAssumptionIds: string[];
  leadingIndicators: LeadingIndicator[];
  nextActions: ActionItem[];
  reviewDate: string;
  quality: RecommendationQuality;
}

export interface RecommendationQuality {
  evidenceAvailability: "sufficient" | "conditional" | "insufficient" | "blocked";
  claimSupport: "supported" | "conflicted" | "assumption_only" | "unsupported";
  assumptionStability: "stable" | "fragile" | "fatal_unknown";
  causalReliability: "confirmed" | "conditional" | "draft" | "rejected";
  strategicRobustness: "robust" | "scenario_sensitive" | "flip_detected";
  processQuality: "passed" | "warning" | "blocked";
  weakestDimension:
    | "evidence_availability"
    | "claim_support"
    | "assumption_stability"
    | "causal_reliability"
    | "strategic_robustness"
    | "process_quality";
  rationale: string[];
}

export interface BriefSection {
  decision: string;
  whyNow: string;
  conditions: string[];
  thresholds: Threshold[];
  exitCriteria: string[];
  reviewDate: string;
}

export interface ReportSection {
  title: string;
  summary: string;
  claimIds: string[];
  evidenceIds: string[];
}

export interface OptionAnalysis {
  optionId: string;
  summary: string;
  benefits: string[];
  risks: string[];
  score?: OptionScore;
}

export interface EvidenceReview {
  evidenceIds: string[];
  conflictGroupIds: string[];
  freshnessWarnings: string[];
}

export interface ReportValidation {
  passed: boolean;
  errors: string[];
  warnings: string[];
  checkedAt: string;
}
```

判别约束：`analysisLevel == focused` 时 `ReportArtifact.type` 只能为 `brief` 且 `structuredContent` 必须是 `FocusedResearchResult`，不得创建 `StrategicLensArtifact` 或 `ExportArtifact`；`analysisLevel == full` 时 `ReportArtifact.type == detailed` 且内容为 `StructuredReport`，才允许创建 HTML/PDF `ExportArtifact`。服务端按该规则校验，不依赖前端隐藏按钮。

full 报告发布前必须已经持久化五个 `ready` StrategicLensArtifact，类型集合与 Charter 冻结的 `requiredStrategicLensTypes` 完全相等，并固定为 Porter、Pre-Mortem、Counterparty、Scenario、Meadows 各一个。`StructuredReport.lensArtifactIds` 必须恰好引用这五个同 Workspace、同 Case、同 Run、同 Charter/方法快照的 artifact；缺失、重复、跨 Run、跨 Workspace、角色映射错误、引用不存在或内容行为校验失败都会阻断 `AnalysisRun.ready`、正式报告、HTML/PDF 和沙盘。

StrategicLensArtifact 只允许 Worker 通过内部 repository 写入，不提供客户端创建、更新或删除 API。读取合同固定为：

- `GET /api/workspaces/{workspaceId}/analyses/{analysisRunId}/strategic-lenses`：按 canonical lens 顺序返回该 full Run 的 `StrategicLensArtifactSummary[]`；summary 保留 ID/type/producer/phase/status、引用计数、版本、hash、origin 和 createdAt，明确不含 `content` 或 `researchRequests`。
- `GET /api/workspaces/{workspaceId}/analyses/{analysisRunId}/strategic-lenses/{artifactId}`：返回一个完整 `StrategicLensArtifact` 判别联合，包括 resolved reference ID、`researchRequests` 与 lens-specific `content`。

两个读取端点都使用 `10-api-and-events.md` 的统一成功/错误信封；Run/artifact 不属于当前 Workspace、artifact 不属于该 Run 或通过其他 Case 猜测 ID 时统一返回 `404`。ready Report 的读取结果只返回 ID 引用和独立 artifact 读取链接，不把五份内容复制进 `StructuredReport`。

P0 的 `RawArtifact` 与 `ExportArtifact` 锁定 `storageProvider == filesystem`。数据库为这些文件只保存 Workspace-scoped 相对路径、媒体类型、字节数和 SHA-256，不保存 HTML/PDF/上传原件的文件正文；canonical `StructuredReport` 仍作为 `ReportArtifact.structuredContent` 保存。路径必须位于 `workspaces/{workspaceId}/...`，且只能由鉴权后的 API 通过 `workspaceId + artifactId` 解析，不能接受客户端传入磁盘路径。

## 因果图数据结构

```ts
export interface CausalGraph {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  reportArtifactId: string;
  currentGraphVersionId: string;
  title: string;
  originModes: OriginMode[];
  createdAt: string;
  updatedAt: string;
}

export interface GraphVersion {
  id: string;
  workspaceId: string;
  graphId: string;
  decisionCaseId: string;
  caseVersion: number;
  sourceReportArtifactId: string;
  version: number;
  branchId: string;
  parentVersionId?: string;
  sourceGraphVersionId?: string;
  status: "draft" | "confirmed" | "archived";
  provenance: Array<{ objectType: "claim" | "evidence" | "assumption" | "user"; objectId: string }>;
  originModes: OriginMode[];
  title: string;
  nodes: CausalNode[];
  edges: CausalEdge[];
  scenarioVersionIds: string[];
  strategyVersionIds: string[];
  scoreDefinition: ScoreDefinition;
  createdBy: string;
  createdAt: string;
  confirmedAt?: string;
}

export type FactorAuthorship = "generated" | "user_added" | "user_modified";
export type FactorEvidenceStatus = "supported" | "conditional" | "assumed" | "unknown";
export type FactorControllability = "controllable" | "partially_controllable" | "uncontrollable";

export interface CausalNode {
  id: string;
  label: string;
  type: "decision" | "lever" | "constraint" | "external" | "unknown" | "intermediate" | "outcome" | "indicator";
  baseline: number;
  current: number;
  min: number;
  max: number;
  unit?: string;
  controllability: FactorControllability;
  normalization: "linear" | "inverse_linear";
  sensitivityStep?: number; // 业务单位；缺省时使用 (max - min) * 0.1。
  authorship: FactorAuthorship;
  evidenceStatus: FactorEvidenceStatus;
  evidenceQualityScore: QualityScore;
  evidenceIds: string[];
  assumptionIds: string[];
  rationale: string;
  status: GeneratedContentStatus;
  editable: boolean;
}

export interface CausalEdge {
  id: string;
  sourceNodeId: string;
  targetNodeId: string;
  polarity: "positive" | "negative";
  strength: number;
  delaySteps: number;
  authorship: FactorAuthorship;
  evidenceStatus: FactorEvidenceStatus;
  relationshipQualityScore: QualityScore;
  rationale: string;
  claimIds: string[];
  evidenceIds: string[];
  assumptionIds: string[];
  status: GeneratedContentStatus | "conditional";
}

export interface ScenarioVersion {
  id: string;
  workspaceId: string;
  graphId: string;
  decisionCaseId: string;
  sourceLensArtifactId: string;
  sourceStrategicScenarioId: string;
  scenarioId: string;
  version: number;
  name: string;
  description: string;
  defaultEdgeMultiplier: number;
  edgeMultipliers: Record<string, number>;
  nodeShifts: Record<string, number>; // 引擎归一化 delta，schema 强制 [-1, 1]。
  strategySurvives: boolean;
  earlyWarningSignals: ScenarioEarlyWarningSignal[];
  damping: number;
  createdAt: string;
}

export interface StrategyVersion {
  id: string;
  workspaceId: string;
  graphId: string;
  decisionCaseId: string;
  version: number;
  optionId: string;
  nodeOverrides: Record<string, number>;
  enabledEdgeIds: string[];
}

export interface OptionOutcomeMapping {
  optionId: string;
  outcomeNodeId: string;
  goalId: string;
  weight: number;
}

export interface RiskWeight {
  optionId: string;
  riskNodeId: string;
  weight: number;
}

export interface ConstraintRule {
  optionId: string;
  constraintNodeId: string;
  operator: ">" | ">=" | "<" | "<=" | "=";
  threshold: number;
  penalty: number;
}

export interface ScoreDefinition {
  id: string;
  workspaceId: string;
  graphId: string;
  decisionCaseId: string;
  version: string;
  optionOutcomeMappings: OptionOutcomeMapping[];
  riskWeights: RiskWeight[];
  constraintRules: ConstraintRule[];
}

export interface GraphBranch {
  id: string;
  workspaceId: string;
  graphId: string;
  name: string;
  baseGraphVersionId: string;
  headGraphVersionId: string;
  status: "active" | "archived";
}

export interface GraphWorkingCopy {
  id: string;
  workspaceId: string;
  graphId: string;
  decisionCaseId: string;
  branchId: string;
  baseGraphVersionId: string;
  revision: number;
  nodes: CausalNode[];
  edges: CausalEdge[];
  status: "active" | "saved" | "discarded";
  updatedBy: string;
  createdAt: string;
  updatedAt: string;
}

export interface FactorCandidate {
  id: string;
  workspaceId: string;
  graphId: string;
  workingCopyId: string;
  sourceText: string;
  proposedNode: Omit<CausalNode, "id" | "status"> & { status: "draft" };
  suggestedRelationships: RelationshipCandidate[];
  status: "pending_review" | "accepted" | "modified" | "rejected";
  createdAt: string;
  reviewedAt?: string;
}

export interface RelationshipCandidate {
  id: string;
  sourceNodeRef: string;
  targetNodeRef: string;
  proposedEdge: Omit<CausalEdge, "id" | "status"> & { status: "draft" };
  status: "pending_review" | "accepted" | "modified" | "rejected";
}

export interface ExperimentPreview {
  id: string;
  workspaceId: string;
  graphId: string;
  workingCopyId: string;
  workingCopyRevision: number;
  baseGraphVersionId: string;
  strategyVersionId: string;
  scenarioVersionId: string;
  scoreDefinitionId: string;
  scoreDefinitionVersion: string;
  decisionMakerProfileId: string;
  decisionMakerProfileVersion: number;
  riskTolerance: number;
  engineVersion: string;
  epsilon: number;
  maxSteps: number;
  inputHash: string;
  simulationMode: "experimental_preview";
  nodeResults: Record<string, number>;
  optionScores: Array<{ optionId: string; score: number }>;
  topDrivers: Array<{ nodeId: string; scoreDelta: number }>;
  recommendationShift: string;
  warnings: string[];
  convergenceStatus: "converged" | "max_steps" | "saturated" | "invalid";
  stale: boolean;
  createdAt: string;
}

export interface SimulationRun {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  graphId: string;
  graphVersionId: string;
  strategyVersionId: string;
  scenarioVersionId: string;
  scoreDefinitionId: string;
  scoreDefinitionVersion: string;
  decisionMakerProfileId: string;
  decisionMakerProfileVersion: number;
  riskTolerance: number;
  engineVersion: string;
  scenarioId: string;
  simulationMode: "formal" | "experimental";
  epsilon: number;
  maxSteps: number;
  steps: number;
  inputHash: string;
  nodeResults: Record<string, number>;
  optionScores: Array<{ optionId: string; score: number }>;
  topDrivers: Array<{ nodeId: string; scoreDelta: number }>;
  recommendationShift: string;
  convergenceStatus: "converged" | "max_steps" | "saturated" | "invalid";
  originModes: OriginMode[];
  createdAt: string;
}
```

`ScenarioVersion` 是用户审阅并接受某个 ready `scenario_planning` artifact 中 `StrategicScenarioFrame` 后生成的沙盘投影，不是 `StrategicLensArtifact` 本身。`sourceLensArtifactId/sourceStrategicScenarioId` 必须解析到同 Workspace、Case 和来源 Report/Run；创建时复制并冻结 external/unknown 假设、`strategySurvives` 与 early warning，不在后续 lens 变化时覆写。Scenario 只描述外部世界状态；决策人风险偏好继续冻结在 `DecisionMakerProfile/AnalysisCharter.preferenceWeights`，风险评分使用 `ScoreDefinition.RiskWeight`，不得进入 ScenarioVersion。Strategy 的主动选择继续由 `StrategyVersion` 表达。

`from-report` 只能创建 `draft` `GraphVersion`。图批量审阅必须对每个自动节点和每条自动边提交 `confirm | modify | reject`，修改后的对象仍需在同一请求中明确确认；所有参与传播的节点必须为 `confirmed`。审阅成功创建新的不可变 `confirmed` `GraphVersion`，原 draft 保留。正式模拟只接受 confirmed GraphVersion，并且引擎只传播其中 `confirmed | conditional` 边；draft GraphVersion 只能用于 `experimental` 模拟，其结果不得进入 PDF 或最终决定的系统建议。
用户在完整模型中新增因素时，客户端只能先创建 `FactorCandidate`。候选节点和候选关系不得直接写入 `GraphVersion`；用户必须逐项确认、修改或否决，接受后的对象才写入带乐观锁 `revision` 的 `GraphWorkingCopy`，且状态仍为 `draft`。用户不得通过该入口创建 `decision` 节点；决策选项必须继续来自正式 Case/Strategy 合同。缺少可追溯证据的新因素必须使用 `evidenceStatus == assumed | unknown`，并保留假设或理由，禁止以 `supported` 呈现。

`ExperimentPreview` 是基于某一工作副本修订生成的短生命周期实验结果，不是 `SimulationRun`，不得被 DecisionRecord、PDF、正式推荐或审计导出引用。任何后续工作副本修改都会使旧预览 `stale == true`。要获得正式结果，用户必须先把工作副本保存为新的不可变 `GraphVersion`，完成所需审阅并确认该版本，再主动创建 `formal` `SimulationRun`。

## 推演议会（CCR-20260804-DELIB-01）

推演议会是因子沙盘之上的长程推演层：每个因子一个持证人智能体，主持智能体组织轮次，用户可介入；一切数值由确定性引擎 `simulate()` 计算。议会对象属于沙盘域，不属于 AnalysisRun 状态机。

```ts
export type DeliberationRunStatus = "preparing" | "running" | "awaiting_user" | "complete" | "cancelled";

export interface DeliberationRun {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  status: DeliberationRunStatus;
  currentRoundSeq: number;
  maxRounds: number;              // 硬上限 5；超限即推进 verdict 并诚实注记
  factorSnapshotHash: string;     // 创建时刻因子基线冻结哈希
  originModes: OriginMode[];
  createdAt: string;
  updatedAt: string;
}

export interface DeliberationFactor {
  id: string;
  workspaceId: string;
  deliberationRunId: string;
  provenance: "objective" | "subjective";
  label: string;
  strength: number;               // 0-1；只能由用户介入或已采纳提议改变
  sourceFactorId?: string;        // objective 必填：引用 factor sandbox 基线因子
  statement?: string;             // subjective 必填：声明文本
  authorUserId?: string;          // subjective 必填：Human 署名（ResponsibilityStamp）
  dossierAssumptionId?: string;   // subjective 可选：引用档案假设
  evidenceStatus: "assumed" | "unknown"; // subjective 永不 supported/conditional
}

export interface DeliberationRound {
  id: string;
  deliberationRunId: string;
  seq: number;                    // run 内严格单调
  kind: "opening" | "challenge" | "verdict";
  status: "active" | "complete";
  startedAt: string;
  endedAt?: string;
}

export interface DeliberationMessage {
  id: string;
  workspaceId: string;
  deliberationRunId: string;
  roundId: string;
  speaker: "witness" | "moderator" | "user";
  speakerFactorId?: string;       // witness 必填
  kind: "statement" | "challenge" | "rebuttal" | "proposal" | "intervention" | "nomination" | "verdict_summary";
  content: string;
  structuredPayload?: Record<string, unknown>; // 经 schema 校验；禁止自报数值结果
  stamp: ResponsibilityStamp;     // Human/Analysis/Unknown（§7）
  originMode: OriginMode;
  sourceOriginModes: OriginMode[];
  createdAt: string;
}

export interface DeliberationProposal {
  id: string;
  workspaceId: string;
  deliberationRunId: string;
  proposerFactorId: string;
  kind: "factor_strength" | "edge_validity" | "new_factor";
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  status: "pending" | "accepted" | "rejected"; // 只有用户可决策
  enginePreview?: FactorSandboxState;          // simulate() 预览，非模型输出
  decidedAt?: string;
}

export interface DeliberationNomination {
  id: string;
  workspaceId: string;
  deliberationRunId: string;
  rationale: string;              // 主持基于 topDrivers/证据薄弱因子的提名理由
  targetDescription: string;
  status: "pending" | "confirmed" | "rejected"; // 永不自动生效
  confirmedFactorId?: string;     // confirmed 后才存在
}

export interface DeliberationOutcome {
  id: string;
  workspaceId: string;
  deliberationRunId: string;      // 一个 run 至多一条；verdict 轮产出，留档 append-only
  conditionProjections: ConditionProjection[]; // 每项 = 采纳提议集 + simulate() 投影 + 条件描述
  flipConditions: FlipCondition[];             // 引擎 topDrivers/flipValue 派生
  dissentLog: DissentEntry[];                  // 立场被推翻的持证人留档
  assumptionLedger: AssumptionLedgerEntry[];   // 全部因子 provenance/evidenceStatus/最终强度
  disclaimer: string;             // 固定文案：沙盘与议会不代表精确预测
  createdAt: string;
}

export interface ConditionProjection {
  acceptedProposalIds: string[];
  projection: { outcomeScore: number; verdict: "proceed" | "hold"; flipThreshold: number };
  condition: string;              // 条件描述；禁止概率化断言
}

export interface DeliberationEvent {
  id: string;
  sequence: number;               // 单个 deliberationRunId 流内严格单调
  workspaceId: string;
  decisionCaseId: string;
  deliberationRunId: string;
  category: "deliberation.round" | "deliberation.message" | "deliberation.proposal" | "deliberation.nomination" | "deliberation.outcome";
  type: string;
  originMode: OriginMode;
  sourceOriginModes: OriginMode[];
  createdAt: string;
  payload: Record<string, unknown>;
}
```

不变量：`DeliberationFactor` 的 subjective 条目必须以 `assumed | unknown` + Human 署名进图，禁止冒充 `supported`；`DeliberationNomination` 在 `confirmed` 前不得产生任何因子或数值效果；`DeliberationProposal` 的 `enginePreview` 与一切投影数值只能来自 `simulate()`，智能体输出不得自报数值；`DeliberationOutcome` 与事件 payload 不得携带“成功概率/结论正确概率”或任何 0-1 概率化断言；跨 Workspace 访问统一 `CASE_NOT_FOUND` 404。

## 决策记录

```ts
export interface DecisionRecord {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  caseVersion: number;
  recordKind: "original" | "revision";
  supersedesDecisionRecordId?: string;
  signoffRequestId: string;
  payload: SignoffPayload; // 签署时原样复制的 canonical value object；是决定内容的事实源。
  payloadHash: string;
  sourceAnalysisRunId: string; // 下列字段是 payload 的不可变索引投影，必须逐字段相等。
  sourceReportArtifactId: string;
  sourceJudgmentSetId: string;
  sourceDissentRecordId: string;
  sourceCausalGraphId?: string;
  sourceCausalGraphVersionId?: string;
  sourceSimulationRunId?: string;
  originModes: OriginMode[];
  systemRecommendation: SystemRecommendation;
  selectedOptionId: string;
  decisionText: string;
  conditions: string[];
  thresholds: Threshold[];
  exitCriteria: string[];
  actionItems: ActionItem[];
  leadingIndicators: LeadingIndicator[];
  acceptedUnknownIds: string[];
  reviewDate: string;
  signedByUserId: string;
  signedAt: string;
  signatureStatement: string;
  signatureHash: string;
  recordHash: string;
}

`DecisionRecord.payload` 是签署内容的 canonical 副本；`payloadHash` 必须等于 SignoffRequest 的哈希。其余来源、建议、选择、条件、阈值、行动、Unknown 与复盘字段仅作为不可变索引/读取投影，服务端必须从 `payload` 生成并逐字段校验，禁止客户端独立提交或数据库独立更新。`payload.caseVersion` 表示请求签署时冻结的 Case 版本；顶层 `caseVersion` 表示完成签署状态转换后的记录版本。

export interface Review {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  decisionRecordId: string;
  sourceCaseVersion: number;
  sourceAnalysisRunId: string;
  sourceCausalGraphVersionId?: string;
  sourceSimulationRunId?: string;
  reviewDate: string;
  outcome: "on_track" | "adjust" | "reverse" | "close";
  recommendationAdoption: "adopted" | "partially_adopted" | "not_adopted";
  executionAssessment: "as_planned" | "minor_deviation" | "major_deviation" | "not_executed";
  decisionProcessAssessment: "sound" | "mixed" | "flawed";
  outcomeQuality: "positive" | "mixed" | "negative" | "not_yet_observable";
  observedIndicatorValues: Record<string, string>;
  thresholdBreaches: string[];
  externalChanges: string[];
  actualOutcomes: string[];
  assumptionResults: AssumptionResult[];
  lessons: string[];
  nextDecisionChanges: string[];
  notes: string;
  nextReviewDate?: string;
  createdBy: string;
  createdAt: string;
}

export interface AssumptionResult {
  assumptionId: string;
  status: "supported" | "weakened" | "falsified" | "unknown";
  observation: string;
}

export interface ActionItem {
  id: string;
  text: string;
  owner: string;
  dueAt: string;
  status: "open" | "done" | "blocked";
}

export interface LeadingIndicator {
  id: string;
  metric: string;
  expectedDirection: "up" | "down" | "stable";
  threshold: string;
  checkCadence: string;
}

export interface Threshold {
  metric: string;
  operator: ">" | ">=" | "<" | "<=" | "=";
  value: string;
  actionIfMissed: string;
}
```

## 版本模型

`case_versions` 保存完整快照或压缩快照：

```json
{
  "id": "ver_004",
  "workspaceId": "ws_demo",
  "decisionCaseId": "case_spherical_robot",
  "version": 4,
  "reason": "analysis_candidates_accepted",
  "createdBy": "user_demo",
  "createdAt": "2026-07-10T14:20:00+08:00",
  "parentVersion": 3,
  "snapshotHash": "sha256:...",
  "summary": "用户采纳报告候选更新，将条件化建议和 2 个关键未知项写入 Case"
}
```

版本规则：

- 用户编辑结构化内容：新版本。
- 任务输出被用户接受：新版本。
- 任务中间事件：只写事件，不提升版本。
- 沙盘试算：写 `simulation_run`；用户明确采纳候选更新并完成确认后才提升档案版本。
- 最终决定：必须提升版本并冻结当时报告与沙盘引用。

## 数据库索引

建议索引：

- `users(email)` 唯一；规范化 email 写入独立列。
- `workspace_memberships(workspaceId, userId)` 唯一，并索引 `(userId, status)` 与 `(workspaceId, status)`。
- `user_sessions(id)` 唯一，并索引 `(userId, revokedAt, expiresAt)`；已撤销或过期 session 不得通过认证。
- `decision_cases(workspaceId, status, updatedAt)`；wire/domain 主键名为 `decisionCaseId`，数据库列为 `decision_case_id`。
- `case_versions(decisionCaseId, version)` 唯一。
- `dossier_versions(workspaceId, dossierId, version)` 唯一。
- `domain_events(workspaceId, aggregateType, aggregateId, createdAt)`。
- `evidence_items(decisionCaseId, sourceGrade, freshnessStatus)`。
- `analysis_charters(workspaceId, decisionCaseId, status, createdAt)`。
- `analysis_runs(workspaceId, decisionCaseId, status, heartbeatAt, createdAt)`；对活动状态建立每个 Case 至多一条的部分唯一约束。
- `analysis_events(analysisRunId, sequence)` 唯一，`id` 全局唯一并用于 SSE `Last-Event-ID` 恢复。
- `report_artifacts(decisionCaseId, caseVersion, type)`。
- `strategic_lens_artifacts(workspaceId, analysisRunId, lensType)` 唯一；同时索引 `(workspaceId, decisionCaseId, createdAt)`，内容与 provenance 使用 JSONB/明确外键保存，写入后不可更新。
- `export_artifacts(reportArtifactId, type, status)`。
- `causal_graphs(workspaceId, decisionCaseId, reportArtifactId)`。
- `graph_versions(workspaceId, graphId, version)` 唯一；`scenario_versions(workspaceId, graphId, scenarioId, version)` 唯一。
- `run_resolutions(workspaceId, analysisRunId, createdAt)`；resolution 与 classification 只追加、不覆盖。
- `signoff_requests(workspaceId, decisionCaseId, status, expiresAt)`；`payloadHash` 唯一性由 `(workspaceId, decisionCaseId, payloadHash, status)` 的业务约束与幂等键共同保护。
- `decision_records(workspaceId, decisionCaseId, signedAt)`；数据库策略拒绝 UPDATE/DELETE。
- `reviews(workspaceId, decisionRecordId, createdAt)`。
- `connectors(workspaceId, provider, enabled)`。
- `connector_calls(workspaceId, connectorId, createdAt)`。

Postgres P0 使用 JSONB 保存低频变化的复杂对象，并将 Workspace、状态、版本、外键和高频检索字段拆成明确列与索引。SQLite 仅可用于隔离的单元测试或显式离线 fixture，不作为正式迁移起点。

## 连接器模型

```ts
export interface Connector {
  id: string;
  workspaceId: string;
  provider: "exa" | "firecrawl" | "tavily" | "user_file" | "fixture";
  displayName: string;
  enabled: boolean;
  readOnly: true;
  secretRef?: string;
  allowedTools: Array<"search_web" | "fetch_url" | "crawl_site" | "extract_document">;
  allowedDomains: string[];
  budget: {
    maxCallsPerRun: number;
    maxResultsPerCall: number;
    maxCrawlPages: number;
  };
  status: "available" | "missing_credentials" | "invalid_credentials" | "rate_limited" | "quota_exhausted" | "provider_error" | "disabled";
  createdAt: string;
  updatedAt: string;
}

export interface ConnectorCall {
  id: string;
  workspaceId: string;
  userId: string;
  connectorId: string;
  decisionCaseId?: string;
  analysisRunId?: string;
  retrievalTaskId?: string;
  stableToolName: "search_web" | "fetch_url" | "crawl_site" | "extract_document" | "get_source_status";
  provider: Connector["provider"];
  requestSummary: string;
  quotaConsumed: number;
  resultHash?: string;
  errorCode?: string;
  fallbackConnectorId?: string;
  originMode: OriginMode;
  startedAt: string;
  completedAt?: string;
}
```

`secretRef` 只引用服务端加密存储，不保存明文 Key。连接器响应只返回掩码和状态。`connector_calls` 保存 Workspace、用户、AnalysisRun、稳定工具名、供应商、请求摘要、耗用额度、结果哈希、错误码和 fallback，不保存完整密钥或不必要的原始敏感正文。

## 决策操作系统工程合同增量（CCR-20260719-002 / CCR-20260721-003）

本节与上文接口共同构成 canonical schema。实现不得只把 Human / Analysis / Unknown 做成视觉颜色；责任类型、actor、来源、转换和签署必须在 Pydantic、数据库、领域服务和测试中一致。

```ts
export type SourceKind = "web_page" | "provider_result" | "uploaded_file" | "human_input" | "case_snapshot";
export type SourceScope = "pre_run" | "run_frozen";

export interface SourceRecordBase {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  kind: SourceKind;
  canonicalUri: string;
  title: string;
  contentHash: string;
  sourceVersion: string;
  originMode: OriginMode;
  rawArtifactId?: string; // 只有真实经过 RawArtifact 的来源才存在。
  createdAt: string;
}

export interface PreRunSourceRecord extends SourceRecordBase {
  sourceScope: "pre_run";
  analysisRunId?: never;
}

export interface RunFrozenSourceRecord extends SourceRecordBase {
  sourceScope: "run_frozen";
  analysisRunId: string;
  frozenFromSourceRecordId: string;
  frozenAt: string;
}

export type SourceRecord = PreRunSourceRecord | RunFrozenSourceRecord;

export interface SourceSpanLocator {
  pageNumber?: number;
  paragraphIndex?: number;
  charStart?: number;
  charEnd?: number;
  sheetName?: string;
  rowStart?: number;
  rowEnd?: number;
  columnStart?: number;
  columnEnd?: number;
  caseFieldPath?: string;
  messageId?: string;
}

export interface SourceSpanBase {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  sourceRecordId: string;
  locator: SourceSpanLocator;
  quote: string;
  quoteHash: string;
  contextBefore?: string;
  contextAfter?: string;
  createdAt: string;
}

export interface PreRunSourceSpan extends SourceSpanBase {
  sourceScope: "pre_run";
  analysisRunId?: never;
}

export interface RunFrozenSourceSpan extends SourceSpanBase {
  sourceScope: "run_frozen";
  analysisRunId: string;
  frozenFromSourceSpanId: string;
}

export type SourceSpan = PreRunSourceSpan | RunFrozenSourceSpan;

export type CynefinDomain = "clear" | "complicated" | "complex" | "chaotic" | "disorder";

export interface CynefinGateResult {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  charterId: string;
  domain: CynefinDomain;
  recommendedAnalysisLevel: AnalysisLevel;
  formalAnalysisAllowed: boolean;
  rationaleCodes: string[];
  safeToFailProbes: string[];
  reviewTriggers: string[];
  overrideRequired: boolean;
  overriddenByUserId?: string;
  overrideReason?: string;
  createdAt: string;
}

export interface RunManifest {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  charterId: string;
  charterVersion: number;
  caseVersion: number;
  caseSnapshotHash: string;
  dossierSnapshotVersion: number;
  dossierSnapshotHash: string;
  materialSnapshotHash: string;
  sourceRecordIds: string[];
  sourceContentHashes: string[];
  methodId: string;
  methodVersion: string;
  methodContentHash: string;
  analysisLevel: FormalAnalysisLevel;
  cynefinGateResultId: string;
  cynefinGateResultHash: string;
  allowedTools: string[];
  allowedConnectorIds: string[];
  budget: Record<string, number>;
  idempotencyKey: string;
  manifestHash: string;
  createdAt: string;
}

export interface Judgment {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  analysisRunId: string;
  text: string;
  judgmentType: "comparative_assessment" | "conditional_conclusion" | "risk_assessment" | "recommendation_basis";
  optionIds: string[];
  supportingClaimIds: string[];
  opposingClaimIds: string[];
  unknownItemIds: string[];
  challengeIds: string[];
  conditions: string[];
  responsibility: ResponsibilityStamp;
  validationStatus: "draft" | "accepted" | "blocked";
  contentHash: string;
  createdAt: string;
}

export interface JudgmentSet {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  analysisRunId: string;
  judgmentIds: string[];
  unresolvedUnknownIds: string[];
  contentHash: string;
  createdAt: string;
}

export interface DissentRecord {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  analysisRunId: string;
  challengeIds: string[];
  minorityJudgmentIds: string[];
  unresolvedDisagreements: string[];
  falsificationConditions: string[];
  synthesisDisposition: { item: string; disposition: "accepted" | "mitigated" | "unresolved" | "rejected"; reason: string }[];
  contentHash: string;
  createdAt: string;
}

export interface DraftRecommendation {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  analysisRunId: string;
  judgmentSetId: string;
  dissentRecordId: string;
  outcome: SystemRecommendation;
  conditions: string[];
  thresholds: Threshold[];
  exitCriteria: string[];
  leadingIndicators: LeadingIndicator[];
  responsibility: ResponsibilityStamp; // 必须是 analysis。
  contentHash: string;
  createdAt: string;
}

export interface SignoffPayload {
  caseVersion: number;
  sourceAnalysisRunId: string;
  sourceReportArtifactId: string;
  sourceJudgmentSetId: string;
  sourceDissentRecordId: string;
  sourceCausalGraphId?: string;
  sourceCausalGraphVersionId?: string;
  sourceSimulationRunId?: string;
  systemRecommendation: SystemRecommendation;
  selectedOptionId: string;
  decisionDraft: string;
  conditions: string[];
  thresholds: Threshold[];
  exitCriteria: string[];
  actionItems: ActionItem[];
  leadingIndicators: LeadingIndicator[];
  acceptedUnknownIds: string[];
  reviewDate: string;
}

export interface SignoffRequest {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  requestedByUserId: string;
  payload: SignoffPayload; // 不可变 JSONB/value object；签署后原样复制到 DecisionRecord。
  payloadHash: string;
  status: "pending" | "signed" | "declined" | "cancelled" | "expired";
  nonceHash: string;
  nonceIssuedAt: string;
  expiresAt: string;
  createdAt: string;
  signedAt?: string;
}

export interface DecisionLifecycleEvent {
  id: string;
  workspaceId: string;
  decisionCaseId: string;
  fromStage: DecisionLifecycleStage;
  toStage: DecisionLifecycleStage;
  actorType: ActorType;
  actorId?: string;
  commandType: string;
  commandId: string;
  payloadHash: string;
  createdAt: string;
}

export interface ValidatorResult {
  validatorId: "V1_scope_charter" | "V2_source_traceability" | "V3_evidence_quality" | "V4_claim_evidence_entailment" | "V5_contradiction_alignment" | "V6_unknown_assumption" | "V7_adversarial_dissent" | "V8_causal_simulation" | "V9_publication_authority";
  validatorVersion: string;
  outcome: "pass" | "warn" | "block";
  findings: { code: string; message: string; artifactIds: string[] }[];
  repairTarget?: string;
  executionMode: "deterministic" | "model_assisted" | "hybrid";
  modelInvocationRef?: string;
}

export interface MethodVersionRef {
  id: string;
  version: string;
  contentHash: string;
}

export interface DeepAnalysisRequest {
  workspaceId: string;
  decisionCaseId: string;
  analysisRunId: string;
  charterId: string;
  charterVersion: number;
  caseSnapshotHash: string;
  dossierSnapshotHash: string;
  materialSnapshotHash: string;
  analysisDepth: FormalAnalysisLevel;
  method: MethodVersionRef;
  budget: Record<string, number>;
  allowedTools: string[];
  allowedConnectorIds: string[];
  idempotencyKey: string;
}

export interface DeepAnalysisResult {
  analysisRunId: string;
  runManifestId: string;
  runManifestHash: string;
  judgmentSetId: string;
  dissentRecordId: string;
  draftRecommendationId: string;
  unresolvedUnknownIds: string[];
  validatorResults: ValidatorResult[];
  qualityGateResultId: string;
  provenanceHash: string;
}
```

强制约束：

1. 新写入的 Claim 必须至少有一个合法 `sourceSpanId`；Run 前用户输入先规范化为 `pre_run human_input` SourceRecord/SourceSpan，创建 Run 时再冻结为新的 `run_frozen` 记录。
2. `SourceSpan.quoteHash` 必须与对应 source scope 的内容匹配；`run_frozen` span 还必须保存原 pre-run span 引用，不得只保存无法校验的展示 snippet。
3. `Judgment`、`JudgmentSet`、`DissentRecord` 和 `DraftRecommendation` 都是 Run-scoped analysis 产物，写入后按内容哈希不可变。
4. `DecisionRecord` 插入后禁止 UPDATE/DELETE；修订必须创建新记录并填写 `supersedesDecisionRecordId`。
5. `SignoffRequest` 只有活动 UserSession、WorkspaceMembership 和 `sign` capability 同时成立的授权人类可签署；签署服务从会话解析用户身份，客户端不得自报签署人。`payloadHash` 必须覆盖完整 SignoffPayload。
6. `ReportArtifact` 必须有同 Workspace/Case 的 qualifying Run；`ready` 还要求 Run ready、V9 publication validator pass 且全部 blocker 清零。
7. `DeepAnalysisRequest` 是正式 Agent Engine 输入，不得添加 chat `messages[]` 作为主合同；`DeepAnalysisResult` 只返回已持久化 artifact ID/hash，不内嵌第二套领域 DTO。
8. `SystemRecommendation.kind == "abstain"` 时不得填写伪造 option ID；DecisionRecord 必须保留 abstain 原因，即使人类最终选择合法 option。
9. `SimulationRun.inputHash` 必须覆盖图、策略、情景、评分、偏好、riskTolerance、epsilon、maxSteps 和 engineVersion。
