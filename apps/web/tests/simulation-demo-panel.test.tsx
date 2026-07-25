/** @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createElement } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";

import type { DemoFlowResult, SimulationRunData } from "../lib/demo/simulationDemo";

const { readDemoFixtureConfig, runDemoFlow } = vi.hoisted(() => ({
  readDemoFixtureConfig: vi.fn(),
  runDemoFlow: vi.fn(),
}));

vi.mock("@/lib/demo/simulationDemo", async () => {
  const actual = await vi.importActual<typeof import("../lib/demo/simulationDemo")>(
    "../lib/demo/simulationDemo",
  );
  return { ...actual, readDemoFixtureConfig, runDemoFlow };
});

import { SimulationDemoPanel } from "../components/demo/SimulationDemoPanel";
import { DemoApiError } from "../lib/demo/simulationDemo";

const fixtureConfig = {
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
  run: runData,
  idempotencyReplay: false,
  replay: runData,
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

async function fillCredentialsAndSubmit() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Email"), "demo@example.test");
  await user.type(screen.getByLabelText("Password"), "demo-password");
  await user.click(screen.getByRole("button", { name: "运行 Demo Simulation" }));
  return user;
}

describe("SimulationDemoPanel", () => {
  test("lists missing fixture variables when the env is not configured", () => {
    readDemoFixtureConfig.mockReturnValue({ ok: false, missing: ["NEXT_PUBLIC_DEMO_GRAPH_ID"] });
    render(createElement(SimulationDemoPanel));
    expect(screen.getByRole("alert")).toHaveTextContent("NEXT_PUBLIC_DEMO_GRAPH_ID");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  test("shows the loading step and then the run + replay result", async () => {
    readDemoFixtureConfig.mockReturnValue({ ok: true, config: fixtureConfig });
    let releaseFlow: (value: DemoFlowResult) => void = () => {};
    runDemoFlow.mockImplementation(
      (_config, _credentials, onStep) =>
        new Promise<DemoFlowResult>((resolve) => {
          onStep?.("run");
          releaseFlow = resolve;
        }),
    );

    render(createElement(SimulationDemoPanel));
    await fillCredentialsAndSubmit();

    expect(await screen.findByRole("status")).toHaveTextContent("4/5 提交 Simulation Run");
    releaseFlow(flowResult);

    await waitFor(() =>
      expect(screen.getAllByText(runData.simulationRunId).length).toBeGreaterThanOrEqual(2),
    );
    expect(screen.getAllByText(runData.inputHash).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(runData.engineVersion)).toBeInTheDocument();
    expect(screen.getByText(/converged/)).toBeInTheDocument();
    expect(screen.getByText(/option-a（shift: stable）/)).toBeInTheDocument();
    expect(screen.getByText(/Δscore -0\.2000/)).toBeInTheDocument();
  });

  test("renders a clear error state when the flow fails", async () => {
    readDemoFixtureConfig.mockReturnValue({ ok: true, config: fixtureConfig });
    runDemoFlow.mockRejectedValue(
      new DemoApiError("AUTH_INVALID_CREDENTIALS", "Email or password is incorrect.", 401),
    );

    render(createElement(SimulationDemoPanel));
    await fillCredentialsAndSubmit();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("AUTH_INVALID_CREDENTIALS");
    expect(alert).toHaveTextContent("Email or password is incorrect.");
    expect(screen.getByRole("button", { name: "运行 Demo Simulation" })).toBeEnabled();
  });
});
