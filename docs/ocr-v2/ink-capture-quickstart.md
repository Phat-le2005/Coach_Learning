# MathCanvas OCR V2 — Dev-only ink capture (PR30-A slice 1)

This is the smallest addition needed to keep a real handwriting segmentation failure for later replay and comparison. It does **not** replace segmentation, change OCR, grade math, or send data to any remote service.

## Capture a real case

1. Start the frontend in **development** mode against an authorized local/test environment.
2. Write a math expression on MathCanvas (try a brace and two equations or text mixed with a formula).
3. Open the existing page OCR review dialog. Click **Xuất nét và phân vùng (QA)**.
4. The browser downloads `ocr-ink-page-N.json`. It includes the original page strokes (including highlights), initial v2 segmentation regions and three diagnostic ID lists.
5. Store captures locally in a gitignored directory (for example `.tmp/tri-ocr-captures/`). **Do not commit, upload, or share a student's handwriting without appropriate permission.** The file may contain personally identifying handwriting even though it does not include account/attempt identifiers.
6. Record separately what the handwriting actually means and which strokes belong together. The exported segmentation is the **prediction**, never the ground truth.

## File format

`schemaVersion: 1`, `sourceKind: "MATHCANVAS_INK"`, `pageIndex`, `strokes`, `segmentation` and `diagnostics`.

- `strokes` is a full deep-copied snapshot of the ink provided to the review dialog.
- `segmentation.algorithm` is `v2`, with each region's ID, bounds and associated stroke IDs.
- `diagnostics.missingPenStrokeIds` lists active pen strokes absent from all regions.
- `diagnostics.repeatedPenStrokeIds` lists active pen strokes mapped to more than one region.
- `diagnostics.unknownRegionStrokeIds` lists IDs referenced by regions that are not active pen ink in the snapshot.

**Important:** A semantically wrong split can still have all three diagnostic arrays empty. These checks cover stroke mapping integrity, **not mathematical correctness or grouping quality**.

The capture intentionally does not include student identity, attempt ID, exercise answer, timestamps, LaTeX, or a ground-truth annotation. It also cannot recover historical pen edits that the current page state no longer contains.

## Verification

Run the existing frontend test command:

```sh
cd frontend
npm test
```

The new `ocr-eval-capture.test.ts` tests snapshot immutability, complete ink preservation, missing/repeated/unknown region references, and invalid page indices.

This is **slice 1**, not the complete Evaluation Lab. Next steps are a validator/reader for captured JSON, ground-truth labeling, replay, and baseline comparisons on consented real handwriting.
