// Task 13: textual overlay describing the located impact path inside the
// full model (which nodes are highlighted and why). Keeps the canvas nodes
// stable; the overlay is presentation-only.

import { impactPathText, type ImpactPath } from "./interpret";

type ImpactPathOverlayProps = {
  path: ImpactPath | null;
  onClear: () => void;
};

export function ImpactPathOverlay({ path, onClear }: ImpactPathOverlayProps) {
  if (!path) return null;
  return (
    <aside className="impact-path-overlay" aria-label="已定位的影响路径">
      <span className="margin-label">已定位路径</span>
      <p>{impactPathText(path)}</p>
      <button type="button" className="text-action" onClick={onClear}>
        清除高亮
      </button>
    </aside>
  );
}
