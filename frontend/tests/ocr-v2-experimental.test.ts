import test from "node:test";
import assert from "node:assert/strict";
import { buildScopeIR, fromPixel, geometryPerception, groupIrUnits, mapLayoutToScopes, reassignScope, renderTransform, routeLabel, scopeIntegrity, strokeCoverage, toPixel, validateLabSource, type LabSource, type RawLayoutRegion } from "../src/features/math-workspace/utils/ocr-v2-experimental";
import { segmentPageInk } from "../src/features/math-workspace/utils/page-ocr";
import { constructScopeCandidates } from "../src/features/math-workspace/utils/ocr-v2-scope-candidates";
import { applyOcrToContentUnit, approveContentUnit, confirmTranscriptionReadingOrder, editContentUnit, projectTranscriptionToLegacySteps } from "../src/features/math-workspace/utils/structured-transcription-ir";
import { editLabScopeKind, readLabScopeProjection } from "../src/features/math-workspace/utils/ocr-v2-experimental";
import { validateSolutionTranscriptionIR } from "../src/features/math-workspace/utils/structured-transcription-ir";
import { reconcileLayoutScopeCandidates } from "../src/features/math-workspace/utils/ocr-v2-scope-candidates";
import type { ScopeProposal } from "../src/features/math-workspace/utils/ocr-v2-experimental";
const source: LabSource = { pageIndex: 0, sourceRevision: 3, sourceKind: "SYNTHETIC_INK", datasetSplit: "DEV", consent: false, strokes: [
  { id: "a", tool: "PEN", color: "#000000", width: 2, points: [{ x: .1, y: .1, pressure: .5 }, { x: .6, y: .1, pressure: .5 }] },
  { id: "dot", tool: "PEN", color: "#000000", width: 2, points: [{ x: .4, y: .12, pressure: .5 }] },
  { id: "b", tool: "PEN", color: "#000000", width: 2, points: [{ x: .1, y: .3, pressure: .5 }, { x: .6, y: .3, pressure: .5 }] },
  { id: "highlight", tool: "HIGHLIGHTER", color: "#ffff00", width: 12, points: [{ x: .5, y: .2, pressure: .5 }] },
] };
const t = renderTransform(16, 1);
const box: RawLayoutRegion = { id: "r", label: "formula", score: .6, box: [250, 110, 420, 160] };
const mark = (id: string, points: number[][]) => ({ id, tool: "PEN" as const, color: "#000000", width: 2, points: points.map(([x, y]) => ({ x: x / 794, y: y / 1123, pressure: .5 })) });
function equation(prefix: string, y: number, x = 0) {
  return [mark(prefix + "x", [[30 + x, y], [42 + x, y + 20], [45 + x, y]]),
    mark(prefix + "eq1", [[65 + x, y + 6], [85 + x, y + 6]]), mark(prefix + "eq2", [[65 + x, y + 14], [77 + x, y + 14]]),
    mark(prefix + "rhs", [[105 + x, y], [115 + x, y + 20], [125 + x, y]])];
}
function inkSource(strokes: LabSource["strokes"]): LabSource { return { ...source, strokes }; }
test("hybrid completes a mislabeled partial box from independent geometry, preserving source and order", () => {
  const s = inkSource(equation("a", 100)), before = JSON.stringify(s);
  const result = constructScopeCandidates(s, { status: "DETECTED", model: "M", regions: [{ id: "text", label: "doc_title", score: .9, box: [75, 106, 160, 150] }] }, t);
  const scope = result.scopes.find(s => s.kind === "MATH")!;
  assert.deepEqual(scope.strokeIds, s.strokes.map(s => s.id)); assert.equal(result.routing[scope.id].action, "COMER_PROBE");
  assert.ok(result.candidates.some(c => c.source === "CLUSTER_COMPLETION")); assert.equal(JSON.stringify(s), before);
  assert.deepEqual(scopeIntegrity(s, result.scopes).duplicateOwnership, []);
});
test("one learned page-wide formula box cannot join nearby independent equality rows or columns", () => {
  for (const strokes of [[...equation("a", 100), ...equation("b", 138)], [...equation("a", 100), ...equation("b", 100, 300)]]) {
    const s = inkSource(strokes), r = constructScopeCandidates(s, { status: "DETECTED", model: "M", regions: [{ id: "all", label: "formula", score: .99, box: [0, 0, 800, 1120] }] }, t);
    assert.ok(r.scopes.every(scope => !(scope.strokeIds.includes("ax") && scope.strokeIds.includes("bx"))));
    assert.ok(r.candidates.some(c => c.source === "LEARNED_LAYOUT" && c.competingIds.length > 1
      && !c.disposition.startsWith("ACCEPTED_")));
    assert.deepEqual(scopeIntegrity(s, r.scopes).missing, []);
  }
});
test("fraction support retains distant numerator, denominator and small dot without whole-page rescue", () => {
  const s = inkSource([mark("num", [[100, 90], [112, 115], [125, 90]]), mark("bar", [[90, 140], [180, 140]]),
    mark("den", [[110, 166], [122, 193], [138, 166]]), mark("dot", [[145, 104]])]);
  const r = constructScopeCandidates(s, { status: "MODEL_MISSING", model: "M", regions: [] }, t);
  assert.ok(r.scopes.some(scope => scope.kind === "MATH" && s.strokes.every(s => scope.strokeIds.includes(s.id))));
  assert.deepEqual(scopeIntegrity(s, r.scopes).unknown, []);
});
test("a long radical close below a fraction bar does not trigger the compact-operator exclusion", () => {
  const s = inkSource([mark("num", [[110, 95], [200, 115], [240, 95]]), mark("bar", [[90, 135], [260, 135]]),
    mark("radical", [[95, 155], [105, 170], [120, 145], [250, 145]]), mark("den", [[130, 174], [165, 204], [200, 174]])]);
  const r = constructScopeCandidates(s, { status: "DETECTED", model: "M", regions: [] }, t);
  assert.ok(r.scopes.some(scope => s.strokes.every(stroke => scope.strokeIds.includes(stroke.id)) && scope.flags.includes("FRACTION_BAR_WITH_ABOVE_BELOW_SUPPORT")));
});
test("a text-like top cross is not positive math evidence; no inference can promote its label", () => {
  const s = inkSource([mark("top", [[20, 100], [43, 100]]), mark("stem", [[30, 100], [30, 126]]), mark("letter", [[52, 111], [65, 127], [75, 110]])]);
  const r = constructScopeCandidates(s, { status: "DETECTED", model: "M", regions: [{ id: "text", label: "text", score: .9, box: [0, 0, 800, 1120] }] }, t);
  assert.ok(r.scopes.every(s => s.kind !== "MATH")); assert.ok(Object.values(r.routing).every(o => o.action === "MANUAL"));
});
test("tall bracket proposes an uncertain relation and never owns both equality rows as one expression", () => {
  const s = inkSource([...equation("a", 100, 80), ...equation("b", 150, 80), mark("bracket", [[100, 93], [96, 183], [102, 183]])]);
  const r = constructScopeCandidates(s, { status: "ERROR", model: "M", regions: [] }, t);
  assert.ok(r.scopes.every(scope => !(scope.strokeIds.includes("ax") && scope.strokeIds.includes("bx"))));
  assert.ok(r.relations.some(relation => relation.kind === "UNKNOWN" && relation.strokeIds.includes("bracket")));
  assert.deepEqual(scopeIntegrity(s, r.scopes).missing, []);
});
test("shared parallel/cross cues, blank source and reordered drawing do not duplicate physical ownership", () => {
  const strokes = equation("a", 100); strokes.push(mark("third-bar", [[65, 121], [84, 121]]));
  for (const list of [strokes, [...strokes].reverse(), []]) {
    const s = inkSource(list), result = constructScopeCandidates(s, { status: "NO_DETECTIONS", model: "M", regions: [] }, t);
    assert.deepEqual(scopeIntegrity(s, result.scopes).missing, []); assert.deepEqual(scopeIntegrity(s, result.scopes).duplicateOwnership, []);
    for (const scope of result.scopes) assert.deepEqual(scope.strokeIds, list.filter(s => scope.strokeIds.includes(s.id)).map(s => s.id));
  }
});
test("A4 forward/inverse transform, invalid ink fails without mutating source", () => {
  const before = JSON.stringify(source), p = { x: .42, y: .81 }; const back = fromPixel(toPixel(p, renderTransform(32, 2)), renderTransform(32, 2));
  assert.ok(Math.abs(back.x - p.x) < 1e-12 && Math.abs(back.y - p.y) < 1e-12);
  const bad = structuredClone(source); bad.strokes[0].points[0].x = 2;
  assert.throws(() => validateLabSource(bad), /OUT_OF_PAGE/); assert.equal(JSON.stringify(source), before);
});
test("segment/polygon intersection maps crossing strokes, dots, excludes highlights and exposes overlap/orphans", () => {
  assert.ok(strokeCoverage(source.strokes[0], box, t) > 0); // both original endpoints are outside the box
  const scopes = mapLayoutToScopes(source, { status: "DETECTED", model: "M", regions: [box, { ...box, id: "r2" }] }, t);
  const integrity = scopeIntegrity(source, scopes);
  assert.deepEqual(integrity.missing, []); assert.deepEqual(integrity.duplicateOwnership, []); assert.deepEqual(integrity.unknown, []);
  assert.ok(integrity.overlappingCandidates.length); assert.ok(integrity.orphans.includes("b"));
  assert.ok(!scopes.flatMap(s => s.strokeIds).includes("highlight"));
});
test("V1/V2 baselines keep exact membership rather than remapping their overlapping boxes", () => {
  for (const profile of ["V1", "V2"] as const) {
    const p = geometryPerception(source.strokes.filter(s => s.tool === "PEN"), profile, t);
    const scopes = mapLayoutToScopes(source, p, t);
    assert.deepEqual(scopes.map(s => s.strokeIds), segmentPageInk(source.strokes, { algorithm: profile === "V1" ? "v1" : "v2" }).map(r => r.strokes.map(s => s.id)));
  }
});
test("zero detections preserve all pen ink as UNKNOWN, independent rows stay separate in fallback", () => {
  const scopes = mapLayoutToScopes(source, { status: "NO_DETECTIONS", model: "M", regions: [] }, t);
  assert.ok(scopes.length > 1); assert.ok(scopes.every(s => s.kind === "UNKNOWN")); assert.deepEqual(scopeIntegrity(source, scopes).missing, []);
  const ir = buildScopeIR(source, scopes); assert.ok(ir.contentUnits.every(u => !u.isManuallyCorrected && u.recognitionStatus === "UNRESOLVED"));
  assert.deepEqual(ir.contentUnits[0].sourceRegionIds, scopes.find(s => `unit-${s.id}` === ir.contentUnits[0].id)!.regionIds);
  assert.equal(routeLabel("formula"), "MATH"); assert.equal(routeLabel("text"), "TEXT"); assert.equal(routeLabel("figure"), "UNKNOWN");
});
test("manual reassignment conserves physical IDs and rejects invented IDs", () => {
  const scopes = mapLayoutToScopes(source, geometryPerception(source.strokes, "V2", t, true), t);
  const next = reassignScope(scopes, ["a", "dot"], "manual", "MATH");
  assert.deepEqual(scopeIntegrity(source, next).duplicateOwnership, []); assert.deepEqual(scopeIntegrity(source, next).missing, []);
  assert.throws(() => reassignScope(scopes, ["invented"], "x", "MATH"));
});
test("rerun cannot overwrite correction, wrong math stays verbatim, source revision invalidates approval", () => {
  const scopes = mapLayoutToScopes(source, geometryPerception(source.strokes, "V2", t), t); let ir = buildScopeIR(source, scopes);
  const id = ir.contentUnits[0].id; ir = applyOcrToContentUnit(ir, id, "x+1=3"); ir = editContentUnit(ir, id, { content: "x+1=3 \\Rightarrow x=5" }); ir = approveContentUnit(ir, id);
  ir = applyOcrToContentUnit(ir, id, "new OCR evidence"); assert.equal(ir.contentUnits[0].approvedContent, "x+1=3 \\Rightarrow x=5");
  const replay = buildScopeIR(source, scopes, ir); assert.equal(replay.contentUnits[0].approvedContent, ir.contentUnits[0].approvedContent);
  const changed = buildScopeIR({ ...source, sourceRevision: 4 }, scopes, ir); assert.equal(changed.approvedUnitCount, 0); assert.equal(changed.reviewStatus, "NEEDS_REVIEW");
  assert.deepEqual(projectTranscriptionToLegacySteps(ir).steps, []); assert.equal(projectTranscriptionToLegacySteps(ir).submitPayload, null);
});
test("explicit structure container has no fake text; child edit invalidates approved parent", () => {
  const scopes = mapLayoutToScopes(source, geometryPerception(source.strokes, "V2", t), t); let ir = buildScopeIR(source, scopes);
  for (const u of ir.contentUnits) { ir = editContentUnit(ir, u.id, { content: "literal handwritten content" }); ir = approveContentUnit(ir, u.id); }
  const before = JSON.stringify(ir), original = ir;
  ir = groupIrUnits(ir, ir.contentUnits.map(u => u.id), "SYSTEM"); assert.equal(JSON.stringify(original), before); const parent = ir.contentUnits.find(u => u.role === "CONTAINER")!;
  assert.equal(parent.approvedContent, null); ir = approveContentUnit(ir, parent.id); ir = confirmTranscriptionReadingOrder(ir);
  ir = editContentUnit(ir, parent.childIds[0], { content: "Suy ra nghiệm không đúng: x=5" }); assert.equal(ir.contentUnits.find(u => u.id === parent.id)!.reviewStatus, "NEEDS_REVIEW");
});

