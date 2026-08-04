/** @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";

import { createElement, type ReactElement } from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import { StressTestControl } from "../components/simulation/StressTestControl";
import type { FragileCondition, ScenarioFrame } from "../components/simulation/types";

afterEach(() => {
  cleanup();
});

const CONDITION: FragileCondition = {
  nodeId: "c-procurement",
  title: "采购周期",
  unit: "个月",
  baselineValue: 10,
  min: 6,
  max: 18,
  step: 1,
  controllability: "external",
  evidenceStatus: "supported",
  impactNote: "采购周期越长，现金窗口越紧",
};

const SCENARIO: ScenarioFrame = {
  id: "scn-baseline",
  title: "基线需求情景",
  externalDrivers: [],
  unknownDrivers: [],
  strategySurvives: true,
  earlyWarnings: [],
  confirmed: true,
  scenarioVersionId: "gv-1",
  conditionAdjustments: { "c-procurement": 14 },
};

function renderControl(props: Record<string, unknown> = {}): void {
  const element = createElement(StressTestControl, {
    condition: CONDITION,
    value: 12,
    onChange: vi.fn(),
    onReset: vi.fn(),
    onRun: vi.fn(),
    running: false,
    confirmedScenarios: [],
    onApplyScenario: vi.fn(),
    ...props,
  } as Record<string, unknown>);
  render(element as ReactElement);
}

describe("StressTestControl", () => {
  test("renders the focused condition with baseline and business units", () => {
    renderControl();
    expect(screen.getByRole("heading", { name: "采购周期" })).toBeInTheDocument();
    expect(screen.getAllByText(/基线 10 个月/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole("slider", { name: "采购周期（个月）" })).toHaveValue("12");
    expect(screen.getByRole("spinbutton")).toHaveValue(12);
  });

  test("slider changes write the working copy without running", () => {
    const onChange = vi.fn();
    renderControl({ onChange });
    fireEvent.change(screen.getByRole("slider", { name: "采购周期（个月）" }), {
      target: { value: "14" },
    });
    expect(onChange).toHaveBeenCalledWith(14);
    expect(screen.getByRole("button", { name: /运行压力测试/ })).toBeInTheDocument();
  });

  test("numeric input clamps out-of-range values", () => {
    const onChange = vi.fn();
    renderControl({ onChange });
    fireEvent.change(screen.getByRole("spinbutton"), { target: { value: "99" } });
    expect(onChange).toHaveBeenCalledWith(18);
  });

  test("reset returns to baseline; run is explicit and disabled while running", () => {
    const onReset = vi.fn();
    const onRun = vi.fn();
    renderControl({ onReset, onRun });
    fireEvent.click(screen.getByRole("button", { name: "回到基线" }));
    expect(onReset).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: /运行压力测试/ }));
    expect(onRun).toHaveBeenCalledTimes(1);

    cleanup();
    renderControl({ running: true });
    const running = screen.getByRole("button", { name: /推演运行中/ });
    expect(running).toBeDisabled();
    expect(running).toHaveAttribute("aria-busy", "true");
  });

  test("confirmed scenario presets apply adjustments via callback", () => {
    const onApplyScenario = vi.fn();
    renderControl({ confirmedScenarios: [SCENARIO], onApplyScenario });
    const presets = screen.getByRole("group", { name: "已确认情景" });
    fireEvent.click(within(presets).getByRole("button", { name: "基线需求情景" }));
    expect(onApplyScenario).toHaveBeenCalledWith(SCENARIO);
  });
});
