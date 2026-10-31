import test from "node:test";
import assert from "node:assert/strict";
import {
  createOcrReviewDraft, applyOcrToDraft, editOcrReviewDraft,
  selectOcrDraftKind, canApproveOcrDraft, approveOcrDraft, skipOcrDraft,
  mergeOcrReviewDrafts, splitOcrReviewDraft, reorderOcrReviewDrafts,
} from "../src/features/math-workspace/utils/ocr-review-draft.js";

const source = (id: string) => ({ localId: id, pageIndex: 0, regionIds: [id], strokeIds: [id + '-stroke'] });

test('new draft is unresolved, not silently labeled EXPLANATION', () => {
  const draft = createOcrReviewDraft(source('a'));
  assert.equal(draft.selectedStepKind, null);
  assert.equal(draft.reviewStatus, 'NEEDS_REVIEW');
  assert.equal(canApproveOcrDraft(draft), false);
});

test('OCR suggests a kind but stores raw recognition separately', () => {
  const draft = applyOcrToDraft(createOcrReviewDraft(source('a')), "y' = 3x^2 - 6x");
  assert.equal(draft.selectedStepKind, 'DERIVATIVE_CALCULATION');
  assert.equal(draft.stepKindSource, 'SUGGESTED');
  assert.equal(draft.rawOcrLatex, "y' = 3x^2 - 6x");
  assert.equal(draft.contentLatex, draft.rawOcrLatex);
});

test('manual math correction and chosen kind are never overwritten by later OCR', () => {
  let draft = applyOcrToDraft(createOcrReviewDraft(source('a')), "y' = 3x^2 - 6x");
  draft = editOcrReviewDraft(draft, { contentLatex: "y' = 3x^2 + 6x" });
  draft = selectOcrDraftKind(draft, 'CUSTOM');
  const retry = applyOcrToDraft(draft, 'x=0');
  assert.equal(retry.contentLatex, "y' = 3x^2 + 6x");
  assert.equal(retry.rawOcrLatex, 'x=0');
  assert.equal(retry.selectedStepKind, 'CUSTOM');
  assert.equal(retry.stepKindSource, 'MANUAL');
});

test('ambiguous x=2 requires a conscious type selection', () => {
  const draft = applyOcrToDraft(createOcrReviewDraft(source('a')), 'x = 2');
  assert.equal(draft.classification.status, 'ABSTAIN');
  assert.equal(draft.selectedStepKind, null);
  assert.throws(() => approveOcrDraft(draft), /OCR_DRAFT_NOT_READY/);
  const approved = approveOcrDraft(selectOcrDraftKind(draft, 'ROOT_FINDING'));
  assert.equal(approved.reviewStatus, 'APPROVED');
});

test('student edits invalidate approval, previously confirmed OCR cannot overwrite it', () => {
  let draft = applyOcrToDraft(createOcrReviewDraft(source('a')), "y'=2x");
  draft = approveOcrDraft(draft);
  assert.strictEqual(applyOcrToDraft(draft, 'x=0'), draft);
  draft = editOcrReviewDraft(draft, { explanationText: 'Đạo hàm của hàm số.' });
  assert.equal(draft.reviewStatus, 'NEEDS_REVIEW');
});

test('merge preserves source identities without automatically approving or inventing kind', () => {
  const a = applyOcrToDraft(createOcrReviewDraft(source('a')), '3x^2-6x=0');
  const b = applyOcrToDraft(createOcrReviewDraft(source('b')), '\\Leftrightarrow x=0');
  const m = mergeOcrReviewDrafts(a,b,'combined');
  assert.deepEqual(m.sourceRegionIds, ['a','b']);
  assert.deepEqual(m.sourceStrokeIds, ['a-stroke','b-stroke']);
  assert.equal(m.selectedStepKind, null);
  assert.equal(m.reviewStatus,'NEEDS_REVIEW');
  assert.match(m.contentLatex, /Leftrightarrow/);
});

test('split uses explicitly supplied expressions and retains ink references', () => {
  const original = applyOcrToDraft(createOcrReviewDraft(source('a')), "y'=3x^2-6x=0");
  const [a,b] = splitOcrReviewDraft(original,
    {localId:'a-1', contentLatex:"y'=3x^2-6x"},
    {localId:'a-2', contentLatex:'3x^2-6x=0'});
  assert.deepEqual(a.sourceStrokeIds,['a-stroke']);
  assert.deepEqual(b.sourceStrokeIds,['a-stroke']);
  assert.notEqual(a.localId,b.localId);
  assert.equal(a.reviewStatus,'NEEDS_REVIEW');
  assert.equal(b.reviewStatus,'NEEDS_REVIEW');
});

