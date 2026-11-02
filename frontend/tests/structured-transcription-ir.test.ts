import test from "node:test";
import assert from "node:assert/strict";
import type { InkStroke } from "../src/lib/api/contracts.js";
import type { StructureCandidate } from "../src/features/math-workspace/utils/structural-candidate-engine.js";
import { segmentPageInk_v2 } from "../src/features/math-workspace/utils/page-ocr.js";
import { detectStructuralCandidates } from "../src/features/math-workspace/utils/structural-candidate-engine.js";
import {
  computeBounds, buildStructuredTranscriptionIR, applyOcrToContentUnit, editContentUnit,
  approveContentUnit, editContainerRelation, confirmTranscriptionReadingOrder,
  setSiblingReadingOrder, getRootContentUnits, getOrderedReviewUnits,
  projectTranscriptionToLegacySteps, validateSolutionTranscriptionIR,
  requireApprovedTranscriptionIR,
  type SolutionTranscriptionIR,
} from "../src/features/math-workspace/utils/structured-transcription-ir.js";

function stroke(id: string, x = 0.1, y = 0.1, w = 0.15, h = 0.02): InkStroke {
  return { id, tool: "PEN", color: "#000000", width: 2, points: [
    { x, y, pressure: 0.5 }, { x: x + w, y: y + h, pressure: 0.5 },
  ] };
}
function simple(count = 1) {
  const strokes = Array.from({ length: count }, (_, i) => stroke(`s${i}`, 0.1, 0.1 + i * 0.15));
  return buildStructuredTranscriptionIR({ pageIndex: 0, strokes, regions: segmentPageInk_v2(strokes) });
}
function system(nested = false) {
  const strokes = [stroke("a", 0.15, 0.1), stroke("b", 0.15, 0.3), stroke("brace", 0.08, 0.08, 0.02, 0.3)];
  const leaf = (id: string, sid: string): StructureCandidate => ({ id, kind: "INDEPENDENT", sourceStrokeIds: [sid],
    bounds: computeBounds(strokes.filter((s) => s.id === sid)), children: [], reasons: [] });
  const candidate: StructureCandidate = { id: "system", kind: "SYSTEM", sourceStrokeIds: strokes.map((s) => s.id),
    bounds: computeBounds(strokes), children: [leaf("A", "a"), leaf("B", "b")], reasons: [] };
  if (nested) candidate.children[0] = { ...candidate.children[0], id: "nested", kind: "ALTERNATIVES", children: [leaf("A", "a")] };
  return buildStructuredTranscriptionIR({ pageIndex: 0, strokes, regions: segmentPageInk_v2(strokes), structuralCandidates: [candidate] });
}
function approveAll(input: SolutionTranscriptionIR) {
  let ir = input;
  for (const { unit } of getOrderedReviewUnits(ir.contentUnits).reverse()) {
    if (unit.role === "ATOMIC") ir = editContentUnit(ir, unit.id, { content: `${unit.id}=2` });
    ir = approveContentUnit(ir, unit.id);
  }
  return confirmTranscriptionReadingOrder(ir);
}
function unit(ir: SolutionTranscriptionIR, id: string) { return ir.contentUnits.find((u) => u.id === id)!; }

test("bounds remain exact for wide/tall strokes and large x, small y", () => {
  assert.deepEqual(computeBounds([stroke("wide", 0.75, 0.05, 0.15, 0.05)]), { left: 0.75, right: 0.9, top: 0.05, bottom: 0.1 });
  assert.deepEqual(computeBounds([stroke("tall", 0.08, 0.05, 0.02, 0.4)]), { left: 0.08, right: 0.1, top: 0.05, bottom: 0.45 });
});

