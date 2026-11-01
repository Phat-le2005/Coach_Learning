import test from "node:test";
import assert from "node:assert/strict";
import { Worker as NodeWorker } from "node:worker_threads";
import { resolve } from "node:path";
import { PerspectiveCamera, OrthographicCamera, Vector3 } from "three";
import { GraphSamplingQueue, type SamplingInput, type SamplingRequest, type SamplingResponse } from "../src/features/math-canvas/sampling-protocol.js";
import { fitGraphCamera } from "../src/features/math-canvas/fit-camera.js";
import { fitCameraPreset, type GraphCameraPreset } from "../src/features/math-canvas/camera-presets.js";
import { frameCurve } from "../src/features/math-canvas/curve-framing.js";
import { analyzeXPolynomialEquation, sampleXPolynomialEquation } from "../src/features/math-canvas/univariate-equation.js";
import { insertMathSnippet } from "../src/features/math-canvas/formula-editing.js";
import { createCoefficientExploration } from "../src/features/math-canvas/coefficient-exploration.js";
import { createExplorationDraft } from "../src/features/math-canvas/exploration.js";
import { parseMathExpression, sampleGraph, sampleImplicit, DEFAULT_GRAPH } from "../src/features/math-canvas/expression.js";
import { sampleImplicitGeometry } from "../src/features/math-canvas/geometry.js";
import { selectLassoStrokes } from "../src/features/math-workspace/utils/lasso.js";
import { mathCanvasProxyPath } from "../src/lib/api/math-canvas-path.js";
import { describeGraphView, isSpatialView, resolveGraphExpression, resolveGraphView, sampleViewPoint } from "../src/features/math-canvas/presentation.js";
import type { InkPoint, InkStroke } from "../src/features/math-workspace/types.js";

test("recognizes Unicode and LaTeX paraboloids with the same geometry", () => {
  for (const formula of ["z = x² + y²", "z=x^{2}+y^{2}", "f(x,y)=x^2+y^2"]) {
    const model = parseMathExpression(formula);
    assert.equal(model.dimension, "3D");
    assert.equal(sampleGraph(model, DEFAULT_GRAPH, 2, 3), 13);
  }
});
test("2D and explicit constant surfaces are classified correctly", () => {
  assert.equal(parseMathExpression("y=sin(x)").dimension, "2D");
  assert.equal(parseMathExpression("z=2").dimension, "3D");
  assert.equal(parseMathExpression("x+y").dimension, "3D");
  assert.throws(() => parseMathExpression("y=x+y"));
});
test("parameters, shifts, signed scale and offset change sampled values", () => {
  const model = parseMathExpression("z=a*x²+b*y²");
  assert.deepEqual(model.parameters, ["a", "b"]);
  assert.equal(sampleGraph(model, { ...DEFAULT_GRAPH, parameters: { a: 2, b: -1 }, shift_x: 1, shift_y: 2, scale: -2, offset: 5 }, 3, 3), -9);
});
test("nested fractions, sqrt, implicit multiplication, unary minus and right-associative powers", () => {
  assert.equal(sampleGraph(parseMathExpression(String.raw`y=\frac{\frac{x^{2}}{2}}{4}`), DEFAULT_GRAPH, 4), 2);
  assert.equal(sampleGraph(parseMathExpression(String.raw`y=\sqrt{x^{2}+1}`), DEFAULT_GRAPH, 0), 1);
  assert.equal(sampleGraph(parseMathExpression("y=2x+3(x+1)"), DEFAULT_GRAPH, 2), 13);
  assert.equal(sampleGraph(parseMathExpression("y=-x^2"), DEFAULT_GRAPH, 2), -4);
  assert.equal(sampleGraph(parseMathExpression("y=2^3^2"), DEFAULT_GRAPH, 0), 512);
});

test("conventional sine/cosine powers from OCR mean powers of the function value", () => {
  for (const source of ["y=sin²(x)+cos²(x)", "y=sin^2(x)+cos^2(x)", String.raw`y = \sin ^ { 2 } ( x ) + \cos ^ { 2 } ( x )`]) {
    const model = parseMathExpression(source);
    for (const x of [-2, -.3, 0, .7, Math.PI / 2]) assert.ok(Math.abs(sampleGraph(model, DEFAULT_GRAPH, x) - 1) < 1e-12, source);
    const restored = parseMathExpression(model.expression);
    assert.deepEqual(restored.node, model.node, "canonical output must restore the same mathematical AST");
  }
  assert.ok(Math.abs(sampleGraph(parseMathExpression("y=2cos²(3*x)+sin³(x)"), DEFAULT_GRAPH, .4) - (2*Math.cos(1.2)**2+Math.sin(.4)**3))<1e-12);
  assert.ok(Math.abs(sampleGraph(parseMathExpression("y=cos²(sin³(x))"), DEFAULT_GRAPH, .4) - Math.cos(Math.sin(.4)**3)**2)<1e-12);
  assert.ok(Math.abs(sampleGraph(parseMathExpression("y=sin²(x)^3"), DEFAULT_GRAPH, .4)-Math.sin(.4)**6)<1e-12);
  assert.ok(Math.abs(sampleGraph(parseMathExpression("y=-cos²(x)"), DEFAULT_GRAPH, .4)+Math.cos(.4)**2)<1e-12);
  assert.ok(Math.abs(sampleGraph(parseMathExpression("y=cos²(x)sin²(x)"), DEFAULT_GRAPH, .4)-Math.cos(.4)**2*Math.sin(.4)**2)<1e-12);
});