test('cross-page merge is rejected', () => {
  const a=createOcrReviewDraft(source('a'));
  const b=createOcrReviewDraft({...source('b'),pageIndex:1});
  assert.throws(()=>mergeOcrReviewDrafts(a,b,'m'),/DIFFERENT_PAGES/);
});

test('skipping a draft prevents approval', () => {
  const draft=skipOcrDraft(applyOcrToDraft(createOcrReviewDraft(source('a')),"y'=2x"));
  assert.equal(canApproveOcrDraft(draft),false);
  assert.throws(()=>approveOcrDraft(draft),/OCR_DRAFT_NOT_READY/);
});

test('reorder is immutable and rejects invalid indices', () => {
  const a=createOcrReviewDraft(source('a')), b=createOcrReviewDraft(source('b'));
  const original=[a,b];
  const changed=reorderOcrReviewDrafts(original,0,1);
  assert.deepEqual(changed.map(d=>d.localId),['b','a']);
  assert.deepEqual(original.map(d=>d.localId),['a','b']);
  assert.deepEqual(reorderOcrReviewDrafts(original,9,0),original);
});

test('whitespace-only content cannot be approved even with selected kind', () => {
  let draft = createOcrReviewDraft(source('a'));
  draft = editOcrReviewDraft(draft, { contentLatex: "   ", explanationText: "   " });
  draft = selectOcrDraftKind(draft, 'EXPLANATION');
  assert.equal(canApproveOcrDraft(draft), false);
  assert.throws(() => approveOcrDraft(draft), /OCR_DRAFT_NOT_READY/);
});

test('explanation-only draft without LaTeX can be approved when kind is selected', () => {
  let draft = createOcrReviewDraft(source('a'));
  draft = editOcrReviewDraft(draft, { contentLatex: "", explanationText: "Hàm số đồng biến trên R." });
  assert.equal(draft.classification.status, 'DETERMINED');
  assert.equal(draft.selectedStepKind, 'CONCLUSION');
  assert.equal(canApproveOcrDraft(draft), true);
  const approved = approveOcrDraft(draft);
  assert.equal(approved.reviewStatus, 'APPROVED');
});

test('merge and split reject already approved drafts', () => {
  const a = approveOcrDraft(selectOcrDraftKind(applyOcrToDraft(createOcrReviewDraft(source('a')), "x=1"), 'ROOT_FINDING'));
  const b = selectOcrDraftKind(applyOcrToDraft(createOcrReviewDraft(source('b')), "x=2"), 'ROOT_FINDING');

  assert.throws(() => mergeOcrReviewDrafts(a, b, 'merged'), /OCR_DRAFT_ALREADY_APPROVED/);
  assert.throws(() => mergeOcrReviewDrafts(b, a, 'merged'), /OCR_DRAFT_ALREADY_APPROVED/);
  assert.throws(() => splitOcrReviewDraft(a, { localId: 's1', contentLatex: 'x=1' }, { localId: 's2', contentLatex: 'x=1' }), /OCR_DRAFT_ALREADY_APPROVED/);
});

test('split rejects duplicate IDs and empty parts', () => {
  const draft = selectOcrDraftKind(applyOcrToDraft(createOcrReviewDraft(source('a')), "x=1 \\wedge y=2"), 'ROOT_FINDING');

  assert.throws(() => splitOcrReviewDraft(draft, { localId: 'same', contentLatex: 'x=1' }, { localId: 'same', contentLatex: 'y=2' }), /OCR_DRAFT_DUPLICATE_ID/);
  assert.throws(() => splitOcrReviewDraft(draft, { localId: 'p1', contentLatex: '   ' }, { localId: 'p2', contentLatex: 'y=2' }), /OCR_DRAFT_EMPTY_PART/);
  assert.throws(() => splitOcrReviewDraft(draft, { localId: 'p1', contentLatex: 'x=1' }, { localId: 'p2', contentLatex: '' }), /OCR_DRAFT_EMPTY_PART/);
});

test('editing a skipped draft is a no-op preserving SKIPPED status', () => {
  let draft = createOcrReviewDraft(source('a'));
  draft = skipOcrDraft(draft);
  assert.equal(draft.reviewStatus, 'SKIPPED');
  const edited = editOcrReviewDraft(draft, { contentLatex: "x=1" });
  assert.strictEqual(edited, draft);
  assert.equal(edited.contentLatex, "");
});
