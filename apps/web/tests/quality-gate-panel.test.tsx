/** @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";

import { createElement } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";

import {
  QualityGatePanel,
  type QualityGateProjection,
} from "../components/quality/QualityGatePanel";

afterEach(() => {
  cleanup();
});

function renderGate(projection: QualityGateProjection): void {
  render(createElement(QualityGatePanel, { projection }));
}

describe("QualityGatePanel", () => {
  test("renders the unassessed margin before any run", () => {
    renderGate({ runStatus: null, gate: null, blockedCodes: [], fixtureRun: false });
    expect(screen.getByText("质量门未评估")).toBeInTheDocument();
    expect(screen.getByText(/发起一次分析后/)).toBeInTheDocument();
    expect(screen.getAllByText("未评估").length).toBeGreaterThanOrEqual(3);
  });

  test("renders the passed gate with dimension scores and no invention", () => {
    renderGate({
      runStatus: "ready",
      gate: { passed: true, score: 0.91, dims: { evidence: 0.9, adversarial: 0.95, consistency: 0.99 } },
      blockedCodes: [],
      fixtureRun: false,
    });
    expect(screen.getByText("已通过最终质量门")).toBeInTheDocument();
    expect(screen.getByText(/均已通过审查/)).toBeInTheDocument();
    expect(screen.queryByText(/未评估/)).not.toBeInTheDocument();
  });

  test("blocked run with stable codes renders repair actions, not generic retry", () => {
    renderGate({
      runStatus: "blocked",
      gate: { passed: false, score: 0.4, dims: {} },
      blockedCodes: ["strategic_lens_incomplete", "validator_rejected"],
      fixtureRun: false,
    });
    expect(screen.getByText("尚未通过最终质量门")).toBeInTheDocument();
    expect(screen.getByText(/重新发起分析/)).toBeInTheDocument();
    expect(screen.getByText(/回 Q 区完善档案/)).toBeInTheDocument();
  });

  test("fixture run is labelled honestly as a demo placeholder", () => {
    renderGate({
      runStatus: "blocked",
      gate: { passed: false, score: 0, dims: {} },
      blockedCodes: [],
      fixtureRun: true,
    });
    expect(screen.getByText(/演示占位模式/)).toBeInTheDocument();
    expect(screen.getByText(/按设计拦截正式产物/)).toBeInTheDocument();
  });

  test("dimension the pipeline did not exercise renders as 未评估", () => {
    renderGate({
      runStatus: "blocked",
      gate: { passed: false, score: 0.3, dims: { evidence: 0.8 } },
      blockedCodes: [],
      fixtureRun: false,
    });
    // adversarial + consistency were not exercised -> both read 未评估.
    expect(screen.getAllByText("未评估").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("有条件")).toBeInTheDocument();
  });
});
