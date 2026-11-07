import type { InkStroke } from "../types";

export interface InkIntent {
  client_action_id: string;
  add: InkStroke[];
  remove: InkStroke[];
  createdAt: number;
}
export interface LiveSnapshot {
  document_revision: number;
  page_index: number;
  strokes: InkStroke[];
}

/** Fixed intent based on the visible page, never remove remote IDs not seen locally. */
export function inkDiff(before: InkStroke[], after: InkStroke[]): Pick<InkIntent, "add" | "remove"> {
  const previous = new Map(before.map(s => [s.id, s]));
  const next = new Map(after.map(s => [s.id, s]));
  for (const s of after) {
    if (previous.has(s.id) && JSON.stringify(previous.get(s.id)) !== JSON.stringify(s)) {
      throw new Error("Không thể thay đổi nội dung của stroke ID đã tồn tại.");
    }
  }
  return { add: after.filter(s => !previous.has(s.id)), remove: before.filter(s => !next.has(s.id)) };
}

export function replayIntents(canonical: InkStroke[], pending: InkIntent[]): InkStroke[] {
  const strokes = new Map(canonical.map(s => [s.id, s]));
  for (const intent of pending) {
    intent.remove.forEach(s => strokes.delete(s.id));
    intent.add.forEach(s => { if (!strokes.has(s.id)) strokes.set(s.id, s); });
  }
  return [...strokes.values()];
}