test("two-equation parent has reviewable children, delimiter provenance, no invented content", () => {
  let ir = system();
  assert.equal(ir.contentUnits.length, 3);
  assert.equal(getRootContentUnits(ir.contentUnits).length, 1);
  assert.deepEqual(unit(ir, "system").childIds, ["sub-A", "sub-B"]);
  assert.throws(() => approveContentUnit(ir, "system"), /CHILDREN_UNAPPROVED/);
  ir = applyOcrToContentUnit(ir, "sub-A", "x+y=1");
  ir = approveContentUnit(ir, "sub-A");
  assert.throws(() => approveContentUnit(ir, "system"), /CHILDREN_UNAPPROVED/);
  ir = applyOcrToContentUnit(ir, "sub-B", "x-y=0");
  ir = approveContentUnit(ir, "sub-B");
  assert.equal(unit(ir, "system").reviewStatus, "NEEDS_REVIEW", "children never approve their parent automatically");
  ir = approveContentUnit(ir, "system");
  assert.equal(unit(ir, "system").approvedContent, null);
  assert.equal(unit(ir, "system").recognitionStatus, "NOT_APPLICABLE");
  assert.equal(ir.reviewStatus, "NEEDS_REVIEW", "reading order also needs explicit confirmation");
  ir = confirmTranscriptionReadingOrder(ir);
  assert.equal(ir.reviewStatus, "APPROVED");
  assert.doesNotThrow(() => validateSolutionTranscriptionIR(JSON.parse(JSON.stringify(ir)), ir.sourceSnapshot.strokes));
});

test("nested construction retains every child; edit invalidates all dependent ancestors", () => {
  let ir = approveAll(system(true));
  assert.equal(ir.contentUnits.length, 4);
  assert.equal(ir.reviewStatus, "APPROVED");
  ir = editContentUnit(ir, "sub-A", { content: "x=3" });
  for (const id of ["sub-A", "sub-nested", "system"]) assert.equal(unit(ir, id).reviewStatus, "NEEDS_REVIEW");
  assert.equal(unit(ir, "sub-B").reviewStatus, "APPROVED");
  assert.equal(ir.approvedUnitCount, 1);
  assert.equal(ir.reviewStatus, "NEEDS_REVIEW");
  assert.throws(() => approveContentUnit(ir, "system"), /CHILDREN_UNAPPROVED/);
  ir = approveContentUnit(ir, "sub-A");
  ir = approveContentUnit(ir, "sub-nested");
  assert.equal(unit(ir, "system").reviewStatus, "NEEDS_REVIEW");
  ir = approveContentUnit(ir, "system");
  assert.equal(ir.reviewStatus, "APPROVED");
});

test("OCR rerun preserves approved manual content and structure, updates only raw evidence", () => {
  let ir = approveAll(system());
  const provenance = structuredClone(ir.sourceSnapshot);
  const accepted = unit(ir, "sub-A").approvedContent;
  ir = applyOcrToContentUnit(ir, "sub-A", "x=999");
  assert.equal(unit(ir, "sub-A").approvedContent, accepted);
  assert.equal(unit(ir, "sub-A").rawRecognition, "x=999");
  assert.equal(ir.reviewStatus, "APPROVED");
  assert.equal(unit(ir, "sub-A").recognitionStatus, "MANUALLY_CORRECTED");
  assert.deepEqual(ir.sourceSnapshot, provenance);
});

test("changed OCR without manual correction invalidates accepted raw content and parent", () => {
  let ir = system();
  for (const id of ["sub-A", "sub-B"]) { ir = applyOcrToContentUnit(ir, id, "x=1"); ir = approveContentUnit(ir, id); }
  ir = confirmTranscriptionReadingOrder(approveContentUnit(ir, "system"));
  ir = applyOcrToContentUnit(ir, "sub-A", "x=2");
  assert.equal(unit(ir, "sub-A").approvedContent, null);
  assert.equal(unit(ir, "system").reviewStatus, "NEEDS_REVIEW");
  assert.equal(ir.reviewStatus, "NEEDS_REVIEW");
});

test("manual edit during pending OCR wins when model result arrives", () => {
  let ir = simple(); const id = ir.contentUnits[0].id;
  ir = editContentUnit(ir, id, { content: "learner correction" });
  ir = applyOcrToContentUnit(ir, id, "late model output");
  assert.equal(unit(ir, id).approvedContent, "learner correction");
});

