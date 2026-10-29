import type { GraphCamera } from "./expression";

type Point = [number, number, number];
export interface GraphBounds { min: Point; max: Point }

/** Fit sampled geometry without changing its coordinates or exceeding saved camera limits. */
export function fitGraphCamera(bounds: GraphBounds, current: GraphCamera,
  view: { spatial: boolean; aspect: number; halfHeight: number; fov?: number }): GraphCamera | null {
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
  const radius = Math.max(.1, Math.hypot(...size) / 2);
  const distance = Math.max(1, radius * 1.15 / Math.sin(Math.min(halfVertical, halfHorizontal)));
  if (!Number.isFinite(distance) || distance > 120) return null;
  let direction = current.position.map((value, i) => value - current.target[i]);
  const length = Math.hypot(...direction);
  direction = length > 0 ? direction.map((value) => value / length) : [0, 0, 1];
  return { position: center.map((value, i) => value + direction[i] * distance) as Point, target: center, zoom: 1 };
}
