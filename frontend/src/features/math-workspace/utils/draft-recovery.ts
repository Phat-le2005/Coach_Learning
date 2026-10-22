import type { StoredPageDraft } from "../storage/indexeddb";
import type { InkStroke } from "../types";

export interface DraftPageMemory {
  strokes: InkStroke[];
  past: InkStroke[][];
  future: InkStroke[][];
  isDirty: boolean;
}

/** Restore only unsynchronized drafts; never replace ink edited since this page mounted. */
export function restoreDirtyPageDrafts(
  pages: ReadonlyMap<number, DraftPageMemory>,
  drafts: readonly StoredPageDraft[],
  locallyEditedPages: ReadonlySet<number>,
  maxPages: number,
): { pages: Map<number, DraftPageMemory>; restored: StoredPageDraft[] } {
  const next = new Map(pages);
  const restored: StoredPageDraft[] = [];
  for (const draft of drafts) {
    if (!draft.isDirty || !Number.isInteger(draft.pageIndex) || draft.pageIndex < 0 || draft.pageIndex >= maxPages) continue;
    if (locallyEditedPages.has(draft.pageIndex) || next.get(draft.pageIndex)?.isDirty) continue;
    next.set(draft.pageIndex, {
      strokes: draft.strokes,
      past: [],
      future: [],
      isDirty: true,
    });
    restored.push(draft);
  }
  return { pages: next, restored };
}

/** A document revision covers every page. A stale revision alone does not mean
 * this page changed. Rebase only when the server strokes are an exact prefix of
 * the local strokes (the normal append-only drawing case). Erasures or edits
 * against a changed page need an explicit user decision. */
export function canSafelyRebaseInkDraft(
  localStrokes: readonly InkStroke[],
  serverStrokes: readonly InkStroke[],
): boolean {
  if (serverStrokes.length > localStrokes.length) return false;
  return serverStrokes.every((serverStroke, index) => {
    const localStroke = localStrokes[index];
    if (!localStroke || serverStroke.id !== localStroke.id) return false;
    if (serverStroke.tool !== localStroke.tool || serverStroke.color !== localStroke.color || serverStroke.width !== localStroke.width) return false;
    if (serverStroke.points.length !== localStroke.points.length) return false;
    return serverStroke.points.every((point, pointIndex) => {
      const localPoint = localStroke.points[pointIndex];
      return localPoint && point.x === localPoint.x && point.y === localPoint.y
        && (point.pressure ?? 0.5) === (localPoint.pressure ?? 0.5);
    });
  });
}