test("containers, TEXT and UNKNOWN cannot be sent to CoMER", () => {
  const ir = system();
  assert.throws(() => applyOcrToContentUnit(ir, "system", "fake system"), /ATOMIC_MATH/);
  assert.throws(() => editContentUnit(ir, "system", { content: "fake system" }), /STRUCTURE_REVIEW/);
  for (const kind of ["TEXT", "UNKNOWN"] as const) {
    const text = editContentUnit(ir, "sub-A", { kind });
    assert.throws(() => applyOcrToContentUnit(text, "sub-A", "fake Vietnamese"), /ATOMIC_MATH/);
  }
});

test("UNKNOWN relation blocks approval; explicit relation edit invalidates ancestors", () => {
  let ir = approveAll(system(true));
  ir = editContainerRelation(ir, "sub-nested", "UNKNOWN");
  assert.equal(unit(ir, "system").reviewStatus, "NEEDS_REVIEW");
  assert.throws(() => approveContentUnit(ir, "sub-nested"), /CHILDREN_UNAPPROVED/);
  ir = editContainerRelation(ir, "sub-nested", "INDEPENDENT");
  ir = approveContentUnit(ir, "sub-nested");
  assert.doesNotThrow(() => approveContentUnit(ir, "system"));
});

test("root detection and review order are independent of ID prefixes and storage array", () => {
  const ir = system();
  const parent = unit(ir, "system"); parent.id = "sub-root-with-misleading-prefix";
  unit(ir, "sub-A").id = "ordinary-child"; parent.childIds[0] = "ordinary-child";
  ir.contentUnits.reverse();
  validateSolutionTranscriptionIR(ir);
  assert.equal(getRootContentUnits(ir.contentUnits)[0].id, parent.id);
  assert.deepEqual(getOrderedReviewUnits(ir.contentUnits).map((r) => [r.unit.id, r.depth]), [
    [parent.id, 0], ["ordinary-child", 1], ["sub-B", 1],
  ]);
});

test("reading order is spatial, not drawing or serialization order", () => {
  const strokes = [stroke("bottom", 0.1, 0.4), stroke("top", 0.1, 0.1)];
  const regions = strokes.map((s) => ({ id: s.id, strokes: [s], bounds: computeBounds([s]) }));
  const ir = buildStructuredTranscriptionIR({ pageIndex: 0, strokes, regions });
  assert.deepEqual(getRootContentUnits(ir.contentUnits).map((u) => u.sourceStrokeIds[0]), ["top", "bottom"]);
  assert.deepEqual(ir.sourceSnapshot.strokes.map((s) => s.id), ["bottom", "top"]);
});

test("two columns remain ambiguous until human orders and confirms them", () => {
  const strokes = [stroke("left", 0.1, 0.1), stroke("right", 0.65, 0.1)];
  let ir = buildStructuredTranscriptionIR({ pageIndex: 0, strokes,
    regions: strokes.map((s) => ({ id: s.id, strokes: [s], bounds: computeBounds([s]) })) });
  assert.equal(ir.readingOrderStatus, "AMBIGUOUS");
  assert.ok(ir.readingOrderWarnings.length);
  ir = setSiblingReadingOrder(ir, null, ["unit-right", "unit-left"]);
  assert.equal(ir.readingOrderStatus, "AMBIGUOUS");
  assert.deepEqual(getRootContentUnits(ir.contentUnits).map((u) => u.id), ["unit-right", "unit-left"]);
  ir = confirmTranscriptionReadingOrder(ir);
  assert.equal(ir.readingOrderStatus, "CONFIRMED");
  assert.equal(ir.reviewStatus, "NEEDS_REVIEW");
  assert.throws(() => setSiblingReadingOrder(ir, null, ["unit-left", "unit-left"]), /INVALID_ORDER/);
});

test("reordering children invalidates parent relation and page order confirmation", () => {
  let ir = approveAll(system());
  ir = setSiblingReadingOrder(ir, "system", ["sub-B", "sub-A"]);
  assert.equal(unit(ir, "system").reviewStatus, "NEEDS_REVIEW");
  assert.equal(unit(ir, "sub-A").reviewStatus, "APPROVED");
  assert.notEqual(ir.readingOrderStatus, "CONFIRMED");
});