test("function powers keep undefined arguments undefined and reject ambiguous inverse notation", () => {
  assert.ok(Number.isNaN(sampleGraph(parseMathExpression("y=cos²(1/x)"), DEFAULT_GRAPH, 0)));
  for (const source of ["y=sin^-1(x)", String.raw`y=\cos^{-1}(x)`, "y=cos²x", "y=cos²(x", "y=sin^a(x)", "y=sin²(window.alert(x))"]) assert.throws(()=>parseMathExpression(source),source);
  assert.ok(Math.abs(sampleGraph(parseMathExpression("y=(sin(x))^(-1)"),DEFAULT_GRAPH,.4)-1/Math.sin(.4))<1e-12);
});
test("undefined math stays undefined rather than becoming plausible surface values", () => {
  assert.ok(Number.isNaN(sampleGraph(parseMathExpression("y=1/x"), DEFAULT_GRAPH, 0)));
  assert.ok(Number.isNaN(sampleGraph(parseMathExpression("y=sqrt(x)"), DEFAULT_GRAPH, -1)));
  assert.ok(Number.isNaN(sampleGraph(parseMathExpression("z=exp(x)"), DEFAULT_GRAPH, 1000)));
});
test("rejects executable syntax, unbalanced and excessive input", () => {
  for (const source of ["z=window.alert(1)", "z=x.constructor", "z=constructor(x)", "z=<script>", "x=y=1", "z=sin(x", "z=z+x", "z=" + "(".repeat(60) + "x" + ")".repeat(60), "z=" + "1".repeat(501)]) {
    assert.throws(() => parseMathExpression(source), source);
  }
});

test("implicit equations retain both sides, classify coordinates and discover parameters", () => {
  const sphere = parseMathExpression("x²+y²+z²=r²");
  assert.equal(sphere.kind, "implicit"); assert.equal(sphere.dimension, "3D");
  assert.equal(sphere.expression, "x^2+y^2+z^2=r^2"); assert.deepEqual(sphere.parameters, ["r"]);
  assert.equal(sampleImplicit(sphere, { ...DEFAULT_GRAPH, parameters: { r: 2 } }, 0, 0, 2), 0);
  assert.equal(parseMathExpression("x²+y²=r²").dimension, "2D");
  assert.equal(parseMathExpression("x=2").kind, "implicit");
  assert.equal(parseMathExpression("sin(x)-(x)=2y").expression, "sin(x)-(x)=2*y");
  assert.throws(() => parseMathExpression("2=3"));
});

test("a reversed y equation retains its vertex outside the contour box in both camera modes", () => {
  const relation = parseMathExpression(String.raw`x^{2}+2x-3=y`);
  const original = structuredClone(relation);
  const explicit = parseMathExpression("y=x^2+2x-3");
  assert.equal(resolveGraphExpression(relation).kind, "explicit");
  for (const view_mode of ["2D", "3D"] as const) {
    const settings = { ...DEFAULT_GRAPH, view_mode };
    assert.equal(resolveGraphView(relation, settings), view_mode === "2D" ? "CURVE_2D" : "CURVE_3D");
    assert.deepEqual(sampleViewPoint(relation, settings, -1), [-1, -4, 0]);
    for (let x = -3; x <= 3; x += .125) {
      const point = sampleViewPoint(relation, settings, x);
      assert.deepEqual(point, sampleViewPoint(explicit, settings, x));
      assert.equal(sampleImplicit(relation, settings, point[0], point[1]), 0);
    }
  }
  assert.deepEqual(relation, original, "rendering must preserve the canonical relation and AST for saving");
});

