// Task 13 sandbox domain types (decision-user-first stress testing).
// Everything here is expressed in BUSINESS language: business values, units,
// evidence status, controllability. Engine internals (normalized values,
// damping, edge multipliers, score formulas, success probabilities) must
// never appear in these types, in rendered copy or in run requests.

export type EvidenceStatus = "confirmed" | "conditional" | "assumed" | "unknown";

export type Controllability = "controllable" | "partially_controllable" | "external";

export type NodeKind =
  | "lever"
  | "external"
  | "constraint"
  | "unknown"
  | "intermediate"
  | "indicator"
  | "outcome"
  | "decision";

export type ConfirmationStatus = "confirmed" | "pending";

/** 当前条件化建议（来源：正式报告版本，只读消费，不在沙盘内改写）。 */
export type SandboxRecommendation = {
  headline: string;
  optionId: string;
  optionLabel: string;
  conditions: string[];
  sourceReportVersion: string;
  /** 非预测限制说明（沙盘暴露失效处，不预测未来）。 */
  scopeNote: string;
};

/** 最脆弱条件（UI 只显示前三项）。 */
export type FragileCondition = {
  /** 图节点 id，同时是 run 请求 nodeOverrides 的 key。 */
  nodeId: string;
  title: string;
  /** 业务单位（如「个月」「万元」）。 */
  unit: string;
  baselineValue: number;
  min: number;
  max: number;
  step: number;
  controllability: Controllability;
  evidenceStatus: EvidenceStatus;
  /** 一句影响说明。 */
  impactNote: string;
  /** 业务归属（如「现金窗口」）。 */
  businessDomain: string;
};

export type SandboxGraphNode = {
  id: string;
  kind: NodeKind;
  title: string;
  businessValue: string;
  baseline: string;
  range: string;
  source: string;
  confirmation: ConfirmationStatus;
  /** 适用限制。 */
  applicability?: string;
};

export type RelationQuality = "evidence" | "human_constraint" | "assumed";

export type SandboxGraphEdge = {
  id: string;
  from: string;
  to: string;
  relationQuality: RelationQuality;
  impactStrength: "strong" | "moderate" | "weak";
  /** 文字化路径动词（如「拉长」「压缩」）。 */
  verb: string;
  source: string;
  confirmation: ConfirmationStatus;
  /** 审阅优先级信号：改变推荐 / 触发硬约束。 */
  wouldChangeRecommendation?: boolean;
  triggersHardConstraint?: boolean;
  applicability?: string;
};

export type HardConstraint = { id: string; label: string };

export type SandboxGraph = {
  nodes: SandboxGraphNode[];
  edges: SandboxGraphEdge[];
  hardConstraints: HardConstraint[];
  /** draft = 尚未保存为正式 GraphVersion。 */
  draft: boolean;
};

/** scenario_planning artifact 的可审阅 frame（独立于图，只读输入）。 */
export type ScenarioFrame = {
  id: string;
  title: string;
  externalDrivers: string[];
  unknownDrivers: string[];
  strategySurvives: boolean;
  earlyWarnings: string[];
  confirmed: boolean;
  /** 已确认 frame 才有版本 anchor；未确认为 null。 */
  scenarioVersionId: string | null;
  /** 情景对脆弱条件的业务值调整（按节点 id，业务单位）；作为已确认情景预设。 */
  conditionAdjustments?: Record<string, number>;
};

/** SIM-02A run API 的全部请求 anchor（服务端权威，前端只透传）。 */
export type SimulationAnchors = {
  workspaceId: string;
  graphId: string;
  graphVersionId: string;
  strategyVersionId: string;
  scenarioVersionId: string;
  scoreDefinitionId: string;
  decisionMakerProfileId: string;
  decisionMakerProfileVersion: number;
};

/** 沙盘工作区的完整只读输入。 */
export type SandboxCaseData = {
  recommendation: SandboxRecommendation;
  fragileConditions: FragileCondition[];
  graph: SandboxGraph;
  scenarioFrames: ScenarioFrame[];
  anchors: SimulationAnchors;
};

/** 候选修订：验证行动 / 情景版本都先落为 candidate，不直接更新正式档案。 */
export type CandidateRevision = {
  kind: "validation_action" | "scenario_version";
  status: "candidate";
  title: string;
  detail: string;
  sourceNodeId?: string;
  sourceFrameId?: string;
};

/** 命名实验分支（非破坏性：回滚只恢复工作副本，不删除任何分支）。 */
export type ExperimentBranch = {
  id: string;
  name: string;
  conditionNodeId: string;
  value: number;
  runId: string | null;
  summary: string;
};

// --- SIM-02A wire types (frozen camelCase data payload) ---------------------

export type SimulationOptionScore = { optionId: string; score: number };
export type SimulationTopDriver = { nodeId: string; scoreDelta: number };

export type SimulationRunData = {
  simulationRunId: string;
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
  simulationMode: string;
  epsilon: number;
  maxSteps: number;
  steps: number;
  inputHash: string;
  nodeResults: Record<string, number>;
  optionScores: SimulationOptionScore[];
  topDrivers: SimulationTopDriver[];
  recommendationShift: string;
  recommendedOptionId: string | null;
  convergenceStatus: string;
  originModes: string[];
  createdAt: string;
};
