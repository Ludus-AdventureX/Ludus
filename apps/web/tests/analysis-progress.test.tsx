/** @vitest-environment jsdom */

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, act, fireEvent } from "@testing-library/react";
import { createElement } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";

import { AnalysisProgress, stageStates } from "../components/shell/views/AnalysisProgress";

// The product complaint was "I cannot tell where the analysis is". These tests
// pin the answer: a real progress bar driven by the run's own progress, a
// six-stage indicator, per-stage thinking, and an honest exit when a run sits
// in `queued` because the worker is not running.

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const TRACE = [
  {
    stage: "retrieving",
    headline: "救援市场认证周期是决定性变量",
    details: ["机构采购决策周期 6-12 个月"],
    model: "deepseek-v4-pro",
  },
  {
    stage: "safety_anchor",
    headline: "所有方向都假设认证排期可控",
    details: [],
  },
];

function renderProgress(overrides: Partial<Parameters<typeof AnalysisProgress>[0]> = {}) {
  return render(
    createElement(AnalysisProgress, {
      status: "analyzing",
      progress: 0.5,
      statusLabel: "分析阶段",
      trace: TRACE,
      runId: "run-abcdef12",
      ...overrides,
    }),
  );
}

describe("stageStates", () => {
  test("marks earlier stages done, the current one active, later ones pending", () => {
    const states = stageStates("criticizing");
    expect(states.planning).toBe("done");
    expect(states.retrieving).toBe("done");
    expect(states.analyzing).toBe("done");
    expect(states.criticizing).toBe("active");
    expect(states.synthesizing).toBe("pending");
    expect(states.validating).toBe("pending");
  });

  test("queued has started nothing, ready has finished everything", () => {
    expect(Object.values(stageStates("queued")).every((s) => s === "pending")).toBe(true);
    expect(Object.values(stageStates("ready")).every((s) => s === "done")).toBe(true);
  });

  test("a stopped run never fakes a completed stage", () => {
    for (const status of ["blocked", "cancelled", "needs_attention"]) {
      expect(Object.values(stageStates(status)).every((s) => s === "stopped")).toBe(true);
    }
  });
});

describe("AnalysisProgress", () => {
  test("renders an accessible progress bar from the run's own progress", () => {
    renderProgress({ progress: 0.43 });

    const bar = screen.getByRole("progressbar", { name: "分析进度" });
    expect(bar).toHaveAttribute("aria-valuenow", "43");
    expect(bar).toHaveAttribute("aria-valuemin", "0");
    expect(bar).toHaveAttribute("aria-valuemax", "100");
    // Text carries the same fact, so colour/width is never the only signal.
    expect(document.querySelector("[data-analysis-percent='43']")).toHaveTextContent("43%");
  });

  test("shows the six stages with their state and hangs each digest on its stage", () => {
    renderProgress({ status: "criticizing" });

    const stepper = document.querySelector("[data-analysis-stepper]");
    expect(stepper).toBeInTheDocument();
    // Direct children only: a stage's digest bullets are nested <li> too.
    expect(document.querySelectorAll("[data-analysis-stepper] > li")).toHaveLength(6);

    expect(document.querySelector("[data-stage='retrieving']")).toHaveAttribute(
      "data-stage-state",
      "done",
    );
    expect(document.querySelector("[data-stage='criticizing']")).toHaveAttribute(
      "data-stage-state",
      "active",
    );
    expect(document.querySelector("[data-stage='validating']")).toHaveAttribute(
      "data-stage-state",
      "pending",
    );

    // The retrieving digest belongs to the retrieving row, not a flat list.
    const retrieving = document.querySelector("[data-stage='retrieving']");
    expect(retrieving).toHaveTextContent("救援市场认证周期是决定性变量");
    expect(retrieving).toHaveTextContent("机构采购决策周期 6-12 个月");
    expect(retrieving?.querySelector("[data-trace-model]")).toHaveTextContent("deepseek-v4-pro");
  });

  test("independent passes render outside the pipeline, never as a stage", () => {
    renderProgress();

    const enrichment = document.querySelector("[data-analysis-enrichment]");
    expect(enrichment).toHaveTextContent("安全锚");
    expect(enrichment).toHaveTextContent("所有方向都假设认证排期可控");
    // It must not be counted among the six pipeline stages.
    expect(document.querySelectorAll("[data-analysis-stepper] > li")).toHaveLength(6);
  });

  test("progress stays at zero while queued - nothing creeps forward", () => {
    renderProgress({ status: "queued", progress: 0, statusLabel: "排队中" });

    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
    expect(document.querySelector("[data-analysis-queued]")).not.toBeInTheDocument();
  });

  test("a queued run that waits too long says the worker may be down and offers an exit", async () => {
    vi.useFakeTimers();
    const onCancel = vi.fn();
    renderProgress({ status: "queued", progress: 0, statusLabel: "排队中", onCancel });

    expect(document.querySelector("[data-analysis-queued]")).not.toBeInTheDocument();

    await act(async () => {
      vi.advanceTimersByTime(31_000);
    });
    const warning = document.querySelector("[data-analysis-queued='warn']");
    expect(warning).toBeInTheDocument();
    expect(warning).toHaveTextContent(/工作器/);
    expect(screen.getByRole("alert")).toBeInTheDocument();

    await act(async () => {
      vi.advanceTimersByTime(180_000);
    });
    const alarm = document.querySelector("[data-analysis-queued='alarm']");
    expect(alarm).toBeInTheDocument();
    expect(alarm).toHaveTextContent(/没有运行|未运行|很可能/);

    // fireEvent, not userEvent: userEvent's own async waits do not advance under
    // fake timers, and the point here is the timer-driven affordance.
    fireEvent.click(screen.getByRole("button", { name: /取消本次分析/ }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  test("no cancel affordance is offered when the caller provides no handler", () => {
    vi.useFakeTimers();
    renderProgress({ status: "queued", progress: 0, statusLabel: "排队中" });
    act(() => {
      vi.advanceTimersByTime(40_000);
    });
    expect(document.querySelector("[data-analysis-queued]")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  test("a blocked run tones the bar without claiming the stages completed", () => {
    renderProgress({ status: "blocked", progress: 0.86, statusLabel: "质量门未通过" });

    expect(document.querySelector("[data-analysis-progress='blocked']")).toBeInTheDocument();
    expect(document.querySelector("[data-stage='validating']")).toHaveAttribute(
      "data-stage-state",
      "stopped",
    );
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "86");
  });
});