test("reversed function rendering preserves parameters and undefined values without reinterpreting implicit relations", () => {
  const settings = { ...DEFAULT_GRAPH, parameters: { a: 2 } };
  assert.deepEqual(sampleViewPoint(parseMathExpression("a*x^2=y"), settings, -2), [-2, 8, 0]);
  assert.ok(Number.isNaN(sampleViewPoint(parseMathExpression("1/x=y"), settings, 0)[1]));
  for (const formula of ["x^2+y^2=4", "x+y=y", "x*y=y", "x^2=y^2", "x^2+z=y", "x^2+2x-3=0"]) {
    const model = parseMathExpression(formula);
    assert.strictEqual(resolveGraphExpression(model), model, formula);
  }
});

test("fixed polynomial coefficients become editable parameters without changing the initial curve or view", () => {
  for (const formula of ["x^{2}+2x-3=y", "y=x^2+2x-3", "y=(x+1)^2-4"]) {
    const model = parseMathExpression(formula);
    const settings = { ...DEFAULT_GRAPH, view_mode: "3D" as const };
    const original = structuredClone({ model, settings });
    const draft = createCoefficientExploration(model, settings);
    assert.ok(draft, formula);
    assert.equal(draft.model.expression, "y=a*x^2+b*x+c");
    assert.deepEqual(draft.settings.parameters, { a: 1, b: 2, c: -3 });
    assert.equal(draft.settings.view_mode, "3D");
    for (let x = -3; x <= 3; x += .125) assert.deepEqual(sampleViewPoint(draft.model, draft.settings, x), sampleViewPoint(model, settings, x));
    const changed = { ...draft.settings, parameters: { ...draft.settings.parameters, a: -1 } };
    assert.equal(sampleGraph(draft.model, changed, 2), -3);
    draft.settings.parameters.b = 5;
    assert.deepEqual({ model, settings }, original, "the original relation and settings must remain independent");
  }
});

test("coefficient controls retain transforms and handle linear, constant and unsupported forms conservatively", () => {
  const settings = { ...DEFAULT_GRAPH, scale: -2, offset: 1, shift_x: .5 };
  for (const [formula, parameters] of [["y=2x-3", { a: 2, b: -3 }], ["y=4", { a: 4 }], ["y=0", { a: 0 }], ["y=-x^2", { a: -1, b: 0, c: 0 }]] as const) {
    const model = parseMathExpression(formula), draft = createCoefficientExploration(model, settings);
    assert.ok(draft, formula);
    assert.deepEqual(draft.settings.parameters, parameters);
    for (const x of [-2, 0, 1, 3]) assert.equal(sampleGraph(draft.model, draft.settings, x), sampleGraph(model, settings, x));
  }
  for (const formula of ["y=sin(x)", "y=1/x", "y=x^3", "y=6x^2", "y=a*x^2", "x^2+y^2=4", "x^2=0", "x+y=y", "z=x^2+y^2"]) {
    assert.equal(createCoefficientExploration(parseMathExpression(formula), DEFAULT_GRAPH), null, formula);
  }
});

test("sampled sphere vertices satisfy the equation and changing radius changes geometry", () => {
  const model = parseMathExpression("x²+y²+z²=r²");
  for (const radius of [1, 2]) {
    const data = sampleImplicitGeometry(model, { ...DEFAULT_GRAPH, parameters: { r: radius } }, false, 16);
    assert.equal(data.primitive, "triangles"); assert.ok(data.positions.length > 100);
    assert.equal(data.positions.length % 9, 0);
    for (let i = 0; i < data.positions.length; i += 3) {
      const [x,z,y] = data.positions.slice(i,i+3);
      assert.ok(Math.abs(x*x+y*y+z*z-radius*radius) < .001);
    }
  }
});

test("implicit circles, vertical lines, plane axis mapping and spatial cross-sections", () => {
  const circle = sampleImplicitGeometry(parseMathExpression("x²+y²=4"), DEFAULT_GRAPH, false, 24);
  assert.equal(circle.primitive, "segments"); assert.ok(circle.positions.length > 100);
  for (let i = 0; i < circle.positions.length; i += 3) {
    const [x,y,z] = circle.positions.slice(i,i+3); assert.ok(Math.abs(x*x+y*y-4) < .001); assert.equal(z, 0);
  }
  const vertical = sampleImplicitGeometry(parseMathExpression("x=2"), DEFAULT_GRAPH, false, 16);
  assert.ok(vertical.positions.length > 0);
  for (let i=0; i<vertical.positions.length; i+=3) assert.ok(Math.abs(vertical.positions[i]-2) < .001);
  const sphere = parseMathExpression("x²+y²+z²=4");
  const slice = sampleImplicitGeometry(sphere, { ...DEFAULT_GRAPH, slice_y: 1 }, true, 24);
  assert.ok(slice.positions.length > 0);
  for (let i=0; i<slice.positions.length; i+=3) assert.ok(Math.abs(slice.positions[i]**2 + slice.positions[i+1]**2 - 3) < .001);
  assert.equal(sampleImplicitGeometry(sphere, { ...DEFAULT_GRAPH, slice_y: 3 }, true, 16).positions.length, 0);
  const plane = sampleImplicitGeometry(parseMathExpression("x+2y+3z=1"), DEFAULT_GRAPH, false, 12);
  assert.ok(plane.positions.length > 0);
  for (let i=0; i<plane.positions.length; i+=3) assert.ok(Math.abs(plane.positions[i]+2*plane.positions[i+2]+3*plane.positions[i+1]-1)<.001);
});

