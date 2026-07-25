// Task 13 Step 2: current conditional recommendation (read-only consumption
// of the formal report version; the sandbox never rewrites it).

import type { SandboxRecommendation } from "./types";

type CurrentRecommendationSummaryProps = {
  recommendation: SandboxRecommendation;
};

export function CurrentRecommendationSummary({ recommendation }: CurrentRecommendationSummaryProps) {
  return (
    <section className="current-recommendation" aria-labelledby="current-recommendation-title">
      <header className="section-line-heading">
        <div>
          <span>当前条件化建议</span>
          <h2 id="current-recommendation-title">{recommendation.headline}</h2>
        </div>
        <small>来源报告版本 {recommendation.sourceReportVersion}</small>
      </header>
      <dl className="recommendation-conditions">
        <dt>成立条件</dt>
        {recommendation.conditions.map((condition) => (
          <dd key={condition}>{condition}</dd>
        ))}
      </dl>
      <p className="recommendation-scope-note">{recommendation.scopeNote}</p>
    </section>
  );
}
