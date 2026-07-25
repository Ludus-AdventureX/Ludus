// Task 13 Step 2: stress-test control. One condition in focus at a time;
// slider + numeric input in BUSINESS units; confirmed-scenario presets;
// reset; explicit run. Adjustments only write the working copy — a
// simulation is never auto-submitted.

import { useId } from "react";

import type { FragileCondition, ScenarioFrame } from "./types";

type StressTestControlProps = {
  condition: FragileCondition;
  /** 工作副本当前值（未运行前只存在于本地）。 */
  value: number;
  onChange: (value: number) => void;
  onReset: () => void;
  onRun: () => void;
  running: boolean;
  /** 只允许「已确认」的情景作为预设。 */
  confirmedScenarios: ScenarioFrame[];
  onApplyScenario: (frame: ScenarioFrame) => void;
};

export function StressTestControl({
  condition,
  value,
  onChange,
  onReset,
  onRun,
  running,
  confirmedScenarios,
  onApplyScenario,
}: StressTestControlProps) {
  const sliderId = useId();
  const numberId = useId();
  const label = `${condition.title}（${condition.unit}）`;

  const parse = (raw: string) => {
    const next = Number(raw);
    if (!Number.isFinite(next)) return;
    onChange(Math.min(condition.max, Math.max(condition.min, next)));
  };

  return (
    <article className="pressure-instrument">
      <header className="section-line-heading">
        <div>
          <span>Fragile condition</span>
          <h2>{condition.title}</h2>
        </div>
        <small>
          基线 {condition.baselineValue} {condition.unit} · {condition.impactNote}
        </small>
      </header>

      <p className="pressure-question">
        如果「{condition.title}」从 <b>{condition.baselineValue}</b> {condition.unit}变为{" "}
        <strong>{value}</strong> {condition.unit}，会发生什么？
      </p>

      <div className="slider-wrap">
        <label className="margin-label" htmlFor={sliderId}>
          {label}
        </label>
        <input
          id={sliderId}
          type="range"
          min={condition.min}
          max={condition.max}
          step={condition.step}
          value={value}
          aria-label={label}
          onChange={(event) => parse(event.target.value)}
        />
        <div className="slider-labels">
          <span>
            {condition.min} {condition.unit}
          </span>
          <span>
            基线 {condition.baselineValue} {condition.unit}
          </span>
          <span>
            {condition.max} {condition.unit}
          </span>
        </div>
        <label className="margin-label" htmlFor={numberId}>
          精确输入（{condition.unit}）
        </label>
        <input
          id={numberId}
          type="number"
          min={condition.min}
          max={condition.max}
          step={condition.step}
          value={value}
          onChange={(event) => parse(event.target.value)}
        />
      </div>

      {confirmedScenarios.length > 0 ? (
        <div className="pressure-presets" role="group" aria-label="已确认情景">
          {confirmedScenarios.map((frame) => (
            <button key={frame.id} type="button" onClick={() => onApplyScenario(frame)}>
              {frame.title}
            </button>
          ))}
        </div>
      ) : null}

      <div className="intro-actions">
        <button type="button" className="secondary-action" onClick={onReset}>
          回到基线
        </button>
        <button
          type="button"
          className="primary-action"
          onClick={onRun}
          disabled={running}
          aria-busy={running}
        >
          <span>{running ? "推演运行中…" : "运行压力测试"}</span>
          <small>使用当前业务值计算建议变化；不运行则不提交</small>
        </button>
      </div>
    </article>
  );
}