test("implicit poles, empty real sets and degenerate identities do not fabricate surfaces", () => {
  for (const formula of ["1/x=0", "x²+y²+z²=-1", "x=x"]) {
    assert.equal(sampleImplicitGeometry(parseMathExpression(formula), DEFAULT_GRAPH, false, 15).positions.length, 0, formula);
  }
});

test("implicit presentation distinguishes level sets from explicit function surfaces", () => {
  const model = parseMathExpression("x²+y²+z²=4");
  assert.equal(resolveGraphView(model, DEFAULT_GRAPH), "LEVEL_SURFACE_3D");
  assert.equal(resolveGraphView(model, { ...DEFAULT_GRAPH, view_mode: "2D" }), "LEVEL_SLICE_2D");
  assert.match(describeGraphView(model, { ...DEFAULT_GRAPH, view_mode: "2D", slice_y: 1 }), /y₀ = 1/);
  assert.equal(resolveGraphView(parseMathExpression("x²+y²=4"), DEFAULT_GRAPH), "CONTOUR_2D");
});
test("canonicalizes numeric formats for backend persistence", () => {
  assert.equal(parseMathExpression("y=01*x+.5").expression, "y=1*x+0.5");
});
test("one-variable functions can switch between 2D and a spatial curve without changing the formula", () => {
  const model = parseMathExpression("y=1-x²");
  const spatial = { ...DEFAULT_GRAPH, view_mode: "3D" as const };
  assert.equal(resolveGraphView(model, DEFAULT_GRAPH), "CURVE_2D");
  assert.equal(resolveGraphView(model, spatial), "CURVE_3D");
  assert.ok(isSpatialView(resolveGraphView(model, spatial)));
  assert.deepEqual(sampleViewPoint(model, spatial, 2), [2, -3, 0]);
  assert.deepEqual(sampleViewPoint(model, spatial, 2), sampleViewPoint(model, DEFAULT_GRAPH, 2));
  assert.equal(model.expression, "y=1-x^2");
  assert.equal(model.dimension, "2D");
});
test("explicit surface extension preserves the curve height along the free z axis", () => {
  const model = parseMathExpression("y=1-x²");
  const extended = { ...DEFAULT_GRAPH, view_mode: "EXTRUDED" as const };
  assert.equal(resolveGraphView(model, extended), "EXTRUDED_3D");
  assert.deepEqual(sampleViewPoint(model, extended, 2, -2), [2, -3, -2]);
  assert.deepEqual(sampleViewPoint(model, extended, 2, 2), [2, -3, 2]);
  assert.match(describeGraphView(model, extended), /z thay đổi tự do/);
});
test("a two-variable surface has a labelled 2D cross-section at the selected y value", () => {
  const model = parseMathExpression("z=x²+y²");
  const slice = { ...DEFAULT_GRAPH, view_mode: "2D" as const, slice_y: 2 };
  assert.equal(resolveGraphView(model, slice), "SLICE_2D");
  assert.equal(isSpatialView(resolveGraphView(model, slice)), false);
  assert.deepEqual(sampleViewPoint(model, slice, 1), [1, 5, 0]);
  assert.deepEqual(sampleViewPoint(model, { ...slice, slice_y: 0 }, 1), [1, 1, 0]);
  assert.match(describeGraphView(model, slice), /y₀ = 2/);
  assert.equal(model.expression, "z=x^2+y^2");
});
test("view changes retain parameter transforms and legacy snapshots retain their default views", () => {
  const curve = parseMathExpression("y=a*x²");
  const legacy = { ...DEFAULT_GRAPH, parameters: { a: 2 }, scale: -1, offset: 4, shift_x: 1 };
  assert.equal(resolveGraphView(curve, legacy), "CURVE_2D");
  assert.deepEqual(sampleViewPoint(curve, { ...legacy, view_mode: "3D" }, 3), [3, -4, 0]);
  const surface = parseMathExpression("z=x²+y²");
  assert.equal(resolveGraphView(surface, DEFAULT_GRAPH), "SURFACE_3D");
  assert.deepEqual(sampleViewPoint(surface, DEFAULT_GRAPH, 1, 2), [1, 5, 2]);
});
const point = (x: number, y: number): InkPoint => ({ x, y, pressure: 0.5 });
const stroke = (id: string, points: InkPoint[], tool: InkStroke["tool"] = "PEN"): InkStroke => ({ id, points, tool, color: "#000000", width: 2 });
test("lasso selects interior dots and crossing segments, excludes outside ink and highlighters", () => {
  const polygon = [point(.2,.2), point(.6,.2), point(.6,.6), point(.2,.6)];
  const strokes = [stroke("dot", [point(.3,.3)]), stroke("crossing", [point(.1,.4), point(.9,.4)]),
    stroke("outside", [point(.8,.8)]), stroke("highlight", [point(.4,.4)], "HIGHLIGHTER")];
  assert.deepEqual(selectLassoStrokes(strokes, polygon).map((s) => s.id), ["dot", "crossing"]);
  assert.equal(strokes.length, 4);
  assert.deepEqual(selectLassoStrokes(strokes, [point(.1,.1),point(.2,.2),point(.3,.3)]), []);
});
test("lasso uses polygon rather than bounding rectangle for concave selections", () => {
  const polygon = [point(.1,.1),point(.8,.1),point(.8,.3),point(.3,.3),point(.3,.8),point(.1,.8)];
  assert.deepEqual(selectLassoStrokes([stroke("cutout", [point(.6,.6)]), stroke("inside",[point(.2,.6)])],polygon).map(s => s.id),["inside"]);
});
test("BFF restricts canvas operations by role, UUID, method and explicit path", () => {
  const id = "11111111-1111-4111-8111-111111111111";
  assert.ok(mathCanvasProxyPath(["attempts",id,"snapshots"],"POST","STUDENT"));
  assert.equal(mathCanvasProxyPath(["teacher","snapshots"],"GET","STUDENT"), null);
  assert.equal(mathCanvasProxyPath(["attempts",id,"explain"],"POST","TEACHER"), null);
  assert.equal(mathCanvasProxyPath(["attempts","..","snapshots"],"POST","STUDENT"), null);
  assert.equal(mathCanvasProxyPath(["attempts",id,"snapshots"],"DELETE","STUDENT"), null);
  assert.ok(mathCanvasProxyPath(["teacher","snapshots"],"GET","TEACHER"));
});

