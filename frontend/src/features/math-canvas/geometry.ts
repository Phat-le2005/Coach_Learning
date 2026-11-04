import { evaluateMath, type GraphSettings, type MathExpression } from "./expression";

type Point = [number, number, number];
interface Vertex { point: Point; value: number }
export interface SampledGeometry { positions: number[]; primitive: "triangles" | "segments"; truncated: boolean }
const mix = (a: Point, b: Point, t: number): Point => a.map((v, i) => v + (b[i] - v) * t) as Point;

/** Bracket a real zero. A sign change across a pole must not create geometry. */
function crossing(a: Vertex, b: Vertex, field: (p: Point) => number): Point | null {
  if (!Number.isFinite(a.value) || !Number.isFinite(b.value) || (a.value < 0) === (b.value < 0)) return null;
  let lo = a, hi = b;
  for (let i = 0; i < 10; i++) {
    const point = mix(lo.point, hi.point, Math.max(.05, Math.min(.95, lo.value / (lo.value - hi.value))));
    const value = field(point);
    if (!Number.isFinite(value)) return null;
    if (Math.abs(value) <= Math.max(1e-10, Math.min(Math.abs(a.value), Math.abs(b.value)) * .002)) return point;
    if ((value < 0) === (lo.value < 0)) lo = { point, value }; else hi = { point, value };
  }
  return null;
}

/** Marching tetrahedra: bounded scalar-field renderer, independent of Three.js.
 * Future geometry adapters can return the same triangles/segments contract.
 * Thin features smaller than a cell and isolated/tangential zero sets may be missed.
 */
export function sampleImplicitGeometry(model: MathExpression, settings: GraphSettings, slice = false, resolution = 28): SampledGeometry {
  const spatial = model.dimension === "3D" && !slice;
  const n = Math.max(8, Math.min(56, Math.floor(resolution))), domain = settings.domain;
  const positions: number[] = [];
  const result: SampledGeometry = { positions, primitive: spatial ? "triangles" : "segments", truncated: false };
  // Reuse the evaluation scope across samples instead of allocating one per vertex.
  const values = { ...settings.parameters, x: 0, y: 0, z: 0 };
  const field = (p: Point) => {
    [values.x, values.y, values.z] = p;
    const value = evaluateMath(model.node, values);
    return Number.isFinite(value) ? value : NaN;
  };
  const grid: Vertex[] = [];
  const coord = (i: number) => -domain + 2 * domain * i / n;
  const index = (x: number, y: number, z = 0) => (z * (n + 1) + y) * (n + 1) + x;
  for (let k = 0; k <= (spatial ? n : 0); k++) for (let j = 0; j <= n; j++) for (let i = 0; i <= n; i++) {
    const point: Point = spatial ? [coord(i), coord(j), coord(k)]
      : slice ? [coord(i), settings.slice_y ?? 0, coord(j)] : [coord(i), coord(j), 0];
    grid.push({ point, value: field(point) });
  }
  const world = (p: Point): Point => spatial ? [p[0], p[2], p[1]] : slice ? [p[0], p[2], 0] : p;
  const emit = (...points: Point[]) => {
    if (positions.length + points.length * 3 > 540000) { result.truncated = true; return; }
    points.forEach((p) => positions.push(...world(p)));
  };
  // A common body diagonal makes neighboring cube faces share the same split.
  const tetrahedra = [[0,1,3,7],[0,3,2,7],[0,2,6,7],[0,6,4,7],[0,4,5,7],[0,5,1,7]];
  for (let k = 0; k < (spatial ? n : 1); k++) for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) {
    if (positions.length >= 540000) { result.truncated = true; return result; }
    const vertices = spatial ? [0,1,2,3,4,5,6,7].map((v) => grid[index(i + (v & 1), j + ((v >> 1) & 1), k + ((v >> 2) & 1))])
      : [grid[index(i,j)], grid[index(i+1,j)], grid[index(i,j+1)], grid[index(i+1,j+1)]];
    for (const cell of spatial ? tetrahedra : [[0,1,3],[0,3,2]]) {
      const inside = cell.filter((v) => vertices[v].value < 0), outside = cell.filter((v) => vertices[v].value >= 0);
      if (!inside.length || !outside.length || cell.some((v) => !Number.isFinite(vertices[v].value))) continue;
      const edge = (a: number, b: number) => crossing(vertices[a], vertices[b], field);
      if (!spatial) {
        const points = inside.flatMap((a) => outside.map((b) => edge(a,b)));
        if (points.length === 2 && points.every((p) => p !== null)) emit(...points as Point[]);
      } else if (inside.length === 2) {
        const points = [edge(inside[0],outside[0]), edge(inside[0],outside[1]), edge(inside[1],outside[0]), edge(inside[1],outside[1])];
        if (points.every((p) => p !== null)) { const [a,b,c,d] = points as Point[]; emit(a,b,c,b,d,c); }
      } else {
        const singleton = inside.length === 1 ? inside : outside, others = inside.length === 1 ? outside : inside;
        const points = others.map((v) => edge(singleton[0],v));
        if (points.every((p) => p !== null)) emit(...points as Point[]);
      }
    }
  }
  return result;
}
