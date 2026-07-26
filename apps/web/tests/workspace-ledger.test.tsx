/** @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { createElement } from "react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { WorkspaceView } from "../components/shell/views/WorkspaceView";
import type { CandidateView, CaseDetailView } from "../lib/shell/caseData";

// The live Q workspace drives real case reads + message/candidate writes; the
// unit layer mocks the caseData module (the golden path covers the wire).
const mocks = vi.hoisted(() => ({
  fetchCaseDetail: vi.fn(),
  fetchCandidates: vi.fn(),
  postCaseMessage: vi.fn(),
  confirmCandidate: vi.fn(),
  rejectCandidate: vi.fn()
}));

vi.mock("@/lib/shell/caseData", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/shell/caseData")>();
  return {
    ...original,
    fetchCaseDetail: mocks.fetchCaseDetail,
    fetchCandidates: mocks.fetchCandidates,
    postCaseMessage: mocks.postCaseMessage,
    confirmCandidate: mocks.confirmCandidate,
    rejectCandidate: mocks.rejectCandidate
  };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const caseDetail: CaseDetailView = {
  decisionCaseId: "case-1",
  decisionSubjectId: "subject-1",
  title: "先验证哪一个市场方向？",
  decisionQuestion: "先验证哪一个市场方向？",
  inferredDecisionType: "market_direction",
  status: "exploration",
  operationalStatus: "active",
  caseVersion: 1,
  confirmedDossierVersion: 1,
  confirmedDossierSnapshotHash: null,
  argumentNodes: [
    {
      id: "arg-root-case-1",
      workspaceId: "ws-1",
      decisionCaseId: "case-1",
      parentId: null,
      type: "claim",
      text: "先验证哪一个市场方向？",
      evidenceIds: [],
      assumptionIds: [],
      supportScore: 0.5,
      status: "confirmed"
    },
    {
      id: "arg-entry-1",
      workspaceId: "ws-1",
      decisionCaseId: "case-1",
      parentId: "arg-root-case-1",
      type: "risk",
      text: "现金窗口只有 12 个月",
      evidenceIds: [],
      assumptionIds: [],
      supportScore: 0.5,
      status: "confirmed"
    }
  ],
  createdAt: "2026-07-26T00:00:00Z",
  updatedAt: "2026-07-26T00:00:00Z"
};

const pendingCandidate: CandidateView = {
  candidateRevisionId: "cand-1",
  decisionCaseId: "case-1",
  sourceType: "conversation",
  sourceId: "msg-1",
  baseDossierVersion: 1,
  baseCaseVersion: 1,
  proposals: [
    { operation: "add", entry: { statementType: "constraint", content: "现金窗口只有 12 个月" } }
  ],
  status: "pending",
  reviewedAt: null
};

function renderView(workspaceId: string | null = "ws-1") {
  return render(
    createElement(WorkspaceView, { decisionCaseId: "case-1", workspaceId })
  );
}

describe("WorkspaceView live Q workspace", () => {
  test("without the ?ws= anchor no read fires and the skeleton stays honest", () => {
    renderView(null);

    expect(screen.getByRole("heading", { level: 1, name: /决策项目 case-1/ })).toBeVisible();
    expect(mocks.fetchCaseDetail).not.toHaveBeenCalled();
    expect(mocks.fetchCandidates).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("写下你的判断、担忧、直觉或问题")).not.toBeInTheDocument();
  });

  test("loads the real case detail into headline, coordinate and folio", async () => {
    mocks.fetchCaseDetail.mockResolvedValue(caseDetail);
    mocks.fetchCandidates.mockResolvedValue([]);
    renderView();

    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1, name: "先验证哪一个市场方向？" })).toBeVisible()
    );
    expect(screen.getByText("CaseVersion v1 · Dossier v1")).toBeVisible();
    expect(screen.getByText(/已确认条目 \/ 1/)).toBeVisible();
    expect(screen.getByText(/现金窗口只有 12 个月/)).toBeVisible();
  });

  test("posting a ledger note renders the reply and the patch summary", async () => {
    const user = userEvent.setup();
    mocks.fetchCaseDetail.mockResolvedValue(caseDetail);
    mocks.fetchCandidates.mockResolvedValue([]);
    mocks.postCaseMessage.mockResolvedValue({
      candidateRevisionId: "cand-1",
      baseDossierVersion: 1,
      baseCaseVersion: 1,
      assistantMessage: "已记录你的判断；现金窗口将作为候选约束等待确认。",
      proposedPatch: { goalsAdded: 0, constraintsAdded: 1, factsAdded: 0, assumptionsAdded: 0, unknownsAdded: 0 }
    });
    renderView();

    await user.type(
      await screen.findByLabelText("写下你的判断、担忧、直觉或问题"),
      "我们只有 12 个月现金窗口。"
    );
    await user.click(screen.getByRole("button", { name: /记入札记/ }));

    await waitFor(() =>
      expect(screen.getByText("已记录你的判断；现金窗口将作为候选约束等待确认。")).toBeVisible()
    );
    expect(mocks.postCaseMessage).toHaveBeenCalledWith("ws-1", "case-1", "我们只有 12 个月现金窗口。");
    expect(screen.getByText(/候选提炼：＋1 约束（待你确认）/)).toBeVisible();
    // The extraction produced a candidate -> the redline list is re-read.
    expect(mocks.fetchCandidates).toHaveBeenCalledTimes(2);
  });

  test("a pending candidate can be written into the canonical dossier", async () => {
    const user = userEvent.setup();
    mocks.fetchCaseDetail.mockResolvedValue(caseDetail);
    mocks.fetchCandidates.mockResolvedValue([pendingCandidate]);
    mocks.confirmCandidate.mockResolvedValue({
      candidateRevisionId: "cand-1",
      status: "accepted",
      dossierVersion: 2,
      caseVersion: 2,
      confirmedEntryIds: ["entry-1"]
    });
    renderView();

    await user.click(await screen.findByRole("button", { name: "写入档案" }));

    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(
        "已写入正式档案：DossierVersion v2 · CaseVersion v2"
      )
    );
    expect(mocks.confirmCandidate).toHaveBeenCalledWith(
      "ws-1",
      "case-1",
      expect.objectContaining({ candidateRevisionId: "cand-1", baseDossierVersion: 1 })
    );
  });

  test("a failing reply keeps an honest notice and never fabricates a response", async () => {
    const user = userEvent.setup();
    mocks.fetchCaseDetail.mockResolvedValue(caseDetail);
    mocks.fetchCandidates.mockResolvedValue([]);
    mocks.postCaseMessage.mockRejectedValue(new Error("boom"));
    renderView();

    await user.type(
      await screen.findByLabelText("写下你的判断、担忧、直觉或问题"),
      "测试失败路径"
    );
    await user.click(screen.getByRole("button", { name: /记入札记/ }));

    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent("系统回应失败，请稍后重试。")
    );
    expect(screen.queryByText(/候选提炼/)).not.toBeInTheDocument();
  });
});