test("sprint04: MIXED versus UNKNOWN survives IR-only JSON restore with exact source membership", () => {
  const scopes = mapLayoutToScopes(source, geometryPerception(source.strokes, "V2", t), t);
  scopes[0].kind = "MIXED"; scopes[1].kind = "UNKNOWN";
  const before = JSON.stringify(source), ir = buildScopeIR(source, scopes);
  const restored = validateSolutionTranscriptionIR(JSON.parse(JSON.stringify(ir)), source.strokes);
  assert.equal(restored.schemaVersion, "1.1");
  assert.equal(restored.contentUnits[0].kind, "UNKNOWN");
  for (const scope of scopes) {
    const evidence = readLabScopeProjection(restored, `unit-${scope.id}`)!;
    assert.equal(evidence.scopeId, scope.id); assert.equal(evidence.originalKind, scope.kind);
    assert.deepEqual(new Set(evidence.sourceStrokeIds), new Set(scope.strokeIds));
  }
  assert.equal(JSON.stringify(source), before);
  const legacy = structuredClone(restored); legacy.contentUnits[0].reasons = [];
  assert.equal(readLabScopeProjection(legacy, legacy.contentUnits[0].id), null);
});

test("sprint04: explicit scope kind edits preserve correction and invalidate approval without auto classifying", () => {
  const scopes = mapLayoutToScopes(source, geometryPerception(source.strokes, "V2", t), t);
  const id = `unit-${scopes[0].id}`;
  let ir = buildScopeIR(source, scopes);
  ir = editContentUnit(ir, id, { content: "Ta có x+1=3 ⇒ x=5" }); ir = approveContentUnit(ir, id);
  const approved = JSON.stringify(ir);
  ir = editLabScopeKind(ir, { ...scopes[0], kind: "MIXED" });
  assert.equal(ir.contentUnits[0].kind, "UNKNOWN");
  assert.equal(ir.contentUnits[0].approvedContent, "Ta có x+1=3 ⇒ x=5");
  assert.equal(ir.contentUnits[0].reviewStatus, "NEEDS_REVIEW");
  assert.equal(readLabScopeProjection(ir, id)!.originalKind, "MIXED");
  ir = editLabScopeKind(ir, { ...scopes[0], kind: "UNKNOWN" });
  assert.equal(readLabScopeProjection(ir, id)!.originalKind, "UNKNOWN");
  assert.equal(JSON.parse(approved).contentUnits[0].reviewStatus, "APPROVED");
  assert.throws(() => editLabScopeKind(ir, { ...scopes[0], strokeIds: ["invented"] }), /SOURCE_MISMATCH/);
});

