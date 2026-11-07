# Core OCR V2 — Implementation 05, increment 1: integral expression grouping

## What actually changed

`proposeIntegralExpressionUnits(strokes)` returns a **read-only geometric
proposal** when it detects an integral-like tall stroke, an upper limit, a
lower limit, and an adjacent right-hand expression. The proposal includes
the source stroke IDs for the integral sign, each limit and the expression
body, plus its composite bounding box. It does not invent LaTeX, correct
math, call CoMER, change `segmentPageInk_v2`, or save student solution steps.

The developer-only Shadow QA modal shows these proposals separately from the
existing structural candidates. Its normal OCR review and batch-save behavior
is unchanged.

### Native handwritten integral captured from MathCanvas

The local QA fixture `.tmp/tri-ocr-native/integral_case_01.json` contains
10 pen strokes: one integral sign, one upper limit, one lower limit and
seven expression strokes. Its existing segmentation still produces four
regions. **The expected new behavior is one optional integral expression
proposal referencing all ten original strokes**, not a change to the
four baseline regions.

To verify locally, from the repo root:

```bash
cd frontend
npm test
npm run typecheck
npm run build
cd ..
node tools/ocr-fixtures/run_real_ink_qa.cjs
```

The CLI requires the local private fixture; it fails closed when absent.
For explicitly mandatory unit acceptance on real handwriting, run
`OCR_REAL_INK_REQUIRED=1 npm test` (PowerShell: set
`$env:OCR_REAL_INK_REQUIRED='1'` first). A normal clean clone should be able
to run `npm test` without private user ink; the real-ink test reports SKIP,
not PASS, if its fixture is missing. The runner writes
`expression_reconstruction.json` under `.tmp/tri-ocr-qa-impl045/`.

### Boundaries and expected failures

This is a constrained pilot, not an integral recognizer. It uses geometric
evidence and requires *both* limits. It intentionally abstains on
indefinite integrals, disconnected/ambiguous ink, roots, matrices, and
non-integral expressions. Long gaps may cause conservative truncation;
tight unrelated neighboring expressions may still cause false merges.
Do not use these proposals as approved transcriptions.

Positive evidence on the **single known real integral** is not enough to
claim real-world recall or precision. The unit suite also includes
synthetic negatives (curly brace, missing limits, distant second column)
and temporal-order permutations. Keep independent held-out handwriting
for subsequent evaluation.

## QA and security prerequisites

This branch is stacked on draft PR #32; it depends on PR #31 and PR #30.
The earlier QA browser script was changed to provision a fresh isolated QA
attempt through the existing PostgreSQL QA helper and to load credentials
from the gitignored `.tmp/tri-ocr-e2e/.qa-e2e.env`, not from source code.
The script draws synthetic pointer strokes on the fresh QA attempt to
test the real UI, and must not report those strokes as native handwriting
recognition evidence.

**Important:** The old version of PR #32 was committed to a public
repository with a demo password in source. That value must be
revoked/rotated by the account owner; removing it from the latest file
does not erase Git history. Never reuse that credential.

## Next engineering increment

After local tests: expand expression reconstruction to simple radicals and
fractions, followed by a data model separating expression units from solution
steps. Only then consider routing expression units through recognizers and
student review behind a feature flag. Keep the current production path intact.
