# DATA-MATH12-021 — Grouped-data dispersion academic curation

This directory is curated academic data. Application code should adapt to the dataset contract, not redefine academic decisions.

## Final curation decisions

- 41 source candidates reviewed.
- 38 standalone candidates are VERIFIED from source question/solution evidence.
- M12_DISP_CAND_0014 is REJECTED_DUPLICATE of M12_DISP_CAND_0015 because their normalized question text is identical; the canonical source-backed answer B is retained on 0015.
- M12_DISP_GROUP_0032 has source-backed key: True, False, False, True.
- M12_DISP_GROUP_0035 has source-backed key: True, False, True, False.
- Both TRUE_FALSE_FOUR groups remain HOLD_MIXED_SCOPE because only one child in each group belongs to grouped-data dispersion; the other children are descriptive-statistics or probability content.
- Five taxonomy problem-type gaps remain real evidence gaps. No synthetic questions are created.
- Rights review and visual-asset review are still required before promotion.
- No database import or canonical snapshot is allowed in DATA-MATH12-021.

## Implementation boundary

Implementation work may repair validators, schemas, tests, importers, and integration code around this dataset. It should not rewrite curated answers, duplicate decisions, taxonomy decisions, source evidence, review statuses, or coverage gaps.