test("sprint04: perception rebuild does not transfer approval between projected MIXED and true UNKNOWN", () => {
  const scopes = mapLayoutToScopes(source, geometryPerception(source.strokes, "V2", t), t);
  scopes[0].kind = "MIXED";
  const id = `unit-${scopes[0].id}`;
  let ir = buildScopeIR(source, scopes);
  ir = editContentUnit(ir, id, { content: "Bản chép thủ công" }); ir = approveContentUnit(ir, id);
  assert.equal(buildScopeIR(source, scopes, ir).contentUnits[0].reviewStatus, "APPROVED");
  const unknown = scopes.map(s => ({ ...s, kind: "UNKNOWN" as const }));
  const rebuilt = buildScopeIR(source, unknown, ir);
  assert.equal(rebuilt.contentUnits[0].reviewStatus, "NEEDS_REVIEW");
  assert.equal(rebuilt.contentUnits[0].approvedContent, "Bản chép thủ công");
  assert.equal(readLabScopeProjection(rebuilt, id)!.originalKind, "UNKNOWN");
  assert.equal(buildScopeIR({ ...source, sourceRevision: 4 }, scopes, ir).approvedUnitCount, 0);
});

test("sprint04: stale or inconsistent scope projection cannot relabel UNKNOWN, raw and correction stay separate", () => {
  const scopes = mapLayoutToScopes(source, geometryPerception(source.strokes, "V2", t), t);
  let ir = buildScopeIR(source, scopes); const id = ir.contentUnits[0].id;
  ir = applyOcrToContentUnit(ir, id, "\\frac{1}{2}");
  ir = editContentUnit(ir, id, { content: "x+1=3 ⇒ x=5" }); ir = approveContentUnit(ir, id);
  ir = applyOcrToContentUnit(ir, id, "retry output");
  const restored = validateSolutionTranscriptionIR(JSON.parse(JSON.stringify(ir)));
  assert.equal(restored.contentUnits[0].rawRecognition, "retry output");
  assert.equal(restored.contentUnits[0].approvedContent, "x+1=3 ⇒ x=5");
  const stale = structuredClone(ir); stale.sourceRevision++;
  assert.equal(readLabScopeProjection(stale, id), null);
  const bad = structuredClone(ir), unit = bad.contentUnits[0];
  unit.reasons = unit.reasons.map(r => r.replace('"originalKind":"MATH"', '"originalKind":"MIXED"'));
  assert.equal(readLabScopeProjection(bad, id), null);
  assert.deepEqual(projectTranscriptionToLegacySteps(restored).steps, []);
  assert.equal(projectTranscriptionToLegacySteps(restored).readyToSubmit, false);
});