test("orphan ink is conserved as UNKNOWN; annotation strokes are outside pen source", () => {
  const a = stroke("a"), orphan = stroke("orphan", 0.8, 0.8);
  const ir = buildStructuredTranscriptionIR({ pageIndex: 0, strokes: [a, orphan, { ...stroke("highlight"), tool: "HIGHLIGHTER" }],
    regions: [{ id: "one", strokes: [a], bounds: computeBounds([a]) }] });
  assert.equal(ir.rawStrokeCount, 2);
  assert.equal(unit(ir, "orphan-orphan").kind, "UNKNOWN");
  assert.equal(unit(ir, "orphan-orphan").recognitionStatus, "UNRESOLVED");
  assert.equal(ir.sourceSnapshot.strokes.length, 2);
  assert.throws(() => approveContentUnit(ir, "orphan-orphan"), /EMPTY_CONTENT/);
});

test("source is copied once; JSON roundtrip preserves physical ink and legal ancestor references", () => {
  const ir = system();
  const decoded = JSON.parse(JSON.stringify(ir));
  validateSolutionTranscriptionIR(decoded, ir.sourceSnapshot.strokes);
  assert.equal(decoded.sourceSnapshot.strokes.length, 3);
  assert.equal(decoded.contentUnits.flatMap((u: { sourceStrokeIds: string[] }) => u.sourceStrokeIds).length, 5);
  assert.equal(new Set(decoded.sourceSnapshot.strokes.map((s: InkStroke) => s.id)).size, 3);
  const original = [stroke("a")];
  const copy = buildStructuredTranscriptionIR({ pageIndex: 0, strokes: original, regions: [] });
  original[0].points[0].x = 0.9;
  assert.equal(copy.sourceSnapshot.strokes[0].points[0].x, 0.1);
  assert.throws(() => validateSolutionTranscriptionIR(copy, original), /SNAPSHOT_MISMATCH/);
});

const malformedCases: [string, (ir: SolutionTranscriptionIR) => void, RegExp][] = [
  ["duplicate child", (ir) => unit(ir, "system").childIds.push("sub-A"), /DUPLICATE_OR_INVALID_CHILD/],
  ["missing child", (ir) => unit(ir, "system").childIds.push("absent"), /MISSING_CHILD/],
  ["cycle", (ir) => unit(ir, "system").childIds.push("system"), /CYCLIC_CHILD/],
  ["multiple parents", (ir) => unit(ir, "sub-B").childIds.push("sub-A"), /MULTIPLE_CHILD_PARENTS|CHILD_STROKE_NOT_IN_PARENT/],
  ["duplicate unit ID", (ir) => ir.contentUnits.push(structuredClone(ir.contentUnits[0])), /DUPLICATE_UNIT_ID/],
  ["unknown source", (ir) => unit(ir, "sub-A").sourceStrokeIds.push("fabricated"), /UNKNOWN_SOURCE_STROKE/],
  ["duplicate source snapshot", (ir) => ir.sourceSnapshot.strokes.push(ir.sourceSnapshot.strokes[0]), /DUPLICATE_SOURCE_STROKE/],
  ["duplicate stroke reference", (ir) => unit(ir, "sub-A").sourceStrokeIds.push("a"), /DUPLICATE_OR_INVALID_STROKE/],
  ["inverted bounds", (ir) => { unit(ir, "sub-A").bounds.left = 0.9; }, /MALFORMED_UNIT_BOUNDS/],
  ["NaN geometry", (ir) => { unit(ir, "sub-A").bounds.top = NaN; }, /INVALID_UNIT_BOUNDS/],
  ["wrong geometry", (ir) => { unit(ir, "sub-A").bounds.right = 0.8; }, /SOURCE_BOUNDS_MISMATCH/],
  ["bad enum", (ir) => { (unit(ir, "sub-A") as unknown as { kind: string }).kind = "GRADING_STEP"; }, /INVALID_UNIT_STATE/],
  ["wrong counter", (ir) => { ir.approvedUnitCount = 100; }, /INCONSISTENT_IR_COUNTERS/],
  ["forged global approval", (ir) => { ir.reviewStatus = "APPROVED"; }, /INCONSISTENT_IR_APPROVAL/],
  ["forged parent approval", (ir) => { unit(ir, "system").reviewStatus = "APPROVED"; }, /APPROVED_PARENT_UNRESOLVED/],
  ["empty approved atom", (ir) => { unit(ir, "sub-A").reviewStatus = "APPROVED"; }, /APPROVED_UNIT_EMPTY_CONTENT/],
  ["duplicate sibling order", (ir) => { unit(ir, "sub-B").readingOrder = 0; }, /DUPLICATE_SIBLING_READING_ORDER/],
];
for (const [name, corrupt, pattern] of malformedCases) test(`validator rejects ${name}; mutations share validator rules`, () => {
  const ir = system(); corrupt(ir);
  assert.throws(() => validateSolutionTranscriptionIR(ir), pattern);
  assert.throws(() => approveContentUnit(ir, "system"), pattern);
  assert.throws(() => projectTranscriptionToLegacySteps(ir), pattern);
});

