// Conflict list (Task 11 B2): renders ConflictListView for a run. Conflicts
// are presented as explicit from/to pairs with the recorded rationale; the
// UI never averages the two sides or declares a winner
// (04-decision-methodology.md「冲突处理」: unresolved conflicts stay visible).

import type { ConflictRelationView, EvidenceItemView } from "@/lib/api/evidence";

type ConflictListProps = {
  conflicts: ConflictRelationView[];
  /** Items of the same run, used to show readable titles next to raw ids. */
  itemsById: Map<string, EvidenceItemView>;
};

function itemLabel(itemsById: Map<string, EvidenceItemView>, evidenceItemId: string): string {
  return itemsById.get(evidenceItemId)?.title ?? evidenceItemId;
}

export function ConflictList({ conflicts, itemsById }: ConflictListProps) {
  return (
    <section className="evidence-conflicts" aria-label="冲突列表">
      <header>
        <h3>冲突</h3>
        <p>相反信息不做强行平均；未对齐口径前不视为已解决。</p>
      </header>
      {conflicts.length === 0 ? (
        <p className="conflicts-empty">该 Run 没有已记录的证据冲突。</p>
      ) : (
        <ul className="conflict-list">
          {conflicts.map((conflict) => (
            <li key={conflict.id} className="conflict-entry" data-conflict-id={conflict.id}>
              <p>
                <b>{itemLabel(itemsById, conflict.fromEvidenceItemId)}</b>
                <span aria-hidden="true">{" ⇄ "}</span>
                <b>{itemLabel(itemsById, conflict.toEvidenceItemId)}</b>
              </p>
              {conflict.groupId && <small>{`冲突组 ${conflict.groupId}`}</small>}
              {conflict.rationale ? (
                <p className="conflict-rationale">{conflict.rationale}</p>
              ) : (
                <p className="conflict-rationale-missing">该冲突尚无解释记录；发布门要求冲突组必须有解释。</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
