import test from "node:test";
import assert from "node:assert/strict";
import { Worker } from "node:worker_threads";
import { resolve } from "node:path";
import { compileLab, describeLabDocument, LAB_EXAMPLES, parseLabDraft, validLabCamera, type LabDocument } from "../src/features/math-canvas/lab-spec.js";
import { numericalDerivative, numericalIntegral, piecewiseValue, sampleLab, type LabDrawing } from "../src/features/math-canvas/lab-geometry.js";
const example = (id: string) => structuredClone(LAB_EXAMPLES.find((item) => item.id === id)!.document);
const close = (actual: number, expected: number, tolerance = 1e-6) => assert.ok(Math.abs(actual - expected) < tolerance, `${actual} != ${expected}`);

test("every gallery document compiles into an editable mathematical representation", () => {
  for (const item of LAB_EXAMPLES) {
    const compiled = compileLab(item.document), parameters = Object.fromEntries(compiled.parameters.map((name) => [name, 1]));
    assert.deepEqual(compileLab(compiled.document).parameters, compiled.parameters);
    const drawing = sampleLab(compiled.document, parameters, 3); assert.ok(drawing.lines.length, item.id);
    assert.ok(drawing.lines.every((line) => line.points.every((point) => point.every(Number.isFinite))));
  }
});
test("piecewise branch precedence, gaps and open endpoints preserve mathematical membership", () => {
  const document: LabDocument = { version: 1, kind: "PIECEWISE", dimension: "2D", branches: [{ expression: "-x", condition: "x<0" }, { expression: "x^2+1", condition: "x>=0" }] };
  const model = compileLab(document);
  assert.deepEqual(piecewiseValue(model, 0, {}), { value: 1, branch: 1 }); close(piecewiseValue(model, -2, {}).value, 2);
  const drawing = sampleLab(document, {}, 3);
  assert.ok(drawing.markers.some((marker) => Math.abs(marker.point[0]) < 1e-7 && Math.abs(marker.point[1]) < 1e-7 && marker.open));
  assert.ok(drawing.markers.some((marker) => Math.abs(marker.point[0]) < 1e-7 && Math.abs(marker.point[1] - 1) < 1e-7 && !marker.open));
  assert.ok(drawing.lines.every((line) => !line.points.some((point) => point[0] < 0) || !line.points.some((point) => point[0] > 0)), "disjoint rules must not be joined");
  document.branches[1].condition = "x>1";
  assert.ok(Number.isNaN(piecewiseValue(compileLab(document), .5, {}).value));
  document.branches[0].condition = "x<=2"; assert.equal(piecewiseValue(compileLab(document), 1.5, {}).branch, 0);
});
test("parametric curves use t as their coordinate and support arbitrary composed expressions", () => {
  const ellipse = example("ellipse"), drawing = sampleLab(ellipse, { a: 2, b: 1 }, 3);
  assert.deepEqual(compileLab(ellipse).parameters, ["a", "b"]);
  for (const point of drawing.lines[0].points) close(point[0] ** 2 / 4 + point[1] ** 2, 1);
  const helix = example("helix"); assert.equal(helix.kind, "PARAMETRIC");
  if (helix.kind !== "PARAMETRIC") return;
  helix.coordinates = ["cos(2*t)+sin(t)", "sin(2*t)", "t/3"];
  const space = sampleLab(helix, {}, 3); assert.ok(space.lines[0].points.some((point) => Math.abs(point[2]) > 1));
  close(space.markers[0].point[2], 0);
});
test("vector sums use components rather than confusing them with endpoint coordinates", () => {
  const document: LabDocument = { version: 1, kind: "VECTOR", dimension: "3D", origin: ["2", "3", "4"], u: ["1", "0", "2"], v: ["0", "2", "1"], operation: "SUM" };
  const drawing = sampleLab(document, {}, 5);
  assert.deepEqual(drawing.lines[2].points, [[2, 3, 4], [3, 5, 7]]);
  document.operation = "PROJECTION";
  assert.deepEqual(sampleLab(document, {}, 5).lines[2].points[1], [2, 3.8, 4.4]);
  document.v = ["0", "0", "0"];
  assert.match(sampleLab(document, {}, 5).notices.join(" "), /v = 0/);
});
test("numerical calculus distinguishes smooth derivatives from corners and undefined domains", () => {
  close(numericalDerivative((x) => x ** 3 - 2 * x, 2)!, 10, 1e-5);
  assert.equal(numericalDerivative(Math.abs, 0), null); assert.equal(numericalDerivative(Math.sqrt, 0), null);
  assert.equal(numericalDerivative((x) => 1 / x, 0), null);
  close(numericalIntegral((x) => x * x - 1, -1, 1)!.value, -4 / 3);
  close(numericalIntegral((x) => x * x - 1, 1, -1)!.value, 4 / 3);
  assert.equal(numericalIntegral((x) => 1 / x, -1, 1), null);
  assert.equal(numericalIntegral(Math.sqrt, -1, 1), null);
  assert.deepEqual(numericalIntegral(Math.sin, 1, 1), { value: 0, error: 0 });
});
test("midpoint rectangles converge and never shade an invalid integral", () => {
  const document = example("calculus"); if (document.kind !== "CALCULUS") return;
  document.expression = "x^2"; document.bounds = [0, 1]; document.rectangles = 4;
  const coarse = sampleLab(document, {}, 3); document.rectangles = 120;
  const fine = sampleLab(document, {}, 3);
  assert.equal(fine.polygons.length, 120);
  assert.ok(Math.abs(Number(fine.measurements[3].value) - 1 / 3) < Math.abs(Number(coarse.measurements[3].value) - 1 / 3));
  document.expression = "1/x"; document.bounds = [-1, 1];
  const invalid = sampleLab(document, {}, 3); assert.equal(invalid.polygons.length, 0); assert.equal(invalid.measurements[2].value, "Chưa xác định");
  assert.ok(invalid.lines.filter((line)=>!line.dashed).every((line) => !line.points.some((point) => point[0] < 0) || !line.points.some((point) => point[0] > 0)));
});
test("typed inputs reject executable source, wrong coordinates, dimensions and unbounded documents", () => {
  const parametric = example("ellipse"); if (parametric.kind !== "PARAMETRIC") return;
  for (const expression of ["window.alert(t)", "x+t", "y", "z", "sin(", "1e309"]) assert.throws(() => compileLab({ ...parametric, coordinates: [expression, "t"] }));
  assert.throws(() => compileLab({ ...parametric, interval: [2, 1] })); assert.throws(() => compileLab({ ...parametric, dimension: "3D" }));
  const piecewise = example("piecewise"); if (piecewise.kind !== "PIECEWISE") return;
  assert.throws(() => compileLab({ ...piecewise, branches: [{ expression: "x", condition: "y<1" }] }));
  assert.throws(() => compileLab({ ...piecewise, branches: Array.from({ length: 7 }, () => piecewise.branches[0]) }));
  const calculus = example("calculus"); if (calculus.kind !== "CALCULUS") return;
  assert.throws(() => compileLab({ ...calculus, rectangles: 100000 }));
  const six = compileLab({ ...parametric, coordinates: ["a+b+c+d+f+g+t", "t"] }); assert.equal(six.parameters.length, 6);
});
test("bounded drafts restore editable documents and exclude malformed parameter caches", () => {
  const draft = { document: example("helix"), parameters: { a: 2 }, domain: 3, note: "Dự đoán bước xoắn" };
  assert.deepEqual(parseLabDraft(JSON.stringify(draft)), draft);
  for (const invalid of [{ ...draft, domain: 30 }, { ...draft, parameters: { a: 6 } }, { ...draft, parameters: { t: 1 } }, { ...draft, note: "a".repeat(1001) }]) assert.equal(parseLabDraft(JSON.stringify(invalid)), null);
  assert.equal(parseLabDraft("not json"), null);
  const camera={position:[4,5,16],target:[4,5,0],zoom:2.5};
  assert.deepEqual(parseLabDraft(JSON.stringify({...draft,camera}))?.camera,camera);
  assert.equal(validLabCamera({...camera,zoom:0}),false);
  assert.equal(validLabCamera({...camera,position:[4,5,0]}),false);
  assert.equal(parseLabDraft(JSON.stringify({...draft,camera:{...camera,zoom:100}}))?.camera,undefined);
  for(const item of LAB_EXAMPLES)assert.ok(describeLabDocument(item.document).every((description)=>typeof description==="string"&&description.length>0));
});
test("the actual exploration worker samples a spatial curve outside the UI thread", { timeout: 10000 }, async (t) => {
  const worker = new Worker(resolve(__dirname, "../../tests/fixtures/math-sampling-worker.cjs"), { workerData: { entry: resolve(__dirname, "../src/features/math-canvas/lab.worker.js") } }); t.after(() => worker.terminate());
  const response = await new Promise<{ id: number; drawing: LabDrawing }>((accept, reject) => { worker.once("message", accept); worker.once("error", reject); worker.postMessage({ id: 7, document: example("helix"), parameters: { a: 2 }, domain: 3 }); });
  assert.equal(response.id, 7); assert.ok(response.drawing.lines[0].points.length > 700); assert.ok(response.drawing.markers.length);
});
