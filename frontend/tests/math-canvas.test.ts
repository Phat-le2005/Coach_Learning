import test from "node:test";
import assert from "node:assert/strict";
import { parseMathExpression, sampleGraph, sampleImplicit, DEFAULT_GRAPH } from "../src/features/math-canvas/expression.js";
import { sampleImplicitGeometry } from "../src/features/math-canvas/geometry.js";
import { selectLassoStrokes } from "../src/features/math-workspace/utils/lasso.js";
import { mathCanvasProxyPath } from "../src/lib/api/math-canvas-path.js";
import { describeGraphView, isSpatialView, resolveGraphView, sampleViewPoint } from "../src/features/math-canvas/presentation.js";
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
