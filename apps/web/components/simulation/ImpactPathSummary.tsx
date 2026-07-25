// Task 13 Step 3: one to three readable impact paths, text first, with a
// control to locate the path inside the full causal model.

import { impactPathText, type ImpactPath } from "./interpret";

type ImpactPathSummaryProps = {
  paths: ImpactPath[];
  /** 定位到完整图：展开 model-mode 并高亮该路径。 */
  onLocate: (path: ImpactPath) => void;
};

export function ImpactPathSummary({ paths, onLocate }: ImpactPathSummaryProps) {
  if (paths.length === 0) return null;
  return (
    <section className="causal-paths" aria-label="关键影响路径">
      <header>
        <span>关键影响路径</span>
        <small>仅显示一至三条可读路径</small>
      </header>
      <ol className="impact-path-list">
        {paths.slice(0, 3).map((path) => (
          <li key={path.id} className="path-row">
            <span>{impactPathText(path)}</span>
            <button type="button" className="text-action" onClick={() => onLocate(path)}>
              在完整模型中定位
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}
