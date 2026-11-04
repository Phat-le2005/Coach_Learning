import type { InkStroke } from "@/lib/api/contracts";
import type { InkBounds } from "./page-ocr";
import { getOcrPenStrokes } from "./ocr-ink";

/**
 * Conservative, read-only structural proposal. An expression unit is NOT a
 * solution step and contains no recognized LaTeX or mathematical correction.
 * Only definite integrals with BOTH limits and a right-hand body are supported
 * in this first increment. Unknown layouts fall back to the existing flow.
 */
export interface IntegralExpressionUnit {
  kind: "INTEGRAL";
  id: string;
  sourceStrokeIds: string[];
  integralStrokeId: string;
  upperLimitStrokeIds: string[];
  lowerLimitStrokeIds: string[];
  bodyStrokeIds: string[];
  bounds: InkBounds;
  reasons: string[];
}

const A4_WIDTH = 794;
const A4_HEIGHT = 1123;

interface Geometry {
  stroke: InkStroke;
  bounds: InkBounds;
  widthPx: number;
  heightPx: number;
  centerX: number;
}

function boundsOfStroke(stroke: InkStroke): InkBounds | null {
  if (stroke.points.length === 0) return null;
  let left = Infinity, right = -Infinity, top = Infinity, bottom = -Infinity;
  for (const point of stroke.points) {
    if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) return null;
    left = Math.min(left, point.x);
    right = Math.max(right, point.x);
    top = Math.min(top, point.y);
    bottom = Math.max(bottom, point.y);
  }
  return { left, right, top, bottom };
}

function unionBounds(geoms: readonly Geometry[]): InkBounds {
  return {
    left: Math.min(...geoms.map((g) => g.bounds.left)),
    right: Math.max(...geoms.map((g) => g.bounds.right)),
    top: Math.min(...geoms.map((g) => g.bounds.top)),
    bottom: Math.max(...geoms.map((g) => g.bounds.bottom)),
  };
}

function isIntegralShaped(geom: Geometry, medianHeight: number): boolean {
  const { points } = geom.stroke;
  if (points.length < 8 || geom.heightPx < 65 ||
      geom.heightPx < medianHeight * 2.1 || geom.widthPx < 9) return false;
  const ratio = geom.widthPx / geom.heightPx;
  if (ratio < 0.10 || ratio > 0.75) return false;
  const first = points[0];
  const last = points[points.length - 1];
  const width = geom.bounds.right - geom.bounds.left;
  const height = geom.bounds.bottom - geom.bounds.top;
  if (width <= 0 || height <= 0) return false;
  // An elongated integral stroke often runs from top-right to bottom-left,
  // unlike a brace whose endpoints return to roughly the same horizontal x.
  return Math.abs(first.x - last.x) / width >= 0.58 &&
    Math.abs(first.y - last.y) / height >= 0.65;
}

function median(values: readonly number[]): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function pickNearest(
  geoms: readonly Geometry[],
  targetX: number,
  anchorY: number,
): Geometry | undefined {
  return [...geoms].sort((a, b) => {
    const sa = Math.abs(a.centerX - targetX) + Math.abs(a.bounds.top - anchorY) * 0.2;
    const sb = Math.abs(b.centerX - targetX) + Math.abs(b.bounds.top - anchorY) * 0.2;
    return sa - sb;
  })[0];
}

/** Builds proposals only: existing region and step segmentation is unchanged. */
export function proposeIntegralExpressionUnits(
  input: readonly InkStroke[],
): IntegralExpressionUnit[] {
  const strokes = getOcrPenStrokes([...input]);
  const geoms: Geometry[] = strokes.flatMap((stroke) => {
    const bounds = boundsOfStroke(stroke);
    if (!bounds) return [];
    return [{
      stroke,
      bounds,
      widthPx: (bounds.right - bounds.left) * A4_WIDTH,
      heightPx: (bounds.bottom - bounds.top) * A4_HEIGHT,
      centerX: (bounds.left + bounds.right) / 2,
    }];
  });
  if (geoms.length < 4) return [];
  const med = median(geoms.map((g) => g.heightPx).filter((h) => h > 2));
  const consumed = new Set<string>();
  const units: IntegralExpressionUnit[] = [];

  // Spatial scanning is independent of the chronological stroke order.
  for (const anchor of [...geoms].sort((a, b) => a.bounds.left - b.bounds.left)) {
    if (consumed.has(anchor.stroke.id) || !isIntegralShaped(anchor, med)) continue;
    const h = anchor.bounds.bottom - anchor.bounds.top;
    const width = anchor.bounds.right - anchor.bounds.left;

    const others = geoms.filter((g) =>
      g.stroke.id !== anchor.stroke.id && !consumed.has(g.stroke.id));

    const upper = pickNearest(others.filter((g) =>
      g.bounds.bottom < anchor.bounds.top + h * 0.08 &&
      g.bounds.top >= anchor.bounds.top - h * 0.72 &&
      Math.abs(g.centerX - anchor.bounds.right) <= Math.max(0.05, width * 0.7)
    ), anchor.bounds.right, anchor.bounds.top);

    const lower = pickNearest(others.filter((g) =>
      g.stroke.id !== upper?.stroke.id &&
      g.bounds.top > anchor.bounds.bottom + h * 0.07 &&
      g.bounds.top <= anchor.bounds.bottom + h * 0.70 &&
      Math.abs(g.centerX - anchor.bounds.left) <= Math.max(0.06, width * 0.85)
    ), anchor.bounds.left, anchor.bounds.bottom);

    // Not enough evidence for a definite integral, so make no proposal.
    if (!upper || !lower) continue;

    const possibleBody = others.filter((g) =>
      g.stroke.id !== upper.stroke.id && g.stroke.id !== lower.stroke.id &&
      g.bounds.left >= anchor.bounds.right + 0.004 &&
      g.bounds.bottom > anchor.bounds.top + h * 0.30 &&
      g.bounds.top <= anchor.bounds.bottom + 0.045
    ).sort((a, b) => a.bounds.left - b.bounds.left);

    const body: Geometry[] = [];
    let rightmost = anchor.bounds.right;
    for (const g of possibleBody) {
      if (g.bounds.left - rightmost > (body.length ? 0.055 : 0.08)) break;
      body.push(g);
      rightmost = Math.max(rightmost, g.bounds.right);
    }
    if (body.length === 0) continue;

    const selected = [anchor, upper, lower, ...body];
    const selectedIds = new Set(selected.map((g) => g.stroke.id));
    if (selectedIds.size !== selected.length) continue;
    const sourceStrokeIds = strokes
      .filter((stroke) => selectedIds.has(stroke.id))
      .map((stroke) => stroke.id);

    units.push({
      kind: "INTEGRAL",
      id: `integral-${anchor.stroke.id}`,
      sourceStrokeIds,
      integralStrokeId: anchor.stroke.id,
      upperLimitStrokeIds: [upper.stroke.id],
      lowerLimitStrokeIds: [lower.stroke.id],
      bodyStrokeIds: body.map((g) => g.stroke.id),
      bounds: unionBounds(selected),
      reasons: [
        "Tall continuous integral-like mark",
        "Distinct upper and lower limit strokes",
        "Right-adjacent expression ink",
        "Geometry-only proposal; recognition not verified",
      ],
    });
    selectedIds.forEach((id) => consumed.add(id));
  }
  return units;
}
