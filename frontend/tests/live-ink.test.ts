import test from "node:test";
import assert from "node:assert/strict";
import { inkDiff, replayIntents, type InkIntent } from "../src/features/math-workspace/live/protocol";
import { normalizeCoordinate } from "../src/features/math-workspace/utils/ink-math";
import type { InkStroke } from "../src/features/math-workspace/types";

const stroke = (id: string): InkStroke => ({ id, tool: "PEN", color: "#123456", width: 2, points: [{ x: .2, y: .3, pressure: .5 }] });
test("mobile and desktop coordinates share the same normalized page", () => {
  assert.equal(normalizeCoordinate(40, 200), normalizeCoordinate(158.8, 794));
  assert.equal(normalizeCoordinate(60, 200), .3);
});
test("operation replay preserves unseen concurrent ink and deduplicates acknowledgements", () => {
  const a = stroke("a"), b = stroke("b"), c = stroke("c");
  const intent: InkIntent = { ...inkDiff([a], [a, b]), createdAt: 1, client_action_id: "one" };
  assert.deepEqual(replayIntents([a, c], [intent]), [a, c, b]);
  assert.deepEqual(replayIntents([a, c, b], [intent]), [a, c, b]);
  const erase: InkIntent = { ...inkDiff([a, b], []), createdAt: 2, client_action_id: "two" };
  assert.deepEqual(replayIntents([a, c, b], [erase]), [c]);
});
test("undo fixed local intent cannot restore a whole stale page over remote edits", () => {
  const a = stroke("a"), b = stroke("b");
  const inverse: InkIntent = { add: [], remove: [a], createdAt: 1, client_action_id: "undo" };
  assert.deepEqual(replayIntents([a, b], [inverse]), [b]);
  assert.throws(() => inkDiff([a], [{ ...a, width: 4 }]), /stroke ID/);
});

test("stale observed canvas never deletes a newer remote stroke on local pointerup", () => {
  const prior = stroke("prior"), remote = stroke("remote"), local = stroke("local");
  // The UI was showing only 'prior' when the finger began drawing.
  // Remote commit arrives before React can rerender the visible canvas.
  const intent: InkIntent = {
    ...inkDiff([prior], [prior, local]), createdAt: 3, client_action_id: "local-draw",
  };
  assert.deepEqual(intent.remove, []);
  assert.deepEqual(replayIntents([prior, remote], [intent]).map(s => s.id),
    ["prior", "remote", "local"]);
});

test("stale observed clear/eraser never removes remote strokes not seen by the user", () => {
  const prior = stroke("prior"), remote = stroke("remote");
  const intent: InkIntent = {
    ...inkDiff([prior], []), createdAt: 4, client_action_id: "local-clear",
  };
  assert.deepEqual(intent.remove.map(s => s.id), ["prior"]);
  assert.deepEqual(replayIntents([prior, remote], [intent]).map(s => s.id), ["remote"]);
});