test("missing source coverage and unrelated top-level ownership are rejected", () => {
  const missing = simple(2); missing.contentUnits.pop();
  assert.throws(() => validateSolutionTranscriptionIR(missing), /MISSING_SOURCE_STROKE_COVERAGE/);
  const dup = simple(); dup.contentUnits.push({ ...structuredClone(dup.contentUnits[0]), id: "unrelated-root", readingOrder: 1 });
  assert.throws(() => validateSolutionTranscriptionIR(dup), /DUPLICATE_SIBLING_STROKE_OWNERSHIP/);
});

test("different sibling IDs cannot conceal duplicate physical stroke ownership", () => {
  const ir = system();
  const a = unit(ir, "sub-A"), b = unit(ir, "sub-B");
  b.sourceStrokeIds = [...a.sourceStrokeIds]; b.bounds = { ...a.bounds };
  assert.throws(() => validateSolutionTranscriptionIR(ir), /DUPLICATE_SIBLING_STROKE_OWNERSHIP/);
});

test("approved handoff guard validates the original source and rejects incomplete review", () => {
  const draft = system();
  assert.throws(() => requireApprovedTranscriptionIR(draft), /REVIEW_INCOMPLETE/);
  const approved = approveAll(draft);
  assert.equal(requireApprovedTranscriptionIR(approved, draft.sourceSnapshot.strokes).reviewStatus, "APPROVED");
  const changed = structuredClone(draft.sourceSnapshot.strokes); changed[0].points[0].y += 0.001;
  assert.throws(() => requireApprovedTranscriptionIR(approved, changed), /SOURCE_SNAPSHOT_MISMATCH/);
});

test("construction rejects collisions, nonexistent proposal strokes and invalid nested ownership", () => {
  const ir = system();
  assert.throws(() => buildStructuredTranscriptionIR({ pageIndex: 0, strokes: [stroke("same"), stroke("same")], regions: [] }), /DUPLICATE_SOURCE/);
  const candidate: StructureCandidate = { id: "bad", kind: "SYSTEM", sourceStrokeIds: ["a"], bounds: computeBounds([stroke("a")]),
    reasons: [], children: [{ id: "missing-source", kind: "INDEPENDENT", sourceStrokeIds: ["invented"], bounds: computeBounds([stroke("a")]), reasons: [], children: [] }] };
  assert.throws(() => buildStructuredTranscriptionIR({ pageIndex: 0, strokes: ir.sourceSnapshot.strokes, regions: [], structuralCandidates: [candidate] }), /UNKNOWN_SOURCE_STROKE/);
  const colliding = { ...candidate, children: [{ ...candidate.children[0], id: "same", sourceStrokeIds: ["a"] }, { ...candidate.children[0], id: "same", sourceStrokeIds: ["a"] }] };
  assert.throws(() => buildStructuredTranscriptionIR({ pageIndex: 0, strokes: ir.sourceSnapshot.strokes, regions: [], structuralCandidates: [colliding] }), /DUPLICATE_UNIT_ID/);
});

