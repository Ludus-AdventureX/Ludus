// Case-scoped run reads + shared gate-finding vocabulary (B-layer).
//
// `listCaseAnalyses` projects GET /cases/{id}/analyses (CCR-20260726-READ-01
// run anchors) for the E/J views. `humanizeFinding` translates the stable
// lower_snake gate reason codes for humans — the raw code stays visible so
// nothing is hidden, and unknown codes pass through untouched.

import { DecisionLoopError, type FetchLike } from "@/lib/shell/decisionLoop";

function defaultFetch(): FetchLike {
  return (input, init) => fetch(input, { credentials: "include", ...init });
}

export type RunAnchor = {
  analysisRunId: string;
  decisionCaseId: string;
  charterId: string;
  analysisLevel: "focused" | "full" | string;
  status: string;
  caseVersion: number;
  createdAt: string;
  completedAt: string | null;
};

export async function listCaseAnalyses(
  workspaceId: string,
  decisionCaseId: string,
  fetchImpl: FetchLike = defaultFetch(),
): Promise<RunAnchor[]> {
  let response: Response;
  try {
    response = await fetchImpl(
      `/api/workspaces/${encodeURIComponent(workspaceId)}/cases/${encodeURIComponent(decisionCaseId)}/analyses`,
      { credentials: "include" },
    );
  } catch {
    throw new DecisionLoopError("NETWORK_ERROR", "无法连接后端服务。", 0);
  }
  const body = (await response.json().catch(() => null)) as
    | { ok?: boolean; data?: { items?: RunAnchor[] } }
    | null;
  if (!response.ok || !body?.ok) {
    throw new DecisionLoopError("RUN_LIST_FAILED", "读取分析运行列表失败。", response.status);
  }
  return body.data?.items ?? [];
}

/** Stable gate reason codes translated for humans; the code stays visible. */
export const FINDING_LABELS: Record<string, string> = {
  strategic_lens_incomplete: "五个战略透镜产物不完整（有缺失或未通过行为校验）",
  strategic_lens_reference_mismatch: "报告引用的透镜产物与本次运行实际产出的五件不一致",
  strategic_lens_duplicate_type: "同一战略透镜出现了多份产物",
  strategic_lens_outside_charter: "出现了章程冻结集合之外的透镜产物",
  deterministic_gate: "确定性质量门（证据 × 反方 × 一致性乘法评分）",
  validator_rejected: "验证审查拒绝：证据链存在漏洞（理由见验证阶段审查产物）",
};

export function humanizeFinding(code: string): string {
  const label = FINDING_LABELS[code];
  return label ? `${label}（${code}）` : code;
}

/** Gate-dimension verdict text from the multiplicative gate's 0..1 score. */
export function dimVerdict(value: number | undefined): string {
  if (typeof value !== "number") return "未评估";
  if (value >= 0.95) return "通过";
  if (value >= 0.6) return "有条件";
  return "薄弱";
}

export const RUN_STATUS_LABELS: Record<string, string> = {
  queued: "排队中",
  planning: "规划中",
  retrieving: "检索中",
  analyzing: "分析中",
  criticizing: "反方质疑中",
  synthesizing: "综合中",
  validating: "验证中",
  ready: "已完成，通过质量门",
  blocked: "已完成：被质量门拦下",
  needs_attention: "已暂停，需要人工关注",
  cancelled: "已取消",
};

export function runStatusLabel(status: string | undefined): string {
  return (status && RUN_STATUS_LABELS[status]) || status || "未知状态";
}

export const EXECUTING_RUN_STATUSES = new Set([
  "queued",
  "planning",
  "retrieving",
  "analyzing",
  "criticizing",
  "synthesizing",
  "validating",
]);