// Constructed geometry below checks decision safety, not handwriting accuracy.
function relationFixture() {
  const strokes = [mark("lhs", [[20, 52], [33, 65]]), mark("num", [[40, 35], [90, 45]]),
    mark("bar", [[40, 60], [100, 60]]), mark("den", [[40, 75], [90, 85]])];
  const scope = (id: string, ids: string[], kind: ScopeProposal["kind"], flags: string[] = []): ScopeProposal => ({
    id, strokeIds: ids, candidateStrokeIds: ids, kind, flags, regionIds: [], rawLabel: "software_fixture", rawScore: null, coverage: {}, method: "TEST_ONLY" });
  const prefix = scope("prefix", ["lhs"], "UNKNOWN"), host = scope("fraction", ["num", "bar", "den"], "MATH", ["FRACTION_BAR_WITH_ABOVE_BELOW_SUPPORT"]);
  const layout = scope("formula", strokes.map(s => s.id), "MATH");
  return { source: inkSource(strokes), prefix, host, layout, scope };
}
test("sprint05: exact formula support reconciles a compact fraction prefix with immutable source and unique ownership", () => {
  const f = relationFixture(), before = JSON.stringify(f);
  const r = reconcileLayoutScopeCandidates(f.source, [f.prefix, f.host], [f.layout], 10);
  assert.equal(r.scopes.length, 1); assert.equal(r.decisions[0].decision, "MERGE");
  assert.deepEqual(r.scopes[0].strokeIds, f.source.strokes.map(s => s.id));
  assert.ok(r.decisions[0].positive.includes("COMPACT_LEFT_PREFIX_WITHIN_FRACTION_BODY_SUPPORT"));
  assert.equal(JSON.stringify(f), before); assert.deepEqual(scopeIntegrity(f.source, r.scopes).duplicateOwnership, []);
});
test("sprint05: independent equality anchors and a page-sized layout cannot force a merge", () => {
  const f = relationFixture(); f.host.flags.push("PARALLEL_EQUALITY_STROKES"); f.prefix.flags.push("PARALLEL_EQUALITY_STROKES");
  const r = reconcileLayoutScopeCandidates(f.source, [f.prefix, f.host], [f.layout], 10);
  assert.equal(r.scopes.length, 2); assert.ok(r.decisions[0].negative.includes("INDEPENDENT_EQUALITY_ANCHORS"));
  const extra = mark("next-line", [[20, 160], [60, 180]]); f.source.strokes.push(extra);
  const third = f.scope("third", [extra.id], "MATH"); f.layout.strokeIds = f.layout.candidateStrokeIds = f.source.strokes.map(s => s.id);
  const page = reconcileLayoutScopeCandidates(f.source, [f.prefix, f.host, third], [f.layout], 10);
  assert.equal(page.scopes.length, 3); assert.equal(page.decisions[0].decision, "KEEP_GEOMETRY");
});
test("sprint05: text evidence and unresolved delimiters remain separate from a math fraction", () => {
  for (const negative of ["TEXT", "DELIMITER"] as const) {
    const f = relationFixture();
    if (negative === "TEXT") f.prefix.kind = "TEXT"; else f.prefix.flags.push("MULTI_ROW_DELIMITER_UNRESOLVED");
    const r = reconcileLayoutScopeCandidates(f.source, [f.prefix, f.host], [f.layout], 10);
    assert.equal(r.scopes.length, 2); assert.ok(r.decisions[0].negative.includes(negative === "TEXT" ? "TEXT_OR_MIXED_EVIDENCE" : "UNRESOLVED_MULTI_ROW_DELIMITER"));
  }
});
test("sprint05: absent or partial layout leaves complete fraction ownership unchanged", () => {
  const f = relationFixture();
  for (const learned of [[], [{ ...f.layout, strokeIds: ["lhs", "num"], candidateStrokeIds: ["lhs", "num"] }]]) {
    const r = reconcileLayoutScopeCandidates(f.source, [f.prefix, f.host], learned, 10);
    assert.deepEqual(new Set(r.scopes.flatMap(s => s.strokeIds)), new Set(f.source.strokes.map(s => s.id)));
    assert.equal(r.scopes.length, 2); assert.ok(r.scopes.some(s => JSON.stringify(s.strokeIds) === JSON.stringify(f.host.strokeIds)));
  }
});
test("sprint05: competing fraction hosts abstain rather than choosing detector array order", () => {
  const f = relationFixture(), clone = f.source.strokes.slice(1).map(s => ({ ...s, id: `other-${s.id}` }));
  f.source.strokes.push(...clone);
  const other = f.scope("other", clone.map(s => s.id), "MATH", ["FRACTION_BAR_WITH_ABOVE_BELOW_SUPPORT"]);
  const alternative = f.scope("alternative", ["lhs", ...clone.map(s => s.id)], "MATH");
  for (const learned of [[f.layout, alternative], [alternative, f.layout]]) {
    const r = reconcileLayoutScopeCandidates(f.source, [f.prefix, f.host, other], learned, 10);
    assert.equal(r.scopes.length, 3); assert.ok(r.decisions.every(d => d.negative.includes("COMPETING_RELATION_HYPOTHESES")));
  }
});

