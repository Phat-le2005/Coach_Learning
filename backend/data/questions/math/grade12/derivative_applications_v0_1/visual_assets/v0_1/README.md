# DATA-MATH12-010 - Derivative chapter visual assets v0.1

Base commit: `1ea4cd17a841f6b503a1eccbdd67f5cb3b91fcf1`.

This bundle resolves the visual-media layer for the 9 academically VERIFIED QuestionGroups that currently have `visual_asset_required=true`. It does **not** change academic review decisions and does **not** enable promotion.

## Result

- Visual-required groups: 9
- Exact source crops available: 8
- Source visual still missing: 1 (`M12_DERIV_GROUP_0012`)
- Rights status cleared: 0
- Promotion eligible: 0

### READY_SOURCE_CROP

- `0024` - function graph - Hà Tĩnh 2025, source page 39
- `0070` - function graph - Trương Ngọc Vỹ test 05, page 81
- `0087` - variation table - test 10, page 179
- `0089` - derivative graph - test 11, page 198
- `0113` - variation table - test 20, page 379
- `0154` - derivative graph - test 34, page 644
- `0163` - function graph - test 37, canonical question page 701 (the structural candidate itself came from solution page 708)
- `0170` - derivative-sign table - test 39, page 740

Each PNG is a direct crop from a rendered source PDF page at 200 DPI. The manifest stores the asset SHA-256, image dimensions, source PDF SHA-256, source page, and PDF-point crop box.

### BLOCKED_SOURCE_VISUAL_MISSING

`M12_DERIV_GROUP_0012` is the Huế 2025 swimming-pool problem. The reviewed source text explicitly refers to a figure, but the available compilation PDF does not display that figure on question page 3 or solution pages 11-13. This bundle deliberately does not fabricate or redraw the diagram. A future recovery pass must obtain a stable primary/authorized source visual and record its provenance before this group can be visually resolved.

## Rights boundary

Both source catalog entries currently have `rights_status=REVIEW_REQUIRED`. Therefore a source crop being technically available is **not** the same as being cleared for production distribution. All 9 manifest rows preserve `rights_status=REVIEW_REQUIRED` and `promotion_eligible=false`.

## Integration rule

Integrate this as a separate immutable visual-asset registry. Do not edit raw candidates, structural staging, academic review records, or set `promotion_ready=true` in this change.
