import type { GraphCamera } from "./expression";

type Point = [number, number, number];
export interface GraphBounds { min: Point; max: Point }

/** Fit sampled geometry without changing its coordinates or exceeding saved camera limits. */
export function fitGraphCamera(bounds: GraphBounds, current: GraphCamera,
  view: { spatial: boolean; aspect: number; halfHeight: number; fov?: number; planarCurve?: boolean }): GraphCamera | null {
  if (![...bounds.min, ...bounds.max, view.aspect].every(Number.isFinite) || view.aspect <= 0) return null;
  const size = bounds.max.map((value, i) => value - bounds.min[i]);
  if (size.some((value) => value < 0)) return null;
  const center = bounds.min.map((value, i) => (value + bounds.max[i]) / 2) as Point;
  if (center.some((value) => Math.abs(value) > 800)) return null;
  if (!view.spatial) {
    const zoom = Math.min(2 * view.halfHeight * view.aspect / Math.max(.1, size[0]) / 1.15,
      2 * view.halfHeight / Math.max(.1, size[1]) / 1.15, 30);
    if (zoom < .05) return null;
    return { position: [center[0], center[1], center[2] + 16], target: center, zoom };
  }
  const halfVertical = (view.fov ?? 42) * Math.PI / 360;
  const halfHorizontal = Math.atan(Math.tan(halfVertical) * view.aspect);
  let direction = current.position.map((value, i) => value - current.target[i]);
  const length = Math.hypot(...direction);
  direction = length > 0 ? direction.map((value) => value / length) : [0, 0, 1];
  // A planar curve viewed edge-on collapses into a line, regardless of zoom.
  if (view.planarCurve && Math.abs(direction[2]) < .35) {
    direction = [.16, .1, 1];
    const safeLength = Math.hypot(...direction);
    direction = direction.map((value) => value / safeLength);
  }
  // Fit the actual projected box instead of an enclosing sphere, which wastes
  // most of the viewport on flat/elongated geometry.
  const horizontalLength = Math.hypot(direction[0], direction[2]);
  const right = horizontalLength > 1e-8 ? [direction[2] / horizontalLength, 0, -direction[0] / horizontalLength] : [1, 0, 0];
  const up = [direction[1] * right[2], direction[2] * right[0] - direction[0] * right[2], -direction[1] * right[0]];
  const dot = (a: number[], b: number[]) => a.reduce((sum, value, i) => sum + value * b[i], 0);
  let distance = 1;
  for (const x of [-size[0] / 2, size[0] / 2]) for (const y of [-size[1] / 2, size[1] / 2]) for (const z of [-size[2] / 2, size[2] / 2]) {
    const corner = [x, y, z], depth = dot(corner, direction);
    distance = Math.max(distance, depth + .2, depth + 1.15 * Math.abs(dot(corner, right)) / Math.tan(halfHorizontal),
      depth + 1.15 * Math.abs(dot(corner, up)) / Math.tan(halfVertical));
  }
  if (!Number.isFinite(distance) || distance > 120) return null;
  return { position: center.map((value, i) => value + direction[i] * distance) as Point, target: center, zoom: 1 };
}
