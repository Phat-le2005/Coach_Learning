import test from "node:test";
import assert from "node:assert/strict";

import { ensureLatestInkSaved } from "../src/features/math-workspace/utils/ocr-sync.js";

test("OCR skips flush when ink already matches server", async () => {
  let saves = 0;
  const ok = await ensureLatestInkSaved(false, async () => {
    saves += 1;
    return true;
  });
  assert.equal(ok, true);
  assert.equal(saves, 0);
});

test("OCR proceeds only after an unsaved page is persisted", async () => {
  let saves = 0;
  const ok = await ensureLatestInkSaved(true, async () => {
    saves += 1;
    return true;
  });
  assert.equal(ok, true);
  assert.equal(saves, 1);
});

test("OCR must not proceed if save failed or has revision conflict", async () => {
  for (const result of [false]) {
    let saves = 0;
    const ok = await ensureLatestInkSaved(true, async () => {
      saves += 1;
      return result;
    });
    assert.equal(ok, false);
    assert.equal(saves, 1);
  }
});

test("OCR does not swallow storage or network failures", async () => {
  await assert.rejects(
    ensureLatestInkSaved(true, async () => {
      throw new Error("local draft unavailable");
    }),
    /local draft unavailable/,
  );
});