test("rapid slider changes coalesce and obsolete worker replies cannot replace the latest graph", () => {
  const sent: SamplingRequest[] = [], delivered: number[] = [], errors: string[] = [];
  const queue = new GraphSamplingQueue((request) => sent.push(request), (result) => delivered.push(result.positions[0]), (error) => errors.push(error));
  const input: SamplingInput = { model: parseMathExpression("x²+y²+z²=r²"), settings: { ...DEFAULT_GRAPH, parameters: { r: 1 } }, slice: false, resolution: 16 };
  queue.request(input);
  queue.request({ ...input, settings: { ...input.settings, parameters: { r: 2 } } });
  queue.request({ ...input, settings: { ...input.settings, parameters: { r: 3 } } });
  assert.equal(sent.length, 1);
  const data = (value: number) => ({ positions: new Float32Array([value,0,0]), primitive: "triangles" as const, truncated: false });
  queue.accept({ id: sent[0].id, data: data(1) });
  assert.equal(sent.length, 2); assert.equal(sent[1].settings.parameters.r, 3); assert.deepEqual(delivered, []);
  queue.accept({ id: sent[0].id, error: "obsolete" });
  queue.accept({ id: sent[1].id, data: data(3) });
  assert.deepEqual(delivered, [3]); assert.deepEqual(errors, []);
  queue.dispose(); queue.request(input); queue.accept({ id: sent[1].id, data: data(4) });
  assert.equal(sent.length, 2); assert.deepEqual(delivered, [3]);
});

test("worker failures are reported for the current input and the queue accepts a corrected formula", () => {
  const sent: SamplingRequest[] = [], errors: string[] = [];
  const queue = new GraphSamplingQueue((request) => sent.push(request), () => {}, (error) => errors.push(error));
  const input: SamplingInput = { model: parseMathExpression("x=2"), settings: DEFAULT_GRAPH, slice: false, resolution: 16 };
  queue.request(input); queue.accept({ id: sent[0].id, error: "sampling failed" });
  queue.request(input);
  assert.deepEqual(errors, ["sampling failed"]); assert.equal(sent.length, 2);
  queue.dispose();
});

