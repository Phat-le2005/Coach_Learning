# DATA-MATH12-011 — Promotion eligibility + canonical QuestionGroup snapshot v0.1

Base commit: `cc24bbf1f09f8bff9a2e81a6235b8682c755f4e9`

This bundle is the promotion-policy decision layer after:
- academic QuestionGroup review: **67/67 complete**
- VERIFIED QuestionGroups: **39**
- visual registry: **8 READY / 1 source visual missing**

## Result

- Academic VERIFIED: **39 groups / 156 children**
- Internal canonical snapshot ready: **38 groups / 152 children**
- Snapshot blocked by missing source visual: **1 group (`M12_DERIV_GROUP_0012`)**
- Production release eligible: **0**
- Database import ready: **0**

### Why production remains blocked

Every current source is still `rights_status=REVIEW_REQUIRED`.
The derivative curriculum taxonomy is still a staging artifact, not the canonical imported curriculum.
The repository has a Question import pipeline but no trusted QuestionGroup import/promotion lifecycle.
The DB requires `difficulty` and `exam_weight`; this reviewed dataset does not contain a reviewed policy for those fields.

This bundle intentionally does **not** invent those values and does not turn review-layer `promotion_ready` on.

## Canonical snapshot rule

38 groups are technically complete enough to materialize into an immutable internal canonical snapshot:
- 30 do not need a visual;
- 8 have a READY source-crop visual;
- `0012` remains excluded because its authentic diagram is absent from the available source PDF.

The snapshot preserves the TRUE/FALSE group as one group plus four child questions.
It must not flatten the group and lose MOET TRUE/FALSE scoring semantics.

## Files

- `promotion_manifest.json`: group-level promotion decisions
- `promotion_stats.json`: expected exact counts
- `promotion_policy.json`: gates and forbidden inference
- `CANONICAL_SNAPSHOT_SCHEMA.md`: deterministic materialization contract
- `CODEX_INTEGRATION_PROMPT.md`: integration task for Codex
