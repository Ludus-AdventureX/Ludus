// Canonical Look V7 five-workspace information architecture (frozen by
// design/look-source-manifest.json and 24-frontend-visual-theme.md).
// Review (复盘) is intentionally NOT a sixth workspace: per B12 it is a
// dialog triggered from the spine and its domain UI belongs to Task 14W.

export const caseWorkspaces = [
  { id: "workspace", coordinate: "Q", label: "问题", description: "界定边界" },
  { id: "analysis", coordinate: "E", label: "证据", description: "研究与质疑" },
  { id: "report", coordinate: "J", label: "判断", description: "条件化建议" },
  { id: "sandbox", coordinate: "G", label: "推演", description: "寻找翻转" },
  { id: "decision", coordinate: "D", label: "决定", description: "冻结行动" }
] as const;

export type CaseWorkspaceId = (typeof caseWorkspaces)[number]["id"];

// Spine slot reserved for the Task 14W review dialog trigger.
export const reviewTrigger = { coordinate: "R", label: "复盘", description: "回到现实" } as const;

export const defaultWorkspaceId: CaseWorkspaceId = "workspace";

export function isCaseWorkspaceId(value: string | null | undefined): value is CaseWorkspaceId {
  return value != null && caseWorkspaces.some((workspace) => workspace.id === value);
}