test("the real sampling worker transfers finite sphere and section geometry from a separate thread", { timeout: 10000 }, async (t) => {
  const worker = new NodeWorker(resolve(__dirname, "../../tests/fixtures/math-sampling-worker.cjs"), {
    workerData: { entry: resolve(__dirname, "../src/features/math-canvas/implicit.worker.js") },
  });
  t.after(() => worker.terminate());
  const request = (input: SamplingRequest) => new Promise<SamplingResponse>((accept, reject) => {
    worker.once("message", accept); worker.once("error", reject); worker.postMessage(input);
  });
  const input: SamplingRequest = { id: 1, model: parseMathExpression("x²+y²+z²=r²"), settings: { ...DEFAULT_GRAPH, parameters: { r: 2 } }, slice: false, resolution: 16 };
  const sphere = await request(input);
  assert.ok("data" in sphere); assert.equal(sphere.id, 1); assert.ok(sphere.data.positions instanceof Float32Array);
  assert.ok(sphere.data.positions.length > 100);
  for (let i = 0; i < sphere.data.positions.length; i += 3) {
    const [x,z,y] = sphere.data.positions.slice(i,i+3); assert.ok(Math.abs(x*x+y*y+z*z-4) < .002);
  }
  const section = await request({ ...input, id: 2, slice: true, settings: { ...input.settings, slice_y: 1, view_mode: "2D" } });
  assert.ok("data" in section); assert.equal(section.data.primitive, "segments"); assert.ok(section.data.positions.length > 0);
  for (let i = 0; i < section.data.positions.length; i += 3) {
    const [x,z,depth] = section.data.positions.slice(i,i+3); assert.ok(Math.abs(x*x+z*z-3) < .002); assert.equal(depth, 0);
  }
});

test("camera fitting contains all sampled bounds in wide and narrow perspective viewports", () => {
  const bounds = { min: [-3,0,-3] as [number,number,number], max: [3,18,3] as [number,number,number] };
  for (const aspect of [16/9, .65]) {
    const fitted = fitGraphCamera(bounds, { position: [11,9,13], target: [0,0,0] }, { spatial: true, aspect, halfHeight: 4 });
    assert.ok(fitted);
    const camera = new PerspectiveCamera(42, aspect, .1, 500); camera.position.fromArray(fitted.position); camera.lookAt(new Vector3(...fitted.target)); camera.updateMatrixWorld();
    for (const x of [-3,3]) for (const y of [0,18]) for (const z of [-3,3]) {
      const point = new Vector3(x,y,z).project(camera);
      assert.ok(Math.abs(point.x) <= 1 && Math.abs(point.y) <= 1 && Math.abs(point.z) <= 1);
    }
  }
  assert.equal(fitGraphCamera({ min: [-1,0,-1], max: [1,100000,1] }, { position: [11,9,13], target: [0,0,0] }, { spatial: true, aspect: 1, halfHeight: 4 }), null);
});

test("planar camera fitting preserves coordinate scale and makes a translated curve visible", () => {
  const fitted = fitGraphCamera({ min: [-3,12,0], max: [3,21,0] }, { position: [0,0,16], target: [0,0,0] }, { spatial: false, aspect: .75, halfHeight: 4 });
  assert.ok(fitted);
  const camera = new OrthographicCamera(-3,3,4,-4,.1,500); camera.position.fromArray(fitted.position); camera.zoom = fitted.zoom!;
  camera.lookAt(new Vector3(...fitted.target)); camera.updateProjectionMatrix(); camera.updateMatrixWorld();
  for (const x of [-3,3]) for (const y of [12,21]) {
    const point = new Vector3(x,y,0).project(camera); assert.ok(Math.abs(point.x) <= 1 && Math.abs(point.y) <= 1);
  }
});

test("a cubic's long tail does not shrink its turning points into a line in the default view", () => {
  const model = parseMathExpression("y=x^3-3*x^2+2");
  const points = Array.from({ length: 901 }, (_, i) => sampleViewPoint(model, DEFAULT_GRAPH, -3 + i / 150));
  const original = structuredClone(points);
  const full = { min: [-3, -52, 0] as [number, number, number], max: [3, 2, 0] as [number, number, number] };
  const focused = frameCurve([points], full);
  assert.equal(focused.focused, true);
  assert.deepEqual(focused.bounds, { min: [-3,-3,0], max: [3,3,0] });
  assert.deepEqual(points, original, "focusing must retain the full geometry and every mathematical coordinate");
  for (const aspect of [.7, 2.1]) {
    const fitted = fitGraphCamera(focused.bounds, { position: [11,9,13], target: [0,0,0] }, { spatial: true, aspect, halfHeight: 4, planarCurve: true });
    assert.ok(fitted);
    const camera = new PerspectiveCamera(42, aspect, .1, 500);
    camera.position.fromArray(fitted.position); camera.lookAt(new Vector3(...fitted.target)); camera.updateMatrixWorld();
    const maximum = new Vector3(0,2,0).project(camera), minimum = new Vector3(2,-2,0).project(camera);
    for (const point of [maximum, minimum]) assert.ok(Math.abs(point.x) < 1 && Math.abs(point.y) < 1);
    assert.ok(maximum.distanceTo(minimum) > .25, "both turns must remain visually separated, even in a narrow viewport");
    const whole = fitGraphCamera(full, { position: [11,9,13], target: [0,0,0] }, { spatial: true, aspect, halfHeight: 4 });
    assert.ok(whole, "the complete sampled curve must still have an explicit full view");
  }
});

