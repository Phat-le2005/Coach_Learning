import type { InkPoint, InkStroke } from "../types";

function cross(a: InkPoint, b: InkPoint, c: InkPoint) { return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x); }
function onSegment(a: InkPoint, b: InkPoint, p: InkPoint) {
  return Math.abs(cross(a, b, p)) < 1e-9 && p.x >= Math.min(a.x, b.x) - 1e-9 && p.x <= Math.max(a.x, b.x) + 1e-9
    && p.y >= Math.min(a.y, b.y) - 1e-9 && p.y <= Math.max(a.y, b.y) + 1e-9;
}
export function pointInLasso(p: InkPoint, polygon: InkPoint[]): boolean {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const a = polygon[j], b = polygon[i];
    if (onSegment(a, b, p)) return true;
    if ((a.y > p.y) !== (b.y > p.y) && p.x < (b.x - a.x) * (p.y - a.y) / (b.y - a.y) + a.x) inside = !inside;
  }
  return inside;
}
export function selectLassoStrokes(strokes: InkStroke[], polygon: InkPoint[]): InkStroke[] {
  if (polygon.length < 3) return [];
  const area = Math.abs(polygon.reduce((sum, p, i) => {
    const next = polygon[(i + 1) % polygon.length]; return sum + p.x * next.y - next.x * p.y;
  }, 0)) / 2;
  if (area < 0.00001) return [];
  return strokes.filter((stroke) => stroke.tool === "PEN" && (
    stroke.points.some((p) => pointInLasso(p, polygon)) || stroke.points.some((a, index) => {
      const b = stroke.points[index + 1];
      return b && polygon.some((c, j) => {
        const d = polygon[(j + 1) % polygon.length];
        return (cross(a, b, c) * cross(a, b, d) < 0 && cross(c, d, a) * cross(c, d, b) < 0)
          || onSegment(a, b, c) || onSegment(c, d, a);
      });
    })
  ));
}
