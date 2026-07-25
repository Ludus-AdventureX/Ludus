// Task 13 Step 6: named experiment branches — save, compare, non-destructive
// rollback. Secondary flow: lives outside the default stress-test surface.
// Rollback only restores the working copy; no branch is ever deleted.

import type { ExperimentBranch } from "./types";

type BranchTimelineProps = {
  branches: ExperimentBranch[];
  onRollback: (branch: ExperimentBranch) => void;
};

export function BranchTimeline({ branches, onRollback }: BranchTimelineProps) {
  if (branches.length === 0) {
    return (
      <section className="branch-timeline" aria-label="实验分支">
        <p>尚未保存命名实验。运行压力测试后可保存实验分支。</p>
      </section>
    );
  }
  return (
    <section className="branch-timeline" aria-label="实验分支">
      <header className="section-line-heading">
        <div>
          <span>命名实验</span>
          <h3>分支时间线</h3>
        </div>
        <small>回滚是非破坏性的：只恢复工作副本，不删除分支</small>
      </header>
      <ol className="branch-list">
        {branches.map((branch) => (
          <li key={branch.id} data-branch-id={branch.id}>
            <b>{branch.name}</b>
            <small>{branch.summary}</small>
            <button type="button" onClick={() => onRollback(branch)}>
              回滚到此分支
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}
