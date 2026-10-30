import type { InkStroke } from "@/lib/api/contracts";
import { getOcrPenStrokes } from "./ocr-ink";

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
 * A fraction bar must have strokes BOTH above it (numerator) AND below it (denominator).
 * A horizontal minus sign '-' or dash has strokes only to its left/right, preventing false merges.
 */
function isTrueFractionBar(
  barEntry: StrokeEntry,
  allEntries: StrokeEntry[],
  medianHeight: number,
): boolean {
  const w = barEntry.bounds.right - barEntry.bounds.left;
  const h = barEntry.bounds.bottom - barEntry.bounds.top;
  const aspectRatio = w / Math.max(0.0005, h);

  // Must be relatively wide and thin compared to median character height
  if (aspectRatio < 3.8 || h > medianHeight * 0.88 || w < 0.015) {
    return false;
  }

  const barY = barEntry.center;
  const maxVerticalGap = Math.max(0.045, medianHeight * 2.2);

  let hasNumerator = false;
  let hasDenominator = false;

  for (const other of allEntries) {
    if (other.stroke.id === barEntry.stroke.id) continue;
    const hOverlap = computeHorizontalOverlap(barEntry.bounds, other.bounds);
    if (hOverlap > 0.35) {
      const vDist = other.center - barY;
      if (vDist < -0.005 && Math.abs(vDist) <= maxVerticalGap) {
        hasNumerator = true;
      } else if (vDist > 0.005 && Math.abs(vDist) <= maxVerticalGap) {
        hasDenominator = true;
      }
    }
    if (hasNumerator && hasDenominator) return true;
  }

  return false;
}

/**
 * Dynamic Column Gutter Detector
 * Finds contiguous vertical white-space gutters based on horizontal density profile,
 * supporting off-center columns (e.g. 40/60 split) instead of hardcoding x=0.5.
 */
function detectDynamicColumnGutter(entries: StrokeEntry[]): number | null {
  if (entries.length < 4) return null;

  const BINS = 100;
  const X_MIN = 0.20;
  const X_MAX = 0.80;
  const binWidth = (X_MAX - X_MIN) / BINS;
  const occupancy = new Array(BINS).fill(0);

  for (const e of entries) {
    const startBin = Math.max(0, Math.floor((e.bounds.left - X_MIN) / binWidth));
    const endBin = Math.min(BINS - 1, Math.floor((e.bounds.right - X_MIN) / binWidth));
    for (let b = startBin; b <= endBin; b++) {
      occupancy[b]++;
    }
  }

  let bestGutterStart = -1;
  let maxGutterLen = 0;
  let curStart = -1;
  let curLen = 0;

  for (let i = 0; i < BINS; i++) {
    if (occupancy[i] === 0) {
      if (curStart === -1) curStart = i;
      curLen++;
    } else {
      if (curLen > maxGutterLen) {
        maxGutterLen = curLen;
        bestGutterStart = curStart;
      }
      curStart = -1;
      curLen = 0;
    }
  }
  if (curLen > maxGutterLen) {
    maxGutterLen = curLen;
    bestGutterStart = curStart;
  }

  const minGutterBins = Math.round(0.035 / binWidth); // At least ~35px gap
  if (maxGutterLen >= minGutterBins) {
    const gutterLeft = X_MIN + bestGutterStart * binWidth;
    const gutterRight = gutterLeft + maxGutterLen * binWidth;
    const gutterCenter = (gutterLeft + gutterRight) / 2;

    const leftStrokes = entries.filter((e) => e.bounds.right <= gutterCenter);
    const rightStrokes = entries.filter((e) => e.bounds.left >= gutterCenter);

    // Both columns must have substantial content (at least 2 strokes each)
    if (leftStrokes.length >= 2 && rightStrokes.length >= 2) {
      const leftSpan =
        Math.max(...leftStrokes.map((e) => e.bounds.right)) -
        Math.min(...leftStrokes.map((e) => e.bounds.left));
      const rightSpan =
        Math.max(...rightStrokes.map((e) => e.bounds.right)) -
        Math.min(...rightStrokes.map((e) => e.bounds.left));

      // A genuine column of handwritten math must span at least 8% of page width (~65px)
      // Otherwise it's just scattered marks or single words on the same horizontal line.
      if (leftSpan >= 0.08 && rightSpan >= 0.08) {
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
      // Strictly bind only vertically overlapping strokes within 1.9 * medianHeight
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
  for (const entry of clusterEntries.sort(
    (a, b) => a.center - b.center || a.reg.bounds.left - b.reg.bounds.left,
  )) {
    const matching = rows
      .map((rowItems, index) => {
        const avgCenter = rowItems.reduce((sum, item) => sum + item.center, 0) / rowItems.length;
        return { index, distance: Math.abs(entry.center - avgCenter) };
      })
      .filter((item) => item.distance <= tolerance)
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

  const heights = entries
    .map((entry) => entry.bounds.bottom - entry.bounds.top)
    .filter((height) => height > 0)
    .sort((a, b) => a - b);
  const medianHeight = heights.length ? heights[Math.floor(heights.length / 2)] : 0.02;

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
