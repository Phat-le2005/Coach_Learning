import type { InkStroke } from "@/lib/api/contracts";
import { getOcrPenStrokes } from "./ocr-ink";

const A4_WIDTH = 794;
const A4_HEIGHT = 1123;

export interface InkBounds {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

export interface PageOcrRegion {
  id: string;
  strokes: InkStroke[];
  bounds: InkBounds;
}

export interface SegmentationOptions {
  algorithm?: "v1" | "v2";
}

interface StrokeEntry {
  stroke: InkStroke;
  bounds: InkBounds;
  originalIndex: number;
  center: number;
}

function strokeBounds(stroke: InkStroke): InkBounds {
  const xs = stroke.points.map((point) => point.x);
  const ys = stroke.points.map((point) => point.y);
  return {
    left: Math.min(...xs),
    top: Math.min(...ys),
    right: Math.max(...xs),
    bottom: Math.max(...ys),
  };
}

function region(id: string, strokes: InkStroke[]): PageOcrRegion {
  const boxes = strokes.map(strokeBounds);
  return {
    id,
    strokes,
    bounds: {
      left: Math.min(...boxes.map((box) => box.left)),
      top: Math.min(...boxes.map((box) => box.top)),
      right: Math.max(...boxes.map((box) => box.right)),
      bottom: Math.max(...boxes.map((box) => box.bottom)),
    },
  };
}

function computeHorizontalOverlap(boxA: InkBounds, boxB: InkBounds): number {
  const overlap = Math.max(0, Math.min(boxA.right, boxB.right) - Math.max(boxA.left, boxB.left));
  const minWidth = Math.min(boxA.right - boxA.left, boxB.right - boxB.left);
  return minWidth > 0 ? overlap / minWidth : 0;
}

/**
 * Geometric Fraction Bar Detector with Minus Sign Guard.
 * Strict conditions:
 * 1. Physical aspect ratio in pixel space >= 3.8 and height <= medianHeight * 0.85.
 * 2. Equals sign precedence: Two parallel horizontal strokes close together form '=', never a fraction bar.
 * 3. Bounded vertical gap: Must have overlapping strokes BOTH above (numerator) AND below (denominator).
 * 4. Width span ratio: The bar must span across the terms it divides (wPx >= 0.50 * blockWidth).
 *    An interlinear minus '-' or bullet between two full lines has wPx << line width, preventing false merges.
 */
function isTrueFractionBar(
  barEntry: StrokeEntry,
  allEntries: StrokeEntry[],
  medianHeight: number,
): boolean {
  const wPx = (barEntry.bounds.right - barEntry.bounds.left) * A4_WIDTH;
  const hPx = (barEntry.bounds.bottom - barEntry.bounds.top) * A4_HEIGHT;
  const aspectRatio = wPx / Math.max(0.5, hPx);
  const medianHeightPx = medianHeight * A4_HEIGHT;

  if (aspectRatio < 3.8 || hPx > Math.max(8, medianHeightPx * 0.6) || wPx < 14) {
    return false;
  }

  // 1. Equals sign '=' check (parallel horizontal bars)
  for (const other of allEntries) {
    if (other.stroke.id === barEntry.stroke.id) continue;
    const oWPx = (other.bounds.right - other.bounds.left) * A4_WIDTH;
    const oHPx = (other.bounds.bottom - other.bounds.top) * A4_HEIGHT;
    const oRatio = oWPx / Math.max(0.5, oHPx);
    if (oRatio >= 3.5 && oHPx <= medianHeightPx * 0.6) {
      const vDistPx = Math.abs(other.center - barEntry.center) * A4_HEIGHT;
      const hOverlap = computeHorizontalOverlap(barEntry.bounds, other.bounds);
      const lenDiff = Math.abs(oWPx - wPx) / Math.max(wPx, oWPx);
      if (vDistPx < 14 && hOverlap > 0.65 && lenDiff < 0.35) {
        return false; // Equals sign pair, not a fraction bar
      }
    }
  }

  // 2. Numerator and Denominator detection
  const barY = barEntry.center;
  const maxGap = Math.max(0.045, medianHeight * 2.2);
  const numerators: StrokeEntry[] = [];
  const denominators: StrokeEntry[] = [];

  for (const other of allEntries) {
    if (other.stroke.id === barEntry.stroke.id) continue;
    const hOverlap = computeHorizontalOverlap(barEntry.bounds, other.bounds);
    if (hOverlap > 0.35) {
      const vDist = other.center - barY;
      if (vDist < -0.004 && Math.abs(vDist) <= maxGap) {
        numerators.push(other);
      } else if (vDist > 0.004 && Math.abs(vDist) <= maxGap) {
        denominators.push(other);
      }
    }
  }

  if (numerators.length === 0 || denominators.length === 0) {
    return false;
  }

  // 3. Fraction Bar Width Span Ratio
  // A true fraction bar must cover a significant portion of the terms it separates.
  // A minus sign between two long lines has wPx << totalLineWPx.
  const totalNumWPx =
    (Math.max(...numerators.map((n) => n.bounds.right)) -
      Math.min(...numerators.map((n) => n.bounds.left))) *
    A4_WIDTH;
  const totalDenWPx =
    (Math.max(...denominators.map((d) => d.bounds.right)) -
      Math.min(...denominators.map((d) => d.bounds.left))) *
    A4_WIDTH;

  if (wPx < totalNumWPx * 0.5 && wPx < totalDenWPx * 0.5) {
    return false; // Interlinear minus or bullet between two full lines!
  }

  return true;
}

/**
 * Dynamic Column Gutter Detector
 * Scans for contiguous vertical white-space gutters based on horizontal density profile,
 * while preventing false two-column splits on single-column indented equations.
 */
function detectDynamicColumnGutter(entries: StrokeEntry[]): number | null {
  if (entries.length < 4) return null;

  const BINS = 100;
  const X_MIN = 0.15;
  const X_MAX = 0.85;
  const binWidth = (X_MAX - X_MIN) / BINS;
  const occupancy = new Array(BINS).fill(0);

  for (const e of entries) {
    const sB = Math.max(0, Math.floor((e.bounds.left - X_MIN) / binWidth));
    const eB = Math.min(BINS - 1, Math.floor((e.bounds.right - X_MIN) / binWidth));
    for (let b = sB; b <= eB; b++) {
      occupancy[b]++;
    }
  }

  let bestStart = -1;
  let maxLen = 0;
  let curStart = -1;
  let curLen = 0;

  for (let i = 0; i < BINS; i++) {
    if (occupancy[i] === 0) {
      if (curStart === -1) curStart = i;
      curLen++;
    } else {
      if (curLen > maxLen) {
        maxLen = curLen;
        bestStart = curStart;
      }
      curStart = -1;
      curLen = 0;
    }
  }
  if (curLen > maxLen) {
    maxLen = curLen;
    bestStart = curStart;
  }

  const minGutterBins = Math.round(0.035 / binWidth); // At least ~35px gap
  if (maxLen >= minGutterBins) {
    const gutterLeft = X_MIN + bestStart * binWidth;
    const gutterRight = gutterLeft + maxLen * binWidth;
    const gutterCenter = (gutterLeft + gutterRight) / 2;
    const gutterWidthPx = (gutterRight - gutterLeft) * A4_WIDTH;

    const leftStrokes = entries.filter((e) => e.bounds.right <= gutterLeft);
    const rightStrokes = entries.filter((e) => e.bounds.left >= gutterRight);

    if (leftStrokes.length >= 2 && rightStrokes.length >= 2) {
      const leftWPx =
        (Math.max(...leftStrokes.map((e) => e.bounds.right)) -
          Math.min(...leftStrokes.map((e) => e.bounds.left))) *
        A4_WIDTH;
      const rightWPx =
        (Math.max(...rightStrokes.map((e) => e.bounds.right)) -
          Math.min(...rightStrokes.map((e) => e.bounds.left))) *
        A4_WIDTH;

      // Guard 1: A column gutter cannot be disproportionately wider than the text column.
      // In indented equations, the gap between LHS and RHS is often 2-3x wider than LHS itself.
      if (gutterWidthPx > leftWPx * 1.25) {
        return null;
      }

      // Guard 2: Both columns must be genuine columns of writing (at least 65px wide)
      if (leftWPx >= 65 && rightWPx >= 65) {
        return gutterCenter;
      }
    }
  }

  return null;
}

/**
 * Segment strokes within a single column (or single-column page).
 */
function segmentColumnStrokes(entries: StrokeEntry[], medianHeight: number): PageOcrRegion[] {
  if (!entries.length) return [];
  const tolerance = Math.max(0.018, Math.min(0.045, medianHeight * 1.45));

  // 1. First Pass: Detect and bind true fraction bars with numerator and denominator
  const fractionBars = entries.filter((e) => isTrueFractionBar(e, entries, medianHeight));
  const assigned = new Set<string>();
  const clusters: StrokeEntry[][] = [];

  for (const bar of fractionBars) {
    if (assigned.has(bar.stroke.id)) continue;
    const group = [bar];
    assigned.add(bar.stroke.id);

    for (const e of entries) {
      if (assigned.has(e.stroke.id)) continue;
      const hOverlap = computeHorizontalOverlap(bar.bounds, e.bounds);
      const vDistance = Math.abs(bar.center - e.center);
      if (hOverlap > 0.35 && vDistance <= medianHeight * 1.9) {
        group.push(e);
        assigned.add(e.stroke.id);
      }
    }
    clusters.push(group);
  }

  // 2. Second Pass: Unassigned strokes form their own individual base clusters
  for (const e of entries) {
    if (!assigned.has(e.stroke.id)) {
      clusters.push([e]);
      assigned.add(e.stroke.id);
    }
  }

  // 3. Third Pass: Cluster row grouping based on vertical tolerance
  const clusterEntries = clusters.map((items) => {
    const allStrokes = items.map((it) => it.stroke);
    const reg = region(items[0].stroke.id, allStrokes);
    return {
      items,
      reg,
      center: (reg.bounds.top + reg.bounds.bottom) / 2,
    };
  });

  const rows: Array<typeof clusterEntries> = [];
  const medianHeightPx = medianHeight * A4_HEIGHT;

  for (const entry of clusterEntries.sort(
    (a, b) => a.center - b.center || a.reg.bounds.left - b.reg.bounds.left,
  )) {
    const matching = rows
      .map((rowItems, index) => {
        const avgCenter = rowItems.reduce((sum, item) => sum + item.center, 0) / rowItems.length;
        return { index, distance: Math.abs(entry.center - avgCenter), rowItems };
      })
      .filter((item) => {
        if (item.distance > tolerance) return false;
        // Chaining Guard: Prevent single-linkage chaining between vertically distinct lines
        const rowTop = Math.min(...item.rowItems.map((it) => it.reg.bounds.top));
        const rowBottom = Math.max(...item.rowItems.map((it) => it.reg.bounds.bottom));
        const newTop = Math.min(rowTop, entry.reg.bounds.top);
        const newBottom = Math.max(rowBottom, entry.reg.bounds.bottom);
        const expandedHeightPx = (newBottom - newTop) * A4_HEIGHT;
        const hasFraction =
          item.rowItems.some((it) => it.items.length > 1) || entry.items.length > 1;
        if (!hasFraction && expandedHeightPx > Math.max(34, medianHeightPx * 2.0)) {
          return false;
        }
        return true;
      })
      .sort((a, b) => a.distance - b.distance)[0];

    if (matching) rows[matching.index].push(entry);
    else rows.push([entry]);
  }

  return rows
    .map((rItems) => {
      const allClusterStrokes = rItems.flatMap((c) => c.items.map((it) => it.stroke));
      // Strictly preserve original chronological drawing order within the region
      const sorted = allClusterStrokes.sort((a, b) => {
        const idxA = entries.find((e) => e.stroke.id === a.id)?.originalIndex ?? 0;
        const idxB = entries.find((e) => e.stroke.id === b.id)?.originalIndex ?? 0;
        return idxA - idxB;
      });
      return region(sorted[0].id, sorted);
    })
    .sort((a, b) => a.bounds.top - b.bounds.top);
}

/**
 * Segmentation V2 (Layout-aware with dynamic gutter and fraction protection).
 */
export function segmentPageInk_v2(strokes: InkStroke[]): PageOcrRegion[] {
  const pen = getOcrPenStrokes(strokes);
  if (!pen.length) return [];

  const entries: StrokeEntry[] = pen.map((stroke, originalIndex) => {
    const bounds = strokeBounds(stroke);
    return { stroke, bounds, originalIndex, center: (bounds.top + bounds.bottom) / 2 };
  });

  // Filter out tiny punctuation/dots/dashes (< 8px) to compute truthful median character height
  const charHeights = entries
    .map((entry) => entry.bounds.bottom - entry.bounds.top)
    .filter((height) => height * A4_HEIGHT >= 8)
    .sort((a, b) => a - b);
  const medianHeight = charHeights.length
    ? charHeights[Math.floor(charHeights.length / 2)]
    : 20 / A4_HEIGHT;

  // Check for dynamic 2-column gutter
  const gutterCenter = detectDynamicColumnGutter(entries);

  if (gutterCenter !== null) {
    const leftStrokes = entries.filter((e) => e.bounds.right <= gutterCenter);
    const rightStrokes = entries.filter((e) => e.bounds.left >= gutterCenter);

    // Natural reading order: Left Column top-to-bottom, then Right Column top-to-bottom
    const leftRegions = segmentColumnStrokes(leftStrokes, medianHeight);
    const rightRegions = segmentColumnStrokes(rightStrokes, medianHeight);
    return [...leftRegions, ...rightRegions];
  }

  return segmentColumnStrokes(entries, medianHeight);
}

/**
 * Segmentation V1 (Baseline heuristic from previous release).
 * Kept for parity verification, fallback, and regression comparison.
 */
export function segmentPageInk_v1(strokes: InkStroke[]): PageOcrRegion[] {
  const pen = getOcrPenStrokes(strokes);
  if (!pen.length) return [];
  const entries: StrokeEntry[] = pen.map((stroke, originalIndex) => {
    const bounds = strokeBounds(stroke);
    return { stroke, bounds, originalIndex, center: (bounds.top + bounds.bottom) / 2 };
  });
  const heights = entries
    .map((entry) => entry.bounds.bottom - entry.bounds.top)
    .filter((height) => height > 0)
    .sort((a, b) => a - b);
  const medianHeight = heights.length ? heights[Math.floor(heights.length / 2)] : 0;
  const tolerance = Math.max(0.018, Math.min(0.04, medianHeight * 1.4));
  const rows: StrokeEntry[][] = [];
  for (const entry of [...entries].sort(
    (a, b) => a.center - b.center || a.bounds.left - b.bounds.left || a.originalIndex - b.originalIndex,
  )) {
    const matching = rows
      .map((items, index) => ({
        index,
        distance: Math.abs(entry.center - items.reduce((sum, item) => sum + item.center, 0) / items.length),
      }))
      .filter((item) => item.distance <= tolerance)
      .sort((a, b) => a.distance - b.distance || a.index - b.index)[0];
    if (matching) rows[matching.index].push(entry);
    else rows.push([entry]);
  }
  return rows
    .map((items) => items.sort((a, b) => a.originalIndex - b.originalIndex))
    .sort((a, b) => Math.min(...a.map((item) => item.center)) - Math.min(...b.map((item) => item.center)))
    .map((items) => region(items[0].stroke.id, items.map((item) => item.stroke)));
}

/**
 * Public Entry Point for Page Ink Segmentation.
 * Defaults to "v2" with fallback option to "v1".
 */
export function segmentPageInk(
  strokes: InkStroke[],
  options?: SegmentationOptions,
): PageOcrRegion[] {
  if (options?.algorithm === "v1") {
    return segmentPageInk_v1(strokes);
  }
  return segmentPageInk_v2(strokes);
}

/** Merge neighbors and restore the original pen stroke order. */
export function mergePageOcrRegions(
  regions: PageOcrRegion[],
  index: number,
  pageStrokes: InkStroke[],
): PageOcrRegion[] {
  if (index < 0 || index >= regions.length - 1) return regions;
  const ids = new Set([...regions[index].strokes, ...regions[index + 1].strokes].map((stroke) => stroke.id));
  const merged = region(
    regions[index].id,
    getOcrPenStrokes(pageStrokes).filter((stroke) => ids.has(stroke.id)),
  );
  return [...regions.slice(0, index), merged, ...regions.slice(index + 2)];
}

/** Explicit cut: stacked formulae and tall symbols cannot be split reliably by line spacing. */
export function splitPageOcrRegion(
  regions: PageOcrRegion[],
  index: number,
  cutY: number,
): PageOcrRegion[] {
  const selected = regions[index];
  if (!selected || !Number.isFinite(cutY)) return regions;
  const upper = selected.strokes.filter((stroke) => {
    const box = strokeBounds(stroke);
    return (box.top + box.bottom) / 2 < cutY;
  });
  const upperIds = new Set(upper.map((stroke) => stroke.id));
  const lower = selected.strokes.filter((stroke) => !upperIds.has(stroke.id));
  if (!upper.length || !lower.length) return regions;
  return [
    ...regions.slice(0, index),
    region(selected.id + ":a", upper),
    region(selected.id + ":b", lower),
    ...regions.slice(index + 1),
  ];
}
