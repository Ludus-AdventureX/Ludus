/** @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createElement } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";

import type { DemoFixtureIds, DemoFlowResult, SimulationRunData } from "../lib/demo/simulationDemo";

const { establishGuestSession, runSimulation } = vi.hoisted(() => ({
  establishGuestSession: vi.fn(),
  runSimulation: vi.fn(),
}));

vi.mock("@/lib/demo/simulationDemo", async () => {
  const actual = await vi.importActual<typeof import("../lib/demo/simulationDemo")>(
    "../lib/demo/simulationDemo",
  );
  return { ...actual, establishGuestSession, runSimulation };
});

import { SimulationDemoPanel } from "../components/demo/SimulationDemoPanel";
import { DemoApiError } from "../lib/demo/simulationDemo";

const fixture: DemoFixtureIds = {
  graphId: "graph-1",
  graphVersionId: "graph-version-1",
  strategyVersionId: "strategy-version-1",
  scenarioVersionId: "scenario-version-1",
  scoreDefinitionId: "score-definition-1",
  decisionMakerProfileId: "profile-1",
  decisionMakerProfileVersion: 1,
};

const runData: SimulationRunData = {
  simulationRunId: "run-1",
  workspaceId: "workspace-1",
  decisionCaseId: "case-1",
  graphId: "graph-1",
  graphVersionId: "graph-version-1",
  strategyVersionId: "strategy-version-1",
  scenarioVersionId: "scenario-version-1",
  scoreDefinitionId: "score-definition-1",
  scoreDefinitionVersion: "1",
  decisionMakerProfileId: "profile-1",
  decisionMakerProfileVersion: 1,
  riskTolerance: 0.5,
  engineVersion: "sim-engine-1.1.0",
  scenarioId: "scenario-1",
  simulationMode: "experimental",
  epsilon: 0.001,
  maxSteps: 12,
  steps: 4,
  inputHash: "c".repeat(64),
  nodeResults: {},
  optionScores: [{ optionId: "option-a", score: 0.61 }],
  topDrivers: [{ nodeId: "price", scoreDelta: -0.2 }],
  recommendationShift: "stable",
  recommendedOptionId: "option-a",
  convergenceStatus: "converged",
  originModes: ["experimental"],
  createdAt: "2026-07-25T00:00:00Z",
};

const flowResult: DemoFlowResult = {
  workspaceId: "workspace-1",
  fixture,
  run: runData,
  idempotencyReplay: false,
  replay: runData,
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("SimulationDemoPanel", () => {
  test("bootstraps the guest session on mount and shows the Run button", async () => {
    let releaseBoot: (value: { workspaceId: string; fixture: DemoFixtureIds }) => void = () => {};
    establishGuestSession.mockImplementation(
      (onStep) =>
        new Promise((resolve) => {
          onStep?.("csrf");
          onStep?.("guest");
          releaseBoot = resolve;
        }),
    );

    render(createElement(SimulationDemoPanel));
    // 初始状态已是 running/csrf；boot 推进到 guest 步骤时显示“2/4”。
    expect(await screen.findByRole("status")).toHaveTextContent(/2\/4|1\/4/);

    releaseBoot({ workspaceId: "workspace-1", fixture });

    await waitFor(() => expect(screen.getByText("Run Simulation")).toBeInTheDocument());
    expect(screen.getByText("workspace-1")).toBeInTheDocument();
    expect(screen.getByText(fixture.graphId)).toBeInTheDocument();
    expect(screen.getByText(/profile-1 v1/)).toBeInTheDocument();
  });

  test("clicking Run walks through the simulation and renders the result", async () => {
    establishGuestSession.mockResolvedValue({ workspaceId: "workspace-1", fixture });
    runSimulation.mockResolvedValue({ run: runData, idempotencyReplay: false, replay: runData });

    const user = userEvent.setup();
    render(createElement(SimulationDemoPanel));
    const runButton = await screen.findByRole("button", { name: "Run Simulation" });
    await user.click(runButton);

    await waitFor(() =>
      expect(screen.getAllByText(runData.simulationRunId).length).toBeGreaterThanOrEqual(2),
    );
    expect(screen.getByText(runData.engineVersion)).toBeInTheDocument();
    expect(screen.getByText(/converged/)).toBeInTheDocument();
    expect(screen.getByText(/option-a（shift: stable）/)).toBeInTheDocument();
    expect(screen.getByText(/Δscore -0\.2000/)).toBeInTheDocument();
    expect(runSimulation).toHaveBeenCalledWith(
      "workspace-1",
      fixture,
      expect.any(Function),
    );
  });

  test("renders a clear error state with retry when the guest step fails", async () => {
    establishGuestSession.mockRejectedValue(
      new DemoApiError("NETWORK_ERROR", "无法连接 /api 服务。", 0),
    );

    render(createElement(SimulationDemoPanel));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("NETWORK_ERROR");
    expect(alert).toHaveTextContent("无法连接 /api 服务。");
    expect(screen.getByRole("button", { name: "重试" })).toBeEnabled();
  });
});