test("native-htr: recheck completed line support without widening row tolerance", () => {
  const s = inkSource([mark("a", [[100, 140], [112, 174]]), mark("b", [[120, 140], [132, 174]]),
    mark("c", [[140, 140], [152, 174]]), mark("descender", [[134, 174], [145, 218]]), mark("late-mark", [[100, 185], [104, 187]])]);
  const before = JSON.stringify(s);
  const result = constructScopeCandidates(s, { status: "NONE", model: "NONE", regions: [] }, t, "GEOMETRY");
  assert.ok(result.trace.some(e => (e as { stage: string }).stage === "POST_COMPLETION_FRAGMENT_RECONCILIATION"));
  assert.ok(result.scopes.some(scope => scope.strokeIds.includes("descender") && scope.strokeIds.includes("late-mark") && scope.strokeIds.includes("a")));
  assert.equal(JSON.stringify(s), before); assert.deepEqual(scopeIntegrity(s, result.scopes).duplicateOwnership, []);
});
test("native-htr: completing satellites does not join independent equality rows", () => {
  const s = inkSource([...equation("a", 100), ...equation("b", 145), mark("late-dot", [[42, 96]])]);
  const result = constructScopeCandidates(s, { status: "NONE", model: "NONE", regions: [] }, t, "GEOMETRY");
  assert.ok(result.scopes.every(scope => !(scope.strokeIds.includes("ax") && scope.strokeIds.includes("bx"))));
  assert.deepEqual(scopeIntegrity(s, result.scopes).missing, []);
});
test("native-htr: unresolved multi-row delimiter remains separate after completion", () => {
  const s = inkSource([...equation("a", 100, 35), ...equation("b", 165, 35), mark("bracket", [[45, 99], [28, 99], [28, 183], [45, 183]])]);
  const result = constructScopeCandidates(s, { status: "NONE", model: "NONE", regions: [] }, t, "GEOMETRY");
  const delimiter = result.scopes.find(scope => scope.strokeIds.includes("bracket"))!;
  assert.equal(delimiter.kind, "UNKNOWN"); assert.ok(!delimiter.strokeIds.includes("ax") && !delimiter.strokeIds.includes("bx"));
  assert.ok(result.relations.some(r => r.strokeIds.includes("bracket"))); assert.deepEqual(scopeIntegrity(s, result.scopes).missing, []);
});
