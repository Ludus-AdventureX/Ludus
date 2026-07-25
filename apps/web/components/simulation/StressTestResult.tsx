// Task 13 Step 3: run result explained in natural language and business
// units first,必要评分细节其次。保持 → 已测试范围；翻转 → 目标选项 + 阈值 +
// 硬约束；无法判断 → 缺失证据。绝不显示 normalized value、damping、edge
// multiplier、评分公式或成功概率。

import type { RunInterpretation } from "./interpret";
import type { HardConstraint } from "./types";

const STATE_LABEL: Record<RunInterpretation["state"], string> = {
  kept: "建议保持",
  flipped: "建议翻转",
  insufficient: "证据不足",
};

const STATE_GLYPH: Record<RunInterpretation["state"], string> = {
  kept: "保",
  flipped: "翻",
  insufficient: "缺",
};

type StressTestResultProps = {
  interpretation: RunInterpretation;
  /** true = 服务端幂等重放的已冻结结果，未重复计算。 */
  idempotencyReplay: boolean;
  hardConstraints: HardConstraint[];
};

export function StressTestResult({
  interpretation,
  idempotencyReplay,
  hardConstraints,
}: StressTestResultProps) {
  return (
    <section
      className="pressure-result"
      data-state={interpretation.state}
      aria-live="polite"
      aria-labelledby="stress-result-title"
    >
      <span className="result-index">
        实验推演 · 非正式{idempotencyReplay ? " · 幂等重放（未重复计算）" : ""}
      </span>
      <div className="result-mark" aria-hidden="true">
        <span>{STATE_GLYPH[interpretation.state]}</span>
      </div>
      <h2 id="stress-result-title">{STATE_LABEL[interpretation.state]}</h2>
      <p>{interpretation.narrative}</p>

      <dl>
        <div>
          <dt>相对基线</dt>
          <dd>{interpretation.baselineDeltaText}</dd>
        </div>
        <div>
          <dt>建议状态</dt>
          <dd>{STATE_LABEL[interpretation.state]}</dd>
        </div>
        {interpretation.testedRangeText ? (
          <div>
            <dt>已测试范围</dt>
            <dd>{interpretation.testedRangeText}</dd>
          </div>
        ) : null}
        {interpretation.flipThresholdText ? (
          <div>
            <dt>翻转阈值</dt>
            <dd>{interpretation.flipThresholdText}</dd>
          </div>
        ) : null}
        {interpretation.flipTargetLabel ? (
          <div>
            <dt>转向选项</dt>
            <dd>{interpretation.flipTargetLabel}</dd>
          </div>
        ) : null}
        {interpretation.missingEvidence ? (
          <div>
            <dt>缺失证据</dt>
            <dd>{interpretation.missingEvidence}</dd>
          </div>
        ) : null}
      </dl>

      {interpretation.state === "flipped" && hardConstraints.length > 0 ? (
        <div className="result-hard-constraints">
          <span className="margin-label">相关硬约束</span>
          <ul>
            {hardConstraints.map((constraint) => (
              <li key={constraint.id}>{constraint.label}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="result-score-detail">
        推演细节：引擎 {interpretation.scoreDetail.engineVersion} · {interpretation.scoreDetail.steps}{" "}
        步 · 收敛状态 {interpretation.scoreDetail.convergenceStatus}
      </p>
    </section>
  );
}
