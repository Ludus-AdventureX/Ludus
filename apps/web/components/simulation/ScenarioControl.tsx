// Task 13 Step 6: scenario secondary flow. Frames are read from the
// independent scenario_planning artifact (external/unknown drivers,
// strategySurvives, early warnings). A ScenarioVersion candidate is created
// only AFTER the user confirms or modifies a frame. Never collects risk
// preference (server-owned per SIM-02A §5).

import { useState } from "react";

import type { CandidateRevision, ScenarioFrame } from "./types";

type ScenarioControlProps = {
  frames: ScenarioFrame[];
  onCreateScenarioVersion: (revision: CandidateRevision) => void;
};

export function ScenarioControl({ frames, onCreateScenarioVersion }: ScenarioControlProps) {
  const [editing, setEditing] = useState<string | null>(null);
  const [modifiedTitle, setModifiedTitle] = useState("");

  if (frames.length === 0) {
    return (
      <section className="scenario-control" aria-label="情景">
        <p>scenario_planning artifact 尚无可审阅的情景 frame。</p>
      </section>
    );
  }

  const submit = (frame: ScenarioFrame, title: string) => {
    onCreateScenarioVersion({
      kind: "scenario_version",
      status: "candidate",
      title,
      detail: `基于情景「${frame.title}」的确认/修改；早期预警：${frame.earlyWarnings.join("；") || "无"}。`,
      sourceFrameId: frame.id,
    });
    setEditing(null);
    setModifiedTitle("");
  };

  return (
    <section className="scenario-control" aria-label="情景">
      <header className="section-line-heading">
        <div>
          <span>scenario_planning artifact</span>
          <h3>情景审阅</h3>
        </div>
        <small>确认或修改后才创建 ScenarioVersion</small>
      </header>
      <ul className="scenario-frame-list">
        {frames.map((frame) => (
          <li key={frame.id} data-frame-id={frame.id}>
            <b>{frame.title}</b>
            <dl>
              <div>
                <dt>外部驱动</dt>
                <dd>{frame.externalDrivers.join("；") || "无"}</dd>
              </div>
              <div>
                <dt>未知驱动</dt>
                <dd>{frame.unknownDrivers.join("；") || "无"}</dd>
              </div>
              <div>
                <dt>策略存活</dt>
                <dd>{frame.strategySurvives ? "strategySurvives：是" : "strategySurvives：否"}</dd>
              </div>
              <div>
                <dt>早期预警</dt>
                <dd>{frame.earlyWarnings.join("；") || "无"}</dd>
              </div>
            </dl>
            {frame.confirmed ? (
              <small>已确认 · ScenarioVersion {frame.scenarioVersionId}</small>
            ) : editing === frame.id ? (
              <div className="scenario-modify">
                <label>
                  修改情景标题
                  <input
                    type="text"
                    value={modifiedTitle}
                    onChange={(event) => setModifiedTitle(event.target.value)}
                  />
                </label>
                <button
                  type="button"
                  onClick={() => submit(frame, modifiedTitle.trim() || frame.title)}
                >
                  以修改稿创建 ScenarioVersion
                </button>
              </div>
            ) : (
              <div className="scenario-actions">
                <button type="button" onClick={() => submit(frame, frame.title)}>
                  确认并创建 ScenarioVersion
                </button>
                <button
                  type="button"
                  className="text-action"
                  onClick={() => {
                    setEditing(frame.id);
                    setModifiedTitle(frame.title);
                  }}
                >
                  修改后再确认
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
