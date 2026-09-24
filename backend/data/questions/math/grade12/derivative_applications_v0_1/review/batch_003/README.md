# DATA-MATH12-005 — Review batch 003

Scope: Toán 12 — Ứng dụng đạo hàm để khảo sát và vẽ đồ thị của hàm số.

## Result

Batch 003 reviews 25 additional DATA-004 candidates:

- 3 VERIFIED
- 11 HOLD
  - 10 `HOLD_VISUAL_SOURCE_REVIEW`
  - 1 `HOLD_CONTENT_EXTRACTION_CORRUPT`
- 11 `REJECTED_DUPLICATE`

Cumulative state after batches 001–003:

- 80 / 175 candidates reviewed
- 28 VERIFIED
- 21 HOLD
- 31 REJECTED
- 95 untouched `REVIEW_REQUIRED`

## Why visual questions are held

For batch 003, the source text/solution can identify an answer for several graph or variation-table questions, but the extracted text does not preserve the actual graph/table. They are therefore **not** marked VERIFIED yet.

A visual-dependent question is only eligible for later VERIFIED review after:
1. the original PDF page is inspected;
2. the exact graph/table is cropped or linked as an asset;
3. question text and answer are checked against that asset.

This is stricter than trusting the source answer key alone.

## Text-only VERIFIED questions

- `M12_DERIV_CAND_0013` → answer `12`
- `M12_DERIV_CAND_0032` → answer `95`
- `M12_DERIV_CAND_0059` → answer `100`

All three are real-world derivative optimization problems. Source solutions and independent derivative checks agree.

## Duplicate handling

Duplicate records are not deleted from raw staging. Their review overlay becomes `REJECTED_DUPLICATE` and points directly to the retained candidate using `duplicate_of_candidate_id`.

## Promotion boundary

`VERIFIED` is still a review-layer status only. All VERIFIED records keep `promotion_ready=false`.
