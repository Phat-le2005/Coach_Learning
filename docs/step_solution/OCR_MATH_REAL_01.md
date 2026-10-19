# OCR-MATH-REAL-01 — Mathpix Strokes (first real-provider slice)

## What this does
EduMS receives normalized vector ink in PostgreSQL. The Mathpix adapter sends only `PEN` x/y coordinates (scaled to the A4 canvas reference) to the documented `POST https://api.mathpix.com/v3/strokes` endpoint, then returns the provider's actual recognized LaTeX. `HIGHLIGHTER` annotation strokes are omitted. Student confirmation before creating a solution step remains required.

This is **real provider integration**, not a claim that math handwriting recognition is accurate enough for deployment. No genuine handwriting benchmark or live credential-based acceptance test has yet been run.

## Configuration
In `backend/.env` (never in frontend or committed to Git):

```ini
MATH_OCR_PROVIDER=mathpix
MATHPIX_APP_ID=<your-app-id>
MATHPIX_APP_KEY=<your-app-key>
MATH_OCR_TIMEOUT_SECONDS=12
```

The default `MATH_OCR_PROVIDER=disabled` returns a controlled 503. Local demonstrations may set `mock`, but production must **never** serve fabricated Mock OCR. In `APP_ENV=test`, the existing test-only mock is retained to avoid destabilizing contract tests.

The backend sends `metadata.improve_mathpix=false` on every real OCR request, so Mathpix documents that it will not store submitted ink content/results for quality improvements; its billing/audit metadata may still be retained. **Before enabling on student data**, verify school/guardian consent and vendor data-processing terms, region, retention and institutional privacy requirements.

## Errors and limits
- Missing provider settings: `503 OCR_NOT_CONFIGURED`
- Invalid credentials: `503 OCR_PROVIDER_AUTH_FAILED`
- Rate limited: `503 OCR_PROVIDER_BUSY`
- Provider timeout: `504 OCR_PROVIDER_TIMEOUT`
- Empty math result: `422 OCR_NOT_RECOGNIZED`
- Unavailable/invalid provider responses: `502/503`
- Oversized requests: `413 OCR_STROKES_TOO_LARGE`

Requests are capped below Mathpix's 512-KiB strokes limit and streamed responses are capped to 64 KiB. The backend uses a fixed HTTPS endpoint and does not follow redirects. Mathpix credentials are server-only, and neither them nor submitted ink are logged.

## Acceptance gates
1. Set genuine Mathpix credentials in a secure deployment and run authorized end-to-end handwriting tests on multiple student-written expressions (different handwriting styles, fractions, radicals, integrals, derivatives, exponents, multiple lines).
2. Build a consented golden dataset; record expression exact match, symbol edit distance, and corrections made at the confirmation modal; compare with a MyScript baseline.
3. Prefer sending one expression (selected `stroke_ids`) rather than full pages. Mathpix returns LaTeX arrays for multiple lines. The current endpoint preserves that provider output; auto-segmentation is a future feature.
4. Handle provider outages, request budgets, quota alerts, and per-student rate limits before switching the provider on at scale.
5. Preserve human confirmation; no OCR response is evidence of mathematical correctness by itself.

References: https://docs.mathpix.com/guides/strokes and https://docs.mathpix.com/concepts/privacy