test("two independent lines are not converted into a system", () => {
  const strokes = [stroke("a"), stroke("b", 0.1, 0.35)];
  const candidates = detectStructuralCandidates(strokes);
  assert.ok(candidates.every((c) => c.kind !== "SYSTEM" && c.kind !== "ALTERNATIVES"));
  const ir = buildStructuredTranscriptionIR({ pageIndex: 0, strokes, regions: segmentPageInk_v2(strokes), structuralCandidates: candidates });
  assert.equal(getRootContentUnits(ir.contentUnits).length, 2);
});

test("student math errors are preserved as transcription, never solved or corrected", () => {
  let ir = simple(); const id = ir.contentUnits[0].id;
  const written = "3x^2 - 3 = 0 \\Leftrightarrow x = 2";
  ir = editContentUnit(ir, id, { content: written });
  ir = confirmTranscriptionReadingOrder(approveContentUnit(ir, id));
  assert.equal(ir.reviewStatus, "APPROVED");
  assert.equal(projectTranscriptionToLegacySteps(ir).candidateUnits[0].approvedContent, written);
});

test("three approved units plus UNKNOWN cannot leak a partial legacy payload", () => {
  let ir = simple(4);
  for (const u of ir.contentUnits.slice(0, 3)) { ir = editContentUnit(ir, u.id, { content: "x=1" }); ir = approveContentUnit(ir, u.id); }
  ir = editContentUnit(ir, ir.contentUnits[3].id, { kind: "UNKNOWN", content: "" });
  const projection = projectTranscriptionToLegacySteps(ir);
  assert.equal(projection.isProjectionBlocked, true);
  assert.equal(projection.readyToSubmit, false);
  assert.equal(projection.submitPayload, null);
  assert.deepEqual(projection.steps, []);
  assert.equal(projection.allUnitsMapped, false);
  assert.equal(projection.candidateUnits.length, 4);
  assert.equal(projection.blockedUnits.length, 4);
});

test("approved mixed TEXT/UNKNOWN/structure is lossless preview; boundaries remain blocked", () => {
  let ir = system();
  ir = editContentUnit(ir, "sub-A", { kind: "TEXT", content: "Suy ra" });
  ir = editContentUnit(ir, "sub-B", { kind: "UNKNOWN", content: "ký hiệu chưa phân loại" });
  ir = approveContentUnit(ir, "sub-A"); ir = approveContentUnit(ir, "sub-B");
  ir = confirmTranscriptionReadingOrder(approveContentUnit(ir, "system"));
  const p = projectTranscriptionToLegacySteps(ir);
  assert.equal(ir.reviewStatus, "APPROVED");
  assert.equal(p.mode, "PREVIEW_ONLY");
  assert.equal(p.isProjectionBlocked, true);
  assert.equal(p.steps.length, 0);
  assert.equal(p.candidateUnits[0].approvedContent, null);
  assert.ok(p.candidateUnits.some((u) => u.kind === "TEXT" && u.approvedContent === "Suy ra"));
  assert.ok(p.blockedUnits.some((u) => u.reason.includes("UNKNOWN")));
  assert.ok(!JSON.stringify(p).includes("predictedType"));
});

test("synthetic four-line plumbing is not a recognition accuracy test", () => {
  let ir = simple(4);
  const contents = ["Tập xác định: R", "y'=3x^2-3", "y'=0 \\Leftrightarrow x=2", "y(1)=-1"];
  for (const [i, u] of ir.contentUnits.entries()) {
    ir = editContentUnit(ir, u.id, { kind: i === 0 ? "TEXT" : "MATH", content: contents[i] });
    ir = approveContentUnit(ir, u.id);
  }
  ir = confirmTranscriptionReadingOrder(ir);
  assert.equal(ir.reviewStatus, "APPROVED");
  assert.equal(ir.recognizedUnitCount, 0, "manual examples are not model outputs");
  assert.equal(projectTranscriptionToLegacySteps(ir).submitPayload, null);
  validateSolutionTranscriptionIR(ir);
});
