# Approved transcription handoff proposal — implementation 05.3

**Proposal for Phát; no evaluator agreement is implied.** Backend schemas and database remain unchanged. The existing `SolutionStepDraft` requires `step_type` and accepts `content_latex`, `explanation_text`, and optional `artifact`; it cannot transport the transcription graph or source references.

## Current local TypeScript contract

```ts
type ApprovedTranscriptionIR = SolutionTranscriptionIR & { reviewStatus: "APPROVED" };
// requireApprovedTranscriptionIR(json, originalPenStrokes) validates before narrowing.
// SolutionTranscriptionIR:
{
  schemaVersion: "1.1";
  attemptId?: string;                     // optional for local/offline review
  pageIndex: number;
  sourceKind: "INK";
  sourceRevision: number;                 // saved document revision in MathWorkspace
  sourceSnapshot: { strokes: InkStroke[] }; // physical pen strokes serialized once
  contentUnits: ContentUnit[];
  readingOrderStatus: "CONFIRMED";
  readingOrderWarnings: string[];
  constructionWarnings: string[];
  reviewStatus: "APPROVED";
  rawStrokeCount: number;
  recognizedUnitCount: number;
  approvedUnitCount: number;
  provenance: { createdAt: string; updatedAt: string; algorithm: string };
}
```

`ContentUnit` contains `id`, `pageIndex`, `role`, `kind`, `structureKind`, `sourceRegionIds`, `sourceStrokeIds`, sibling `readingOrder`, `childIds`, exact `bounds`, `rawRecognition`, `approvedContent`, `recognitionStatus`, `reviewStatus`, `isManuallyCorrected`, and `reasons`. The validator rejects schema 1.0 rather than interpreting an old QA artifact as the stronger 1.1 contract. There is no database migration.

## Structure and uncertainty

- `ATOMIC`: `MATH`, `TEXT`, or `UNKNOWN`; no children. Approval requires accepted nonempty content and resolved recognition/manual transcription. An approved `UNKNOWN` with manual text remains semantically unknown; the kind is never guessed to make projection pass.
- `CONTAINER`: `STRUCTURE`, nonempty children, explicit `SYSTEM`, `ALTERNATIVES`, `FRACTION`, `INDEPENDENT`, or `UNKNOWN` relation. No independent content string. `recognitionStatus = NOT_APPLICABLE`; approval confirms the relation only after every immediate child is approved. `UNKNOWN` relation cannot be confirmed.
- Atomic `UNRESOLVED` or skipped units remain in the draft and prevent whole-page approval. Original strokes always remain available. No stroke-only substitute is silently considered accepted text.
- Editing a child, its kind, a relation, or sibling order invalidates the dependent container approvals. OCR reruns update raw evidence without replacing manual content. A changed raw result without a manual correction requires review again.
- Roots derive from validated `childIds`, not IDs or array positions. Nested containers use the same rules (maximum depth 64). Sibling order is contiguous and independent of drawing chronology. Spatial proposals and ambiguous columns require explicit order confirmation.

## Required tracing for an eventual evaluator transport

Require attempt/source identity, page, **actual saved source revision**, source snapshot or immutable retrievable reference plus digest, unit IDs, region/stroke references, hierarchy, ordered presentation, raw and accepted content, unresolved states, and review provenance. Parent and child can reference the same ink; unrelated siblings cannot own the same physical strokes. Check the snapshot against the original source, not just against its own counts.

The current workspace propagates its saved document revision into the IR. Standalone offline constructors default to local snapshot revision 1 and must not claim it is a server revision. Local run manifests contain source/code/model SHA-256 values and the CoMER configuration; model version, reviewer identity, and an append-only correction audit are **not yet a durable evaluator transport contract**. Final agreement must specify these and the treatment of unreadable regions before persistence or submission.

## Grading boundaries and legacy adapter

Module G owns GradingStep boundaries and rubric/StepKind decisions. OCR approval does not establish mathematical correctness, a grading boundary, or evaluator readiness. A system's two equations are not automatically two grading steps. The learner reviews presentation and transcription without selecting StepKind.

`projectTranscriptionToLegacySteps()` is deliberately fail-closed: `mode=PREVIEW_ONLY`, `readyToSubmit=false`, `submitPayload=null`, `steps=[]`, `isProjectionBlocked=true`, and `allUnitsMapped=false`. `candidateUnits` retains every unit, including TEXT/UNKNOWN and container relations, for inspection. It is not an API payload. Reasons and warnings explain unresolved content and the absence of an explicit G mapping.

A future legacy mapping needs an explicit boundary decision and StepKind for every mapped span, a complete coverage check, a specified structure serializer/artifact, and an accounted-for treatment of all TEXT/UNKNOWN. The legacy schema otherwise loses hierarchy, stroke/source provenance, order uncertainty, recognition evidence, and review state. No partial step list is returned today; no IR action writes to the existing batch journal or backend.

## Reproducing the bounded verification

From `frontend`, run `npm test`, `npm run typecheck`, and `npm run build`. From the repository root, run `node tools/ocr-fixtures/run_transcription_slice.cjs` after test compilation.

Add `--legacy-regression` to run the existing human-review and F5 batch-recovery Playwright cases against the same isolated servers. These tests legitimately create grading steps in their own QA attempts; IR review scenarios separately assert zero API mutations, zero grading steps, and zero batch operations.

The browser runner uses the existing dedicated QA environment/helper, rejects occupied ports 3003/8003, launches the actual Next.js application and backend on those ports, and runs the actual bundled CoMER in Chrome. It requires the gitignored `.tmp/tri-ocr-native/integral_case_01.json` fixture; it does not embed or commit handwriting or credentials. Results go to `.tmp/tri-ocr-core-impl053/`.

Evidence is separated as REAL_INK (one existing integral), SYNTHETIC_INK (a four-line calculus page drawn through MathCanvas pointer events and a geometry-only two-child system), MODEL_OUTPUT (unmocked CoMER), and MANUAL_CORRECTION (simulated review). Native integral transcription has no independently annotated ground truth; its partial visual correction and simulated acceptance do not certify OCR accuracy. **REAL_MULTI_LINE_NOT_VERIFIED** remains until native multi-line handwriting is available and replayed.
