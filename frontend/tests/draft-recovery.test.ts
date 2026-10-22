import assert from "node:assert/strict";
import test from "node:test";

import { canSafelyRebaseInkDraft, restoreDirtyPageDrafts } from "../src/features/math-workspace/utils/draft-recovery.js";
import type { StoredPageDraft } from "../src/features/math-workspace/storage/indexeddb.js";
import type { InkStroke } from "../src/features/math-workspace/types.js";

const stroke = { id: "local-stroke", tool: "PEN", color: "#000000", width: 2,
  points: [{ x: 0.1, y: 0.2, pressure: 0.5 }] } as InkStroke;
function draft(pageIndex: number, isDirty = true): StoredPageDraft {
  return { attemptId: "attempt", pageIndex, strokes: [stroke], documentRevision: 4,
    clientActionId: "action", isDirty, updatedAt: 1 };
}

test("recovers unsaved strokes over the server copy and restores additional pages", () => {
  const serverPage = { strokes: [], past: [], future: [], isDirty: false };
  const original = new Map([[0, serverPage]]);
  const result = restoreDirtyPageDrafts(original, [draft(0), draft(2)], new Set(), 30);
  assert.equal(result.restored.length, 2);
  assert.deepEqual(result.pages.get(0)?.strokes, [stroke]);
  assert.equal(result.pages.get(2)?.isDirty, true);
  assert.equal(original.get(0), serverPage);
});

test("does not overwrite newer in-memory edits or a clean local page", () => {
  const newer = { strokes: [], past: [], future: [], isDirty: true };
  const original = new Map([[0, newer]]);
  const result = restoreDirtyPageDrafts(original, [draft(0), draft(1), draft(2, false), draft(30)], new Set([1]), 30);
  assert.equal(result.restored.length, 0);
  assert.equal(result.pages.get(0), newer);
  assert.equal(result.pages.has(1), false);
  assert.equal(result.pages.has(2), false);
});

test("a recovered draft rebases over an unchanged or empty server page", () => {
  assert.equal(canSafelyRebaseInkDraft([stroke], []), true);
  assert.equal(canSafelyRebaseInkDraft([stroke], [stroke]), true);
});

test("an append-only draft preserves existing server ink despite a newer document revision", () => {
  const first = { id: "first", tool: "PEN", color: "#000000", width: 2,
    points: [{ x: 0.1, y: 0.2, pressure: 0.5 }] } as InkStroke;
  const second = { ...first, id: "second" };
  assert.equal(canSafelyRebaseInkDraft([first, second], [{ ...first }]), true);
});

test("a changed server stroke or a local erasure needs explicit conflict resolution", () => {
  const first = { id: "first", tool: "PEN", color: "#000000", width: 2,
    points: [{ x: 0.1, y: 0.2, pressure: 0.5 }] } as InkStroke;
  const changed = { ...first, points: [{ x: 0.4, y: 0.2, pressure: 0.5 }] };
  assert.equal(canSafelyRebaseInkDraft([first], [changed]), false);
  assert.equal(canSafelyRebaseInkDraft([], [first]), false);
  assert.equal(canSafelyRebaseInkDraft([first], [first, { ...first, id: "newer" }]), false);
});
