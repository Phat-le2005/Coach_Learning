# DATA-MATH12-005 — Review batch 002

Scope: Grade 12 Mathematics — `Ứng dụng đạo hàm để khảo sát và vẽ đồ thị của hàm số`.

## Batch result

- 39 additional candidates reviewed.
- 13 VERIFIED.
- 8 HOLD.
- 18 REJECTED.
  - 12 duplicate extraction records.
  - 6 out-of-scope records.

After batch 001 + batch 002:
- 55 / 175 candidates have review decisions.
- 25 VERIFIED.
- 10 HOLD.
- 20 REJECTED.
- 120 untouched candidates remain.

## Important quality findings

### Primary-source provenance
Candidates `0003`, `0007`, `0009` come from a secondary solution compilation that contains official 2025 exam material.
Their mathematics/content was checked, but they remain `HOLD_PRIMARY_SOURCE_CROSSCHECK` because the source catalog requires primary MOET cross-check before VERIFIED.

### Misdetected question type
Candidates `0012`, `0019`, `0035`, `0047`, `0052` contain four statements a/b/c/d.
They were extracted as `SHORT_ANSWER`, but must be handled as `TRUE_FALSE_GROUP` / `QuestionGroup`.
They remain review-only.

### Duplicate extraction
12 records are rejected as duplicate question instances. The original provenance is kept, and `duplicate_of_candidate_id` points to the retained review record.

### Out-of-scope routing
- Advertising-area and road-area questions are routed to `M12_CORE_CALCULUS_ANTIDERIVATIVE_INTEGRAL`.
- Oxyz/mặt cầu questions are routed to `M12_CORE_GEOMETRY_COORDINATE_3D`.

### Visual questions
All 13 new VERIFIED questions depend on a graph or variation table.
They are academically reviewed but are **not production-ready** until a visual asset pipeline exists.
Each record contains `visual_asset_required=true` and `visual_source_page`.

## Promotion boundary

`VERIFIED` means the source, answer, and taxonomy mapping passed review.
It does not mean production import is allowed.

All VERIFIED records in this batch keep:
`promotion_ready=false`.