test("curve focusing keeps shifted features and the parabola vertex, without bridging gaps", () => {
  for (const offset of [0, 20]) {
    const points = Array.from({ length: 901 }, (_, i) => { const x = -3 + i / 150; return [x, x ** 3 - 3 * x ** 2 + 2 + offset, 0] as [number, number, number]; });
    const focused = frameCurve([points], { min: [-3,-52+offset,0], max: [3,2+offset,0] });
    assert.ok(focused.focused);
    assert.ok(focused.bounds.min[1] <= -2+offset && focused.bounds.max[1] >= 2+offset);
    assert.ok(focused.bounds.max[1] - focused.bounds.min[1] < 15);
  }
  const parabola = Array.from({ length: 901 }, (_, i) => { const x = -3 + i / 150; return [x, x*x+2*x-3, 0] as [number, number, number]; });
  const focus = frameCurve([parabola], { min: [-3,-4,0], max: [3,12,0] });
  assert.ok(focus.bounds.min[1] <= -4 && focus.bounds.max[1] >= 0);
  const compact = { min: [-3,-1,0] as [number, number, number], max: [3,1,0] as [number, number, number] };
  assert.deepEqual(frameCurve([], compact), { bounds: compact, focused: false });
  const disconnected: [number,number,number][][] = [[[-3,90,0],[-1,80,0]], [[1,120,0],[3,110,0]]];
  assert.equal(frameCurve(disconnected, { min: [-3,80,0], max: [3,120,0] }).focused, false, "do not invent central features across a discontinuity");
});

test("fit restores a readable planar curve angle when the current 3D camera is edge-on", () => {
  const bounds = { min: [-3,-3,0] as [number,number,number], max: [3,3,0] as [number,number,number] };
  const fitted = fitGraphCamera(bounds, { position: [16,0,0], target: [0,0,0] }, { spatial: true, aspect: 2, halfHeight: 4, planarCurve: true });
  assert.ok(fitted);
  const camera = new PerspectiveCamera(42, 2, .1, 500); camera.position.fromArray(fitted.position); camera.lookAt(new Vector3(...fitted.target)); camera.updateMatrixWorld();
  const left = new Vector3(-3,0,0).project(camera), right = new Vector3(3,0,0).project(camera);
  assert.ok(Math.abs(right.x - left.x) > .5, "fitting must not preserve an edge-on angle that collapses the curve");
});

test("quick camera planes respect the surface axis mapping and contain translated geometry", () => {
  const bounds = { min: [4,-2,-6] as [number,number,number], max: [10,16,0] as [number,number,number] };
  for (const dimension of ["2D", "3D"] as const) for (const aspect of [.65, 1.8]) {
    for (const preset of ["PERSPECTIVE", "OXY", "OXZ", "OYZ"] as GraphCameraPreset[]) {
      const saved = fitCameraPreset(preset, bounds, dimension, aspect);
      assert.ok(saved);
      assert.deepEqual(saved.target, [7,7,-3]);
      const direction = new Vector3(...saved.position).sub(new Vector3(...saved.target)).normalize();
      if (preset === "OYZ") assert.ok(direction.x > .999);
      if (preset === "OXY") assert.ok((dimension === "3D" ? direction.y : direction.z) > .999);
      if (preset === "OXZ") assert.ok((dimension === "3D" ? direction.z : direction.y) > .999);
      const camera = new PerspectiveCamera(42, aspect, .1, 500);
      camera.position.fromArray(saved.position); camera.lookAt(new Vector3(...saved.target)); camera.updateMatrixWorld();
      for (const x of [4,10]) for (const y of [-2,16]) for (const z of [-6,0]) {
        const point = new Vector3(x,y,z).project(camera);
        assert.ok(Math.abs(point.x) <= 1 && Math.abs(point.y) <= 1 && Math.abs(point.z) <= 1);
      }
    }
  }
  assert.equal(fitCameraPreset("OXY", bounds, "3D", 0), null);
});

