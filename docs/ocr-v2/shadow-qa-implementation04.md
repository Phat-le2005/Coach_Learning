# MathCanvas OCR V2 — Implementation 04: shadow QA

## Scope

This is a **development-only inspection** of the structural prototype, not a
change to student OCR or grading. The page review dialog keeps its existing
segmentation, CoMER, step drafts, merge/split controls, batch saving and
recovery behavior. The shadow panel is mounted only after a QA user clicks
**Xem đề xuất cấu trúc (QA)** when `NODE_ENV !== "production"`.

The panel compares the original page ink against the **initial** page
segmentation snapshot; it does not re-run on user-edited review rows. It shows
top-level candidates, source stroke counts, their child nodes, baseline region
overlap by stroke ID, and missing/repeated ink diagnostics. Child stroke IDs
may also appear in the parent by design; conservation checks use top-level
candidates only. A proposed group is not a ground-truth solution step.

**No save/confirm/reorder callbacks are passed to the QA panel.** It makes no
API calls, and does not automatically rewrite OCR drafts or transmit ink.

## QA workflow for MathCanvas-native handwriting

1. Run the local frontend in an authorized development/test environment.
2. Write one genuine example on MathCanvas, e.g. a brace with two equations,
   a square bracket with branches, a fraction, or two unrelated lines.
3. Open **Trích xuất trang**, expand **Xem đề xuất cấu trúc (QA)**.
4. Compare each proposed group to the original pen preview and overlapping
   baseline regions; note false splits/merges. Do not treat a high heuristic
   score as a calibrated accuracy estimate.
5. Use the separate **Xuất nét và phân vùng (QA)** action to save the initial
   capture locally if needed for reproducible regression tests.
6. Keep 3–5 consenting MathCanvas-native cases under a gitignored `.tmp/`
   directory; do not publish personal handwriting or account information.
7. Label system/alternative/independent cases separately from predictions,
   and retain at least one held-out case. The MathWriting 15-expression pilot
   has no confirmed positive handwritten two-line SYSTEM fixture.

## Offline evaluation of external InkML fixtures

1. Use the existing InkML converter CLI to convert the selected samples into
   `INKML_EXTERNAL` JSON under `.tmp/`. Keep the source selection manifest.
2. From the repository root:

```bash
cd frontend
npm run test:compile
cd ..
node tools/ocr-fixtures/run_shadow_batch.cjs \
  .tmp/tri-ocr-external-fixtures \
  .tmp/tri-ocr-shadow-results
```

3. Inspect `.tmp/tri-ocr-shadow-results/shadow_batch.json`. It records
   `gitHead`, SHA-256 hashes for loaded compiled JS and source TS, input
   fixture hashes, initial baseline regions and shadow candidates. Do not
   compare timestamps or pretend that this JSON is structural ground truth.
   Use the **same SHA-256 file hashes** when comparing runs. Fresh compilation
   is required; this runner records hashes but cannot prove a particular
   compiled artifact came from a source version without a trusted build.

No dataset, student capture or generated output belongs in Git.
This runner does not download data, run any cloud AI service, or submit results.

## Verification and integration gates

- `cd frontend && npm test && npm run typecheck && npm run build`
- Confirm **no QA controls in production** and that opening/closing the panel
  does not change current review rows, approved drafts or batch recovery.
- Verify at least one true positive handwritten SYSTEM and negatives such as
  integral, matrix parenthesis, isolated tall stroke, and independent columns.
- Do **not** enable the structural engine for the normal student flow until
  that acceptance work and review are complete.

Known limitations: top-level classification is a heuristic, matrix/root
relations and nested expressions are incomplete, and the panel shows
proposals but does not annotate or edit the structural tree.
