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


## Optional external online-ink samples (not MathCanvas-native)

MathWriting publishes a small excerpt of real online handwritten **single
mathematical expressions**: https://storage.googleapis.com/mathwriting_data/mathwriting-2024-excerpt.tgz .
Its data are CC BY-NC-SA 4.0; review the licence before use. The original
human splits are distinct from the dataset's programmatically composed
`synthetic/` samples. Do not commit downloaded samples to the repository.

PowerShell example from the repository root:

```powershell
New-Item -ItemType Directory -Force .tmp/tri-ocr-external | Out-Null
Invoke-WebRequest "https://storage.googleapis.com/mathwriting_data/mathwriting-2024-excerpt.tgz" -OutFile ".tmp/tri-ocr-external/mathwriting-excerpt.tgz"
python tools/ocr-fixtures/inkml_to_mathcanvas.py ".tmp/tri-ocr-external/mathwriting-excerpt.tgz" --output ".tmp/tri-ocr-external-fixtures" --limit 15
```

The converter writes normalized MathCanvas-style `InkStroke[]` inside a
`sourceKind: "INKML_EXTERNAL"` fixture, **not** an OcrEvalCaptureV1
segmentation snapshot. To evaluate it with the baseline, feed `strokes`
to `segmentPageInk_v2()` and add separate grouping annotations where
necessary. It preserves strokes as stroke paths, but normalizes their page
scale; it cannot reproduce original pen hardware, pressure, or a complete
multi-step student solution. Any InkML without clear human-split provenance
is marked `UNVERIFIED`, not falsely called human-written.

Real MathCanvas-native cases with Vietnamese prose, multi-line systems,
crossed-out edits and natural reading order still require direct captures
from willing test writers. A screenshot or AI-styled handwritten image
is not a substitute for native recorded ink.