test("resuming exploration retains the equation and current view without mutating saved values", () => {
  const settings = { ...DEFAULT_GRAPH, parameters: { r: 2 }, view_mode: "2D" as const, slice_y: 1 };
  const camera = { position: [0,0,16] as [number,number,number], target: [0,0,0] as [number,number,number], zoom: 1.5 };
  const draft = createExplorationDraft({ expression: "x^2+y^2+z^2=r^2", note: "Observe the section" }, settings, camera);
  assert.equal(draft.source, "x^2+y^2+z^2=r^2"); assert.equal(draft.settings.slice_y, 1); assert.equal(draft.camera.zoom, 1.5);
  draft.settings.parameters.r = 3; draft.camera.position[0] = 4;
  assert.equal(settings.parameters.r, 2); assert.equal(camera.position[0], 0);
});

test("a one-variable quadratic shows its actual roots and an explicitly chosen related function", () => {
  const model = parseMathExpression("x^{2}+2x-3=0");
  const result = analyzeXPolynomialEquation(model, {});
  assert.ok(result);
  assert.equal(result.degree, 2);
  assert.deepEqual(result.roots, [-3, 1]);
  assert.equal(result.solution, "FINITE");
  assert.equal(model.kind, "implicit");
  const related = parseMathExpression(result.relatedFunction);
  assert.equal(related.kind, "explicit");
  for (const root of result.roots) assert.equal(sampleGraph(related, DEFAULT_GRAPH, root), 0);
  const nonzeroRhs = analyzeXPolynomialEquation(parseMathExpression("x²=4"), {});
  assert.ok(nonzeroRhs);
  assert.deepEqual(nonzeroRhs.roots, [-2, 2]);
  assert.equal(sampleGraph(parseMathExpression(nonzeroRhs.relatedFunction), DEFAULT_GRAPH, 0), -4);
});

test("double roots, no-real-root equations and identities do not depend on sign-change sampling", () => {
  const repeated = analyzeXPolynomialEquation(parseMathExpression("(x-1)^2=0"), {});
  assert.ok(repeated);
  assert.deepEqual(repeated.roots, [1]);
  assert.deepEqual(sampleXPolynomialEquation(repeated, 3).positions, [1,-3,0,1,3,0]);
  assert.equal(analyzeXPolynomialEquation(parseMathExpression("x²+1=0"), {})?.solution, "NO_REAL");
  assert.equal(analyzeXPolynomialEquation(parseMathExpression("x-x=0"), {})?.solution, "ALL_REAL");
  assert.equal(analyzeXPolynomialEquation(parseMathExpression("x-x=1"), {})?.solution, "NO_REAL");
  assert.deepEqual(sampleXPolynomialEquation(repeated, .5).positions, []);
});

test("quadratic parameter degeneracy and cancellation preserve real polynomial semantics", () => {
  const model = parseMathExpression("a*x²+b*x+c=0");
  assert.deepEqual(analyzeXPolynomialEquation(model, {a:0,b:2,c:-3})?.roots, [1.5]);
  assert.equal(analyzeXPolynomialEquation(model, {a:0,b:0,c:3})?.solution, "NO_REAL");
  assert.equal(analyzeXPolynomialEquation(model, {a:0,b:0,c:0})?.solution, "ALL_REAL");
  const large = analyzeXPolynomialEquation(parseMathExpression("x²+1000000*x+1=0"), {});
  assert.ok(large);
  assert.ok(Math.abs(large.roots[0] * large.roots[1] - 1) < 1e-10);
});

test("analytic root annotations reject poles, higher degrees and two-coordinate relations", () => {
  for (const source of ["sin(x)=0", "x^3=0", "1/(x-1)=0", "x²+y²=1", "z=x²", "y=x²", "x/a=0"]) {
    assert.equal(analyzeXPolynomialEquation(parseMathExpression(source), {a:0}), null, source);
  }
});

test("formula keys preserve selected expressions, replace constants and keep the caret inside functions", () => {
  const squared = insertMathSnippet("y=x+1", 2, 5, "", "^2", "x");
  assert.ok(squared);
  assert.equal(sampleGraph(parseMathExpression(squared.text), DEFAULT_GRAPH, 2), 9);
  assert.equal(squared.text, "y=(x+1)^2");
  assert.equal(insertMathSnippet("y=x", 2, 3, "pi", "", "")?.text, "y=pi");
  const sine = insertMathSnippet("y=", 2, 2, "sin(", ")", "x");
  assert.ok(sine);
  assert.equal(sine.text.slice(sine.selectionStart, sine.selectionEnd), "x");
  assert.equal(sine.text, "y=sin(x)");
  assert.equal(insertMathSnippet("x".repeat(500), 500, 500, "pi", "", ""), null);
});
